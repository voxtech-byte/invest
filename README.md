# Quant Alpha V9 Pro – Automated Stock Notification System 📈

Quant Alpha V9 Pro adalah sistem notifikasi saham otomatis berbasis Python yang berjalan di **GitHub Actions** secara **gratis**.  
Bot ini memindai saham-saham **Bursa Efek Indonesia (BEI)**, melakukan analisis teknikal dan kuantitatif, lalu mengirimkan laporan terstruktur ke Telegram dalam format:

- **Market regime** (trend + ADX + multi‑timeframe)
- **Bullish/Bearish dynamics** (RSI, phase, support–resistance)
- **Smart Money Proxy** (PVT, CMF, anomali volume)
- **Signal per saham** dengan:
  - Entry zone, invalidation (cutloss), target (TP)
  - Position sizing berbasis risk (% dari equity)
  - Statistik historis (jika tersedia)

Semua eksekusi berjalan otomatis di server GitHub – Anda tidak perlu menyalakan komputer.

***

## 🧩 Universe Saham (Default)

Secara bawaan, sistem memantau 15 saham likuid BEI (contoh):

- **BBCA.JK** – Bank Central Asia Tbk  
- **BMRI.JK** – Bank Mandiri Tbk  
- **BBNI.JK** – Bank Negara Indonesia Tbk  
- **BRIS.JK** – Bank Syariah Indonesia Tbk  
- **GOTO.JK** – GoTo Gojek Tokopedia Tbk  
- **ASII.JK** – Astra International Tbk  
- **TLKM.JK** – Telkom Indonesia Tbk  
- **UNVR.JK** – Unilever Indonesia Tbk  
- **PTBA.JK**, **MERK.JK**, **PGAS.JK**, **UNTR.JK**, dan beberapa saham likuid lain.

Daftar ini dapat dikustomisasi sepenuhnya melalui konfigurasi.

Untuk mengubah saham yang dipantau, cukup sesuaikan daftar ticker (misalnya `STOCKS` atau `universe`) pada konfigurasi / file Python terkait, dengan format kode Yahoo Finance **diakhiri `.JK`**.

***

## 🔍 Logika Analisis & Sinyal (Ringkas)

Sistem menggunakan data harian (daily) untuk:

- **Market Regime**
  - Mengidentifikasi kondisi **Trending / Sideways** dengan indikator seperti **ADX**. 
  - Menandai bias **Bullish / Bearish** dan memberikan rekomendasi gaya: misalnya *“Defensive, short bias”* di regime bearish.

- **Screening Bullish / Bearish**
  - Menyusun dua daftar:
    - **Bullish Dynamics**: saham dengan struktur teknikal relatif kuat (misalnya tren naik, markup, atau konsolidasi sehat).  
    - **Bearish Dynamics**: saham dengan struktur melemah / rawan turun (bisa untuk dihindari atau short, tergantung use case).  

  Beberapa indikator utama:
  - **RSI**: momentum (overbought/oversold). 
  - **Support / Resistance**: area harga kunci.  
  - **Trend Phase**: CONSOLIDATION, MARKUP, dsb.  

- **Smart Money Proxy**
  - Menggabungkan **Price–Volume Trend (PVT)**, **Chaikin Money Flow (CMF)**, dan **anomali volume** untuk memberi skor 1–10 seberapa kuat indikasi akumulasi/distribusi institusional. 

- **Signal per Saham (Single-Stock Report)**
  Contoh isi signal:
  - Market Regime (daily + weekly)  
  - Price, Volume (vs rata‑rata)  
  - P/E, PBV, Market Cap (konteks fundamental ringkas)  
  - Technical Pulse: phase, volatility (mis. **SQUEEZE**)  
  - Smart Money Proxy (skor + indikator penyusun)  
  - Execution Rules:
    - Entry zone  
    - Invalidation / cutloss (biasanya daily close di bawah level tertentu)  
    - Target (TP1, TP2)  
    - Holding period (mis. *Swing 3–14 hari*)  
  - Position Sizing:
    - Perhitungan lot berdasarkan **risk X% dari initial equity**. 
  - Health Check:
    - Liquidity, news risk, dll.  
  - Historical Stats (jika sudah ada backtest/forward test cukup):
    - Winrate, Profit Factor, Max Drawdown, dan jumlah sampel (N). 

Sistem ini dirancang sebagai **alat bantu keputusan** – bukan jaminan profit – dengan pendekatan probabilistik dan manajemen risiko yang eksplisit.

***

## 🚀 Setup & Deploy (GitHub Actions + Telegram)

### 1. Buat Telegram Bot

1. Di Telegram, cari **@BotFather** dan kirim `/newbot`.  
2. Ikuti instruksi untuk memberi nama dan username bot (username harus berakhiran `_bot`).  
3. BotFather akan memberikan **HTTP API Token**, contohnya:  
   `123456789:ABCDefGhiJkL`  
   Simpan token ini – ini akan menjadi `TELEGRAM_BOT_TOKEN`.

