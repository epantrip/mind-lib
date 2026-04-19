#!/bin/bash
# Mind Library — Linux/macOS 启动脚本
# 用法:
#   ./start.sh          开发模式（Flask 内置服务器）
#   ./start.sh --prod   生产模式（Gunicorn）
#   ./start.sh --gunicorn-flags "-w 4 --reload"  自定义参数

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================"
echo "Mind Library v2.1.1 — 启动脚本"
echo "================================================"

# 加载 .env 文件（如果存在）
if [ -f .env ]; then
    echo "[*] 加载 .env 配置..."
    set -a
    source .env
    set +a
fi

# 检查依赖
if ! python3 -c "import flask" 2>/dev/null; then
    echo "[!] Flask 未安装，正在安装依赖..."
    pip3 install -r requirements.txt
fi

# 生产模式
if [ "$1" == "--prod" ] || [ "$1" == "prod" ]; then
    echo "[*] 生产模式：使用 Gunicorn"
    if ! command -v gunicorn &>/dev/null; then
        echo "[!] gunicorn 未安装，正在安装..."
        pip3 install gunicorn
    fi
    exec gunicorn -c gunicorn.conf.py mind_server_v2.1:app
else
    # 开发模式
    echo "[*] 开发模式：使用 Flask 内置服务器"
    echo "[*] 提示：生产环境请使用 ./start.sh --prod"
    exec python3 mind_server_v2.1.py
fi
