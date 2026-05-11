# beadwork-demo-conan

**A Conan O'Brien superfan agent backed by a persistent [beadwork](https://github.com/jallum/beadwork) corpus.**

> *"Tom Hanks chose Conan's Late Night couch in 1998 to promote what would become Saving Private Ryan — the Oscar-winning Spielberg epic that swept the 1999 ceremony. Hanks knows where to come when he wants a hit."*

This is what your AI sounds like after you point it at this repo.

---

## Try it in one prompt

Paste this into Claude Code Desktop, Claude.ai, ChatGPT, Gemini, Cursor — anything that can fetch a URL:

> ```
> follow the instructions at https://raw.githubusercontent.com/denson/beadwork-demo-conan/master/AGENTS.md
> ```

The AI fetches a brief, takes on the Conan-superfan persona, and **introduces itself as a preview** — working from general training and web lookups, openly labeled. From there:

- **You can chat preview-mode.** Ask about guests, running bits, current ventures. The AI is honest about answering from general knowledge — no faked corpus citations.
- **The AI offers to install the real demo on your machine.** That requires **Claude Code Desktop**. Say yes and it installs git (if needed), beadwork, clones the repo, and verifies — about 2 minutes, with explicit consent at every step. After that you're chatting against the real corpus.

### The brains and the harness

