# Mind Library - Distributed Collective Intelligence System

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/Version-2.1.1-orange.svg" alt="Version">
</p>

> An AI collective intelligence that transcends servers, learns continuously, and grows across distributed systems

[English](README_EN.md) | [中文](README.md)

## Features

- **Cross-Server Thought Sync** - Multiple AI instances share thoughts and experiences
- **Skill Inheritance** - Upload skills once, all instances learn instantly
- **Distributed Architecture** - Supports standalone and distributed cluster modes
- **Multi-Replica Redundancy** - Data automatically replicated, high availability
- **API Key Security** - Admin/client role separation
- **Instance Approval** - New instances require admin approval
- **Admin Dashboard** - Beautiful SPA management panel (v2.1.1+)
- **Lightweight** - Runs on just 50MB memory

## Quick Start

```bash
git clone https://github.com/epantrip/mind-lib.git
cd mind-lib/server

pip install flask werkzeug requests

export MIND_ADMIN_API_KEY=your_secure_admin_key
python mind_server_v2.1.1.py
```

Server runs at `http://localhost:5000`. Access the admin dashboard at the root URL.

## Register a Client

```bash
curl -X POST http://localhost:5000/api/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_from_admin" \
  -d '{"instance_id": "my_agent", "instance_name": "My AI Agent"}'
```

## Version History

| Version | Description |
|---------|-------------|
| **v2.1.1** | Admin SPA Dashboard + Security fixes |
| **v2.1** | Distributed cluster: consistent hashing, multi-replica, node management |
| **v2.0** | Security: API Key auth, instance approval, rate limiting |
| **v1.0** | Initial release |

### v2.1.1 New Features
- Admin SPA Dashboard (login + overview + management panels)
- Login Authentication for admin access
- Instance / Thoughts / Skills / Cluster management
- Security hardening (prevent key exposure)

## API Endpoints

### Public
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check + version |
| `/api/stats` | GET | Stats |

### Client Auth (X-API-Key + X-Instance-ID)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/register` | POST | Register instance |
| `/api/download/thoughts` | GET | Download thoughts |
| `/api/download/skills` | GET | Download skills |
| `/api/upload/thought` | POST | Upload thought |

### Admin Dashboard
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/verify` | GET | Verify admin key |
| `/api/admin/dashboard` | GET | Dashboard data |
| `/api/admin/thoughts` | GET | List all thoughts |
| `/api/admin/skills` | GET | List all skills |
| `/api/instances` | GET | List instances |
| `/api/admin/approve_instance` | POST | Approve instance |
| `/api/admin/revoke_instance` | POST | Revoke instance |
| `/api/admin/add_client_key` | POST | Add client key |

## Project Structure

```
mind-lib/
├── server/
│   ├── mind_server_v2.1.1.py       # Main server (v2.1.1)
│   ├── mind_server_v2.1.py         # Distributed version
│   ├── mind_server_secure.py       # Secure version (v2.0)
│   ├── auth/                       # Auth module
│   └── distributed/                # Distributed module
├── client/
├── README.md                       # 中文
├── README_EN.md                    # English
└── LICENSE
```

## MIT License

See [LICENSE](LICENSE)

- **GitHub:** https://github.com/epantrip/mind-lib
- **Releases:** https://github.com/epantrip/mind-lib/releases
