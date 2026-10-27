"""Terbitkan postingan yang sudah di-approve dan jadwalnya sudah tiba."""
from __future__ import annotations

import os
import time

from . import instagram
from .common import env, load_brand, load_posts, now, parse_iso, save_posts
from .telegram import notify

MAX_PER_RUN = 2        # cegah banjir posting bila ada yang menumpuk
MAX_ATTEMPTS = 3
STALE_HOURS = 48       # jadwal yang terlewat lebih dari ini ditandai 'expired', bukan ditayangkan


def public_url(post_id: str, filename: str) -> str:
    repo = env("GITHUB_REPOSITORY")  # contoh: username/mom-kids-autopilot
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/posts/{post_id}/{filename}"


def publish_due() -> int:
    brand = load_brand()
    posts = load_posts()
    current = now(brand)
    ig_user_id = env("IG_USER_ID")
    done = 0

    for post in posts:
        if post["status"] != "approved":
            continue
        due = parse_iso(post["scheduled_at"])
        if due > current:
            continue
        if (current - due).total_seconds() > STALE_HOURS * 3600:
            post["status"] = "expired"
            notify(f"Postingan {post['id']} melewati jadwal lebih dari {STALE_HOURS} jam dan tidak ditayangkan.")
            continue
        if done >= MAX_PER_RUN:
            break

        try:
            urls = [public_url(post["id"], f) for f in post["images"]]
            media_id = instagram.publish_carousel(ig_user_id, urls, post["full_caption"])
            post["status"] = "published"
            post["media_id"] = media_id
            post["published_at"] = current.isoformat()
            try:
                post["permalink"] = instagram.get(media_id, fields="permalink").get("permalink", "")
            except Exception:  # noqa: BLE001
                post["permalink"] = ""
            notify(f"Tayang: {post['hook']}\n{post.get('permalink', '')}")
            done += 1
            time.sleep(3)
        except Exception as e:  # noqa: BLE001
            post["attempts"] = post.get("attempts", 0) + 1
            post["error"] = str(e)[:500]
            if post["attempts"] >= MAX_ATTEMPTS:
                post["status"] = "failed"
                notify(f"GAGAL tayang {post['id']} setelah {MAX_ATTEMPTS} percobaan:\n{post['error']}")
            else:
                print(f"[warn] {post['id']} gagal (percobaan {post['attempts']}): {post['error']}")

    save_posts(posts)
    return done
