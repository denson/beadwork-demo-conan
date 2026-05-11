#!/usr/bin/env python
"""
Build the Conan corpus hypergraph SQLite DB from the local IMDb extraction JSONs.

INPUT:
  D:\\team_coco_videos\\coco_superfan\\conan_extraction\\
    parent_shows.json
    episodes_raw.json
    episode_metadata.json
    episode_principals.json
    name_map.json
    ratings.json

OUTPUT:
  beadwork-demo-conan/data/conan.db

Design: store the GRAPH (entities + relationships + canonical IMDb URLs).
Do NOT duplicate IMDb's content. When the agent talks about a person or
episode, it opens the canonical_url in the user's browser. The DB holds
the structure; IMDb holds the substance.

Runtime: a few seconds. Reads ~14MB JSON, writes ~5-10MB SQLite.
"""
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
IMDB_DIR = Path(r"D:\team_coco_videos\coco_superfan\conan_extraction")
OUT_DB = REPO_ROOT / "data" / "conan.db"
SCHEMA_SQL = REPO_ROOT / "data" / "schema.sql"


def n(v):
    """IMDb null marker is the literal 2 chars  \  N."""
    return None if v == r"\N" else v


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_extracts():
    print("[1/6] Loading IMDb extraction JSONs ...")
    parents = json.loads((IMDB_DIR / "parent_shows.json").read_text(encoding="utf-8"))
    episodes_raw = json.loads((IMDB_DIR / "episodes_raw.json").read_text(encoding="utf-8"))
    episode_meta = json.loads((IMDB_DIR / "episode_metadata.json").read_text(encoding="utf-8"))
    principals = json.loads((IMDB_DIR / "episode_principals.json").read_text(encoding="utf-8"))
    names = json.loads((IMDB_DIR / "name_map.json").read_text(encoding="utf-8"))
    ratings = json.loads((IMDB_DIR / "ratings.json").read_text(encoding="utf-8"))
    print(
        f"      parents={len(parents)} "
        f"episodes_raw={sum(len(eps) for eps in episodes_raw.values())} "
        f"episode_meta={len(episode_meta)} "
        f"principals_eps={len(principals)} "
        f"names={len(names)} "
        f"ratings={len(ratings)}"
    )
    return parents, episodes_raw, episode_meta, principals, names, ratings


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def init_db():
    if OUT_DB.exists():
        OUT_DB.unlink()
    conn = sqlite3.connect(str(OUT_DB))
    conn.execute("PRAGMA foreign_keys = ON;")
    print("[2/6] Applying schema ...")
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Populate nodes
# ---------------------------------------------------------------------------
def insert_node(conn, node_id, kind, name, canonical_url, data):
    conn.execute(
        "INSERT OR REPLACE INTO nodes (id, kind, name, canonical_url, data_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (node_id, kind, name, canonical_url, json.dumps(data, ensure_ascii=False)),
    )
    conn.execute(
        "INSERT OR IGNORE INTO name_aliases (alias, node_id) VALUES (?, ?)",
        (name, node_id),
    )


def populate_shows(conn, parents):
    print("[3/6] Inserting show nodes ...")
    for p in parents:
        tc = p["tconst"]
        data = {
            "startYear": n(p.get("startYear")),
            "endYear": n(p.get("endYear")),
            "genres": n(p.get("genres")),
            "titleType": p.get("titleType"),
        }
        insert_node(
            conn,
            tc,
            "show",
            p["primaryTitle"],
            f"https://www.imdb.com/title/{tc}/",
            data,
        )
        # Original title as alt-alias if it differs
        orig = p.get("originalTitle")
        if orig and orig != p["primaryTitle"]:
            conn.execute(
                "INSERT OR IGNORE INTO name_aliases (alias, node_id) VALUES (?, ?)",
                (orig, tc),
            )
    conn.commit()


