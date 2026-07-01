$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Release dir: $BaseDir"
Write-Host "Read docs\INSTALL_WINDOWS.md"
Write-Host "Main binaries are in bin\"
Write-Host "To install WinSW service:"
Write-Host "powershell -ExecutionPolicy Bypass -File $BaseDir\scripts\windows\install_winsw.ps1 -ConfigPath \"$env:USERPROFILE\.config\cc-switch\usage_reporter.json\""
