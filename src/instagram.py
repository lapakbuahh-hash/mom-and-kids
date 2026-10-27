"""Klien tipis untuk Instagram API with Instagram Login (graph.instagram.com)."""
from __future__ import annotations

import time

import requests

from .common import env

BASE = "https://graph.instagram.com/v21.0"


class InstagramError(RuntimeError):
    pass


def _token() -> str:
    return env("IG_ACCESS_TOKEN")  # type: ignore[return-value]


def _check(r: requests.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        raise InstagramError(f"Respons bukan JSON ({r.status_code}): {r.text[:200]}")
    if r.status_code >= 400 or "error" in data:
        raise InstagramError(str(data.get("error", data)))
    return data


def post(path: str, **params) -> dict:
    params["access_token"] = _token()
    return _check(requests.post(f"{BASE}/{path}", data=params, timeout=90))


def get(path: str, **params) -> dict:
    params["access_token"] = _token()
    return _check(requests.get(f"{BASE}/{path}", params=params, timeout=90))


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
