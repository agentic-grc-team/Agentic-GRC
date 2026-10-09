# Provisional database and identity model

This is the MVP schema for organization onboarding and invitations. It is intentionally small and remains subject to review by the teammate responsible for the final project schema.

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
