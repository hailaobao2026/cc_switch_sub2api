param(
    [string]$ConfigPath = "$env:USERPROFILE\.config\cc-switch\usage_reporter.json",
    [string]$WinSWPath = ".\WinSW-x64.exe",
    [string]$ServiceXml = ".\cc-usage-reporter.xml"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $WinSWPath)) {
    $downloadScript = Join-Path $PSScriptRoot "download_winsw.ps1"
    if (Test-Path $downloadScript) {
        Write-Host "未找到 WinSW，尝试自动下载..."
        & $downloadScript -OutputPath $WinSWPath
    }
}
if (-not (Test-Path $WinSWPath)) {
    throw "未找到 WinSW 可执行文件: $WinSWPath"
}
if (-not (Test-Path $ServiceXml)) {
    throw "未找到服务配置文件: $ServiceXml"
}

[xml]$xml = Get-Content $ServiceXml
$xml.service.arguments = "-m cc_usage_reporter daemon --config `"$ConfigPath`""
$xml.Save($ServiceXml)

& $WinSWPath install
& $WinSWPath start
Write-Host "WinSW service installed and started."
