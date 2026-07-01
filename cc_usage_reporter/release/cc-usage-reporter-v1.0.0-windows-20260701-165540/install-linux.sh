#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$BASE_DIR/scripts/linux/install_systemd_user.sh"
bash "$BASE_DIR/scripts/linux/install_systemd_user.sh" "$HOME/.config/cc-switch/usage_reporter.json"
