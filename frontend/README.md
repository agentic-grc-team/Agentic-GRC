# Agentic GRC frontend

React + Vite interface for account access, organizations, invitations, security assessments, and the AI-led interview. Expert review, evidence workflows, and reporting are outside the initial interview journey.

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
4. Start FastAPI, then Vite. Sign in, create an organization, and invite a representative by email.
5. New invitees open the one-use email link and set a password. Existing accounts sign in and accept pending invitations from the workspace.
6. An administrator or consultant creates an assessment for the organization. The representative opens **Assessments**, selects that assessment, and chooses **Go to interview**.
7. In **Interview**, choose **Start or resume interview**. The page saves responses as they are sent; opening the assessment again resumes the participant's session.

## Current scope

- Supabase email/password authentication and optional Google OAuth, with short-lived access tokens and SDK-managed refresh.
- Organization creation uses server-provided sector and size catalogs; fallback values are temporary until client-approved catalogs are supplied.
- Duplicate organization names require explicit confirmation.
- Administrators invite consultants or representatives. The backend sends a one-use link that expires after seven days through the configured SMTP server.
- Organization data is scoped through application memberships and FastAPI authorization.
- Administrators and consultants can create assessments; organization members can inspect assessment scope. The interview page starts or resumes the existing AI interview for an in-progress assessment.
- Interview sessions are scoped to the selected organization, assessment, and participant. Responses are persisted and retries use an idempotency key. The initial interview content and model evaluation use synthetic data; the current interview agent supports English.
- Evidence uploads require active organization membership, including for platform administrators. The evidence page requests `GET /organizations?active_memberships_only=true` and preserves an eligible workspace through `/evidence?organization_id=<id>`.
- Opening evidence without workspace context requires selecting an organization before uploading. The target organization is displayed beside the upload area; switching organizations clears previous results and cancels the previous client request. Canceling a client request does not undo an upload already processed by the server.

Run frontend checks with `npm test` and `npm run build`.

## Browser E2E

Install Chromium and run the deterministic browser journey from `frontend/`:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "0"
npx playwright install chromium
npm run test:e2e
```

The browser suite covers organization creation, invitations, assessment setup, starting and resuming an interview, and retrying an answer after a simulated assistant outage. Supabase Auth and API calls are stubbed in the browser; the backend API and PostgreSQL interview behavior are covered separately by `backend/tests/test_interviews_e2e.py`.
