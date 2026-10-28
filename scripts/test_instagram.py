"""Tes koneksi Instagram TANPA memposting apa pun.

Mencetak username dan user_id akunmu. user_id inilah yang diisi ke GitHub Secrets sebagai IG_USER_ID.
Token tidak pernah dicetak.
"""
import os
import sys

import requests

token = os.environ.get("IG_ACCESS_TOKEN")
if not token:
    sys.exit("IG_ACCESS_TOKEN belum diisi di GitHub Secrets.")

version = os.environ.get("IG_API_VERSION") or "v26.0"
r = requests.get(
    f"https://graph.instagram.com/{version}/me",
    params={"fields": "user_id,username,account_type,followers_count,media_count", "access_token": token},
    timeout=60,
)
data = r.json()
if r.status_code >= 400 or "error" in data:
    print("GAGAL:", data.get("error", data))
    sys.exit(1)

print("Koneksi OK")
print("username      :", data.get("username"))
print("IG_USER_ID    :", data.get("user_id"), " <- isi angka ini ke GitHub Secrets")
print("tipe akun     :", data.get("account_type"))
print("pengikut      :", data.get("followers_count"))
print("jumlah postingan:", data.get("media_count"))
if data.get("account_type") not in ("BUSINESS", "MEDIA_CREATOR"):
    print("PERINGATAN: akun bukan Business/Creator, auto-post tidak akan jalan.")