def populate_episodes(conn, episode_meta, episodes_raw, ratings):
    print("[4/6] Inserting episode nodes ...")
    # Build {episode_tconst: (parent_tconst, season, episode_number)}
    parent_of = {}
    season_episode = {}
    for parent_tc, eps in episodes_raw.items():
        for ep in eps:
            parent_of[ep["tconst"]] = parent_tc
            season_episode[ep["tconst"]] = (
                n(ep.get("seasonNumber")),
                n(ep.get("episodeNumber")),
            )

    inserted = 0
    for tc, meta in episode_meta.items():
        rating = ratings.get(tc, {})
        s, e = season_episode.get(tc, (None, None))
        data = {
            "parent": parent_of.get(tc),
            "season": s,
            "episode": e,
            "year": n(meta.get("startYear")),
            "runtimeMinutes": n(meta.get("runtimeMinutes")),
            "genres": n(meta.get("genres")),
            "averageRating": rating.get("averageRating"),
            "numVotes": rating.get("numVotes"),
        }
        name = meta.get("primaryTitle") or "(no title)"
        insert_node(
            conn,
            tc,
            "episode",
            name,
            f"https://www.imdb.com/title/{tc}/",
            data,
        )
        inserted += 1
    conn.commit()
    print(f"      inserted {inserted:,} episode nodes")


def populate_people(conn, names):
    print("[5/6] Inserting person nodes ...")
    for nconst, info in names.items():
        data = {
            "birthYear": n(info.get("birthYear")),
            "deathYear": n(info.get("deathYear")),
            "primaryProfession": n(info.get("primaryProfession")),
            "knownForTitles": n(info.get("knownForTitles")),
        }
        insert_node(
            conn,
            nconst,
            "person",
            info.get("primaryName") or "(unknown)",
            f"https://www.imdb.com/name/{nconst}/",
            data,
        )
    conn.commit()
    print(f"      inserted {len(names):,} person nodes")


# ---------------------------------------------------------------------------
# Hyperedges: one appearance edge per episode, connecting venue + participants
# ---------------------------------------------------------------------------
def _classify_role(category: str, characters: str | None) -> str:
    """Map (category, characters-string) onto a hyperedge role."""
    chars = (characters or "").lower()
    if category == "self":
        # Conan and the on-camera people. The 'characters' field carries the
        # role hint in talk-show data — 'Self - Host', 'Self - Co-Host', etc.
        if "co-host" in chars or "co host" in chars:
            return "cohost"
        if "host" in chars:
            return "host"
        if "announcer" in chars:
            return "announcer"
        if "musical guest" in chars or "musical-guest" in chars:
            return "musical_guest"
        if "bandleader" in chars or "band leader" in chars:
            return "bandleader"
        if "guest" in chars:
            return "guest"
        if "band" in chars or "featuring" in chars:
            return "band"
        return "self"  # fallback for un-roled self credits
    # Crew categories pass through verbatim
    return category


def populate_appearances(conn, principals, episode_meta):
    print("[6/6] Building appearance hyperedges + participants ...")
    year_of = {tc: n(meta.get("startYear")) for tc, meta in episode_meta.items()}

    edges_count = 0
    pa_count = 0
    skipped_archive = 0
    skipped_dupes = 0

    for ep_tc, plist in principals.items():
        # One appearance hyperedge per episode
        edge_id = f"appear-{ep_tc}"
        date = year_of.get(ep_tc)
        edge_data = {"episode_tconst": ep_tc}
        conn.execute(
            "INSERT INTO edges (id, kind, date, data_json) VALUES (?, ?, ?, ?)",
            (edge_id, "appearance", date, json.dumps(edge_data, ensure_ascii=False)),
        )
        edges_count += 1

        # The episode itself participates as 'venue'
        conn.execute(
            "INSERT OR IGNORE INTO participants (edge_id, node_id, role) VALUES (?, ?, ?)",
            (edge_id, ep_tc, "venue"),
        )
        pa_count += 1

        # Each person principal becomes a participant with a classified role
        for p in plist:
            cat = p.get("category", "")
            if cat == "archive_footage":
                skipped_archive += 1
                continue
            nconst = p["nconst"]
            chars = p.get("characters")
            # IMDb characters field is sometimes a JSON-stringified list; flatten
            if chars and chars.startswith("["):
                try:
                    chars_list = json.loads(chars)
                    chars = ", ".join(chars_list) if isinstance(chars_list, list) else chars
                except json.JSONDecodeError:
                    pass
            role = _classify_role(cat, chars)
            try:
                conn.execute(
                    "INSERT INTO participants (edge_id, node_id, role) VALUES (?, ?, ?)",
                    (edge_id, nconst, role),
                )
                pa_count += 1
            except sqlite3.IntegrityError:
                # Same (edge, node, role) already inserted (rare; same person credited twice in same role)
                skipped_dupes += 1
    conn.commit()
    print(
        f"      created {edges_count:,} appearance edges, "
        f"{pa_count:,} participant rows "
        f"(skipped {skipped_archive:,} archive_footage, {skipped_dupes:,} dupes)"
    )


