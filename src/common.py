"""Fungsi bersama: konfigurasi, penyimpanan data, dan helper waktu."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
from zoneinfo import ZoneInfo

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POSTS_DIR = ROOT / "posts"
DOCS_DIR = ROOT / "docs"
FONT_DIR = ROOT / "assets" / "fonts"


def load_brand() -> dict:
    path = ROOT / "config" / "brand.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def get_tz(brand: dict) -> ZoneInfo:
    return ZoneInfo(brand.get("timezone", "Asia/Jakarta"))


def now(brand: dict) -> dt.datetime:
    return dt.datetime.now(get_tz(brand))


def env(name: str, required: bool = True, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(
            f"Variabel lingkungan {name} belum diisi. "
            f"Tambahkan di GitHub Secrets (atau export di terminal untuk uji lokal)."
        )
    return value


def _read_json(path: pathlib.Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_posts() -> list[dict]:
    return _read_json(DATA_DIR / "posts.json", [])


def save_posts(posts: list[dict]) -> None:
    _write_json(DATA_DIR / "posts.json", posts)


def load_state() -> dict:
    return _read_json(DATA_DIR / "state.json", {})


def save_state(state: dict) -> None:
    _write_json(DATA_DIR / "state.json", state)


def load_json(name: str, default):
    return _read_json(DATA_DIR / name, default)


def save_json(name: str, obj) -> None:
    _write_json(DATA_DIR / name, obj)


def parse_iso(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def find_post(posts: list[dict], post_id: str) -> dict | None:
    for p in posts:
        if p["id"] == post_id:
            return p
    return None
