param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,
    [string]$TaskName = "CCSwitch-UsageReporter",
    [string]$Interval = "Hourly"   # Hourly | Daily
)

# 注册一个计划任务，定时运行 cc_usage_reporter 上报本地用量。
# 用法：
#   powershell -ExecutionPolicy Bypass -File dev\register_task.ps1 -ConfigPath "F:\path\config.json"

$ErrorActionPreference = "Stop"

$python = (Get-Command python).Source
$repoDir = Split-Path -Parent $PSScriptRoot   # cc_usage_reporter 目录

$action = New-ScheduledTaskAction -Execute $python `
    -Argument "-m cc_usage_reporter run --config `"$ConfigPath`"" `
    -WorkingDirectory $repoDir

if ($Interval -eq "Daily") {
    $trigger = New-ScheduledTaskTrigger -Daily -At 9:00AM
} else {
    # 每小时一次
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Hours 1) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "上报 CC Switch 本地模型用量到 sub2api" -Force

Write-Host "已注册计划任务: $TaskName ($Interval)"
Write-Host "立即测试: Start-ScheduledTask -TaskName $TaskName"
Write-Host "查看历史: Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "删除任务: Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
