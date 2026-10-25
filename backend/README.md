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
python -m app.cli init-interview-checkpointer
python -m app.cli bootstrap-admin --user-id <SUPABASE_AUTH_UUID> --email <ADMIN_EMAIL>
uvicorn app.main:app --reload
```

To keep test credentials separate from the default local environment, copy `.env.example` to
`.env.testing`, fill it with the isolated test project's values, and select it in the PowerShell
session before running Alembic or the API:

```powershell
Copy-Item .env.example .env.testing
$env:AGRC_ENV_FILE = ".env.testing"
alembic upgrade head
python -m app.cli init-interview-checkpointer
uvicorn app.main:app --reload
```

`AGRC_ENV_FILE` is resolved relative to the `backend` directory when it is not an absolute path.
The selected environment file is ignored by Git; never commit database passwords or Supabase secret
keys. Remove the process override with `Remove-Item Env:AGRC_ENV_FILE` to return to `.env`.

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
- Demo report: `ALLOW_DEMO_REPORT` (default false; refused in production).
- Interview data gate: `INTERVIEW_DATA_MODE` defaults to `synthetic`; anonymized testing requires an approval flag, and real mode requires each transfer, retention, deletion, redaction, storage, and topology gate.
- Interview agent (development): `AGRC_OLLAMA_HOST`, `AGRC_LLM_MODEL`, `AGRC_LLM_TIMEOUT_S`, `AGRC_LLM_RETRIES`, `AGRC_MAX_FOLLOW_UPS`, and optionally `AGRC_KB_PATH`. The current adapter is the local Ollama proof of concept; GCP remains the provisional production inference target and is not configured by this adapter.

The old `JWT_SECRET` and local password-hash settings are no longer used. Remove the temporary JWT secret from your local environment once this branch is adopted. Supabase email/password sign-in and Google OAuth are authenticated by Supabase; the current app SMTP server only sends organization invitations.

## Authenticated assessment interviews

The session endpoint starts or resumes the LangGraph thread using the assessment session UUID and stores the first agent prompt in `interview_turns`. Posting a participant answer requires both `replies_to_turn_id` (the latest agent turn) and `question_id` matching that prompt; repeat submissions must reuse the same `client_request_id` or `Idempotency-Key`. The response includes generated agent turns and draft results. `GET .../interview` restores the durable transcript and in-scope drafts.

The agent uses the assessment's exact `kb_version` and filters its question mappings against `assessment_controls.in_scope`. The checked-in YAML KB is provisional and currently matches `demo-0.2`; synthetic sessions can use it when the normalized KB question rows are absent. Block interviews require questions in the selected stored block. Real or approved-anonymized sessions require matching stored question rows. Run `python -m app.cli init-interview-checkpointer` after migrations before opening sessions. For local development, install the backend requirements and run Ollama with the configured model; model failures degrade to the agent's deterministic rules and templates. For setup, tuning, benchmark, and demo checklist, see [docs/ollama-setup.md](../docs/ollama-setup.md).

## Tests

Run unit tests with:

```powershell
python -m unittest discover -v
```

Auth service and configuration tests do not require network access. Organization workflow integration tests require a reachable Supabase PostgreSQL database with the migrations applied; they are skipped if PostgreSQL is unavailable.
