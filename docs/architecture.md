# worm-ai — Architecture

> © 3MH Technologies — https://3mh.pages.dev/ — https://t.me/j49_c

> **Goal:** a production-grade AI chat platform with strict admin approval,
> internal model backends (chat + Worm Agent coding mode), research + canvas,
> and an original premium UI.

---

## 1. System diagram

```
                    ┌─────────────────────────────────────┐
                    │            Browser / Mobile         │
                    │  Next.js 15 · React 19 · TS · Zstd  │
                    └────────────────┬────────────────────┘
                                     │ HTTPS (TLS 1.2+)
                                     │ fetch + ReadableStream (SSE)
                                     ▼
                    ┌─────────────────────────────────────┐
                    │   Nginx (reverse proxy + TLS term)  │
                    │   CSP, HSTS, X-Frame-Options, gzip  │
                    └────────────────┬────────────────────┘
                                     │
                ┌────────────────────┴────────────────────┐
                ▼                                         ▼
   ┌──────────────────────────┐           ┌──────────────────────────┐
   │   FastAPI (apps/api)     │           │  Next.js server (apps/web)│
   │  Pydantic v2 · async     │           │  App Router · Route grps │
   │  Internal dispatch       │           └──────────────┬───────────┘
   │  ├─ chat: notrack (SSE)  │                          │
   │  └─ agent: deepseek      │           (Static / RSC rendering,
   │     (server-side tools)  │            rewrites /api/v1/* to API)
   └────────┬─────────────────┘
            │
   ┌────────┴─────────┐    ┌─────────────────────┐
   ▼                  ▼    ▼                     ▼
┌──────────┐   ┌──────────────┐         ┌──────────────────┐
│ MongoDB  │   │   Redis      │         │  Web search      │
│ Atlas    │   │  rate-limit  │         │  DDG / Serper /  │
│          │   │  token usage │         │  Tavily          │
└──────────┘   └──────────────┘         └──────────────────┘
```

---

## 2. Folder structure

```
.
├── apps/
│   ├── api/                         # FastAPI backend
│   │   ├── app/
│   │   │   ├── main.py              # entrypoint, lifespan, middleware wiring
│   │   │   ├── core/                # cross-cutting (config, security, crypto, middleware, logging)
│   │   │   ├── db/                  # Mongo + Redis connection helpers and indexes
│   │   │   ├── cache/               # Redis-backed rate limiter and counters
│   │   │   ├── models/              # Pydantic v2 request/response schemas
│   │   │   ├── services/            # notrack, deepseek, prompt_guard, audit
│   │   │   └── api/
│   │   │       ├── deps.py          # current_user, role guards, rate limit
│   │   │       ├── router.py        # v1 aggregator
│   │   │       └── v1/              # admin, agent, attachments, auth, canvas,
│   │   │                            # chat, health, memory, models, notifications,
│   │   │                            # password_reset, research, search, security,
│   │   │                            # summarize, system_prompts, web
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── web/                         # Next.js 15 frontend
│       ├── src/
│       │   ├── app/                 # App Router
│       │   │   ├── login/           # public — email + password
│       │   │   ├── register/        # public — sign up
│       │   │   ├── forgot/          # public — password reset
│       │   │   ├── (app)/           # authenticated shell with sidebar + topbar
│       │   │   │   ├── c/[[...id]]  # conversation
│       │   │   │   ├── agent/[[...id]] # Worm Agent coding mode
│       │   │   │   ├── canvas/      # list, new, [id] (with versions)
│       │   │   │   ├── research/
│       │   │   │   ├── search/
│       │   │   │   ├── admin/       # users, prompts, audit, errors
│       │   │   │   ├── settings/
│       │   │   │   ├── profile/
│       │   │   │   ├── security/    # sessions + devices, revoke
│       │   │   │   ├── notifications/
│       │   │   │   └── pending/     # awaiting approval
│       │   │   ├── not-found.tsx
│       │   │   ├── error.tsx
│       │   │   └── loading.tsx
│       │   ├── components/
│       │   │   ├── ui/              # shadcn-style primitives
│       │   │   ├── layout/          # sidebar, topbar
│       │   │   ├── chat/            # composer, message bubble, list
│       │   │   ├── renderers/       # markdown, code, mermaid
│       │   │   └── admin/           # stats cards, recent activity widgets
│       │   ├── lib/                 # api client, utils, hooks
│       │   ├── stores/              # Zustand: auth, ui
│       │   └── types/               # ambient declarations
│       ├── public/
│       ├── package.json
│       ├── tsconfig.json
│       ├── next.config.mjs
│       ├── tailwind.config.ts
│       └── postcss.config.cjs
├── infra/
│   └── docker/                      # Dockerfile.api, Dockerfile.web, docker-compose, nginx/
├── .github/workflows/ci.yml
├── docs/
│   ├── architecture.md              # this file
│   └── security.md                  # threat model + controls
├── .env.example
├── .gitignore
├── AGENTS.md
└── package.json                     # root: workspaces + scripts
```

