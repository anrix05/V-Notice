import argparse
import getpass
import sys

import config
from security import validate_password_strength
from storage import storage


def cmd_create_admin(args):
    email = str(args.email or "").strip().lower()
    name = str(args.name or "").strip()
    if not email or "@" not in email:
        print("Error: --email must be a valid email address.", file=sys.stderr)
        sys.exit(1)
    if not name:
        print("Error: --name is required.", file=sys.stderr)
        sys.exit(1)

    existing = storage.get_user(email)
    if existing:
        print(f"Error: User '{email}' already exists.", file=sys.stderr)
        sys.exit(1)

    if args.invite:
        user = storage.create_user(
            email=email,
            name=name,
            role="admin",
            departments=["ALL"],
            can_post_college_wide=True,
            can_post_urgent=True,
            status="invited",
        )
        token, _ = storage.create_invite(
            user_id=user["id"],
            purpose="invite",
            expires_hours=getattr(config, "INVITE_EXPIRY_HOURS", 72),
            created_by=None,
        )
        base_url = getattr(config, "PUBLIC_BASE_URL", "") or f"http://localhost:{config.ADMIN_PORT}"
        storage.record_audit("cli", "USER_INVITED", str(user["id"]), f"CLI invited admin {email}")
        print(f"Admin invite created for {email}:")
        print(f"{base_url.rstrip('/')}/invite/{token}")
        return

    pw1 = getpass.getpass("Password (min 12 chars): ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        print("Error: Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    ok, err = validate_password_strength(pw1)
    if not ok:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    user = storage.create_user(
        email=email,
        name=name,
        password=pw1,
        role="admin",
        departments=["ALL"],
        can_post_college_wide=True,
        can_post_urgent=True,
        status="active",
    )
    storage.record_audit("cli", "CREATE_ADMIN", str(user["id"]), f"CLI created admin {email}")
    print(f"Admin account created: {user['email']} (id={user['id']})")


def main():
    parser = argparse.ArgumentParser(description="V Notice management CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("create-admin", help="Create an admin account")
    p_admin.add_argument("--email", required=True, help="Admin email address")
    p_admin.add_argument("--name", required=True, help="Admin display name")
    p_admin.add_argument("--invite", action="store_true", help="Print an invite link instead of prompting for a password")
    p_admin.set_defaults(func=cmd_create_admin)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

