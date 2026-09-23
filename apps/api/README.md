# worm-ai API

FastAPI service for the worm-ai platform. © 3MH Technologies — https://3mh.pages.dev — t.me/j49_c

## Quick start

```bash
# 1. Create a virtualenv
python -m venv .venv
. .venv/bin/activate            # Linux / macOS
# .venv\Scripts\activate         # Windows PowerShell

# 2. Install
pip install -e ".[dev]"

# 3. Configure
cp ../../.env.example ../../.env
# edit ../../.env

# 4. Run
uvicorn app.main:app --reload --port 8000
```

## Endpoints

- `GET  /api/v1/health`               liveness
- `GET  /api/v1/health/ready`         mongo + redis check
- `POST /api/v1/auth/register`        sign up (status = pending)
- `POST /api/v1/auth/login`           returns access + refresh
- `POST /api/v1/auth/refresh`         rotate access token
- `GET  /api/v1/auth/me`              current user
- `GET  /api/v1/models`               list enabled models
- `POST /api/v1/models`               (admin) create model
- `PATCH /api/v1/models/{id}`         (admin) update model
- `POST /api/v1/models/{id}/test`     ping the model
- `GET  /api/v1/system-prompts/summary`  lightweight list (no content)
- `GET  /api/v1/system-prompts`       (admin) full content
- `POST /api/v1/system-prompts`       (admin) create with content
- `GET  /api/v1/chat/conversations`   list
- `POST /api/v1/chat/conversations`   create
- `POST /api/v1/chat/conversations/{id}/stream`  SSE chat
- `GET  /api/v1/chat/conversations/{id}`         with messages
- `PATCH /api/v1/chat/conversations/{id}/messages/{mid}`  edit
- `POST /api/v1/chat/conversations/{id}/messages/{mid}/react`
- `GET  /api/v1/chat/folders`         / POST /api/v1/chat/folders
- `GET  /api/v1/memory`               / POST /api/v1/memory
- `GET  /api/v1/notifications`        mark read
- `GET  /api/v1/search?q=...&kinds=conversation,message,model,canvas,memory,user`
- `GET  /api/v1/canvas`               / POST /api/v1/canvas
- `GET  /api/v1/canvas/{id}/versions`
- `POST /api/v1/canvas/{id}/restore/{v}`
- `POST /api/v1/research/run`         one-shot research
- `POST /api/v1/research/stream`      streaming research (SSE)
- `POST /api/v1/web/search`           web search
- `GET  /api/v1/web/fetch?url=...`    fetch + extract
- `GET  /api/v1/admin/stats`          (admin)
- `GET  /api/v1/admin/users`          (admin)
- `POST /api/v1/admin/users/{id}/approve|reject`
- `GET  /api/v1/admin/audit-logs`     (admin)
- `GET  /api/v1/developer/models`     (admin) all models
- `POST /api/v1/developer/models/{id}/reveal`  (superadmin)

OpenAPI docs at `http://localhost:8000/api/docs`.
