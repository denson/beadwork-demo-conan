#!/usr/bin/env python
"""
Extend conan.db with the rest of IMDb that's relevant to our Conan-guests.

For each of the 7,006 people already in the hypergraph, pull their full
filmography (every credit OUTSIDE Conan's own shows). For each title in
that filmography, pull metadata + ratings. This is what lets the agent
answer "what was Tom Hanks promoting when he came on Conan in 1998?"

Adds two things to conan.db:
  - WORK NODES (kind='work') — every film/TV/short/etc. our guests were in
  - CAST HYPEREDGES (kind='cast') — work + people-with-roles

Personal-use IMDb data; outputs of this script live on PRINCIPAL's
machine. The DB itself (which contains only derived facts — IDs, names,
years, ratings, all individually findable in many sources) is what ships
in the public demo repo.

Runtime: ~6-10 min (one slow pass over the 730MB title.principals file,
one moderate pass over the 212MB title.basics file, one trivial pass over
title.ratings).
"""
import csv
import gzip
import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(2**24)

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "conan.db"
IMDB_DIR = Path(r"D:\team_coco_videos\coco_superfan\imdb_datasets")
CACHE_DIR = Path(r"D:\team_coco_videos\coco_superfan\conan_extraction")


def open_tsv(name):
    return gzip.open(IMDB_DIR / name, "rt", encoding="utf-8", newline="")


def n(v):
    return None if v == r"\N" else v


# ---------------------------------------------------------------------------
# Phase 1: read the current state of conan.db
# ---------------------------------------------------------------------------
def phase1_read_state(conn):
    print("[Phase 1] Reading current conan.db state ...")
    people = {row[0] for row in conn.execute("SELECT id FROM nodes WHERE kind='person'")}
    eps = {row[0] for row in conn.execute("SELECT id FROM nodes WHERE kind='episode'")}
    shows = {row[0] for row in conn.execute("SELECT id FROM nodes WHERE kind='show'")}
    # knownForTitles per person (from data_json)
    known_for_tconsts = set()
    for nconst, data_json in conn.execute("SELECT id, data_json FROM nodes WHERE kind='person'"):
        try:
            data = json.loads(data_json or "{}")
        except json.JSONDecodeError:
            continue
        kft = data.get("knownForTitles")
        if kft and kft != r"\N":
            for tc in kft.split(","):
                if tc.startswith("tt"):
                    known_for_tconsts.add(tc)
    print(
        f"      people={len(people):,}  conan_episodes={len(eps):,}  "
        f"conan_shows={len(shows):,}  knownForTitles_unique={len(known_for_tconsts):,}"
    )
    return people, eps | shows, known_for_tconsts


# ---------------------------------------------------------------------------
# Phase 2: stream title.principals, keep rows where (nconst is a Conan guest)
# AND (tconst is NOT a Conan title we already have)
# ---------------------------------------------------------------------------
PRINCIPALS_CACHE = CACHE_DIR / "guest_filmography_principals.json"


def phase2_filmography_principals(guest_nconsts, conan_tconsts):
    if PRINCIPALS_CACHE.exists():
        print(f"[Phase 2] Loading cached {PRINCIPALS_CACHE.name} ...")
        rows = json.loads(PRINCIPALS_CACHE.read_text(encoding="utf-8"))
        print(f"      cached: {len(rows):,} principal records")
        return rows

    print(
        f"[Phase 2] Streaming title.principals for {len(guest_nconsts):,} guests "
        f"(skip {len(conan_tconsts):,} Conan-titles) ..."
    )
    t0 = time.time()
    rows = []
    n_matched = 0
    with open_tsv("title.principals.tsv.gz") as f:
        r = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        for i, row in enumerate(r, 1):
            if i % 5_000_000 == 0:
                print(f"  ...{i:,} rows scanned, {n_matched:,} kept ({time.time()-t0:.0f}s)")
            if row["nconst"] not in guest_nconsts:
                continue
            if row["tconst"] in conan_tconsts:
                continue
            rows.append(row)
            n_matched += 1
    print(f"[Phase 2] Done. {n_matched:,} non-Conan credits in {time.time()-t0:.0f}s.")
    PRINCIPALS_CACHE.write_text(json.dumps(rows), encoding="utf-8")
    print(f"      cached to {PRINCIPALS_CACHE}")
    return rows


# ---------------------------------------------------------------------------
# Phase 3: pull title.basics for every unique tconst referenced
# (filmography titles + knownForTitles)
# ---------------------------------------------------------------------------
BASICS_CACHE = CACHE_DIR / "guest_filmography_basics.json"


