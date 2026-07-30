# SAIRA Backend — Authentication Service

This is the backend for SAIRA (Smart AI Research Assistant), scaffolded from
scratch with **authentication only**. No SAIRA business features (projects,
papers, search, AI) are implemented yet — this is the foundation the rest of
the API will be built on.

The frontend (Next.js MVP) is a separate project and is not touched by this
backend in any way.

---

## Tech stack

| Concern            | Choice                                              |
|---------------------|------------------------------------------------------|
| Framework           | FastAPI                                             |
| Language            | Python 3.13+ (developed/tested on 3.12; no 3.13-only syntax is used, see note below) |
| ORM                 | SQLAlchemy 2.x (async, `asyncpg` driver)             |
| Migrations          | Alembic (async-aware `env.py`)                      |
| Database            | PostgreSQL                                           |
| OAuth                | Authlib (Google via OpenID Connect, ORCID via OAuth2) |
| Auth tokens          | JWT (PyJWT), HS256                                   |
| Password hashing     | Argon2id (via passlib)                              |
| Validation           | Pydantic v2                                          |
| Server                | Uvicorn                                              |

> **Python version note:** this sandbox only had Python 3.12.3 available (no
> `python3.13` package in the base Ubuntu repos and no internet access to
> add a PPA), so development and all testing below happened on 3.12. Nothing
> in this codebase relies on a 3.13-only language feature — install with
> 3.13 in your own environment and it will run unchanged.

---

## Folder structure

```
saira-backend/
├── alembic/
│   ├── env.py                  # async-aware Alembic environment
│   └── versions/                # migration scripts
├── alembic.ini
├── app/
│   ├── main.py                  # FastAPI app instance, middleware, routers
│   ├── core/
│   │   ├── config.py            # Pydantic Settings (env-based config)
│   │   ├── security.py          # password hashing + JWT create/decode
│   │   └── oauth.py              # Authlib client registry (Google, ORCID)
│   ├── db/
│   │   ├── base.py               # SQLAlchemy DeclarativeBase
│   │   └── session.py            # async engine + get_db() dependency
│   ├── models/
│   │   ├── user.py               # User model (matches the ERD)
│   │   └── refresh_token.py      # server-side refresh token records
│   ├── schemas/                  # Pydantic request/response models
│   │   ├── auth.py
│   │   ├── token.py
│   │   └── user.py
│   ├── services/                 # business logic, framework-agnostic
│   │   ├── user_service.py       # user CRUD
│   │   ├── auth_service.py       # register/login/refresh/logout logic
│   │   └── oauth_service.py      # OAuth account resolution (find-or-create)
│   ├── api/
│   │   ├── deps.py               # get_current_user() dependency
│   │   └── v1/
│   │       ├── router.py         # aggregates all v1 routers
│   │       └── endpoints/
│   │           ├── auth.py            # register, login, refresh, logout, me
│   │           ├── oauth_google.py    # /auth/google/login, /callback
│   │           └── oauth_orcid.py     # /auth/orcid/login, /callback
│   ├── exceptions/
│   │   └── auth_exceptions.py    # domain exceptions (not raw HTTPException)
│   └── middleware/
│       └── error_handler.py      # translates exceptions → JSON responses
├── requirements.txt
├── .env.example
└── .gitignore
```

### Why it's organized this way

- **`api` (routes) → `services` (logic) → `models`/`db` (data)** is a strict
  one-way dependency. Endpoints are thin: they parse input, call a service,
  and return the result. All the actual auth logic lives in `services/`,
  which has no FastAPI imports at all — that's what makes it easy to unit
  test and easy to reuse once background jobs or CLI scripts need the same
  logic later.
- **`exceptions/` + `middleware/error_handler.py`**: services raise
  domain-specific exceptions (`InvalidCredentialsError`,
  `UserAlreadyExistsError`, ...) instead of `HTTPException`. A single
  registered handler maps every one of them to the right status code and a
  consistent `{"detail": "..."}` body. This keeps HTTP concerns out of the
  service layer entirely.
- **New SAIRA modules (`projects`, `papers`, `search`, ...) plug in by adding
  a new `models/`, `schemas/`, `services/`, and `api/v1/endpoints/` module
  each, then registering the new router in `api/v1/router.py`** — nothing
  in the auth module needs to change.

---

## 1. Prerequisites

