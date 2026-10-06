# Agentic GRC API

FastAPI service for the first organization, login, and invitation workflows. API routes live under `/api/v1`.

## Run locally (PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Set the PostgreSQL and JWT values. Configure SMTP to test email invitations.
alembic upgrade head
python -m app.cli bootstrap-admin
uvicorn app.main:app --reload
```

The health check is at `http://127.0.0.1:8000/api/v1/health` and interactive API docs are at `http://127.0.0.1:8000/docs`.

## Authentication and accounts

There is no public sign-up. Provision the first platform administrator once with `python -m app.cli bootstrap-admin`; the password is prompted, hashed, and never passed as a command-line argument. New consultant and representative accounts are created when they accept an invitation. Acceptance verifies the invited email and activates the organization membership.

`POST /api/v1/auth/login` accepts an email and password and returns a short-lived HS256 bearer token. `GET /api/v1/auth/me` returns the current account. Set `JWT_SECRET` to a unique random value of at least 32 bytes; do not reuse the example value. Login failures are rate-limited in-process as a basic MVP safeguard.

## Organizations and invitations

- The organization creator becomes its first administrator. Organization membership and organization creation are committed together.
- Sector and size are foreign keys into lookup tables. The migration preserves existing labels and adds only fallback choices (`Other / not specified`, `Not specified`) so a fresh database is usable; replace or extend these when the client-approved catalog is available.
- Organization-name duplicates require an explicit confirmation that records the matching organization and confirmer. Data is logically scoped by organization in the shared `agentic_grc` database.
- Administrators can invite consultants or representatives. SMTP must be configured; a failed email delivery leaves no pending invitation. The one-use activation token is stored only as a SHA-256 hash and expires after seven days.
- New invitees set a password at `POST /api/v1/auth/accept-invitation`. Existing users sign in and accept their pending invitation at `POST /api/v1/organizations/invitations/{id}/accept`.

See [DATABASE.md](DATABASE.md) for the provisional schema and boundaries. Reset-password flows, invitation resend/revocation, and invitations to additional administrators are outside this first implementation.

## Configuration and migrations

Database settings are read from `backend/.env` or the process environment: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and `DB_SSLMODE`. The database defaults to `agentic_grc`. `JWT_SECRET`, `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_ACCESS_TOKEN_MINUTES`, and `APP_BASE_URL` configure local authentication and invitation links.

Email delivery uses `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_SENDER_EMAIL`, `SMTP_STARTTLS`, and `SMTP_TIMEOUT_SECONDS`. Do not commit `.env` or real credentials. Apply schema changes with `alembic upgrade head`.

Run the tests with:

```powershell
python -m unittest discover -v
```

The authentication/password tests do not require PostgreSQL. Organization/invitation integration tests are skipped when PostgreSQL cannot be reached and require the migrations to have been applied.
