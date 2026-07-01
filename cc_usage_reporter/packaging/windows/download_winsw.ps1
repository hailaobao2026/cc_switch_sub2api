param(
    [string]$OutputPath = ".\WinSW-x64.exe",
    [string]$ApiUrl = "https://api.github.com/repos/winsw/winsw/releases/latest"
)

$ErrorActionPreference = "Stop"

Write-Host "Fetching latest WinSW release metadata..."
$release = Invoke-RestMethod -Uri $ApiUrl -Headers @{"User-Agent"="cc-usage-reporter"}
$asset = $release.assets | Where-Object { $_.name -match 'WinSW.*x64.*\.exe$' } | Select-Object -First 1
if (-not $asset) {
    $asset = $release.assets | Where-Object { $_.name -match 'WinSW.*\.exe$' } | Select-Object -First 1
}
if (-not $asset) {
    throw "未在最新 release 中找到 WinSW exe 资产"
}

Write-Host "Downloading $($asset.name) -> $OutputPath"
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $OutputPath
Write-Host "Downloaded WinSW: $OutputPath"
