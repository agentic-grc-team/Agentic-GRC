# Deployment: Cloudflare Pages + Azure Container Apps

First phase of the cloud architecture proposal: the React frontend on **Cloudflare Pages**, the
FastAPI API (with the LangGraph agent still inside it) on **Azure Container Apps**, and
**Supabase** for Auth and PostgreSQL. The agent and Ollama move to the institutional VM in a later
phase.

```
Browser ──► Cloudflare Pages (static)            https://<project>.pages.dev
   │
   └──────► Azure Container Apps (FastAPI)       https://<app>.<region>.azurecontainerapps.io
                 │
                 └──► Supabase (Auth + PostgreSQL via session pooler)
```

`.github/workflows/deploy.yml` runs migrations, builds the API image, pushes it to GHCR, deploys a
new Container Apps revision, checks `/api/v1/health` and publishes the frontend. Pushes to `main`
deploy only when the repository variable `DEPLOY_ENABLED` is `true`; it can always be run by hand
(**Actions → Deploy → Run workflow**).

## Known limitations of this phase

- **No model in Azure.** Ollama is not reachable from the container, so interviews use the agent's
  deterministic fallback (keyword interpretation and template questions). Controls closed this
  way always require human review. Pointing `AGRC_OLLAMA_HOST` at a remote host requires HTTPS and
  `INTERVIEW_EXTERNAL_TRANSFER_APPROVED` / `INTERVIEW_TOPOLOGY_DOCUMENTED` (ADR 0003).
- **Evidence files are ephemeral.** Uploads are written to the container disk and lost on restart.
  Only the extracted text, stored in PostgreSQL, is used afterwards.
- **Cold starts.** With zero minimum replicas the first request after idle takes several seconds.
- **Supabase Free pauses** after a week without activity; open the project before a demo.
- **Synthetic data only** (`INTERVIEW_DATA_MODE=synthetic`) until ADR 0003's gates are approved.

## One-time setup

### 1. Supabase

1. Note the **session pooler** connection (Project Settings → Database → Connection pooling →
   *Session*, port 5432). Azure and GitHub runners use IPv4, and the direct connection is IPv6
   only. Do not use the transaction pooler (port 6543): LangGraph checkpoints need session mode.
2. Auth → URL Configuration: set *Site URL* to `https://<project>.pages.dev` and add
   `https://<project>.pages.dev/auth/callback` to *Redirect URLs*.
3. Keep public sign-ups disabled (see `backend/README.md`).

### 2. Cloudflare Pages

1. Create a Pages project with **Direct Upload** (the workflow uploads `frontend/dist`). Its name is
   `CLOUDFLARE_PAGES_PROJECT`.
2. Create an API token with the *Cloudflare Pages: Edit* permission.

No SPA rewrite file is needed: without a `404.html`, Pages serves `index.html` for routes such as
`/invite/accept` and `/auth/callback`.

### 3. Azure Container Apps

```bash
az group create --name agentic-grc-rg --location <region-near-supabase>
az containerapp env create --name agentic-grc-env --resource-group agentic-grc-rg --location <region>
az containerapp create --name agentic-grc-api --resource-group agentic-grc-rg \
  --environment agentic-grc-env --image mcr.microsoft.com/k8se/quickstart:latest \
  --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 \
  --cpu 0.5 --memory 1.0Gi
```

The image lives in GHCR. Either make the `agentic-grc-api` package public after the first push, or
register GHCR with a read-only token:
`az containerapp registry set --name agentic-grc-api --resource-group agentic-grc-rg --server ghcr.io --username <user> --password <token-with-read:packages>`.

Store the secrets and reference them from environment variables:

```bash
az containerapp secret set --name agentic-grc-api --resource-group agentic-grc-rg --secrets \
  db-password=<...> supabase-secret-key=<...> smtp-password=<...>

az containerapp update --name agentic-grc-api --resource-group agentic-grc-rg --set-env-vars \
  APP_ENVIRONMENT=production \
  APP_BASE_URL=https://<project>.pages.dev \
  CORS_ALLOWED_ORIGINS=https://<project>.pages.dev \
  DB_HOST=<pooler-host> DB_PORT=5432 DB_NAME=postgres DB_USER=<pooler-user> DB_SSLMODE=require \
  DB_PASSWORD=secretref:db-password \
  SUPABASE_URL=https://<ref>.supabase.co SUPABASE_PUBLISHABLE_KEY=<publishable-key> \
  SUPABASE_SECRET_KEY=secretref:supabase-secret-key \
  SMTP_HOST=<host> SMTP_PORT=587 SMTP_USERNAME=<user> SMTP_PASSWORD=secretref:smtp-password \
  SMTP_SENDER_EMAIL=<sender> SMTP_STARTTLS=true \
  ALLOW_DEMO_REPORT=false INTERVIEW_DATA_MODE=synthetic
```

Production settings refuse to start without HTTPS URLs, both Supabase keys and SMTP with STARTTLS
(`backend/app/core/config.py`).

### 4. GitHub OIDC login to Azure

Create an app registration with a federated credential for this repository's `production`
environment and give it the *Contributor* role on the resource group (or a narrower custom role
with `Microsoft.App/containerApps/write`). See
[Azure login with OpenID Connect](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect).

### 5. GitHub `production` environment

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | App registration from step 4 |
| Secret | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | Step 2 |
| Secret | `DB_HOST`, `DB_USER`, `DB_PASSWORD` | Supabase session pooler (migrations) |
| Variable | `DB_PORT`, `DB_NAME` | Optional; default `5432`, `postgres` |
| Variable | `AZURE_RESOURCE_GROUP`, `AZURE_CONTAINERAPP_NAME` | `agentic-grc-rg`, `agentic-grc-api` |
| Variable | `API_PUBLIC_URL` | `https://<app>.<region>.azurecontainerapps.io` (no trailing slash) |
| Variable | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | Public values used in the frontend build |
| Variable | `CLOUDFLARE_PAGES_PROJECT` | Pages project name |

Set the repository variable `DEPLOY_ENABLED=true` once a manual run succeeds.

### 6. First administrator

After the first successful deployment, create the admin in Supabase Auth (confirmed email) and run
once, from a machine with the pooler credentials in `backend/.env`:

```bash
python -m app.cli bootstrap-admin --user-id <SUPABASE_AUTH_UUID> --email <ADMIN_EMAIL>
```

## Protecting the free budget

Keep `--min-replicas 0 --max-replicas 1`, watch Azure for Students credit in Cost Management and
set a budget alert. Replica limits reduce consumption but are not spending caps.
