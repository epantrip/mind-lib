# Mind Library v2.3.0 设计方案：实例审批系统

**讨论日期**: 2026-04-19
**版本**: v2.3.0 (设计阶段，未开发)

## 核心理念

不实现传统 Web 管理面板，而是指定一个"管理员实例"，通过即时通讯（IM）通知人类审批。

## 架构

```
新实例注册 → 服务器 Webhook → 管理员实例 → Telegram/Signal → 人类
                                                           ↓
                          服务器 ←─── 批准/拒绝 API ←───────┘
```

---

## 1. 安装引导

### 默认：CLI 交互式安装（新手友好）

```bash
$ mind-lib setup

=== Mind Library Setup ===

[1] 管理员实例位置
  1) 本地运行（推荐新手）
  2) 远程服务器（需输入 IP:Port）
请选择 [1-2]: 2

请输入远程服务器 IP: 132.226.117.183
请输入端口 [5000]: 5000

[2] 即时通讯工具
  1) Telegram Bot（推荐，稳定易用）
  2) Signal Bot（隐私更好，开发复杂）
  3) 自定义 Webhook（对接任意系统）
请选择 [1-3]: 1

请输入 Telegram Bot Token: xxxxxx
请输入管理员 Chat ID: xxxxxxx

[3] 安全配置
  - 生成 JWT Secret: [自动生成]
  - 生成 Admin API Key: [自动生成]

配置已保存到 .env
启动服务器: ./start.sh
```

### 进阶：配置文件模板（自动化）

```bash
# 下一版本支持
$ mind-lib setup --config /path/to/config.yaml

# 或生成模板
$ mind-lib setup --template > config.yaml
# 编辑 config.yaml 后
$ mind-lib setup --config config.yaml
```

---

## 2. IM 菜单

### 默认：Telegram Bot

**优势**:
- 稳定成熟，API 文档完善
- Python 库丰富 (`python-telegram-bot`)
- 全球可用，无需翻墙
- Inline Keyboard 支持良好

**实现**:
```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

keyboard = [
    [InlineKeyboardButton("✅ 批准", callback_data="approve:xxx"),
     InlineKeyboardButton("❌ 拒绝", callback_data="reject:xxx")]
]
```

### 下一版本：Signal Bot

**现状**:
- 有 `signal-cli` 和 `signald` 库
- 但配置复杂，需要 Signal 账号
- 适合隐私要求极高的场景

**暂不实现，预留接口**:
```python
# signal_handler.py (预留)
class SignalHandler(IMHandler):
    def send_notification(self, message, buttons):
        # TODO: Signal implementation
        pass
```

### 通用：自定义 Webhook

**用途**: 对接 Discord、Slack、企业微信、钉钉等

**协议**:
```
POST <webhook_url>
Content-Type: application/json

{
  "event": "new_instance",
  "instance_id": "xxx",
  "timestamp": "2026-04-19T17:00:00Z",
  "callback_url": "https://server/api/webhook/response"
}
```

**响应**:
```
POST <callback_url>
{
  "action": "approve" | "reject",
  "instance_id": "xxx",
  "approved_by": "human_name"
}
```

---

## 3. 安全机制

### 3.1 授权：API Key + JWT 双认证

**API Key**: 用于实例与服务器之间的长期认证
```
Headers:
  X-API-Key: ml_xxx...
  X-Instance-ID: pumpking_main
```

**JWT**: 用于管理员实例的短期会话（防重放攻击）
```
Headers:
  Authorization: Bearer <jwt_token>
  
JWT Payload:
{
  "sub": "admin_instance",
  "iat": 1713526800,
  "exp": 1713528600,  # 5分钟有效期
  "jti": "unique_nonce"  # 一次性使用
}
```

**双认证流程**:
1. 管理员实例用 API Key 获取 JWT Token
2. 后续请求携带 JWT（短期有效）
3. JWT 过期后需重新获取

### 3.2 审批：Telegram/Signal 菜单审批

**通知消息格式**:
```
🆕 新实例申请

实例ID: pumpking_main
注册时间: 2026-04-19 17:00:00
IP地址: 203.0.113.45

[✅ 批准] [❌ 拒绝] [🔍 查看详情]
```

