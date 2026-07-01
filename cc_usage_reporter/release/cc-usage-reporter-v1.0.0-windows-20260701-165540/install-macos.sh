#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$BASE_DIR/scripts/macos/install_launchd.sh"
bash "$BASE_DIR/scripts/macos/install_launchd.sh" "$HOME/Library/Application Support/cc-switch/usage_reporter.json"
