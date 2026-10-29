"""Klien tipis untuk Instagram API with Instagram Login (graph.instagram.com)."""
from __future__ import annotations

import os
import time

import requests

from .common import env

API_VERSION = os.environ.get("IG_API_VERSION") or "v26.0"   # bisa diganti lewat env bila Meta menaikkan versi
BASE = f"https://graph.instagram.com/{API_VERSION}"


class InstagramError(RuntimeError):
    pass


def _token() -> str:
    return env("IG_ACCESS_TOKEN")  # type: ignore[return-value]


def _explain(err: dict) -> str:
    code, sub = err.get("code"), err.get("error_subcode")
    if code == 190:
        return "Token tidak valid/kedaluwarsa. Buat token baru di dashboard Meta lalu perbarui secret IG_ACCESS_TOKEN."
    if code == 100 and sub == 33:
        return ("Akun/objek tidak ditemukan atau token tidak punya izin posting. Pastikan token dibuat dengan izin "
                "instagram_business_content_publish dan akun berstatus Instagram tester yang sudah diterima.")
    if code in (10, 200):
        return "Izin kurang. Buat ulang token dengan semua izin (basic, content_publish, manage_insights) diaktifkan."
    return ""


def _check(r: requests.Response, where: str) -> dict:
    try:
        data = r.json()
    except ValueError:
        raise InstagramError(f"{where}: respons bukan JSON ({r.status_code}): {r.text[:200]}")
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", data)
        hint = _explain(err) if isinstance(err, dict) else ""
        detail = err.get("error_user_msg") or err.get("message") if isinstance(err, dict) else ""
        raise InstagramError(f"{where} -> kode {err.get('code') if isinstance(err, dict) else '?'}"
                             f"/{err.get('error_subcode') if isinstance(err, dict) else '?'} {detail or ''} {hint}".strip())
    return data


def post(path: str, **params) -> dict:
    params["access_token"] = _token()
    return _check(requests.post(f"{BASE}/{path}", data=params, timeout=90), f"POST {path}")


def get(path: str, **params) -> dict:
    params["access_token"] = _token()
    return _check(requests.get(f"{BASE}/{path}", params=params, timeout=90), f"GET {path}")


def account_id() -> str:
    """ID akun profesional (user_id) langsung dari token, jadi tidak bergantung pada secret IG_USER_ID."""
    uid = get("me", fields="user_id").get("user_id")
    if not uid:
        raise InstagramError("GET me: user_id tidak ditemukan. Cek izin token dan tipe akun (Business/Creator).")
    return str(uid)


def wait_until_ready(container_id: str, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = get(container_id, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise InstagramError(f"Container {container_id} berstatus {status}")
        time.sleep(4)
    raise InstagramError(f"Container {container_id} belum siap setelah {timeout} detik")


def publish_carousel(ig_user_id: str, image_urls: list[str], caption: str) -> str:
    """Terbitkan carousel (atau foto tunggal bila hanya satu gambar). Mengembalikan media id."""
    if len(image_urls) == 1:
        c = post(f"{ig_user_id}/media", image_url=image_urls[0], caption=caption)
        wait_until_ready(c["id"])
        return post(f"{ig_user_id}/media_publish", creation_id=c["id"])["id"]

    children = []
    for url in image_urls:
        child = post(f"{ig_user_id}/media", image_url=url, is_carousel_item="true")
        children.append(child["id"])
    for cid in children:
        wait_until_ready(cid)
    parent = post(f"{ig_user_id}/media", media_type="CAROUSEL", children=",".join(children), caption=caption)
    wait_until_ready(parent["id"])
    return post(f"{ig_user_id}/media_publish", creation_id=parent["id"])["id"]
