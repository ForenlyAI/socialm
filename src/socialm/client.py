"""Instagram Graph API için ince HTTP istemcisi (hata yönetimi, tekrar deneme, sayfalama)."""

from __future__ import annotations

import time
from typing import Any, Callable, Iterator

import requests

GRAPH_HOST = "https://graph.facebook.com"

# https://developers.facebook.com/docs/graph-api/overview/rate-limiting
RATE_LIMIT_CODES = {4, 17, 32, 613, 80002}


class GraphAPIError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, subcode: int | None = None,
                 error_type: str | None = None, transient: bool = False, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.subcode = subcode
        self.error_type = error_type
        self.transient = transient
        self.status = status

    @property
    def is_rate_limit(self) -> bool:
        return self.code in RATE_LIMIT_CODES

    @property
    def retryable(self) -> bool:
        return self.transient or self.is_rate_limit or (self.status is not None and self.status >= 500)

    def __str__(self) -> str:
        parts = [self.message]
        if self.code is not None:
            parts.append(f"(code={self.code}" + (f", subcode={self.subcode})" if self.subcode else ")"))
        return " ".join(parts)


class GraphClient:
    def __init__(self, access_token: str, api_version: str = "v23.0", *,
                 session: requests.Session | None = None, max_retries: int = 3,
                 backoff: float = 2.0, timeout: float = 30.0,
                 sleep: Callable[[float], None] = time.sleep):
        self.access_token = access_token
        self.api_version = api_version
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.backoff = backoff
        self.timeout = timeout
        self._sleep = sleep

    @property
    def base_url(self) -> str:
        return f"{GRAPH_HOST}/{self.api_version}"

    def get(self, path: str, **params: Any) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        params = {k: v for k, v in params.items() if v is not None}
        params["access_token"] = self.access_token
        return self._request(url, params)

    def paginate(self, path: str, *, max_items: int | None = None, **params: Any) -> Iterator[dict]:
        """`data` listesini `paging.next` bağlantılarını izleyerek sırayla döndürür."""
        page = self.get(path, **params)
        yielded = 0
        while True:
            for item in page.get("data", []):
                if max_items is not None and yielded >= max_items:
                    return
                yield item
                yielded += 1
            next_url = (page.get("paging") or {}).get("next")
            if not next_url or (max_items is not None and yielded >= max_items):
                return
            # `next` bağlantısı access_token dahil tüm parametreleri içerir.
            page = self._request(next_url, None)

    def _request(self, url: str, params: dict | None) -> dict:
        attempt = 0
        while True:
            try:
                return self._send(url, params)
            except GraphAPIError as exc:
                if not exc.retryable or attempt >= self.max_retries:
                    raise
            except (requests.ConnectionError, requests.Timeout):
                if attempt >= self.max_retries:
                    raise
            self._sleep(self.backoff * (2 ** attempt))
            attempt += 1

    def _send(self, url: str, params: dict | None) -> dict:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        try:
            payload = resp.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict) and "error" in payload:
            err = payload["error"]
            raise GraphAPIError(
                err.get("error_user_msg") or err.get("message", "Bilinmeyen Graph API hatası"),
                code=err.get("code"),
                subcode=err.get("error_subcode"),
                error_type=err.get("type"),
                transient=bool(err.get("is_transient")),
                status=resp.status_code,
            )
        if resp.status_code >= 400 or not isinstance(payload, dict):
            raise GraphAPIError(f"HTTP {resp.status_code}: beklenmeyen yanıt", status=resp.status_code)
        return payload
