from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from app.core.config import load_runtime_config
from app.runner import run_once, status_summary
from app.scheduler.windows import install_tasks, remove_tasks, task_exists, task_names
from app.sites.registry import SITE_REGISTRY


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _print_status_rows(rows: list[dict[str, str]]) -> None:
    for row in rows:
        print(f"{row['site']:<8} {row['enabled']:<8} last_result={row['last_result']:<14} last_success={row['last_success']}")


def cmd_run(args: argparse.Namespace) -> int:
    return run_once(
        project_root=_project_root(),
        site=args.site,
        trigger=args.trigger,
        mode="run",
        force=args.force,
        fallback_if_missed=args.fallback_if_missed,
        scheduled_time=args.scheduled_time,
    )


def cmd_sync(args: argparse.Namespace) -> int:
    return run_once(
        project_root=_project_root(),
        site=args.site,
        trigger=args.trigger,
        mode="sync",
        force=True,
    )


def cmd_install_task(args: argparse.Namespace) -> int:
    project_root = _project_root()
    app_cfg, _, _, _ = load_runtime_config(project_root, args.site)
    time_value = args.time or app_cfg.schedule_daily_time
    delay = args.delay if args.delay is not None else app_cfg.schedule_logon_delay_minutes
    daily_name, fallback_name = install_tasks(project_root, args.site, time_value, delay)
    print(f"Installed task: {daily_name} at {time_value}")
    print(f"Installed task: {fallback_name} (logon +{delay}m)")
    return 0


def cmd_remove_task(args: argparse.Namespace) -> int:
    removed = remove_tasks(args.site)
    if removed:
        print("Removed tasks:")
        for name in removed:
            print(f"- {name}")
    else:
        print("No tasks were removed.")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    rows = status_summary(_project_root())
    _print_status_rows(rows)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    project_root = _project_root()
    checks: list[tuple[str, bool, str]] = []

    checks.append(("Python executable found", True, sys.executable))

    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    checks.append(("virtual environment found", venv_python.exists(), str(venv_python)))

    requests_ok = importlib.util.find_spec("requests") is not None
    checks.append(("requests dependency importable", requests_ok, "requests"))

    global_env = project_root / "config" / "global.env"
    site_env = project_root / "config" / f"{args.site}.env"
    checks.append(("config/global.env exists", global_env.exists(), str(global_env)))
    checks.append((f"config/{args.site}.env exists", site_env.exists(), str(site_env)))

    data_dir = project_root / "data"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
    except OSError:
        writable = False
    checks.append(("data directory writable", writable, str(data_dir)))

    try:
        app_cfg, site_cfg, _, _ = load_runtime_config(project_root, args.site)
        config_ok = True
        msg = f"timezone={app_cfg.timezone}, enabled={site_cfg.enabled}"
    except Exception as exc:  # noqa: BLE001
        config_ok = False
        msg = str(exc)
    checks.append(("config validation", config_ok, msg))

    daily_name, fallback_name = task_names(args.site)
    daily_ok = task_exists(daily_name)
    fallback_ok = task_exists(fallback_name)
    checks.append(("daily scheduled task installed", daily_ok, daily_name))
    checks.append(("logon fallback task installed", fallback_ok, fallback_name))

    if config_ok:
        cookie_empty = not bool(site_cfg.cookie.strip()) if hasattr(site_cfg, "cookie") else True
        checks.append(("FishC cookie is configured or file-based", not cookie_empty or bool(site_cfg.cookie_file), site_cfg.cookie_file))

    any_fail = False
    for title, ok, detail in checks:
        tag = "OK" if ok else "FAIL"
        print(f"[{tag}] {title}")
        if detail:
            print(f"      {detail}")
        if not ok:
            any_fail = True
    return 1 if any_fail else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auto Checkin Framework v1")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run check-in")
    p_run.add_argument("--site", choices=sorted(SITE_REGISTRY.keys()), required=True)
    p_run.add_argument("--trigger", default="manual", help="manual / daily_task / logon_fallback")
    p_run.add_argument("--force", action="store_true", help="force run even if local status says done")
    p_run.add_argument("--fallback-if-missed", action="store_true", help="only run when today's schedule was missed")
    p_run.add_argument("--scheduled-time", default="09:05", help="scheduled HH:mm for fallback checks")
    p_run.set_defaults(func=cmd_run)

    p_sync = sub.add_parser("sync", help="sync local status with remote")
    p_sync.add_argument("--site", choices=sorted(SITE_REGISTRY.keys()), required=True)
    p_sync.add_argument("--trigger", default="sync_manual")
    p_sync.set_defaults(func=cmd_sync)

    p_install = sub.add_parser("install-task", help="install scheduled tasks")
    p_install.add_argument("--site", choices=sorted(SITE_REGISTRY.keys()), required=True)
    p_install.add_argument("--time", help="daily HH:mm")
    p_install.add_argument("--delay", type=int, help="logon fallback delay minutes")
    p_install.set_defaults(func=cmd_install_task)

    p_remove = sub.add_parser("remove-task", help="remove scheduled tasks")
    p_remove.add_argument("--site", choices=sorted(SITE_REGISTRY.keys()), required=True)
    p_remove.set_defaults(func=cmd_remove_task)

    p_doctor = sub.add_parser("doctor", help="run environment checks")
    p_doctor.add_argument("--site", choices=sorted(SITE_REGISTRY.keys()), required=True)
    p_doctor.set_defaults(func=cmd_doctor)

    p_status = sub.add_parser("status", help="show local status summary")
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
