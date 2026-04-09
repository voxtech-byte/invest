# Automated Stock Notification System 📈

Sistem ini adalah bot Python yang berjalan otomatis di **GitHub Actions** secara **GRATIS**. Bot ini memantau sejumlah saham di Bursa Efek Indonesia (BEI) menggunakan indikator teknikal (RSI, Moving Average, Volume) dan akan langsung mengirim notifikasi mendetail ke Telegram Anda setiap kali sinyal BUY atau SELL terpicu.

## Daftar Saham (Default)
1. **BBCA.JK** (Bank Central Asia Tbk)
2. **GOTO.JK** (GoTo Gojek Tokopedia Tbk)
3. **ASII.JK** (Astra International Tbk)
4. **TLKM.JK** (Telkom Indonesia Tbk)
5. **UNVR.JK** (Unilever Indonesia Tbk)

*(Untuk mengganti saham yang dimonitor, cukup edit list `STOCKS` pada file `main.py`)*

## Logic Indikator

#### Menggunakan Data `yfinance` daily (1 tahun ke belakang):
- **BUY SIGNAL (Confidence: HIGH)**
  - `RSI (14)` < 30 (Oversold)
  - `Harga Penutupan` > `MA200`
  - `Volume` > 150% dari `Rata-rata Volume 20 Hari`

- **SELL SIGNAL (Confidence: MEDIUM)**
  - `RSI (14)` > 70 (Overbought)
  - `Harga Penutupan` < `MA50` **ATAU** `Volume` > 200% dari `Rata-rata Volume 20 Hari`

---

## 🚀 Panduan Setup (Lengkap & Step-by-step)

### Langkah 1: Buat Telegram Bot
1. Di Telegram, cari bot bernama **@BotFather** lalu kirim pesan: `/newbot`
2. BotFather akan meminta nama bot Anda (misal: `Saham Notifier`)
3. Masukkan username unik untuk bot Anda (misal: `MySahamNotifier_bot` - **harus** diakhiri _bot)
4. BotFather akan memberikan sebuah **HTTP API Token** (contoh: `123456789:ABCDefGhiJkL`). **Simpan token ini**, ini adalah `TELEGRAM_BOT_TOKEN` Anda.

### Langkah 2: Dapatkan Chat ID Anda
1. Buka chat dengan bot Anda yang baru saja dibuat, klik **Start** (atau tulis `/start`). Ini penting agar bot diizinkan mengirim pesan ke Anda.
2. Buka bot di Telegram bernama **@userinfobot** dan klik **Start**.
3. Bot tersebut akan membalas dengan `Id` Anda (contoh: `12345678`). Ini adalah `TELEGRAM_CHAT_ID` Anda.

*(Jika ingin kirim ke Group: Undang bot Anda ke Group, lalu cari ID group Anda. Biasanya diawali dengan tanda minus, misal: `-100123456789`)*

### Langkah 3: Fork dan Deploy di GitHub (GRATIS)
Agar bot ini berjalan otomatis tanpa menyalakan laptop Anda:

1. Buat akun GitHub (jika belum punya) > Buat sebuah _Repository_ baru.
2. Upload semua file yang ada di folder ini ke Repository Anda.
3. Di tab Repository Anda, klik **Settings** > **Secrets and variables** > **Actions**.
4. Klik tombol hijau **New repository secret**:
   - `Name`: `TELEGRAM_BOT_TOKEN`
   - `Secret`: Masukkan API Token dari BotFather
   - **Add secret**
5. Lakukan hal yang sama untuk Chat ID:
   - `Name`: `TELEGRAM_CHAT_ID`
   - `Secret`: Masukkan Chat ID Anda
   - **Add secret**

Selesai! Sistem akan otomatis berjalan di **Senin - Jumat jam 09:00 WIB dan 15:00 WIB.**

---

## 🧪 Cara Testing & Debugging Sebelum Production

Anda **SANGAT DISARANKAN** mengetes dulu sistemnya menggunakan fitur Mocking, untuk memastikan bot Telegram sudah benar-benar terhubung dengan baik sebelum ditunggu otomatis esok hari.

### Cara Menjalankan Test Mocking:
Karena market belum tentu sedang memicu sinyal BUY/SELL, saya telah membuat script `test_mock.py` untuk **memancing pengiriman satu contoh Notif BUY Sempurna** agar Anda tahu bot Telegram-nya bisa mengirim chat ke HP Anda.

1. Buka terminal/command prompt di komputer lokal Anda.
2. Install library jika belum:
   ```bash
   pip install -r requirements.txt
   ```
3. Set API key di komputer lokal Anda (sesuaikan dengan OS Anda):
   - **Mac/Linux:**
     ```bash
     export TELEGRAM_BOT_TOKEN="123456789:TokenAnda"
     export TELEGRAM_CHAT_ID="12345678"
     ```
   - **Windows (Command Prompt):**
     ```cmd
     set TELEGRAM_BOT_TOKEN=123456789:TokenAnda
     set TELEGRAM_CHAT_ID=12345678
     ```
   - **Windows (PowerShell):**
     ```powershell
     $env:TELEGRAM_BOT_TOKEN="123456789:TokenAnda"
     $env:TELEGRAM_CHAT_ID="12345678"
     ```
4. Jalankan script Testing:
   ```bash
   python test_mock.py --send-telegram
   ```
5. Cek Telegram Anda! Anda harusnya menerima pesan dummy format persis seperti aslinya.

---

### Cara Merubah Konfigurasi Saham
Buka `main.py` menggunakan text editor apa pun, cari baris berikut (di bagian atas file):

```python
STOCKS = ['BBCA.JK', 'GOTO.JK', 'ASII.JK', 'TLKM.JK', 'UNVR.JK']
```
Tambahkan kode saham dengan akhiran `.JK` (kode proxy BEI di Yahoo Finance).

### Troubleshooting (Masalah Umum)
1. **GitHub Action Tidak Jalan:**
   Pastikan Repository Anda publik atau Anda masih punya kuota Actions untuk repo private (tier Free GitHub memberi puluhan ribu menit/bulan yang sangat cukup).
2. **Tidak ada Pesan Telegram di Local/Tes Mocking:**
   Apakah Anda sudah menge-chat `/start` pada bot Anda di Telegram? Bot Telegram akan me-reject sistem kalau Anda belum klik _start_ atau jika bot di-block.
3. **Data yFinance error/timeout:**
   Kadangkala Yahoo Finance lambat membalas atau memblokir sementara API IP jika kena rate limit (tapi ini sangat jarang terjadi di Github Actions karena mereka selalu memutar range IP Container). Script tidak akan mogok dan akan tetap berjalan ke saham nomor dua.
