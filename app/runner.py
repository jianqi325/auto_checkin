from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path

from app.core.config import load_runtime_config
from app.core.exceptions import ConfigError, LockBusyError, StateFileError
from app.core.lock import file_lock
from app.core.logging_util import setup_logging, with_context
from app.core.models import (
    RESULT_AUTH_EXPIRED,
    RESULT_CONFIG_ERROR,
    RESULT_NETWORK_ERROR,
    RESULT_SITE_CHANGED,
    RESULT_STATE_ERROR,
    SUCCESS_CODES,
    CheckinResult,
    RunRecord,
)
from app.core.notify import notify
from app.core.state import append_history, load_status, save_status
from app.core.time_util import same_day, today_str
from app.sites.registry import SITE_REGISTRY, create_site

FALLBACK_LAST_CHECK_DATE_KEY = "fallback_last_check_date"


def _run_id(now: datetime) -> str:
    return now.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def _result_exit_code(result_code: str) -> int:
    if result_code in SUCCESS_CODES:
        return 0
    if result_code in {RESULT_AUTH_EXPIRED, RESULT_SITE_CHANGED}:
        return 2
    if result_code == RESULT_NETWORK_ERROR:
        return 3
    if result_code in {RESULT_CONFIG_ERROR, RESULT_STATE_ERROR}:
        return 4
    return 1


def _status_file(project_root: Path, site: str) -> Path:
    return project_root / "data" / "status" / f"{site}.status.json"


def _history_file(project_root: Path, site: str) -> Path:
    return project_root / "data" / "history" / f"{site}-runs.jsonl"


def _lock_file(project_root: Path, site: str) -> Path:
    return project_root / "data" / "locks" / f"{site}.lock"


def _log_file(project_root: Path) -> Path:
    return project_root / "data" / "logs" / "app.log"


def _passed_scheduled_time(now: datetime, scheduled_hhmm: str) -> bool:
    hour = int(scheduled_hhmm[0:2])
    minute = int(scheduled_hhmm[3:5])
    return (now.hour, now.minute) >= (hour, minute)


def _update_pause_state(status, result: CheckinResult, app_cfg) -> None:
    streak = status.meta.get("error_streak", {})
    auth_count = int(streak.get("AUTH_EXPIRED", 0))
    changed_count = int(streak.get("SITE_CHANGED", 0))

    if result.result_code in SUCCESS_CODES:
        auth_count = 0
        changed_count = 0
    else:
        if result.result_code == RESULT_AUTH_EXPIRED:
            auth_count += 1
        if result.result_code == RESULT_SITE_CHANGED:
            changed_count += 1

    streak["AUTH_EXPIRED"] = auth_count
    streak["SITE_CHANGED"] = changed_count
    status.meta["error_streak"] = streak

    if auth_count >= app_cfg.pause_on_auth_expired:
        status.is_paused = True
        status.pause_reason = f"AUTH_EXPIRED repeated {auth_count} times"
    elif changed_count >= app_cfg.pause_on_site_changed:
        status.is_paused = True
        status.pause_reason = f"SITE_CHANGED repeated {changed_count} times"


def _apply_result_to_status(
    status,
    result: CheckinResult,
    run_id: str,
    trigger: str,
    now_iso: str,
    fallback_checked_date: str = "",
) -> None:
    status.last_attempt_at = now_iso
    status.last_result_code = result.result_code
    status.meta["last_run_id"] = run_id
    status.meta["last_trigger"] = trigger

    if result.result_code in SUCCESS_CODES:
        status.last_success_at = now_iso
        status.last_error_code = ""
        status.last_error_message = ""
        status.pause_reason = ""
    else:
        status.last_error_code = result.result_code
        status.last_error_message = result.message[:500]

    if result.consecutive_days is not None:
        status.consecutive_days = result.consecutive_days
    if fallback_checked_date:
        status.meta[FALLBACK_LAST_CHECK_DATE_KEY] = fallback_checked_date


