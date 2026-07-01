ARG GOLANG_IMAGE=golang:1.22-alpine
ARG ALPINE_IMAGE=alpine:3.20
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn

FROM ${GOLANG_IMAGE} AS builder

ARG GOPROXY
ARG GOSUMDB
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}

WORKDIR /src

COPY go.mod ./
RUN go mod download

COPY . ./
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/cc-usage-sidecar .

FROM ${ALPINE_IMAGE}

RUN apk add --no-cache ca-certificates tzdata wget && rm -rf /var/cache/apk/*
RUN addgroup -g 1000 sidecar && adduser -u 1000 -G sidecar -s /bin/sh -D sidecar

WORKDIR /app
COPY --from=builder /out/cc-usage-sidecar /app/cc-usage-sidecar
COPY config.example.json /app/config.example.json

USER sidecar
EXPOSE 8788

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -q -T 5 -O /dev/null http://localhost:8788/healthz || exit 1

ENTRYPOINT ["/app/cc-usage-sidecar"]
CMD ["-config", "/app/config.json"]
