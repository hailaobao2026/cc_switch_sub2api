param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,
    [string]$TaskName = "CCSwitch-UsageReporter",
    [string]$AtTimes = "10:00,18:00"
)

# 注册一个计划任务，按指定时间运行 cc_usage_reporter 上报本地用量。
# 用法：
#   powershell -ExecutionPolicy Bypass -File dev\register_task.ps1 -ConfigPath "F:\path\config.json" -AtTimes "10:00,18:00"

$ErrorActionPreference = "Stop"

$python = (Get-Command python).Source
$repoDir = Split-Path -Parent $PSScriptRoot
$times = $AtTimes.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }

if ($times.Count -eq 0) {
    throw "AtTimes 至少要包含一个 HH:mm 时间"
}

$action = New-ScheduledTaskAction -Execute $python `
    -Argument "-m cc_usage_reporter run --config `"$ConfigPath`"" `
    -WorkingDirectory $repoDir

$triggers = @()
foreach ($t in $times) {
    $parts = $t.Split(':')
    if ($parts.Count -ne 2) {
        throw "无效时间格式: $t"
    }
    $hour = [int]$parts[0]
    $minute = [int]$parts[1]
    $triggerTime = (Get-Date).Date.AddHours($hour).AddMinutes($minute)
    $triggers += New-ScheduledTaskTrigger -Daily -At $triggerTime
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
    -Settings $settings -Description "上报 CC Switch 本地模型用量到 sub2api" -Force

Write-Host "已注册计划任务: $TaskName ($AtTimes)"
Write-Host "立即测试: Start-ScheduledTask -TaskName $TaskName"
Write-Host "查看历史: Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "删除任务: Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
