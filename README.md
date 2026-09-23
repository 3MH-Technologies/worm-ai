---
title: worm-ai
emoji: 🧠
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# worm-ai

> Production-grade AI chat platform. Streaming chat, multi-source research, collaborative canvases, Worm Agent coding mode, admin approval workflow, and a polished ChatGPT-style UI.

- **Frontend:** Next.js 15, React 19, TypeScript, TailwindCSS, ShadCN primitives, Framer Motion, Zustand, React Query.
- **Backend:** FastAPI, Python 3.13, async-first, Pydantic v2.
- **Storage:** MongoDB Atlas (with Realm interpreted as Atlas App Services — see *Architecture notes* below).
- **Cache:** Redis.
- **AI:** internal models only — chat mode (A/B/C/F) and the Worm Agent coding mode. No provider/key management.
- **Infra:** Docker, Docker Compose, Nginx, Let's Encrypt via certbot, GitHub Actions CI.
- **Credits:** © 3MH Technologies — https://3mh.pages.dev/ — t.me/j49_c

## Layout

```
.
├── apps/
│   ├── web/           Next.js 15 frontend
│   └── api/           FastAPI backend (Python 3.13)
├── packages/
│   └── shared/        (optional) cross-app types
├── infra/
│   ├── docker/        Dockerfiles, docker-compose, Nginx
│   └── ci/            CI templates
├── .github/workflows  GitHub Actions
├── scripts/           One-off scripts (seed etc.)
└── docs/              Architecture / runbooks
```

## Quick start (local)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env: set MONGO_URI, JWT_SECRET, ENCRYPTION_KEY, GROQ_API_KEY
```

Generate secrets:

```bash
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

### 2. Start infrastructure (Mongo + Redis)

Easiest path is the bundled compose stack:

```bash
npm run docker:up
```

This brings up Mongo, Redis, the API, the web app, Nginx, and certbot.

### 3. Run the dev servers (without Docker)

```bash
# Terminal 1: API on :8000
npm run dev:api

# Terminal 2: Web on :3000
npm run dev:web
```

Open http://localhost:3000. The first time, the backend creates a bootstrap superadmin from `BOOTSTRAP_*` in `.env`. Sign in with it and head to the **Admin** area to approve new users.

### 4. Seed sample data (optional)

```bash
npm run seed
# seeds: demo@wormgpt.local / Demo123!  +  "worm-ai Default" system prompt
```

## Default ports

| Service        | Port |
|----------------|------|
| Web (Next.js)  | 3000 |
| API (FastAPI)  | 8000 |
| Mongo          | 27017 |
| Redis          | 6379 |
| Nginx          | 80 / 443 |

## LLM backends (no provider management)

There are two engines, both configured via env — no API-key UI, no provider CRUD:

### 1. Chat mode (default) — internal models

All chat completions flow through the internal dispatch endpoint via `apps/api/app/services/notrack.py`
(`POST /api/dispatch` + SSE). The four internal models (A, B, C default, F) are served
statically from `GET /api/v1/models` as **Worm Core / Worm Pro / Worm Flash / Worm Synth** —
no vendor branding is exposed anywhere in the UI.

| Env | Purpose |
|-----|---------|
| `NOTRACK_BASE` | Service URL (default `https://notrack.ai`) |
| `NOTRACK_COOKIE` | Optional browser-style cookie string for higher limits |
| `NOTRACK_MODEL` | Default model code `A`/`B`/`C`/`F` |
| `NOTRACK_PERSONA` | `normal`, `creative`, `precise`, `concise`, `socratic`, `tutor`, `coder` |
| `NOTRACK_MAX_TURNS` | Agent turns per dispatch (default 6) |

### 2. Worm Agent mode — coding agent (internal models, by 3MH Technologies)

`/agent` runs an autonomous tool loop through the internal API proxy
(`apps/api/app/services/deepseek.py`, OpenAI-compatible `/v1/chat/completions` with tools).
Credits: https://3mh.pages.dev/ | https://t.me/j49_c

| Env | Purpose |
|-----|---------|
| `DEEPSEEK_PROXY_BASE` | Proxy URL (default the 3MH worker) |
| `DEEPSEEK_TOKEN` | **Required** — DeepSeek token from chat.deepseek.com |
| `DEEPSEEK_MODEL` | `deepseek-chat` (default) or `deepseek-reasoner` |
| `AGENT_MAX_ITERATIONS` | Max tool-loop rounds per run (default 8) |

Tools: `create_file`, `read_file`, `list_files`, `delete_file` (workspace files are stored as
versioned canvases scoped to owner + conversation), `web_search`, `fetch_url`.
Endpoints: `GET /api/v1/agent/models`, `GET /api/v1/agent/status`,
`POST /api/v1/agent/conversations/{id}/stream` (SSE).

## Architecture notes

### "Realm"

The spec mentions "Realm Database / Realm Sync / Realm Authentication". Realm is a mobile-first sync SDK (React Native / iOS / Android) and has no first-party Python sync SDK. We map that to **MongoDB Atlas App Services** (the renamed MongoDB Realm) and use MongoDB Atlas as the primary store. Auth lives in FastAPI with JWT + refresh tokens.

### Security

- Passwords hashed with bcrypt.
- API keys encrypted at rest with Fernet.
- System prompts never sent to non-admin users.
- JWT with refresh tokens, CSRF token on cookies for non-GET requests, CSP headers, rate limiting, account lockout after 8 failed logins, audit log for every privileged action, device fingerprinting.

### Streaming

Chat uses Server-Sent Events. The browser's `fetch` + `ReadableStream` is used (instead of `EventSource`) so we can send the auth header in the request. The server emits `start`, `delta`, `finish`, `error`, and `done` events. The final `done` event contains the assistant message id and timing metadata.

Worm Agent mode streams the same `start`/`delta`/`error`/`done` events plus `thinking`
(DeepSeek reasoning), `tool` (tool started) and `tool_result` (tool finished).

### LLM clients

Chat completions go through `app/services/notrack.py` (chat) and agent runs through
`app/services/deepseek.py`. There is no generic provider abstraction anymore — both
clients are first-class and config-only, exposed to users as **internal models**.

## License

Proprietary. © worm-ai — a 3MH Technologies project.

- https://3mh.pages.dev/
- https://t.me/j49_c
