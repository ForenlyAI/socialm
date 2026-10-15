"""Pazarlama analizleri: API çağrıları + metrik hesaplama + kalıcı kayıt."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .client import GraphAPIError
from .instagram import Instagram
from .metrics import extract_mentions, summarize_media
from .storage import Storage, utcnow


def account_row(profile: dict, summary: dict) -> dict:
    return {
        "username": profile.get("username"),
        "name": profile.get("name"),
        "followers": profile.get("followers_count"),
        "following": profile.get("follows_count"),
        "media_count": profile.get("media_count"),
        "analyzed_posts": summary["post_count"],
        "avg_likes": summary["avg_likes"],
        "avg_comments": summary["avg_comments"],
        "engagement_rate": summary["engagement_rate"],
        "posts_per_week": summary["posts_per_week"],
        "top_hashtags": " ".join(f"#{t}" for t, _ in summary["top_hashtags"][:5]),
        "website": profile.get("website"),
    }


def analyze_account(ig: Instagram, store: Storage | None, username: str, media_limit: int = 25) -> tuple[dict, dict]:
    """Rakip/hesap analizi. (profil, özet) döndürür ve anlık görüntüyü kaydeder."""
    profile = ig.business_discovery(username, media_limit=media_limit)
    summary = summarize_media(profile["media"], profile.get("followers_count"))
    if store is not None:
        fetched_at = utcnow()
        store.save_account_snapshot(profile, summary, fetched_at=fetched_at)
        store.save_media(profile["media"], owner_username=profile.get("username"), fetched_at=fetched_at)
    return profile, summary


def analyze_hashtag(ig: Instagram, store: Storage | None, tag: str, kind: str = "top", limit: int = 50) -> dict:
    tag = tag.lstrip("#").strip().lower()
    hashtag_id = store.get_hashtag_id(tag) if store is not None else None
    if hashtag_id is None:
        hashtag_id = ig.hashtag_id(tag)
        if store is not None:
            store.save_hashtag_id(tag, hashtag_id)

    media = ig.hashtag_media(hashtag_id, kind=kind, limit=limit)
    if store is not None:
        store.save_hashtag_media(tag, kind, media)

    summary = summarize_media(media)
    # Aranan hashtag'in kendisini "birlikte kullanılan" listesinden çıkar.
    summary["top_hashtags"] = [(t, n) for t, n in summary["top_hashtags"] if t != tag]
    summary["hashtag"] = tag
    summary["kind"] = kind
    summary["media"] = media
    return summary


@dataclass
class InfluencerResult:
    matches: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


def influencer_candidates_from_hashtags(ig: Instagram, store: Storage | None, tags: Iterable[str],
                                        limit: int = 50) -> list[str]:
    """Hashtag üst gönderilerinin açıklamalarında @ ile anılan hesapları aday olarak toplar."""
    counts: dict[str, int] = {}
    for tag in tags:
        summary = analyze_hashtag(ig, store, tag, kind="top", limit=limit)
        for m in summary["media"]:
            for username in extract_mentions(m.get("caption")):
                counts[username] = counts.get(username, 0) + 1
    return sorted(counts, key=lambda u: (-counts[u], u))


def discover_influencers(ig: Instagram, store: Storage | None, candidates: Iterable[str], *,
                         min_followers: int = 0, max_followers: int | None = None,
                         min_engagement: float = 0.0, media_limit: int = 12) -> InfluencerResult:
    result = InfluencerResult()
    seen: set[str] = set()
    for raw in candidates:
        username = raw.lstrip("@").strip().lower()
        if not username or username in seen:
            continue
        seen.add(username)
        try:
            profile, summary = analyze_account(ig, store, username, media_limit=media_limit)
        except GraphAPIError as exc:
            # Kişisel hesaplar Business Discovery ile görülemez.
            result.errors[username] = str(exc)
            continue

        row = account_row(profile, summary)
        followers = row["followers"] or 0
        er = row["engagement_rate"]
        reasons = []
        if followers < min_followers:
            reasons.append(f"takipçi < {min_followers}")
        if max_followers is not None and followers > max_followers:
            reasons.append(f"takipçi > {max_followers}")
        if er is None or er < min_engagement:
            reasons.append(f"etkileşim < %{min_engagement}")

        if reasons:
            row["reason"] = ", ".join(reasons)
            result.rejected.append(row)
        else:
            result.matches.append(row)

    result.matches.sort(key=lambda r: r["engagement_rate"] or 0, reverse=True)
    return result


def own_account_report(ig: Instagram, store: Storage | None, days: int = 28, media_limit: int = 25,
                       with_media_insights: bool = True) -> dict:
    profile = ig.own_profile()
    media = ig.own_media(limit=media_limit)
    summary = summarize_media(media, profile.get("followers_count"))
    account_insights = ig.account_insights(days=days)

    media_rows = []
    for m in media:
        row = {
            "id": m["id"],
            "timestamp": m.get("timestamp"),
            "type": m.get("media_product_type") or m.get("media_type"),
            "likes": m.get("like_count"),
            "comments": m.get("comments_count"),
            "permalink": m.get("permalink"),
        }
        if with_media_insights:
            try:
                insights = ig.media_insights(m["id"])
            except GraphAPIError as exc:
                insights = {}
                row["error"] = str(exc)
            row.update(insights)
            if store is not None and insights:
                store.save_insights("media", m["id"], insights)
        media_rows.append(row)

    if store is not None:
        store.save_account_snapshot(profile, summary)
        store.save_media(media, owner_username=profile.get("username"))
        store.save_insights("account", profile.get("id") or ig.ig_user_id, account_insights)

    return {
        "profile": profile,
        "summary": summary,
        "account_insights": account_insights,
        "days": max(1, min(days, 30)),
        "media": media_rows,
    }
