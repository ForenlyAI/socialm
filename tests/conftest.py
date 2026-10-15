from __future__ import annotations

from typing import Callable
from urllib.parse import parse_qs, urlparse

import pytest

from socialm.client import GraphClient
from socialm.instagram import Instagram
from socialm.storage import Storage


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """`handler(path, params) -> payload | (payload, status)` ile yanıt üreten sahte requests.Session."""

    def __init__(self, handler: Callable):
        self.handler = handler
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None, timeout=None):
        parsed = urlparse(url)
        merged = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        merged.update(params or {})
        path = parsed.path.split("/", 2)[-1]  # "/v23.0/<path>" -> "<path>"
        self.calls.append((path, merged))
        result = self.handler(path, merged)
        if isinstance(result, tuple):
            return FakeResponse(*result)
        return FakeResponse(result)


@pytest.fixture
def make_ig():
    def _make(handler):
        session = FakeSession(handler)
        client = GraphClient("TOKEN", "v23.0", session=session, sleep=lambda s: None)
        return Instagram(client, "ME"), session
    return _make


@pytest.fixture
def store():
    s = Storage(":memory:")
    yield s
    s.close()
