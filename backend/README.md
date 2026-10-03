# Agentic GRC API

Initial FastAPI service scaffold. API routes live under `/api/v1`.

## Run locally (PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with the PostgreSQL connection details before running migrations.
alembic upgrade head
uvicorn app.main:app --reload
```

The API health check is available at `http://127.0.0.1:8000/api/v1/health`.
Interactive API docs are available at `http://127.0.0.1:8000/docs`.

The provisional database model, endpoint behavior, and assumptions are documented in [DATABASE.md](DATABASE.md). Organization and invitation endpoints require a verified JWT from the configured OIDC provider. Set `AUTH_ISSUER`, `AUTH_AUDIENCE`, and `AUTH_JWKS_URL` in `.env`; issuer and JWKS URLs must use HTTPS. Until these are configured, protected routes return `503` by design. Invitations are stored but not emailed yet; the API supports discovery by the invitee's verified email and acceptance.

The SQLAlchemy connection URL is assembled from `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and `DB_SSLMODE`. These values are read from `backend/.env` (or the process environment) by both FastAPI's database session helper and Alembic. The database name defaults to `agentic_grc`; use the actual host, username, password, and TLS settings supplied for the PostgreSQL connection. Never commit `.env`.

The organization API requires a bearer access token with `iss`, `aud`, `exp`, `sub`, `email`, and boolean `email_verified: true` claims. Only RS256 and ES256 signing keys published by the configured JWKS endpoint are accepted. The API never trusts a user ID or email passed in request headers or bodies to establish identity.
