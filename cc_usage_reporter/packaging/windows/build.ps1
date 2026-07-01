$ErrorActionPreference = "Stop"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
pyinstaller .\cc-usage-reporter.spec
pyinstaller .\cc-usage-reporter-gui.spec
Write-Host "Build complete: .\dist\"

python -m cc_usage_reporter deps-check || Write-Host "tray optional deps check failed; continue if you only need CLI/daemon"
python -m cc_usage_reporter release-pack
