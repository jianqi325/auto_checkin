from __future__ import annotations

import hashlib
import html as ihtml
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from requests.utils import add_dict_to_cookiejar

from app.core.config import resolve_cookie_path
from app.core.exceptions import AuthExpiredError, NetworkError, SiteChangedError
from app.core.http_client import HttpClient, HttpOptions
from app.core.models import (
    RESULT_ALREADY_DONE,
    RESULT_AUTH_EXPIRED,
    RESULT_FAILED,
    RESULT_NETWORK_ERROR,
    RESULT_SITE_CHANGED,
    RESULT_SUCCESS,
    CheckinResult,
)
from app.sites.base import CheckinSite

LOGIN_FAIL_KEYWORDS = ("登录失败", "密码错误", "用户名不存在", "登录错误")
ALREADY_DONE_KEYWORDS = ("今天已签到", "今日已签到", "今日已签", "已经签到", "已签到", "您今天已经签到")
SIGN_SUCCESS_KEYWORDS = ("succeedhandle_qiandao", "签到成功", "恭喜", "获得", "奖励")
CAPTCHA_HINT_KEYWORDS = ("验证码", "captcha", "geetest", "人机验证", "安全验证")
SITE_CHANGED_HINTS = ("k_misign", "plugin.php?id=k_misign:sign")


@dataclass
class LoginForm:
    action: str
    formhash: str
    quickforward: str
    handlekey: str


