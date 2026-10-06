import argparse
from datetime import datetime, timezone
from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_engine
from app.security.passwords import hash_password


def bootstrap_platform_admin() -> int:
    email = input("Administrator email: ").strip().lower()
    try:
        normalized_email = str(TypeAdapter(EmailStr).validate_python(email))
    except ValidationError:
        print("Enter a valid email address.")
        return 2

    password = getpass("Password (12-128 characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        print("The passwords do not match.")
        return 2
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        print(str(exc))
        return 2

    with Session(get_engine()) as session:
        with session.begin():
            existing_admin = session.scalar(
                select(User.id).where(User.is_platform_admin.is_(True)).limit(1)
            )
            if existing_admin is not None:
                print("A platform administrator already exists. No changes were made.")
                return 1
            existing = session.scalar(
                select(User.id).where(func.lower(func.btrim(User.email)) == normalized_email)
            )
            if existing is not None:
                print("A user with this email already exists. No changes were made.")
                return 1
            admin = User(
                email=normalized_email,
                password_hash=password_hash,
                email_verified_at=datetime.now(timezone.utc),
                is_platform_admin=True,
            )
            session.add(admin)
            session.flush()

    print(f"Platform administrator created: {normalized_email}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Agentic GRC platform accounts.")
    parser.add_argument(
        "command",
        choices=["bootstrap-admin"],
        help="Create the initial platform administrator.",
    )
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        return bootstrap_platform_admin()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
