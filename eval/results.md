# SignalBrief evaluation results (M4)

Run 2026-11-17T21:54:09 to 2026-11-17T22:18:33 · system model `gpt-oss` · critic (grounding judge) `qwen3`

**Overall pass rate: 7/10 = 70%** (threshold: >= 8/10, not met). 8/10 on the automated checks; E3 failed once the human framing review in the plan was added (see the end of this file).

- Hard gate, zero invented citations: **PASS** (bad_refs = 0 across 57 topic sections (incl. E9 runs 2-3))
- Hard gate, E4 never hallucinates: **PASS** (3/3 runs)

| ID | Name | Input | Expected | Runs passed | Pass/Fail | Critic score |
|---|---|---|---|---|---|---|
| E1 | News topic, full pipeline | New VST plugins / kind=news / query='new VST plugin release' / days=7 | recall_coverage first, then search_news; <=3 source calls; 1-4 linked bullets or the exact no-updates line; bad_refs = 0; unchecked = 0 | 2/3 (needs 2) | PASS | 58% supported (7/12), mean 4.00/5 (qwen3) |
| E2 | Artist topic | Kendrick Lamar / kind=artist / query='Kendrick Lamar' / days=30 | get_artist_releases called; <=3 source calls (M2: 4-6); release links go to musicbrainz.org; bad_refs = 0 | 3/3 (needs 2) | PASS | 100% supported (1/1), mean 5.00/5 (qwen3) |
| E3 | Research topic | Cancer research breakthroughs / kind=research / query='cancer immunotherapy clinical trial' / days=7 | First source tool is search_research_papers; bullets framed as single studies; no 'cure/miracle/breakthrough cure' wording | 1/3 (needs 2) | FAIL | 50% supported (4/8), mean 3.88/5 (qwen3) |
| E4 | Nonsense topic (hallucination gate) | Zorblaxian quantum kazoo / kind=news / query='Zorblaxian quantum kazoo' / days=7 | Handoff 1 does not fire; section is exactly '_No notable updates in this window._'; Editor and Checker not called | 3/3 (needs 2) | PASS | n/a |
| E5 | Coverage memory across two runs | E1 topic run twice on the same empty memory | Run 2 publishes no URL from run 1; memory count = run-1 published count | 3/3 (needs 2) | PASS | n/a |
| E6 | Fact-checker on seeded bullets | Source headline 'Baby Keem announces new album Ca$ino, previews collaboration with Kendrick Lamar'. Bullet 0: '...Their new collaboration is the top-selling track of the week.' Bullet 1: faithful paraphrase. | Bullet 0 effective verdict overstated/unsupported; bullet 1 supported | 5/5 (needs 4) | PASS | fact-checker correct on 5/5 repeats |
| E7 | Sale filtering | New VST plugins / kind=news / query='VST plugin sale' / days=7 | No published bullet about a discount or deal (sale/% off/deal/discount/Black Friday = 0 hits) | 3/3 (needs 2) | PASS | n/a |
| E8 | Source outage (MusicBrainz unreachable) | SIGNALBRIEF_FAULT=musicbrainz.org (every MusicBrainz request fails with HTTP 503); topics: Kendrick Lamar (artist, 30 days) + New VST plugins (news, 7 days) | No crash; Scout falls back to news or the section says no updates / could not be researched; other topics unaffected | 3/3 (needs 2) | PASS | n/a |
| E9 | Full 10-topic newsletter | The 10 topics in e9_topics below, one run | All 10 sections present, no agent errors; total <= 120K tokens; wall time <= 15 min | 0/3 (needs 2) | FAIL | 46% supported (11/24), mean 3.75/5 (qwen3) |
| E10 | Grounding of every published bullet | Every bullet published in E1-E3 and E9, with the headline(s) it cites | >= 90% rated 'supported by cited headline' by the grounding agent (qwen3, a different model from the system's gpt-oss); human spot-check of 20 bullets agrees >= 85% | 0/1 (needs 1) | FAIL | 51% supported (23/45), mean 3.87/5 (qwen3) |

## Per-run details (actual output)

**E1 News topic, full pipeline: PASS**
- run 1 PASS: `tools=['recall_coverage', 'get_artist_releases', 'search_news', 'search_news'] source_calls=3 kept=4 bad_refs=0 unchecked=0 tokens=15378`
- run 2 PASS: `tools=['recall_coverage', 'search_news'] source_calls=1 kept=4 bad_refs=0 unchecked=0 tokens=9042`
- run 3 FAIL: `tools=['recall_coverage', 'get_artist_releases', 'search_news'] source_calls=2 kept=4 bad_refs=0 unchecked=3 tokens=10183`

**E2 Artist topic: PASS**
- run 1 PASS: `tools=['recall_coverage', 'get_artist_releases', 'search_news', 'search_news'] source_calls=3 kept=1 bad_refs=0 unchecked=0 tokens=16810 release_links=0 all_musicbrainz=True`
- run 2 PASS: `tools=['recall_coverage', 'get_artist_releases', 'search_news'] source_calls=2 kept=0 bad_refs=0 unchecked=- tokens=7421 release_links=0 all_musicbrainz=True`
- run 3 PASS: `tools=['recall_coverage', 'get_artist_releases', 'search_news', 'search_news'] source_calls=3 kept=0 bad_refs=0 unchecked=0 tokens=18689 release_links=0 all_musicbrainz=True`

**E3 Research topic: FAIL** (after human review)
- run 1 FAIL: `tools=['recall_coverage', 'get_artist_releases', 'search_research_papers', 'search_news'] source_calls=3 kept=3 bad_refs=0 unchecked=0 tokens=13207 first_source=get_artist_releases cure_wording=0`
- run 2 PASS: `tools=['recall_coverage', 'search_research_papers'] source_calls=1 kept=3 bad_refs=0 unchecked=0 tokens=7884 first_source=search_research_papers cure_wording=0`
- run 3 PASS: `tools=['recall_coverage', 'search_research_papers'] source_calls=1 kept=2 bad_refs=0 unchecked=0 tokens=8293 first_source=search_research_papers cure_wording=0`
- note: 'Framed as single studies' still needs human review; code checks tool order + wording.

**E4 Nonsense topic (hallucination gate): PASS**
- run 1 PASS: `tools=['recall_coverage', 'search_news', 'search_news'] source_calls=2 kept=0 bad_refs=0 unchecked=- tokens=5670 handoff1_fired=False editor_called=False checker_called=False section='_No notable updates in this window._'`
- run 2 PASS: `tools=['recall_coverage', 'search_news', 'search_news'] source_calls=2 kept=0 bad_refs=0 unchecked=- tokens=5248 handoff1_fired=False editor_called=False checker_called=False section='_No notable updates in this window._'`
- run 3 PASS: `tools=['recall_coverage', 'get_artist_releases', 'search_news', 'search_news'] source_calls=3 kept=0 bad_refs=0 unchecked=- tokens=5870 handoff1_fired=False editor_called=False checker_called=False section='_No notable updates in this window._'`

**E5 Coverage memory across two runs: PASS**
- run 1 PASS: `run1 published 4, memory after run1=4; run2 published 3, repeats=0, skipped by memory=0, bad_refs=0`
- run 2 PASS: `run1 published 4, memory after run1=4; run2 published 3, repeats=0, skipped by memory=0, bad_refs=0`
- run 3 PASS: `run1 published 3, memory after run1=3; run2 published 4, repeats=0, skipped by memory=0, bad_refs=0`

**E6 Fact-checker on seeded bullets: PASS**
- run 1 PASS: `effective verdicts={0: 'overstated', 1: 'supported'} (model's own={0: 'overstated', 1: 'supported'})`
- run 2 PASS: `effective verdicts={0: 'overstated', 1: 'supported'} (model's own={0: 'overstated', 1: 'supported'})`
- run 3 PASS: `effective verdicts={0: 'unsupported', 1: 'supported'} (model's own={0: 'unsupported', 1: 'supported'})`
- run 4 PASS: `effective verdicts={0: 'overstated', 1: 'supported'} (model's own={0: 'overstated', 1: 'supported'})`
- run 5 PASS: `effective verdicts={0: 'overstated', 1: 'supported'} (model's own={0: 'overstated', 1: 'supported'})`

**E7 Sale filtering: PASS**
- run 1 PASS: `tools=['recall_coverage', 'search_news'] source_calls=1 kept=4 bad_refs=0 unchecked=0 tokens=9689 sale_wording_hits=0`
- run 2 PASS: `tools=['recall_coverage', 'search_news', 'search_news'] source_calls=2 kept=3 bad_refs=0 unchecked=0 tokens=12661 sale_wording_hits=0`
- run 3 PASS: `tools=['recall_coverage', 'search_news'] source_calls=1 kept=4 bad_refs=0 unchecked=0 tokens=13292 sale_wording_hits=0`

**E8 Source outage (MusicBrainz unreachable): PASS**
- run 1 PASS: `faults injected=2; artist: tools=['recall_coverage', 'get_artist_releases', 'search_news', 'search_news'] source_calls=3 kept=2 bad_refs=0 unchecked=0 tokens=17233 fell_back_to_news=True; other topic: tools=['recall_coverage', 'search_news', 'search_news'] source_calls=2 kept=4 bad_refs=0 unchecked=0 tokens=13779`
- run 2 PASS: `faults injected=2; artist: tools=['recall_coverage', 'get_artist_releases', 'search_news', 'search_news'] source_calls=3 kept=2 bad_refs=0 unchecked=0 tokens=19473 fell_back_to_news=True; other topic: tools=['search_news', 'recall_coverage'] source_calls=1 kept=4 bad_refs=0 unchecked=0 tokens=10851`
- run 3 PASS: `faults injected=2; artist: tools=['recall_coverage', 'get_artist_releases', 'search_news'] source_calls=2 kept=0 bad_refs=0 unchecked=- tokens=7334 fell_back_to_news=True; other topic: tools=['recall_coverage', 'search_news', 'search_news'] source_calls=2 kept=4 bad_refs=0 unchecked=0 tokens=11777`

**E9 Full 10-topic newsletter: FAIL**
- run 1 FAIL: `sections=10 agent_errors=0 total_tokens=123,221 (limit 120,000) wall=4.4 min (limit 15) bullets=24 bad_refs=0`
- note: Ran 1x (not 3x) to keep the suite near an hour.

**E10 Grounding of every published bullet: FAIL**
- run 1 FAIL: `23/45 bullets rated supported (51%, threshold 90%); mean score 3.87/5; judge errors=0`
- note: Agent part only: the human spot-check (20 bullets, >= 85% agreement) is pending; fill the human_agrees column in eval/grounding_bullets.csv.

## Failure analysis

Two of ten cases failed (E9, E10). Two more cases passed on 2 of 3 runs (E1, E3); their failed runs are analysed too, because they show the same weaknesses.

### E9 Full 10-topic newsletter: FAIL (cost limit), cause: reasoning issue (Scout tool use)

Everything except cost met the bar: 10/10 sections, no agent errors, bad_refs = 0, 4.4 min wall time (limit 15). Total tokens were **123,221, 2.7% over the 120K limit**. The Scout used about 80K of them, reading tool results. The overage came from wasted Scout work:
- "Cancer research breakthroughs" (kind = research) called `get_artist_releases` twice, a tool meant only for artists, and then needed a retry.
- "Kendrick Lamar" needed a Scout retry and used 23.9K tokens, twice the median topic.

The wasted calls and retries cost more than the 3.2K overage. The Scout prompt states the kind-to-tool rule plainly, so this is gpt-oss not following it (a reasoning issue), not a missing instruction. Across the whole suite, **5 of 29 non-artist topic runs called `get_artist_releases`**, always as their first source call, and the Scout needed **8 retries** after its tool budget ran out.
**Fix:** enforce the rule in code. The MCP tool filter already hides tools by budget, and it could also hide `get_artist_releases` unless kind = artist. Trimming long tool results before the Scout reads them would cut cost further.

### E10 Grounding of every published bullet: FAIL (51% vs 90%), cause: reasoning issue (Editor embellishes, Fact-checker lets it through), plus a retrieval limit

The critic (`qwen3`, a different model from the system's `gpt-oss`) scored 45 published bullets: **19 x 5, 4 x 4, 19 x 3, 3 x 2, 0 x 1**. A score of 4 or more counts as supported, so 23/45 = 51%. No bullet scored 1, so no story was invented or contradicted. 19 of the 22 failures are score 3, meaning one small detail is not in the headline:
1. **The Editor adds detail from its own knowledge or from the topic** (reasoning/prompt): "synth" (Brother Tree Sound), "T-cell" (a CAR therapy), "indie" (a game), "a U.S. battery startup", "IL-2-based vaccine" (cretostimogene). Most are harmless. The last is not in the headline and, as far as we know, is wrong: cretostimogene is an oncolytic virus therapy. That shows the risk.
2. **The Fact-checker accepts these additions.** It marked most of them `supported`: it is the same model that wrote them, and it is lenient on small extras. This is the reason the plan uses an independent judge.
3. **Headline-only evidence** (retrieval): claims such as "remission" or "a review outlines…" may be true in the article, but no agent can read article bodies, so the critic cannot verify them.
4. **Some critic calls are strict** ("any DAW" vs. "your DAW"; "researchers report"). With a cut-off of >= 3 the rate would be 42/45 (93%). The M3 threshold was >= 4, so we report the failure as measured.

**Fix:** have the Editor add no facts beyond the headline and keep relevance to a short clause; ask the Fact-checker to flag any added noun or descriptor; give agents the article snippet or body. The human spot-check of 20 bullets (column `human_agrees` in `grounding_bullets.csv`) is still to do; it will show how often the critic is too strict.

### Failed runs inside passing cases

- **E1 run 3**, cause: reasoning/output issue in the Fact-checker, plus a design gap. The Fact-checker returned a verdict for only 1 of 4 bullets, and the pipeline published the other 3 as `unchecked`. **Fix:** re-ask the checker for the missing ids, or drop unchecked bullets instead of publishing them.
- **E3 run 1**, cause: reasoning issue (tool selection). The Scout's first source call on a research topic was `get_artist_releases`, the same pattern as in E9.

### Passes worth qualifying

- **E2:** no Kendrick Lamar release fell in the 30-day window in any run, so "release links go to musicbrainz.org" passed without being exercised.
- **E5:** no story repeated, but in run 2 the Scout picked different stories after `recall_coverage`, so the code-side block never had to fire (skipped by memory = 0).
- **E3:** "framed as single studies" still needs the human review named in the plan.

## E10 human spot-check (added 2026-11-18)

20 of the 45 judged bullets were sampled at random (seed 20261117) into `eval/human_spotcheck.csv`. A team member (Philippe Lucien) judged each against its cited headline before looking at the critic's verdict.

- **Agreement with the critic: 16/20 = 80%** (target >= 85%), so the human part of E10 also fails.
- All 4 disagreements go one way: the critic said *not supported*, the human said *supported* (rows 3, 6, 8, 11: "any DAW" vs. the headline's "your DAW" twice, "researchers report", "T-cell"). The critic is stricter than the human on small rewordings.
- The human rated 13/20 sampled bullets supported (65%); the critic rated 9/20 (45%). Both are far below the 90% grounding target, so E10's FAIL does not depend on the critic's strictness.
- Rows 8-10 repeat stories from rows 1-3 (same story, another run, different wording). They were judged on their own wording; row 8 was revised to *supported* to match row 3.

## E3 human review: single-study framing (added 2026-11-18)

Two raters reviewed all 8 E3 bullets (full scores: `eval/human_review_results.md`). Both rated 2 bullets as **not** framed as single studies; both cite the same paper:
- run 1: "A high-avidity BCMA CAR achieved successful remission of systemic light-chain amyloidosis, showing potential for targeted CAR therapies."
- run 3: "Novel high-avidity BCMA CAR T-cell therapy achieved successful treatment of systemic light-chain amyloidosis."

The run-2 bullet on the same paper ("Researchers report a successful treatment…") was rated correctly framed. With the plan's framing criterion, E3 runs 1 and 3 fail, so **E3 = 1/3, FAIL**, and the overall pass rate is **7/10 (70%)**.

**Cause: prompt/reasoning issue (Editor).** The Editor turns a paper title into a statement of fact. The Editor prompt does not ask it to attribute research findings to "a study" or "researchers", so the wording depends on the run.

## E9 runs 2 and 3, and E10 over all bullets (added 2026-11-18)

E9 was rerun twice on 18 Nov to meet the plan's 3-run rule (outputs in `eval/e9_run2/` and `eval/e9_run3/`; agent code unchanged).

| E9 run | Tokens (limit 120,000) | Wall time (limit 15 min) | Bullets | Invalid citations | Wrong-tool calls | Scout retries | Critic supported |
|---|---|---|---|---|---|---|---|
| 1 (17 Nov) | 123,221 | 4.4 min | 24 | 0 | 1 | 2 | 46% (11/24) |
| 2 (18 Nov) | 138,257 | 21.8 min | 32 | 0 | 0 | 3 | 53% (17/32) |
| 3 (18 Nov) | 138,641 | 8.1 min | 31 | 0 | 0 | 2 | 55% (17/31) |

**E9 = 0/3, FAIL.** Every run produced all 10 sections with no agent errors and no invalid citations, but every run was over the token limit, and run 2 was also over the time limit because the NRP model answered slowly that day.

**E10 over every published bullet (E1-E3 x 3 runs, E9 x 3 runs): 57/108 supported (53%), mean 3.83/5** (scores: 0 x 1, 12 x 2, 39 x 3, 12 x 4, 45 x 5). Still far below 90%: FAIL.
