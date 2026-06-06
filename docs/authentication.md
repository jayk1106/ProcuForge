# Authentication

Single-user admin authentication for the ProcuForge admin panel.

For production deployment (Vercel + Cloud Run, CORS, secrets), see [production_setup_guide.md](./production_setup_guide.md).

## What it protects

- **All HTTP endpoints under `/api/v1/*`** — `products`, `workflow`, `vendor-threads`, `test`, plus `auth/me` and `auth/ws-ticket`.
- **Both WebSocket endpoints** — `/ws/workflow/{workflow_id}` and `/ws/vendor-threads/{rfq_id}`.

Left intentionally public:

- `/health`, `/health/live`, `/health/ready` — load-balancer / Kubernetes probes.
- `POST /api/v1/auth/login` — must be reachable without a session, obviously.

## How it works

```
┌──────────── Next.js (app.example.com) ────────────┐
│ AuthGate: GET /auth/me → redirect if unauthenticated │
│ /login → POST /api/v1/auth/login                  │
│ api-client: credentials: 'include' (always)       │
│ useWorkflowSocket: POST /auth/ws-ticket → WS?ticket=
└───────────────────────────────────────────────────┘
                       │  cookie: pf_session=<JWT>
                       ▼
┌──────────── FastAPI (api.example.com) ────────────┐
│ /auth/login        → set HttpOnly cookie          │
│ /auth/logout       → clear cookie                 │
│ /auth/me           → current admin                │
│ /auth/ws-ticket    → 60s JWT for WS handshake     │
│ Depends(get_current_admin) gates every API route  │
│ WS handlers: verify ticket before manager.connect │
└───────────────────────────────────────────────────┘
```

