# worm-ai - Agent Notes

© 3MH Technologies — https://3mh.pages.dev/ — https://t.me/j49_c

## Layout

- `apps/web`  - Next.js 15 + React 19 frontend
- `apps/api`  - FastAPI backend (Python 3.13)
- `packages/shared` - Cross-app types/utilities (TS, optional)
- `infra/docker` - Dockerfiles, docker-compose, Nginx
- `infra/ci` - CI templates
- `.github/workflows` - GitHub Actions
- `scripts` - One-off scripts (seed etc.)
- `docs` - Architecture / runbooks

## Commands

| Task            | Command                            |
|-----------------|------------------------------------|
| Dev (both)      | `npm run dev`                      |
| Dev API only    | `npm run dev:api`                  |
| Dev Web only    | `npm run dev:web`                  |
| Typecheck       | `npm run typecheck`                |
| Lint            | `npm run lint`                     |
| Seed            | `npm run seed`                     |
| Docker up       | `npm run docker:up`                |

## Conventions

- Frontend: TypeScript strict, App Router, route groups in parens.
- Backend: Python 3.13, type hints everywhere, async-first, Pydantic v2.
- All env via `.env` (root) or service-local `.env`. Never commit secrets.
- **Chat mode is NoTrack-only**: all chat completions flow through `app/services/notrack.py`
  (`POST /api/dispatch` + SSE, cookie auth via `NOTRACK_COOKIE`). Model codes A/B/C/F are
  served statically from `GET /api/v1/models`. There is no provider/key management anymore.
- **Worm Agent mode** (`/agent`) is a coding agent on the 3MH Technologies DeepSeek proxy:
  client in `app/services/deepseek.py` (OpenAI-compatible `/v1/chat/completions` with tools),
  tool loop in `app/api/v1/agent.py`. Requires `DEEPSEEK_TOKEN`; model list at
  `GET /api/v1/agent/models`, health at `GET /api/v1/agent/status`.
- Agent workspace files are canvases with an `agentPath` field (scoped to owner +
  conversation) and are versioned in `canvas_versions`.
- Conversations carry `mode: "chat" | "agent"`; `/c/*` and `/agent/*` cross-redirect on mismatch.
- **Branding rule:** user-facing copy must say **"internal models"** — never vendor names
  (NoTrack, DeepSeek, Groq, …) and never "WormGPT". Display names: Worm Core / Worm Pro /
  Worm Flash / Worm Synth (chat) and Worm Agent / Worm Agent R1 (agent). Site name: **worm-ai**.
- **Credits (required):** © 3MH Technologies — https://3mh.pages.dev/ — https://t.me/j49_c
- System prompts: never serialized to non-admin users.

## Verification hooks

- Backend: `python -c "import apps.api.app.main"` should not fail at import (after `pip install`).
- Frontend: `npm run typecheck` from repo root should exit 0.