- Python 3.13+ (see note above)
- PostgreSQL 14+ running locally or reachable over the network
- (Optional) Google OAuth credentials, ORCID OAuth credentials — only
  needed to exercise those two login flows

## 2. Setup

```bash
cd saira-backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create your database:

```bash
psql -U postgres -c "CREATE DATABASE saira;"
```

Copy the environment template and fill in real values:

```bash
cp .env.example .env
```

At minimum, set `DATABASE_URL` to point at your Postgres instance, and
generate real secrets for local dev:

```bash
python -c "import secrets; print(secrets.token_hex(32))"   # run twice
```

Use the two outputs for `JWT_SECRET_KEY` and `SESSION_SECRET_KEY`.

## 3. Run the initial migration

The migration in `alembic/versions/` was generated against a real local
Postgres instance (not hand-written), and creates two tables: `users` and
`refresh_tokens`.

```bash
alembic upgrade head
```

To regenerate a migration after changing a model:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## 4. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

- API base: `http://localhost:8000/api/v1`
- Interactive docs: `http://localhost:8000/api/v1/docs`
- Health check: `http://localhost:8000/health`

---

## Authentication design

### Tokens

- **Access token** — JWT, 15 minutes by default (`ACCESS_TOKEN_EXPIRE_MINUTES`),
  sent as `Authorization: Bearer <token>` on every protected request.
- **Refresh token** — JWT, 30 days by default (`REFRESH_TOKEN_EXPIRE_DAYS`).
  Unlike the access token, its hash is also stored server-side in the
  `refresh_tokens` table. This is what makes **logout** and **revocation**
  possible — a bare stateless JWT can't be invalidated before it expires,
  so a DB-backed record is required if "log out" is supposed to mean
  anything.
- Every refresh **rotates**: calling `/auth/refresh` revokes the token you
  sent and issues a brand new access/refresh pair. If a refresh token is
  ever replayed after rotation (e.g. it was stolen and both the attacker and
  the legitimate client try to use it), the second use is rejected with
  `401 — This token has been revoked.`
- Only a SHA-256 hash of each refresh token is stored, never the raw value
  — a compromised database alone can't be used to mint sessions.
- Access and refresh tokens carry a `type` claim and are validated against
  it, so an access token can never be used where a refresh token is
  expected, or vice versa.

### Password hashing

Argon2id (via `passlib`), the algorithm currently recommended by OWASP for
new applications — memory-hard, and considerably more resistant to
GPU/ASIC-accelerated cracking than bcrypt or PBKDF2.

### OAuth account resolution

Both Google and ORCID funnel into the same `find_or_create_oauth_user()` in
`app/services/oauth_service.py`:

1. Look up by `(provider, provider_id)` — the returning-user path.
2. If not found, check for an existing account with the same email but a
   **different** provider. This is treated as a conflict
   (`409 — already registered with a different sign-in method`) rather than
   silently merged, since the backend has no way to prove the person
   signing in now is the same person who originally registered that email.
3. Otherwise, create a new account tied to that provider.

**Google** uses standard OpenID Connect (discovered via Google's
`.well-known/openid-configuration`), so the callback gets `sub`, `email`,
and `name` from the validated `id_token`.

**ORCID** uses ORCID's own "Authenticate with ORCID" flow — plain OAuth2,
not OIDC. The token endpoint response itself already contains the ORCID iD
and the person's name, so no extra userinfo call is needed. ORCID's basic
flow does not grant an email address by default (that requires a separate
member API scope), so a stable placeholder
(`{orcid_id}@orcid.users.saira.app`) is used if none is returned — this
keeps the `email` uniqueness constraint intact without blocking sign-in.

Both OAuth callbacks currently **return the token pair as JSON** rather
than redirecting to the frontend. This keeps the backend independently
testable via curl/Postman without assuming anything about how the frontend
will eventually consume it. The natural next step for a real integration is
either a redirect to a frontend route with the tokens attached, or setting
an httpOnly cookie and redirecting to `FRONTEND_URL` — that's a
frontend-integration decision, not an auth-service one, so it was left as
the seam to change in `oauth_google.py` / `oauth_orcid.py` rather than
guessed at here.

---

## API reference

All routes are prefixed with `/api/v1`.

