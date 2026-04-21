#!/bin/bash
# Sovereign Quant V15 - macOS Setup Script

echo "=========================================="
echo "🏛️ SOVEREIGN QUANT TERMINAL V15 PRO"
echo "macOS Quick Setup Wizard"
echo "=========================================="

echo "[1/4] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python is not installed. Please install Python 3.10+ from python.org"
    exit 1
fi
echo "✅ Python detected."

echo "[2/4] Setting up virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
echo "✅ Virtual environment created & activated."

echo "[3/4] Installing quant dependencies (this may take a few minutes)..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Dependencies installed."

echo "[4/4] Setting up environment variables..."
if [ ! -f .env ]; then
    echo "Creating blank .env file. Please edit this to add your API keys."
    echo "TELEGRAM_BOT_TOKEN=" > .env
    echo "TELEGRAM_CHAT_ID=" >> .env
    echo "SUPABASE_URL=" >> .env
    echo "SUPABASE_KEY=" >> .env
fi
echo "✅ Environment ready."

echo ""
echo "🎉 Setup Complete!"
echo "To launch the terminal:"
echo "1. Activate context: source .venv/bin/activate"
echo "2. Edit config.json to insert your License Key."
echo "3. Run app: streamlit run app.py"
echo "=========================================="
