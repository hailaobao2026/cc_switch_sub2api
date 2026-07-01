package main

import (
	"context"
	"crypto/subtle"
	"database/sql"
	"embed"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	_ "github.com/lib/pq"
)

//go:embed migrations/*.sql
var migrationsFS embed.FS

type Config struct {
	ListenAddr     string   `json:"listen_addr"`
	DatabaseURL    string   `json:"database_url"`
	ReportToken    string   `json:"report_token"`
	AutoMigrate    bool     `json:"auto_migrate"`
	AllowedSources []string `json:"allowed_sources"`
	MaxItems       int      `json:"max_items"`
}

type Server struct {
	cfg            Config
	db             *sql.DB
	allowedSources map[string]struct{}
}

type UsageReportRequest struct {
	Username    string            `json:"username"`
	Email       string            `json:"email"`
	Source      string            `json:"source"`
	Granularity string            `json:"granularity"`
	Items       []UsageReportItem `json:"items"`
}

type UsageReportItem struct {
	Date                string  `json:"date"`
	AppType             string  `json:"app_type"`
	Model               string  `json:"model"`
	RequestModel        string  `json:"request_model"`
	RequestCount        int     `json:"request_count"`
	SuccessCount        int     `json:"success_count"`
	InputTokens         int64   `json:"input_tokens"`
	OutputTokens        int64   `json:"output_tokens"`
	CacheReadTokens     int64   `json:"cache_read_tokens"`
	CacheCreationTokens int64   `json:"cache_creation_tokens"`
	TotalCostUSD        float64 `json:"total_cost_usd"`
	DedupKey            string  `json:"dedup_key"`
}

type ExternalUsageDaily struct {
	UserID              int64
	Source              string
	UsageDate           string
	AppType             string
	Model               string
	RequestedModel      string
	RequestCount        int
	SuccessCount        int
	InputTokens         int64
	OutputTokens        int64
	CacheReadTokens     int64
	CacheCreationTokens int64
	TotalCost           string
}

type ReportResponse struct {
	Accepted int   `json:"accepted"`
	Rejected int   `json:"rejected"`
	UserID   int64 `json:"user_id"`
}

type ErrorResponse struct {
	Error string `json:"error"`
}

func main() {
	configPath := flag.String("config", "config.json", "path to sidecar config JSON")
	flag.Parse()

	cfg, err := LoadConfig(*configPath)
	if err != nil {
		log.Fatalf("load config: %v", err)
	}
	if err := cfg.Validate(); err != nil {
		log.Fatalf("invalid config: %v", err)
	}

	db, err := sql.Open("postgres", cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("open database: %v", err)
	}
	defer db.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		log.Fatalf("ping database: %v", err)
	}
	if cfg.AutoMigrate {
		if err := RunMigrations(ctx, db); err != nil {
			log.Fatalf("run migrations: %v", err)
		}
	}

	server := NewServer(cfg, db)
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", server.HandleHealth)
	mux.HandleFunc("POST /api/v1/usage/report", server.HandleReport)

	httpServer := &http.Server{
		Addr:              cfg.ListenAddr,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}
	log.Printf("cc-switch usage sidecar listening on %s", cfg.ListenAddr)
	if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("http server: %v", err)
	}
}

func LoadConfig(path string) (Config, error) {
	cfg := Config{
		ListenAddr:     "127.0.0.1:8788",
		AutoMigrate:    true,
		AllowedSources: []string{"cc-switch"},
		MaxItems:       5000,
	}
	if path != "" {
		data, err := os.ReadFile(path)
		if err != nil && !errors.Is(err, os.ErrNotExist) {
			return cfg, err
		}
		if len(data) > 0 {
			if err := json.Unmarshal(data, &cfg); err != nil {
				return cfg, err
			}
		}
	}
	if value := os.Getenv("CC_USAGE_SIDECAR_LISTEN_ADDR"); value != "" {
		cfg.ListenAddr = value
	}
	if value := os.Getenv("CC_USAGE_SIDECAR_DATABASE_URL"); value != "" {
		cfg.DatabaseURL = value
	}
	if value := os.Getenv("CC_USAGE_SIDECAR_REPORT_TOKEN"); value != "" {
		cfg.ReportToken = value
	}
	if value := os.Getenv("CC_USAGE_SIDECAR_AUTO_MIGRATE"); value != "" {
		cfg.AutoMigrate = parseBool(value)
	}
	return cfg, nil
}

