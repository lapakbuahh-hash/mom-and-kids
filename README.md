# Pikupiku Autopilot

Aplikasi pribadi yang menjalankan Instagram secara otomatis, terinspirasi dari Bleam AI. Biaya Rp 0.

**Alurnya**

1. Tiap Minggu sore, Gemini membuat rencana konten 7 hari ke depan (carousel + caption + hashtag) sesuai brand kit kamu.
2. Slide carousel dirender otomatis (1080x1350) dari template.
3. Draf dikirim ke Telegram kamu. Kamu tinggal tekan **Approve** atau **Skip**.
4. Yang di-approve tayang otomatis ke Instagram di jam yang sudah dijadwalkan.
5. Tiap malam, metrik (jangkauan, suka, komentar, simpan, bagikan) diambil dan tampil di dashboard.

Semuanya berjalan di GitHub Actions, jadi komputermu tidak perlu menyala.

---

## Yang kamu butuhkan (semua gratis)

| Kebutuhan | Untuk apa |
|---|---|
| Akun GitHub | Menjalankan jadwal otomatis dan menyimpan data |
| Akun Google | API key Gemini (pembuat konten) |
| Akun Telegram | Menerima draf dan menekan Approve |
| Instagram **Bisnis atau Kreator** | Syarat auto-post lewat API resmi |
| Akun Meta for Developers | Membuat app untuk mendapat token Instagram |

---

## Langkah setup

### 1. Taruh proyek di GitHub

1. Buat repository baru di GitHub. **Harus Public** (gambar dibaca Instagram lewat link raw GitHub, dan Actions gratis tanpa batas untuk repo publik).
2. Upload seluruh isi folder ini ke repository.

> Repo publik berarti draf gambar dan caption bisa dilihat orang yang membuka repo. API key dan token **tidak** ikut terlihat karena disimpan di GitHub Secrets.

### 2. Edit brand kit

Buka `config/brand.yaml` dan ganti semua contoh: nama brand, @handle, produk digitalmu, pilar konten, warna, jam posting. **Ini bagian paling menentukan kualitas hasil.**

### 3. Gemini API key

1. Buka https://aistudio.google.com/apikey lalu buat API key.
2. Simpan, nanti dimasukkan ke secret `GEMINI_API_KEY`.

Free tier punya batas request harian. Untuk satu akun dengan 5 post per minggu, cukup.

### 4. Bot Telegram

1. Di Telegram, chat **@BotFather**, kirim `/newbot`, ikuti langkahnya. Kamu mendapat **token bot** (`TELEGRAM_BOT_TOKEN`).
2. Buka bot barumu, tekan **Start**, kirim pesan apa saja.
3. Dapatkan chat id kamu: buka `https://api.telegram.org/bot<TOKEN_BOT>/getUpdates` di browser, cari angka di `"chat":{"id": ...}`. Itu `TELEGRAM_CHAT_ID`.

### 5. Token Instagram

> Tampilan dan nama menu di Meta for Developers sering berubah. Kalau berbeda dari di bawah, cari menu yang setara. Panduan resmi: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login

1. Ubah akun Instagram-mu ke **Professional** (Bisnis atau Kreator) di pengaturan Instagram.
2. Masuk ke https://developers.facebook.com, buat **App** (tipe Business).
3. Tambahkan produk **Instagram**, pilih **API setup with Instagram login**.
4. Tambahkan akun Instagram-mu sebagai tester/akun terhubung, lalu **Generate token**. Izin yang dibutuhkan: `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_insights`.
5. Salin **token** (`IG_ACCESS_TOKEN`) dan **Instagram account ID** (`IG_USER_ID`).

Selama app berstatus Development dan akunmu terdaftar di app itu, auto-post ke akun sendiri bisa berjalan tanpa App Review.

Token berlaku **60 hari**. Perpanjang tiap sekitar 50 hari: `IG_ACCESS_TOKEN=token_lama python scripts/refresh_token.py`, lalu perbarui secret. Pasang pengingat di kalender.

