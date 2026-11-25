#!/usr/bin/env python3
"""Import text-only SAMPLE replies into the local database."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402

REPLIES_PATH = ROOT / "data" / "sample" / "replies.csv"
DEFAULT_DB_PATH = db.DEFAULT_DB_PATH


def load_reply_rows(path: Path = REPLIES_PATH) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames or []
    if fields != ["reply_id", "text"]:
        raise ValueError("replies.csv columns must be exactly reply_id,text")
    if len(rows) != 60:
        raise ValueError(f"replies.csv must contain 60 rows, got {len(rows)}")
    ids = [row.get("reply_id", "").strip() for row in rows]
    if len(set(ids)) != len(ids) or any(re.fullmatch(r"R\d{3}", reply_id) is None for reply_id in ids):
        raise ValueError("replies.csv IDs must be unique R### values")
    if any(not row.get("text", "").strip() for row in rows):
        raise ValueError("replies.csv contains an empty reply")
    return [{"reply_id": row["reply_id"].strip(), "text": row["text"]} for row in rows]


def import_replies(path: Path = REPLIES_PATH, db_path: str | None = None) -> int:
    rows = load_reply_rows(path)
    conn = db.connect(db_path)
    try:
        db.init_db(conn)
        return db.upsert_sample_replies(conn, rows)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=str(REPLIES_PATH), help="text-only reply CSV")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="local Harvey SQLite database")
    args = parser.parse_args(argv)
    try:
        count = import_replies(Path(args.csv), args.db_path)
    except (OSError, ValueError) as exc:
        print(f"reply import failed: {exc}", file=sys.stderr)
        return 2
    print(f"Imported {count} reply records; text was not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
