#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-$HOME/.config/cc-switch/usage_reporter.json}"
SERVICE_NAME="cc-usage-reporter.service"
TARGET_DIR="$HOME/.config/systemd/user"
SCRIPT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$SCRIPT_DIR/service_templates/linux/cc-usage-reporter.service"
TARGET_FILE="$TARGET_DIR/$SERVICE_NAME"

mkdir -p "$TARGET_DIR" "$HOME/.local/bin" "$HOME/.local/share/cc-usage-reporter"
cp "$TEMPLATE" "$TARGET_FILE"
sed -i "s|%h/.local/bin/cc-usage-reporter|$(command -v python3) -m cc_usage_reporter|g" "$TARGET_FILE"
sed -i "s|%h/.config/cc-switch/usage_reporter.json|$CONFIG_PATH|g" "$TARGET_FILE"

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"

echo "Installed and started: $SERVICE_NAME"
systemctl --user status "$SERVICE_NAME" --no-pager || true
