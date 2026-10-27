"""Perpanjang token Instagram (berlaku 60 hari). Jalankan tiap ~50 hari.

    IG_ACCESS_TOKEN=token_lama python scripts/refresh_token.py

Salin token baru yang tercetak ke GitHub Secrets (IG_ACCESS_TOKEN).
Token hanya bisa diperpanjang jika umurnya minimal 24 jam dan belum kedaluwarsa.
"""
import os
import sys

import requests

token = os.environ.get("IG_ACCESS_TOKEN")
if not token:
    sys.exit("Isi dulu IG_ACCESS_TOKEN di terminal.")
r = requests.get(
    "https://graph.instagram.com/refresh_access_token",
    params={"grant_type": "ig_refresh_token", "access_token": token},
    timeout=60,
)
data = r.json()
if "access_token" not in data:
    sys.exit(f"Gagal memperpanjang: {data}")
print("Token baru:", data["access_token"])
print("Berlaku (detik):", data.get("expires_in"))
