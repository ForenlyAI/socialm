"""socialm komut satırı arayüzü."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from . import analysis
from .client import GraphAPIError, GraphClient
from .config import DEFAULT_DB_PATH, ConfigError, Settings, load_dotenv
from .instagram import Instagram
from .storage import TABLES, Storage, write_csv


# ---- Çıktı yardımcıları ----------------------------------------------------------------

def fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def print_table(rows: Sequence[dict], columns: Sequence[str], headers: Sequence[str] | None = None,
                max_width: int = 40) -> None:
    if not rows:
        print("(sonuç yok)")
        return
    headers = list(headers or columns)
    cells = [[fmt(r.get(c))[:max_width] for c in columns] for r in rows]
    widths = [max(len(h), *(len(row[i]) for row in cells)) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for row in cells:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths)))


def read_usernames(values: Sequence[str], files: Sequence[str]) -> list[str]:
    names = list(values)
    for f in files:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                names.append(line)
    return names


# ---- Komutlar ----------------------------------------------------------------------------

def cmd_competitors(args, ig: Instagram, store: Storage) -> int:
    rows, failed = [], 0
    for username in read_usernames(args.usernames, args.file):
        try:
            profile, summary = analysis.analyze_account(ig, store, username, media_limit=args.media_limit)
        except GraphAPIError as exc:
            print(f"! @{username}: {exc}", file=sys.stderr)
            failed += 1
            continue
        rows.append(analysis.account_row(profile, summary))

    rows.sort(key=lambda r: r["followers"] or 0, reverse=True)
    print_table(rows, ["username", "followers", "analyzed_posts", "avg_likes", "avg_comments",
                       "engagement_rate", "posts_per_week", "top_hashtags"],
                ["hesap", "takipçi", "gönderi", "ort.beğeni", "ort.yorum", "etkileşim%", "gönderi/hafta",
                 "en çok hashtag"])
    if args.csv:
        print(f"\nCSV: {write_csv(rows, args.csv)}")
    return 1 if failed and not rows else 0


def cmd_history(args, ig: Instagram | None, store: Storage) -> int:
    rows = store.account_history(args.username.lstrip("@").lower())
    if not rows:
        print(f"@{args.username} için kayıt yok. Önce `socialm competitors {args.username}` çalıştırın.")
        return 1
    prev = None
    for row in rows:
        followers = row["followers_count"]
        row["change"] = (followers - prev) if followers is not None and prev is not None else None
        prev = followers if followers is not None else prev
    print_table(rows, ["fetched_at", "followers_count", "change", "media_count", "engagement_rate", "posts_per_week"],
                ["tarih", "takipçi", "değişim", "gönderi", "etkileşim%", "gönderi/hafta"])
    if args.csv:
        print(f"\nCSV: {write_csv(rows, args.csv)}")
    return 0


def cmd_hashtag(args, ig: Instagram, store: Storage) -> int:
    for tag in args.tags:
        summary = analysis.analyze_hashtag(ig, store, tag, kind=args.kind, limit=args.limit)
        print(f"\n#{summary['hashtag']} ({'en popüler' if args.kind == 'top' else 'en yeni'}) "
              f"- {summary['post_count']} gönderi")
        print(f"  ort. beğeni: {fmt(summary['avg_likes'])}   ort. yorum: {fmt(summary['avg_comments'])}"
              f"   gönderi/hafta: {fmt(summary['posts_per_week'])}")
        print(f"  medya türleri: {summary['media_types']}")
        if summary["top_hashtags"]:
            print("  birlikte kullanılan hashtag'ler: "
                  + ", ".join(f"#{t} ({n})" for t, n in summary["top_hashtags"]))
        if summary["top_mentions"]:
            print("  en çok anılan hesaplar: " + ", ".join(f"@{u} ({n})" for u, n in summary["top_mentions"]))
        print("\n  En yüksek etkileşimli gönderiler:")
        top = [{**m, "caption": (m.get("caption") or "").replace("\n", " ")} for m in summary["top_posts"][:5]]
        print_table(top, ["like_count", "comments_count", "media_type", "permalink", "caption"],
                    ["beğeni", "yorum", "tür", "bağlantı", "açıklama"])
        if args.csv:
            path = Path(args.csv)
            if len(args.tags) > 1:
                path = path.with_name(f"{path.stem}_{summary['hashtag']}{path.suffix}")
            print(f"\n  CSV: {write_csv(summary['media'], path)}")
    return 0


def cmd_influencers(args, ig: Instagram, store: Storage) -> int:
    candidates = read_usernames(args.usernames, args.file)
    if args.from_hashtag:
        found = analysis.influencer_candidates_from_hashtags(ig, store, args.from_hashtag, limit=args.hashtag_limit)
        print(f"Hashtag gönderilerinden {len(found)} aday hesap bulundu.")
        candidates.extend(found[: args.max_candidates])
    if not candidates:
        print("Aday yok. Kullanıcı adı, --file veya --from-hashtag verin.", file=sys.stderr)
        return 2

    result = analysis.discover_influencers(
        ig, store, candidates,
        min_followers=args.min_followers, max_followers=args.max_followers,
        min_engagement=args.min_engagement, media_limit=args.media_limit,
    )
    print(f"\nUygun influencer'lar ({len(result.matches)}):")
    print_table(result.matches, ["username", "followers", "engagement_rate", "avg_likes", "avg_comments",
                                 "posts_per_week", "top_hashtags"],
                ["hesap", "takipçi", "etkileşim%", "ort.beğeni", "ort.yorum", "gönderi/hafta", "en çok hashtag"])
    if result.rejected:
        print(f"\nFiltreye takılan: {len(result.rejected)} hesap")
        if args.verbose:
            for r in result.rejected:
                print(f"  @{r['username']}: {r['reason']}")
    if result.errors:
        print(f"Erişilemeyen (kişisel/gizli hesap ya da bulunamadı): {len(result.errors)} hesap")
        if args.verbose:
            for username, err in result.errors.items():
                print(f"  @{username}: {err}")
    if args.csv:
        print(f"\nCSV: {write_csv(result.matches, args.csv)}")
    return 0


INSIGHT_LABELS = {
    "reach": "erişim", "views": "görüntülenme", "accounts_engaged": "etkileşen hesap",
    "total_interactions": "toplam etkileşim", "likes": "beğeni", "comments": "yorum", "shares": "paylaşım",
    "saves": "kaydetme", "saved": "kaydetme", "replies": "yanıt", "profile_views": "profil ziyareti",
    "website_clicks": "web sitesi tıklaması", "follows_and_unfollows": "takip/bırakma",
}


def cmd_report(args, ig: Instagram, store: Storage) -> int:
    report = analysis.own_account_report(ig, store, days=args.days, media_limit=args.media_limit,
                                         with_media_insights=not args.no_media_insights)
    p, s = report["profile"], report["summary"]
    print(f"@{p.get('username')} — {fmt(p.get('followers_count'))} takipçi, {fmt(p.get('media_count'))} gönderi")
    print(f"Son {s['post_count']} gönderi: etkileşim %{fmt(s['engagement_rate'])}, "
          f"ort. beğeni {fmt(s['avg_likes'])}, haftada {fmt(s['posts_per_week'])} gönderi")
    if s["engagement_by_type"]:
        print("İçerik türüne göre etkileşim: "
              + ", ".join(f"{k} %{v:.2f}" for k, v in sorted(s["engagement_by_type"].items(), key=lambda kv: -kv[1])))

    print(f"\nHesap metrikleri (son {report['days']} gün):")
    for metric, value in report["account_insights"].items():
        print(f"  {INSIGHT_LABELS.get(metric, metric):<22} {fmt(value)}")

    print("\nGönderiler:")
    cols = ["timestamp", "type", "likes", "comments"]
    if not args.no_media_insights:
        cols += ["reach", "views", "shares", "saved"]
    print_table(report["media"], cols + ["permalink"])
    if args.csv:
        print(f"\nCSV: {write_csv(report['media'], args.csv)}")
    return 0


def cmd_export(args, ig: Instagram | None, store: Storage) -> int:
    out_dir = Path(args.out)
    unknown = [t for t in args.tables if t not in TABLES]
    if unknown:
        print(f"Bilinmeyen tablo: {', '.join(unknown)}. Seçenekler: {', '.join(TABLES)}", file=sys.stderr)
        return 2
    for table in (args.tables or TABLES):
        rows = store.table_rows(table)
        print(f"{table}: {len(rows)} satır -> {write_csv(rows, out_dir / f'{table}.csv')}")
    return 0


# ---- Argümanlar ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="socialm", description="Instagram marketing analiz aracı (Graph API)")
    parser.add_argument("--env-file", default=".env", help="ayar dosyası (varsayılan: .env)")
    parser.add_argument("--db", help="SQLite veritabanı yolu (varsayılan: SOCIALM_DB veya data/socialm.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("competitors", help="rakip / hesap analizi (Business Discovery)")
    p.add_argument("usernames", nargs="*", help="Instagram kullanıcı adları")
    p.add_argument("-f", "--file", action="append", default=[], help="her satırda bir kullanıcı adı olan dosya")
    p.add_argument("--media-limit", type=int, default=25, help="hesap başına analiz edilecek gönderi (varsayılan 25)")
    p.add_argument("--csv", help="sonuçları CSV'ye yaz")
    p.set_defaults(func=cmd_competitors)

    p = sub.add_parser("history", help="bir hesabın kayıtlı geçmişini (takipçi büyümesi) göster")
    p.add_argument("username")
    p.add_argument("--csv")
    p.set_defaults(func=cmd_history, offline=True)

    p = sub.add_parser("hashtag", help="hashtag & trend analizi")
    p.add_argument("tags", nargs="+", help="hashtag'ler (# olmadan da yazılabilir)")
    p.add_argument("--kind", choices=["top", "recent"], default="top",
                   help="top: en popüler, recent: son 24 saat (varsayılan top)")
    p.add_argument("--limit", type=int, default=50, help="hashtag başına gönderi (varsayılan 50)")
    p.add_argument("--csv", help="gönderileri CSV'ye yaz")
    p.set_defaults(func=cmd_hashtag)

    p = sub.add_parser("influencers", help="influencer keşfi ve filtreleme")
    p.add_argument("usernames", nargs="*", help="aday kullanıcı adları")
    p.add_argument("-f", "--file", action="append", default=[], help="aday listesi dosyası")
    p.add_argument("--from-hashtag", action="append", default=[], metavar="TAG",
                   help="bu hashtag'in popüler gönderilerinde anılan hesapları aday yap (tekrarlanabilir)")
    p.add_argument("--hashtag-limit", type=int, default=50, help="hashtag başına taranacak gönderi")
    p.add_argument("--max-candidates", type=int, default=30, help="hashtag'lerden alınacak en fazla aday")
    p.add_argument("--min-followers", type=int, default=1_000)
    p.add_argument("--max-followers", type=int, default=None)
    p.add_argument("--min-engagement", type=float, default=1.0, help="en az etkileşim oranı %% (varsayılan 1.0)")
    p.add_argument("--media-limit", type=int, default=12, help="aday başına analiz edilecek gönderi")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--csv")
    p.set_defaults(func=cmd_influencers)

    p = sub.add_parser("report", help="kendi hesabınızın performans raporu (Insights)")
    p.add_argument("--days", type=int, default=28, help="hesap metrikleri için gün sayısı (en fazla 30)")
    p.add_argument("--media-limit", type=int, default=25)
    p.add_argument("--no-media-insights", action="store_true", help="gönderi bazlı insights çekme (daha hızlı)")
    p.add_argument("--csv")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("export", help="veritabanı tablolarını CSV'ye aktar")
    p.add_argument("tables", nargs="*", help=f"tablolar: {', '.join(TABLES)} (varsayılan: hepsi)")
    p.add_argument("--out", default="exports", help="çıktı klasörü (varsayılan: exports)")
    p.set_defaults(func=cmd_export, offline=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    offline = getattr(args, "offline", False)

    ig = None
    if offline:
        load_dotenv(args.env_file)
        db_path = args.db or os.environ.get("SOCIALM_DB", DEFAULT_DB_PATH)
    else:
        try:
            settings = Settings.from_env(args.env_file)
        except ConfigError as exc:
            print(f"Hata: {exc}", file=sys.stderr)
            return 2
        ig = Instagram(GraphClient(settings.access_token, settings.api_version), settings.ig_user_id)
        db_path = args.db or settings.db_path

    with Storage(db_path) as store:
        try:
            return args.func(args, ig, store)
        except GraphAPIError as exc:
            print(f"Graph API hatası: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
