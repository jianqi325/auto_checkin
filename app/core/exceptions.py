class CheckinError(Exception):
    """Base exception for the framework."""


class ConfigError(CheckinError):
    pass


class StateFileError(CheckinError):
    pass


class NetworkError(CheckinError):
    pass


class AuthExpiredError(CheckinError):
    pass


class AlreadyCheckedIn(CheckinError):
    pass


class SiteChangedError(CheckinError):
    pass


class NotSupportedError(CheckinError):
    pass


class NotificationError(CheckinError):
    pass


class LockBusyError(CheckinError):
    pass