func (c Config) Validate() error {
	if strings.TrimSpace(c.ListenAddr) == "" {
		return errors.New("listen_addr is required")
	}
	if strings.TrimSpace(c.DatabaseURL) == "" {
		return errors.New("database_url is required")
	}
	if strings.TrimSpace(c.ReportToken) == "" {
		return errors.New("report_token is required")
	}
	if len(c.ReportToken) < 20 {
		return errors.New("report_token should be at least 20 characters")
	}
	if c.MaxItems <= 0 {
		return errors.New("max_items must be positive")
	}
	return nil
}

func parseBool(value string) bool {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func RunMigrations(ctx context.Context, db *sql.DB) error {
	entries, err := migrationsFS.ReadDir("migrations")
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".sql") {
			continue
		}
		data, err := migrationsFS.ReadFile("migrations/" + entry.Name())
		if err != nil {
			return err
		}
		if _, err := db.ExecContext(ctx, string(data)); err != nil {
			return fmt.Errorf("%s: %w", entry.Name(), err)
		}
		log.Printf("migration applied: %s", entry.Name())
	}
	return nil
}

func NewServer(cfg Config, db *sql.DB) *Server {
	allowed := make(map[string]struct{}, len(cfg.AllowedSources))
	for _, source := range cfg.AllowedSources {
		source = strings.TrimSpace(source)
		if source != "" {
			allowed[source] = struct{}{}
		}
	}
	return &Server{cfg: cfg, db: db, allowedSources: allowed}
}

func (s *Server) HandleHealth(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()
	if err := s.db.PingContext(ctx); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) HandleReport(w http.ResponseWriter, r *http.Request) {
	if !s.authorized(r) {
		writeJSON(w, http.StatusUnauthorized, ErrorResponse{Error: "invalid report token"})
		return
	}
	defer r.Body.Close()

	var req UsageReportRequest
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid json: " + err.Error()})
		return
	}
	if req.Granularity != "" && req.Granularity != "daily" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "granularity must be daily"})
		return
	}
	if len(req.Items) == 0 {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "items cannot be empty"})
		return
	}
	if len(req.Items) > s.cfg.MaxItems {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: fmt.Sprintf("items exceeds max_items=%d", s.cfg.MaxItems)})
		return
	}

	source := strings.TrimSpace(req.Source)
	if source == "" {
		source = "cc-switch"
	}
	if !s.sourceAllowed(source) {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "source is not allowed"})
		return
	}

	userID, err := s.ResolveUserID(r.Context(), req.Username, req.Email)
	if err != nil {
		writeJSON(w, http.StatusForbidden, ErrorResponse{Error: err.Error()})
		return
	}

	rows := make([]ExternalUsageDaily, 0, len(req.Items))
	rejected := 0
	for _, item := range req.Items {
		row, err := normalizeItem(userID, source, item)
		if err != nil {
			rejected++
			continue
		}
		rows = append(rows, row)
	}
	if len(rows) == 0 {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "all items are invalid"})
		return
	}
	accepted, err := s.UpsertBatch(r.Context(), rows)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "write failed: " + err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, ReportResponse{Accepted: accepted, Rejected: rejected, UserID: userID})
}

func (s *Server) authorized(r *http.Request) bool {
	header := strings.TrimSpace(r.Header.Get("Authorization"))
	if header == "" {
		return false
	}
	parts := strings.SplitN(header, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
		return false
	}
	provided := strings.TrimSpace(parts[1])
	if provided == "" {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(provided), []byte(s.cfg.ReportToken)) == 1
}

func (s *Server) sourceAllowed(source string) bool {
	if len(s.allowedSources) == 0 {
		return true
	}
	_, ok := s.allowedSources[source]
	return ok
}

