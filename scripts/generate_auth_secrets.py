#!/usr/bin/env python3
"""
Generate the secrets required to bootstrap admin auth.

Outputs:
  - ADMIN_PASSWORD_HASH : bcrypt hash of the admin password
  - JWT_SECRET          : 64 random bytes, base64-encoded

Usage:
  uv run python scripts/generate_auth_secrets.py
  uv run python scripts/generate_auth_secrets.py --password 's3cret'
  uv run python scripts/generate_auth_secrets.py --hash-only --password 's3cret'
  uv run python scripts/generate_auth_secrets.py --secret-only

By default the password is read interactively (hidden) and confirmed.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import secrets
import sys

import bcrypt


def _read_password_interactive() -> str:
    while True:
        pw = getpass.getpass("admin password: ")
        if not pw:
            print("password cannot be empty.", file=sys.stderr)
            continue
        confirm = getpass.getpass("confirm password: ")
        if pw != confirm:
            print("passwords do not match. try again.\n", file=sys.stderr)
            continue
        return pw


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _generate_jwt_secret(num_bytes: int = 64) -> str:
    raw = secrets.token_bytes(num_bytes)
    return base64.b64encode(raw).decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--password",
        help="Admin password in plaintext. If omitted, prompts interactively.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--hash-only",
        action="store_true",
        help="Print only the password hash (no JWT secret).",
    )
    mode.add_argument(
        "--secret-only",
        action="store_true",
        help="Print only the JWT secret (no password hash).",
    )
    parser.add_argument(
        "--env-style",
        action="store_true",
        default=True,
        help="Format output as KEY='value' env lines (default).",
    )
    parser.add_argument(
        "--bare",
        dest="env_style",
        action="store_false",
        help="Print raw values without KEY= prefix.",
    )

    args = parser.parse_args()

    password_hash: str | None = None
    jwt_secret: str | None = None

    if not args.secret_only:
        password = args.password or _read_password_interactive()
        password_hash = _hash_password(password)

    if not args.hash_only:
        jwt_secret = _generate_jwt_secret()

    if args.env_style:
        print()
        print("# Copy these into your backend .env (root or api/.env):")
        if password_hash is not None:
            print(f"ADMIN_PASSWORD_HASH='{password_hash}'")
        if jwt_secret is not None:
            print(f"JWT_SECRET='{jwt_secret}'")
        print()
    else:
        if password_hash is not None:
            print(password_hash)
        if jwt_secret is not None:
            print(jwt_secret)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
