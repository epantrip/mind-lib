# Mind Library v2.3.0 - Admin Instance Approval System

## Overview

Add an admin instance-based approval workflow instead of traditional web admin panel.

## Architecture

```
New Instance Registers → Server Webhook → Admin Instance → IM (Telegram/Signal) → Human
                                                           ↓
                          Server ←─── Approve/Reject API ←─┘
```

## User Requirements (from 2026-04-19 discussion)

### 1. Admin Instance Location

During server installation, prompt user to select:

- **Local**: Admin instance runs locally, connect directly to server
- **Cloud/Remote**: Admin instance runs on user's cloud server or elsewhere, need to input IP:port

Implementation: Prompt in `start.sh` / `start.bat` or `.env` configuration.

### 2. IM Tool Selection

Provide menu during installation to choose:

- **Telegram** (recommended, already in use)
- **Signal** (better privacy)
- Custom webhook URL (for other tools like Discord, Slack, etc.)

Implementation: Environment variable `MIND_ADMIN_NOTIFICATION_TYPE` (telegram|signal|custom)

### 3. Inline Buttons

When human receives notification, show inline buttons:

- ✅ Approve
- ❌ Reject

Implementation: Telegram Bot Inline Keyboard or Signal similar feature.

### 4. Installation Package

- Include installation instructions in server package
- Recommend installing on user's cloud server where AI instances are running
- Simple setup: `start.sh` / `start.bat` + `.env` configuration

---

## Development Tasks

### Phase 1: Server-side Changes

1. **Notify Admin Instance** (server)
   - Add config: `MIND_ADMIN_INSTANCE_ID` (which instance is admin)
   - When new instance registers → POST to admin instance's webhook
   - Payload: `{event: "new_instance", instance_id, registration_time, ...}`

2. **Admin Instance Endpoint** (server)
   - Add `/api/webhook/admin` endpoint to receive notifications
   - Forward to IM tool

### Phase 2: Admin Instance Side

1. **Webhook Handler**
   - Receive notification from server
   - Format message for IM

2. **Telegram Bot Integration**
   - Send message with inline keyboard (Approve/Reject)
   - Handle callback from inline buttons
   - Call server API to approve/reject

3. **Signal Integration** (if supported)
   - Similar flow for Signal

### Phase 3: Installation Experience

1. **Installation Prompts**
   - Ask: Where is admin instance? (local/cloud)
   - Ask: Which IM tool? (Telegram/Signal/Custom)
   - Generate .env with appropriate settings

2. **Documentation**
   - Include INSTALL.md in server package
   - Recommend cloud server deployment
   - Explain local vs remote admin instance

---

## API Design

### Server → Admin Instance Webhook

```
POST <admin-instance-url>/api/webhook/admin-notify
Content-Type: application/json

{
  "event": "new_instance_registered",
  "instance_id": "pumpking_main",
  "registered_at": "2026-04-19T16:00:00Z",
  "api_key_prefix": "ml_abc123..."
}
```

### Admin Instance → Server Approve/Reject

```
POST http://<server>:5000/api/admin/approve_instance
Headers: X-API-Key: <admin-api-key>
Body: {"instance_id": "pumpking_main"}

POST http://<server>:5000/api/admin/reject_instance
Headers: X-API-Key: <admin-api-key>
Body: {"instance_id": "pumpking_main"}
```

---

## Configuration

### Server (.env)

```bash
# Admin Instance (which instance handles admin notifications)
MIND_ADMIN_INSTANCE_ID=pumpking_main

# How to notify admin (telegram|signal|custom)
MIND_ADMIN_NOTIFICATION_TYPE=telegram

# For custom webhook
MIND_ADMIN_WEBHOOK_URL=https://...

# Admin API Key (for admin instance to call server API)
MIND_ADMIN_API_KEY=your-admin-api-key
```

### Admin Instance (.env)

```bash
# Server connection
MIND_SERVER_URL=http://132.226.117.183:5000

# This instance's credentials (to call server API)
MIND_INSTANCE_ID=pumpking_main
MIND_INSTANCE_KEY=your-instance-key

# IM Configuration
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ADMIN_CHAT_ID=your-chat-id

# Or Signal
SIGNAL_CLI_NUMBER=+1234567890
```

---

## File Changes

### Server-side (mind_server_v2.1.py)

1. Add `/api/webhook/admin-notify` endpoint
2. When instance registers, notify admin instance
3. Config in `config.py`: `ADMIN_INSTANCE_ID`, `NOTIFICATION_TYPE`, `ADMIN_WEBHOOK_URL`

### Client-side (mind_client.py or new admin_client.py)

1. Webhook handler to receive notifications
2. Telegram/Signal integration for IM
3. Callback handler for inline buttons

---

## Notes

- Version target: v2.3.0
- This replaces the need for traditional web admin panel
- More secure: no public admin panel, all through trusted admin instance
- Human-in-the-loop: all approvals go through human via IM