class FishCSite(CheckinSite):
    name = "fishc"

    def __init__(self, app_cfg, site_cfg, project_root: Path, logger):
        self.app_cfg = app_cfg
        self.site_cfg = site_cfg
        self.project_root = project_root
        self.logger = logger
        options = HttpOptions(
            timeout_seconds=app_cfg.http_timeout_seconds,
            retry_attempts=app_cfg.retry_max_attempts,
            retry_backoff_seconds=app_cfg.retry_backoff_seconds,
        )
        self.client = HttpClient(options)
        self._setup_headers()

    def _setup_headers(self) -> None:
        self.client.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": urljoin(self.site_cfg.base_url + "/", "plugin.php?id=k_misign:sign"),
            }
        )

    def validate_config(self) -> None:
        if not self.site_cfg.enabled:
            return
        if not self.site_cfg.cookie and not (self.site_cfg.username and self.site_cfg.password):
            raise ValueError("FishC config requires cookie or username/password")

    @staticmethod
    def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(k.lower() in lowered for k in keywords)

    @staticmethod
    def _safe_preview(text: str, limit: int = 260) -> str:
        compact = " ".join(text.split())
        return compact[:limit]

    @staticmethod
    def _read_response_text(response: requests.Response) -> str:
        content_type = (response.headers.get("content-type") or "").lower()
        if "charset=gbk" in content_type or "charset=gb2312" in content_type:
            response.encoding = "gbk"
        elif not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    @staticmethod
    def _extract_login_form(html: str) -> LoginForm | None:
        action_match = re.search(r'<form[^>]+id="lsform"[^>]+action="([^"]+)"', html, re.IGNORECASE)
        if not action_match:
            return None
        formhash_match = re.search(r'name="formhash"\s+value="([0-9a-zA-Z]+)"', html, re.IGNORECASE)
        quickforward_match = re.search(r'name="quickforward"\s+value="([^"]*)"', html, re.IGNORECASE)
        handlekey_match = re.search(r'name="handlekey"\s+value="([^"]*)"', html, re.IGNORECASE)
        return LoginForm(
            action=ihtml.unescape(action_match.group(1)),
            formhash=formhash_match.group(1) if formhash_match else "",
            quickforward=quickforward_match.group(1) if quickforward_match else "yes",
            handlekey=handlekey_match.group(1) if handlekey_match else "ls",
        )

    @staticmethod
    def _extract_formhash(html: str) -> str:
        patterns = (
            r'name="formhash"\s+value="([0-9a-zA-Z]+)"',
            r"formhash['\"]?\s*[:=]\s*['\"]([0-9a-zA-Z]+)['\"]",
        )
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _parse_cookie(raw: str) -> dict[str, str]:
        cookies: dict[str, str] = {}
        for chunk in raw.split(";"):
            part = chunk.strip()
            if not part or "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key:
                cookies[key] = value
        return cookies

    def _load_cookie_text(self) -> str:
        if self.site_cfg.cookie:
            return self.site_cfg.cookie.lstrip("\ufeff").strip()
        cookie_path = resolve_cookie_path(self.project_root, self.site_cfg.cookie_file)
        if cookie_path.exists():
            return cookie_path.read_text(encoding="utf-8").lstrip("\ufeff").strip()
        return ""

    def _apply_cookie(self) -> bool:
        raw = self._load_cookie_text()
        if not raw:
            return False
        cookie_dict = self._parse_cookie(raw)
        if not cookie_dict:
            return False
        add_dict_to_cookiejar(self.client.session.cookies, cookie_dict)
        return True

    def _save_cookie(self) -> None:
        if not self.site_cfg.save_cookie_after_success:
            return
        cookies = [f"{c.name}={c.value}" for c in self.client.session.cookies if c.name and c.value]
        if not cookies:
            return
        cookie_path = resolve_cookie_path(self.project_root, self.site_cfg.cookie_file)
        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        cookie_path.write_text("; ".join(cookies), encoding="utf-8")
        self.logger.info("cookie file updated: %s", cookie_path)

    def _request_get(self, url: str, **kwargs) -> requests.Response:
        response = self.client.get(url, **kwargs)
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise NetworkError(str(exc)) from exc
        return response

    def _request_post(self, url: str, **kwargs) -> requests.Response:
        response = self.client.post(url, **kwargs)
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise NetworkError(str(exc)) from exc
        return response

    def _fetch_sign_page(self) -> tuple[str, requests.Response]:
        sign_url = urljoin(self.site_cfg.base_url + "/", "plugin.php?id=k_misign:sign")
        response = self._request_get(sign_url)
        text = self._read_response_text(response)
        if not any(k in text for k in SITE_CHANGED_HINTS):
            raise SiteChangedError("FishC sign page structure appears changed")
        return text, response

    def _login_with_password(self, page_html: str) -> str:
        login_form = self._extract_login_form(page_html)
        if login_form is None:
            return page_html

        if not self.site_cfg.allow_password_login:
            raise AuthExpiredError("cookie expired and password login disabled")
        if not self.site_cfg.username or not self.site_cfg.password:
            raise AuthExpiredError("cookie expired and credentials missing")

        login_url = urljoin(self.site_cfg.base_url + "/", login_form.action)
        if "inajax=1" not in login_url:
            sep = "&" if "?" in login_url else "?"
            login_url = f"{login_url}{sep}inajax=1"

        password = self.site_cfg.password
        if self.site_cfg.enable_password_md5:
            password = hashlib.md5(password.encode("utf-8")).hexdigest()

        payload = {
            "username": self.site_cfg.username,
            "password": password,
            "cookietime": "2592000",
            "formhash": login_form.formhash,
            "quickforward": login_form.quickforward,
            "handlekey": login_form.handlekey,
        }

        login_resp = self._request_post(login_url, data=payload)
        login_text = self._read_response_text(login_resp)
        if self._has_any(login_text, LOGIN_FAIL_KEYWORDS):
            msg = self._safe_preview(login_text)
            if self._has_any(login_text, CAPTCHA_HINT_KEYWORDS):
                msg += " | captcha required, refresh cookie manually"
            raise AuthExpiredError(msg)

        refreshed_html, _ = self._fetch_sign_page()
        if self._extract_login_form(refreshed_html) is not None:
            raise AuthExpiredError("password login did not establish session")
        return refreshed_html

    def _already_signed(self, html: str) -> bool:
        return self._has_any(html, ALREADY_DONE_KEYWORDS)

    def _discover_sign_urls(self, html: str) -> list[str]:
        urls: list[str] = []
        patterns = (
            r"(plugin\.php\?id=k_misign:sign&operation=qiandao[^\"'<\s]*)",
            r"url\s*:\s*['\"](plugin\.php\?id=k_misign:sign&operation=qiandao[^\"']*)['\"]",
        )
        for pattern in patterns:
            for item in re.findall(pattern, html, re.IGNORECASE):
                full = urljoin(self.site_cfg.base_url + "/", ihtml.unescape(item))
                if full not in urls:
                    urls.append(full)

        fallback = [
            urljoin(self.site_cfg.base_url + "/", "plugin.php?id=k_misign:sign&operation=qiandao"),
            urljoin(self.site_cfg.base_url + "/", "plugin.php?id=k_misign:sign&operation=qiandao&inajax=1"),
            urljoin(
                self.site_cfg.base_url + "/",
                "plugin.php?id=k_misign:sign&operation=qiandao&infloat=1&inajax=1",
            ),
        ]
        for item in fallback:
            if item not in urls:
                urls.append(item)
        return urls

    def _sign_payload(self, formhash: str) -> dict[str, str]:
        return {
            "formhash": formhash,
            "operation": "qiandao",
            "format": "button",
            "from": "insign",
            "inajax": "1",
            "is_ajax": "1",
            "qdmode": self.site_cfg.qdmode,
            "todaysay": self.site_cfg.todaysay,
            "fastreply": self.site_cfg.fastreply,
        }

    def _extract_consecutive_days(self, text: str) -> int | None:
        match = re.search(r"连续签到\D*(\d+)\D*天", text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def _sign_success(self, text: str) -> tuple[bool, bool]:
        if self._has_any(text, SIGN_SUCCESS_KEYWORDS):
            return True, False
        if self._has_any(text, ALREADY_DONE_KEYWORDS):
            return True, True
        return False, False

    def _try_sign(self, html_after_login: str) -> tuple[bool, bool, str, int | None]:
        formhash = self._extract_formhash(html_after_login)
        if not formhash:
            raise SiteChangedError("cannot find formhash")

        payload = self._sign_payload(formhash)
        last_info = "no sign endpoint accepted"
        days: int | None = None

        for sign_url in self._discover_sign_urls(html_after_login):
            get_resp = self._request_get(sign_url, params=payload)
            get_text = self._read_response_text(get_resp)
            ok, already = self._sign_success(get_text)
            if ok:
                days = self._extract_consecutive_days(get_text)
                return True, already, self._safe_preview(get_text), days

            post_resp = self._request_post(sign_url, data=payload)
            post_text = self._read_response_text(post_resp)
            ok, already = self._sign_success(post_text)
            if ok:
                days = self._extract_consecutive_days(post_text)
                return True, already, self._safe_preview(post_text), days

            last_info = f"{sign_url}: GET={self._safe_preview(get_text)} | POST={self._safe_preview(post_text)}"

        return False, False, last_info, days

    def _build_result(self, code: str, success: bool, message: str, days: int | None = None) -> CheckinResult:
        return CheckinResult(site=self.name, result_code=code, success=success, message=message, consecutive_days=days)

    def _prepare_authenticated_page(self) -> str:
        self._apply_cookie()
        page_html, _ = self._fetch_sign_page()
        if self._extract_login_form(page_html) is not None:
            self.logger.info("session unauthenticated, trying password login fallback")
            page_html = self._login_with_password(page_html)
        return page_html

    def checkin(self) -> CheckinResult:
        if not self.site_cfg.enabled:
            return self._build_result(RESULT_ALREADY_DONE, True, "site is disabled")

        try:
            page_html = self._prepare_authenticated_page()
            if self._already_signed(page_html):
                self._save_cookie()
                return self._build_result(RESULT_ALREADY_DONE, True, "already signed today")

            ok, already_done, message, days = self._try_sign(page_html)
            if ok:
                self._save_cookie()
                if already_done:
                    return self._build_result(RESULT_ALREADY_DONE, True, message, days)
                return self._build_result(RESULT_SUCCESS, True, message, days)

            return self._build_result(RESULT_FAILED, False, message)
        except AuthExpiredError as exc:
            return self._build_result(RESULT_AUTH_EXPIRED, False, str(exc))
        except SiteChangedError as exc:
            return self._build_result(RESULT_SITE_CHANGED, False, str(exc))
        except NetworkError as exc:
            return self._build_result(RESULT_NETWORK_ERROR, False, str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._build_result(RESULT_FAILED, False, f"unexpected error: {exc}")

    def sync_status(self) -> CheckinResult:
        if not self.site_cfg.enabled:
            return self._build_result(RESULT_ALREADY_DONE, True, "site is disabled")

        try:
            page_html = self._prepare_authenticated_page()
            if self._already_signed(page_html):
                self._save_cookie()
                return self._build_result(RESULT_ALREADY_DONE, True, "remote status: already signed")
            return self._build_result(RESULT_FAILED, False, "remote status: not signed yet")
        except AuthExpiredError as exc:
            return self._build_result(RESULT_AUTH_EXPIRED, False, str(exc))
        except SiteChangedError as exc:
            return self._build_result(RESULT_SITE_CHANGED, False, str(exc))
        except NetworkError as exc:
            return self._build_result(RESULT_NETWORK_ERROR, False, str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._build_result(RESULT_FAILED, False, f"unexpected error: {exc}")
