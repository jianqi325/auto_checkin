from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import requests

from .exceptions import NotificationError
from .models import (
    RESULT_ALREADY_DONE,
    RESULT_AUTH_EXPIRED,
    RESULT_CONFIG_ERROR,
    RESULT_FAILED,
    RESULT_NETWORK_ERROR,
    RESULT_SITE_CHANGED,
    RESULT_SUCCESS,
    AppConfig,
    CheckinResult,
)


HIGH_PRIORITY_CODES = {RESULT_AUTH_EXPIRED, RESULT_SITE_CHANGED, RESULT_CONFIG_ERROR}


def _cache_path(project_root: Path) -> Path:
    return project_root / "data" / "history" / "notify_cache.json"


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _should_send(result_code: str, cache: dict, cache_key: str) -> bool:
    if result_code in {RESULT_SUCCESS, RESULT_ALREADY_DONE}:
        return False
    if result_code not in HIGH_PRIORITY_CODES:
        return True
    raw = cache.get(cache_key, "")
    if not raw:
        return True
    try:
        last = datetime.fromisoformat(raw)
    except ValueError:
        return True
    return datetime.now() - last >= timedelta(hours=24)


def _write_desktop_artifacts(project_root: Path, result: CheckinResult, run_id: str, trigger: str) -> None:
    desktop = Path.home() / "Desktop"
    marker = desktop / f"checkin_failed_{result.site}.txt"
    fail_dir = desktop / "checkin_failures"
    fail_dir.mkdir(parents=True, exist_ok=True)
    detail = fail_dir / f"{result.site}_{datetime.now().strftime('%Y-%m-%d')}.log"

    marker_lines = [
        "Check-in FAILED",
        f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"site: {result.site}",
        f"result_code: {result.result_code}",
        f"run_id: {run_id}",
        f"trigger: {trigger}",
        f"details: {detail}",
    ]
    marker.write_text("\n".join(marker_lines), encoding="utf-8")

    detail_lines = [
        f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"site: {result.site}",
        f"result_code: {result.result_code}",
        f"message: {result.message}",
        f"run_id: {run_id}",
        f"trigger: {trigger}",
        f"project_path: {project_root}",
    ]
    detail.write_text("\n".join(detail_lines), encoding="utf-8")


def _clear_marker(site: str) -> None:
    marker = Path.home() / "Desktop" / f"checkin_failed_{site}.txt"
    if marker.exists():
        marker.unlink(missing_ok=True)


def _send_webhook(url: str, result: CheckinResult, run_id: str, trigger: str) -> None:
    payload = {
        "site": result.site,
        "result_code": result.result_code,
        "success": result.success,
        "message": result.message,
        "run_id": run_id,
        "trigger": trigger,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    response = requests.post(url, json=payload, timeout=8)
    if response.status_code >= 400:
        raise NotificationError(f"Webhook returned HTTP {response.status_code}")


def notify(app_cfg: AppConfig, project_root: Path, result: CheckinResult, run_id: str, trigger: str, logger) -> None:
    if result.result_code in {RESULT_SUCCESS, RESULT_ALREADY_DONE}:
        _clear_marker(result.site)
    else:
        _write_desktop_artifacts(project_root, result, run_id, trigger)

    cache_file = _cache_path(project_root)
    cache = _load_cache(cache_file)
    cache_key = f"{result.site}:{result.result_code}"

    if not _should_send(result.result_code, cache, cache_key):
        return

    if app_cfg.notify_webhook_url:
        try:
            _send_webhook(app_cfg.notify_webhook_url, result, run_id, trigger)
            logger.info("notification webhook sent")
        except Exception as exc:  # noqa: BLE001
            logger.warning("notification webhook failed: %s", exc)

    if result.result_code in HIGH_PRIORITY_CODES:
        cache[cache_key] = datetime.now().isoformat(timespec="seconds")
        _save_cache(cache_file, cache)
