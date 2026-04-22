from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

RESULT_SUCCESS = "SUCCESS"
RESULT_ALREADY_DONE = "ALREADY_DONE"
RESULT_AUTH_EXPIRED = "AUTH_EXPIRED"
RESULT_NETWORK_ERROR = "NETWORK_ERROR"
RESULT_SITE_CHANGED = "SITE_CHANGED"
RESULT_CONFIG_ERROR = "CONFIG_ERROR"
RESULT_STATE_ERROR = "STATE_ERROR"
RESULT_NOT_SUPPORTED = "NOT_SUPPORTED"
RESULT_FAILED = "FAILED"

SUCCESS_CODES = {RESULT_SUCCESS, RESULT_ALREADY_DONE}


@dataclass
class CheckinResult:
    site: str
    result_code: str
    success: bool
    message: str
    consecutive_days: int | None = None
    reward: str | None = None
    raw_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SiteStatus:
    version: int = 1
    site: str = ""
    last_attempt_at: str = ""
    last_success_at: str = ""
    last_result_code: str = ""
    last_error_code: str = ""
    last_error_message: str = ""
    consecutive_days: int | None = None
    is_paused: bool = False
    pause_reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunRecord:
    run_id: str
    site: str
    trigger: str
    started_at: str
    ended_at: str
    result_code: str
    message: str
    error_code: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AppConfig:
    project_root: str
    data_dir: str
    timezone: str
    log_retention_days: int
    http_timeout_seconds: int
    retry_max_attempts: int
    retry_backoff_seconds: int
    notify_toast: bool
    notify_webhook_url: str
    schedule_daily_time: str
    schedule_logon_delay_minutes: int
    pause_on_auth_expired: int
    pause_on_site_changed: int


@dataclass
class FishcConfig:
    enabled: bool
    base_url: str
    cookie: str
    cookie_file: str
    username: str
    password: str
    allow_password_login: bool
    save_cookie_after_success: bool
    qdmode: str
    todaysay: str
    fastreply: str
    enable_password_md5: bool


@dataclass
class RuntimeContext:
    run_id: str
    site: str
    trigger: str
    now: datetime
    status: SiteStatus