# ---------------------------------------------------------------------------
# Verification sample queries
# ---------------------------------------------------------------------------
def verify(conn):
    print("\n[verify] sample queries:")
    cur = conn.cursor()

    cur.execute("SELECT kind, COUNT(*) FROM nodes GROUP BY kind ORDER BY kind")
    print("  nodes by kind:")
    for kind, count in cur.fetchall():
        print(f"    {kind}: {count:,}")

    cur.execute("SELECT kind, COUNT(*) FROM edges GROUP BY kind")
    print("  edges by kind:")
    for kind, count in cur.fetchall():
        print(f"    {kind}: {count:,}")

    cur.execute("SELECT role, COUNT(*) FROM participants GROUP BY role ORDER BY COUNT(*) DESC")
    print("  participants by role:")
    for role, count in cur.fetchall():
        print(f"    {role}: {count:,}")

    cur.execute(
        """SELECT n.name, n.canonical_url, COUNT(*) AS apps
           FROM participants p JOIN nodes n ON n.id = p.node_id
           WHERE p.role = 'guest' GROUP BY p.node_id
           ORDER BY apps DESC LIMIT 10"""
    )
    print("  top 10 guests:")
    for name, url, c in cur.fetchall():
        print(f"    {c:>4}  {name}  ({url})")

    # Pick one known person and show their appearances
    cur.execute(
        """SELECT e.id, n.name, n.canonical_url, e.date
           FROM edges e
           JOIN participants p_guest ON p_guest.edge_id = e.id AND p_guest.node_id = ?
           JOIN participants p_ep    ON p_ep.edge_id = e.id AND p_ep.role = 'venue'
           JOIN nodes n ON n.id = p_ep.node_id
           WHERE p_guest.role IN ('guest', 'self')
           ORDER BY e.date
           LIMIT 5""",
        ("nm0000158",),  # Tom Hanks
    )
    print("  Tom Hanks's first 5 appearances (nconst nm0000158):")
    for edge_id, name, url, date in cur.fetchall():
        print(f"    {date}  {name[:60]:<60}  {url}")


# ---------------------------------------------------------------------------
def main():
    if not IMDB_DIR.exists():
        print(f"ERROR: IMDb extraction directory not found: {IMDB_DIR}", file=sys.stderr)
        sys.exit(1)
    if not SCHEMA_SQL.exists():
        print(f"ERROR: schema.sql not found: {SCHEMA_SQL}", file=sys.stderr)
        sys.exit(1)

    parents, episodes_raw, episode_meta, principals, names, ratings = load_extracts()
    conn = init_db()
    try:
        populate_shows(conn, parents)
        populate_episodes(conn, episode_meta, episodes_raw, ratings)
        populate_people(conn, names)
        populate_appearances(conn, principals, episode_meta)
        verify(conn)
    finally:
        conn.close()

    size_mb = OUT_DB.stat().st_size / 1024 / 1024
    print(f"\nDone. {OUT_DB} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
