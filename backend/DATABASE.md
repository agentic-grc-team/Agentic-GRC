# Provisional database and authentication design

This is an implementation baseline for the login and organization-invitation phases, not the final project-wide schema. It applies only the relevant organization/account tables from the shared SQL design; assessment, evidence, report, and analysis tables remain out of scope for these phases.

## Tables

| Table | Purpose | Key relationships |
| --- | --- | --- |
| `users` | Global account keyed by normalized email; stores a password hash, verification time, platform-admin flag, and lifecycle fields. | One user can have memberships in many organizations. Legacy OIDC identity columns are retained for schema compatibility but are not used by local login. |
| `organizations` | Client name, sector/size references, creator, and duplicate-name confirmation audit. | Sector/size refer to lookup tables; creator and duplicate references link to users/organizations. |
| `industry_sectors`, `organization_sizes` | Editable catalogs used to validate and contextualize organization records. | Each organization references one row from each catalog. |
| `organization_memberships` | User role and status within one organization. | Many-to-many join between users and organizations, unique per pair. Roles include administrator, consultant, and representative. |
| `organization_invitations` | Invited email, intended role, token hash, sender, expiry, and acceptance/status audit. | Belongs to one organization and can link to the user created or matched at acceptance. |

The migration keeps historic sector/size labels, if any, and adds two fallback catalog options for an empty database. Those are temporary minimum options, not the client's approved taxonomy. All organization data lives in one PostgreSQL database (`agentic_grc`) with logical tenant isolation. Every future organization-owned table must carry a non-null `organization_id`; service queries must check membership and scope records to that organization. PostgreSQL row-level security is not enabled in this MVP.

## Account and invitation flow

There is no public sign-up. A one-time CLI command provisions the initial platform administrator after migrations are applied. An administrator creates an organization and becomes its first organization administrator. That administrator can invite consultants and representatives by email; invitations expire after seven days.

The API generates a high-entropy, single-use token, stores only its SHA-256 hash, and emails the raw token in the URL fragment of an activation link. A new invitee creates a profile by setting a password through that link. Successful acceptance verifies the invited email and creates the user and organization membership in one transaction. A user who already has an account signs in and accepts the pending invitation from the authenticated invitation list. Administrator invitations, password reset, resend, and revoke workflows are not part of this MVP.

Passwords are stored as scrypt hashes. Access tokens are short-lived HS256 JWTs signed with `JWT_SECRET`. SMTP delivery is performed before committing a pending invitation; a delivery failure rolls back the invitation. This avoids leaving an invitation that the API reports as sent when SMTP rejected it.

## API behavior

- `POST /api/v1/auth/login`: verifies an active, email-verified account and returns a short-lived access token.
- `GET /api/v1/auth/me`: returns the signed-in user.
- `POST /api/v1/auth/accept-invitation`: consumes an emailed token and creates or activates the invitee's profile and membership.
- `GET /api/v1/reference-data/industry-sectors` and `/organization-sizes`: return the available catalogs to authenticated clients.
- `POST /api/v1/organizations`: creates an organization and its first administrator membership in one transaction. Duplicate names return matching organizations and require explicit confirmation on retry.
- `GET /api/v1/organizations` and `GET /api/v1/organizations/{id}`: return organizations available to the current user (platform administrators can see all).
- `PATCH /api/v1/organizations/{id}`: updates organization data for an administrator.
- `POST /api/v1/organizations/{id}/invitations`: administrator-only invite by email, limited to consultant or representative.
- `GET /api/v1/organizations/me/invitations` and `POST /api/v1/organizations/invitations/{id}/accept`: list and accept pending invitations for the signed-in email.

The application enforces role authorization. UUIDs are not treated as access control, and clients cannot choose their own user ID, email, or membership role. A representative can view organization details and results when those future endpoints are implemented; this phase does not add assessment/report endpoints.

## Decisions deferred

- Replace or extend the temporary sector/size fallback options with the client-approved catalog.
- Add reset-password and invitation resend/revocation flows if needed.
- Decide whether additional administrators can be invited and how platform-admin management works after bootstrap.
- Revisit row-level security/deployment TLS requirements before production use.

Database connection values belong in the ignored local `backend/.env` file. Never commit actual credentials or JWT/SMTP secrets.
