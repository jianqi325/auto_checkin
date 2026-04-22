from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

from .exceptions import ConfigError
from .models import AppConfig, FishcConfig
from .time_util import validate_timezone

_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data


def _bool(value: str, default: bool) -> bool:
    if value is None or value == "":
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _int(value: str, default: int, name: str, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if parsed < min_value or parsed > max_value:
        raise ConfigError(f"{name} must be between {min_value} and {max_value}")
    return parsed


def _normalize_url(url: str, key: str) -> str:
    clean = (url or "").strip()
    if not clean:
        raise ConfigError(f"{key} cannot be empty")
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean
    parsed = urlparse(clean)
    if not parsed.scheme or not parsed.netloc:
        raise ConfigError(f"{key} is not a valid URL")
    return clean.rstrip("/")


def _merge_with_env(file_data: dict[str, str]) -> dict[str, str]:
    merged = dict(file_data)
    for key in file_data:
        if key in os.environ:
            merged[key] = os.environ[key]
    return merged


def load_runtime_config(project_root: Path, site: str) -> tuple[AppConfig, FishcConfig, Path, Path]:
    config_dir = project_root / "config"
    global_path = config_dir / "global.env"
    site_path = config_dir / f"{site}.env"

    if not global_path.exists():
        raise ConfigError(f"Missing config file: {global_path}")
    if not site_path.exists():
        raise ConfigError(f"Missing config file: {site_path}")

    global_env = _merge_with_env(parse_env_file(global_path))
    site_env = _merge_with_env(parse_env_file(site_path))

    timezone = global_env.get("APP_TIMEZONE", "Asia/Shanghai")
    try:
        validate_timezone(timezone)
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"APP_TIMEZONE is invalid: {timezone}") from exc

    schedule_time = global_env.get("SCHEDULE_DAILY_TIME", "09:05")
    if not _TIME_PATTERN.match(schedule_time):
        raise ConfigError("SCHEDULE_DAILY_TIME must be HH:mm")

    app_cfg = AppConfig(
        project_root=str(project_root),
        data_dir=str(project_root / "data"),
        timezone=timezone,
        log_retention_days=_int(global_env.get("LOG_RETENTION_DAYS", "7"), 7, "LOG_RETENTION_DAYS", 1, 60),
        http_timeout_seconds=_int(global_env.get("HTTP_TIMEOUT_SECONDS", "15"), 15, "HTTP_TIMEOUT_SECONDS", 3, 120),
        retry_max_attempts=_int(global_env.get("RETRY_MAX_ATTEMPTS", "3"), 3, "RETRY_MAX_ATTEMPTS", 1, 10),
        retry_backoff_seconds=_int(global_env.get("RETRY_BACKOFF_SECONDS", "2"), 2, "RETRY_BACKOFF_SECONDS", 0, 60),
        notify_toast=_bool(global_env.get("NOTIFY_TOAST", "true"), True),
        notify_webhook_url=global_env.get("NOTIFY_WEBHOOK_URL", "").strip(),
        schedule_daily_time=schedule_time,
        schedule_logon_delay_minutes=_int(
            global_env.get("SCHEDULE_LOGON_DELAY_MINUTES", "10"),
            10,
            "SCHEDULE_LOGON_DELAY_MINUTES",
            0,
            180,
        ),
        pause_on_auth_expired=_int(global_env.get("PAUSE_ON_AUTH_EXPIRED", "3"), 3, "PAUSE_ON_AUTH_EXPIRED", 1, 20),
        pause_on_site_changed=_int(global_env.get("PAUSE_ON_SITE_CHANGED", "2"), 2, "PAUSE_ON_SITE_CHANGED", 1, 20),
    )

    webhook = app_cfg.notify_webhook_url
    if webhook:
        _normalize_url(webhook, "NOTIFY_WEBHOOK_URL")

    if site != "fishc":
        raise ConfigError(f"Unsupported site config loader: {site}")

    enabled = _bool(site_env.get("FISHC_ENABLED", "true"), True)
    base_url = _normalize_url(site_env.get("FISHC_BASE_URL", "https://fishc.com.cn"), "FISHC_BASE_URL")
    cookie = site_env.get("FISHC_COOKIE", "").strip()
    cookie_file = site_env.get("FISHC_COOKIE_FILE", "config/fishc.cookie.txt").strip() or "config/fishc.cookie.txt"
    username = site_env.get("FISHC_USERNAME", "").strip()
    password = site_env.get("FISHC_PASSWORD", "").strip()

    if username and not password:
        raise ConfigError("FISHC_PASSWORD is required when FISHC_USERNAME is set")
    if password and not username:
        raise ConfigError("FISHC_USERNAME is required when FISHC_PASSWORD is set")
    if not cookie and not (username and password):
        raise ConfigError("Provide FISHC_COOKIE or FISHC_USERNAME/FISHC_PASSWORD")

    fishc_cfg = FishcConfig(
        enabled=enabled,
        base_url=base_url,
        cookie=cookie,
        cookie_file=cookie_file,
        username=username,
        password=password,
        allow_password_login=_bool(site_env.get("FISHC_ALLOW_PASSWORD_LOGIN", "true"), True),
        save_cookie_after_success=_bool(site_env.get("FISHC_SAVE_COOKIE_AFTER_SUCCESS", "true"), True),
        qdmode=site_env.get("FISHC_QDMODE", "1").strip() or "1",
        todaysay=site_env.get("FISHC_TODAYSAY", "Daily check-in by script.").strip() or "Daily check-in by script.",
        fastreply=site_env.get("FISHC_FASTREPLY", "0").strip() or "0",
        enable_password_md5=_bool(site_env.get("FISHC_ENABLE_PASSWORD_MD5", "true"), True),
    )

    return app_cfg, fishc_cfg, global_path, site_path


def resolve_cookie_path(project_root: Path, cookie_file_value: str) -> Path:
    candidate = Path(cookie_file_value)
    if candidate.is_absolute():
        return candidate
    return (project_root / candidate).resolve()