**防误触设计**:
- 点击按钮后显示确认弹窗
- 5分钟内可撤销操作
- 操作后立即推送确认消息

### 3.3 日志：审计日志

**日志内容**:
```json
{
  "timestamp": "2026-04-19T17:00:00Z",
  "level": "AUDIT",
  "event": "instance_approved",
  "instance_id": "pumpking_main",
  "approved_by": "admin_instance",
  "approved_via": "telegram",
  "client_ip": "203.0.113.45",
  "server_ip": "132.226.117.183",
  "request_id": "req_xxx",
  "user_agent": "python-requests/2.31.0"
}
```

**日志存储**:
- 本地文件: `logs/audit.log`
- 可选: 发送到 SIEM / ELK
- 保留期: 90天（可配置）

### 3.4 限流：防暴力破解、防 DDoS

**多层限流**:

| 层级 | 策略 | 限制 |
|------|------|------|
| IP 层 | 单 IP 请求频率 | 60 req/min |
| 实例层 | 单实例 API 调用 | 100 req/min |
| 全局层 | 服务器总请求 | 1000 req/min |
| 认证层 | 登录/Token 获取 | 5 req/min |

**限流响应**:
```json
{
  "error": "Rate limit exceeded",
  "code": "RATE_LIMIT",
  "retry_after": 60,
  "limit": 60,
  "window": "1m"
}
```

**防暴力破解**:
- 连续 5 次认证失败 → IP 封禁 15 分钟
- 连续 10 次 → 封禁 1 小时
- 封禁记录写入日志，可配置告警

---

## 4. 开发任务

### 阶段一：服务器端（v2.3.0）

1. **JWT 认证模块**
   - `auth/jwt.py`: JWT 生成、验证、刷新
   - 端点: `/api/auth/token` (用 API Key 换 JWT)

2. **审计日志模块**
   - `audit_logger.py`: 结构化日志输出
   - 中间件: 自动记录所有管理操作

3. **限流中间件**
   - `middleware/rate_limit.py`: 多层限流
   - 配置: `RATE_LIMIT_*` 环境变量

4. **Webhook 通知**
   - 端点: `/api/webhook/admin-notify`
   - 触发: 新实例注册时

### 阶段二：管理员实例端（v2.3.0）

1. **Telegram Bot 实现**
   - `im/telegram_bot.py`: Bot 主程序
   - 处理 Inline Keyboard 回调
   - 调用服务器 API（JWT 认证）

2. **JWT 管理**
   - 自动获取/刷新 JWT Token
   - Token 过期前 1 分钟自动刷新

### 阶段三：安装工具（v2.3.0）

1. **CLI 安装向导**
   - `cli/setup.py`: 交互式配置
   - 生成 `.env` 和 `docker-compose.yml`

2. **配置验证**
   - 检查 Telegram Bot Token 有效性
   - 测试服务器连通性
   - 验证 JWT 签名

### 阶段四：进阶功能（v2.4.0）

1. Signal Bot 支持
2. 配置文件模板模式
3. 多管理员实例支持
4. 审批工作流（多级审批）

---

## 5. API 设计

### 5.1 认证相关

```
# 获取 JWT Token
POST /api/auth/token
Headers: X-API-Key: <admin-api-key>
Response: {"token": "jwt_xxx", "expires_in": 300}

# 刷新 JWT Token
POST /api/auth/refresh
Headers: Authorization: Bearer <jwt_token>
Response: {"token": "jwt_new_xxx", "expires_in": 300}
```

### 5.2 实例审批

```
# 批准实例
POST /api/admin/approve_instance
Headers:
  Authorization: Bearer <jwt_token>
  X-Request-ID: <uuid>
Body: {"instance_id": "xxx"}

# 拒绝实例
POST /api/admin/reject_instance
Headers:
  Authorization: Bearer <jwt_token>
  X-Request-ID: <uuid>
Body: {"instance_id": "xxx", "reason": "optional"}
```

### 5.3 Webhook 通知

