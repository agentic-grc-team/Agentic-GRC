# Agentic GRC frontend

React + Vite interface for the first organization, account-login, and invitation workflows. The assessment conversation and AI analysis are intentionally out of scope.

## Run locally (PowerShell)

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open `http://127.0.0.1:4178`. Vite proxies `/api` requests to `http://127.0.0.1:8000` by default; set `VITE_API_PROXY_TARGET` if FastAPI runs elsewhere. `VITE_API_BASE_URL` can override the browser API base path.

## First setup

1. Start PostgreSQL and configure `backend/.env`, including `JWT_SECRET` and SMTP settings for email invitations.
2. Apply database migrations and provision the initial administrator from the backend: `alembic upgrade head` then `python -m app.cli bootstrap-admin`.
3. Sign in with that account, create an organization, and invite a consultant or representative by email.
4. Invitees open the single-use link, set a password, and are signed in after their profile and organization membership are created.

## Current scope

- Email/password login with a short-lived bearer token held in the browser tab's session storage.
- Organization creation uses server-provided sector and size catalogs; their fallback values are temporary until the approved client catalogs are supplied.
- Duplicate organization names require an explicit confirmation.
- Administrators invite consultants or representatives. The backend sends a one-use activation link that expires after seven days; SMTP configuration is required.
- Invitees with an existing account sign in and accept the pending invitation from the workspace.
- Organization data remains logically isolated in the shared backend database. Assessment, evidence upload, and AI analysis workflows are not part of this screen yet.

Run frontend checks with `npm test` and `npm run build`.
