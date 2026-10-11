import argparse
from uuid import UUID

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_engine


def bootstrap_platform_admin(user_id: UUID, email: EmailStr) -> int:
    normalized_email = str(email).strip().lower()
    with Session(get_engine()) as session:
        with session.begin():
            auth_user = session.execute(
                text(
                    "SELECT email, email_confirmed_at FROM auth.users WHERE id = :user_id"
                ),
                {"user_id": user_id},
            ).one_or_none()
            if auth_user is None or auth_user.email_confirmed_at is None:
                print("The Supabase Auth user must exist and have a confirmed email.")
                return 1
            if str(auth_user.email).strip().lower() != normalized_email:
                print("The supplied email does not match the Supabase Auth user.")
                return 1

            existing_admin = session.scalar(
                select(User.id).where(User.is_platform_admin.is_(True)).limit(1)
            )
            if existing_admin is not None:
                print("A platform administrator already exists. No changes were made.")
                return 1

            admin = session.get(User, user_id)
            if admin is None:
                conflicting_user = session.scalar(
                    select(User.id).where(func.lower(func.btrim(User.email)) == normalized_email)
                )
                if conflicting_user is not None:
                    print("A profile with this email is linked to another Auth identity.")
                    return 1
                admin = User(id=user_id, email=normalized_email)
                session.add(admin)
            admin.is_platform_admin = True

    print(f"Platform administrator profile provisioned: {normalized_email}")
    return 0


def _email(value: str) -> EmailStr:
    try:
        return TypeAdapter(EmailStr).validate_python(value.strip())
    except ValidationError as exc:
        raise argparse.ArgumentTypeError("Enter a valid email address.") from exc


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Enter the Supabase Auth user's UUID.") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Agentic GRC platform profiles.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    admin_parser = subparsers.add_parser(
        "bootstrap-admin",
        help="Link an existing confirmed Supabase Auth user to the initial platform admin profile.",
    )
    admin_parser.add_argument("--user-id", required=True, type=_uuid)
    admin_parser.add_argument("--email", required=True, type=_email)
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        return bootstrap_platform_admin(args.user_id, args.email)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