```
# 服务器 → 管理员实例
POST /api/webhook/admin-notify
Headers:
  X-Signature: <hmac_signature>
  X-Timestamp: <unix_timestamp>
Body: {
  "event": "new_instance_registered",
  "instance_id": "pumpking_main",
  "registered_at": "2026-04-19T17:00:00Z",
  "client_ip": "203.0.113.45",
  "callback_url": "https://server/api/webhook/response"
}

# 管理员实例 → 服务器（响应）
POST /api/webhook/response
Headers:
  Authorization: Bearer <jwt_token>
Body: {
  "action": "approve",
  "instance_id": "pumpking_main",
  "approved_by": "human_name",
  "timestamp": "2026-04-19T17:01:00Z"
}
```

---

## 6. 配置

### 服务器 (.env)

```bash
# === 管理员实例配置 ===
MIND_ADMIN_INSTANCE_ID=pumpking_main
MIND_ADMIN_NOTIFICATION_TYPE=telegram

# === JWT 配置 ===
JWT_SECRET_KEY=your-random-secret-key-min-32-chars
JWT_EXPIRE_SECONDS=300

# === 限流配置 ===
RATE_LIMIT_IP_PER_MINUTE=60
RATE_LIMIT_INSTANCE_PER_MINUTE=100
RATE_LIMIT_GLOBAL_PER_MINUTE=1000
RATE_LIMIT_AUTH_PER_MINUTE=5

# === 审计日志 ===
AUDIT_LOG_PATH=logs/audit.log
AUDIT_LOG_RETENTION_DAYS=90
AUDIT_LOG_TO_SIEM=false

# === 暴力破解防护 ===
AUTH_FAILURE_THRESHOLD=5
AUTH_FAILURE_LOCKOUT_MINUTES=15
AUTH_FAILURE_BAN_THRESHOLD=10
AUTH_FAILURE_BAN_MINUTES=60
```

### 管理员实例 (.env)

```bash
# === 服务器连接 ===
MIND_SERVER_URL=http://132.226.117.183:5000
MIND_ADMIN_API_KEY=your-admin-api-key

# === 本实例标识 ===
MIND_INSTANCE_ID=pumpking_main

# === Telegram 配置 ===
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ADMIN_CHAT_ID=your-chat-id

# === JWT 自动刷新 ===
JWT_REFRESH_BEFORE_EXPIRY=60  # 提前60秒刷新
```

---

## 7. 文件结构

```
server/
├── auth/
│   ├── api_key.py          # 现有
│   ├── jwt.py              # 新增：JWT 认证
│   └── __init__.py
├── middleware/
│   ├── rate_limit.py       # 新增：限流中间件
│   ├── audit_log.py        # 新增：审计日志中间件
│   └── __init__.py
├── audit/
│   ├── logger.py           # 新增：审计日志记录器
│   └── __init__.py
├── cli/
│   ├── setup.py            # 新增：安装向导
│   └── __init__.py
├── mind_server_v2.3.py     # 新增：主服务器（v2.3.0）
└── ...

admin-instance/             # 新增：管理员实例包
├── im/
│   ├── telegram_bot.py     # Telegram Bot 实现
│   ├── signal_handler.py   # Signal 预留接口
│   ├── webhook_handler.py  # 自定义 Webhook
│   └── __init__.py
├── auth/
│   └── jwt_manager.py      # JWT 自动管理
├── cli.py                  # 入口
└── requirements.txt
```

---

## 8. 安全清单

- [ ] JWT Secret Key 随机生成，≥32字符
- [ ] JWT Token 短期有效（5分钟）
- [ ] API Key 和 JWT 双认证
- [ ] 所有管理操作记录审计日志
- [ ] 多层限流（IP/实例/全局/认证）
- [ ] 暴力破解防护（失败次数锁定）
- [ ] Webhook 签名验证（HMAC-SHA256）
- [ ] HTTPS 强制（生产环境）
- [ ] 敏感配置不在日志中输出
- [ ] 定期轮换 API Key 和 JWT Secret

---

## 9. 备注

- **版本目标**: v2.3.0
- **替代方案**: 传统 Web 管理面板（不再开发）
- **核心优势**: 人在环中、无公开面板、安全审计
- **下一步**: 完成设计评审后开始开发