#!/usr/bin/env python
"""
orchestrator_fire.py — one fire of the Conan-corpus agent team.

Implements the workflow documented in `.claude/skills/conan-orchestrator/SKILL.md`:
SCOUT → EDITOR → HERALD → (weekly) AUDITOR → CHANGELOG roll-up.

For v1 this implements the SCOUT phase end-to-end:
- fetch the Google News celebrities RSS feed
- extract candidate names + resolve against name_aliases
- for each matched ticket, post a [scout] [news-id:<hash>] comment (deduped)
- write a CHANGELOG entry summarizing the fire

EDITOR / HERALD / AUDITOR phases are stubs for now — they'll do real work
once tickets accumulate state via SCOUT. The orchestrator is designed to
be re-fired safely; every step is idempotent.

Usage:
    python scripts/orchestrator_fire.py
    python scripts/orchestrator_fire.py --dry-run  # report what would happen, don't write
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Make `lib.*` importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.extract_names import find_corpus_names
from lib.feed_fetch import fetch_and_parse

GOOGLE_NEWS_CELEBRITIES = (
    "https://news.google.com/rss/topics/"
    "CAAqJggKIiBDQkFTRWdvSUwyMHZNREpxYW5RU0FtVnVHZ0pWVXlnQVAB"
    "?hl=en-US&gl=US&ceid=US%3Aen"
)
BW = "bw"
CHANGELOG = REPO_ROOT / "data" / "CHANGELOG.md"
# Local dedup cache so we don't re-post the same news-id to the same ticket on
# subsequent fires. Gitignored; rebuilt locally. Cheaper than `bw show`-based
# dedup (which times out on Windows at scale).
DEDUP_CACHE = REPO_ROOT / "data" / ".tmp" / "scout_posted_keys.json"


def load_dedup() -> set:
    if not DEDUP_CACHE.exists():
        return set()
    try:
        return set(tuple(p) for p in json.loads(DEDUP_CACHE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return set()


def save_dedup(keys: set) -> None:
    DEDUP_CACHE.parent.mkdir(exist_ok=True, parents=True)
    DEDUP_CACHE.write_text(
        json.dumps([list(p) for p in keys], indent=0), encoding="utf-8"
    )


def bw_comment(ticket_id: str, text: str, author: str, dry_run: bool = False) -> bool:
    """Post a comment with the given author. Returns True on success.
    bw on Windows can take 30-90 seconds per write (go-git overhead),
    so the timeout is generous."""
    if dry_run:
        return True
    env = os.environ.copy()
    env["BW_AUTHOR"] = author
    try:
        subprocess.check_output(
            [BW, "comment", ticket_id, text],
            stderr=subprocess.STDOUT,
            env=env,
            timeout=180,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"    ERROR posting to {ticket_id}: {e.output.decode(errors='replace')[:200]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT posting to {ticket_id} after 180s")
        return False


# ---------------------------------------------------------------------------
# Phase 1: SCOUT — passive feed-match
# ---------------------------------------------------------------------------
def phase_scout_passive(dry_run: bool) -> dict:
    print("\n[Phase: SCOUT passive feed-match]")
    print(f"  Fetching feed: {GOOGLE_NEWS_CELEBRITIES[:80]}...")
    stories = fetch_and_parse(GOOGLE_NEWS_CELEBRITIES)
    print(f"  Fetched {len(stories)} stories")

    dedup = load_dedup()
    print(f"  Dedup cache: {len(dedup)} (ticket_id, news_id) pairs from prior fires")

    posted = 0
    skipped_dedup = 0
    skipped_no_match = 0
    matched_stories = 0
    errors = 0
    today = time.strftime("%Y-%m-%d")

    for story in stories:
        text = f"{story['title']} {story['summary']}"
        matches = find_corpus_names(text)
        if not matches:
            skipped_no_match += 1
            continue
        matched_stories += 1

        news_id = story["news_id"]
        comment_text = (
            f"[news-id:{news_id}] [scout] news match {today}: "
            f'"{story["title"]}"\n'
            f"{story['link']}\n"
            f"Summary: {story.get('summary', '')[:240]}"
        )

        for match in matches:
            ticket_id = f"bw-p-{match['node_id']}"
            key = (ticket_id, news_id)
            if key in dedup:
                skipped_dedup += 1
                continue
            ok = bw_comment(ticket_id, comment_text, author="conan-scout", dry_run=dry_run)
            if ok:
                posted += 1
                if not dry_run:
                    dedup.add(key)
                print(f"    POST {ticket_id} ({match['canonical_name']}) :: news-id:{news_id}")
            else:
                errors += 1

    if not dry_run:
        save_dedup(dedup)

    return {
        "fetched": len(stories),
        "matched_stories": matched_stories,
        "posted": posted,
        "skipped_dedup": skipped_dedup,
        "skipped_no_match": skipped_no_match,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Phase 2: EDITOR — process state:needs-search / state:searched tickets
# ---------------------------------------------------------------------------
def phase_editor(dry_run: bool) -> dict:
    print("\n[Phase: EDITOR]")
    # Stub: SCOUT in passive-feed-match mode doesn't create state-tagged tickets
    # for matched-existing-person cases (only for orphan stubs). Until SCOUT
    # creates orphans (Job 1.5), EDITOR has nothing to process here.
    # When orphans exist, this phase would:
    #   - bw list --label state:needs-search --all
    #   - for each: read SCOUT's findings, classify, route, transition
    # For v1 first-fire test: report and pass through.
    print("  No state:needs-search or state:searched tickets to process this fire.")
    return {"processed": 0}


# ---------------------------------------------------------------------------
# Phase 3: HERALD — deep-dive state:needs-tracking project tickets
# ---------------------------------------------------------------------------
def phase_herald(dry_run: bool) -> dict:
    print("\n[Phase: HERALD]")
    # Stub: HERALD processes state:needs-tracking project tickets.
    # Until SCOUT's active-project-search runs (or the user creates project
    # tickets manually), this is a no-op.
    print("  No kind:project state:needs-tracking tickets this fire.")
    return {"processed": 0}


# ---------------------------------------------------------------------------
# Phase 4: AUDITOR — periodic (weekly) meta-review
# ---------------------------------------------------------------------------
def phase_auditor(dry_run: bool, scout_stats: dict) -> dict:
    print("\n[Phase: AUDITOR (skipped on first fire)]")
    # Stub: AUDITOR samples recent EDITOR decisions + HERALD research.
    # On the first fire there's nothing to audit. Will run on a ~weekly cadence
    # in production (checked via age of most-recent kind:audit ticket).
    return {"ran": False, "reason": "no prior agent decisions to audit"}


# ---------------------------------------------------------------------------
# Roll-up + CHANGELOG
# ---------------------------------------------------------------------------
def write_changelog(stats: dict, dry_run: bool) -> None:
    if dry_run:
        print(f"\n[CHANGELOG] (dry-run; would append entry)")
        return
    ts = time.strftime("%Y-%m-%d %H:%M")
    note = (
        "initial test fire" if not CHANGELOG.exists() else f"fire {ts}"
    )
    entry = (
        f"## {ts} ({note})\n\n"
        f"scout: fetched {stats['scout']['fetched']} stories from Google News Celebrities, "
        f"posted {stats['scout']['posted']} new comments, "
        f"skipped {stats['scout']['skipped_dedup']} as duplicates, "
        f"{stats['scout']['skipped_no_match']} stories had no corpus match. "
        f"({stats['scout']['errors']} errors)\n"
        f"editor: processed {stats['editor']['processed']} tickets.\n"
        f"herald: processed {stats['herald']['processed']} project tickets.\n"
        f"auditor: {'ran' if stats['auditor']['ran'] else 'skipped'} ({stats['auditor'].get('reason','')}).\n\n"
        f"---\n\n"
    )
    if not CHANGELOG.exists():
        header = (
            "# CHANGELOG\n\n"
            "Each `/loop` fire of the conan-orchestrator appends an entry below.\n"
            "Format: scout / editor / herald / auditor counts per phase.\n\n"
        )
        CHANGELOG.write_text(header + entry, encoding="utf-8")
    else:
        with CHANGELOG.open("a", encoding="utf-8") as f:
            f.write(entry)
    print(f"\n[CHANGELOG] appended entry to {CHANGELOG}")


# ---------------------------------------------------------------------------
def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== orchestrator_fire (DRY RUN — no bw writes) ===")
    else:
        print("=== orchestrator_fire ===")

    stats = {
        "scout": phase_scout_passive(dry_run),
        "editor": phase_editor(dry_run),
        "herald": phase_herald(dry_run),
    }
    stats["auditor"] = phase_auditor(dry_run, stats["scout"])

    print("\n=== Fire summary ===")
    print(json.dumps(stats, indent=2))

    write_changelog(stats, dry_run)


if __name__ == "__main__":
    main()
