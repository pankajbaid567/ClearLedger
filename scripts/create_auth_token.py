"""Create a private local bearer file and its configured identity without logging credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument(
        "--role", choices=["viewer", "operator", "reviewer", "admin"], required=True
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,160}", args.subject):
        parser.error("subject must contain 1–160 letters, digits, dots, @, underscores or hyphens")
    directory = args.output_dir or Path.home() / ".config" / "clearledger" / args.subject
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    bearer_path = directory / "access.bearer-token"
    identity_path = directory / "auth-tokens.json"
    if bearer_path.exists() or identity_path.exists():
        parser.error("output exists; choose a fresh directory for a new identity or rotation")
    token = secrets.token_urlsafe(32)
    identity = [
        {
            "subject": args.subject,
            "role": args.role,
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        }
    ]
    for path, content in (
        (bearer_path, token + "\n"),
        (identity_path, json.dumps(identity, indent=2) + "\n"),
    ):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
    print(f"Private bearer file: {bearer_path}")
    print(f"Server identity configuration: {identity_path}")
    print("Keep the bearer private. Set AUTH_TOKENS to the identity JSON, never the bearer.")


if __name__ == "__main__":
    main()
