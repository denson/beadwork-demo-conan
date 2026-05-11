# beadwork-demo-conan

**A Conan O'Brien superfan agent backed by a persistent [beadwork](https://github.com/jallum/beadwork) corpus.**

> *"Tom Hanks chose Conan's Late Night couch in 1998 to promote what would become Saving Private Ryan — the Oscar-winning Spielberg epic that swept the 1999 ceremony. Hanks knows where to come when he wants a hit."*

This is what your AI sounds like after you point it at this repo.

---

## Two paths in

### 1. **No install. Paste this into your AI:**

> `Be a Conan O'Brien superfan using this brief: https://denson.github.io/beadwork-demo-conan/AGENTS.md`

Any AI that can fetch a URL (Claude, ChatGPT, Gemini, Cursor, your phone's assistant) reads the brief and takes on the voice. It can answer questions about Conan, pull the latest CONAF transcript, walk you through any guest's career, all without an install. The brief is self-contained.

### 2. **Full install (Claude Code Desktop):**

For the *agent team* that keeps a personal corpus current over time:

```bash
git clone https://github.com/denson/beadwork-demo-conan
cd beadwork-demo-conan
bw init && bw import data/bw_seed.jsonl
```

Then in Claude Code:

```
/loop 6h "refresh conan corpus"
```

Walk away. Five agents (SCOUT, EDITOR, HERALD, AUDITOR, ORCHESTRATOR) coordinate via [beadwork](https://github.com/jallum/beadwork) and keep the corpus fresh — pulling celebrity news, tracking new Conan ventures, auditing each other's work. The user-facing voice (SUPERFAN) reads it all and brags about Conan on demand.

---

## What's in the corpus

| layer | count |
|---|---:|
| Conan's shows | 5 (Late Night, Tonight Show, Conan TBS, Serious Jibber-Jabber, *Must Go*) |
| Episodes | 4,433 (with IMDb URLs, season/episode numbers, air-years, ratings) |
| People (guests + crew + collaborators) | 7,008 (full IMDb-derived guest list) |
| The 12-name posse | Conan, Sona, Matt Gourley, David Hopping, Bley, Eduardo, Mike Sweeney, Adam Sachs, Jeff Ross, José Arroyo, Jordan Schlansky, Kevin Nealon |
| **Total bw tickets** | **11,446** |

Every ticket carries a canonical IMDb URL (`canonical_url`) — when the agent talks about Tom Hanks's appearance, it opens his real IMDb page in your browser. The substrate holds the *graph* (who-appeared-where, when, with-whom); IMDb holds the canonical content.

---

## The agent team

Six skills under `.claude/skills/`:

| skill | role |
|---|---|
| **conan-superfan** | The voice. User-facing. Answers questions with self-brag mode + on-the-fly IMDb/YouTube lookups. |
| **conan-scout** | Ingests Google News celebrity feed + active project-search for the posse. Matches stories to existing tickets, creates orphan stubs for unknown names. |
| **conan-editor** | Classifies SCOUT's findings — signal vs noise vs duplicate vs (rare) privacy violation. Routes cross-references. |
| **conan-herald** | Deep-dives new project tickets. Captures structured metadata (release dates, principals, canonical URLs). Bidirectional links to person tickets. |
| **conan-auditor** | Weekly meta-review of EDITOR/HERALD/SCOUT work for drift. Writes one audit ticket per pass. Demonstrates beadwork-as-meta-analysis live. |
| **conan-orchestrator** | The `/loop` entry point. Fires phases in sequence. Writes a roll-up to `data/CHANGELOG.md` per fire. |

Each agent sets `BW_AUTHOR=conan-<role>` so every comment is attributable in `bw history`. The state machine (`state:needs-search → searched → analyzed`; `needs-tracking → tracked`) is the inter-agent message bus.

---

## What the bit actually sounds like

**You:** *Who's been on Conan the most?*

**Agent:** *"Marc Maron understood the assignment better than anyone — 55 appearances on Conan's shows, more than any other guest. He went on to launch the most successful comedy interview podcast in the world (WTF) shortly thereafter, which is not a coincidence. Patton Oswalt (39 appearances) and Kevin Nealon (39) are the silver and bronze. Will Ferrell, Jim Gaffigan, Al Roker, Adam Sandler — all in the 30s. There's a pattern."*

**You:** *Tell me about Eduardo.*

**Agent:** *"Eduardo is the CONAF sound engineer — and the one person Conan visibly defers to more than anyone else. That's not nothing. Finding a sound engineer who can also do on-air comedy is rare, and Conan knows it. Listen to any recent episode and you'll hear Conan check in with Eduardo with a respect he doesn't extend to, frankly, anyone."*

**You:** *What's Conan up to these days?*

**Agent:** *"Where to even begin. **Conan O'Brien Needs A Friend** — the #1 comedy podcast in the world. **Conan O'Brien Must Go** on HBO Max — season 2 just landed, and **Werner Herzog narrates the opening.** Werner. Herzog. He's on a stand-up tour right now: [teamcoco.com/tour](https://teamcoco.com/tour). He sold Team Coco to SiriusXM in 2022 for a reported $150 million. He's having the best post-late-night career in television history. Have you subscribed to the podcast? Because you should."*

The voice is unapologetic, the facts are real, the framing is performative. **The bit is the demo.**

---

## How it's built

```
data/
├── conan.db          ← 11 MB SQLite hypergraph (nodes + edges + name_aliases)
├── schema.sql        ← the DDL (committed for review)
├── bw_seed.jsonl     ← 11,446-ticket bw import file
└── conaf_regulars.json  ← CONAF YouTube appearance counts per person

scripts/
├── build_hypergraph.py        ← regenerates conan.db from IMDb extract (personal QA only)
├── compile_conaf_regulars.py  ← yt-dlp metadata pull of the CONAF playlist
├── seed_bw.py                 ← conan.db → bw_seed.jsonl
└── scout_passive_feed.py      ← Google News RSS → corpus name matches

lib/
├── extract_names.py  ← entity extraction against name_aliases
└── feed_fetch.py     ← RSS/Atom parser with stable news_id per item

.claude/skills/       ← the 6 agent skills
```

---

## Honest caveats

- **Late Night & Tonight Show full episodes aren't streamable anywhere.** Conan personally curates clips; old monologue topical material doesn't all hold up. Team Coco's YouTube channel has the bits he stands behind; full episodes aren't on Peacock or Max. The agent knows this and frames it as a curation choice, not a limitation.
- **CONAF audio back-catalog isn't programmatically transcribable for free.** The public RSS feed has the most recent ~30-50 episodes. Older episodes need a SiriusXM Podcasts+ subscription ($5.99/mo) to access the subscriber RSS, OR they remain metadata-only with link-outs to Apple Podcasts / Spotify. The corpus reflects this honestly.
- **Privacy is about acquisition, not propagation.** The agent doesn't scrape private accounts or aggregate dossiers. But it does propagate anything that comes through Google News' aggregation — including personal stories celebrities have chosen to discuss publicly. We trust the aggregator's public/private discrimination.
- **Conan's comedy bits look predatory and aren't.** Stalker-boss bits, performance-review humiliations, Triumph insults, *Must Go's* fan-stalking premise — these use predatory framing as the joke. The subjects are professional co-performers. The agent engages with them as comedy, not as concerning content.

---

## License & attribution

[MIT](LICENSE), copyright (c) 2026 Denson Smith.

`bw` itself is also MIT, by [jallum](https://github.com/jallum).

This demo was developed and tested in **Claude Code Desktop**, but the lite tier (paste-the-URL path above) works with any AI that can fetch a URL. The full agent team (`/loop` orchestrator) requires CCD.
