"""
Run SignalBrief's test cases (see tests/test_cases.json for inputs + expected outputs).

  python tests/run_tests.py          # offline cases O1-O9 (no API key; O5 needs Chroma's local model)
  python tests/run_tests.py --live   # also live cases L1-L6 (needs NRP_API_KEY + internet)

Live cases check properties (tools used, budget, handoffs, verdicts, citations,
no repeats) because the actual news changes every day.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import news_mcp_server as srv  # noqa: E402
from citations import sources_from_tool_outputs, verify_and_link  # noqa: E402
from pipeline import (  # noqa: E402
    FactCheckReport,
    ToolBudget,
    Verdict,
    apply_verdicts,
    budget_tool_filter,
    build_factcheck_request,
    build_research_packet,
    editor_input,
    handoff_to_editor,
    react_trace,
    split_bullets,
)

TODAY = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
results: list[tuple[str, bool, str]] = []
NO_UPDATES = "_No notable updates in this window._"


def check(case_id: str, condition: bool, detail: str) -> None:
    results.append((case_id, bool(condition), detail))
    print(f"  [{'PASS' if condition else 'FAIL'}] {case_id}: {detail}")


def news_items() -> list[dict]:
    return srv.parse_google_news_rss((FIX / "google_news_sample.xml").read_bytes(), 7, 10, now=TODAY)


# ---------------------------------------------------------------- offline
def test_o1_news_parser():
    items = news_items()
    print("  O1 actual:", json.dumps(items, indent=2))
    ok = (len(items) == 2
          and items[0]["title"].startswith("Arturia") and items[0]["published"] == "2026-09-29"
          and items[1]["title"] == "Xfer Records releases Serum 2 update with new wavetables"
          and all(i["ref"].startswith("n-") for i in items))
    check("O1", ok, "2 recent, de-duplicated articles with refs, newest first")


def test_o2_music_parser():
    data = json.loads((FIX / "musicbrainz_rg_sample.json").read_text())
    rel = srv.parse_musicbrainz_releases(data, "Test Artist", 30, now=TODAY)
    print("  O2 actual:", [(r["title"], r["type"], r["published"]) for r in rel])
    ok = ([r["title"] for r in rel] == ["Brand New Single", "Live Set"]
          and rel[1]["type"] == "Album / Live"
          and rel[0]["url"].startswith("https://musicbrainz.org/release-group/"))
    check("O2", ok, "only exactly-dated releases in the last 30 days")


def test_o3_pubmed_parser():
    data = json.loads((FIX / "pubmed_summary_sample.json").read_text())
    papers = srv.parse_pubmed_summary(data, 5)
    print("  O3 actual:", [(p["url"], p["journal"], p["published"]) for p in papers])
    ok = (len(papers) == 2
          and papers[0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/40000001/"
          and papers[0]["journal"] == "The Lancet Oncology"
          and papers[0]["published"] == "2026-09-27"
          and papers[1]["journal"] == "Nat Commun")
    check("O3", ok, "PubMed links, journal names, dates")


def test_o4_guardrail():
    items = news_items()
    tool_output = json.dumps({"articles": items})
    # simulate the MCP wrapper the Agents SDK can put around tool text
    wrapped = json.dumps({"type": "text", "text": tool_output})
    sources = sources_from_tool_outputs([wrapped])
    serum_ref = next(i["ref"] for i in items if "Serum" in i["title"])
    agent_text = (
        f"- **Serum 2 update.** Xfer shipped new wavetables. [{serum_ref}]\n"
        "- **Fake news.** A plugin that does not exist launched. [n-fffff]\n"
        "- **Uncited claim.** Something with no source at all.\n"
    )
    md, stats = verify_and_link(agent_text, sources)
    print("  O4 output:\n    " + md.replace("\n", "\n    "), "\n  O4 stats:", stats)
    ok = (stats == {"kept": 1, "dropped": 2, "bad_refs": 1}
          and "[MusicRadar, 2026-09-28](https://news.google.com/rss/articles/SAMPLE_A)" in md
          and "Fake news" not in md and "Uncited" not in md)
    check("O4", ok, "real citation linked, invented + uncited bullets dropped")


def test_o5_memory():
    from memory_store import CoverageMemory
    serum = next(i for i in news_items() if "Serum" in i["title"])
    arturia = next(i for i in news_items() if "Arturia" in i["title"])
    today = date(2026, 9, 30)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d1, \
            tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d2:
        mem = CoverageMemory(d1)
        mem.remember("New VST plugins", serum, serum["title"], sent_on="2026-09-30")
        a = mem.find_match("New VST plugins", serum, today=today)
        reworded = {"url": "https://example.com/other-outlet/serum2",
                    "title": "Serum 2 gets a big update from Xfer Records with new wavetables"}
        b = mem.find_match("New VST plugins", reworded, today=today)
        c = mem.find_match("New VST plugins", arturia, today=today)
        d = mem.find_match("Kendrick Lamar", reworded, today=today)
        old = CoverageMemory(d2)
        old.remember("New VST plugins", serum, serum["title"], sent_on="2026-08-01")
        e = old.find_match("New VST plugins", serum, today=today)
    print("  O5 actual:", {"a": a and a["match"], "b": b and (b["match"], b["distance"]),
                           "c": c, "d": d, "e": e})
    ok = (a is not None and a["match"] == "same_url"
          and b is not None and b["match"] == "same_story" and b["distance"] <= 0.35
          and c is None and d is None and e is None)
    check("O5", ok, "same URL + re-worded story matched; unrelated / other topic / old item not")


def test_o6_handoff_packet():
    items = news_items()
    sources = {i["ref"]: i for i in items}
    arturia = next(i for i in items if "Arturia" in i["title"])
    serum = next(i for i in items if "Serum" in i["title"])
    covered = lambda rec: ({"title": rec["title"], "sent_on": "2026-09-29", "match": "same_url"}
                           if "Serum" in rec["title"] else None)
    topic = {"name": "New VST plugins", "kind": "news", "days": 7, "why": "producer"}
    scout_text = (f"- [{arturia['ref']}] big synth launch\n"
                  "- [n-fffff] a plugin nobody returned\n"
                  f"- [{serum['ref']}] Serum update")
    packet = build_research_packet(topic, scout_text, sources, covered)
    ed = editor_input(packet)
    none_packet = build_research_packet(topic, "NONE", sources, covered)
    print("  O6 packet:", {k: packet[k] for k in ("candidates", "already_covered", "invented_refs")})
    ok = ([c["ref"] for c in packet["candidates"]] == [arturia["ref"]]
          and [c["ref"] for c in packet["already_covered"]] == [serum["ref"]]
          and packet["invented_refs"] == ["n-fffff"]
          and handoff_to_editor(packet)
          and "http" not in ed and serum["ref"] not in ed
          and packet["candidates"][0]["why_relevant"] == "big synth launch"
          and not handoff_to_editor(none_packet))
    check("O6", ok, "packet = real records only; invented + already-sent removed; NONE -> no handoff")


def test_o7_factcheck():
    items = news_items()
    a, s = items[0]["ref"], items[1]["ref"]
    packet = {"topic": {"name": "New VST plugins"},
              "candidates": [{"ref": i["ref"], "title": i["title"], "source": i["source"],
                              "published": i["published"], "type": ""} for i in items]}
    editor_text = (f"- **Arturia synth.** Arturia launched a synth. [{a}]\n"
                   f"- **Serum 2.** Serum 2 is the best-selling synth of the year. [{s}]\n"
                   f"- **Made up.** A plugin that cures tinnitus. [{a}]\n"
                   f"**Serum wavetables.** New wavetables in Serum 2. [{s}]")
    bullets = split_bullets(editor_text)
    request = build_factcheck_request(bullets, packet)
    report = FactCheckReport(verdicts=[
        Verdict(id=0, reasoning="launch stated in headline", verdict="supported"),
        Verdict(id=1, reasoning="'best-selling' not in headline", verdict="overstated",
                revised_bullet="- **Serum 2.** Xfer released a Serum 2 update."),
        Verdict(id=2, reasoning="nothing about tinnitus", verdict="unsupported"),
    ])
    kept, stats = apply_verdicts(bullets, report)
    print("  O7 kept:", kept, "\n  O7 stats:", stats)
    ok = (len(bullets) == 4
          and [len(i["cited_sources"]) for i in request["items"]] == [1, 1, 1, 1]
          and request["items"][1]["cited_sources"][0]["title"].startswith("Xfer")
          and len(kept) == 3
          and kept[0] == bullets[0]
          and kept[1] == f"- **Serum 2.** Xfer released a Serum 2 update. [{s}]"
          and "tinnitus" not in " ".join(kept)
          and kept[2] == bullets[3]
          and stats == {"supported": 1, "overstated": 1, "unsupported": 1, "unchecked": 1})
    check("O7", ok, "supported kept, overstated revised (ref restored), unsupported dropped, missing = unchecked")


def test_o8_budget():
    budget = ToolBudget(max_source_calls=3, max_memory_calls=1)
    ctx = SimpleNamespace(run_context=SimpleNamespace(context=budget))
    names = ["recall_coverage", "search_news", "search_research_papers",
             "get_artist_releases", "some_other_tool"]
    visible = lambda: [n for n in names if budget_tool_filter(ctx, SimpleNamespace(name=n))]
    before = visible()
    budget.record("recall_coverage")
    for _ in range(3):
        budget.record("search_news")
    after = visible()
    print("  O8 visible before:", before, "after:", after)
    check("O8", before == names and after == ["some_other_tool"],
          "budget spent -> source + memory tools hidden by the MCP tool filter")


def test_o9_react_trace():
    wrapped = json.dumps({"type": "text", "text": json.dumps({"articles": [{}, {}]})})
    steps = [("thought", "Check memory first."),
             ("action", ("recall_coverage", '{"topic": "VST"}')),
             ("observation", json.dumps({"topic": "VST", "already_sent": []})),
             ("thought", "Nothing sent yet; search news."),
             ("action", ("search_news", '{"query": "new VST plugin"}')),
             ("observation", wrapped),
             ("answer", "- [n-12345] why")]
    trace = react_trace(steps)
    print("  O9 trace:", trace)
    ok = (len(trace) == 3
          and trace[0]["action"].startswith("recall_coverage") and trace[0]["observation"] == "0 already sent"
          and trace[1]["thought"] == "Nothing sent yet; search news."
          and trace[1]["observation"] == "2 articles"
          and trace[2] == {"answer": "- [n-12345] why"})
    check("O9", ok, "Thought -> Action -> Observation steps, then the answer")


# ---------------------------------------------------------------- live
def first_source_tool(tools: list[str]) -> str | None:
    return next((t for t in tools if t != "recall_coverage"), None)


def checked_ok(s: dict) -> bool:
    """Published bullets all went through the fact-checker."""
    return s["stats"]["kept"] == 0 or s.get("factcheck", {}).get("unchecked", 1) == 0


async def run_live():
    import signalbrief_agent as sb
    from agents import Agent, Runner

    cases = {c["id"]: c for c in json.loads((ROOT / "tests" / "test_cases.json").read_text())["live"]}

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as mem_dir:
        topics = [dict(cases[i]["input"]) for i in ("L1", "L2", "L3", "L4")]
        sections = await sb.run(topics, "test", Path(mem_dir), write_memory=False)
    for cid, s in zip(("L1", "L2", "L3", "L4"), sections):
        print(f"\n--- {cid}: {cases[cid]['name']} ---")
        print("  section:\n    " + s["markdown"].replace("\n", "\n    "))
        tools, budget, stats = s.get("tools", []), s.get("budget", {}), s["stats"]
        no_updates = s["markdown"] == NO_UPDATES
        base_ok = ("error" not in s and stats["bad_refs"] == 0
                   and budget.get("source_calls", 99) <= 3)
        if cid == "L1":
            ok = (base_ok and tools[:1] == ["recall_coverage"] and "search_news" in tools
                  and (no_updates or (stats["kept"] >= 1 and checked_ok(s))))
        elif cid == "L2":
            ok = base_ok and "get_artist_releases" in tools and (no_updates or stats["kept"] >= 1)
        elif cid == "L3":
            ok = (base_ok and first_source_tool(tools) == "search_research_papers"
                  and (no_updates or checked_ok(s)))
        else:  # L4 nonsense topic
            ok = ("error" not in s and stats["kept"] == 0 and no_updates
                  and not s.get("packet", {}).get("candidates"))
        check(cid, ok, f"tools={tools} source_calls={budget.get('source_calls')} kept={stats['kept']} "
                       f"factcheck={s.get('factcheck')} bad_refs={stats['bad_refs']}")

    # L5: memory across two "days"
    print(f"\n--- L5: {cases['L5']['name']} ---")
    from memory_store import CoverageMemory
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as mem_dir:
        run1 = await sb.run([dict(cases["L1"]["input"])], "test", Path(mem_dir), write_memory=True)
        urls1 = {r["url"] for r in run1[0].get("published", [])}
        count1 = CoverageMemory(mem_dir).count()
        run2 = await sb.run([dict(cases["L1"]["input"])], "test", Path(mem_dir), write_memory=True)
        urls2 = {r["url"] for r in run2[0].get("published", [])}
        skipped = len(run2[0].get("packet", {}).get("already_covered", []))
    check("L5", not (urls1 & urls2) and count1 == len(urls1),
          f"run1 published {len(urls1)}, memory={count1}; run2 published {len(urls2)}, "
          f"repeats={len(urls1 & urls2)}, code-skipped as already sent={skipped}")

    # L6: fact-checker on seeded bullets
    print(f"\n--- L6: {cases['L6']['name']} ---")
    checker = Agent(name="SignalBrief Fact-checker", instructions=sb.CHECKER_INSTRUCTIONS,
                    model=sb.MODEL, output_type=FactCheckReport)
    src = {"ref": "n-abcde", "title": "Baby Keem announces new album Ca$ino, previews "
           "collaboration with Kendrick Lamar", "source": "Billboard Canada",
           "published": "2026-09-30", "type": ""}
    request = {"topic": "Kendrick Lamar", "items": [
        {"id": 0, "bullet": "- **Kendrick x Baby Keem.** Their new collaboration is the "
                            "top-selling track of the week. [n-abcde]", "cited_sources": [src]},
        {"id": 1, "bullet": "- **Baby Keem album.** Baby Keem announced his album Ca$ino and "
                            "previewed a collaboration with Kendrick Lamar. [n-abcde]",
         "cited_sources": [src]},
    ]}
    try:
        report = (await Runner.run(checker, json.dumps(request), max_turns=2)).final_output
        verdicts = {v.id: v.verdict for v in report.verdicts}
        for v in report.verdicts:
            print(f"  [{v.id}] {v.verdict}: {v.reasoning[:200]}")
    except Exception as exc:
        verdicts = {"error": str(exc)}
    check("L6", verdicts.get(0) in ("overstated", "unsupported") and verdicts.get(1) == "supported",
          f"verdicts={verdicts}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="also run live agent cases (needs NRP key)")
    args = ap.parse_args()

    print("Offline test cases")
    for test in (test_o1_news_parser, test_o2_music_parser, test_o3_pubmed_parser,
                 test_o4_guardrail, test_o5_memory, test_o6_handoff_packet,
                 test_o7_factcheck, test_o8_budget, test_o9_react_trace):
        test()
    if args.live:
        print("\nLive test cases (3-agent pipeline, real tools + NRP model)")
        asyncio.run(run_live())

    passed = sum(ok for _, ok, _ in results)
    print(f"\n{passed}/{len(results)} test cases passed")
    for cid, ok, detail in results:
        print(f"  {cid}: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