def run_once(
    project_root: Path,
    site: str,
    trigger: str,
    mode: str = "run",
    force: bool = False,
    fallback_if_missed: bool = False,
    scheduled_time: str = "09:05",
) -> int:
    now = datetime.now()
    run_id = _run_id(now)

    try:
        app_cfg, site_cfg, _, _ = load_runtime_config(project_root, site)
    except ConfigError as exc:
        print(f"[CONFIG_ERROR] {exc}")
        return _result_exit_code(RESULT_CONFIG_ERROR)

    logger = setup_logging(_log_file(project_root), app_cfg.log_retention_days)
    log = with_context(logger, run_id=run_id, site=site, trigger=trigger)

    log.info("start mode=%s", mode)

    try:
        with file_lock(_lock_file(project_root, site)):
            status_path = _status_file(project_root, site)
            history_path = _history_file(project_root, site)

            try:
                status = load_status(status_path, site)
            except StateFileError as exc:
                result = CheckinResult(site=site, result_code=RESULT_STATE_ERROR, success=False, message=str(exc))
                notify(app_cfg, project_root, result, run_id, trigger, log)
                return _result_exit_code(result.result_code)

            if status.is_paused and mode != "sync":
                result = CheckinResult(site=site, result_code=RESULT_STATE_ERROR, success=False, message=f"site paused: {status.pause_reason}")
                log.warning(result.message)
                notify(app_cfg, project_root, result, run_id, trigger, log)
                _apply_result_to_status(status, result, run_id, trigger, datetime.now().isoformat(timespec="seconds"))
                save_status(status_path, status)
                return _result_exit_code(result.result_code)

            if fallback_if_missed:
                today = today_str(app_cfg.timezone)
                if str(status.meta.get(FALLBACK_LAST_CHECK_DATE_KEY, "")) == today:
                    log.info("fallback skipped: already checked today")
                    return 0
                if not _passed_scheduled_time(datetime.now(), scheduled_time):
                    log.info("fallback skipped: current time earlier than scheduled time %s", scheduled_time)
                    return 0
                if same_day(status.last_success_at, app_cfg.timezone):
                    log.info("fallback skipped: success already recorded today")
                    return 0
            else:
                today = ""

            if mode == "run" and (not force) and same_day(status.last_success_at, app_cfg.timezone):
                result = CheckinResult(site=site, result_code="ALREADY_DONE", success=True, message="local state indicates already successful today")
                log.info(result.message)
            else:
                site_impl = create_site(site, app_cfg=app_cfg, site_cfg=site_cfg, project_root=project_root, logger=log)
                site_impl.validate_config()
                result = site_impl.checkin() if mode == "run" else site_impl.sync_status()

            ended_at = datetime.now()
            started_at = now
            duration = int((ended_at - started_at).total_seconds() * 1000)
            now_iso = ended_at.isoformat(timespec="seconds")

            _apply_result_to_status(
                status,
                result,
                run_id,
                trigger,
                now_iso,
                fallback_checked_date=today if fallback_if_missed else "",
            )
            _update_pause_state(status, result, app_cfg)
            save_status(status_path, status)

            record = RunRecord(
                run_id=run_id,
                site=site,
                trigger=trigger,
                started_at=started_at.isoformat(timespec="seconds"),
                ended_at=ended_at.isoformat(timespec="seconds"),
                result_code=result.result_code,
                message=result.message,
                error_code="" if result.success else result.result_code,
                duration_ms=duration,
            )
            append_history(history_path, record.to_dict())

            log.info("result=%s message=%s", result.result_code, result.message)
            notify(app_cfg, project_root, result, run_id, trigger, log)
            return _result_exit_code(result.result_code)
    except LockBusyError:
        log.warning("another run is in progress, skip")
        return 0
    except ConfigError as exc:
        result = CheckinResult(site=site, result_code=RESULT_CONFIG_ERROR, success=False, message=str(exc))
        notify(app_cfg, project_root, result, run_id, trigger, log)
        return _result_exit_code(result.result_code)
    except Exception as exc:  # noqa: BLE001
        result = CheckinResult(site=site, result_code="FAILED", success=False, message=f"runner exception: {exc}")
        log.exception("runner crashed")
        notify(app_cfg, project_root, result, run_id, trigger, log)
        return _result_exit_code(result.result_code)


def status_summary(project_root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for site in sorted(SITE_REGISTRY.keys()):
        path = _status_file(project_root, site)
        try:
            status = load_status(path, site)
        except Exception:  # noqa: BLE001
            rows.append({"site": site, "enabled": "unknown", "last_result": "STATE_ERROR", "last_success": ""})
            continue
        rows.append(
            {
                "site": site,
                "enabled": "paused" if status.is_paused else "enabled",
                "last_result": status.last_result_code or "N/A",
                "last_success": status.last_success_at or "N/A",
            }
        )
    return rows