func (s *Server) ResolveUserID(ctx context.Context, username, email string) (int64, error) {
	username = strings.TrimSpace(username)
	email = strings.TrimSpace(email)
	if username == "" && email == "" {
		return 0, errors.New("username or email is required")
	}

	query := `
SELECT id
FROM users
WHERE deleted_at IS NULL
  AND (($1 <> '' AND username = $1) OR ($2 <> '' AND email = $2))
ORDER BY CASE WHEN username = $1 THEN 0 ELSE 1 END
LIMIT 1`
	var userID int64
	if err := s.db.QueryRowContext(ctx, query, username, email).Scan(&userID); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return 0, errors.New("target user not found")
		}
		return 0, fmt.Errorf("resolve target user: %w", err)
	}
	return userID, nil
}

func normalizeItem(userID int64, source string, item UsageReportItem) (ExternalUsageDaily, error) {
	date := strings.TrimSpace(item.Date)
	if _, err := time.Parse("2006-01-02", date); err != nil {
		return ExternalUsageDaily{}, err
	}
	model := strings.TrimSpace(item.Model)
	if model == "" {
		return ExternalUsageDaily{}, errors.New("model is required")
	}
	if item.RequestCount < 0 || item.SuccessCount < 0 || item.SuccessCount > item.RequestCount {
		return ExternalUsageDaily{}, errors.New("invalid request counts")
	}
	if item.InputTokens < 0 || item.OutputTokens < 0 || item.CacheReadTokens < 0 || item.CacheCreationTokens < 0 {
		return ExternalUsageDaily{}, errors.New("token counts must be non-negative")
	}
	appType := strings.TrimSpace(item.AppType)
	if appType == "" {
		appType = "unknown"
	}
	requestModel := strings.TrimSpace(item.RequestModel)
	if requestModel == "" {
		requestModel = model
	}
	return ExternalUsageDaily{
		UserID:              userID,
		Source:              source,
		UsageDate:           date,
		AppType:             appType,
		Model:               model,
		RequestedModel:      requestModel,
		RequestCount:        item.RequestCount,
		SuccessCount:        item.SuccessCount,
		InputTokens:         item.InputTokens,
		OutputTokens:        item.OutputTokens,
		CacheReadTokens:     item.CacheReadTokens,
		CacheCreationTokens: item.CacheCreationTokens,
		TotalCost:           formatCost(item.TotalCostUSD),
	}, nil
}

func formatCost(value float64) string {
	if value < 0 {
		value = 0
	}
	return strconv.FormatFloat(value, 'f', 10, 64)
}

func (s *Server) UpsertBatch(ctx context.Context, rows []ExternalUsageDaily) (int, error) {
	if len(rows) == 0 {
		return 0, nil
	}

	const cols = 13
	valueClauses := make([]string, 0, len(rows))
	args := make([]any, 0, len(rows)*cols)
	for index, row := range rows {
		base := index * cols
		placeholders := make([]string, cols)
		for offset := 0; offset < cols; offset++ {
			placeholders[offset] = fmt.Sprintf("$%d", base+offset+1)
		}
		valueClauses = append(valueClauses, "("+strings.Join(placeholders, ",")+")")
		args = append(args,
			row.UserID,
			row.Source,
			row.UsageDate,
			row.AppType,
			row.Model,
			row.RequestedModel,
			row.RequestCount,
			row.SuccessCount,
			row.InputTokens,
			row.OutputTokens,
			row.CacheReadTokens,
			row.CacheCreationTokens,
			row.TotalCost,
		)
	}

	query := `
INSERT INTO external_usage_daily (
    user_id, source, usage_date, app_type, model, requested_model,
    request_count, success_count, input_tokens, output_tokens,
    cache_read_tokens, cache_creation_tokens, total_cost
) VALUES ` + strings.Join(valueClauses, ",") + `
ON CONFLICT (user_id, source, usage_date, app_type, model, requested_model)
DO UPDATE SET
    request_count          = EXCLUDED.request_count,
    success_count          = EXCLUDED.success_count,
    input_tokens           = EXCLUDED.input_tokens,
    output_tokens          = EXCLUDED.output_tokens,
    cache_read_tokens      = EXCLUDED.cache_read_tokens,
    cache_creation_tokens  = EXCLUDED.cache_creation_tokens,
    total_cost             = EXCLUDED.total_cost,
    reported_at            = now();`
	if _, err := s.db.ExecContext(ctx, query, args...); err != nil {
		return 0, err
	}
	return len(rows), nil
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(value); err != nil {
		log.Printf("write response: %v", err)
	}
}
