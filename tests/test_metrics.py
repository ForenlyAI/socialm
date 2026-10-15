from socialm.metrics import (engagement_rate, extract_hashtags, extract_mentions, posts_per_week,
                             summarize_media)


def test_extract_hashtags_and_mentions():
    caption = "Yeni koleksiyon! #Moda #yaz2026 @marka.tr ile birlikte, info@site.com @ayse_k."
    assert extract_hashtags(caption) == ["moda", "yaz2026"]
    assert extract_mentions(caption) == ["marka.tr", "ayse_k"]
    assert extract_hashtags(None) == []


def test_engagement_rate_handles_hidden_likes():
    assert engagement_rate({"like_count": 90, "comments_count": 10}, 1000) == 10.0
    assert engagement_rate({"comments_count": 10}, 1000) is None
    assert engagement_rate({"like_count": 1}, 0) is None


def test_posts_per_week():
    media = [{"timestamp": f"2026-01-{d:02d}T10:00:00+0000"} for d in (1, 8, 15)]
    assert posts_per_week(media) == 1.5  # 3 gönderi / 2 hafta
    assert posts_per_week(media[:1]) is None


def test_summarize_media():
    media = [
        {"id": "1", "like_count": 100, "comments_count": 10, "media_product_type": "REELS",
         "caption": "#a #b", "timestamp": "2026-01-01T00:00:00+0000"},
        {"id": "2", "like_count": 50, "comments_count": 0, "media_product_type": "FEED",
         "caption": "#a @x", "timestamp": "2026-01-08T00:00:00+0000"},
        {"id": "3", "comments_count": 4, "media_product_type": "FEED", "timestamp": "2026-01-15T00:00:00+0000"},
    ]
    s = summarize_media(media, followers=1000)
    assert s["post_count"] == 3
    assert s["avg_likes"] == 75
    assert s["engagement_rate"] == (11.0 + 5.0) / 2
    assert s["top_hashtags"][0] == ("a", 2)
    assert s["top_mentions"] == [("x", 1)]
    assert s["media_types"] == {"REELS": 1, "FEED": 2}
    assert s["engagement_by_type"] == {"REELS": 11.0, "FEED": 5.0}
    assert [m["id"] for m in s["top_posts"]] == ["1", "2"]
