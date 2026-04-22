from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import msvcrt

from .exceptions import LockBusyError


@contextmanager
def file_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise LockBusyError(f"Lock busy: {lock_path}") from exc

        handle.seek(0)
        handle.truncate(0)
        handle.write(str(os.getpid()).encode("ascii", errors="ignore"))
        handle.flush()
        yield
    finally:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        handle.close()
