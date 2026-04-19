# Mind Library v2.3.0 设计方案：实例审批系统

**讨论日期**: 2026-04-19

## 核心理念

不实现传统 Web 管理面板，而是指定一个"管理员实例"，通过即时通讯（IM）通知人类审批。

## 架构

```
新实例注册 → 服务器 Webhook → 管理员实例 → Telegram/Signal → 人类
                                                           ↓
                          服务器 ←─── 批准/拒绝 API ←───────┘
```

## 用户需求（来自讨论）

### 1. 管理员实例安装位置

服务器安装时让用户选择：

- **本地**：管理员实例运行在本机，直接连接服务器
- **云/远程**：管理员实例运行在云服务器或其他地方，需输入 IP:Port

实现：`start.sh` / `start.bat` 或 `.env` 配置时提示。

### 2. 即时通讯工具选择

安装时提供菜单选择：

- **Telegram**（推荐，已在用）
- **Signal**（隐私更好）
- 自定义 Webhook（用于 Discord、Slack 等）

实现：环境变量 `MIND_ADMIN_NOTIFICATION_TYPE` (telegram|signal|custom)

### 3. Inline Buttons

人类收到通知时显示：

- ✅ 批准
- ❌ 拒绝

实现：Telegram Bot Inline Keyboard 或 Signal 类似功能。

### 4. 安装包

- 服务器安装包包含安装说明
- 优先推荐在用户拥有的、AI 实例正在运行的云服务器上安装
- 简单安装：`start.sh` / `start.bat` + `.env` 配置

---

## 开发任务

### 阶段一：服务器端改动

1. **通知管理员实例**
   - 新增配置：`MIND_ADMIN_INSTANCE_ID`（哪个实例是管理员）
   - 新实例注册时 → POST 到管理员实例的 webhook
   - Payload: `{event: "new_instance", instance_id, registration_time, ...}`

2. **管理员实例端点**
   - 新增 `/api/webhook/admin` 端点接收通知
   - 转发到 IM 工具

### 阶段二：管理员实例端

1. **Webhook 处理**
   - 接收服务器通知
   - 格式化消息发给 IM

2. **Telegram Bot 集成**
   - 发送带 Inline Keyboard 的消息
   - 处理回调，执行批准/拒绝 API

3. **Signal 集成**（如果支持）
   - 类似 Signal 流程

### 阶段三：安装体验

1. **安装引导**
   - 问：管理员实例在哪？（本地/云）
   - 问：用哪个 IM？（Telegram/Signal/自定义）
   - 生成对应配置的 .env

2. **文档**
   - 包内包含 INSTALL.md
   - 推荐云服务器部署
   - 解释本地 vs 远程管理员实例

---

## API 设计

### 服务器 → 管理员实例 Webhook

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

### 管理员实例 → 服务器 批准/拒绝

```
POST http://<server>:5000/api/admin/approve_instance
Headers: X-API-Key: <admin-api-key>
Body: {"instance_id": "pumpking_main"}

POST http://<server>:5000/api/admin/reject_instance
Headers: X-API-Key: <admin-api-key>
Body: {"instance_id": "pumpking_main"}
```

---

## 配置

### 服务器 (.env)

```bash
# 管理员实例（哪个实例处理管理通知）
MIND_ADMIN_INSTANCE_ID=pumpking_main

# 如何通知管理员 (telegram|signal|custom)
MIND_ADMIN_NOTIFICATION_TYPE=telegram

# 自定义 webhook
MIND_ADMIN_WEBHOOK_URL=https://...

# 管理员 API Key（用于管理员实例调用服务器 API）
MIND_ADMIN_API_KEY=your-admin-api-key
```

### 管理员实例 (.env)

```bash
# 服务器连接
MIND_SERVER_URL=http://132.226.117.183:5000

# 本实例凭据（调用服务器 API 用）
MIND_INSTANCE_ID=pumpking_main
MIND_INSTANCE_KEY=your-instance-key

# IM 配置
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ADMIN_CHAT_ID=your-chat-id

# 或 Signal
SIGNAL_CLI_NUMBER=+1234567890
```

---

## 文件改动

### 服务端 (mind_server_v2.1.py)

1. 新增 `/api/webhook/admin-notify` 端点
2. 实例注册时通知管理员实例
3. 配置在 `config.py`: `ADMIN_INSTANCE_ID`, `NOTIFICATION_TYPE`, `ADMIN_WEBHOOK_URL`

### 客户端 (mind_client.py 或新的 admin_client.py)

1. Webhook 处理程序接收通知
2. Telegram/Signal IM 集成
3. Inline Buttons 回调处理

---

## 备注

- 版本目标：v2.3.0
- 替代传统 Web 管理面板需求
- 更安全：无公开管理面板，所有操作通过可信管理员实例
- 人在环中：所有审批通过 IM 由人类完成