---

## 3. Data models (MongoDB)

> Document layer with **clean schema boundaries**: each collection has a
> single source of truth (Pydantic model in `apps/api/app/models/`), and
> indexes are declared in `apps/api/app/db/mongo.py`.

| Collection          | Purpose                                       | Key fields                                                                                                              |
|---------------------|-----------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| `users`             | account + role + status + lockout             | `username` (uniq), `email` (uniq), `passwordHash`, `role`, `status`, `failedLoginAttempts`, `lockedUntil`               |
| `password_resets`   | one-time forgot-password tokens               | `userId`, `tokenHash`, `expiresAt`, `usedAt`                                                                            |
| `refresh_tokens`    | rotating refresh tokens                       | `token`, `userId`, `revoked`, `expiresAt`                                                                              |
| `devices`           | device fingerprints for trust/session mgmt    | `userId`, `fingerprint`, `userAgent`, `ip`, `firstSeen`, `lastSeen`, `trusted`, `revokedAt`                            |
| `conversations`     | chat thread metadata                          | `userId`, `title`, `modelId`, `folderId`, `favorite`, `shared`, `lastMessageAt`                                        |
| `messages`          | chat turns                                    | `conversationId`, `userId`, `role`, `content`, `tokens`, `model`, `metadata`, `parentId`, `reaction`, `attachments[]`  |
| `conversation_summaries` | rolling summaries (memory compression)    | `conversationId`, `userId`, `summary`, `uptoMessageId`, `createdAt`                                                     |
| `models`            | legacy registry (catalogue served statically) | `name` (uniq), `provider`, `endpoint`, `temperature`, `maxTokens`, `topP`, `systemPromptId`, `enabled`     |
| `system_prompts`    | versioned prompts (admin-only content)        | `name`, `description`, `currentVersion`, `versions[] {version, content, changelog, createdAt}`                          |
| `folders`           | sidebar folders                               | `userId`, `name`, `color`, `icon`                                                                                      |
| `canvases`          | document/code/research workspaces             | `ownerId`, `title`, `type`, `content`, `metadata`, `currentVersion`                                                     |
| `canvas_versions`   | immutable canvas history                      | `canvasId`, `version`, `content`, `commitMessage`, `authorId`                                                           |
| `memories`          | per-user memory slices                        | `userId`, `kind ∈ {long_term, context, session, preference, summary}`, `content`, `weight`, `source`                   |
| `audit_logs`        | append-only privileged-action log             | `actorId`, `action`, `resource`, `ipAddress`, `userAgent`, `metadata`, `timestamp`                                      |
| `notifications`     | per-user inbox                                | `userId`, `title`, `body`, `kind`, `read`, `createdAt`                                                                  |
| `attachments`       | uploaded files/images metadata                | `userId`, `messageId?`, `conversationId?`, `kind`, `mimeType`, `size`, `storageKey`, `originalName`                    |

### Indexes (declared in `db/mongo.py`)

- `users.email` unique · `users.username` unique · `users.status` · `users.role`
- `conversations.(userId, updatedAt desc)` · `.(userId, folderId)` · `.(userId, favorite)` · text on `title`
- `messages.(conversationId, createdAt)` · text on `content`
- `models.name` unique · `models.provider`
- `system_prompts.(name, currentVersion desc)`
- `audit_logs.(actorId, timestamp desc)` · `audit_logs.action`
- `notifications.(userId, createdAt desc)` · `notifications.(userId, read)`
- `canvases.(ownerId, updatedAt desc)` · `canvases.type`
- `canvas_versions.(canvasId, version desc)` unique
- `memories.(userId, kind)` · text on `content`
- `folders.(userId, name)`
- `refresh_tokens.token` unique · `refresh_tokens.userId`
- `devices.(userId)` · `devices.fingerprint`
- `attachments.(userId, createdAt desc)`
- `conversation_summaries.(conversationId, createdAt desc)` unique

---

## 4. API surface (`/api/v1`)

> All authenticated routes expect `Authorization: Bearer <accessToken>`.
> All write methods require matching CSRF token from cookie.

### Auth & profile
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | public | Create user with `status: pending`, notifies admins |
| POST | `/auth/login` | public | Returns access + refresh; tracks device |
| POST | `/auth/refresh` | public | Rotates access token |
| POST | `/auth/logout` | user | Revokes supplied refresh token |
| POST | `/auth/logout-all` | user | Revokes all refresh tokens for the user |
| GET  | `/auth/me` | user | Current public user |
| PATCH| `/auth/me` | user | Update username/avatar |
| POST | `/auth/change-password` | user | With old password |
| POST | `/auth/forgot-password` | public | Issue one-time reset token (returns token in dev; email in prod) |
| POST | `/auth/reset-password` | public | Consume token, set new password |

