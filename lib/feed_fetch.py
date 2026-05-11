#!/usr/bin/env python
"""
feed_fetch.py — fetch + parse an RSS/Atom feed; emit a list of story records.

Used by SCOUT to ingest the Google News Celebrities feed (and any other RSS
feed we want to poll). Each story gets a stable `news_id` derived from the
feed-provided GUID (or, failing that, a SHA-1 hash of the link) so SCOUT
can dedup across re-fires without re-commenting.

Library usage:
    from lib.feed_fetch import fetch_and_parse
    stories = fetch_and_parse("https://news.google.com/rss/topics/...")

CLI usage:
    python -m lib.feed_fetch "https://news.google.com/rss/topics/..."

Output: a JSON array of {news_id, title, link, pub_date, summary} entries.
The summary is HTML-stripped and capped at 500 chars.
"""

import hashlib
import html
import json
import re
import sys
import urllib.request
from xml.etree import ElementTree as ET

USER_AGENT = "Mozilla/5.0 (compatible; conan-corpus-scout/1.0)"
SUMMARY_CAP = 500


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def stable_id(item: ET.Element) -> str:
    """Use the feed's GUID if present, else SHA-1 of the link."""
    guid_el = item.find("guid")
    if guid_el is not None and (guid_el.text or "").strip():
        seed = guid_el.text.strip()
    else:
        link_el = item.find("link")
        seed = (link_el.text or "").strip() if link_el is not None else ""
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    # Standard RSS: root is <rss>, has <channel> child with <item>s.
    # Atom: root is <feed>, items are <entry>. Handle both.
    channel = root.find("channel")
    if channel is not None:
        items = channel.findall("item")
        return [parse_rss_item(it) for it in items]
    # Atom path
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    return [parse_atom_entry(e, ns) for e in entries]


def parse_rss_item(item: ET.Element) -> dict:
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    pub_date = (item.findtext("pubDate") or "").strip()
    summary = strip_html(item.findtext("description") or "")[:SUMMARY_CAP]
    return {
        "news_id": stable_id(item),
        "title": title,
        "link": link,
        "pub_date": pub_date,
        "summary": summary,
    }


def parse_atom_entry(entry: ET.Element, ns: dict) -> dict:
    title = (entry.findtext("atom:title", "", ns)).strip()
    link_el = entry.find("atom:link", ns)
    link = link_el.get("href", "").strip() if link_el is not None else ""
    pub_date = (entry.findtext("atom:published", "", ns)).strip()
    summary = strip_html(entry.findtext("atom:summary", "", ns))[:SUMMARY_CAP]
    # Atom doesn't have GUID; use link hash
    seed = link or title
    return {
        "news_id": hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12],
        "title": title,
        "link": link,
        "pub_date": pub_date,
        "summary": summary,
    }


def fetch_and_parse(url: str) -> list[dict]:
    """Public API."""
    return parse(fetch(url))


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m lib.feed_fetch <feed_url>", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    stories = fetch_and_parse(url)
    print(json.dumps(stories, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