def phase3_work_metadata(wanted_tconsts):
    if BASICS_CACHE.exists():
        print(f"[Phase 3] Loading cached {BASICS_CACHE.name} ...")
        meta = json.loads(BASICS_CACHE.read_text(encoding="utf-8"))
        print(f"      cached: {len(meta):,} work-metadata records")
        return meta

    print(f"[Phase 3] Streaming title.basics for {len(wanted_tconsts):,} tconsts ...")
    t0 = time.time()
    meta = {}
    with open_tsv("title.basics.tsv.gz") as f:
        r = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        for i, row in enumerate(r, 1):
            if i % 2_000_000 == 0:
                print(f"  ...{i:,} rows scanned, {len(meta):,} matched ({time.time()-t0:.0f}s)")
            if row["tconst"] in wanted_tconsts:
                meta[row["tconst"]] = row
                if len(meta) == len(wanted_tconsts):
                    print("  All matched, early exit.")
                    break
    print(f"[Phase 3] Done. {len(meta):,}/{len(wanted_tconsts):,} in {time.time()-t0:.0f}s.")
    BASICS_CACHE.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print(f"      cached to {BASICS_CACHE}")
    return meta


# ---------------------------------------------------------------------------
# Phase 4: ratings for those tconsts
# ---------------------------------------------------------------------------
RATINGS_CACHE = CACHE_DIR / "guest_filmography_ratings.json"


def phase4_work_ratings(wanted_tconsts):
    if RATINGS_CACHE.exists():
        print(f"[Phase 4] Loading cached {RATINGS_CACHE.name} ...")
        ratings = json.loads(RATINGS_CACHE.read_text(encoding="utf-8"))
        print(f"      cached: {len(ratings):,} ratings")
        return ratings

    print(f"[Phase 4] Streaming title.ratings for {len(wanted_tconsts):,} tconsts ...")
    t0 = time.time()
    ratings = {}
    with open_tsv("title.ratings.tsv.gz") as f:
        r = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        for row in r:
            if row["tconst"] in wanted_tconsts:
                ratings[row["tconst"]] = row
    print(f"[Phase 4] Done. {len(ratings):,} rated works in {time.time()-t0:.0f}s.")
    RATINGS_CACHE.write_text(json.dumps(ratings), encoding="utf-8")
    return ratings


