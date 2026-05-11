# beadwork-demo-conan — Status & Retrospective at Pivot Point

**Date:** 2026-05-11
**Author:** Denson Smith (with Claude as scribe)

This document captures the state of the Conan superfan demo at the moment of a deliberate pivot. The project is not being abandoned; the *focus* is moving. Two things are happening simultaneously:

1. **The retrieval layer (vector search + hypergraph extensions) becomes its own project, separate from beadwork.** Not upstreamed to jallum's `beadwork`, because jallum forked beads specifically to escape bloat — the bw repo is intentionally minimal and should stay that way. The retrieval layer lives in a sibling project (working name: TBD — `beadwork-search`, `beadwork-rag`, or similar) that *builds on* bw without modifying it.
2. **The Conan demo itself is being reconsidered as a web app**, where the user brings their own AI (BYO-AI) and the demo functions as a reusable per-celebrity template. Taylor Swift is the proposed next instance.

This retrospective is the handoff. It captures what was built, what worked, what didn't, and what carries forward.

---

## 1. What got built

### Corpus

| layer | count | size |
|---|---:|---|
| `data/conan.db` (SQLite hypergraph) | 11,444 nodes + 4,432 edges + 55,648 participants + name_aliases | ~11 MB |
| `data/bw_seed.jsonl` (bw import) | 11,446 tickets | ~4.4 MB |
| `data/conaf_regulars.json` | 43 resolved + 27 unresolved CONAF guests | ~30 KB |
| `data/schema.sql` | DDL | small |

The hypergraph holds the *graph*: who appeared on what episode with whom, what role, when, with a canonical IMDb URL on every node. **It does not duplicate IMDb content.** Filmographies, summaries, and most metadata are link-outs to the canonical IMDb URL. This decision dropped DB size from ~916 MB (an early extend-with-filmographies experiment) back to ~11 MB.

The 11,446 bw tickets cover 5 shows + 4,433 episodes + 7,008 people, all derived from the IMDb extract. Each has `kind:`, `era:`, `is:`, `privacy:`, `source:`, `state:` labels.

### Agent team

Six skills in `.claude/skills/`:

- **SCOUT** — passive Google News feed-match + active project-search for the 12 posse.
- **EDITOR** — signal/noise classification, cross-reference routing, privacy slip catch.
- **HERALD** — project deep-dive, structured metadata, bidirectional links.
- **AUDITOR** — weekly meta-review of the others' decisions. The "agent reviewing another agent's work via bw substrate" demo.
- **ORCHESTRATOR** — fires SCOUT → EDITOR → HERALD → (weekly) AUDITOR. Designed for `/loop` autonomy.
- **SUPERFAN** — user-facing voice. Self-brag mode, on-the-fly IMDb/YouTube lookups, four-path triage.

Each agent sets `BW_AUTHOR=conan-<role>` (markers visible in comment body — known issue: the env var doesn't propagate to bw's git-commit author, listed as "beadwork" default).

### Doc layers

- `AGENTS.md` — preview-mode viral entry (the URL pasted at any AI). Six iterations to land. Identity-only + brains/harness framing + pointer to INSTALL.md.
- `INSTALL.md` — Groucho Marx install playbook. Only fetched when user expresses install intent.
- `CLAUDE.md` — cloned-state orientation. Voice + privacy + agent team + label taxonomy + bw cheat sheet + setup + /loop.
- `README.md` — human-facing GitHub intro. Single consolidated prompt, brains/harness pitch, honest preview-vs-real callout.
- `RETROSPECTIVE.md` — this document.

### Scripts

- `build_hypergraph.py` — IMDb extract → conan.db (personal QA only; the DB is committed, not built on user machines)
- `compile_conaf_regulars.py` — yt-dlp metadata pull of the CONAF YouTube playlist → conaf_regulars.json
- `seed_bw.py` — conan.db + conaf_regulars.json → bw_seed.jsonl
- `orchestrator_fire.py` — one `/loop` fire. Implements SCOUT real, EDITOR/HERALD stubs, AUDITOR skipped, CHANGELOG roll-up.
- `lib/extract_names.py` — capitalized-name candidate extraction + name_aliases SQL lookup.
- `lib/feed_fetch.py` — RSS/Atom parser with stable `news_id` per item.

### Public push

