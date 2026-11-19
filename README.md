# SignalBrief — Team Project 4, M4 Evaluated Multi-Agent System

**Problem:** people who follow a few niche interests either check several sites every day or trust AI summaries that can't show where a claim came from.

**SignalBrief** is a personal daily newsletter. You give it up to 10 topics (new VST plugins, an artist's new music, cancer research, …). For each topic, three agents research, write and fact-check a short section, and **every bullet links to the source it came from**. A memory of what you were already sent keeps yesterday's news out of today's brief.

> CEN 4930 AI Agent Studio · Team Project 4 · Milestone 4. **Evaluation results file: [`eval/Testing Results_1.1.csv`](eval/Testing%20Results_1.1.csv)** (all 10 cases, pass rate 7/10, failure analysis). Agent improvements since M3: [CHANGES (M3 → M4)](#changes-m3--m4). The user testing report and pivot decision are in the PDF report.

## What it does right now

For each topic:

| Step | Who | What happens |
|---|---|---|
| 1 | **Scout agent** (ReAct) | Checks coverage memory (`recall_coverage`), then searches Google News, PubMed or MusicBrainz through our MCP server. It thinks before each tool call and reads each result before deciding to search again or stop. At most **3 source calls**, and only the tools that fit the topic kind (news → news search; artist → MusicBrainz + news; research → PubMed first, then news), **both enforced in code**. It answers with the ref ids worth reporting. |
| → | **Handoff 1** (code) | Builds a `ResearchPacket` from the records the tools **actually returned** for those refs. Drops refs no tool returned and stories already sent (ChromaDB match). **Trigger:** at least one fresh, verified candidate is left; otherwise the topic ends with "No notable updates" and no more model calls. |
| 2 | **Editor agent** | Writes 0–4 plain-English bullets for this reader, citing `[ref]` ids only. No facts or descriptors beyond the cited titles; research findings are attributed ("A study reports…"). |
| → | **Handoff 2** (code) | Sends each bullet plus the headline, outlet, date and type of every source it cites. |
| 3 | **Fact-checker agent** (chain-of-thought) | Lists each claim, including any added descriptor (`in_source` true/false), checks it against the cited headline, then rules: `supported` (keep), `overstated` (rewritten without the extra detail), `unsupported` (dropped). Code won't accept `supported` if the checker's own claim list or reasoning says something isn't in the source, asks again for any bullet it skipped, and never publishes an unchecked bullet. |
| 4 | Code | `citations.py` swaps ref ids for real links. Published sources are saved to memory. |

The console shows the ReAct steps (`[react n] THOUGHT / ACTION / OBSERVATION`), both handoffs with what was passed, each verdict with its reasoning, and token usage per agent. Each run also saves `output/runs/run_<timestamp>.json` with the full trace, handoff payloads, verdicts and token counts.

### Not implemented yet (on purpose)

- Email delivery and a daily schedule. The newsletter is a Markdown file, console output, or the web page.
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

Put your course NRP token in `.env` (`NRP_API_KEY=...`). The model defaults to NRP's `gpt-oss`; set `SIGNALBRIEF_MODEL` to try another. Tested with openai-agents 0.24.0 and chromadb 1.5.9. **First run:** ChromaDB downloads its local embedding model (all-MiniLM-L6-v2, about 80 MB) once.

## Run it

```bash
python signalbrief_agent.py                         # all topics in topics.json
python signalbrief_agent.py --only VST              # just one topic
python signalbrief_agent.py --topics other.json
python signalbrief_agent.py --no-memory-write       # demo without recording what was sent
```

The newsletter prints at the end and is saved to `output/newsletter_YYYY-MM-DD.md` (sample: `output/newsletter_2026-10-28.md`). Memory lives in `memory/` (gitignored). Delete that folder to start fresh. Run the same topic twice to see memory at work: the second run skips stories the first one sent.

Topic format (`topics.json`): `name`, `kind` (`news`, `artist` or `research`; decides which source tools the Scout may use), `query`, `days` (lookback window), `why` (why the reader cares).

### Web UI

```bash
python web_app.py                    # open http://127.0.0.1:8000
python web_app.py --password <pw>    # or SIGNALBRIEF_UI_PASSWORD in .env, before sharing a link
```

A newspaper-style page: type your name, set up to 3 topics and press **Run the presses**. The **Wire Room** streams the agent output live; **Today's Edition** shows the newsletter. Each reader name gets its own memory (`memory_web/<name>/`) and newsletters (`output/web/<name>/`). One run at a time; a second tester sees how long to wait; closing the tab stops the run. `Dockerfile` builds the same app for a container host (we deployed it to Google Cloud Run for user testing).

## Architecture

```
topics.json / web form
   │
   ▼
Scout agent (ReAct) ──MCP──► news_mcp_server.py    search_news / search_research_papers / get_artist_releases
   │               ──MCP──► memory_mcp_server.py  recall_coverage ──► ChromaDB (memory/)
   │  MCP tool filter: hides tools once 3 source / 1 memory calls are spent,
   │  and source tools that don't fit the topic kind
   ▼
HANDOFF 1 (pipeline.build_research_packet) ── checks refs vs tool output, memory.find_match
   ▼
Editor agent ──► HANDOFF 2 (pipeline.build_factcheck_request) ──► Fact-checker agent (+ one re-ask for skipped bullets)
   ▼
pipeline.apply_verdicts ──► citations.verify_and_link ──► newsletter.md ──► memory.remember
```

| File | What it is |
|---|---|
| `signalbrief_agent.py` | Orchestrator: the 3 agents, their prompts, tool budget hooks, both handoffs, newsletter and run log. |
| `pipeline.py` | Plain-code logic: `ToolBudget` + MCP tool filter (budget and topic kind), ReAct trace, handoff payload builders, verdict handling. |
| `news_mcp_server.py` | MCP server (FastMCP, stdio): Google News RSS, PubMed, MusicBrainz. Free, no extra keys. Retries on HTTP 429; `SIGNALBRIEF_FAULT` injects outages for testing. |
| `memory_mcp_server.py` | MCP server: read-only `recall_coverage` over the coverage memory. |
| `memory_store.py` | ChromaDB coverage memory: `remember`, `recent`, `find_match` (same URL, or same story with cosine distance ≤ 0.35). |
| `citations.py` | Citation guardrail: ref ids → links; drops bullets that cite nothing a tool returned. |
| `web_app.py`, `web/index.html` | Web UI (standard library server, streams the CLI's output). |
| `tests/` | Offline and live tests (`run_tests.py`, `test_cases.json`) and the M4 evaluation suite (`run_eval.py`, `eval_cases.json`). |
| `eval/` | M4 evaluation results and evidence; start with [`eval/README.md`](eval/README.md). |

**Why the handoffs are code, not `transfer_to_…` tools:** we tested gpt-oss with a structured output type and MCP tools together. It skipped the tools entirely and returned four invented plugins with made-up ref ids. So the Scout only names ref ids, and code builds every handoff payload from real tool records. A model can't pass along a source that no tool returned.

**Why ReAct:** the Scout's job is a tool loop: decide what's missing, call one tool, read the result, then search again or stop. The Thoughts are gpt-oss's own reasoning output, captured from the run. The Fact-checker uses chain-of-thought (it lists claims before giving a verdict) because it judges text instead of calling tools.

**Why rules live in code where possible:** the M4 evaluation showed gpt-oss breaking rules its prompts already state (wrong tool for the topic kind, research stated as fact). Rules that code can check (tool choice, citations, unchecked bullets) are enforced in code; the rest are prompt rules checked by the Fact-checker.

**Why memory writes happen in code:** only bullets that passed the fact-checker and the citation guardrail are stored, so an invented claim can never become "already covered".

## Tests and evaluation

```bash
python tests/run_tests.py             # O1–O11: offline (no key; O5 needs the one-time embedding model)
python tests/run_tests.py --live      # + L1–L6: 3-agent pipeline, real tools + NRP model (~10 min)
python tests/run_eval.py              # M4 evaluation E1–E10 (~1 hour; results to eval/latest/)
python tests/run_eval.py --only E4 E6 # selected evaluation cases
```

**Offline and live tests** (`tests/test_cases.json`):

| ID | Tests | Expected |
|---|---|---|
| O1–O3 | MCP tool parsers on saved Google News / MusicBrainz / PubMed data | Window, de-duplication, links and dates correct |
| O4 | Citation guardrail | Real ref linked; fake ref + uncited bullet dropped |
| O5 | Coverage memory | Same URL and re-worded same story match; unrelated, other topic, and items older than 30 days don't |
| O6 | Handoff 1 | Packet holds only real records; invented and already-sent refs removed; `NONE` → no handoff |
| O7 | Handoff 2 + verdicts | Supported kept, overstated revised (ref restored), unsupported dropped, a bullet with no verdict left out |
| O8 | Tool budget | After 3 source + 1 memory calls, the MCP filter hides those tools |
| O9 | ReAct trace | Thought → Action → Observation steps, then the answer |
| O10 | Verdict consistency | A `supported` verdict whose own reasoning or claim list says a claim isn't in the source is overridden and the bullet dropped |
| O11 | Topic-kind tool filter | News → news search only; artist → MusicBrainz + news; research → PubMed first, news only after a paper search |
| L1–L6 | Live: news, artist, research and nonsense topics; memory across runs; fact-checker on seeded bullets | See `tests/test_cases.json` |

**M4 evaluation** (`tests/eval_cases.json`, the 10 cases from the M3 evaluation plan): each live case runs 3 times and passes on ≥ 2/3 (E6: 5 runs, ≥ 4/5). Code checks properties of each result; an independent critic agent (`qwen3`, a different model from the system's `gpt-oss`) scores every published bullet against its cited headline; two teammates did a human spot-check and a relevance/tone/framing review. **Baseline result: 7/10 (70%)**, below our 8/10 threshold; both hard gates held (0 invented citations, nonsense topic returns nothing). Results, failure analysis and evidence: [`eval/`](eval/README.md).

## Known limitations and bugs

- **The Editor still adds small details.** In the baseline the critic rated 53% of 108 bullets fully supported by their headline; most failures were one added descriptor ("synth", "T-cell"). Changes 3 and 4 below target this; their effect on the grounding score has not been measured yet.
- **gpt-oss doesn't always follow its prompt.** It broke the Scout's kind-to-tool rule and the Editor's single-study rule even though both were in the prompts. Tool choice is now enforced in code; wording rules can only be checked.
- **Cost and speed vary by day.** A 10-topic edition used 123K–139K tokens (budget 120K) and took 4.4–21.8 minutes in the baseline, depending on NRP's speed. Topics run one at a time (MusicBrainz allows 1 request/second; Google News rate-limits quick follow-up searches).
- **The Scout still sometimes ends with no answer** once its tool budget is spent; one retry without tools recovers it (6 retries in 27 baseline topic runs, 7 in 27 after the changes).
- **Cloud hosting blocks two sources.** From Google Cloud Run, Google News returned HTTP 503 and MusicBrainz dropped connections, so news and artist topics come back empty on a cloud host; PubMed works. Run locally (or behind a tunnel) for full coverage.
- **The fact-checker only sees headlines,** and is the same model as the Editor; the independent critic is used in evaluation only. Same-story matching uses a 0.35 cosine threshold tuned on a handful of headlines. Google News links are redirects.

## CHANGES (M3 → M4)

All changes are on branch `feat/updates1.2` (and `906feb1` on `main`), committed after the M3 submission (last M3 commit `10551ee`, 28 Oct 2026).

**How impact was measured.** *Before* = the M4 baseline: the full E1–E10 suite on the unchanged M3 agent (17–18 Nov, `eval/baseline/`). *After* = a rerun of E1–E8 (26 runs, 27 topic sections) with all five agent changes applied (18 Nov, `eval/after_1.2/eval_run.log`), compared with the same 26 baseline runs. E9, E10 and the human framing check were not rerun after the changes, so effects that only show there are marked "not measured". News changes daily, so small differences between runs are noise.

**Overall:** E1–E8 passed 26/26 runs after the changes, up from 24/26 in the baseline (E1 2/3 → 3/3, E3 2/3 → 3/3 on its automated checks). Invented citations stayed at 0.

### Agent changes, made because of the evaluation results

| # | Change (commit) | Why | Improved evaluation results? By how much |
|---|---|---|---|
| 1 | **Scout tool filter enforces the topic kind** (`b04d9ac`): news → news search; artist → MusicBrainz + news; research → PubMed first, news only after a paper search. New offline test O11. | gpt-oss ignored the kind-to-tool rule in its prompt: 4 of 21 non-artist E1–E8 runs (5 of 29 including E9) called the artist tool. That failed E3 run 1 and wasted calls and tokens in E9. | **Yes.** Wrong-tool calls 4/21 → **0/21** non-artist runs. E3 tool order 2/3 → **3/3** runs. |
| 2 | **Cheaper Scout retry** (`e6330fb`): the no-tools retry gets a one-line-per-record list instead of the whole conversation. | E9 was over its 120K-token budget in all 3 runs, and the Scout retried 2–3 times per edition; each baseline retry resent the full conversation (2,383–4,638 tokens, mean 3,513). | **Not measured.** E9 was not rerun, and the rerun log does not record per-retry tokens. Retries still happen (6 → 7 in 27 topic runs): the change makes them cheaper, not rarer. Tokens for E1–E4 and E7 combined: 159,337 → 152,113 (−5%), within normal run-to-run variation. |
| 3 | **Editor prompt** (`4b98046`): no descriptors the title doesn't use (with two examples from the baseline failures); every research bullet starts with an attribution ("A study reports…"); plain words instead of unexplained acronyms. | E10: 51 of 108 bullets failed grounding, 39 of them for one added detail. E3: two research bullets stated a study's result as fact. Raters scored research bullets 3.88/5 on tone for jargon. | **Not measured** on E10 or the human framing check (neither was rerun). In one smoke run after the change, all 3 research bullets opened with an attribution; one still added "CAR-T". |
| 4 | **Fact-checker prompt** (`9f9ea38`): added descriptors count as claims to check; an unattributed research result is `overstated` and rewritten with the attribution; a verdict for every bullet. | The same-model Fact-checker rated most bullets with added details `supported`, which the independent critic then failed; it also skipped 3 of 4 bullets once. | **Partly measured.** The checker got stricter: bullets ruled `overstated` 31/71 → **38/68** checked (44% → 56%), `unsupported` 5 → 0. E6 (seeded bullets) stayed 5/5. Effect on the E10 grounding score: not measured. |
| 5 | **Never publish an unchecked bullet** (`bec9554`): ask the checker again for skipped bullets; if still unchecked, leave the bullet out. O7 updated. | E1 run 3 published 3 bullets the Fact-checker never ruled on. | **Yes, for E1:** unchecked bullets published 3 → **0**, E1 2/3 → **3/3** runs. In the rerun the checker skipped no bullet, so the re-ask path was exercised only by the offline test (O7). |

### Other changes since M3 (tooling, web, deployment)

| Change (commit) | Why | Effect on evaluation results |
|---|---|---|
| **Evaluation suite** `tests/run_eval.py` + `tests/eval_cases.json`, with the `qwen3` critic agent (`7d9a455`) | The M3 tests (L1–L6) covered part of the plan; E7–E10 and the 3-run reliability rule had no code. | Made E7, E9 and E10 measurable; produced the baseline 7/10. |
| **Fault-injection switch** `SIGNALBRIEF_FAULT` in the news MCP server; the server now receives the full environment (`7d9a455`) | E8 (source outage) was marked "to build" in M3, after a real MusicBrainz 503 on 28 Oct. | Made E8 testable: 3/3 in the baseline and after the changes. |
| **Google News retry on HTTP 429** (`1dc47f8`) | A rate limit on quick follow-up searches emptied a topic in testing on 16 Nov. | None measured: the retry never fired during the evaluation (0 HTTP 429s). |
| **Web UI** (`906feb1`, Andrew) | User testing needed a page non-technical testers could use. | Not part of the agent pipeline. |
| **Web UI for testers**: separate memory and newsletters per reader, 3-topic cap, "try again in N minutes" message, optional password, live output through proxies; `--output` option on the CLI (`1dc47f8`) | Testers shared one memory, so one person's run hid stories from the next. | Not part of the agent pipeline. |
| **Container and Cloud Run deployment** (`Dockerfile`, `.dockerignore`, `.gcloudignore`; `1dc47f8`, `7b06d30`) | A permanent link for user testing that doesn't depend on a team member's PC. | Not part of the agent pipeline. Found that Google News and MusicBrainz block cloud servers (see limitations). |

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
