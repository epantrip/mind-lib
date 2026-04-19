@echo off
:: Mind Library ? Windows Startup Script
:: Usage: start.bat
:: Production: gunicorn -c gunicorn.conf.py mind_server_v2.1:app

echo ================================================
echo Mind Library v2.2.0 - Starting...
echo ================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+ first.
    pause
    exit /b 1
)

:: Check dependencies
pip show flask >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Flask not installed, installing dependencies...
    pip install -r requirements.txt
)

:: Check .env file
if not exist .env (
    echo [WARNING] .env not found. Template created as .env.example
    echo [WARNING] Please copy .env.example to .env and fill in the values!
    echo.
)

:: Load environment variables from .env
if exist .env (
    for /f "usebackq tokens=1,* delims=" %%a in (.env) do (
        echo %%a | findstr /i "^[A-Z]" >nul
        if not errorlevel 1 (
            for /f "tokens=1,2 delims==" %%k in ("%%a") do (
                set %%k=%%l
            )
        )
    )
)

:: Production mode: use Gunicorn
if "%1"=="--prod" (
    where gunicorn >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] gunicorn not installed. Run: pip install gunicorn
        pause
        exit /b 1
    )
    echo [PROD] Starting with Gunicorn
    gunicorn -c gunicorn.conf.py mind_server_v2.1:app
) else (
    echo [DEV] Starting with Flask built-in server
    python mind_server_v2.1.py
)

