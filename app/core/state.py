from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .exceptions import StateFileError
from .models import SiteStatus


def default_status(site: str) -> SiteStatus:
    return SiteStatus(site=site, meta={"run_counts": {}, "error_streak": {}})


def _decode_status(data: dict, site: str) -> SiteStatus:
    base = default_status(site).to_dict()
    base.update(data or {})
    base["site"] = site
    if not isinstance(base.get("meta"), dict):
        base["meta"] = {}
    return SiteStatus(**base)


def load_status(path: Path, site: str) -> SiteStatus:
    if not path.exists():
        return default_status(site)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("status json root must be object")
        return _decode_status(raw, site)
    except Exception as exc:  # noqa: BLE001
        broken = path.with_suffix(path.suffix + f".broken.{datetime.now().strftime('%Y%m%d%H%M%S')}")
        try:
            path.replace(broken)
        except OSError:
            pass
        raise StateFileError(f"State file is invalid and moved to {broken.name}") from exc


def save_status(path: Path, status: SiteStatus) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(status.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_history(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")
