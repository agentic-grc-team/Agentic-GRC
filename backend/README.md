# Agentic GRC API

FastAPI service for the first organization, login, and invitation workflows. API routes live under `/api/v1`.

## Run locally (PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Set the Supabase, PostgreSQL, and SMTP values described below.
alembic upgrade head
python -m app.cli bootstrap-admin --user-id <SUPABASE_AUTH_UUID> --email <ADMIN_EMAIL>
uvicorn app.main:app --reload
```

The health check is at `http://127.0.0.1:8000/api/v1/health` and interactive API docs are at `http://127.0.0.1:8000/docs`.

## Authentication setup

Supabase Auth is the identity provider. Enable Email in the Supabase Auth providers and disable public sign-ups; the backend creates new Auth identities only after validating an organization invitation. Create the initial platform administrator in Supabase Auth with a confirmed email. Use that Auth user's UUID and email with the CLI command above to create the application profile and grant platform-admin access. The CLI never creates or stores a password.

The frontend supports email/password sign-in and optional Google OAuth through the same Supabase project. To enable Google, configure the Google provider in Supabase with a Google OAuth client ID and secret, then add the Supabase callback URL shown in that provider's settings to the Google OAuth client's authorized redirect URIs. Add `http://127.0.0.1:4178/auth/callback` to Supabase's allowed redirect URLs for local development. Google sign-in must resolve to the invited/registered email; a Supabase identity without an organization membership receives no organization data.

FastAPI validates each bearer token with Supabase Auth's user endpoint and uses its verified user ID and email to resolve the application profile. It does not issue its own JWTs. `GET /api/v1/auth/me` returns the current application account.

## Organizations and invitations

- The organization creator becomes its first administrator. Organization membership and organization creation are committed together.
- Sector and size are foreign keys into lookup tables. The current fallback choices (`Other / not specified`, `Not specified`) are temporary until approved client catalogs are available.
- Organization-name duplicates require explicit confirmation, recorded with the matching organization and confirmer.
- Administrators can invite consultants or representatives. The invitation token is random, single-use, stored only as a SHA-256 hash, and expires after seven days.
- FastAPI continues to send organization invitations through its configured SMTP server. Following the invite link, a new invitee chooses a password; the backend verifies the invitation before creating a confirmed Supabase Auth user and committing the profile and membership.
- If the email already has a Supabase account, the invitee signs in first and accepts the invitation from the workspace. The invitation's email must match the authenticated account.

## Environment variables

`backend/.env` is read by the backend and Alembic. Configure:

- PostgreSQL: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE`.
- Supabase Auth: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `SUPABASE_SECRET_KEY`. The publishable key may also be the project's legacy anon key. The secret key (or legacy service-role key) is server-only and must never be put in a `VITE_*` variable or committed.
- Invitation links: `APP_BASE_URL`.
- Outbound organization email: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_SENDER_EMAIL`, `SMTP_STARTTLS`, and `SMTP_TIMEOUT_SECONDS`.
- Runtime mode: `APP_ENVIRONMENT`.

The old `JWT_SECRET` and local password-hash settings are no longer used. Remove the temporary JWT secret from your local environment once this branch is adopted. Supabase email/password sign-in and Google OAuth are authenticated by Supabase; the current app SMTP server only sends organization invitations.

## Tests

Run unit tests with:

```powershell
python -m unittest discover -v
```

Auth service and configuration tests do not require network access. Organization workflow integration tests require a reachable Supabase PostgreSQL database with the migrations applied; they are skipped if PostgreSQL is unavailable.
