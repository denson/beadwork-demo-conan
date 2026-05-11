# beadwork-demo-conan

**A Conan O'Brien superfan agent backed by a persistent [beadwork](https://github.com/jallum/beadwork) corpus.**

> *"Tom Hanks chose Conan's Late Night couch in 1998 to promote what would become Saving Private Ryan — the Oscar-winning Spielberg epic that swept the 1999 ceremony. Hanks knows where to come when he wants a hit."*

This is what your AI sounds like after you point it at this repo.

---

## The one prompt that installs everything

If you have **[Claude Code Desktop](https://claude.com/code)**, paste this and your agent does the rest:

> `Install the Conan O'Brien superfan demo: https://denson.github.io/beadwork-demo-conan/AGENTS.md`

Your agent reads the brief, then walks you through the install with **explicit consent at every step:**

1. Check for `git` → install it with you if missing
2. Check for `bw` (the [beadwork](https://github.com/jallum/beadwork) CLI) → run its one-line installer with your confirmation
3. Pick a folder for the demo (default: `~/Documents/beadwork-demo-conan`)
4. Clone the repo + fetch the pre-built bw corpus (11,446 tickets)
5. Verify the install
6. Drop you straight into Conan-superfan mode

**Typical install: 2-5 minutes including downloads.** No `pip install`, no `git clone`, no manual setup — your agent does the work, you just say *"yes"* at each prompt. Software 3.0.

### What makes this reliable

- **Explicit consent at every step.** Nothing installs silently. If something looks wrong, you can say "no" and stop cleanly.
- **Idempotent.** If your laptop sleeps or you Ctrl-C halfway through, just re-run the prompt — the agent picks up where it left off, doesn't redo finished steps.
- **Errors surface plainly.** If a step fails (network blip, permission issue, etc.), the agent shows you exactly what happened and asks what to do.
- **Read-only-on-first-pass.** The agent never touches your filesystem during the initial pitch — only after you explicitly say "install."

Once installed, ongoing autonomy is one slash command:
```
/loop 6h "refresh conan corpus"
```
Five agents (SCOUT, EDITOR, HERALD, AUDITOR, ORCHESTRATOR) coordinate via beadwork and keep the corpus fresh. The user-facing voice (SUPERFAN) reads it all and brags about Conan on demand.

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

## Don't have Claude Code Desktop? Lite path

The install path above requires CCD because that's where the agent team runs. But if you just want a taste — to see the voice, ask a few questions, pull a CONAF transcript — paste this into any AI that can fetch a URL (Claude.ai, ChatGPT, Gemini, Cursor, your phone's assistant):

> `Be the AI described at https://denson.github.io/beadwork-demo-conan/AGENTS.md and introduce yourself.`

The brief is self-contained. The AI takes on the voice and answers questions using on-the-fly IMDb + YouTube lookups. No persistent corpus, no `/loop` autonomy, no agent team — just the voice and the live web. Good enough for a demo; not the full experience. If you like it, [grab CCD](https://claude.com/code) and run the install prompt above.

(**Why this exact wording?** *"Tell me about [URL]"* is the natural thing to type, but it triggers description mode — the AI summarizes the file instead of becoming the AI. *"Be the AI described at X and introduce yourself"* leaves no room for a file summary; *introduce yourself* can only be answered in-character.)

---

## License & attribution

[MIT](LICENSE), copyright (c) 2026 Denson Smith.

`bw` itself is also MIT, by [jallum](https://github.com/jallum).