In production the frontend (Vercel) and API (Cloud Run) are on **different domains**. The session cookie is stored for the API domain. `AuthGate` verifies auth via `GET /auth/me` instead of checking cookie presence on the Vercel domain. See [production_setup_guide.md#authentication-in-production](./production_setup_guide.md#authentication-in-production).

Two JWT flavours are issued, both signed with `JWT_SECRET` (HS256):

| Token         | TTL                 | Carries                          | Used for                                       |
| ------------- | ------------------- | -------------------------------- | ---------------------------------------------- |
| **session**   | `JWT_EXPIRATION_SECONDS` (default 7 days) | `sub`, `org`, `typ="session"`    | HTTP API auth, delivered as `pf_session` cookie |
| **ws_ticket** | `JWT_WS_TICKET_TTL_SECONDS` (default 60 s) | `sub`, `org`, `typ="ws_ticket"`  | Single WebSocket handshake (`?ticket=...`)     |

The session cookie is `HttpOnly; Secure; SameSite=None; Path=/` so it survives cross-origin requests in both development (browsers grant `Secure` an exemption on `localhost`) and production.

`AuthGate` calls `GET /auth/me` to gate protected routes — real JWT verification happens in FastAPI on every request. A forged or expired session fails the next API/WS call and the user is redirected to `/login`.

## Setup

### 1. Install backend deps

```bash
uv sync
```

This pulls in `bcrypt` and `PyJWT` from `pyproject.toml`.

### 2. Generate the admin password hash and JWT secret

Use the helper script:

```bash
# Interactive (recommended) — prompts for the password twice, hidden input
uv run python scripts/generate_auth_secrets.py

# Non-interactive (handy for one-off scripts, NOT for shell history)
uv run python scripts/generate_auth_secrets.py --password 'your-password'

# Generate only one of the two
uv run python scripts/generate_auth_secrets.py --hash-only --password '...'
uv run python scripts/generate_auth_secrets.py --secret-only
```

Output looks like:

```
# Copy these into your backend .env (root or api/.env):
ADMIN_PASSWORD_HASH='$2b$12$YJSrlk8ru/IQhWbvbTi5VOxmtm0kGZgKZsld/a8q0N2qwkIfSE9Qm'
JWT_SECRET='9n9mpCxpkbFoaSges9lqvxW74oAes5Lv71lFBIGjSQp6fKtWKEi0GEP/W5uOb1yuxysclGs4fld4nSpCERRGXQ=='
```

Both values are quoted single-quotes because the bcrypt hash contains `$` characters and the JWT secret may contain `/` and `+`.

### 3. Backend env

Add to the root `.env` (or `api/.env`):

```bash
# --- admin auth ---
ADMIN_USER_ID=admin
ADMIN_ORG_ID=acme
ADMIN_PASSWORD_HASH='<paste from script>'
JWT_SECRET='<paste from script>'

# Optional tuning (defaults shown):
# JWT_ALGORITHM=HS256
# JWT_EXPIRATION_SECONDS=604800       # 7 days
# JWT_WS_TICKET_TTL_SECONDS=60        # 1 minute
# SESSION_COOKIE_NAME=pf_session

# --- CORS ---
# Optional in dev (defaults to http://localhost:3000). REQUIRED in prod.
# MUST be an explicit origin (not "*") because the auth cookie requires
# allow_credentials=True. Wildcard fails startup in non-dev envs.
# API_CORS_ORIGINS=http://localhost:3000
# API_CORS_ORIGINS=http://localhost:3000,https://admin.example.com   # multiple
```

### 4. Frontend env

`web/.env.local` only needs the API base URL:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

No secrets ever live in the frontend — the JWT secret never leaves the server.

### 5. Boot

```bash
# Terminal 1 — backend
uv run uvicorn api.main:app --reload --port 8000

# Terminal 2 — frontend
cd web && npm run dev
```

Visit <http://localhost:3000>. You should be redirected to `/login` with a `?next=/flows` query param. Enter the password → you land back on `/flows`.

## Changing the password

1. Re-run `uv run python scripts/generate_auth_secrets.py --hash-only`.
2. Replace `ADMIN_PASSWORD_HASH` in your backend `.env`.
3. Restart the API server.

Existing sessions remain valid until they expire because the JWT secret didn't change. To **invalidate all existing sessions** (e.g. after a suspected leak), rotate `JWT_SECRET` instead — everyone is forced to log in again.

## Sanity checks

```bash
# Public route — works without a cookie:
curl -i http://localhost:8000/health

# Protected route — 401 without a cookie:
curl -i http://localhost:8000/api/v1/workflow/list
# → HTTP/1.1 401 Unauthorized
# → {"detail":"not_authenticated"}

# Log in, persist the cookie, retry:
curl -i -c /tmp/cookie.txt \
  -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"password":"YOUR_PASSWORD"}'

curl -i -b /tmp/cookie.txt http://localhost:8000/api/v1/workflow/list
# → 200

# Bad cookie:
curl -i -b 'pf_session=garbage' http://localhost:8000/api/v1/workflow/list
# → 401 invalid_session

# WebSocket without ticket — closes with code 4401 immediately:
# (use a tool like websocat)
websocat ws://localhost:8000/ws/workflow/some-id
```

## Troubleshooting

**Login request shows "CORS error" / "Failed to fetch" in DevTools.**
The browser blocked a credentialed request because the server didn't set `Access-Control-Allow-Credentials: true` (which happens whenever `API_CORS_ORIGINS` is `*`). Check the backend startup log for `cors.configured origins=… allow_credentials=…` — if `allow_credentials=False`, fix `API_CORS_ORIGINS` to a concrete origin (e.g. `http://localhost:3000`) and restart. The default in dev is now `http://localhost:3000`; you only need to set this if your frontend runs elsewhere.

**Login succeeds but the next API call gets 401.**
The cookie isn't being sent. Three usual suspects:

1. `API_CORS_ORIGINS` is `*` in a non-dev env (rejected at startup) **or** the origin you actually serve the frontend from isn't listed.
2. The frontend fetch is missing `credentials: 'include'`. All API calls flow through `web/src/lib/api-client.ts:apiFetch`, which already sets this — don't bypass it.
3. The cookie path or domain doesn't match. The cookie is `Path=/`, no `Domain`, so the browser binds it to the API host exactly. Make sure the frontend calls the same hostname (not e.g. `localhost` vs `127.0.0.1` — those are different cookie jars).

**Browser console: `cookie ... has been rejected because it has the Secure attribute but is not from a secure context`.**
You're on plain HTTP and not on `localhost`. Either:
- Use `localhost` (not your LAN IP) in dev — `Secure` is exempt there.
- Or put the API behind TLS.

**The WebSocket reconnects in a loop after logout.**
Should not happen — the hook treats close codes `4401`/`4403` as terminal and redirects to `/login`. If it does, check that the FastAPI close call is reaching `ws.accept()` before `ws.close(code=4401)` — without `accept()` the browser sees a generic upgrade failure (`code=1006`) and the hook treats it as a transient error.

**`auth_not_configured` (503) from `/auth/login`.**
The server started but `JWT_SECRET` or `ADMIN_PASSWORD_HASH` is empty. In `API_ENV=development` this is allowed at startup (so dev boots painlessly) but `/auth/login` still refuses to issue tokens. Set the env vars and restart.

**Lifespan refuses to start in non-dev: `Missing required env vars`.**
`api/main.py` enforces `ADMIN_PASSWORD_HASH` and `JWT_SECRET` (plus the existing `WORKFLOW_DEFAULT_*` pair) whenever `API_ENV != "development"`. Set them or set `API_ENV=development` if you're knowingly running an unauthenticated dev box.

## API reference

| Method | Path                        | Auth      | Body                | Returns                            |
| ------ | --------------------------- | --------- | ------------------- | ---------------------------------- |
| POST   | `/api/v1/auth/login`        | none      | `{ password }`      | `{ user_id, org_id }` + cookie     |
| POST   | `/api/v1/auth/logout`       | none      | —                   | `204`, cookie cleared              |
| GET    | `/api/v1/auth/me`           | cookie    | —                   | `{ user_id, org_id }`              |
| POST   | `/api/v1/auth/ws-ticket`    | cookie    | —                   | `{ ticket, expires_in }`           |

WebSocket auth: append `?ticket=<jwt>` to the URL. Close codes used by the server:

| Code | Meaning              |
| ---- | -------------------- |
| 4401 | unauthorized (missing or invalid ticket) |
| 4403 | reserved for future use (e.g. revoked principal) |

## Files

```
api/
├── config.py                       # ADMIN_*, JWT_*, SESSION_COOKIE_NAME
├── dependencies.py                 # get_current_admin, CurrentAdminDep
├── main.py                         # auth router registration + CORS guard
├── routers/auth.py                 # /login /logout /me /ws-ticket
├── routers/{products,workflow,vendor_threads,test}.py  # gated
├── routers/ws.py                   # ticket-gated WS handshake
├── schemas/auth.py                 # LoginRequest, AdminPrincipal, …
└── services/auth_service.py        # bcrypt verify + JWT encode/decode

web/src/
├── components/auth/AuthGate.tsx      # client-side auth gate (production cross-origin)
├── app/login/page.tsx              # login form
├── components/layout/{ClientShell,TopNav}.tsx  # chrome skip on /login, logout button
├── hooks/{useAuth,useWorkflowSocket}.ts        # user state + ws ticket flow
├── lib/api-client.ts               # credentials: 'include', UnauthorizedError, helpers
└── types/auth.ts                   # LoginPayload, MeResponse, …

scripts/generate_auth_secrets.py    # bcrypt hash + JWT secret generator
```

## Out of scope (and what would be needed if you ever go there)

- **Multi-user / RBAC.** Would need a real user store and a `users` collection; the JWT `sub` would become a user id rather than the env-static `ADMIN_USER_ID`.
- **Password reset / "remember me" / TOTP.** Single-user admin is too small a surface area to justify any of these; rotate `JWT_SECRET` to log everyone out and re-run the hash script to change the password.
- **CSRF tokens.** All mutating endpoints accept JSON only (`Content-Type: application/json`), and `SameSite=None` is paired with a same-site front-end origin that's the only thing the cookie travels with, so the standard CSRF preconditions don't apply. Revisit if you ever accept `application/x-www-form-urlencoded` or `multipart/form-data` on a mutating endpoint.
- **Audit log persistence.** Login attempts, ws-ticket issuance, and session decodes log to stdout in the existing format (`auth.login.success`, `auth.login.failure`, `auth.token.invalid`, `auth.ws_ticket.issued`). Pipe these to your log sink of choice.
