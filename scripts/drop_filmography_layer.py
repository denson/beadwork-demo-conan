#!/usr/bin/env python
"""
One-shot: drop the work-nodes + cast-edges layer from conan.db.

Reverts the DB to the "Conan-shows only" v1 state (~12 MB). The full
filmography data stays cached on PRINCIPAL's machine at
D:\\team_coco_videos\\coco_superfan\\conan_extraction\\guest_filmography_*.json
for QA / re-load if we ever want it back.

Rationale: filmography data lives on IMDb. The conan-superfan agent looks
it up on-the-fly via Chrome MCP when needed, instead of cached in the DB
(which would blow past GitHub's 100 MB single-file cap).
"""
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "conan.db"


def main():
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} not found.", file=sys.stderr)
        sys.exit(1)
    size_before = DB_PATH.stat().st_size / 1024 / 1024
    print(f"Before:  {DB_PATH} ({size_before:.2f} MB)")

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Count what we're about to drop
    (n_works,) = cur.execute("SELECT COUNT(*) FROM nodes WHERE kind='work'").fetchone()
    (n_cast,) = cur.execute("SELECT COUNT(*) FROM edges WHERE kind='cast'").fetchone()
    (n_part,) = cur.execute(
        "SELECT COUNT(*) FROM participants WHERE edge_id IN (SELECT id FROM edges WHERE kind='cast')"
    ).fetchone()
    (n_aliases,) = cur.execute(
        "SELECT COUNT(*) FROM name_aliases WHERE node_id IN (SELECT id FROM nodes WHERE kind='work')"
    ).fetchone()
    print(
        f"Dropping: {n_works:,} work nodes / {n_cast:,} cast edges / "
        f"{n_part:,} participant rows / {n_aliases:,} aliases ..."
    )

    cur.execute("DELETE FROM participants WHERE edge_id IN (SELECT id FROM edges WHERE kind='cast')")
    cur.execute("DELETE FROM edges WHERE kind='cast'")
    cur.execute("DELETE FROM name_aliases WHERE node_id IN (SELECT id FROM nodes WHERE kind='work')")
    cur.execute("DELETE FROM nodes WHERE kind='work'")
    conn.commit()

    print("Running VACUUM to reclaim space ...")
    cur.execute("VACUUM")
    conn.commit()
    conn.close()

    size_after = DB_PATH.stat().st_size / 1024 / 1024
    print(f"After:   {DB_PATH} ({size_after:.2f} MB)")
    print(f"Saved {size_before - size_after:.2f} MB")

    # Sanity-check final state
    conn = sqlite3.connect(str(DB_PATH))
    print("\nFinal node/edge counts:")
    for kind, n in conn.execute("SELECT kind, COUNT(*) FROM nodes GROUP BY kind ORDER BY kind"):
        print(f"  nodes.{kind}: {n:,}")
    for kind, n in conn.execute("SELECT kind, COUNT(*) FROM edges GROUP BY kind ORDER BY kind"):
        print(f"  edges.{kind}: {n:,}")
    (parts,) = conn.execute("SELECT COUNT(*) FROM participants").fetchone()
    print(f"  participants: {parts:,}")
    conn.close()


if __name__ == "__main__":
    main()
