#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller
pyinstaller cc-usage-reporter.spec
pyinstaller cc-usage-reporter-gui.spec
mkdir -p dist/linux-package
cp -r dist/cc-usage-reporter* dist/linux-package/ 2>/dev/null || true
tar -czf dist/cc-usage-reporter-linux.tar.gz -C dist linux-package
echo "Build complete: dist/cc-usage-reporter-linux.tar.gz"

python3 -m cc_usage_reporter deps-check || echo "tray optional deps check failed; continue if you only need CLI/daemon"
python3 -m cc_usage_reporter release-pack
