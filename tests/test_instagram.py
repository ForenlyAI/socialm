from datetime import datetime, timezone

from socialm.client import GraphAPIError


def _media(i):
    return {"id": str(i), "like_count": 10 * i, "comments_count": i, "timestamp": "2026-01-01T00:00:00+0000"}


def test_business_discovery_paginates_with_cursor(make_ig):
    def handler(path, params):
        assert path == "ME"
        fields = params["fields"]
        assert fields.startswith("business_discovery.username(rakip){")
        if ".after(CUR)" in fields:
            return {"business_discovery": {"username": "rakip", "followers_count": 500,
                                           "media": {"data": [_media(3)]}}}
        return {"business_discovery": {"username": "rakip", "followers_count": 500,
                                       "media": {"data": [_media(1), _media(2)],
                                                 "paging": {"cursors": {"after": "CUR"}, "next": "x"}}}}

    ig, session = make_ig(handler)
    profile = ig.business_discovery("@rakip", media_limit=3)
    assert profile["username"] == "rakip"
    assert [m["id"] for m in profile["media"]] == ["1", "2", "3"]
    assert len(session.calls) == 2


def test_hashtag_lookup_and_media(make_ig):
    def handler(path, params):
        if path == "ig_hashtag_search":
            assert params["q"] == "kahve" and params["user_id"] == "ME"
            return {"data": [{"id": "H1"}]}
        assert path == "H1/top_media"
        return {"data": [_media(1), _media(2)]}

    ig, _ = make_ig(handler)
    assert ig.hashtag_id("#Kahve") == "H1"
    assert len(ig.hashtag_media("H1", "top", limit=10)) == 2


def test_insights_falls_back_per_metric_on_invalid_metric(make_ig):
    def handler(path, params):
        metric = params["metric"]
        if "," in metric or metric == "views":
            return {"error": {"message": "metric[0] must be one of ...", "code": 100}}, 400
        return {"data": [{"name": metric, "total_value": {"value": 42}}]}

    ig, _ = make_ig(handler)
    result = ig.account_insights(days=7, metrics=["reach", "views"],
                                 now=datetime(2026, 1, 8, tzinfo=timezone.utc))
    assert result == {"reach": 42, "views": None}


def test_insights_raises_on_other_errors(make_ig):
    ig, _ = make_ig(lambda p, q: ({"error": {"message": "token expired", "code": 190}}, 401))
    try:
        ig.media_insights("M1")
    except GraphAPIError as exc:
        assert exc.code == 190
    else:
        raise AssertionError("hata bekleniyordu")
