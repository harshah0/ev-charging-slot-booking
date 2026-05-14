#!/usr/bin/env python3
"""Simple requirements validation for production readiness.

Checks that critical production packages are present in requirements.txt.
"""
import sys
from pathlib import Path

REQUIRED = {"gunicorn", "psycopg2-binary", "whitenoise"}


def main():
    root = Path(__file__).resolve().parents[1]
    req = root / "requirements.txt"
    if not req.exists():
        print("requirements.txt not found", file=sys.stderr)
        return 2

    text = req.read_text()
    present = set()
    for line in text.splitlines():
        pkg = line.strip().split("==")[0].lower()
        if pkg:
            present.add(pkg)

    missing = [p for p in REQUIRED if p not in present]
    if missing:
        print("Missing production packages:", ", ".join(missing))
        return 1

    print("All required production packages present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