### Models
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/models` | user | List the four internal models (static catalogue) |
| GET  | `/models/{id}` | user | Get one (`A`/`B`/`C`/`F`) |

### System prompts
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/system-prompts` | **admin** (full) | List with content |
| GET  | `/system-prompts/summary` | user | Lightweight list (no content) |
| GET  | `/system-prompts/{id}` | **admin** | Full content + versions |
| POST | `/system-prompts` | **admin** | Create v1 |
| PATCH| `/system-prompts/{id}` | **admin** | Append new version |
| DELETE| `/system-prompts/{id}` | **admin** | Delete |
| GET  | `/system-prompts/{id}/versions/{v}` | **admin** | Read historical version |

### Chat
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/chat/conversations` | user | List, supports `q`, `folderId`, `favorite`, `shared` |
| POST | `/chat/conversations` | user | Create |
| GET  | `/chat/conversations/{id}` | user | With messages |
| PATCH| `/chat/conversations/{id}` | user | Rename, favorite, share, folder |
| DELETE| `/chat/conversations/{id}` | user | Delete |
| POST | `/chat/conversations/{id}/stream` | user | **SSE** chat |
| POST | `/chat/conversations/{id}/messages` | user | Non-streaming post |
| PATCH| `/chat/conversations/{id}/messages/{mid}` | user | Edit |
| DELETE| `/chat/conversations/{id}/messages/{mid}` | user | Delete |
| POST | `/chat/conversations/{id}/messages/{mid}/react` | user | Reaction |
| POST | `/chat/conversations/{id}/summarize` | user | Run summarization job → context memory |
| GET  | `/chat/folders` | user | List |
| POST | `/chat/folders` | user | Create |
| DELETE| `/chat/folders/{id}` | user | Delete |

### Memory
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/memory` | user | List own memory slices |
| POST | `/memory` | user | Add |
| DELETE| `/memory/{id}` | user | Delete |

### Canvas
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/canvas` | user | List |
| POST | `/canvas` | user | Create |
| GET  | `/canvas/{id}` | user | Read |
| PATCH| `/canvas/{id}` | user | Edit (creates new version) |
| DELETE| `/canvas/{id}` | user | Delete |
| GET  | `/canvas/{id}/versions` | user | List versions |
| POST | `/canvas/{id}/restore/{v}` | user | Restore from version |
| GET  | `/canvas/{id}/diff/{a}/{b}` | user | Unified diff |

### Research
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/research/run` | user | One-shot, returns full report + sources + citations |
| POST | `/research/stream` | user | **SSE** with sources → deltas → done |

### Web search
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/web/search` | user | Returns ranked results, optional content fetch |
| GET  | `/web/fetch?url=` | user | Sanitised fetch |

### Search
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/search?q=&kinds=` | user | Cross-collection full-text |

### Notifications
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/notifications` | user | List |
| POST | `/notifications/{id}/read` | user | Mark read |
| POST | `/notifications/read-all` | user | Mark all |
| DELETE| `/notifications/{id}` | user | Delete |

### Security / sessions
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/security/sessions` | user | List active sessions/devices |
| POST | `/security/sessions/{id}/revoke` | user | Revoke a session/device |
| POST | `/security/sessions/revoke-others` | user | Revoke every other session |
| POST | `/security/sessions/cleanup` | user | Purge expired/revoked rows |

### Attachments
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/attachments` | user | Multipart upload (≤ 20 MB) |
| GET  | `/attachments/{id}` | user | Stream (auth-checked) |
| DELETE| `/attachments/{id}` | user | Delete own attachment |

### Worm Agent
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/agent/models` | user | List agent model aliases |
| GET  | `/agent/status` | user | Proxy health + token presence |
| POST | `/agent/conversations/{cid}/stream` | user | **SSE** agent tool loop (files, web_search, fetch_url) |

