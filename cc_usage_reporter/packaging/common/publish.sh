#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller
python3 -m cc_usage_reporter deps-check || echo "tray deps missing; continue if you only need CLI/daemon"

case "$(uname -s)" in
  Linux)
    bash packaging/linux/build.sh
    ;;
  Darwin)
    bash packaging/macos/build.sh
    ;;
  *)
    echo "Unsupported POSIX platform for this script" >&2
    exit 1
    ;;
esac

python3 -m cc_usage_reporter release-pack