### 2. Dapatkan Chat ID

1. Buka chat dengan bot Anda dan klik **Start** (`/start`).  
2. Cari bot **@userinfobot**, klik **Start**, dan baca balasan yang berisi `Id` Anda (contoh: `12345678`).  
   Itu adalah `TELEGRAM_CHAT_ID`.  

Untuk group:
- Tambahkan bot ke group.
- Ambil ID group (biasanya bentuknya `-100xxxxxxxxxx`).

### 3. Fork & Deploy di GitHub (Gratis)

1. Buat akun GitHub bila belum punya.  
2. Buat repository baru dan upload seluruh isi proyek ini.  
3. Di repository tersebut, buka **Settings** → **Secrets and variables** → **Actions**.  
4. Tambah secret baru:
   - `TELEGRAM_BOT_TOKEN` → isi dengan token dari BotFather.  
   - `TELEGRAM_CHAT_ID` → isi dengan chat ID (user atau group).  

GitHub Actions akan menjalankan bot secara otomatis sesuai jadwal (misal: hari kerja pada jam pre‑open dan/atau menjelang penutupan, bisa diatur di file workflow).

***

## 🧪 Testing & Debugging (Sebelum Live)

Sangat disarankan melakukan **testing manual** terlebih dahulu untuk memastikan koneksi Telegram dan format pesan sudah benar.

### Test Notifikasi Dummy

1. Buka terminal di lokal.  
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set environment variable di lokal:

   **Mac / Linux:**
   ```bash
   export TELEGRAM_BOT_TOKEN="123456789:TokenAnda"
   export TELEGRAM_CHAT_ID="12345678"
   ```

   **Windows (Command Prompt):**
   ```cmd
   set TELEGRAM_BOT_TOKEN=123456789:TokenAnda
   set TELEGRAM_CHAT_ID=12345678
   ```

   **Windows (PowerShell):**
   ```powershell
   $env:TELEGRAM_BOT_TOKEN="123456789:TokenAnda"
   $env:TELEGRAM_CHAT_ID="12345678"
   ```

4. Jalankan script uji (misalnya `test_mock.py` jika tersedia):
   ```bash
   python test_mock.py --send-telegram
   ```
5. Pastikan Anda menerima pesan dummy di Telegram dengan format mirip laporan aslinya.

***

## ⚙️ Kustomisasi & Konfigurasi

### Mengubah Universe Saham

Buka file konfigurasi atau `main.py` dan sesuaikan daftar saham, misalnya:

```python
STOCKS = ['BBCA.JK', 'GOTO.JK', 'ASII.JK', 'TLKM.JK', 'UNVR.JK']
```

Tambahkan / kurangi ticker sesuai kebutuhan, pastikan menggunakan kode Yahoo Finance dengan akhiran `.JK` untuk saham BEI.

### Initial Equity & Risk

- **Initial Equity** (misalnya Rp 50.000.000) diset di `config.json` atau variabel konfigurasi lain.  
- Risk per posisi dihitung sebagai persentase dari equity (misalnya 1–2% per trade).

Dengan begitu, perhitungan lot dan simulasi hasil menjadi lebih realistis.

### Sector Mapping

Sector/industry mapping dapat didefinisikan manual di `config.json` (misalnya mengelompokkan saham per sektor).  
Ke depan, ini dapat dihubungkan ke data provider yang menyediakan klasifikasi sektor otomatis.

***

## 🔧 Troubleshooting (Masalah Umum)

1. **GitHub Actions tidak berjalan**  
   - Pastikan workflow `.yml` sudah ada di folder `.github/workflows/`.  
   - Cek tab **Actions** di GitHub untuk melihat log error.  
   - Pastikan repo tidak kehabisan kuota Actions untuk akun gratis.

2. **Telegram tidak menerima pesan**  
   - Pastikan Anda sudah klik `/start` dengan bot Anda.  
   - Cek kembali nilai `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID`.  
   - Jika mengirim ke group, pastikan bot sudah dipanggil minimal sekali di group dan tidak di‑mute/block.

3. **Data yfinance / data provider error**  
   - Terkadang provider seperti Yahoo Finance dapat lambat atau rate‑limited.  
   - Script sebaiknya memiliki mekanisme retry dan/atau fallback ke sumber data lain jika tersedia.  

***

## ⚠️ Disclaimer

Quant Alpha V9 Pro adalah sistem analisis dan notifikasi berbasis aturan (rule‑based) dan indikator teknikal/fundamental.  
Semua sinyal bersifat **probabilistik, bukan kepastian**.  
Gunakan manajemen risiko yang disiplin, dan selalu kombinasikan sinyal sistem dengan penilaian pribadi, konteks berita, serta profil risiko Anda sendiri.
