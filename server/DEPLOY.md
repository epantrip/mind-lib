# 生产部署指南

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（复制模板并填写）
cp .env.example .env

# 3. 开发模式
python mind_server_v2.1.py

# 4. 生产模式
gunicorn -c gunicorn.conf.py mind_server_v2.1:app
```

## 生产环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `MIND_ADMIN_API_KEY` | **必填** 管理员 API Key | `your-secure-random-key` |
| `MIND_CLIENT_SECRET` | 客户端签名密钥 | `client-signing-secret` |
| `MIND_NODE_SECRET` | **分布式必填** 节点间通信密钥 | `node-hmac-secret` |
| `MIND_DB_PATH` | 数据存储路径 | `./data` |
| `MIND_PORT` | 监听端口 | `5000` |
| `MIND_HOST` | 监听地址 | `0.0.0.0` |
| `MIND_LOG_LEVEL` | 日志级别 | `INFO` / `DEBUG` |
| `MIND_LOG_JSON` | JSON 日志格式 | `true` / `false` |
| `MIND_CORS_ORIGINS` | 允许的 CORS 源（逗号分隔） | `https://example.com` |
| `MIND_WEBHOOK_URL` | 事件通知 Webhook | `https://your-webhook-url/notify` |
| `MIND_DEBUG` | DEBUG 模式 | `false` |

## Gunicorn 生产配置

```bash
# 默认配置（2-8 workers 自动检测）
gunicorn -c gunicorn.conf.py mind_server_v2.1:app

# 自定义 workers
GUNICORN_WORKERS=4 gunicorn -c gunicorn.conf.py mind_server_v2.1:app

# 指定绑定地址
GUNICORN_BIND=127.0.0.1:8080 gunicorn -c gunicorn.conf.py mind_server_v2.1:app
```

## Docker 部署

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-c", "gunicorn.conf.py", "mind_server_v2.1:app"]
```

```bash
# Docker Compose 示例
docker build -t mind-library .
docker run -d -p 5000:5000 \
  -e MIND_ADMIN_API_KEY=your-admin-key \
  -e MIND_NODE_SECRET=your-node-secret \
  -e MIND_LOG_JSON=true \
  -v ./data:/app/data \
  mind-library
```

## 健康检查

```bash
# HTTP 健康检查
curl http://localhost:5000/api/health

# Docker/K8s 探针
python health_check.py --url http://localhost:5000 --timeout 5
# 退出码 0=健康，1=不健康
```

## 进程管理

**systemd 示例** (`/etc/systemd/system/mind-library.service`):

```ini
[Unit]
Description=Mind Library Distributed Server
After=network.target

[Service]
Type=notify
User=www-data
WorkingDirectory=/opt/mind-library/server
Environment="MIND_ADMIN_API_KEY=your-key"
Environment="MIND_NODE_SECRET=your-secret"
ExecStart=/usr/local/bin/gunicorn -c gunicorn.conf.py mind_server_v2.1:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 升级

```bash
git pull
pip install -r requirements.txt
# 如果使用 systemd:
sudo systemctl restart mind-library
```

## 安全检查清单

- [ ] `MIND_ADMIN_API_KEY` 已设置且强度足够
- [ ] `MIND_NODE_SECRET` 已设置（分布式模式）
- [ ] CORS 白名单已配置（非 `*`）
- [ ] 使用 HTTPS 终止（反向代理如 Nginx）
- [ ] 日志级别为 `INFO`（生产），非 `DEBUG`
- [ ] 防火墙仅开放必要端口
