# Sovereign Quant Terminal V15 — Quickstart Guide

Welcome to **Sovereign V15 PRO**, the institutional-grade quantitative trading companion for the Indonesian Stock Exchange (IDX).

---

## 1. Installation

Sovereign provides 1-click setup scripts to automate virtual environment creation and dependency installation.

### macOS / Linux
Open your terminal and run:
```bash
chmod +x setup_mac.sh
./setup_mac.sh
```

### Windows
Double-click `setup_windows.bat` or run it from the command prompt:
```cmd
setup_windows.bat
```

---

## 2. Configuration & API Keys

Sovereign requires a few credentials to operate fully (Cloud Sync, Telegram Alerts).

> [!TIP]
> **Don't have API keys yet?**
> You can run Sovereign in **Demo Mode** without any credentials. 
> Just skip this step and run directly (see Section 3).

1. The installer created a blank `.env` file in your directory. Open it in a text editor.
2. Fill in the following:
   - `TELEGRAM_BOT_TOKEN="your-bot-token"` 
   - `TELEGRAM_CHAT_ID="your-chat-id"`
   - `SUPABASE_URL="your-supabase-url"` *(Optional, for cloud sync)*
   - `SUPABASE_KEY="your-supabase-key"` *(Optional, for cloud sync)*
3. If you want to use Google Sheets to log trades, ensure `service_account.json` is placed in the root directory and you have added your Spreadsheet ID to `config.json`.

### License Activation
Sovereign V15 requires a valid license key for production use.
1. Buka file `config.json`
2. Cari line: `"license_key": "YOUR_LICENSE_KEY_HERE"`
3. Ganti dengan UUID yang diberikan saat pembelian.
4. Save dan restart terminal.

**Demo Mode (tanpa license key):**
- Bisa digunakan selama 7 hari dengan fitur terbatas.
- Setelah 7 hari, Anda harus memasukkan license key untuk melanjutkan.

---

## 3. Starting the Engine

Once configured, activate your virtual environment and launch the terminal:

### Option A: Standard Mode
```bash
# macOS / Linux
source .venv/bin/activate
streamlit run app.py

# Windows
call .venv\Scripts\activate.bat
streamlit run app.py
```

### Option B: Demo Mode
```bash
# Biplots with cached historical data and simulator
streamlit run app.py -- --demo
```

---

## 4. First Run Operations

1. **Check System Health**: Look at the Sidebar. Click **Run Health Check**. Ensure all services show a green `✅` checkmark.
2. **Review Config**: Check if any warnings appear below the Health Check. Sovereign has a built-in strict validator that catches misconfigurations.
3. **Paper Mode**: Turn on the `AUTO-PILOT` toggle. Ensure the `📄 PAPER MODE` badge is visible.

💡 **Visual Guide**: Lihat folder `docs/screenshots/` (jika tersedia) untuk panduan UI.
Tampilan awal yang diharapkan:
- **Kiri**: Live chart + terminal log.
- **Kanan**: Sector heatmap + scan results.
- **Atas**: IHSG ticker + Portfolio balance.

---

## 5. Troubleshooting Common Issues

### ❌ "ModuleNotFoundError: No module named 'pandas'"
**Solution**: Virtual environment belum aktif. Jalankan:
```bash
source .venv/bin/activate  # macOS/Linux
call .venv\Scripts\activate.bat  # Windows
```

### ❌ "SUPABASE_URL not set"
**Solution**: File `.env` tidak terbaca. Pastikan:
- File `.env` ada di root folder (bukan di subfolder).
- Format: `SUPABASE_URL="https://..."` (tanpa spasi tambahan).
- Restart Streamlit: `Ctrl+C` lalu jalankan lagi.

### ❌ "Telegram connection failed"
**Solution**: Token atau Chat ID salah. Di `.env`, pastikan:
- `TELEGRAM_BOT_TOKEN` dimulai dengan angka.
- `TELEGRAM_CHAT_ID` adalah angka (negatif atau positif), bukan username.

### ❌ "Health Check shows 🔴 Supabase FAIL"
**Solution**: Supabase bersifat opsional. Sistem tetap berjalan tanpa cloud sync menggunakan JSON lokal.

---

## 6. Next Steps

- **Learn the Signals**: Baca `SIGNAL_REFERENCE.md` untuk memahami cara kerja *conviction scoring*.
- **Customize Watchlist**: Klik "Watchlist Manager" di sidebar untuk menambah/menghapus saham.
- **Backtest Strategy**: Jalankan `python backtest.py` untuk validasi parameter sebelum masuk ke market.
- **Join Community**: Gabung dengan grup Telegram untuk diskusi strategi dengan *quant traders* lain.

---

## 7. Automation with GitHub Actions (Optional)

Jika ingin bot melakukan *scan* otomatis tanpa perlu membuka laptop:
1. **Fork** repository ini ke akun GitHub Anda.
2. Buka `.github/workflows/sovereign-scheduler.yml`.
3. **Uncomment** jadwal yang diinginkan (pre-open, sesi 1, sesi 2).
4. **Commit & Push**. GitHub akan menjalankan bot sesuai jadwal secara otomatis.

---

*Need support? Contact VoxTech Client Success.*