# ---------------------------------------------------------------------------
# Phase 5: load into conan.db as work nodes + cast hyperedges
# ---------------------------------------------------------------------------
def phase5_load_into_db(conn, principals, basics, ratings, known_for_tconsts):
    print("[Phase 5] Loading work nodes + cast hyperedges into conan.db ...")

    # --- work nodes
    inserted_works = 0
    for tc, row in basics.items():
        rating = ratings.get(tc, {})
        data = {
            "titleType": row.get("titleType"),
            "originalTitle": n(row.get("originalTitle")),
            "startYear": n(row.get("startYear")),
            "endYear": n(row.get("endYear")),
            "runtimeMinutes": n(row.get("runtimeMinutes")),
            "genres": n(row.get("genres")),
            "isAdult": row.get("isAdult"),
            "averageRating": rating.get("averageRating"),
            "numVotes": rating.get("numVotes"),
            "is_known_for_someone": tc in known_for_tconsts,
        }
        conn.execute(
            "INSERT OR REPLACE INTO nodes (id, kind, name, canonical_url, data_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                tc,
                "work",
                row.get("primaryTitle") or "(no title)",
                f"https://www.imdb.com/title/{tc}/",
                json.dumps(data, ensure_ascii=False),
            ),
        )
        # alias the work's primary title
        conn.execute(
            "INSERT OR IGNORE INTO name_aliases (alias, node_id) VALUES (?, ?)",
            (row.get("primaryTitle") or "", tc),
        )
        # alias the original title if different
        orig = row.get("originalTitle")
        if orig and orig != row.get("primaryTitle"):
            conn.execute(
                "INSERT OR IGNORE INTO name_aliases (alias, node_id) VALUES (?, ?)",
                (orig, tc),
            )
        inserted_works += 1
    conn.commit()
    print(f"      inserted {inserted_works:,} work nodes")

    # --- cast hyperedges (one per work, with all people-in-roles as participants)
    # Group principals by tconst
    by_work = defaultdict(list)
    for p in principals:
        by_work[p["tconst"]].append(p)

    edges_created = 0
    participants_created = 0
    skipped_archive = 0
    skipped_dupes = 0
    for tc, plist in by_work.items():
        edge_id = f"cast-{tc}"
        edge_data = {"work_tconst": tc}
        date = None
        meta = basics.get(tc, {})
        date = n(meta.get("startYear"))
        try:
            conn.execute(
                "INSERT INTO edges (id, kind, date, data_json) VALUES (?, ?, ?, ?)",
                (edge_id, "cast", date, json.dumps(edge_data, ensure_ascii=False)),
            )
            edges_created += 1
        except sqlite3.IntegrityError:
            # already exists; skip
            continue
        # the work itself participates as 'work'
        conn.execute(
            "INSERT OR IGNORE INTO participants (edge_id, node_id, role) VALUES (?, ?, ?)",
            (edge_id, tc, "work"),
        )
        participants_created += 1
        for p in plist:
            cat = p.get("category", "")
            if cat == "archive_footage":
                skipped_archive += 1
                continue
            try:
                conn.execute(
                    "INSERT INTO participants (edge_id, node_id, role) VALUES (?, ?, ?)",
                    (edge_id, p["nconst"], cat),
                )
                participants_created += 1
            except sqlite3.IntegrityError:
                skipped_dupes += 1
    conn.commit()
    print(
        f"      inserted {edges_created:,} cast edges, "
        f"{participants_created:,} participant rows "
        f"(skipped {skipped_archive:,} archive_footage, {skipped_dupes:,} dupes)"
    )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def verify(conn):
    print("\n[verify] post-extension state:")
    cur = conn.cursor()

    cur.execute("SELECT kind, COUNT(*) FROM nodes GROUP BY kind ORDER BY kind")
    print("  nodes by kind:")
    for kind, count in cur.fetchall():
        print(f"    {kind}: {count:,}")

    cur.execute("SELECT kind, COUNT(*) FROM edges GROUP BY kind ORDER BY kind")
    print("  edges by kind:")
    for kind, count in cur.fetchall():
        print(f"    {kind}: {count:,}")

    # Sample query: Tom Hanks's filmography around 1998
    print("\n  Tom Hanks's filmography near 1998 (within 2 years either side):")
    cur.execute(
        """SELECT n.name, n.data_json
           FROM participants p
           JOIN edges e ON e.id = p.edge_id AND e.kind = 'cast'
           JOIN nodes n ON n.id = (
             SELECT node_id FROM participants
             WHERE edge_id = e.id AND role = 'work' LIMIT 1
           )
           WHERE p.node_id = 'nm0000158'
             AND p.role IN ('actor', 'actress', 'self')
             AND CAST(e.date AS INTEGER) BETWEEN 1996 AND 2000
           ORDER BY e.date""",
    )
    for name, data_json in cur.fetchall()[:10]:
        try:
            data = json.loads(data_json or "{}")
            year = data.get("startYear")
            tt = data.get("titleType")
        except json.JSONDecodeError:
            year = "?"; tt = "?"
        print(f"    {year}  [{tt:<10}]  {name}")

    # Sample: Marc Maron's filmography
    print("\n  Marc Maron's 5 most-recent works:")
    cur.execute(
        """SELECT n.name, n.canonical_url, n.data_json
           FROM participants p
           JOIN edges e ON e.id = p.edge_id AND e.kind = 'cast'
           JOIN nodes n ON n.id = (
             SELECT node_id FROM participants
             WHERE edge_id = e.id AND role = 'work' LIMIT 1
           )
           WHERE p.node_id = 'nm0549505'
           ORDER BY e.date DESC LIMIT 5"""
    )
    for name, url, data_json in cur.fetchall():
        try:
            data = json.loads(data_json or "{}")
            year = data.get("startYear")
        except json.JSONDecodeError:
            year = "?"
        print(f"    {year}  {name}  {url}")


# ---------------------------------------------------------------------------
def main():
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} not found. Run scripts/build_hypergraph.py first.", file=sys.stderr)
        sys.exit(1)
    CACHE_DIR.mkdir(exist_ok=True, parents=True)

    overall_t0 = time.time()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        people, conan_tconsts, known_for = phase1_read_state(conn)
        principals = phase2_filmography_principals(people, conan_tconsts)
        # Union of (tconsts in principals) + (knownForTitles tconsts) - (Conan titles we already have)
        wanted_tconsts = {p["tconst"] for p in principals} | known_for
        wanted_tconsts -= conan_tconsts
        basics = phase3_work_metadata(wanted_tconsts)
        ratings = phase4_work_ratings(wanted_tconsts)
        phase5_load_into_db(conn, principals, basics, ratings, known_for)
        verify(conn)
    finally:
        conn.close()
    print(f"\nDone in {time.time()-overall_t0:.0f}s. DB at {DB_PATH} ({DB_PATH.stat().st_size/1024/1024:.2f} MB).")


if __name__ == "__main__":
    main()
