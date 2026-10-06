# Agentic GRC frontend

React + Vite interface for the first organization, account-login, and invitation workflows. The assessment conversation and AI analysis are intentionally out of scope.

## Run locally (PowerShell)

```powershell
cd frontend
npm install
Copy-Item .env.example .env
# Set the Supabase URL and publishable key in .env.
npm run dev
```

Open `http://127.0.0.1:4178`. Vite proxies `/api` requests to `http://127.0.0.1:8000` by default; set `VITE_API_PROXY_TARGET` if FastAPI runs elsewhere. `VITE_API_BASE_URL` can override the browser API base path.

## Authentication configuration

Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` from the Supabase project. Only the publishable/legacy anon key belongs in this frontend configuration. Never put `SUPABASE_SECRET_KEY`, a service-role key, database credentials, or an SMTP password in a `VITE_*` variable.

In Supabase Auth, disable public sign-ups so invited accounts are provisioned by the backend only. In URL Configuration, allow `http://127.0.0.1:4178/auth/callback` for local Google OAuth. Configure the Google provider in Supabase if the Google sign-in button should be active. Email/password remains available through Supabase Auth.

The app stores Supabase sessions in the current browser tab and sends the access token to FastAPI. FastAPI validates that token with Supabase before returning the platform profile. Google OAuth uses Supabase as the identity provider; use the same verified email that was invited. Organization membership and authorization remain in the application database.

## First setup

1. Configure the PostgreSQL, Supabase Auth, and SMTP settings in `backend/.env` and the public Supabase values in `frontend/.env`.
2. Configure Email in Supabase Auth. To enable Google, set up its OAuth client in Supabase and allow the local callback URL.
3. Apply the backend migrations and provision the initial administrator profile from an existing confirmed Supabase Auth user. See `backend/README.md` for the exact command.
4. Start FastAPI, then Vite. Sign in, create an organization, and invite a consultant or representative by email.
5. New invitees open the one-use email link and set a password. Existing accounts sign in and accept pending invitations from the workspace.

## Current scope

- Supabase email/password authentication and optional Google OAuth, with short-lived access tokens and SDK-managed refresh.
- Organization creation uses server-provided sector and size catalogs; fallback values are temporary until client-approved catalogs are supplied.
- Duplicate organization names require explicit confirmation.
- Administrators invite consultants or representatives. The backend sends a one-use link that expires after seven days through the configured SMTP server.
- Organization data is scoped through application memberships and FastAPI authorization. Assessment, evidence upload, and AI analysis workflows are not part of this screen yet.

Run frontend checks with `npm test` and `npm run build`.
