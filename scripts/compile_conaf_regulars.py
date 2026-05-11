#!/usr/bin/env python
"""
Compile a count of CONAF YouTube full-episode appearances per person.

INPUT:
- CONAF full-episodes playlist on YouTube (public, no auth):
  https://www.youtube.com/playlist?list=PLVL8S3lUHf0Te3TvS37LaF6dk4rhkc2gg
- data/conan.db — for name resolution against name_aliases

OUTPUT:
- data/conaf_regulars.json — per-person CONAF appearance counts

WHY:
seed_bw.py reads this to apply labels:
  - is:posse              -> 2+ CONAF YouTube full-episode appearances (auto)
                            OR member of the hand-curated 11 (core crew)
  - is:conaf_guest        -> exactly 1 CONAF YouTube full-episode appearance
  - is:regular_tv_guest   -> 10+ historical TV appearances AND not posse
  - is:deceased           -> deathYear populated in IMDb data

YT-DLP USAGE NOTE:
This script invokes yt-dlp with `--flat-playlist --skip-download`,
which fetches PLAYLIST METADATA ONLY (title, duration, video_id per entry)
by reading the public playlist page YouTube renders for any visitor.
**No video or audio content is downloaded.** Same access pattern as a user
opening the playlist in their browser. yt-dlp's TOS-violating download
modes (full video, audio extraction) are not used.

Runtime: ~30s for yt-dlp playlist fetch; ~1s for name resolution.
"""
import json
import re
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "conan.db"
OUT_PATH = REPO_ROOT / "data" / "conaf_regulars.json"

PLAYLIST_ID = "PLVL8S3lUHf0Te3TvS37LaF6dk4rhkc2gg"
PLAYLIST_URL = f"https://www.youtube.com/playlist?list={PLAYLIST_ID}"

# Full episodes are 30+ min; teasers/clips/comps are shorter.
DURATION_FILTER_SECONDS = 30 * 60

# ---------- Title parsing heuristics ----------

# CONAF brand suffix — strip and everything after it
CONAF_SUFFIX_PATTERNS = [
    r"\s*\|\s*Conan O[''’]Brien Needs (?:A|a) Friend\s*",
    r"\s*\|\s*CONAF\s*",
    r"\s*[-—–]\s*Conan O[''’]Brien Needs (?:A|a) Friend\s*",
]

# Episode-marker tags (case-insensitive) to strip from anywhere in the title
TAG_PATTERNS = [
    r"\(FULL EPISODE\)",
    r"\(Live\)",
    r"\(LIVE\)",
    r"\(Live at .+?\)",
]

# "Returns/Revisits" suffixes that decorate a recurring guest's name
RETURN_SUFFIX_PATTERNS = [
    r"\bReturns?\s+Once\s+More\b",
    r"\bReturns?\s+Yet\s+Again\b",
    r"\bReturns?\s+Again\b",
    r"\bReturns?\b",
    r"\bRevisits?\b",
    r"\bRetakes?\b",
]

# "Live with X at Y" / "Live at Y with X" prefixes — keep what comes after "with"
LIVE_PREFIX_PATTERN = re.compile(r"^Live\s+(?:with|at)\s+", re.IGNORECASE)

# "...with X" pattern — when present, the guest is everything after the last " with "
WITH_GUEST_PATTERN = re.compile(r"\s+[Ww]ith\s+(.+)$")

# Things that mark "this is not a guest episode" — drop the whole title
NON_GUEST_PATTERNS = [
    r"\bbest of\b",
    r"\bhighlights?\b",
    r"\bcompilation\b",
    r"\btrailer\b",
    r"\bintroducing\b",
    r"\bannouncing\b",
    r"\btake a listen\b",
]

# Multi-guest separators
GUEST_SEPARATORS = re.compile(r"\s*(?:,|/|\s+&\s+|\s+and\s+)\s*")


def ensure_yt_dlp():
    try:
        out = subprocess.check_output([sys.executable, "-m", "yt_dlp", "--version"], stderr=subprocess.STDOUT)
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(
            "ERROR: yt-dlp not found (tried `python -m yt_dlp`). Install with:\n"
            "    pip install -U --user yt-dlp\n"
            "or:\n"
            "    pip install -U yt-dlp\n",
            file=sys.stderr,
        )
        sys.exit(1)