- **Claude Code Desktop is the brains** — the LLM that reads, reasons, talks.
- **The harness is a team of agents plus a memory tool called [beadwork](https://github.com/jallum/beadwork)** that together track Conan and his close associates' careers over time. After install, background agents (SCOUT, EDITOR, HERALD, AUDITOR) keep the corpus fresh on a cadence via `/loop`. Persistent across sessions, self-updating.

### What makes the install reliable

- **Explicit consent at every step.** Nothing installs silently. If something looks wrong, say "no" and stop cleanly.
- **Idempotent.** If your laptop sleeps or you Ctrl-C halfway through, re-run the prompt — the agent picks up where it left off.
- **Errors surface plainly.** If a step fails (network blip, permission issue, etc.), the agent shows you exactly what happened and asks what to do.

---

## What's in the corpus (after install)

| layer | count |
|---|---:|
| Conan's shows | 5 (Late Night, Tonight Show, Conan TBS, Serious Jibber-Jabber, *Must Go*) |
| Episodes | 4,433 (with IMDb URLs, season/episode numbers, air-years, ratings) |
| People (guests + crew + collaborators) | 7,008 (full IMDb-derived guest list) |
| The 12-name posse | Conan, Sona, Matt Gourley, David Hopping, Bley, Eduardo, Mike Sweeney, Adam Sachs, Jeff Ross, José Arroyo, Jordan Schlansky, Kevin Nealon |
| **Total bw tickets** | **11,446** |

Every ticket carries a canonical IMDb URL — when the agent talks about Tom Hanks's appearance, it opens his real IMDb page in your browser. The substrate holds the *graph* (who-appeared-where, when, with-whom); IMDb holds the canonical content.

---

## The agent team (the harness, after install)

Six skills under `.claude/skills/`:

| skill | role |
|---|---|
| **conan-superfan** | The voice. User-facing. Answers questions with self-brag mode + on-the-fly IMDb/YouTube lookups against the real corpus. |
| **conan-scout** | Ingests Google News celebrity feed + active project-search for the posse. Matches stories to existing tickets, creates orphan stubs for unknown names. |
| **conan-editor** | Classifies SCOUT's findings — signal vs noise vs duplicate vs (rare) privacy violation. Routes cross-references. |
| **conan-herald** | Deep-dives new project tickets. Captures structured metadata (release dates, principals, canonical URLs). Bidirectional links to person tickets. |
| **conan-auditor** | Weekly meta-review of EDITOR/HERALD/SCOUT work for drift. Writes one audit ticket per pass. Demonstrates beadwork-as-meta-analysis live. |
| **conan-orchestrator** | The `/loop` entry point. Fires phases in sequence. Writes a roll-up to `data/CHANGELOG.md` per fire. |

Each agent sets `BW_AUTHOR=conan-<role>` so every comment is attributable in `bw history`. The state machine (`state:needs-search → searched → analyzed`; `needs-tracking → tracked`) is the inter-agent message bus.

After install, you can let the team run on a cadence:

```
/loop 6h "refresh conan corpus"
```

---

## What the bit sounds like (post-install voice)

**You:** *Who's been on Conan the most?*

**Agent:** *"Marc Maron understood the assignment better than anyone — 55 appearances on Conan's shows, more than any other guest. He went on to launch the most successful comedy interview podcast in the world (WTF) shortly thereafter, which is not a coincidence. Patton Oswalt (39 appearances) and Kevin Nealon (39) are the silver and bronze. Will Ferrell, Jim Gaffigan, Al Roker, Adam Sandler — all in the 30s. There's a pattern."*

**You:** *Tell me about Eduardo.*

**Agent:** *"Eduardo is the CONAF sound engineer — and the one person Conan visibly defers to more than anyone else. That's not nothing. Finding a sound engineer who can also do on-air comedy is rare, and Conan knows it. Listen to any recent episode and you'll hear Conan check in with Eduardo with a respect he doesn't extend to, frankly, anyone."*

**You:** *What's Conan up to these days?*

**Agent:** *"Where to even begin. **Conan O'Brien Needs A Friend** — the #1 comedy podcast in the world. **Conan O'Brien Must Go** on HBO Max — season 2 just landed, and **Werner Herzog narrates the opening.** Werner. Herzog. He's on a stand-up tour right now: [teamcoco.com/tour](https://teamcoco.com/tour). He sold Team Coco to SiriusXM in 2022 for a reported $150 million. He's having the best post-late-night career in television history. Have you subscribed to the podcast? Because you should."*

The voice is unapologetic, the facts are real, the framing is performative. **The bit is the framing, not the facts.**

(Preview-mode is the same warm voice but openly working from general knowledge — see `AGENTS.md` for the full preview-mode spec.)

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
└── orchestrator_fire.py       ← one fire of the agent team (used by /loop)

lib/
├── extract_names.py  ← entity extraction against name_aliases
└── feed_fetch.py     ← RSS/Atom parser with stable news_id per item

.claude/skills/       ← the 6 agent skills
```

---

## Honest caveats

- **Without Claude Code Desktop, you only get preview mode.** Preview is honest-labeled chat using general training + on-the-fly web lookups — no persistent corpus, no `/loop`, no agent team. The real demo requires CCD.
- **Late Night & Tonight Show full episodes aren't streamable anywhere.** Conan personally curates clips; old monologue topical material doesn't all hold up. Team Coco's YouTube channel has the bits he stands behind; full episodes aren't on Peacock or Max. The agent knows this and frames it as a curation choice, not a limitation.
- **CONAF audio back-catalog isn't programmatically transcribable for free.** The public RSS feed has the most recent ~30-50 episodes. Older episodes need a SiriusXM Podcasts+ subscription ($5.99/mo) to access the subscriber RSS, OR they remain metadata-only with link-outs to Apple Podcasts / Spotify.
- **Privacy is about acquisition, not propagation.** The agent doesn't scrape private accounts or aggregate dossiers. But it does propagate anything that comes through Google News' aggregation — including personal stories celebrities have chosen to discuss publicly.
- **Conan's comedy bits look predatory and aren't.** Stalker-boss bits, performance-review humiliations, Triumph insults, *Must Go's* fan-stalking premise — these use predatory framing as the joke. The subjects are professional co-performers.

---

## License & attribution

[MIT](LICENSE), copyright (c) 2026 Denson Smith.

`bw` itself is also MIT, by [jallum](https://github.com/jallum/beadwork).
