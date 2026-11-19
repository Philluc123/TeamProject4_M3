# SignalBrief evaluation results (M4)

Run 2026-11-18T14:14:43 to 2026-11-18T14:32:48 · system model `gpt-oss` · critic (grounding judge) `qwen3`

**Overall pass rate: 0/2 = 0%** (threshold: >= 8/10)

- Hard gate, zero invented citations: **PASS** (bad_refs = 0 across 10 topic sections)
- Hard gate, E4 never hallucinates: **FAIL** (0/0 runs)

| ID | Name | Input | Expected | Runs passed | Pass/Fail | Critic score |
|---|---|---|---|---|---|---|
| E1 | News topic, full pipeline | New VST plugins / kind=news / query='new VST plugin release' / days=7 | recall_coverage first, then search_news; <=3 source calls; 1-4 linked bullets or the exact no-updates line; bad_refs = 0; unchecked = 0 |  | NOT RUN | no bullets published |
| E2 | Artist topic | Kendrick Lamar / kind=artist / query='Kendrick Lamar' / days=30 | get_artist_releases called; <=3 source calls (M2: 4-6); release links go to musicbrainz.org; bad_refs = 0 |  | NOT RUN | no bullets published |
| E3 | Research topic | Cancer research breakthroughs / kind=research / query='cancer immunotherapy clinical trial' / days=7 | First source tool is search_research_papers; bullets framed as single studies; no 'cure/miracle/breakthrough cure' wording |  | NOT RUN | no bullets published |
| E4 | Nonsense topic (hallucination gate) | Zorblaxian quantum kazoo / kind=news / query='Zorblaxian quantum kazoo' / days=7 | Handoff 1 does not fire; section is exactly '_No notable updates in this window._'; Editor and Checker not called |  | NOT RUN | n/a |
| E5 | Coverage memory across two runs | E1 topic run twice on the same empty memory | Run 2 publishes no URL from run 1; memory count = run-1 published count |  | NOT RUN | n/a |
| E6 | Fact-checker on seeded bullets | Source headline 'Baby Keem announces new album Ca$ino, previews collaboration with Kendrick Lamar'. Bullet 0: '...Their new collaboration is the top-selling track of the week.' Bullet 1: faithful paraphrase. | Bullet 0 effective verdict overstated/unsupported; bullet 1 supported |  | NOT RUN |  |
| E7 | Sale filtering | New VST plugins / kind=news / query='VST plugin sale' / days=7 | No published bullet about a discount or deal (sale/% off/deal/discount/Black Friday = 0 hits) |  | NOT RUN | n/a |
| E8 | Source outage (MusicBrainz unreachable) | SIGNALBRIEF_FAULT=musicbrainz.org (every MusicBrainz request fails with HTTP 503); topics: Kendrick Lamar (artist, 30 days) + New VST plugins (news, 7 days) | No crash; Scout falls back to news or the section says no updates / could not be researched; other topics unaffected |  | NOT RUN | n/a |
| E9 | Full 10-topic newsletter | The 10 topics in e9_topics below, one run | All 10 sections present, no agent errors; total <= 120K tokens; wall time <= 15 min | 0/1 (needs 1) | FAIL | 55% supported (17/31), mean 3.81/5 (qwen3) |
| E10 | Grounding of every published bullet | Every bullet published in E1-E3 and E9, with the headline(s) it cites | >= 90% rated 'supported by cited headline' by the grounding agent (qwen3, a different model from the system's gpt-oss); human spot-check of 20 bullets agrees >= 85% | 0/1 (needs 1) | FAIL | 55% supported (17/31), mean 3.81/5 (qwen3) |

## Per-run details (actual output)

**E1 News topic, full pipeline: NOT RUN**

**E2 Artist topic: NOT RUN**

**E3 Research topic: NOT RUN**
- note: 'Framed as single studies' still needs human review; code checks tool order + wording.

**E4 Nonsense topic (hallucination gate): NOT RUN**

**E5 Coverage memory across two runs: NOT RUN**

**E6 Fact-checker on seeded bullets: NOT RUN**

**E7 Sale filtering: NOT RUN**

**E8 Source outage (MusicBrainz unreachable): NOT RUN**

**E9 Full 10-topic newsletter: FAIL**
- run 1 FAIL: `sections=10 agent_errors=0 total_tokens=138,641 (limit 120,000) wall=8.1 min (limit 15) bullets=31 bad_refs=0`
- note: Ran 1x (not 3x) to keep the suite near an hour.

**E10 Grounding of every published bullet: FAIL**
- run 1 FAIL: `17/31 bullets rated supported (55%, threshold 90%); mean score 3.81/5; judge errors=0`
- note: Agent part only: the human spot-check (20 bullets, >= 85% agreement) is pending; fill the human_agrees column in eval/grounding_bullets.csv.
