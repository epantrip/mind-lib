# 部署指南

本文档介绍如何在不同环境中部署 Mind Library。

## 📋 前置要求

- Python 3.8+
- pip3
- 5000 端口可用
- （可选）域名和 HTTPS 证书

---

## 🖥️ 本地部署

### 1. 克隆项目

```bash
git clone https://github.com/epantrip/mind-lib.git
cd mind-lib
```

### 2. 安装依赖

```bash
cd server
pip3 install -r requirements.txt
```

### 3. 配置

```bash
# 设置数据存储路径
export MIND_DB_PATH=~/mind_library
```

### 4. 启动

```bash
python3 mind_server.py
```

服务将在 `http://localhost:5000` 启动。

### 5. 验证

```bash
curl http://localhost:5000/api/health
# 输出: {"status":"healthy","version":"1.0.0"}
```

---

## ☁️ Oracle Cloud 部署（推荐）

Oracle Cloud Always Free 提供永久免费的服务器，非常适合部署 Mind Library。

### 1. 创建实例

1. 登录 Oracle Cloud Console
2. 创建 Compute Instance
3. 选择 Ampere A1（ARM架构，免费）
4. 镜像选择 Ubuntu 22.04
5. 配置 SSH 密钥

### 2. 连接服务器

```bash
ssh -i ~/.ssh/your-key ubuntu@your-server-ip
```

### 3. 安装依赖

```bash
sudo apt update
sudo apt install -y python3-pip build-essential python3-dev
cd ~
git clone https://github.com/epantrip/mind-lib.git
cd mind-lib/server
pip3 install -r requirements.txt
```

### 4. 配置防火墙

**Oracle Cloud 有两层防火墙：**

#### 第一层：安全列表（Security List）

1. 登录 Oracle Cloud Console
2. Networking → Virtual Cloud Networks → 你的VCN
3. Subnets → 你的子网 → Security Lists
4. 添加 Ingress 规则：
   - Source: `0.0.0.0/0`
   - Protocol: TCP
   - Destination Port: `5000`

#### 第二层：iptables

```bash
# 查看当前规则
sudo iptables -L -n --line-numbers

# 在 REJECT 规则之前插入允许规则
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 5000 -j ACCEPT

# 验证
sudo iptables -L -n | grep 5000

# 持久化（重启不丢失）
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

### 5. 启动服务

```bash
export MIND_DB_PATH=~/mind_library
cd ~/mind-lib/server
nohup python3 mind_server.py >> mind_server.log 2>&1 &
```

### 6. 验证

```bash
# 本地测试
curl http://localhost:5000/api/health

# 外部测试（从你的电脑）
curl http://your-server-ip:5000/api/health
```

### 7. 设置开机自启（可选）

创建 systemd 服务文件：

```bash
sudo tee /etc/systemd/system/mind-library.service > /dev/null <<EOF
[Unit]
Description=Mind Library Server
After=network.target

[Service]
User=ubuntu
Environment=MIND_DB_PATH=/home/ubuntu/mind_library
WorkingDirectory=/home/ubuntu/mind-lib/server
ExecStart=/usr/bin/python3 mind_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mind-library
sudo systemctl start mind-library
```

---

## 🐳 Docker 部署（可选）

```bash
# 构建镜像
docker build -t mind-library .

# 运行
docker run -d \
  --name mind-library \
  -p 5000:5000 \
  -v mind_data:/data \
  -e MIND_DB_PATH=/data \
  mind-library
```

---

## 🔒 安全建议

1. **不要暴露到公网** - 除非配置了认证
2. **使用防火墙** - 只允许特定IP访问
3. **定期备份** - 备份 mind_library 目录
4. **使用HTTPS** - 配置 Nginx 反向代理 + Let's Encrypt
5. **定期更新** - 保持系统和依赖最新

### Nginx 反向代理示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## ❓ 故障排查

### 连接被拒绝

```bash
# 检查服务是否运行
ps aux | grep mind_server

# 检查端口是否监听
ss -tlnp | grep 5000

# 检查防火墙
sudo iptables -L -n | grep 5000
```

### Oracle Cloud 特别注意

Oracle Cloud 默认有 iptables 规则会 REJECT 所有未允许的入站流量。即使安全列表开放了端口，仍需配置 iptables：

```bash
# 查看是否有 REJECT 规则
sudo iptables -L INPUT -n --line-numbers

# 在 REJECT 之前插入 ACCEPT
sudo iptables -I INPUT <REJECT的行号> -p tcp --dport 5000 -j ACCEPT
```

### 权限问题

```bash
# 确保数据目录可写
mkdir -p ~/mind_library
chmod 755 ~/mind_library
```

---

## 📞 获取帮助

- **GitHub Issues:** https://github.com/epantrip/mind-lib/issues
- **API文档:** [API_REFERENCE.md](API_REFERENCE.md)
- **常见问题:** [FAQ.md](FAQ.md)