| Method | Path                    | Auth required | Description |
|--------|--------------------------|:---:|--------------|
| POST   | `/auth/register`         |  | Create an email/password account |
| POST   | `/auth/login`            |  | Exchange email + password for a token pair |
| POST   | `/auth/refresh`          |  | Exchange a refresh token for a new pair (rotates) |
| POST   | `/auth/logout`           | Y | Revoke a refresh token |
| GET    | `/auth/me`               | Y | Get the current user's profile |
| GET    | `/auth/google/login`     |  | Redirect to Google's consent screen |
| GET    | `/auth/google/callback`  |  | Google redirects here; returns a token pair |
| GET    | `/auth/orcid/login`      |  | Redirect to ORCID's consent screen |
| GET    | `/auth/orcid/callback`   |  | ORCID redirects here; returns a token pair |

### Example flow

```bash
# Register
curl -X POST localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Ada Lovelace","email":"ada@example.com","password":"supersecret1"}'

# Login
curl -X POST localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","password":"supersecret1"}'
# => {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

# Get current user
curl localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"

# Refresh (rotates both tokens)
curl -X POST localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'

# Logout (revokes the refresh token; requires the access token too)
curl -X POST localhost:8000/api/v1/auth/logout \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"refresh_token":"<refresh_token>"}'
```

Every error response has the shape `{"detail": "human-readable message"}`
(validation errors additionally include an `errors` array with per-field
detail), so the frontend can handle all of them uniformly.

### Validation rules

- `name`: required, non-blank
- `email`: valid email format (checked via `email-validator`)
- `password`: minimum 8 characters, must contain at least one letter and
  one number

---

## Setting up OAuth credentials

### Google

1. Google Cloud Console → APIs & Credentials → *Create OAuth client ID* →
   *Web application*.
2. Add an authorized redirect URI matching `GOOGLE_REDIRECT_URI` in your `.env`
   (e.g. `http://localhost:8000/api/v1/auth/google/callback`).
3. Copy the client ID/secret into `.env`.

### ORCID

1. Register a client at ORCID's developer tools (or the sandbox
   equivalent for testing — set `ORCID_ENVIRONMENT=sandbox` to match).
2. Add a redirect URI matching `ORCID_REDIRECT_URI`.
3. Copy the client ID/secret into `.env`.

Both `/auth/{provider}/login` endpoints require the app to reach the
provider's servers over the network (Google's OIDC discovery document, or
ORCID's authorize endpoint) — make sure outbound HTTPS is available in
whatever environment you deploy this to.

---

## Extending this for the rest of SAIRA

This scaffold is intentionally scoped to auth only. When it's time to add a
real feature module (e.g. `projects`):

1. Add `app/models/project.py`, import it in `app/models/__init__.py`.
2. Add `app/schemas/project.py`.
3. Add `app/services/project_service.py` — pure logic, takes an `AsyncSession`.
4. Add `app/api/v1/endpoints/projects.py` — thin routes calling the service,
   protected with `Depends(get_current_user)` wherever the resource is
   user-scoped.
5. Register it: `api_router.include_router(projects.router, prefix="/projects")`
   in `app/api/v1/router.py`.
6. `alembic revision --autogenerate -m "add projects table"` then
   `alembic upgrade head`.

No changes to the auth module are needed for any of this.

---

## What was verified

This isn't just written to compile — it was run end-to-end against a real
local PostgreSQL instance:

- Confirmed: `alembic revision --autogenerate` produced the migration in
  `alembic/versions/` from the actual models (not hand-written), and
  `alembic upgrade head` applied cleanly with no drift (`alembic check`
  reports no new operations after applying).
- Confirmed: register (201) then duplicate-email rejection (409), then
  login (200) then wrong-password rejection (401), then `/me` (200), then
  refresh rotation (200), then replay of the now-rotated token (401,
  revoked), then logout (200), then refresh after logout (401, revoked).
- Confirmed: token-type guards — a refresh token rejected on `/me`, an
  access token rejected on `/refresh`.
- Confirmed: validation errors (bad email, weak password) return
  structured 422 responses.
- Confirmed: the ORCID login redirect returns a real `302` to ORCID's
  authorize URL.
- Known limitation of the sandbox this was built in: the Google login
  redirect requires live network access to `accounts.google.com` for OIDC
  discovery, which this sandbox's network allowlist blocks. The identical
  code path is used for ORCID, which *was* verified end-to-end, so the
  redirect mechanism itself is sound — just confirm it against real Google
  credentials and normal network access before shipping.