def fetch_playlist():
    print(f"[Phase 1] Fetching CONAF playlist metadata via yt-dlp ...")
    print(f"          (--flat-playlist --skip-download — metadata only, no downloads)")
    t0 = time.time()
    try:
        result = subprocess.check_output(
            [
                sys.executable, "-m", "yt_dlp",
                "--flat-playlist",
                "--skip-download",
                "--dump-single-json",
                "--quiet",
                PLAYLIST_URL,
            ],
            stderr=subprocess.PIPE,
            timeout=300,
        )
    except subprocess.CalledProcessError as e:
        print(f"ERROR: yt-dlp failed: {e.stderr.decode()[:500]}", file=sys.stderr)
        print(
            "\nIf this is a bot-detection error, try adding:"
            "\n  --cookies-from-browser chrome"
            "\nto the yt-dlp invocation. You may need to be signed in to YouTube in Chrome.",
            file=sys.stderr,
        )
        sys.exit(1)
    data = json.loads(result)
    entries = data.get("entries", [])
    print(f"          fetched {len(entries):,} playlist items in {time.time()-t0:.0f}s")
    return entries


def parse_guest_names(title: str) -> list[str]:
    """Heuristic title parser. Returns list of guest names (may be empty)."""
    if not title:
        return []
    t = title

    # Strip the CONAF brand suffix
    for pat in CONAF_SUFFIX_PATTERNS:
        t = re.split(pat, t, flags=re.IGNORECASE)[0]
    t = t.strip()

    # Skip obvious non-guest titles (compilations, trailers, etc.)
    for pat in NON_GUEST_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return []

    # Strip episode-marker tags
    for pat in TAG_PATTERNS:
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()

    # Handle "Live with X at Y" by stripping the prefix
    t = LIVE_PREFIX_PATTERN.sub("", t).strip()

    # If there's a "with X" pattern, the guest is what comes after the last "with"
    with_match = WITH_GUEST_PATTERN.search(t)
    if with_match:
        t = with_match.group(1).strip()

    # Strip "Live From [venue]" / "at the [venue]" / "from [venue]" trailing patterns
    t = re.sub(r"\s+(?:Live\s+)?[Ff]rom\s+(?:the\s+)?[\w\s'&\.\-]+$", "", t).strip()
    t = re.sub(r"\s+at\s+(?:the\s+)?[\w\s'&\.\-]+$", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\s+LIVE\b.*$", "", t).strip()

    # Strip Returns/Revisits suffixes
    for pat in RETURN_SUFFIX_PATTERNS:
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()

    # Trim trailing punctuation
    t = t.strip(" -—–:'\"")
    if not t:
        return []

    # Split on multi-guest separators
    names = [n.strip() for n in GUEST_SEPARATORS.split(t) if n.strip()]
    # Filter to reasonable name lengths (drop fragments + over-long descriptions)
    names = [n for n in names if 2 < len(n) < 60]
    return names


def resolve_name(conn, name: str) -> str | None:
    """Look up name -> nconst via name_aliases. Prefers person nodes over
    episode nodes (since episode titles often re-use guest names).
    Returns None if unresolved."""
    cur = conn.execute(
        """SELECT na.node_id
           FROM name_aliases na
           JOIN nodes n ON n.id = na.node_id
           WHERE na.alias = ? COLLATE NOCASE
           ORDER BY CASE n.kind
             WHEN 'person' THEN 0
             WHEN 'show' THEN 1
             WHEN 'episode' THEN 2
             ELSE 3
           END
           LIMIT 1""",
        (name,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def main():
    yt_dlp_version = ensure_yt_dlp()
    print(f"yt-dlp version: {yt_dlp_version}")

    if not DB_PATH.exists():
        print(
            f"ERROR: {DB_PATH} not found. Run scripts/build_hypergraph.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    entries = fetch_playlist()

    # Filter by duration
    print(f"[Phase 2] Filtering to full episodes (duration >= {DURATION_FILTER_SECONDS//60} min) ...")
    full_episodes = []
    skipped_short = 0
    skipped_unknown_duration = 0
    for e in entries:
        duration_sec = e.get("duration")
        if duration_sec is None:
            skipped_unknown_duration += 1
            continue
        if duration_sec < DURATION_FILTER_SECONDS:
            skipped_short += 1
            continue
        full_episodes.append(e)
    print(
        f"          {len(full_episodes):,} full episodes kept "
        f"(skipped {skipped_short:,} short, {skipped_unknown_duration:,} unknown-duration)"
    )

    # Parse + resolve names
    print(f"[Phase 3] Parsing guest names + resolving against conan.db ...")
    conn = sqlite3.connect(str(DB_PATH))
    by_id = defaultdict(lambda: {"name": "", "conaf_appearances": 0, "episodes": []})
    unresolved = defaultdict(lambda: {"name": "", "appearances": 0, "episodes": []})

    for e in full_episodes:
        title = e.get("title", "")
        video_id = e.get("id", "")
        duration_sec = e.get("duration") or 0
        ep_record = {
            "title": title,
            "duration_minutes": round(duration_sec / 60),
            "video_id": video_id,
            "youtube_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        }
        names = parse_guest_names(title)
        if not names:
            continue
        for name in names:
            nconst = resolve_name(conn, name)
            if nconst:
                by_id[nconst]["name"] = name
                by_id[nconst]["conaf_appearances"] += 1
                by_id[nconst]["episodes"].append(ep_record)
            else:
                key = name.lower()
                unresolved[key]["name"] = name
                unresolved[key]["appearances"] += 1
                unresolved[key]["episodes"].append(ep_record)

    # Backfill canonical names from conan.db for resolved entries
    for nconst in by_id:
        row = conn.execute("SELECT name FROM nodes WHERE id = ?", (nconst,)).fetchone()
        if row:
            by_id[nconst]["name"] = row[0]
    conn.close()

    # Stats
    resolved_with_2plus = sum(1 for r in by_id.values() if r["conaf_appearances"] >= 2)
    resolved_with_1 = sum(1 for r in by_id.values() if r["conaf_appearances"] == 1)

    out = {
        "metadata": {
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "playlist_id": PLAYLIST_ID,
            "playlist_url": PLAYLIST_URL,
            "total_playlist_items": len(entries),
            "after_duration_filter": len(full_episodes),
            "duration_filter_min": DURATION_FILTER_SECONDS // 60,
            "resolved_people": len(by_id),
            "auto_posse_2plus": resolved_with_2plus,
            "conaf_guests_1x": resolved_with_1,
            "unresolved_names": len(unresolved),
        },
        "by_id": dict(by_id),
        "unresolved_names": sorted(
            unresolved.values(), key=lambda x: -x["appearances"]
        ),
    }

    OUT_PATH.parent.mkdir(exist_ok=True, parents=True)
    OUT_PATH.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n[Phase 4] Output written to {OUT_PATH}")
    print(f"          Total resolved people: {len(by_id):,}")
    print(f"          Auto-posse (>=2 CONAF YouTube appearances): {resolved_with_2plus:,}")
    print(f"          CONAF guests (exactly 1): {resolved_with_1:,}")
    print(f"          Unresolved names (manual review): {len(unresolved):,}")

    # Sample auto-posse (top 25 by appearance count)
    print(f"\n[sample] Top 25 by CONAF appearance count (auto-posse threshold = 2):")
    sorted_by_count = sorted(by_id.items(), key=lambda x: -x[1]["conaf_appearances"])
    for nconst, rec in sorted_by_count[:25]:
        marker = "POSSE" if rec["conaf_appearances"] >= 2 else "guest"
        print(f"    [{marker}] {rec['conaf_appearances']:>3}x  {rec['name']:<40}  ({nconst})")

    # Sample unresolved (top 15)
    if unresolved:
        print(f"\n[sample] Top 15 unresolved names (review for aliases or team-<slug>):")
        sorted_unresolved = sorted(unresolved.values(), key=lambda x: -x["appearances"])
        for rec in sorted_unresolved[:15]:
            print(f"    {rec['appearances']:>3}x  {rec['name']}")


if __name__ == "__main__":
    main()
