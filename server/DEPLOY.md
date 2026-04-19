# Production Deployment Guide

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment variables (copy template and fill in)
cp .env.example .env

# 3. Development mode
python mind_server_v2.1.py

# 4. Production mode
gunicorn -c gunicorn.conf.py mind_server_v2.1:app
```

## Production Environment Variables

| Variable | Description | Example |
|------|------|------|
| `MIND_ADMIN_API_KEY` | **Required** Admin API Key | `your-secure-random-key` |
| `MIND_CLIENT_SECRET` | Client signing secret | `client-signing-secret` |
| `MIND_NODE_SECRET` | **Required for distributed mode** Node-to-node communication secret | `node-hmac-secret` |
| `MIND_DB_PATH` | Data storage path | `./data` |
| `MIND_PORT` | Listening port | `5000` |
| `MIND_HOST` | Listening address | `0.0.0.0` |
| `MIND_LOG_LEVEL` | Log level | `INFO` / `DEBUG` |
| `MIND_LOG_JSON` | JSON log format | `true` / `false` |
| `MIND_CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `https://example.com` |
| `MIND_WEBHOOK_URL` | Event notification Webhook | `https://your-webhook-url/notify` |
| `MIND_DEBUG` | DEBUG mode | `false` |

## Gunicorn Production Configuration

```bash
# Default configuration (2-8 workers auto-detected)
gunicorn -c gunicorn.conf.py mind_server_v2.1:app

# Custom workers
GUNICORN_WORKERS=4 gunicorn -c gunicorn.conf.py mind_server_v2.1:app

# Specify bind address
GUNICORN_BIND=127.0.0.1:8080 gunicorn -c gunicorn.conf.py mind_server_v2.1:app
```

## Docker Deployment

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
# Docker Compose example
docker build -t mind-library .
docker run -d -p 5000:5000 \
  -e MIND_ADMIN_API_KEY=your-admin-key \
  -e MIND_NODE_SECRET=your-node-secret \
  -e MIND_LOG_JSON=true \
  -v ./data:/app/data \
  mind-library
```

## Health Check

```bash
# HTTP health check
curl http://localhost:5000/api/health

# Docker/K8s probe
python health_check.py --url http://localhost:5000 --timeout 5
# Exit code 0=healthy, 1=unhealthy
```

## Process Management

**systemd example** (`/etc/systemd/system/mind-library.service`):

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

## Upgrade

```bash
git pull
pip install -r requirements.txt
# If using systemd:
sudo systemctl restart mind-library
```

## Security Checklist

- [ ] `MIND_ADMIN_API_KEY` is set and sufficiently strong
- [ ] `MIND_NODE_SECRET` is set (distributed mode)
- [ ] CORS whitelist configured (not `*`)
- [ ] Using HTTPS termination (reverse proxy like Nginx)
- [ ] Log level set to `INFO` (production), not `DEBUG`
- [ ] Firewall only exposes necessary ports
