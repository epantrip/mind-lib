# Mind Library v2.3.0 Design: Admin Instance Approval System

**Discussion Date**: 2026-04-19
**Version**: v2.3.0 (Design Phase, Not Yet Developed)

## Core Concept

Instead of implementing a traditional web admin panel, designate an "admin instance" that notifies humans via instant messaging (IM) for approval.

## Architecture

```
New Instance Registers → Server Webhook → Admin Instance → Telegram/Signal → Human
                                                           ↓
                          Server ←─── Approve/Reject API ←─┘
```

---

## 1. Installation Guide

### Default: CLI Interactive Installation (Beginner-Friendly)

```bash
$ mind-lib setup

=== Mind Library Setup ===

[1] Admin Instance Location
  1) Local (recommended for beginners)
  2) Remote Server (requires IP:Port)
Select [1-2]: 2

Enter remote server IP: 132.226.117.183
Enter port [5000]: 5000

[2] Instant Messaging Tool
  1) Telegram Bot (recommended, stable and easy)
  2) Signal Bot (better privacy, complex development)
  3) Custom Webhook (integrate with any system)
Select [1-3]: 1

Enter Telegram Bot Token: xxxxxx
Enter Admin Chat ID: xxxxxxx

[3] Security Configuration
  - Generate JWT Secret: [auto-generated]
  - Generate Admin API Key: [auto-generated]

Configuration saved to .env
Start server: ./start.sh
```

### Advanced: Config File Template (Automation)

```bash
# Next version support
$ mind-lib setup --config /path/to/config.yaml

# Or generate template
$ mind-lib setup --template > config.yaml
# Edit config.yaml
$ mind-lib setup --config config.yaml
```

---

## 2. IM Menu

### Default: Telegram Bot

**Advantages**:
- Stable and mature, well-documented API
- Rich Python libraries (`python-telegram-bot`)
- Globally available, no firewall issues
- Excellent Inline Keyboard support

**Implementation**:
```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

keyboard = [
    [InlineKeyboardButton("✅ Approve", callback_data="approve:xxx"),
     InlineKeyboardButton("❌ Reject", callback_data="reject:xxx")]
]
```

### Next Version: Signal Bot

**Current Status**:
- `signal-cli` and `signald` libraries available
- Complex configuration, requires Signal account
- Suitable for high-privacy scenarios

**Reserved Interface**:
```python
# signal_handler.py (reserved)
class SignalHandler(IMHandler):
    def send_notification(self, message, buttons):
        # TODO: Signal implementation
        pass
```

### Universal: Custom Webhook

**Purpose**: Integrate with Discord, Slack, WeChat Work, DingTalk, etc.

**Protocol**:
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

**Response**:
```
POST <callback_url>
{
  "action": "approve" | "reject",
  "instance_id": "xxx",
  "approved_by": "human_name"
}
```

---

## 3. Security Mechanisms

### 3.1 Authorization: API Key + JWT Dual Authentication

**API Key**: Long-term authentication between instances and server
```
Headers:
  X-API-Key: ml_xxx...
  X-Instance-ID: pumpking_main
```

**JWT**: Short-term session for admin instances (anti-replay)
```
Headers:
  Authorization: Bearer <jwt_token>
  
JWT Payload:
{
  "sub": "admin_instance",
  "iat": 1713526800,
  "exp": 1713528600,  # 5-minute validity
  "jti": "unique_nonce"  # Single-use
}
```

**Dual Authentication Flow**:
1. Admin instance obtains JWT Token using API Key
2. Subsequent requests carry JWT (short-term valid)
3. Re-acquire JWT after expiration

### 3.2 Approval: Telegram/Signal Menu Approval

**Notification Message Format**:
```
🆕 New Instance Request

Instance ID: pumpking_main
Registration Time: 2026-04-19 17:00:00
IP Address: 203.0.113.45

[✅ Approve] [❌ Reject] [🔍 View Details]
```

**Anti-Misclick Design**:
- Confirmation popup after button click
- 5-minute window to undo action
- Immediate confirmation message after action

### 3.3 Logging: Audit Logs

**Log Content**:
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

**Log Storage**:
- Local file: `logs/audit.log`
- Optional: Send to SIEM / ELK
- Retention: 90 days (configurable)

### 3.4 Rate Limiting: Anti-Brute Force, Anti-DDoS

**Multi-Layer Rate Limiting**:

| Layer | Strategy | Limit |
|-------|----------|-------|
| IP Layer | Single IP request rate | 60 req/min |
| Instance Layer | Single instance API calls | 100 req/min |
| Global Layer | Total server requests | 1000 req/min |
| Auth Layer | Login/Token acquisition | 5 req/min |

**Rate Limit Response**:
```json
{
  "error": "Rate limit exceeded",
  "code": "RATE_LIMIT",
  "retry_after": 60,
  "limit": 60,
  "window": "1m"
}
```

**Anti-Brute Force**:
- 5 consecutive auth failures → IP blocked for 15 minutes
- 10 consecutive failures → Blocked for 1 hour
- Block records written to logs, configurable alerts

---

## 4. Development Tasks

### Phase 1: Server-Side (v2.3.0)

1. **JWT Authentication Module**
   - `auth/jwt.py`: JWT generation, validation, refresh
   - Endpoint: `/api/auth/token` (exchange API Key for JWT)

2. **Audit Logging Module**
   - `audit_logger.py`: Structured log output
   - Middleware: Auto-log all admin operations

3. **Rate Limiting Middleware**
   - `middleware/rate_limit.py`: Multi-layer rate limiting
   - Config: `RATE_LIMIT_*` environment variables

