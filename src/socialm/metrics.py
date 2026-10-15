"""Gönderi listelerinden pazarlama metrikleri hesaplama."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from statistics import mean
from typing import Iterable

HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)
MENTION_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_](?:[A-Za-z0-9_.]{0,28}[A-Za-z0-9_])?)")


def extract_hashtags(caption: str | None) -> list[str]:
    return [tag.lower() for tag in HASHTAG_RE.findall(caption or "")]


def extract_mentions(caption: str | None) -> list[str]:
    return [m.lower() for m in MENTION_RE.findall(caption or "")]


def parse_timestamp(value: str | None) -> datetime | None:
    """Graph API zaman damgası: 2024-05-01T12:00:00+0000"""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def interactions(media: dict) -> int | None:
    """Beğeni + yorum. Beğeni sayısı gizlenmişse None."""
    likes = media.get("like_count")
    if likes is None:
        return None
    return likes + (media.get("comments_count") or 0)


def engagement_rate(media: dict, followers: int | None) -> float | None:
    """Tek gönderi için (beğeni + yorum) / takipçi * 100."""
    total = interactions(media)
    if total is None or not followers:
        return None
    return total / followers * 100


def posts_per_week(media: Iterable[dict]) -> float | None:
    stamps = [t for t in (parse_timestamp(m.get("timestamp")) for m in media) if t]
    if len(stamps) < 2:
        return None
    span_days = (max(stamps) - min(stamps)).total_seconds() / 86400
    if span_days <= 0:
        return None
    return len(stamps) / (span_days / 7)


def summarize_media(media: list[dict], followers: int | None = None, top_n: int = 10) -> dict:
    """Bir hesabın ya da hashtag'in gönderi listesinin özeti."""
    with_likes = [m for m in media if m.get("like_count") is not None]
    rates = [r for r in (engagement_rate(m, followers) for m in media) if r is not None]
    tags = Counter(tag for m in media for tag in extract_hashtags(m.get("caption")))
    mentions = Counter(u for m in media for u in extract_mentions(m.get("caption")))
    types = Counter(m.get("media_product_type") or m.get("media_type") or "UNKNOWN" for m in media)

    by_type_er: dict[str, float] = {}
    if followers:
        for kind in types:
            kind_rates = [r for m in media
                          if (m.get("media_product_type") or m.get("media_type") or "UNKNOWN") == kind
                          and (r := engagement_rate(m, followers)) is not None]
            if kind_rates:
                by_type_er[kind] = mean(kind_rates)

    top_posts = sorted(with_likes, key=lambda m: interactions(m) or 0, reverse=True)[:top_n]
    return {
        "post_count": len(media),
        "avg_likes": mean(m["like_count"] for m in with_likes) if with_likes else None,
        "avg_comments": mean(m.get("comments_count") or 0 for m in media) if media else None,
        "engagement_rate": mean(rates) if rates else None,
        "posts_per_week": posts_per_week(media),
        "media_types": dict(types),
        "engagement_by_type": by_type_er,
        "top_hashtags": tags.most_common(top_n),
        "top_mentions": mentions.most_common(top_n),
        "top_posts": top_posts,
    }
