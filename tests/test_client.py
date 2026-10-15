import pytest

from socialm.client import GraphAPIError


def test_paginate_follows_next_links(make_ig):
    def handler(path, params):
        if params.get("after") == "c2":
            return {"data": [{"id": 3}]}
        if params.get("after") == "c1":
            return {"data": [{"id": 2}], "paging": {"next": "https://graph.facebook.com/v23.0/x?after=c2"}}
        return {"data": [{"id": 1}], "paging": {"next": "https://graph.facebook.com/v23.0/x?after=c1"}}

    ig, session = make_ig(handler)
    assert [i["id"] for i in ig.client.paginate("x")] == [1, 2, 3]
    assert [i["id"] for i in ig.client.paginate("x", max_items=2)] == [1, 2]
    assert session.calls[0][1]["access_token"] == "TOKEN"


def test_retries_rate_limit_then_succeeds(make_ig):
    attempts = []

    def handler(path, params):
        attempts.append(1)
        if len(attempts) < 3:
            return {"error": {"message": "Application request limit reached", "code": 4}}, 403
        return {"ok": True}

    ig, _ = make_ig(handler)
    assert ig.client.get("me") == {"ok": True}
    assert len(attempts) == 3


def test_non_retryable_error_raises_immediately(make_ig):
    attempts = []

    def handler(path, params):
        attempts.append(1)
        return {"error": {"message": "Invalid user", "code": 110, "error_subcode": 2207013}}, 400

    ig, _ = make_ig(handler)
    with pytest.raises(GraphAPIError) as exc:
        ig.client.get("me")
    assert exc.value.code == 110
    assert len(attempts) == 1
