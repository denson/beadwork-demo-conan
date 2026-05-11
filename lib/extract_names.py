#!/usr/bin/env python
"""
extract_names.py — find person names in text that match our bw corpus.

Used by SCOUT's passive feed-match: for each fetched news story,
identify which corpus people are mentioned.

Approach:
1. Extract candidate proper-noun spans (1-4 consecutive Capitalized words)
   from text, filtering common false positives (months, days, places, etc.).
2. For each candidate, look up `name_aliases` in conan.db (person nodes only).
3. Return the unique matched person records.

Library usage:
    from lib.extract_names import find_corpus_names
    matches = find_corpus_names("Tom Hanks promotes his new film with Steven Spielberg")

CLI usage:
    python -m lib.extract_names "Tom Hanks promotes his new film"

Output: a JSON array of {name_in_text, canonical_name, node_id} entries.
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "conan.db"

# 1-4 consecutive Capitalized words. Allow ' . - inside a word.
NAME_CANDIDATE = re.compile(
    r"\b[A-Z][a-zA-Z'.\-]+(?:\s+(?:[A-Z][a-zA-Z'.\-]+|[a-z][a-z]?)){0,3}\b"
)

# False positives: words that get capitalized in headlines but aren't names.
FALSE_POSITIVES = {
    # Generic
    "The", "A", "An", "And", "But", "Or", "If", "Then", "So", "Of", "In", "On",
    "I", "He", "She", "It", "They", "We", "You",
    "This", "That", "These", "Those",
    # Honorifics standing alone
    "Mr", "Mrs", "Ms", "Dr", "Sir", "Lord", "Lady",
    # Days / months
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    # Common places
    "United States", "New York", "Los Angeles", "Hollywood", "Beverly Hills",
    "London", "Paris", "Tokyo", "Boston", "Chicago", "San Francisco",
    "United Kingdom", "Great Britain",
    # Common entities / platforms
    "TV", "HBO", "Apple", "Spotify", "YouTube", "Netflix", "Hulu",
    "Disney", "Amazon", "Google", "Facebook", "Twitter", "Instagram",
    "Saturday Night Live", "Late Night", "Tonight Show", "Today Show",
    # Months alone get picked up sometimes
}


def extract_candidates(text: str) -> set[str]:
    """Return unique candidate name strings from text."""
    candidates = set()
    for m in NAME_CANDIDATE.finditer(text):
        s = m.group(0).strip()
        if len(s) < 3:
            continue
        if s in FALSE_POSITIVES:
            continue
        # Strip trailing punctuation
        s = s.rstrip(".,;:!?")
        words = s.split()
        # 1-word candidates are too noisy unless they're long enough and not a common word
        if len(words) == 1 and (len(s) < 5 or s in FALSE_POSITIVES):
            continue
        # 5+ word candidates are usually phrase fragments, not names
        if len(words) > 4:
            continue
        candidates.add(s)
    return candidates


def lookup_names(conn: sqlite3.Connection, candidates: set[str]) -> list[dict]:
    """Resolve each candidate via name_aliases (person nodes only)."""
    matches = []
    seen_ids = set()
    for name in candidates:
        cur = conn.execute(
            """SELECT na.node_id, n.name
               FROM name_aliases na JOIN nodes n ON n.id = na.node_id
               WHERE na.alias = ? COLLATE NOCASE AND n.kind = 'person'
               LIMIT 1""",
            (name,),
        )
        row = cur.fetchone()
        if row:
            node_id, canonical = row
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                matches.append({
                    "name_in_text": name,
                    "canonical_name": canonical,
                    "node_id": node_id,
                })
    return matches


def find_corpus_names(text: str) -> list[dict]:
    """Public API: extract corpus-matching person names from text."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found")
    conn = sqlite3.connect(str(DB_PATH))
    try:
        candidates = extract_candidates(text)
        matches = lookup_names(conn, candidates)
    finally:
        conn.close()
    return matches


def main():
    if len(sys.argv) < 2:
        print('Usage: python -m lib.extract_names "<text>"', file=sys.stderr)
        sys.exit(1)
    text = " ".join(sys.argv[1:])
    matches = find_corpus_names(text)
    print(json.dumps(matches, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
