# SAIRA — Local Development Setup

SAIRA is split into two independent projects in this repo:

```
.
├── backend/     FastAPI + SQLAlchemy + PostgreSQL (auth, API)
└── frontend/    Next.js (App Router) + TypeScript (UI)
```

They talk to each other over HTTP — the frontend calls the backend directly
from the browser, authenticated via HttpOnly cookies. Both need to be
running at the same time for the app to work end to end.

This guide covers both **Linux/macOS** and **Windows**. Steps are identical
unless a platform is called out explicitly.

---

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.13+ | 3.12 also works — nothing here uses 3.13-only syntax |
| Node.js | 20+ | includes `npm` |
| PostgreSQL | 14+ | server running locally, or reachable over the network |
| Git | any recent version | |

**Windows-specific:** install Python and Node from their official
installers (python.org, nodejs.org) and check "Add to PATH" during setup.
PostgreSQL for Windows ships with **pgAdmin** and a `psql` shell in the
Start Menu — you can use either that or a terminal for the database steps
below. If you use PowerShell and get an error about "running scripts is
disabled", see [Troubleshooting](#troubleshooting).

Verify everything is on your PATH before continuing:

```bash
python --version    # or python3 --version on Linux/macOS
node --version
npm --version
psql --version
```

---

## 2. Clone the repo

```bash
git clone <your-repo-url> saira
cd saira
```

---

## 3. Database setup

Create the database once, using whichever `psql` client you have:

```bash
# Linux/macOS
sudo -u postgres psql -c "CREATE DATABASE saira;"

# Windows (Command Prompt or PowerShell, if `psql` is on PATH)
psql -U postgres -c "CREATE DATABASE saira;"
```

If you don't have a `postgres` superuser password set yet, `psql -U postgres`
will prompt for one, or you can set it with:

```sql
ALTER USER postgres PASSWORD 'yourpassword';
```

Keep the resulting connection details (user, password, host, port, db name)
handy — you'll put them into the backend's `.env` in step 5.

---

## 4. Backend setup

### 4.1 Create and activate a virtual environment

**Linux/macOS:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate.bat
```

Your shell prompt should now show `(.venv)`. Do this every time you open a
new terminal to work on the backend.

### 4.2 Install dependencies

```bash
pip install -r requirements.txt
```

### 4.3 Configure environment variables

```bash
# Linux/macOS
cp .env.example .env

# Windows
copy .env.example .env
```

Open `backend/.env` and fill in real values:

```dotenv
ENVIRONMENT=development
DEBUG=true

BACKEND_CORS_ORIGINS=http://localhost:3000

# Match whatever you created in step 3
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/saira

# Generate both with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=
SESSION_SECRET_KEY=

ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30

FRONTEND_URL=http://localhost:3000

# https://console.cloud.google.com/apis/credentials — redirect URI must be
# added there exactly as below
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

# ORCID is not implemented yet — leave blank
ORCID_CLIENT_ID=
ORCID_CLIENT_SECRET=
ORCID_REDIRECT_URI=http://localhost:8000/api/v1/auth/orcid/callback
ORCID_ENVIRONMENT=sandbox

# Avatar uploads (local disk storage)
MEDIA_ROOT=media
BACKEND_PUBLIC_URL=http://localhost:8000
AVATAR_MAX_SIZE_MB=5.0
```

> `DATABASE_URL` always uses forward slashes and the `postgresql+asyncpg://`
> prefix, even on Windows — it's a connection string, not a file path.

### 4.4 Run database migrations

```bash
alembic upgrade head
```

This creates the `users`, `refresh_tokens` tables and everything else the
app needs. You should see `Running upgrade ... -> ..., <message>` lines
with no errors.

### 4.5 Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

Leave this running. Confirm it's up:

- Health check: http://localhost:8000/health
- Interactive API docs: http://localhost:8000/api/v1/docs

---

## 5. Frontend setup

Open a **new terminal** (leave the backend running in the first one).

```bash
cd frontend
npm install
```

Create the frontend's environment file:

```bash
# Linux/macOS
echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1" > .env.local

# Windows (PowerShell)
"NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1" | Out-File -Encoding utf8 .env.local

# Windows (Command Prompt)
echo NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 > .env.local
```

Start the dev server:

```bash
npm run dev
```

Open http://localhost:3000 — you should land on the SAIRA landing page.

---

## 6. Verify it's all wired up

With both servers running:

1. Go to http://localhost:3000/dashboard while logged out → you should be
   redirected to `/login` (protected-route check working).
2. On `/login`, create an account → you should land on `/dashboard` with
   your name/email initial showing in the sidebar.
3. Go to **Settings → Profile**, change your name and/or upload an avatar
   photo → changes should appear immediately in the sidebar, no refresh
   needed.
4. Log out (sidebar) → you should land back on `/login`.
5. Log back in with the same credentials → same session restored.
6. "Sign in with Google" on `/login` requires real Google OAuth credentials
   in `backend/.env` (see step 4.3) and a matching redirect URI configured
   in the Google Cloud Console.

---

## Running both servers day-to-day

You'll want two terminals open:

```bash
# Terminal 1 — backend
cd backend
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Backend: http://localhost:8000 · Frontend: http://localhost:3000

---

## Troubleshooting

**PowerShell says "running scripts is disabled on this system"**
Activating the venv runs a `.ps1` script, which PowerShell blocks by
default. Run PowerShell as Administrator once and execute:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Then retry activating the venv.

**`psycopg2`/`asyncpg` fails to install on Windows**
This project uses `asyncpg`, which ships prebuilt wheels for Windows — you
shouldn't need a C compiler. If installation still fails, make sure you're
on a 64-bit Python install and `pip` is up to date (`python -m pip install
--upgrade pip`).

**Port already in use**
```bash
# Linux/macOS — find and kill whatever's on port 8000 or 3000
lsof -i :8000
kill -9 <PID>

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**CORS errors in the browser console**
Check that `backend/.env`'s `BACKEND_CORS_ORIGINS` exactly matches the URL
the frontend is running on (`http://localhost:3000`, no trailing slash),
and that `frontend/.env.local`'s `NEXT_PUBLIC_API_URL` points at the
backend (`http://localhost:8000/api/v1`).

**Logged in but immediately redirected back to `/login`**
Usually means the `refresh_token` cookie isn't being set or read. Confirm
both servers are on `localhost` (not `127.0.0.1` on one and `localhost` on
the other — cookies are host-specific) and that you're not in a private/
incognito window with third-party cookies blocked.

**Alembic can't connect to the database**
Double-check `DATABASE_URL` in `backend/.env` — wrong password, wrong port,
or Postgres not running are the usual culprits. Confirm Postgres is up:
```bash
# Linux/macOS
sudo service postgresql status

# Windows — check "Services" app for "postgresql-x64-<version>",
# or if installed via installer it usually starts automatically
```

**Avatar upload fails or images don't show**
Confirm `MEDIA_ROOT` and `BACKEND_PUBLIC_URL` are set in `backend/.env` —
the backend creates the `media/` folder automatically on startup, but it
needs write permission to do so.

---

## Notes

- ORCID sign-in is intentionally not implemented yet — the button is
  present but disabled in the UI.
- Uploaded avatars are stored on local disk under `backend/media/` for
  development. This is not committed to git and not suitable for a real
  production deployment (use S3/GCS/Cloudinary there instead).
- Never commit real `.env` / `.env.local` files — only the `.env.example`
  templates belong in git.