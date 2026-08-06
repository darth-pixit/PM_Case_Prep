#!/usr/bin/env python3
"""Extract every user who has given an email — and their emails — from the DB.

Signed-in users live in the `users` table of the app's SQLite database
(written by SkillGraph.link_email when someone finishes Google sign-in or an
email-code login): one row per email, mapping email -> cookie uid. This script
reads that table and joins in each uid's activity from `scores`, so the export
answers both "who gave us an email?" and "how much have they done?".

The database is opened READ-ONLY (SQLite `mode=ro`) — an export must never be
able to mutate production data, even by accident.

Usage:
    # Human-readable table; DB resolved like the app ($PMCP_DB, else ./skill_graph.db)
    python scripts/export_user_emails.py

    # Against the production disk on Render, as CSV
    python scripts/export_user_emails.py --db /data/skill_graph.db --format csv -o users.csv

    # Just the addresses, one per line (paste into a mail tool)
    python scripts/export_user_emails.py --format emails

A note on identity: one person (uid) can legitimately hold several emails —
saved with one, later signed in with another. The export keeps one row per
email (the raw truth) and marks the uid's most recent link as `primary`,
matching SkillGraph.email_for_uid's "the one they signed in with last".
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


def open_readonly(db_path: str | Path) -> sqlite3.Connection:
    """Open the SQLite DB without write access. Fails loudly if it's missing —
    a typo'd path must not quietly create an empty DB and report zero users."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"database not found: {path} — pass --db or set PMCP_DB "
            "(on Render the disk is mounted at /data/skill_graph.db)"
        )
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def fetch_users_with_emails(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """All email->uid links, newest first, enriched with per-uid activity.

    `cases` mirrors SkillGraph.sessions_count (distinct graded sessions in
    `scores`) and `last_active` is the latest graded-case timestamp — both
    empty for someone who signed in but hasn't finished a case yet.
    """
    if not _has_table(conn, "users"):
        return []  # DB predates logins (or wrong file) — nobody has given an email

    if _has_table(conn, "scores"):
        rows = conn.execute(
            "SELECT u.email, u.uid, u.created_at, "
            "       COUNT(DISTINCT s.session_id) AS cases, "
            "       MAX(s.created_at) AS last_active "
            "FROM users u LEFT JOIN scores s ON s.user_id = u.uid "
            "GROUP BY u.email, u.uid, u.created_at "
            "ORDER BY u.created_at DESC, u.rowid DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT email, uid, created_at, 0, NULL FROM users "
            "ORDER BY created_at DESC, rowid DESC"
        ).fetchall()

    users = [
        {
            "email": email,
            "uid": uid,
            "linked_at": linked_at,
            "cases": cases or 0,
            "last_active": last_active,
        }
        for email, uid, linked_at, cases, last_active in rows
    ]

    # Rows arrive in email_for_uid's ordering (created_at DESC, rowid DESC),
    # so the first row seen for a uid is that person's primary email.
    seen_uids: set[str] = set()
    for u in users:
        u["primary"] = u["uid"] not in seen_uids
        seen_uids.add(u["uid"])
    return users


FIELDS = ["email", "uid", "linked_at", "primary", "cases", "last_active"]


def render_table(users: list[dict[str, Any]]) -> str:
    if not users:
        return "No users have given an email yet."
    rows = [FIELDS] + [
        [str(u[f] if u[f] is not None else "-") for f in FIELDS] for u in users
    ]
    widths = [max(len(r[i]) for r in rows) for i in range(len(FIELDS))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(r, widths)).rstrip() for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    lines.append(f"\n{len(users)} email(s) across {len({u['uid'] for u in users})} user(s)")
    return "\n".join(lines)


def render_csv(users: list[dict[str, Any]], out) -> None:
    writer = csv.DictWriter(out, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows({f: u[f] for f in FIELDS} for u in users)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--db",
        default=os.environ.get("PMCP_DB", "skill_graph.db"),
        help="SQLite DB path (default: $PMCP_DB, else ./skill_graph.db)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "csv", "json", "emails"],
        default="table",
        help="table (default), csv, json, or emails (one address per line)",
    )
    parser.add_argument(
        "-o", "--output", default=None, help="write to this file instead of stdout"
    )
    args = parser.parse_args(argv)

    try:
        conn = open_readonly(args.db)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        users = fetch_users_with_emails(conn)
    finally:
        conn.close()

    out = open(args.output, "w", newline="") if args.output else sys.stdout
    try:
        if args.format == "table":
            print(render_table(users), file=out)
        elif args.format == "csv":
            render_csv(users, out)
        elif args.format == "json":
            json.dump(users, out, indent=2)
            out.write("\n")
        elif args.format == "emails":
            for u in users:
                print(u["email"], file=out)
    finally:
        if args.output:
            out.close()
    if args.output:
        print(f"wrote {len(users)} row(s) to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
