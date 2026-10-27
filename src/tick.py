"""Dijalankan tiap ~20 menit oleh GitHub Actions: proses tombol Telegram lalu terbitkan yang jatuh tempo."""
from __future__ import annotations

from .publish import publish_due
from .telegram import process_updates


def main() -> None:
    handled = process_updates()
    published = publish_due()
    print(f"Tombol diproses: {handled} | Dipublikasikan: {published}")


if __name__ == "__main__":
    main()
