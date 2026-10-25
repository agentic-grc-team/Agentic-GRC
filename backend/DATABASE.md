# Database and identity model

This document covers the current organization identity model and the additive interview persistence slice. The attached project DDL remains the canonical target for assessment, evidence, and result normalization; those existing tables are migrated in later phases after reference-data mapping is approved.

## Identity and application data

Supabase Auth owns credentials, email verification, OAuth identities, and access/refresh tokens. The application does not store passwords or provider identity tokens. `public.users.id` is the same UUID as `auth.users.id`; the profile table stores the application email snapshot, platform-admin flag, deactivation state, and audit timestamps. The cross-schema foreign key cascades profile removal when an Auth identity is deleted.

The backend validates each bearer token through Supabase Auth's `/auth/v1/user` endpoint, then resolves or provisions the matching application profile. Roles and organization access are read from application tables, never trusted from user-editable token metadata.

## Tables

| Table | Purpose | Key relationship |
| --- | --- | --- |
| `auth.users` | Supabase-managed credentials and identities. | Supabase Auth owns this table; application migrations never create it. |
| `public.users` | Application profile and platform privileges. | `id` references `auth.users.id`. |
| `public.organizations` | Client organization name, sector, size, and duplicate-name audit. | Creator and duplicate confirmer reference `public.users`. |
| `public.organization_memberships` | User access and role within one organization. | Unique organization/user pair; roles are administrator, consultant, or representative. |
| `public.organization_invitations` | Pending invitations, hashed one-time token, role, expiry, and acceptance audit. | On acceptance, links the new or existing profile and creates membership. |
| `public.industry_sectors` | Sector lookup values used by organization profiles. | Referenced by organizations. |
| `public.organization_sizes` | Size lookup values used by organization profiles. | Referenced by organizations. |

Organization invitations expire after seven days. The raw invitation token is included only in the email; the database stores its SHA-256 hash. A new invitee's account is created through the Supabase Admin Auth API only after that token is validated. An existing Auth user signs in first and accepts the invitation through the authenticated organization API.

## Access boundaries

Row Level Security is enabled on the application tables. The frontend uses Supabase only for Auth and calls domain endpoints through FastAPI; it must never receive the Supabase secret key. No direct Data API policies are defined for these application tables. The FastAPI service uses the configured PostgreSQL connection for domain queries and enforces organization membership and role checks.

The first platform administrator must first be created and email-confirmed in Supabase Auth, then linked by the backend CLI. Do not seed an application-only user because every profile must reference an Auth identity.

## Migration notes

`20261006_0005_supabase_auth_identity` removes the former local password and OIDC columns, links profiles to `auth.users`, and enables RLS on the application's public tables. It stops before changing the schema if it finds an application profile without a matching Supabase Auth identity. If earlier migrations were already applied and `public.users` contains data, map those profiles to matching Auth UUIDs before running it; do not bypass the preflight check.

The migration is prepared but has not been applied to the remote Supabase project from this environment. Check the current Alembic revision and take a backup before applying schema changes.

## Interview persistence and checkpoint state

Migration `20261020_0008` adds the interview catalog/session slice: framework and knowledge-base version identifiers, interview blocks, modules and questions, participants, assessment sessions, session participants, interview turns, and normalized interview source links for decision traces. Tenant-owned session, turn, and trace-source rows use composite organization-scoped foreign keys. RLS is enabled on the new public tables; the FastAPI database role remains responsible for membership checks because no direct Supabase Data API policies are defined.

The existing `assessments` table still carries the earlier text fields for framework and knowledge-base versions. The new catalog is additive; a follow-up migration must map those existing values before replacing legacy columns or normalizing assessment controls. The optional `questions.statement_id` and `questions.remediation_template_id` references remain nullable until those catalog tables are brought in. For trace compatibility, interview sources are written both to the normalized `decision_trace_sources` rows and to the legacy trace JSON until the trace API is migrated.

LangGraph checkpoint state is stored separately in the non-exposed `agentic_grc_private` schema. Alembic creates that schema and revokes access from `PUBLIC`; the LangGraph library owns its checkpoint tables and migrations. After applying Alembic, initialize those tables once with:

```powershell
cd backend
python -m app.cli init-interview-checkpointer
```

Checkpoint threads use the assessment session UUID. Graph state must be JSON-compatible, use the restricted MsgPack serializer, and contain no credentials. Checkpoints are working memory, not the canonical record of answers or findings. They contain conversation state and are subject to the same production-data gate and future retention/deletion policy as interview turns.

The backend defaults `INTERVIEW_DATA_MODE` to `synthetic`. `approved_anonymized` requires `INTERVIEW_ANONYMIZED_DATA_APPROVED=true`. `real` fails settings validation unless transfer, retention, deletion, redaction, storage, and topology gates are each explicitly enabled. These switches record deployment approvals; they do not replace the required written approval in [ADR 0003](../docs/decisions/0003-interview-data-governance.md).
