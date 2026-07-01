#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-$HOME/Library/Application Support/cc-switch/usage_reporter.json}"
SCRIPT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$SCRIPT_DIR/service_templates/macos/com.local.cc-usage-reporter.plist"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_FILE="$TARGET_DIR/com.local.cc-usage-reporter.plist"
LOG_DIR="$HOME/.cc-switch"

mkdir -p "$TARGET_DIR" "$LOG_DIR"
cp "$TEMPLATE" "$TARGET_FILE"
sed -i '' "s|__CONFIG_PATH__|$CONFIG_PATH|g" "$TARGET_FILE"
sed -i '' "s|__STDOUT_PATH__|$LOG_DIR/cc-usage-reporter.stdout.log|g" "$TARGET_FILE"
sed -i '' "s|__STDERR_PATH__|$LOG_DIR/cc-usage-reporter.stderr.log|g" "$TARGET_FILE"

launchctl unload "$TARGET_FILE" >/dev/null 2>&1 || true
launchctl load "$TARGET_FILE"

echo "Installed and loaded: $TARGET_FILE"
launchctl list | grep cc-usage-reporter || true
