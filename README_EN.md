# Mind Library - Distributed Collective Intelligence System

## Features
- Admin SPA Dashboard (v2.1.1)
- Distributed Cluster with consistent hashing (v2.1)
- API Key Auth with instance approval (v2.0)
- Lightweight - runs on 50MB memory

## Quick Start
```bash
pip install flask werkzeug requests
export MIND_ADMIN_API_KEY=your_key
python mind_server_v2.1.1.py
```
Server at http://localhost:5000

## API Endpoints
- GET /api/health - Health check
- GET /api/stats - Statistics
- GET /api/download/thoughts - Download thoughts
- GET /api/download/skills - Download skills
- POST /api/upload/thought - Upload thought
- GET /api/admin/dashboard - Admin dashboard (requires X-API-Key)
- POST /api/admin/approve_instance - Approve instance
- POST /api/admin/revoke_instance - Revoke instance
- POST /api/admin/add_client_key - Add client key

## Version History
| Version | Description |
|---------|-------------|
| v2.1.1 | Admin SPA Dashboard + Security fixes |
| v2.1 | Distributed cluster + multi-replica |
| v2.0 | API Key auth + instance approval |
| v1.0 | Initial release |

For full documentation, see README.md (中文)

MIT License - see LICENSE
