from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def resolve_tzinfo(tz_name: str):
    try:
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        # Windows Python environments may miss IANA tzdata; provide a safe fallback.
        if tz_name in {"Asia/Shanghai", "PRC", "China Standard Time"}:
            return timezone(timedelta(hours=8))
        raise


def now_in_timezone(tz_name: str) -> datetime:
    return datetime.now(resolve_tzinfo(tz_name))


def iso_now(tz_name: str) -> str:
    return now_in_timezone(tz_name).isoformat(timespec="seconds")


def today_str(tz_name: str) -> str:
    return now_in_timezone(tz_name).strftime("%Y-%m-%d")


def same_day(iso_value: str, tz_name: str) -> bool:
    if not iso_value:
        return False
    try:
        dt = datetime.fromisoformat(iso_value)
    except ValueError:
        return False
    return dt.astimezone(resolve_tzinfo(tz_name)).date() == now_in_timezone(tz_name).date()


def validate_timezone(tz_name: str) -> None:
    resolve_tzinfo(tz_name)
