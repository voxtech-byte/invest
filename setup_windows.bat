@echo off
echo ==========================================
echo 🏛️ SOVEREIGN QUANT TERMINAL V15 PRO
echo Windows Quick Setup Wizard
echo ==========================================

echo [1/4] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Python is not installed. Please install Python 3.10+ from python.org
    pause
    exit /b
)
echo [OK] Python detected.

echo [2/4] Setting up virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat
echo [OK] Virtual environment created & activated.

echo [3/4] Installing quant dependencies (this may take a few minutes)...
python -m pip install --upgrade pip
pip install -r requirements.txt
echo [OK] Dependencies installed.

echo [4/4] Setting up environment variables...
if not exist ".env" (
    echo Creating blank .env file. Please edit this to add your API keys.
    echo TELEGRAM_BOT_TOKEN= > .env
    echo TELEGRAM_CHAT_ID= >> .env
    echo SUPABASE_URL= >> .env
    echo SUPABASE_KEY= >> .env
)
echo [OK] Environment ready.

echo.
echo 🎉 Setup Complete!
echo To launch the terminal:
echo 1. Activate context: call .venv\Scripts\activate.bat
echo 2. Edit config.json to insert your License Key.
echo 3. Run app: streamlit run app.py
echo ==========================================
pause
