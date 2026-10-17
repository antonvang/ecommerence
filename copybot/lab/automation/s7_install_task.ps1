# S7 scheduled automation for the research lab: PREPARED, NOT ACTIVATED.
#
# Registers a Windows Task Scheduler entry that starts `py -m lab supervise` at logon and keeps it running.
# It refuses to do anything unless the S7 gate is open: stages 1-6 must have run cleanly for >= 7 days
# (`py -m lab gate --require` exits 0). Run it by hand only after that, from the copybot folder:
#
#   powershell -ExecutionPolicy Bypass -File lab\automation\s7_install_task.ps1
#
# To remove the task later:  Unregister-ScheduledTask -TaskName "ResearchLab-Supervisor" -Confirm:$false
param([string]$TaskName = "ResearchLab-Supervisor")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # ...\copybot
Push-Location $root
try {
    & py -m lab gate --require
    if ($LASTEXITCODE -ne 0) {
        Write-Host "S7 gate is closed: scheduled automation was NOT installed." -ForegroundColor Yellow
        exit 2
    }
    $action = New-ScheduledTaskAction -Execute "py" -Argument "-u -m lab supervise" -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
        -Description "Research lab supervisor (paper only). Single instance enforced by lab.lock." | Out-Null
    Write-Host "Registered scheduled task '$TaskName' (starts at next logon)."
} finally { Pop-Location }
