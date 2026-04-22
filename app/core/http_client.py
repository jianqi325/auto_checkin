from __future__ import annotations

from dataclasses import dataclass

import requests

from .exceptions import NetworkError
from .retry import run_with_retry


@dataclass
class HttpOptions:
    timeout_seconds: int
    retry_attempts: int
    retry_backoff_seconds: int


class HttpClient:
    def __init__(self, options: HttpOptions):
        self.options = options
        self.session = requests.Session()

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        timeout = kwargs.pop("timeout", self.options.timeout_seconds)

        def _do() -> requests.Response:
            try:
                response = self.session.request(method=method, url=url, timeout=timeout, **kwargs)
                return response
            except requests.RequestException as exc:
                raise NetworkError(str(exc)) from exc

        def _should_retry(exc: Exception) -> bool:
            return isinstance(exc, NetworkError)

        return run_with_retry(
            _do,
            attempts=self.options.retry_attempts,
            backoff_seconds=self.options.retry_backoff_seconds,
            should_retry=_should_retry,
        )

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)
