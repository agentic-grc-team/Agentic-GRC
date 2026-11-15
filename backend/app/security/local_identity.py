"""Mirror Supabase-verified identities into a self-hosted auth.users table.

On Supabase, auth.users is managed by Supabase Auth. On a self-hosted PostgreSQL (the Beta VMs)
it is only the stub from tests/sql/supabase_auth_stub.sql, so public.users (which has a foreign
key to auth.users) cannot be created for a new user until a matching row exists there.

When AUTH_MIRROR_LOCAL_IDENTITIES is enabled, a minimal row is written for an identity that
Supabase has already verified, in the caller's transaction. The mirror grants nothing:
memberships, roles and platform-admin rights stay in public.* with their own checks.
"""

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.security.supabase import SupabaseIdentity


class LocalIdentityMirrorRefused(RuntimeError):
    """The mirror is enabled but cannot run: the database looks like a real Supabase project, or the
    app role cannot write auth.users (for example, the INSERT/UPDATE grant was not applied)."""


_MIRROR_SQL = text(
    "INSERT INTO auth.users (id, aud, role, email, email_confirmed_at, created_at, updated_at) "
    "VALUES (:id, 'authenticated', 'authenticated', :email, now(), now(), now()) "
    "ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, updated_at = now()"
)

_SUPABASE_MARKER_SQL = text("SELECT to_regclass('auth.schema_migrations') IS NOT NULL")


def _is_real_supabase(db: Session) -> bool:
    # Supabase Auth (GoTrue) creates auth.schema_migrations; the local stub never does.
    return db.scalar(_SUPABASE_MARKER_SQL) is True


def mirror_verified_identity(identity: SupabaseIdentity, db: Session, settings: Settings) -> None:
    """Ensure auth.users holds a row for a Supabase-verified identity on a self-hosted database.

    Does nothing unless AUTH_MIRROR_LOCAL_IDENTITIES is enabled and the email is verified.
    Never commits: the caller's transaction does. Never logs the email or any token.
    """
    if not settings.auth_mirror_local_identities:
        return
    if not identity.email_verified:
        return
    if _is_real_supabase(db):
        raise LocalIdentityMirrorRefused(
            "AUTH_MIRROR_LOCAL_IDENTITIES must be false when the database is Supabase."
        )
    try:
        db.execute(_MIRROR_SQL, {"id": identity.id, "email": identity.email})
    except DBAPIError as exc:
        # Typically "permission denied for table users": the flag was enabled before
        # deploy/vm/postgres/auth-users-grants.sql granted INSERT/UPDATE. The caller rolls back.
        raise LocalIdentityMirrorRefused("Could not write the local auth.users row.") from exc
