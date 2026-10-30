# SignalBrief — Team Project 4, M3 Multi-Agent System

**Problem:** people who follow a few niche interests either check several sites every day or trust AI summaries that can't show where a claim came from.

**SignalBrief** is a personal daily newsletter. You give it up to 10 topics (new VST plugins, an artist's new music, cancer research, …). For each topic, three agents research, write and fact-check a short section, and **every bullet links to the source it came from**. A memory of what you were already sent keeps yesterday's news out of today's brief.

> CEN 4930 AI Agent Studio · Team Project 4 · Milestone 3. The architecture diagram, evaluation plan, cost model, sustainability analysis and user testing plan are in the PDF report (`TeamProject4_M3.pdf`), not this repo.

## What it does right now

For each topic in `topics.json`:

| Step | Who | What happens |
|---|---|---|
| 1 | **Scout agent** (ReAct) | Checks coverage memory (`recall_coverage`), then searches Google News, PubMed or MusicBrainz through our MCP server. It thinks before each tool call and reads each result before deciding to search again or stop. At most **3 source calls, enforced in code**. It answers with the ref ids worth reporting. |
| → | **Handoff 1** (code) | Builds a `ResearchPacket` from the records the tools **actually returned** for those refs. Drops refs no tool returned and stories already sent (ChromaDB match). **Trigger:** at least one fresh, verified candidate is left; otherwise the topic ends with "No notable updates" and no more model calls. |
| 2 | **Editor agent** | Writes 0–4 plain-English bullets for this reader, citing `[ref]` ids only. |
| → | **Handoff 2** (code) | Sends each bullet plus the headline, outlet, date and type of every source it cites. |
| 3 | **Fact-checker agent** (chain-of-thought) | Lists each claim (`in_source` true/false), checks it against the cited headline, then rules: `supported` (keep), `overstated` (rewritten without the extra detail), `unsupported` (dropped). Code won't accept `supported` if the checker's own claim list or reasoning says something isn't in the source. |
| 4 | Code | `citations.py` swaps ref ids for real links. Published sources are saved to memory. |

The console shows the ReAct steps (`[react n] THOUGHT / ACTION / OBSERVATION`), both handoffs with what was passed, each verdict with its reasoning, and token usage per agent. Each run also saves `output/runs/run_<timestamp>.json` with the full trace, handoff payloads, verdicts and token counts.

### Not implemented yet (on purpose)

- Email delivery and a daily schedule. The newsletter is a Markdown file plus console output.
- Reading full article text. The agents see headlines and metadata only.
- Reader feedback ("more/less like this") and per-reader preferences in memory.

## Setup

Python 3.11+.

```bash
python -m venv venv
venv\Scripts\activate            # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # macOS/Linux: cp .env.example .env
```

Put your course NRP token in `.env` (`NRP_API_KEY=...`). The model defaults to NRP's `gpt-oss`; set `SIGNALBRIEF_MODEL` to try another.

The course `AI-Agent-Workflows` venv already has every package (tested with openai-agents 0.22.0 and chromadb 1.5.9), so you can activate it and skip `pip install`. **First run:** ChromaDB downloads its local embedding model (all-MiniLM-L6-v2, about 80 MB) once.

## Run it

```bash
python signalbrief_agent.py                         # all topics in topics.json
python signalbrief_agent.py --only VST              # just one topic
python signalbrief_agent.py --topics other.json
python signalbrief_agent.py --memory-dir memory_demo --no-memory-write   # demo without touching real memory
```

The newsletter prints at the end and is saved to `output/newsletter_YYYY-MM-DD.md`. Memory lives in `memory/` (gitignored). Delete that folder to start fresh. Run the same topic twice to see memory at work: the second run skips stories the first one sent.

### Web UI

```bash
python web_app.py        # open http://127.0.0.1:8000
```

A newspaper-style page: edit topics (name, kind, lookback days, why) and press **Run the presses**. The **Wire Room** terminal streams the full agent output live. When the run ends, **Today's Edition** shows the newsletter. Standard library only. The page runs `signalbrief_agent.py` on just the topics you entered (saved to `output/web_topics.json`), one run at a time, and stops the run if you close the tab.

Topic format (`topics.json`): `name`, `kind` (`news`, `artist` or `research`, a hint for which tool fits), `query`, `days` (lookback window), `why` (why the reader cares).

## Architecture

```
topics.json
   │
   ▼
Scout agent (ReAct) ──MCP──► news_mcp_server.py    search_news / search_research_papers / get_artist_releases
   │               ──MCP──► memory_mcp_server.py  recall_coverage ──► ChromaDB (memory/)
   │  tool budget: MCP tool filter hides tools once 3 source / 1 memory calls are spent
   ▼
HANDOFF 1 (pipeline.build_research_packet) ── checks refs vs tool output, memory.find_match
   ▼
Editor agent ──► HANDOFF 2 (pipeline.build_factcheck_request) ──► Fact-checker agent
   ▼
pipeline.apply_verdicts ──► citations.verify_and_link ──► newsletter.md ──► memory.remember
```

| File | What it is |
|---|---|
| `signalbrief_agent.py` | Orchestrator: the 3 agents, their prompts, tool budget hooks, both handoffs, newsletter and run log. |
| `pipeline.py` | Plain-code logic: `ToolBudget` + MCP tool filter, ReAct trace, handoff payload builders, verdict handling. |
| `news_mcp_server.py` | MCP server (FastMCP, stdio): Google News RSS, PubMed, MusicBrainz. Free, no extra keys. |
| `memory_mcp_server.py` | MCP server: read-only `recall_coverage` over the coverage memory. |
| `memory_store.py` | ChromaDB coverage memory: `remember`, `recent`, `find_match` (same URL, or same story with cosine distance ≤ 0.35). |
| `citations.py` | Citation guardrail: ref ids → links; drops bullets that cite nothing a tool returned. |
| `tests/` | `test_cases.json` (inputs + expected outputs) and `run_tests.py`. |

**Why the handoffs are code, not `transfer_to_…` tools:** we tested gpt-oss with a structured output type and MCP tools together. It skipped the tools entirely and returned four invented plugins with made-up ref ids. So the Scout only names ref ids, and code builds every handoff payload from real tool records. A model can't pass along a source that no tool returned.

**Why ReAct:** the Scout's job is a tool loop: decide what's missing, call one tool, read the result, then search again or stop. The Thoughts are gpt-oss's own reasoning output, captured from the run. The Fact-checker uses chain-of-thought (it lists claims before giving a verdict) because it judges text instead of calling tools. We didn't add the sequential-thinking MCP server: it adds tool calls, and gpt-oss already made too many in M2.

**Why memory writes happen in code:** only bullets that passed the fact-checker and the citation guardrail are stored, so an invented claim can never become "already covered".

## Test cases

```bash
python tests/run_tests.py             # O1–O10: offline (no key; O5 needs the one-time embedding model)
python tests/run_tests.py --live      # + L1–L6: 3-agent pipeline, real tools + NRP model (~10 min)
python tests/run_tests.py --case L6   # offline + just the live cases you name
```

| ID | Tests | Expected |
|---|---|---|
| O1–O3 | MCP tool parsers on saved Google News / MusicBrainz / PubMed data | Window, de-duplication, links and dates correct |
| O4 | Citation guardrail | Real ref linked; fake ref + uncited bullet dropped |
| O5 | Coverage memory | Same URL and re-worded same story match; unrelated, other topic, and items older than 30 days don't |
| O6 | Handoff 1 | Packet holds only real records; invented and already-sent refs removed; `NONE` → no handoff |
| O7 | Handoff 2 + verdicts | Supported kept, overstated revised (ref restored), unsupported dropped, missing verdict counted as unchecked |
| O8 | Tool budget | After 3 source + 1 memory calls, the MCP filter hides those tools |
| O9 | ReAct trace | Thought → Action → Observation steps, then the answer |
| O10 | Verdict consistency | A `supported` verdict whose own reasoning or claim list says a claim isn't in the source is overridden and the bullet dropped |
| L1 | News topic, full pipeline | memory → search; ≤ 3 source calls; every published bullet fact-checked; 0 bad refs |
| L2 | Artist topic | `get_artist_releases` used; ≤ 3 source calls (M2 made 4–6) |
| L3 | Research topic | PubMed searched first; bullets fact-checked |
| L4 | Nonsense topic | No handoff; "No notable updates"; nothing invented |
| L5 | Two runs, same memory | Run 2 publishes none of run 1's sources |
| L6 | Fact-checker on seeded bullets | "Top-selling track of the week" (not in headline) is not `supported` after the code check; faithful paraphrase is |

Full inputs and expected outputs: `tests/test_cases.json`. Live cases check properties, not exact text, because the news changes daily.

## Known limitations and bugs

- **gpt-oss varies from run to run.** The same topic can give 0 or 4 bullets on different runs. In one run the Editor wrote a single bullet without a `- ` marker and it was thrown away. That's fixed: a line that cites a ref now counts as a bullet.
- **The fact-checker is strict and inconsistent.** It only sees headlines. In one run it marked all 4 VST bullets "overstated" for reader-relevance phrases like "adds classic tape saturation to mixes" and stripped them; in another run it accepted similar phrases. It did catch a real invented detail (a "20-year anniversary" the headline never mentioned).
- **The fact-checker once contradicted itself.** In live test L6 its reasoning said "top-selling track of the week – not mentioned in the source" and its verdict still said `supported`. We added a per-claim `in_source` list and a code check that overrides a self-contradicting `supported`. After that, L6 passed 3 of 3 runs; in those runs the model's own verdicts were already right, so the override was only exercised offline (O10). The text check looks for phrases like "not mentioned", so an oddly worded reasoning could slip past it or drop a good bullet. A wrong `supported` with consistent reasoning is not caught; no second judge checks the checker.
- **The tool budget can leave the Scout with nothing to say.** Once the budget hides every tool, gpt-oss once "wanted" another tool and returned an empty answer. The code now gives it one retry without tools. That retry path has not yet been seen to run in a live test.
- **Same-story matching is a threshold.** The 0.35 cosine cutoff was tuned on a handful of headlines (re-worded same story ≈ 0.07–0.21, unrelated ≈ 0.7). Two different stories about the same product could be merged, and a re-worded repeat could slip through.
- **Summaries come from headlines and metadata,** not article bodies. Google News links are redirects. Artist features rely on news search.
- **Three agents cost more and run slowly.** In our development runs a topic used 4–6 model requests and about 6K–11K tokens (most of it the Scout reading tool results), and took about 1–2.5 minutes. Topics run one at a time (MusicBrainz allows 1 request/second), so 10 topics can take 15+ minutes.

## CHANGES (M2 → M3)

| Change | Why |
|---|---|
| Split the single agent into **Scout → Editor → Fact-checker** | M2's one agent did research, writing and judging in one prompt. Separate roles let each be checked on its own, and the fact-checker targets M2's "top-selling track of the week" bullet, which cited a real source but claimed something the headline didn't say. |
| **Two explicit handoffs built in code** (`pipeline.py`) with a trigger | gpt-oss with structured output skipped the tools and invented sources, so payloads come from real tool records. Handoff 1 only fires when a fresh, verified candidate exists, which saves 2 model calls on quiet topics. |
| **ReAct Scout** with its Thought/Action/Observation trace logged | Makes the tool loop visible and testable; the trace is in the console and the run log. |
| **Chain-of-thought fact-checker** with structured verdicts | Claims are listed and checked one by one; overstated bullets are rewritten, not just deleted. |
| **Coverage memory** (ChromaDB + `memory_mcp_server.py`) | Fixes M2's "same story two days running" limitation. The Scout recalls past coverage over MCP; code also blocks repeats by URL or similar headline. |
| **Tool budget enforced in code** (dynamic MCP tool filter + run hooks, one tool call at a time) | M2 asked for "max 3 tools" in the prompt and the Kendrick topic made 4–6 calls (failed L2). |
| Scout retry when it ends with no answer | Seen in testing after the budget hid every tool. |
| Fact-checker lists claims with `in_source` flags; code overrides a `supported` verdict that contradicts them | Live test L6 failed: the checker's reasoning flagged the invented claim but its verdict said `supported`. |
| Editor output parsing accepts bullets without a `- ` marker | A whole topic was lost in testing because of a missing dash. |
| Run log `output/runs/*.json` with token usage per agent | Data for the M3 cost model and the M4 evaluation. |
| Tests grew from 8 to 16 (O5–O10, L5–L6 added; L1–L4 updated); `--case` runs single live cases | Cover memory, handoffs, verdicts, budget, ReAct trace and the fact-checker. |
| `requirements.txt` adds `chromadb`; `openai-agents>=0.22` | Memory layer; the dynamic MCP tool filter. |

## Team

Team Project 4, CEN 4930 (Fall 2026): Philippe Lucien, Paul Perez, Andrew Shinnick. See the PDF report for roles and contributions.

AI disclosure: code and documentation were drafted with help from Claude (Anthropic) and reviewed, run and tested by the team.
