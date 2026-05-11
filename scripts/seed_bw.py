#!/usr/bin/env python
"""
seed_bw.py — produce the initial bw import JSONL from conan.db + conaf_regulars.json.

Reads:
- data/conan.db (the hypergraph: shows, episodes, people)
- data/conaf_regulars.json (CONAF YouTube appearance counts per person)

Mutates conan.db:
- Adds team-<slug> nodes for manual posse members not in IMDb (Eduardo, etc.)
- Adds short-name aliases for unambiguous crew nicknames (Bley, Sona, Coco)

Writes:
- data/bw_seed.jsonl (one bw-importable record per ticket)

After this, `bw init && bw import data/bw_seed.jsonl --dry-run` validates the
file; then `bw import data/bw_seed.jsonl` does the real import.

Label taxonomy (locked May 2026):
  kind:        person | show | episode | project | audit
  era:         late_night | tonight_show | conan_tbs | conaf | must_go | jibber_jabber | multi
  is:          posse | conaf_guest | regular_tv_guest | current_team | deceased | conan_himself
  privacy:     public_work_only | public_record
  source:      imdb_seed | discover_youtube | discover_news | manual
  state:       (set later by the agent team: needs-search | searched | analyzed | needs-tracking | tracked | private_skip | needs-audit | audited)
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "conan.db"
CONAF_JSON = REPO_ROOT / "data" / "conaf_regulars.json"
OUT_PATH = REPO_ROOT / "data" / "bw_seed.jsonl"

# Optional local cache of all-titles metadata (from the dropped filmography extension).
# Resolves knownForTitles tconsts to real titles for better grep matching.
# Gitignored — only on PRINCIPAL's machine.
TITLE_CACHE_PATH = Path(r"D:\team_coco_videos\coco_superfan\conan_extraction\guest_filmography_basics.json")

# Hand-curated posse — get is:posse + is:current_team regardless of CONAF count
HAND_CURATED_POSSE = [
    # (display_name, candidate_id_or_None, role_description)
    ("Conan O'Brien", "nm0005277", "host, the center"),
    ("Sona Movsesian", "nm3530452", "co-host, longtime assistant"),
    ("Aaron Bleyaert", "nm1723773", "writer, Clueless Gamer alum, host of *Good Game Nice Try*"),
    ("Jordan Schlansky", "nm1700005", "recurring on-camera character, dry as parchment"),
    # Crew that may or may not be in IMDb — we look them up; if absent, create team-<slug>
    ("Matt Gourley", None, "producer + co-host (on paternity leave May 2026)"),
    ("David Hopping", None, "fill-in producer covering Matt's leave"),
    ("Mike Sweeney", None, "head writer; institutional memory; directs Must Go episodes"),
    ("Adam Sachs", None, "executive producer"),
    ("Jeff Ross", None, "executive producer since Late Night 1993"),
    ("José Arroyo", None, "long-serving Conan writer"),
    # Not in IMDb at all — sound engineer
    ("Eduardo", "team-eduardo", "CONAF sound engineer who speaks on-air; Conan defers to him"),
]

# Unambiguous crew aliases (avoid common short names that collide with celebrities)
CREW_ALIASES = {
    "Bley": "Aaron Bleyaert",
    "Sona": "Sona Movsesian",
    "Coco": "Conan O'Brien",
    "Eduardo": "Eduardo",  # he is just Eduardo
}

# Show -> era
SHOW_TO_ERA = {
    "tt0106052": "late_night",      # Late Night with Conan O'Brien
    "tt0899126": "tonight_show",    # The Tonight Show with Conan O'Brien
    "tt12164696": "jibber_jabber",  # Serious Jibber-Jabber
    "tt1637574": "conan_tbs",       # Conan (TBS)
    "tt27790101": "must_go",        # Conan O'Brien Must Go
}

REGULAR_TV_GUEST_THRESHOLD = 10


def find_person_by_name(conn, name):
    """Lookup name -> nconst, person nodes only."""
    cur = conn.execute(
        """SELECT na.node_id FROM name_aliases na JOIN nodes n ON n.id = na.node_id
           WHERE na.alias = ? COLLATE NOCASE AND n.kind = 'person' LIMIT 1""",
        (name,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def slugify(name):
    out = ""
    for c in name.lower().replace("'", ""):
        if c.isalnum():
            out += c
        elif c.isspace() or c == "-":
            out += "-"
    return out.strip("-")


def add_manual_team(conn):
    """Add team-<slug> nodes for posse members not in IMDb. Add crew aliases."""
    print("[Phase 2] Adding manual posse entries to conan.db ...")
    posse_ids = []
    added_team = []
    for name, candidate, role in HAND_CURATED_POSSE:
        node_id = candidate
        if node_id is None or not (node_id.startswith("nm") or node_id.startswith("team-")):
            existing = find_person_by_name(conn, name)
            if existing:
                node_id = existing
            else:
                node_id = f"team-{slugify(name)}"
        # Create team-<slug> entry if it doesn't exist in conan.db
        exists = conn.execute("SELECT 1 FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not exists:
            if node_id.startswith("team-"):
                data = {"role": role, "manual_addition": True, "primaryProfession": "crew"}
                conn.execute(
                    "INSERT INTO nodes (id, kind, name, canonical_url, data_json) VALUES (?, ?, ?, ?, ?)",
                    (node_id, "person", name, None, json.dumps(data)),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO name_aliases (alias, node_id) VALUES (?, ?)",
                    (name, node_id),
                )
                added_team.append((name, node_id))
            else:
                print(f"  WARN: posse member '{name}' not found in IMDb and no team-slug fallback")
                continue
        posse_ids.append(node_id)

    # Crew short-name aliases
    for short, full_name in CREW_ALIASES.items():
        target = find_person_by_name(conn, full_name)
        if target:
            conn.execute(
                "INSERT OR IGNORE INTO name_aliases (alias, node_id) VALUES (?, ?)",
                (short, target),
            )

    conn.commit()
    if added_team:
        print(f"          added {len(added_team)} team-<slug> entries:")
        for n, nid in added_team:
            print(f"            {nid:<26}  {n}")
    print(f"          posse member IDs resolved: {len(posse_ids)}")
    return set(posse_ids)


def precompute_appearance_counts(conn):
    """Per node_id, count distinct 'guest'-role participations."""
    print("[Phase 3a] Precomputing guest-appearance counts ...")
    counts = dict(
        conn.execute(
            "SELECT node_id, COUNT(DISTINCT edge_id) FROM participants "
            "WHERE role = 'guest' GROUP BY node_id"
        ).fetchall()
    )
    print(f"            {len(counts):,} people with guest credits")
    return counts


def precompute_eras(conn):
    """Per node_id, the set of eras they appeared in based on appearance edges."""
    print("[Phase 3b] Precomputing eras per person ...")
    person_eras = defaultdict(set)
    rows = conn.execute(
        """SELECT p_actor.node_id, n_ep.data_json
           FROM participants p_actor
           JOIN edges e ON e.id = p_actor.edge_id AND e.kind = 'appearance'
           JOIN participants p_ep ON p_ep.edge_id = e.id AND p_ep.role = 'venue'
           JOIN nodes n_ep ON n_ep.id = p_ep.node_id"""
    ).fetchall()
    for node_id, data_json in rows:
        try:
            data = json.loads(data_json or "{}")
            parent = data.get("parent")
            era = SHOW_TO_ERA.get(parent)
            if era:
                person_eras[node_id].add(era)
        except json.JSONDecodeError:
            pass
    print(f"            {len(person_eras):,} people with era information")
    return person_eras


def build_show_records(conn):
    records = []
    for tc, name, url, data_json in conn.execute(
        "SELECT id, name, canonical_url, data_json FROM nodes WHERE kind = 'show'"
    ):
        data = json.loads(data_json or "{}")
        era = SHOW_TO_ERA.get(tc, "multi")
        sy, ey = data.get("startYear"), data.get("endYear")
        years = f"{sy}–{ey or 'present'}"
        labels = [
            "kind:show",
            f"era:{era}",
            "source:imdb_seed",
            "privacy:public_record",
        ]
        description = (
            f"{name} ({years}). A show in Conan's career arc.\n"
            f"IMDb: {url}\n"
            f"_search: {name} | {sy or ''}"
        )
        records.append({
            "id": f"bw-s-{tc}",
            "title": name,
            "description": description,
            "labels": labels,
            "issue_type": "task",
            "status": "open",
        })
    return records


def build_episode_records(conn):
    records = []
    for tc, title, url, data_json in conn.execute(
        "SELECT id, name, canonical_url, data_json FROM nodes WHERE kind = 'episode'"
    ):
        data = json.loads(data_json or "{}")
        parent = data.get("parent")
        era = SHOW_TO_ERA.get(parent, "multi")
        year = data.get("year")
        s, e = data.get("season"), data.get("episode")
        rating = data.get("averageRating")
        runtime = data.get("runtimeMinutes")
        labels = [
            "kind:episode",
            f"era:{era}",
            "source:imdb_seed",
            "privacy:public_record",
        ]
        desc_lines = [
            f"{title}. {era}, S{s or '?'}E{e or '?'}, {year or '?'}.",
        ]
        if runtime:
            desc_lines.append(f"Runtime: {runtime} min.")
        if rating:
            desc_lines.append(f"IMDb rating: {rating}.")
        desc_lines.append(f"IMDb: {url}")
        desc_lines.append(f"_search: {title} | {year or ''} | S{s}E{e}")
        records.append({
            "id": f"bw-e-{tc}",
            "title": title,
            "description": "\n".join(desc_lines),
            "labels": labels,
            "issue_type": "task",
            "status": "open",
        })
    return records


def load_title_cache():
    """Load the cached title-metadata file if present; return {tconst: title} dict."""
    if not TITLE_CACHE_PATH.exists():
        print(f"[Phase 3c] Title cache not found at {TITLE_CACHE_PATH}; "
              f"knownForTitles will be omitted from _search.")
        return {}
    print(f"[Phase 3c] Loading title cache from {TITLE_CACHE_PATH} ...")
    raw = json.loads(TITLE_CACHE_PATH.read_text(encoding="utf-8"))
    titles = {tc: row.get("primaryTitle") for tc, row in raw.items() if row.get("primaryTitle")}
    print(f"            {len(titles):,} tconsts -> titles loaded")
    return titles


def build_person_records(conn, posse_hand_curated, posse_auto, guest_counts, person_eras, conaf_by_id, title_cache):
    records = []
    posse_total = posse_hand_curated | posse_auto
    for node_id, name, url, data_json in conn.execute(
        "SELECT id, name, canonical_url, data_json FROM nodes WHERE kind = 'person'"
    ):
        data = json.loads(data_json or "{}") if data_json else {}
        appearance_count = guest_counts.get(node_id, 0)
        conaf_record = conaf_by_id.get(node_id)
        conaf_count = conaf_record["conaf_appearances"] if conaf_record else 0
        eras = sorted(person_eras.get(node_id, set()))
        is_posse_member = node_id in posse_total
        deceased = bool(data.get("deathYear"))

        labels = ["kind:person", "source:imdb_seed"]

        # Era
        if len(eras) > 1:
            labels.append("era:multi")
        elif len(eras) == 1:
            labels.append(f"era:{eras[0]}")
        elif is_posse_member:
            labels.append("era:multi")  # posse-only manual additions (Eduardo etc.)

        # Posse / guest tiers
        if node_id == "nm0005277":  # Conan himself
            labels += ["is:conan_himself", "is:posse", "is:current_team"]
        elif node_id in posse_hand_curated:
            labels += ["is:posse", "is:current_team"]
        elif node_id in posse_auto:
            labels.append("is:posse")

        if conaf_count == 1 and not is_posse_member:
            labels.append("is:conaf_guest")

        if appearance_count >= REGULAR_TV_GUEST_THRESHOLD and not is_posse_member:
            labels.append("is:regular_tv_guest")

        if deceased:
            labels.append("is:deceased")

        # Privacy
        labels.append("privacy:public_work_only" if is_posse_member else "privacy:public_record")

        # Description
        birth = data.get("birthYear")
        death = data.get("deathYear")
        profs = data.get("primaryProfession") or ""
        known_for_titles = data.get("knownForTitles") or ""
        manual_role = data.get("role")

        bio_facts = []
        if birth:
            bio_facts.append(f"{birth}–{death}" if death else f"b. {birth}")
        if manual_role:
            bio_facts.append(manual_role)
        elif profs:
            bio_facts.append(profs.replace(",", ", "))
        bio_line = " | ".join(bio_facts) if bio_facts else "(no IMDb bio data)"

        appearance_line = f"Conan-show appearances: {appearance_count}"
        if conaf_count > 0:
            appearance_line += f" (incl. {conaf_count} on-camera CONAF)"
        if deceased:
            appearance_line = f"DECEASED ({birth}–{death}). " + appearance_line

        search_tokens = [name]
        if known_for_titles:
            # Resolve tconsts to real titles for greppable _search
            tconsts = [t.strip() for t in known_for_titles.split(",") if t.strip().startswith("tt")]
            resolved_titles = [title_cache.get(tc) for tc in tconsts]
            resolved_titles = [t for t in resolved_titles if t]
            if resolved_titles:
                search_tokens.append(" | ".join(resolved_titles))

        desc_lines = [f"{name}. {bio_line}.", appearance_line]
        if url:
            desc_lines.append(f"IMDb: {url}")
        desc_lines.append(f"_search: {' | '.join(search_tokens)}")

        records.append({
            "id": f"bw-p-{node_id}",
            "title": name,
            "description": "\n".join(desc_lines),
            "labels": labels,
            "issue_type": "task",
            "status": "open",
        })
    return records


def main():
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} not found.", file=sys.stderr)
        sys.exit(1)
    if not CONAF_JSON.exists():
        print(f"ERROR: {CONAF_JSON} not found. Run compile_conaf_regulars.py first.", file=sys.stderr)
        sys.exit(1)

    conaf_data = json.loads(CONAF_JSON.read_text(encoding="utf-8"))
    conaf_by_id = conaf_data["by_id"]
    print(f"[Phase 1] Loaded conaf_regulars.json: {len(conaf_by_id)} people resolved on CONAF YouTube")

    conn = sqlite3.connect(str(DB_PATH))
    posse_hand_curated = add_manual_team(conn)

    # Auto-posse from CONAF data (2+ full-video appearances)
    posse_auto = {
        nconst for nconst, rec in conaf_by_id.items() if rec["conaf_appearances"] >= 2
    }
    print(f"          auto-posse (2+ CONAF YouTube): {len(posse_auto)}  {sorted(posse_auto)}")

    guest_counts = precompute_appearance_counts(conn)
    person_eras = precompute_eras(conn)
    title_cache = load_title_cache()

    print(f"[Phase 4] Building bw import records ...")
    show_records = build_show_records(conn)
    print(f"            shows:    {len(show_records):,}")
    ep_records = build_episode_records(conn)
    print(f"            episodes: {len(ep_records):,}")
    person_records = build_person_records(
        conn, posse_hand_curated, posse_auto, guest_counts, person_eras, conaf_by_id, title_cache
    )
    print(f"            people:   {len(person_records):,}")
    conn.close()

    all_records = show_records + ep_records + person_records

    OUT_PATH.parent.mkdir(exist_ok=True, parents=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    size_mb = OUT_PATH.stat().st_size / 1024 / 1024
    print(f"\n[Phase 5] Output: {OUT_PATH} ({len(all_records):,} records, {size_mb:.2f} MB)")

    # Label histogram
    print(f"\n[label-distribution]")
    label_counts = defaultdict(int)
    for r in all_records:
        for lab in r["labels"]:
            label_counts[lab] += 1
    for lab in sorted(label_counts):
        print(f"    {lab:<32}  {label_counts[lab]:>6,}")

    # Sample a posse ticket
    print(f"\n[sample] posse ticket — Conan O'Brien (bw-p-nm0005277):")
    for r in all_records:
        if r["id"] == "bw-p-nm0005277":
            print(json.dumps(r, indent=2, ensure_ascii=False))
            break

    # Sample a CONAF guest ticket
    print(f"\n[sample] conaf_guest ticket — first one in the output:")
    for r in all_records:
        if "is:conaf_guest" in r["labels"]:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            break

    print(f"\nNext step: `bw init` in this repo, then `bw import data/bw_seed.jsonl --dry-run`")


if __name__ == "__main__":
    main()
