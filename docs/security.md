# Security Model

## Threat model

| Threat                                       | Mitigation                                                                       |
|----------------------------------------------|----------------------------------------------------------------------------------|
| Credential stuffing / brute force             | bcrypt + account lockout after 8 failures (15 min)                                |
| Session hijack                                | Short access TTL (30 min) + refresh rotation + device fingerprint + revoke UI    |
| CSRF                                          | Double-submit cookie pattern; `CSRFMiddleware` blocks unsafe w/o header         |
| XSS via rich text                             | `rehype-sanitize` on all markdown + safe Prism highlighter + KaTeX              |
| Secret exfiltration to browser                | No provider keys stored at all; model catalogue responses carry no secrets       |
| System prompt leakage                         | Admin-only endpoints; `SystemPromptOut` field names strip content for non-admins|
| SSRF via web search                           | Only outbound GET to `http(s)` URLs; HTML cleaned, no JS executed                |
| Rate limit abuse                              | Redis fixed-window per (user\|IP) on all sensitive endpoints                    |
| Mass assignment                               | Strict Pydantic models; `exclude_none` on updates; `extra=ignore` config       |
| Mongo injection                               | BSON ObjectId validation; no raw `$where`/`$function`                           |
| Log injection                                 | Structured `structlog` JSON, request ID propagated, secrets redacted in logger  |
| TLS downgrade                                 | Nginx forces HSTS, TLS 1.2+ ciphers, HTTP → HTTPS redirect                      |
| Clickjacking                                  | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'`                          |
| Open redirect                                 | Login redirects stay on same origin via Next.js route guards                    |
| Memory poisoning                              | Memory items stored per-user; only owners can list/delete; admins audit access  |
| Prompt injection                              | System prompt assembled server-side from admin-curated content + user memory; user message never injected into the system block; agent tool calls are server-side only with an owner+conversation-scoped workspace |

## Encryption at rest

- **No provider API keys** are stored — the model catalogue is internal and credential-less (`hasApiKey` is always `false`); the Fernet helpers in `core/crypto.py` remain available for future secrets.
- **System prompts** stored in plaintext (they are not secrets) but **never sent** to non-admin clients.
- **Refresh tokens** stored hashed (sha256) so DB leak does not enable session replay.

## Transport

- TLS terminated at Nginx; backend listens plain HTTP behind the proxy.
- Cookies: `Secure` (production), `HttpOnly` (refresh), `SameSite=Lax` by default.
- Security headers: CSP, HSTS (1y, includeSubDomains), X-Content-Type-Options=nosniff, X-Frame-Options=DENY, Referrer-Policy=strict-origin-when-cross-origin, Permissions-Policy.

## Logging

- `structlog` JSON to stdout.
- `x-request-id` propagated from client or generated, returned in response.
- Timing header `x-response-time-ms`.
- `audit_logs` collection is append-only from the application's perspective; only superadmin can soft-archive (out of scope for v1).

## Rate limiting

- Fixed-window per (user id, IP fallback), configurable via `RATE_LIMIT_PER_MIN`.
- Default 120/min.
- Returns `429` with `Retry-After`.

## Future hardening (out of scope for v1)

- Argon2id migration path (config flag).
- WebAuthn / passkeys.
- mTLS for admin endpoints.
- Per-IP WAF rules.
- Vector-based prompt-injection classifier on user inputs.
