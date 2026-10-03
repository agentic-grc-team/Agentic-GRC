# Provisional database design

This is a first-pass schema for the organization-registration story, not an approved final data model. It is intentionally small and should be reviewed and adjusted by the teammate responsible for the database design.

## Tables

| Table | Purpose | Key relationships |
| --- | --- | --- |
| `organizations` | Client name, sector, size, creator, and duplicate-name confirmation audit. | Optional creator and duplicate reference point to `users` / `organizations`. |
| `users` | Platform-level identity identified by a verified email and the `(OIDC issuer, subject)` pair from the identity provider. The API stores no password or authentication token. | One user can have many memberships. |
| `organization_memberships` | A user's role and status within one organization. | Many-to-many join between `users` and `organizations`, unique per pair. |
| `organization_invitations` | Email invitation, intended role, sender, expiry/status, and a hash of the acceptance token. | Belongs to one organization; acceptance can link to a user. |

Organization sector and size are stored as bounded strings rather than database enums because the client's allowed values are not yet settled. They can be supplied to the agent later as interview context; the database itself does not call the agent.

## Tenant data space

The provisional choice is one shared PostgreSQL database (`agentic_grc`) with logical tenant isolation, not one physical database or schema per client. An organization row and UUID establish its empty scope. Every future organization-owned table (assessments, evidence, answers, and similar records) must carry a non-null `organization_id` foreign key, and service queries must authorize and filter by the caller's organization membership. This keeps a new organization's space empty until records are created without provisioning separate infrastructure.

This MVP model does not enable PostgreSQL row-level security. Application authorization and tenant scoping will therefore be mandatory before adding organization-data endpoints; UUIDs alone are not access control.

## Duplicate names

For this first pass, names are compared globally, case-insensitively after trimming whitespace. A non-unique functional index supports that lookup while still allowing a confirmed duplicate. When a duplicate is explicitly accepted, the service should record `duplicate_of_organization_id`, `duplicate_name_confirmed_at`, and `duplicate_name_confirmed_by_user_id`. The reference and timestamp stay null for an ordinary name; the confirmer can later become null if that user is removed. The service must check duplicates transactionally; the non-unique index by itself does not prevent concurrent duplicate submissions.

## Invitation and membership flow

Assumption for review: the user who creates an organization becomes its first administrator. Organization creation and that initial membership are saved in one transaction. An active administrator creates a consultant invitation scoped to their organization. Email delivery is deliberately deferred; the invitation is persisted as pending, and a verified user whose email matches can discover it at `GET /api/v1/organizations/me/invitations` and accept it through the API. Acceptance creates the organization membership and updates the invitation in one transaction. The user's identity is global, while role and membership status are per organization, so one user can belong to multiple clients with separate roles. The invitation UUID is not an authentication secret: acceptance also requires a valid provider JWT with the same verified email. Raw invite tokens must never be stored. Enforcing that only an active administrator can invite is an API authorization rule, not a database constraint.

## API behavior (initial HU implementation)

- `POST /api/v1/organizations`: requires a verified provider JWT; creates the organization and first administrator membership atomically. Names are compared globally, case-insensitively after trimming. If a match exists, the API returns `409` and matching IDs; a retry must set `confirm_duplicate_of` to one of those IDs to record explicit confirmation.
- `GET /api/v1/organizations` and `GET /api/v1/organizations/{id}`: return only organizations with an active membership for the authenticated user.
- `POST /api/v1/organizations/{id}/invitations`: active administrators only. It creates a pending consultant invitation, expires after seven days (provisional), and reports `delivery_status: not_sent`. It rejects an existing membership or unexpired pending invitation for that organization/email.
- `GET /api/v1/organizations/me/invitations` and `POST /api/v1/organizations/invitations/{id}/accept`: a verified email can discover and accept only its own pending invitation. Acceptance adds a separate membership row.

All non-health API routes use OIDC bearer JWT verification. Configure `AUTH_ISSUER`, `AUTH_AUDIENCE`, and `AUTH_JWKS_URL`; issuer and JWKS URLs must use HTTPS. The verifier checks the signing key from JWKS, issuer, audience, expiration, subject, and a strictly boolean `email_verified: true` claim. The accepted signing algorithms are RS256 and ES256. The API fails closed when authentication is not configured. No email-sending provider is configured yet.

## Provisional choices to review

- Confirm whether duplicate-name matching should be global or scoped to a client/workspace.
- The accepted sector/size values and their maximum lengths.
- Confirm that the creator becomes the first administrator.
- Invitation expiry, re-invitation, and role-assignment rules.
- Confirm the provider-specific JWT claims/algorithms and whether invitations should later be sent by SMTP, Microsoft Graph, or another mailer.
- Whether the final deployment needs PostgreSQL row-level security or separate schemas.

`DB_SSLMODE=prefer` is intended only as a convenient local-development default. A deployed environment should use the TLS mode and CA-verification policy specified by the PostgreSQL administrator (typically `verify-full` with the correct certificate configuration).

No real database credentials are included. Put the connection values in an ignored local `backend/.env` file and apply migrations with `alembic upgrade head`.
