"""Dijalankan tiap ~20 menit oleh GitHub Actions: proses tombol Telegram lalu terbitkan yang jatuh tempo.

Dua tahap ini dibuat saling terpisah: kalau pembacaan tombol Telegram bermasalah, postingan yang sudah
di-approve dan jatuh tempo tetap diterbitkan. Kegagalan tetap dilaporkan (exit code 1) di akhir.
"""
from __future__ import annotations

import sys

from .publish import publish_due
from .telegram import process_updates


def main() -> None:
    errors: list[str] = []
    handled = published = 0

    try:
        handled = process_updates()
    except Exception as e:  # noqa: BLE001
        errors.append(f"process_updates: {e}")
        print(f"[error] {errors[-1]}")

    try:
        published = publish_due()
    except Exception as e:  # noqa: BLE001
        errors.append(f"publish_due: {e}")
        print(f"[error] {errors[-1]}")

    print(f"Tombol diproses: {handled} | Dipublikasikan: {published}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