4. **Webhook Notifications**
   - Endpoint: `/api/webhook/admin-notify`
   - Trigger: When new instance registers

### Phase 2: Admin Instance-Side (v2.3.0)

1. **Telegram Bot Implementation**
   - `im/telegram_bot.py`: Bot main program
   - Handle Inline Keyboard callbacks
   - Call server API (JWT authentication)

2. **JWT Management**
   - Auto-acquire/refresh JWT Token
   - Auto-refresh 1 minute before expiration

### Phase 3: Installation Tool (v2.3.0)

1. **CLI Installation Wizard**
   - `cli/setup.py`: Interactive configuration
   - Generate `.env` and `docker-compose.yml`

2. **Configuration Validation**
   - Check Telegram Bot Token validity
   - Test server connectivity
   - Verify JWT signature

### Phase 4: Advanced Features (v2.4.0)

1. Signal Bot support
2. Config file template mode
3. Multi-admin instance support
4. Approval workflow (multi-level approval)

---

## 5. API Design

### 5.1 Authentication Related

```
# Get JWT Token
POST /api/auth/token
Headers: X-API-Key: <admin-api-key>
Response: {"token": "jwt_xxx", "expires_in": 300}

# Refresh JWT Token
POST /api/auth/refresh
Headers: Authorization: Bearer <jwt_token>
Response: {"token": "jwt_new_xxx", "expires_in": 300}
```

### 5.2 Instance Approval

```
# Approve Instance
POST /api/admin/approve_instance
Headers:
  Authorization: Bearer <jwt_token>
  X-Request-ID: <uuid>
Body: {"instance_id": "xxx"}

# Reject Instance
POST /api/admin/reject_instance
Headers:
  Authorization: Bearer <jwt_token>
  X-Request-ID: <uuid>
Body: {"instance_id": "xxx", "reason": "optional"}
```

### 5.3 Webhook Notifications

```
# Server → Admin Instance
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

# Admin Instance → Server (Response)
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

## 6. Configuration

### Server (.env)

```bash
# === Admin Instance Configuration ===
MIND_ADMIN_INSTANCE_ID=pumpking_main
MIND_ADMIN_NOTIFICATION_TYPE=telegram

# === JWT Configuration ===
JWT_SECRET_KEY=your-random-secret-key-min-32-chars
JWT_EXPIRE_SECONDS=300

# === Rate Limiting Configuration ===
RATE_LIMIT_IP_PER_MINUTE=60
RATE_LIMIT_INSTANCE_PER_MINUTE=100
RATE_LIMIT_GLOBAL_PER_MINUTE=1000
RATE_LIMIT_AUTH_PER_MINUTE=5

# === Audit Logs ===
AUDIT_LOG_PATH=logs/audit.log
AUDIT_LOG_RETENTION_DAYS=90
AUDIT_LOG_TO_SIEM=false

# === Brute Force Protection ===
AUTH_FAILURE_THRESHOLD=5
AUTH_FAILURE_LOCKOUT_MINUTES=15
AUTH_FAILURE_BAN_THRESHOLD=10
AUTH_FAILURE_BAN_MINUTES=60
```

### Admin Instance (.env)

```bash
# === Server Connection ===
MIND_SERVER_URL=http://132.226.117.183:5000
MIND_ADMIN_API_KEY=your-admin-api-key

# === This Instance Identity ===
MIND_INSTANCE_ID=pumpking_main

# === Telegram Configuration ===
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ADMIN_CHAT_ID=your-chat-id

# === JWT Auto-Refresh ===
JWT_REFRESH_BEFORE_EXPIRY=60  # Refresh 60 seconds before expiry
```

---

## 7. File Structure

```
server/
├── auth/
│   ├── api_key.py          # Existing
│   ├── jwt.py              # NEW: JWT authentication
│   └── __init__.py
├── middleware/
│   ├── rate_limit.py       # NEW: Rate limiting middleware
│   ├── audit_log.py        # NEW: Audit logging middleware
│   └── __init__.py
├── audit/
│   ├── logger.py           # NEW: Audit log recorder
│   └── __init__.py
├── cli/
│   ├── setup.py            # NEW: Installation wizard
│   └── __init__.py
├── mind_server_v2.3.py     # NEW: Main server (v2.3.0)
└── ...

admin-instance/             # NEW: Admin instance package
├── im/
│   ├── telegram_bot.py     # Telegram Bot implementation
│   ├── signal_handler.py   # Signal reserved interface
│   ├── webhook_handler.py  # Custom webhook
│   └── __init__.py
├── auth/
│   └── jwt_manager.py      # JWT auto-management
├── cli.py                  # Entry point
└── requirements.txt
```

---

## 8. Security Checklist

- [ ] JWT Secret Key randomly generated, ≥32 characters
- [ ] JWT Token short-term valid (5 minutes)
- [ ] API Key and JWT dual authentication
- [ ] All admin operations recorded in audit logs
- [ ] Multi-layer rate limiting (IP/instance/global/auth)
- [ ] Brute force protection (failure count lockout)
- [ ] Webhook signature verification (HMAC-SHA256)
- [ ] HTTPS enforced (production environment)
- [ ] Sensitive config not output in logs
- [ ] Regular rotation of API Key and JWT Secret

---

## 9. Notes

- **Version Target**: v2.3.0
- **Alternative**: Traditional web admin panel (no longer planned)
- **Core Advantages**: Human-in-the-loop, no public panel, security audit
- **Next Step**: Begin development after design review completion