#!/usr/bin/env python3
"""Set the passphrase for the coming-soon gate.

The site is served as static files, so a JavaScript check alone would be
theatre: anyone could read the real page out of the source. Instead the
passphrase *is* the address. One PBKDF2 derivation produces two independent
halves:

    verifier  the gate compares what you typed against this, so a wrong
              passphrase fails locally and quietly — no request, no 404, no
              oracle telling an attacker they were close
    token     the filename the real page lives under, e.g. 7f3a….html

So the real page is not linked from anywhere, not named in the gate's source,
and cannot be reached by reading index.html. What protects it is the entropy of
the passphrase, stretched by PBKDF2 so that guessing at the verifier is slow.

Usage:

    python3 tools/gate.py set 'some passphrase'   # rotate; renames the page
    python3 tools/gate.py show                    # current config
    python3 tools/gate.py check 'some passphrase' # does it open the gate?

Caveats worth knowing before relying on it:

  * The filename is committed to this repository. If the repository is public,
    the address is public and only the coming-soon page's obscurity remains —
    rotate to a fresh passphrase at deploy time, or keep the repo private.
  * A static host with directory listing enabled defeats it entirely. Check.
  * `crypto.subtle` needs a secure context: https, or localhost while testing.
  * For real access control, put the site behind HTTP basic auth or an identity
    proxy (Cloudflare Access, oauth2-proxy). This gate is a locked door on a
    building with no walls: it keeps the page out of sight, not out of reach.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
GATE_JS = SITE / "gate.js"

ITERATIONS = 250_000
VERIFIER_BYTES = 16
TOKEN_BYTES = 8

CONFIG_RE = re.compile(
    r"(/\* gate:config \*/\s*var CONFIG = )(\{.*?\})(;)", re.DOTALL
)


def derive(passphrase: str, salt_hex: str) -> tuple[str, str]:
    """Return (verifier, token) — two independent halves of one derivation."""
    bits = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        bytes.fromhex(salt_hex),
        ITERATIONS,
        dklen=VERIFIER_BYTES + TOKEN_BYTES,
    )
    return bits[:VERIFIER_BYTES].hex(), bits[VERIFIER_BYTES:].hex()


def read_config() -> dict:
    match = CONFIG_RE.search(GATE_JS.read_text(encoding="utf-8"))
    if not match:
        sys.exit("gate.js: no /* gate:config */ block found")
    return json.loads(match.group(2))


def write_config(config: dict) -> None:
    source = GATE_JS.read_text(encoding="utf-8")
    rendered = json.dumps(config, indent=4).replace("\n", "\n  ")
    GATE_JS.write_text(CONFIG_RE.sub(lambda m: m.group(1) + rendered + m.group(3),
                                     source, count=1), encoding="utf-8")


def cmd_set(passphrase: str, page: str | None) -> None:
    if len(passphrase) < 6:
        sys.exit("passphrase too short — at least 6 characters, and prefer more")

    old = read_config()
    current_page = SITE / (page or old.get("target") or "")
    if not current_page.is_file():
        sys.exit(
            f"cannot find the page to rename: {current_page.name or '(unset)'}\n"
            "pass it explicitly: gate.py set '<passphrase>' --page <file.html>"
        )

    salt = secrets.token_hex(16)
    verifier, token = derive(passphrase, salt)
    target = f"{token}.html"

    if current_page.name != target:
        os.rename(current_page, SITE / target)

    write_config(
        {
            "salt": salt,
            "iterations": ITERATIONS,
            "length": len(passphrase),
            "verifier": verifier,
            "target": target,
        }
    )

    print(f"passphrase set ({len(passphrase)} characters)")
    print(f"  page   {current_page.name} -> {target}")
    print(f"  open   https://<host>/{target}")
    print(f"  or     https://<host>/#{passphrase}")
    print("\nremember to commit both gate.js and the renamed page.")


def cmd_show() -> None:
    config = read_config()
    print(f"salt        {config['salt']}")
    print(f"iterations  {config['iterations']}")
    print(f"length      {config['length']} characters")
    print(f"verifier    {config['verifier']}")
    print(f"target      {config['target']}"
          f"{'' if (SITE / config['target']).is_file() else '   (MISSING)'}")


def cmd_check(passphrase: str) -> None:
    config = read_config()
    verifier, token = derive(passphrase, config["salt"])
    ok = verifier == config["verifier"] and f"{token}.html" == config["target"]
    print("opens the gate" if ok else "does not open the gate")
    sys.exit(0 if ok else 1)


def main(argv: list[str]) -> None:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return
    command, rest = argv[0], argv[1:]

    if command == "set":
        if not rest:
            sys.exit("usage: gate.py set '<passphrase>' [--page <file.html>]")
        page = None
        if "--page" in rest:
            index = rest.index("--page")
            page = rest[index + 1] if len(rest) > index + 1 else None
            rest = rest[:index]
        cmd_set(" ".join(rest), page)
    elif command == "show":
        cmd_show()
    elif command == "check":
        if not rest:
            sys.exit("usage: gate.py check '<passphrase>'")
        cmd_check(" ".join(rest))
    else:
        sys.exit(f"unknown command: {command}")


if __name__ == "__main__":
    main(sys.argv[1:])