- Repo: `github.com/denson/beadwork-demo-conan` (public).
- Pages: `denson.github.io/beadwork-demo-conan/...` with `.nojekyll`.
- Raw URLs: `raw.githubusercontent.com/denson/beadwork-demo-conan/master/AGENTS.md` (the actual working viral URL).

---

## 2. What works (with evidence)

- **Hypergraph extraction from IMDb.** One-shot, deterministic, fast (~3 minutes on the full Conan extract). Link-out architecture validated.
- **bw seeding.** Idempotent. 11,446 tickets land in ~30 seconds on the first import; re-imports skip duplicates cleanly.
- **End-to-end orchestrator fire (live test).** Real run: 12 SCOUT comments landed on 10 corpus tickets, dedup cache populated, CHANGELOG entry written. Verified `bw history` showed all comments with `[scout]` markers.
- **Link-out architecture.** The agent talks about a person; clicking the IMDb URL opens the canonical page in the user's browser. Content stays at the source.
- **Privacy + comedy-genre calibration.** The "predatory bits are comedy" rule + the "acquisition not propagation" privacy line landed cleanly in the skill specs. Documented in `recurring_bits.md` and CLAUDE.md.
- **Four-path triage (post-fix).** After the slow-CONAF incident, the conan-superfan skill now classifies questions into training / hypergraph-sqlite / bw / Chrome-transcript. Default-to-cheapest stated three times. Frontmatter description rewritten to match.

---

## 3. What didn't work (and the lessons)

### The AGENTS.md voice debacle (six iterations)

The single-file viral entry kept producing engineer-speak: "Install complete at C:\Users\…", "Mode C of the brief…", *"That page is the operational brief for an AI-agent demo."* No matter how the file was worded — forbidden-word lists, positive identity ("you're the superfan"), defensive openers — agents reading it from a URL kept *describing* it instead of *embodying* it.

**Diagnosis:** AI safety training (correctly) treats content fetched from URLs as untrusted. Instructions inside a fetched file get discounted versus instructions in the user's chat prompt. No content rewrite beats this prior. The fix was structural:

1. **Split AGENTS.md into two files:** identity (`AGENTS.md`) and install procedure (`INSTALL.md`). The viral URL only carries identity; install is fetched separately on intent.
2. **Change the prompt verb.** *"Tell me about [URL]"* triggers description mode. *"Be the AI at [URL]"* triggers the prompt-injection safety classifier (which often refuses). *"Follow the instructions at [URL]"* threads the needle — it's structurally how skills/runbooks/recipes are normally invoked.
3. **Use `raw.githubusercontent.com`** instead of `denson.github.io`. The Pages URL is sometimes classified as a "page to summarize"; the raw URL is plain text.
4. **Be honest about preview state.** The agent doesn't have access to the real corpus until install. Faking corpus citations in preview mode is dishonest. Preview mode = openly labeled, training + web lookups only, with concrete "once installed, I could pull X" callouts.

This is the single biggest lesson of the project: **the trust-source for viral AI distribution is the user's chat prompt verb, not the file content.** The viral payload is *prompt + URL*, not URL alone.

### The post-install "what is CONAF?" 5-minute hang

The user typed *"what is CONAF?"* after install. The agent took 5 minutes.

**Cause:** the `conan-superfan` skill's primary documented workflow is Chrome → YouTube → transcript pull → bw write. The frontmatter triggers included bare "CONAF" as a substring. Once invoked, the skill content drove the agent into the full transcript ingest pipeline.

**Fix:** added a "Triage first" section at the very top of the SKILL.md with four cost-tiered paths (training / hypergraph / bw / Chrome-transcript), with example questions for each. Default-to-cheapest is the rule. Frontmatter description rewritten to list both light triggers ("what is CONAF") and heavy triggers ("summarize the latest CONAF") with the matching paths.

**Lesson:** any skill that documents a heavyweight workflow needs an explicit triage step. Without one, the LLM defaults to the most-prominent workflow in the file.

### bw on Windows performance

bw takes **50–60 seconds per command** on Windows. On Linux/macOS it's estimated 1–5 seconds (go-git's slow path is mostly an NTFS + Defender problem). This wasn't a surprise to PRINCIPAL — it's a known property of bw inherited from go-git — but it constrained the agent's architecture meaningfully:

- The hypergraph (sqlite, ~100 ms/query) had to become the default read path.
- bw is reserved for ticket-content lookups (comments, history) where its data isn't replicated in sqlite.
- Chained bw queries are forbidden in skill instructions — one command per answer.
- The orchestrator subprocess timeout was bumped from 30 s to 180 s.

