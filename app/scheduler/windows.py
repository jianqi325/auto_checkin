from __future__ import annotations

import subprocess
from pathlib import Path


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_powershell(script: str) -> None:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown scheduler error").strip()
        raise RuntimeError(detail)


def _task_prefix(site: str) -> str:
    return site.upper()


def task_names(site: str) -> tuple[str, str]:
    prefix = _task_prefix(site)
    return (f"{prefix}-Checkin-Daily", f"{prefix}-Checkin-LogonFallback")


def install_tasks(project_root: Path, site: str, daily_time: str, delay_minutes: int) -> tuple[str, str]:
    daily_name, fallback_name = task_names(site)
    run_script = project_root / "scripts" / "run_now.ps1"
    current_user = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", "[System.Security.Principal.WindowsIdentity]::GetCurrent().Name"],
        text=True,
    ).strip()

    run_script_q = _ps_quote(str(run_script))
    daily_name_q = _ps_quote(daily_name)
    fallback_name_q = _ps_quote(fallback_name)
    site_q = _ps_quote(site)
    user_q = _ps_quote(current_user)

    script = f"""
$ErrorActionPreference = 'Stop'
$dailyName = {daily_name_q}
$fallbackName = {fallback_name_q}
$runScript = {run_script_q}
$site = {site_q}
$currentUser = {user_q}

$dailyArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`" -Site $site -Trigger daily_task"
$dailyAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $dailyArgs
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At '{daily_time}'
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
Register-ScheduledTask -TaskName $dailyName -Action $dailyAction -Trigger $dailyTrigger -Settings $settings -Description "Daily check-in task for $site" -Force | Out-Null

$fallbackArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`" -Site $site -Trigger logon_fallback -FallbackIfMissed -ScheduledTime {daily_time}"
$fallbackAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $fallbackArgs
$fallbackTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$fallbackTrigger.Delay = 'PT{int(delay_minutes)}M'
$fallbackSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
Register-ScheduledTask -TaskName $fallbackName -Action $fallbackAction -Trigger $fallbackTrigger -Settings $fallbackSettings -Description "Logon fallback task for $site" -Force | Out-Null
"""
    _run_powershell(script)
    return daily_name, fallback_name


def remove_tasks(site: str) -> list[str]:
    daily_name, fallback_name = task_names(site)
    names = [daily_name, fallback_name]

    # cleanup old project naming too
    if site == "fishc":
        names += [
            "FISHC-Auto-Checkin",
            "FISHC-Auto-Checkin-LogonFallback",
            "FISHC-Auto-Checkin-Startup",
            "FISHC-Auto-Checkin-Logon",
            "BBXY-Auto-Checkin",
            "BBXY-Auto-Checkin-LogonFallback",
            "BBXY-Auto-Checkin-Startup",
            "BBXY-Auto-Checkin-Logon",
            "BBXY-Auto-Checkin-Test",
        ]

    removed: list[str] = []
    for name in names:
        proc = subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"], capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            removed.append(name)
    return removed


def task_exists(task_name: str) -> bool:
    proc = subprocess.run(["schtasks", "/Query", "/TN", task_name], capture_output=True, text=True, check=False)
    return proc.returncode == 0
