$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
python -m cc_usage_reporter deps-check
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
python -m cc_usage_reporter release-pack
