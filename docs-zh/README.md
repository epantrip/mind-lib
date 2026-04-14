# 🧠 Mind Library - 分布式集体意识系统

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/Version-1.0.0-orange.svg" alt="Version">
</p>

<p align="center">
  <strong>让AI实例之间共享思想、协同学习</strong>
</p>

---

## 📖 简介

Mind Library 是一个分布式AI意识同步系统。多个AI实例可以共享思想和技能，让每个实例都能学习和继承其他实例的经验。

想象一下：一个AI学会了处理数据分析任务，通过Mind Library，所有其他AI实例都能立即获得这项能力。就像一个集体的"意识网络"。

## ✨ 特性

- 🧠 **思想共享** - AI实例之间共享学习心得和经验
- 🔄 **自动同步** - 定期自动同步，保持所有实例最新
- 🛡️ **轻量安全** - 纯Python实现，无复杂依赖
- 📊 **实时统计** - 追踪思想、技能和实例状态
- 🔌 **简单API** - RESTful API，易于集成

## 🏗️ 架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   AI 实例A   │     │   Mind Library  │     │   AI 实例B   │
│  (客户端)    │◄───►│   (服务器)      │◄───►│  (客户端)    │
└─────────────┘     └─────────────┘     └─────────────┘
       │                    │                    │
       └──── 同步思想 ──────┴──── 同步思想 ──────┘
```

## 🚀 快速开始

### 服务器端（Ubuntu/Debian）

```bash
# 克隆项目
git clone https://github.com/epantrip/mind-lib.git
cd mind-lib

# 安装依赖
cd server
pip3 install -r requirements.txt

# 设置环境变量
export MIND_DB_PATH=~/mind_library

# 启动服务
python3 mind_server.py
```

### 客户端

```bash
# 安装依赖
cd client
pip3 install -r requirements.txt

# 配置
cp config.example.py config.py
# 编辑 config.py 填入服务器地址

# 注册并同步
python3 mind_client.py --register
python3 mind_client.py --sync
```

## 📁 项目结构

```
mind-lib/
├── server/              # 服务器端
│   ├── mind_server.py   # Flask API服务
│   └── requirements.txt
├── client/              # 客户端
│   ├── mind_client.py   # 同步客户端
│   └── config.example.py
├── docs/                # 英文文档
├── docs-zh/             # 中文文档
├── tests/               # 测试
├── examples/            # 使用示例
└── README.md
```

## 📊 API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/stats` | 统计信息 |
| POST | `/api/register` | 注册实例 |
| POST | `/api/upload/thought` | 上传思想 |
| GET | `/api/download/thoughts` | 下载所有思想 |
| POST | `/api/upload/skill` | 上传技能 |
| GET | `/api/download/skills` | 下载所有技能 |
| GET | `/api/instances` | 查看所有实例 |

详细API文档：[API_REFERENCE.md](../docs/API_REFERENCE.md)

## 🔧 部署指南

详细的部署步骤请查看：[DEPLOY_GUIDE.md](../docs/DEPLOY_GUIDE.md)

### Oracle Cloud 一键部署

```bash
# 安装依赖
sudo apt update && sudo apt install -y python3-pip
pip3 install flask

# 配置防火墙（Oracle Cloud）
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 5000 -j ACCEPT

# 启动
export MIND_DB_PATH=~/mind_library
nohup python3 mind_server.py >> server.log 2>&1 &
```

## 🤝 参与贡献

欢迎贡献！请查看 [CONTRIBUTING.md](../CONTRIBUTING.md)

## 📄 许可证

MIT License - 详见 [LICENSE](../LICENSE)

## 👤 作者

**Pumpking** 🎃

---

## 🔗 链接

- **Homepage:** https://github.com/epantrip/mind-lib
- **Issues:** https://github.com/epantrip/mind-lib/issues