### Admin
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/admin/stats` | admin | Aggregates + recent activity |
| GET  | `/admin/users` | admin | List + filter + paginate |
| PATCH| `/admin/users/{id}` | admin | Role/status |
| POST | `/admin/users/{id}/approve` | admin | |
| POST | `/admin/users/{id}/reject` | admin | |
| DELETE| `/admin/users/{id}` | admin | |
| GET  | `/admin/audit-logs` | admin | Filtered audit feed |
| GET  | `/admin/errors` | admin | Recent server errors |

### Health
| Method | Path | Auth | Description |
|---|---|---|---|
| GET  | `/health` | public | Liveness |
| GET  | `/health/ready` | public | Mongo + Redis ping |

---

## 5. Frontend route map

| Route                    | Layout               | Purpose                                                                                  |
|--------------------------|----------------------|------------------------------------------------------------------------------------------|
| `/`                      | public               | Landing (CTA, features) → redirects to `/c` when authenticated                            |
| `/login`                 | public               | Email + password sign-in                                                                 |
| `/register`              | public               | Sign up; on success → "pending approval" card                                            |
| `/forgot`                | public               | Password reset request                                                                    |
| `/pending`               | auth-gated           | Shown when `user.status != approved`; CTA to re-check or sign out                        |
| `/c`                     | app shell            | Empty chat with composer; "How can I help today?"                                         |
| `/c/[...id]`             | app shell            | Conversation view with sidebar, top bar, streaming messages                              |
| `/agent`                 | app shell            | Worm Agent coding mode — workspace files + tool events (`/agent/[...id]` reopens one)     |
| `/canvas`                | app shell            | List of user's canvases                                                                  |
| `/canvas/new`            | app shell            | Type picker + title                                                                      |
| `/canvas/[id]`           | app shell            | Edit / split / preview; version history sidebar; restore; diff; autosave                 |
| `/research`              | app shell            | Query input → SSE report + sources; save to canvas                                       |
| `/search`                | app shell            | Debounced full-text search across collections                                             |
| `/notifications`         | app shell            | Inbox with read/unread + mark all                                                         |
| `/settings`              | app shell            | Profile, password, memory, sessions shortcut                                              |
| `/profile`               | app shell            | Display name, avatar, bio                                                                |
| `/security`              | app shell            | Active sessions/devices + revoke + change password                                        |
| `/admin`                 | app shell (admin)    | Stats cards + recent activity widgets                                                     |
| `/admin/users`           | app shell (admin)    | User table, role/status actions                                                          |
| `/admin/audit`           | app shell (admin)    | Audit log feed                                                                           |
| `/admin/errors`          | app shell (admin)    | Recent server errors                                                                     |
| `/admin/prompts`         | app shell (admin)    | System prompt manager with versioning                                                     |
| `/_not-found`            | global               | Custom 404                                                                               |
| `/loading` / `error`     | global               | Suspense + error boundaries                                                              |

### Cross-cutting UI
- **Sidebar** (`components/layout/sidebar.tsx`): new chat, debounced search, favorites/shared/all tabs, folder tree, agent mode entry, admin entries (gated).
- **Top bar** (`components/layout/topbar.tsx`): model selector, workspace selector, notifications popover, theme switcher, profile menu.
- **Chat composer** (`components/chat/composer.tsx`): textarea with auto-grow, Web/Canvas toggles, token-aware status, file picker, send/stop, regenerate shortcut.
- **Message bubble** (`components/chat/message.tsx`): copy, edit, delete, regenerate, reaction bar, latency/tokens metadata.
- **Markdown renderer** (`components/renderers/markdown.tsx`): GFM tables, KaTeX math, syntax-highlighted code (Prism), Mermaid diagrams, sanitised HTML.

---

## 6. Streaming transport

`POST /api/v1/chat/conversations/{id}/stream` returns `text/event-stream`:

```
event: start
data: {"userMessageId":"...","model":"Worm Core","provider":"internal"}

event: delta
data: {"text":"Hello"}

event: delta
data: {"text":" there"}

event: finish
data: {"reason":"stop"}

event: done
data: {"assistantMessageId":"...","tokens":18,"latency_ms":412,"ttft_ms":118}
```

The client uses `fetch` + `ReadableStream` (not `EventSource`) so the bearer
header is sent. Errors emit a single `event: error` and the connection closes.

---

## 7. Security model

See `docs/security.md` for the full threat model. Highlights:

- Bcrypt password hashing.
- No provider API keys stored (internal, credential-less models); Fernet helpers remain in `core/crypto.py` for future secrets.
- JWT access (15-30 min) + refresh (14 d) with rotation + revocation table.
- CSRF double-submit on unsafe methods.
- CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.
- Rate limit (60-120/min by user/IP) in Redis.
- Account lockout after 8 failed logins (15 min cool-down).
- Device fingerprint on login; user can revoke per device.
- Audit log entry on every privileged action.
- System prompts **never** serialised to non-admin users (enforced at the route level).
- Markdown sanitised via `rehype-sanitize` before render.
- Strict input validation via Pydantic v2; no string concatenation into prompts except for system-prompt assembly which is admin-gated and stored separately.

---

## 8. Performance budget

- First contentful paint < 1.5 s on a warm cache; full chat shell < 2 s.
- First-token latency (internal dispatch) median < 300 ms; p95 < 700 ms.
- All chat reads paginate; history capped at 400 messages before summarization is triggered.
- MongoDB indexes cover all hot read paths; full-text search uses Mongo's `$text`.
- Redis-backed sliding window for rate limit + daily token counters.
- Mermaid + KaTeX lazy-loaded; syntax highlighter uses a small language set.
