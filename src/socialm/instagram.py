"""Instagram Graph API uç noktaları: Business Discovery, Hashtag Search, Insights."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from .client import GraphAPIError, GraphClient

MEDIA_FIELDS = "id,caption,media_type,media_product_type,like_count,comments_count,timestamp,permalink"
# Hashtag uç noktaları media_product_type ve kullanıcı adı döndürmez.
HASHTAG_MEDIA_FIELDS = "id,caption,media_type,like_count,comments_count,timestamp,permalink"
PROFILE_FIELDS = "id,username,name,biography,website,followers_count,follows_count,media_count,profile_picture_url"

# Graph API v22+ hesap metrikleri (metric_type=total_value).
DEFAULT_ACCOUNT_METRICS = (
    "reach", "views", "accounts_engaged", "total_interactions", "likes", "comments",
    "shares", "saves", "replies", "profile_views", "website_clicks", "follows_and_unfollows",
)
DEFAULT_MEDIA_METRICS = ("reach", "views", "likes", "comments", "shares", "saved", "total_interactions")

# Business Discovery tek seferde en fazla bu kadar gönderi döndürür.
_BD_PAGE_SIZE = 50
_INVALID_METRIC_CODES = {100}


class Instagram:
    def __init__(self, client: GraphClient, ig_user_id: str):
        self.client = client
        self.ig_user_id = ig_user_id

    # ---- Rakip / herhangi bir business-creator hesabı -------------------------------

    def business_discovery(self, username: str, media_limit: int = 25) -> dict:
        """Başka bir Business/Creator hesabının herkese açık profilini ve son gönderilerini getirir."""
        username = username.lstrip("@").strip()
        profile: dict | None = None
        media: list[dict] = []
        after: str | None = None

        while True:
            page_size = min(_BD_PAGE_SIZE, max(media_limit - len(media), 1))
            media_expr = f"media{f'.after({after})' if after else ''}.limit({page_size}){{{MEDIA_FIELDS}}}"
            fields = f"business_discovery.username({username}){{{PROFILE_FIELDS},{media_expr}}}"
            data = self.client.get(self.ig_user_id, fields=fields)["business_discovery"]

            media_block = data.pop("media", {}) or {}
            if profile is None:
                profile = data
            media.extend(media_block.get("data", []))

            after = ((media_block.get("paging") or {}).get("cursors") or {}).get("after")
            has_next = bool((media_block.get("paging") or {}).get("next"))
            if len(media) >= media_limit or not after or not has_next:
                break

        profile["media"] = media[:media_limit]
        return profile

    # ---- Hashtag ---------------------------------------------------------------------

    def hashtag_id(self, name: str) -> str:
        """Not: Bir hesap 7 günde en fazla 30 farklı hashtag sorgulayabilir."""
        name = name.lstrip("#").strip().lower()
        data = self.client.get("ig_hashtag_search", user_id=self.ig_user_id, q=name).get("data", [])
        if not data:
            raise GraphAPIError(f"Hashtag bulunamadı: #{name}")
        return data[0]["id"]

    def hashtag_media(self, hashtag_id: str, kind: str = "top", limit: int = 50) -> list[dict]:
        if kind not in ("top", "recent"):
            raise ValueError("kind 'top' veya 'recent' olmalı")
        return list(self.client.paginate(
            f"{hashtag_id}/{kind}_media",
            max_items=limit,
            user_id=self.ig_user_id,
            fields=HASHTAG_MEDIA_FIELDS,
            limit=min(limit, 50),
        ))

    # ---- Kendi hesabınız ---------------------------------------------------------------

    def own_profile(self) -> dict:
        return self.client.get(self.ig_user_id, fields=PROFILE_FIELDS)

    def own_media(self, limit: int = 25) -> list[dict]:
        return list(self.client.paginate(
            f"{self.ig_user_id}/media", max_items=limit, fields=MEDIA_FIELDS, limit=min(limit, 100),
        ))

    def account_insights(self, days: int = 28, metrics: Iterable[str] = DEFAULT_ACCOUNT_METRICS,
                         now: datetime | None = None) -> dict[str, int | None]:
        """Son `days` gün (en fazla 30) için toplam değerler. Desteklenmeyen metrikler None döner."""
        days = max(1, min(days, 30))
        until = (now or datetime.now(timezone.utc)).replace(microsecond=0)
        since = until - timedelta(days=days)
        params = {
            "period": "day",
            "metric_type": "total_value",
            "since": int(since.timestamp()),
            "until": int(until.timestamp()),
        }
        return self._insights(f"{self.ig_user_id}/insights", list(metrics), params)

    def media_insights(self, media_id: str, metrics: Iterable[str] = DEFAULT_MEDIA_METRICS) -> dict[str, int | None]:
        return self._insights(f"{media_id}/insights", list(metrics), {})

    def _insights(self, path: str, metrics: list[str], params: dict) -> dict[str, int | None]:
        """Tüm metrikleri tek istekte dener; geçersiz metrik hatasında tek tek sorgulayıp atlar."""
        try:
            data = self.client.get(path, metric=",".join(metrics), **params).get("data", [])
            values = {row["name"]: _insight_value(row) for row in data}
            return {m: values.get(m) for m in metrics}
        except GraphAPIError as exc:
            if exc.code not in _INVALID_METRIC_CODES or len(metrics) == 1:
                raise

        result: dict[str, int | None] = {}
        for metric in metrics:
            try:
                data = self.client.get(path, metric=metric, **params).get("data", [])
                result[metric] = _insight_value(data[0]) if data else None
            except GraphAPIError as exc:
                if exc.code not in _INVALID_METRIC_CODES:
                    raise
                result[metric] = None
        return result


def _insight_value(row: dict) -> int | None:
    total = row.get("total_value")
    if isinstance(total, dict) and "value" in total:
        return total["value"]
    values = row.get("values") or []
    nums = [v.get("value") for v in values if isinstance(v.get("value"), (int, float))]
    return sum(nums) if nums else None
