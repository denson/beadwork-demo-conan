#!/usr/bin/env python
"""
scout_passive_feed.py — the one-call entry point for SCOUT's passive feed-match.

Fetches the configured RSS feed (Google News Celebrities by default),
parses each story, extracts candidate person names, resolves each against
the bw corpus's name_aliases, and prints a single JSON document SCOUT can
act on.

For each story, the output includes a stable `news_id` SCOUT uses to dedup
across re-fires (search for "news-id:<id>" in any candidate ticket's
history before posting a new comment).

Usage:
    python scripts/scout_passive_feed.py

    # or override the feed URL:
    python scripts/scout_passive_feed.py "https://...other-rss-feed..."

Output (stdout): JSON array of:
    {
      "news_id": "abc123",
      "title": "...",
      "link": "...",
      "pub_date": "...",
      "summary": "...",
      "matches": [
        {"name_in_text": "Tom Hanks", "canonical_name": "Tom Hanks", "node_id": "nm0000158"},
        ...
      ]
    }

Stories with zero corpus matches are still included (so SCOUT's
Job 1.5 — auto-orphans for unknown names appearing in 2+ stories — has
the data it needs).
"""
import json
import sys
from pathlib import Path

# Make `lib.*` importable when invoked as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.extract_names import find_corpus_names
from lib.feed_fetch import fetch_and_parse

GOOGLE_NEWS_CELEBRITIES = (
    "https://news.google.com/rss/topics/"
    "CAAqJggKIiBDQkFTRWdvSUwyMHZNREpxYW5RU0FtVnVHZ0pWVXlnQVAB"
    "?hl=en-US&gl=US&ceid=US%3Aen"
)


def main():
    feed_url = sys.argv[1] if len(sys.argv) > 1 else GOOGLE_NEWS_CELEBRITIES
    stories = fetch_and_parse(feed_url)
    enriched = []
    for s in stories:
        text = f"{s['title']} {s['summary']}"
        matches = find_corpus_names(text)
        enriched.append({**s, "matches": matches})
    print(json.dumps(enriched, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
