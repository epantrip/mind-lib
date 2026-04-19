@echo off
:: Mind Library — Windows 启动脚本
:: 用法: start.bat
:: 生产环境建议使用 gunicorn: gunicorn -c gunicorn.conf.py mind_server_v2.1:app

echo ================================================
echo Mind Library v2.1.1  - 启动中
echo ================================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

:: 检查依赖
pip show flask >nul 2>&1
if errorlevel 1 (
    echo [警告] Flask 未安装，正在安装依赖...
    pip install -r requirements.txt
)

:: 检查 .env 文件
if not exist .env (
    echo [警告] .env 文件不存在，已创建模板 .env.example
    echo [警告] 请复制 .env.example 为 .env 并填写实际值！
    echo.
)

:: 设置环境变量（从 .env 加载）
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

:: 生产模式：使用 Gunicorn
if "%1"=="--prod" (
    where gunicorn >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未安装 gunicorn，执行: pip install gunicorn
        pause
        exit /b 1
    )
    echo [生产模式] 使用 Gunicorn 启动
    gunicorn -c gunicorn.conf.py mind_server_v2.1:app
) else (
    echo [开发模式] 使用 Flask 内置服务器启动
    python mind_server_v2.1.py
)
