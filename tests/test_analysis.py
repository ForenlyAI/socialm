from socialm import analysis
from socialm.cli import main


def _bd_handler(accounts):
    def handler(path, params):
        fields = params.get("fields", "")
        username = fields.split("username(", 1)[1].split(")", 1)[0]
        if username not in accounts:
            return {"error": {"message": "Invalid user id", "code": 110}}, 400
        followers, likes = accounts[username]
        media = [{"id": f"{username}{i}", "like_count": likes, "comments_count": 0,
                  "timestamp": f"2026-01-0{i + 1}T00:00:00+0000"} for i in range(3)]
        return {"business_discovery": {"id": username, "username": username, "followers_count": followers,
                                       "media": {"data": media}}}
    return handler


def test_discover_influencers_filters_and_ranks(make_ig, store):
    ig, _ = make_ig(_bd_handler({
        "kucuk": (500, 50),        # takipçi az
        "iyi": (10_000, 500),      # %5
        "dahaiyi": (20_000, 1600), # %8
        "dusuk": (50_000, 100),    # %0.2
    }))
    result = analysis.discover_influencers(
        ig, store, ["@iyi", "kucuk", "dahaiyi", "dusuk", "kisisel", "IYI"],
        min_followers=1000, min_engagement=1.0,
    )
    assert [r["username"] for r in result.matches] == ["dahaiyi", "iyi"]
    assert {r["username"] for r in result.rejected} == {"kucuk", "dusuk"}
    assert list(result.errors) == ["kisisel"]
    assert len(store.account_history("iyi")) == 1


def test_analyze_hashtag_caches_id_and_excludes_self(make_ig, store):
    def handler(path, params):
        if path == "ig_hashtag_search":
            return {"data": [{"id": "H9"}]}
        return {"data": [{"id": "m1", "like_count": 5, "comments_count": 1, "caption": "#kahve #latte @barista"}]}

    ig, session = make_ig(handler)
    s1 = analysis.analyze_hashtag(ig, store, "Kahve")
    analysis.analyze_hashtag(ig, store, "kahve")
    assert [c[0] for c in session.calls].count("ig_hashtag_search") == 1
    assert s1["top_hashtags"] == [("latte", 1)]
    assert s1["top_mentions"] == [("barista", 1)]
    assert len(store.table_rows("hashtag_media")) == 1


def test_cli_competitors_writes_csv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("IG_ACCESS_TOKEN=T\nIG_USER_ID=ME\n")
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("IG_USER_ID", raising=False)

    from tests.conftest import FakeSession
    import socialm.client as client_mod
    monkeypatch.setattr(client_mod.requests, "Session", lambda: FakeSession(_bd_handler({"marka": (1000, 50)})))

    out = tmp_path / "rakipler.csv"
    code = main(["--env-file", str(env), "--db", str(tmp_path / "t.db"), "competitors", "marka", "--csv", str(out)])
    assert code == 0
    text = out.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].startswith("username,")
    assert "marka" in text

    assert main(["--env-file", str(env), "--db", str(tmp_path / "t.db"), "history", "marka"]) == 0
    assert main(["--env-file", str(env), "--db", str(tmp_path / "t.db"), "export", "--out", str(tmp_path / "x")]) == 0
    assert (tmp_path / "x" / "account_snapshots.csv").exists()
