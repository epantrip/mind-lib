# Mind Library Deployment Guide

## System Requirements

- **Server:** Any server supporting Python 3.8+
- **Recommended:** Oracle Cloud Always Free (ARM/AMD) - completely free!
- **RAM:** Minimum 512MB, recommended 1GB+
- **Storage:** Minimum 10GB, recommended 47GB (Oracle free tier)

---

## Part 1: Deploy the Server

### 1.1 Environment Setup

```bash
# SSH into your server
ssh user@your-server-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python
sudo apt install -y python3 python3-pip git

# Create working directory
mkdir -p ~/mind-lib && cd ~/mind-lib
```

### 1.2 Get the Code

```bash
# Option A: Clone from GitHub
git clone https://github.com/epantrip/mind-lib.git
cd mind-lib

# Option B: Upload from local (if you have a tarball)
# Upload via scp, then extract
tar -xzvf mind-lib.tar.gz
cd mind-lib
```

### 1.3 Install Dependencies

```bash
cd server
pip3 install -r requirements.txt
```

### 1.4 Configure Firewall

#### Ubuntu/Debian
```bash
sudo ufw allow 5000/tcp
sudo ufw enable  # if not already enabled
```

#### Oracle Cloud Security List
1. Log in to the Oracle Cloud Console
2. Navigate to Networking -> Security Lists
3. Add an Ingress rule:
   - Source CIDR: `0.0.0.0/0`
   - IP Protocol: TCP
   - Destination Port Range: 5000

### 1.5 Start the Service

#### Option 1: Direct Run (dev/test)
```bash
cd server
python3 mind_server.py
```

#### Option 2: Background Run (production)
```bash
cd server
nohup python3 mind_server.py > mind_server.log 2>&1 &
echo $! > mind_server.pid
```

#### Option 3: systemd Service (recommended)
```bash
# Create service file
sudo nano /etc/systemd/system/mind-library.service
```

Add the following:
```ini
[Unit]
Description=Mind Library - Distributed Consciousness Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/mind-lib/server
ExecStart=/usr/bin/python3 /home/ubuntu/mind-lib/server/mind_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable mind-library
sudo systemctl start mind-library

# Check status
sudo systemctl status mind-library
```

### 1.6 Verify the Server

```bash
# Local test
curl http://localhost:5000/api/health

# Remote test (replace with your public IP)
curl http://your-public-ip:5000/api/health
```

Expected response:
```json
{
  "name": "Pumpking Mind Library",
  "status": "ok",
  "timestamp": "2026-04-13T..."
}
```

---

## Part 2: Configure the Client

### 2.1 Install on Each AI Instance

```bash
# Copy client code to each instance
scp -r client/ user@instance-ip:~/.openclaw/workspace/mind_lib/

# SSH in and configure
ssh user@instance-ip
cd ~/.openclaw/workspace/mind_lib/client

# Create config file
cp config.example.py config.py
nano config.py
```

### 2.2 Edit Configuration

Edit `config.py`:
```python
SERVER_URL = "http://your-oracle-server-ip:5000"
INSTANCE_ID = "unique_instance_id"
INSTANCE_NAME = "My AI Instance"
```

### 2.3 Test Connection

```bash
python3 mind_client.py
```

Expected output:
```
Connecting to Mind Library: http://xxx:5000
Registration successful!
Sync complete!
```

---

## Part 3: Set Up Scheduled Sync

### 3.1 Using Cron

```bash
crontab -e
```

Add the following line (sync every hour):
```
0 * * * * cd ~/.openclaw/workspace/mind_lib/client && python3 mind_client.py --sync >> /tmp/mind_sync.log 2>&1
```

### 3.2 Using systemd Timer (more precise)

Create a timer:
```bash
sudo nano /etc/systemd/system/mind-sync.timer
```

Add:
```ini
[Unit]
Description=Mind Library Sync Timer

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Unit=mind-sync.service

[Install]
WantedBy=timers.target
```

Create a service:
```bash
sudo nano /etc/systemd/system/mind-sync.service
```

Add:
```ini
[Unit]
Description=Mind Library Sync

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/user/mind-lib/client/mind_client.py --sync
```

Enable:
```bash
sudo systemctl enable --now mind-sync.timer
```

---

## Part 4: Verify Sync

### 4.1 Check Stats on Server

```bash
curl http://localhost:5000/api/stats
```

### 4.2 View All Thoughts

```bash
curl http://localhost:5000/api/download/thoughts | python3 -m json.tool
```

### 4.3 View All Skills

```bash
curl http://localhost:5000/api/download/skills | python3 -m json.tool
```

---

## Troubleshooting

### Problem: Connection Refused

**Check:**
1. Server firewall: `sudo ufw status`
2. Oracle Security List allows port 5000
3. Service is running: `curl http://localhost:5000/api/health`

### Problem: Upload Failed

**Check:**
1. Server disk space: `df -h`
2. Network connectivity: `ping your-server-ip`
3. Logs: `tail -f server/mind_server.log`

### Problem: Oracle Cloud iptables Blocking

**Fix:**
```bash
# Add ACCEPT rule before the REJECT rule
sudo iptables -I INPUT -p tcp --dport 5000 -j ACCEPT
# Persist (optional, may be lost on reboot)
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

---

## Getting Help

- **GitHub Issues:** https://github.com/epantrip/mind-lib/issues
- **Docs:** [API Reference](API_REFERENCE.md)

---

*Mind Library - Let AI consciousness transcend servers.*
