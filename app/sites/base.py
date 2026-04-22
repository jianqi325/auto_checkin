from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.models import CheckinResult


class CheckinSite(ABC):
    name: str

    @abstractmethod
    def validate_config(self) -> None:
        pass

    @abstractmethod
    def checkin(self) -> CheckinResult:
        pass

    @abstractmethod
    def sync_status(self) -> CheckinResult:
        """Try to align local state with remote status."""
        pass
