#!/usr/bin/env bash
# Unduh font Poppins (lisensi OFL) ke assets/fonts. Dipakai oleh workflow dan bisa dijalankan manual.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/fonts
for f in Poppins-Bold Poppins-SemiBold Poppins-Regular; do
  [ -s "assets/fonts/$f.ttf" ] && continue
  curl -sSfL -o "assets/fonts/$f.ttf" \
    "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/$f.ttf"
done
ls -la assets/fonts