### 6. Isi GitHub Secrets

Di repository: **Settings > Secrets and variables > Actions > New repository secret**. Buat lima secret:

- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `IG_ACCESS_TOKEN`
- `IG_USER_ID`

### 7. Aktifkan dashboard (opsional)

**Settings > Pages**, Source: *Deploy from a branch*, Branch: `main`, folder `/docs`. Dashboard muncul di `https://<username>.github.io/<nama-repo>/`.

### 8. Uji coba

1. Tab **Actions** > **Buat konten mingguan** > **Run workflow**. Dalam beberapa menit, draf masuk ke Telegram.
2. Tekan **Approve** pada satu draf. Dalam ≤20 menit status diproses.
3. Untuk menguji auto-post tanpa menunggu jadwal, edit `scheduled_at` draf itu di `data/posts.json` ke waktu yang sudah lewat, lalu jalankan manual workflow **Proses approve dan tayangkan**.

**Saran:** uji pertama kali dengan akun Instagram cadangan, atau approve satu post saja dulu.

---

## Uji tampilan di komputer sendiri (tanpa API)

```bash
pip install -r requirements.txt
bash scripts/get_fonts.sh                 # unduh font Poppins
python -m src.generate --sample --no-telegram
```

Hasil gambar ada di folder `posts/`. Untuk uji dengan Gemini asli tanpa Telegram:
`GEMINI_API_KEY=... python -m src.generate --no-telegram`.

Untuk menjalankan uji otomatis logika alur: `python tests/test_pipeline.py`.

---

## Struktur proyek

```
config/brand.yaml         brand kit (EDIT INI)
src/generate.py           rencana konten via Gemini + penjadwalan slot
src/render.py             template slide carousel (Pillow)
src/telegram.py           kirim draf dan baca tombol Approve/Skip
src/publish.py            tayangkan yang sudah approved dan jatuh tempo
src/instagram.py          klien Instagram API
src/insights.py           ambil metrik, tulis docs/analytics.json
src/tick.py               dijalankan tiap 20 menit
data/posts.json           semua postingan dan statusnya
posts/<id>/slide_XX.png   gambar hasil render
docs/                     dashboard analitik (GitHub Pages)
.github/workflows/        jadwal otomatis
```

Status postingan: `draft` > `approved` > `published`. Cabang lain: `skipped`, `expired` (jadwal terlewat >48 jam), `failed` (3 kali gagal tayang, kamu dikabari lewat Telegram).

---

## Batasan dan hal yang perlu diketahui

- **Belum diuji dengan akun asli.** Logika alur sudah diuji dengan simulasi, tapi koneksi nyata ke Gemini, Telegram, dan Instagram baru terbukti saat kamu menjalankannya. Kalau ada error, pesannya tercatat di log tab Actions dan di Telegram.
- **Waktu tayang tidak presisi.** GitHub Actions kadang menunda jadwal beberapa menit, jadi post bisa tayang 0 sampai 30 menit dari jam yang diatur.
- **TikTok tidak disertakan.** API posting TikTok hanya mengizinkan posting publik setelah aplikasi diaudit. Untuk pemakaian pribadi, upload manual lebih praktis.
- **Hanya carousel gambar.** Reels/video tidak termasuk.
- **Jadwal GitHub bisa mati sendiri** jika repo tidak ada aktivitas 60 hari. Bot ini rutin melakukan commit, tapi kalau sempat berhenti, aktifkan lagi di tab Actions.
- **Model Gemini** bisa berganti. Default `gemini-2.5-flash`; ganti lewat environment `GEMINI_MODEL` di workflow bila model itu sudah tidak tersedia.
- **Kualitas konten** tetap perlu kamu review. Jangan approve sembarangan, terutama untuk topik parenting. Aturan "hindari klaim medis" ada di brand kit, tapi AI bisa salah.
- Hanya satu akun Instagram. Untuk beberapa brand, salin repo ini per brand.
