"""Ambil metrik performa postingan dan akun, simpan ke docs/analytics.json untuk dashboard."""
from __future__ import annotations

import datetime as dt

from . import instagram
from .common import DOCS_DIR, _write_json, load_brand, load_json, load_posts, now, parse_iso, save_json

METRICS = ["reach", "likes", "comments", "shares", "saved", "total_interactions"]
LOOKBACK_DAYS = 45


def media_metrics(media_id: str) -> dict:
    """Ambil per metrik; satu metrik yang tidak tersedia tidak boleh menggagalkan yang lain."""
    out: dict[str, int] = {}
    for m in METRICS:
        try:
            data = instagram.get(f"{media_id}/insights", metric=m)
            out[m] = int(data["data"][0]["values"][0]["value"])
        except Exception:  # noqa: BLE001
            continue
    return out


def main() -> None:
    brand = load_brand()
    current = now(brand)
    posts = load_posts()
    cutoff = current - dt.timedelta(days=LOOKBACK_DAYS)

    rows = []
    for p in posts:
        if p["status"] != "published" or not p.get("media_id"):
            continue
        pub = parse_iso(p["published_at"])
        if pub < cutoff:
            # Metrik lama tidak diambil ulang; pakai yang sudah tersimpan.
            if p.get("metrics"):
                rows.append(_row(p))
            continue
        p["metrics"] = media_metrics(p["media_id"]) or p.get("metrics", {})
        rows.append(_row(p))

    account = {}
    try:
        account = instagram.get("me", fields="username,followers_count,media_count")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] gagal ambil data akun: {e}")

    history = load_json("followers.json", [])
    if account.get("followers_count") is not None:
        today = current.date().isoformat()
        history = [h for h in history if h["date"] != today]
        history.append({"date": today, "followers": account["followers_count"]})
        save_json("followers.json", history[-365:])

    from .common import save_posts

    save_posts(posts)
    rows.sort(key=lambda r: r["published_at"], reverse=True)
    _write_json(
        DOCS_DIR / "analytics.json",
        {
            "updated": current.isoformat(),
            "brand": brand["brand_name"],
            "account": account,
            "followers_history": history,
            "posts": rows,
        },
    )
    print(f"Analitik diperbarui untuk {len(rows)} postingan.")


def _row(p: dict) -> dict:
    return {
        "id": p["id"],
        "pillar": p.get("pillar", ""),
        "topic": p.get("topic", ""),
        "hook": p.get("hook", ""),
        "published_at": p["published_at"],
        "permalink": p.get("permalink", ""),
        "metrics": p.get("metrics", {}),
    }


if __name__ == "__main__":
    main()