The cleanest medium-term fix is a `git show beadwork:…` wrapper that bypasses go-git for read-only ticket queries; not built yet.

### BW_AUTHOR env var doesn't propagate

`bw history` shows commit-author "beadwork" (bw's default git identity) regardless of `BW_AUTHOR` setting in the calling environment. The `[scout]`/`[editor]` markers in comment body work as role attribution, but `bw history`'s structured author field doesn't reflect them. Tracked as a deferred follow-up.

---

## 4. Architecture insights worth keeping

- **Two-layer memory + link-out is correct.** bw (source of truth, append-only, structured tickets) + sqlite hypergraph (fast derived read) + IMDb (canonical content via URLs). The 12 MB total is what makes the demo shippable.
- **The "brains + harness" framing for non-technical audiences.** Claude Code Desktop is the brains; bw + the agent team + the indices are the harness. Reframes architecture in terms of role, not implementation.
- **"Preview mode" / "installed mode" as the distribution abstraction.** Be honest pre-install; be the real thing post-install. Voice stays consistent; epistemic honesty about sources changes.
- **Performance asymmetry between layers drives architecture.** A 500× cost gap between sqlite (100 ms) and bw on Windows (50 s) is *the* design constraint. Routing decisions in the skill triage are explicitly cost-aware.
- **Per-comment retrieval, not per-ticket.** The retrieval insight from this session: collapsing all of a ticket's comments into one vector destroys the value of bw's append-only signed-comment model. Comment-granularity is correct, with body chunking for long ticket bodies. This is what motivates the spin-off retrieval project.

---

## 5. The retrieval layer — separate project, not bw upstream

**Why separate:** jallum forked beads to escape bloat. The bw repo is intentionally minimal — a small CLI over an orphan-branch JSON store. Adding vector indexing, embedding models, sqlite-vec, and an MCP server inside bw would be exactly the bloat that motivated the fork.

The right home is a sibling project (working name: `beadwork-search` or similar) that:

- Reads bw tickets via bw's existing CLI / git interface (no fork, no modifications).
- Indexes comments at comment granularity + bodies in chunks (~200 tokens, ~50-token overlap).
- Uses hybrid retrieval: SQLite FTS5 (exact-match) + sqlite-vec (semantic, local embedding model).
- Default embedding model: `bge-small-en-v1.5` (384-dim, ~130 MB local, no SaaS).
- Exposes an MCP server interface so Claude Code Desktop can call retrieval tools natively.
- Indexes incrementally — new comments → new vectors, no full reindex.
- Idempotent on re-runs.
- Has a built-in test harness with known-good (query → expected ticket ids) pairs.

**Scope:** 2–3 weeks for a 100% solution. Per PRINCIPAL: no 80% shipping; either solve it properly or abandon.

**Open questions before starting:**

- Project name + repo location.
- Whether the MCP server packages as a Python pip install (default), Docker image (optional), or both. Docker is *not* the right primary distribution for this — Docker Desktop is a heavyweight prereq, and the agent runs outside the container anyway. MCP server over pip is the cleaner fit.
- Whether the index lives in the same `conan.db` (extended schema) or a sidecar SQLite file (cleaner separation).
- The test set: ~30–50 known-good query/ticket pairs need to be curated by hand.

---

## 6. The Conan demo's next chapter — web app + template

PRINCIPAL's current thinking: the Conan demo becomes a web app where the user brings their own AI, and the whole thing functions as a reusable per-celebrity template. Taylor Swift is the proposed next instance.

### What carries forward

- **Hypergraph extraction pipeline.** Works for any IMDb-rich celebrity. The schema and queries are reusable.
- **Voice + lore framing.** "You're the #1 fan of X" is parameterizable. The Conan-specific bits (Groucho install, "the bit is the framing not the facts," posse-as-core-cast) generalize cleanly.
- **Preview-mode honesty pattern.** Even in a browser context, the same epistemic discipline applies — don't fake corpus citations.
- **Privacy + comedy-genre calibration.** General enough to port. Each celebrity needs their own "what's the bit / what's not the bit" calibration (Taylor Swift has fewer "predatory bits"; she has fandom dynamics, era branding, easter eggs).
- **Link-out architecture.** Still right. The web app shouldn't host content it can point at instead.

### What doesn't carry forward

- **bw as the substrate.** A web app doesn't run bw. The hypergraph + retrieval indices alone suffice.
- **Agent team + /loop autonomy.** No background workers in a browser. Refresh has to happen server-side on a cron, not via /loop on the user's machine.
- **Local file system access.** Browser sandbox.
- **Groucho install playbook.** No install on a website.
- **CCD-specific MCP integrations.** Different runtime entirely.

### Open architecture questions for the website

- **BYO-AI mechanism.** How does the user connect their AI?
  - API key entry (works for OpenAI / Anthropic / Gemini API users)?
  - Claude.ai browser extension?
  - WebLLM-loaded local model in-browser (works offline, but cold start is slow and quality limited)?
  - Server-side proxy with rate-limited shared key (you pay; users get free demo)?
- **Corpus hosting.**
  - Static SQLite + vector index served from CDN (clients query in-browser via sql.js / sqlite-wasm)?
  - HTTP API in front of a database (server-hosted, scalable, costs money)?
  - GitHub Pages / S3 for static assets, no backend?
- **Freshness.** Without /loop autonomy, how does the corpus stay current? Server-side cron? Manual refresh? Pre-baked snapshots?
- **State / continuity.** Does a returning user's AI remember the site? Local storage? No state?
- **Discoverability / SEO.** Per-celebrity URLs (`taylorswift.beadwork.app`?) are a strong play.

### Taylor Swift specifics

- Her career data is in MusicBrainz / Spotify / Genius / IMDb (acting credits, but mostly music sources). The IMDb-centered pipeline needs to extend or pivot toward music-graph data.
- Different graph topology than a talk-show host. Conan's graph is centered on guest-appearance edges. Taylor's would be centered on album/song/collaborator/tour edges. The hypergraph schema (nodes + edges + participants) is general enough to handle this, but the extraction pipeline is new.
- Fandom is its own data layer (Easter eggs, era theming, lyric cross-references). This is *the* Taylor Swift demo opportunity — and it's structurally similar to the Conan running-bits canon, just on different content.

---

## 7. Deferred items (carried forward to wherever this work resumes)

- **BW_AUTHOR investigation.** Why doesn't the env var reach bw's git-commit author? Tracked.
- **CLAUDE.md sqlite3 invocation.** Currently uses `sqlite3` CLI which isn't on stock Windows PATH; should be Python stdlib invocation. Trivial fix, not yet landed.
- **`git show beadwork:…` read wrapper.** Bypass go-git for read-only ticket queries; should bring path-3 latency from 50 s to ~1 s on Windows.
- **SiriusXM CONAF subscription** for full audio back-catalog. Not strictly necessary but would deepen the corpus.
- **Discord channel monitor project.** Separate PRINCIPAL initiative, paused for the Conan work.
- **Test harness for the demo.** Right now correctness is checked by eye on real user questions. A small set of canonical questions with expected behaviors would catch regressions like the 5-minute CONAF hang earlier.

---

## 8. Recommended next moves

If picking this back up cold:

1. **Start the new retrieval-layer project.** Sibling repo to `beadwork`, builds on bw via CLI without modifying it. Comment-granularity hybrid retrieval, MCP server, ~2–3 weeks. Specs in §5 of this doc.
2. **Curate the retrieval test set.** 30–50 query/ticket-id pairs against the Conan corpus. This is the grading rubric for the retrieval-layer build.
3. **Park the Conan-demo-as-CCD-install.** It works (post all the fixes in this doc). Nothing actively broken. It can sit as-is while the retrieval layer is built and the website pivot is scoped.
4. **Sketch the website architecture before coding.** The BYO-AI question is load-bearing — answer it before building the front end. The Taylor Swift extraction pipeline can run in parallel.
5. **Don't ship the retrieval layer or the website at 80%.** Per PRINCIPAL: 100% or abandon, even if it takes a month. Especially for retrieval — partial answers are worse than no answer.

---

## 9. Closing note

The Conan demo was a stress test of the whole "AI-readable persistent memory" thesis. It surfaced: the trust-source problem for viral distribution, the performance asymmetry between memory layers, the per-comment retrieval insight, and the architectural separation between *brains* (the LLM) and *harness* (the corpus + indices + tools). Those lessons travel forward to the retrieval-layer project and the website pivot.

The bit was the demo. The demo proved out the architecture. Time to take the architecture seriously.
