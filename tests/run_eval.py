"""
M4 evaluation: run the 10 cases (E1-E10) committed to in the M3 evaluation plan.

  python tests/run_eval.py                  # full suite (~1 hour; NRP key + internet)
  python tests/run_eval.py --only E4 E6     # just some cases (E10 judges whatever ran)
  python tests/run_eval.py --repeats 1      # quicker smoke run (reliability rule off)

Writes to eval/:
  results.csv            one row per case: id, input, expected, actual, pass/fail, critic score
  results.md             same table + pass rate, hard gates and per-run details
  grounding_bullets.csv  every bullet the critic judged (with an empty column for the
                         human spot-check)
  raw/eval_<time>.json   everything each run returned, for the failure analysis

Reliability rule (M3 plan): each live case runs 3 times and passes if >= 2/3 runs pass;
E6 runs 5 times and passes if >= 4/5. E9 (a 10-topic newsletter, ~15 min) runs once by
default; use --e9-runs 3 for the full rule.

Critic: E10's grounding judge is a *different* model (qwen3 on NRP) from the system's own
gpt-oss agents, so the fact-checker never grades itself.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import signalbrief_agent as sb  # noqa: E402  (exits early if NRP_API_KEY is missing)
from agents import Agent, Runner  # noqa: E402
from memory_store import CoverageMemory  # noqa: E402
from pipeline import FactCheckReport, effective_verdict  # noqa: E402

CASES = json.loads((ROOT / "tests" / "eval_cases.json").read_text(encoding="utf-8"))
CASE = {c["id"]: c for c in CASES["cases"]}
OUT = ROOT / "eval"
MCP_LOG = ROOT / "output" / "mcp_server.log"
NO_UPDATES = "_No notable updates in this window._"
COULD_NOT = "_Could not be researched today"
SALE_RE = re.compile(r"\bsales?\b|% off|\bdeals?\b|discount|black friday", re.I)
CURE_RE = re.compile(r"\bcure[sd]?\b|\bmiracle\b|breakthrough cure", re.I)
JUDGE_MODEL = os.getenv("SIGNALBRIEF_JUDGE_MODEL", "qwen3")
TOKEN_LIMIT, WALL_LIMIT_S = 120_000, 15 * 60

runs: dict[str, list[dict]] = {}     # case id -> [{ok, detail}, ...]
raw: dict[str, list] = {}            # case id -> raw sections per run (for the analysis)
bullets_to_judge: list[dict] = []    # E10 input: bullets published in E1-E3 and E9


# ---------------------------------------------------------------- helpers
def record(cid: str, ok: bool, detail: str) -> None:
    runs.setdefault(cid, []).append({"ok": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {cid} run {len(runs[cid])}: {detail}", flush=True)


def first_source_tool(tools: list[str]) -> str | None:
    return next((t for t in tools if t != "recall_coverage"), None)


def tokens(section: dict) -> int:
    return sum(u.get("total_tokens", 0) for u in section.get("usage", {}).values())


def published_bullets(section: dict) -> list[dict]:
    """Bullets that made it into the newsletter, each with the source records it cites."""
    by_ref = {r["ref"]: r for r in section.get("published", []) if r.get("ref")}
    out = []
    for b in section.get("final_bullets", []):
        cited = [by_ref[r] for r in sb.REF_PATTERN.findall(b) if r in by_ref]
        if cited:
            out.append({"bullet": b, "sources": cited})
    return out


def bullet_text(b: str) -> str:
    """Bullet without its [ref] ids (so a ref can't trip a keyword check)."""
    return re.sub(r"\s*\[[\s,]*\]", "", sb.REF_PATTERN.sub("", b)).strip()


def summary(s: dict) -> str:
    fc = s.get("factcheck", {})
    return (f"tools={s.get('tools', [])} source_calls={s.get('budget', {}).get('source_calls')} "
            f"kept={s['stats']['kept']} bad_refs={s['stats']['bad_refs']} "
            f"unchecked={fc.get('unchecked', '-')} tokens={tokens(s)}"
            + (f" error={s['error'][:80]!r}" if "error" in s else ""))


def base_ok(s: dict) -> bool:
    return ("error" not in s and s["stats"]["bad_refs"] == 0
            and s.get("budget", {}).get("source_calls", 99) <= 3)


def no_updates(s: dict) -> bool:
    return s["markdown"] == NO_UPDATES


async def run_topics(topics: list[dict], mem_dir: Path, write_memory: bool = False):
    return await sb.run([dict(t) for t in topics], "eval", mem_dir, write_memory=write_memory)


# ---------------------------------------------------------------- E1-E4, E7 (one batch per repeat)
def check_e1(s):
    kept, fc = s["stats"]["kept"], s.get("factcheck", {})
    ok = (base_ok(s) and s.get("tools", [])[:1] == ["recall_coverage"]
          and "search_news" in s.get("tools", [])
          and (no_updates(s) or (1 <= kept <= 4 and fc.get("unchecked", 1) == 0)))
    return ok, summary(s)


def check_e2(s):
    releases = [r for r in s.get("published", []) if r.get("ref", "").startswith("m-")]
    mb_links = all("musicbrainz.org" in r.get("url", "") for r in releases)
    ok = base_ok(s) and "get_artist_releases" in s.get("tools", []) and mb_links
    return ok, summary(s) + f" release_links={len(releases)} all_musicbrainz={mb_links}"


def check_e3(s):
    texts = [bullet_text(b["bullet"]) for b in published_bullets(s)]
    cure_hits = [t for t in texts if CURE_RE.search(t)]
    checked = s["stats"]["kept"] == 0 or s.get("factcheck", {}).get("unchecked", 1) == 0
    ok = (base_ok(s) and first_source_tool(s.get("tools", [])) == "search_research_papers"
          and not cure_hits and checked)
    return ok, summary(s) + f" first_source={first_source_tool(s.get('tools', []))} cure_wording={len(cure_hits)}"


def check_e4(s):
    usage = s.get("usage", {})
    ok = ("error" not in s and s["stats"]["kept"] == 0 and no_updates(s)
          and not s.get("packet", {}).get("candidates")
          and "editor" not in usage and "checker" not in usage)
    return ok, (summary(s) + f" handoff1_fired={bool(s.get('packet', {}).get('candidates'))} "
                f"editor_called={'editor' in usage} checker_called={'checker' in usage} "
                f"section={s['markdown'][:60]!r}")


def check_e7(s):
    texts = [bullet_text(b["bullet"]) for b in published_bullets(s)]
    hits = [t for t in texts if SALE_RE.search(t)]
    ok = "error" not in s and s["stats"]["bad_refs"] == 0 and not hits
    return ok, summary(s) + f" sale_wording_hits={len(hits)}" + (f" e.g. {hits[0][:100]!r}" if hits else "")


BATCH = {"E1": check_e1, "E2": check_e2, "E3": check_e3, "E4": check_e4, "E7": check_e7}


async def batch_cases(ids: list[str], repeats: int):
    for rep in range(repeats):
        print(f"\n##### Batch {rep + 1}/{repeats}: {', '.join(ids)}", flush=True)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as mem:
            try:
                sections = await run_topics([CASE[i]["input"] for i in ids], Path(mem))
            except Exception as exc:  # whole run crashed: every case in it fails this repeat
                for cid in ids:
                    record(cid, False, f"pipeline crashed: {exc!r}"[:300])
                continue
        for cid, s in zip(ids, sections):
            raw.setdefault(cid, []).append(s)
            ok, detail = BATCH[cid](s)
            record(cid, ok, detail)
            if cid in ("E1", "E2", "E3"):
                for b in published_bullets(s):
                    bullets_to_judge.append({"case": cid, "run": rep + 1, "topic": s["topic"]["name"], **b})


# ---------------------------------------------------------------- E5 memory
async def case_e5(repeats: int):
    for rep in range(repeats):
        print(f"\n##### E5 repeat {rep + 1}/{repeats}", flush=True)
        topic = CASE["E1"]["input"]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as mem:
            try:
                r1 = await run_topics([topic], Path(mem), write_memory=True)
                urls1 = {r["url"] for r in r1[0].get("published", [])}
                count1 = CoverageMemory(mem).count()
                r2 = await run_topics([topic], Path(mem), write_memory=True)
            except Exception as exc:
                record("E5", False, f"pipeline crashed: {exc!r}"[:300])
                continue
        urls2 = {r["url"] for r in r2[0].get("published", [])}
        skipped = len(r2[0].get("packet", {}).get("already_covered", []))
        raw.setdefault("E5", []).append({"run1": r1[0], "run2": r2[0]})
        bad = r1[0]["stats"]["bad_refs"] + r2[0]["stats"]["bad_refs"]
        record("E5", not (urls1 & urls2) and count1 == len(urls1) and bad == 0,
               f"run1 published {len(urls1)}, memory after run1={count1}; run2 published {len(urls2)}, "
               f"repeats={len(urls1 & urls2)}, skipped by memory={skipped}, bad_refs={bad}")


# ---------------------------------------------------------------- E6 fact-checker
async def case_e6(repeats: int):
    print(f"\n##### E6 x{repeats}", flush=True)
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
    for _ in range(repeats):
        verdicts, rawv = {}, {}
        try:
            report = (await Runner.run(checker, json.dumps(request), max_turns=2)).final_output
            for v in report.verdicts:
                rawv[v.id] = v.verdict
                verdicts[v.id] = effective_verdict(v)[0]
        except Exception as exc:
            verdicts = {"error": str(exc)[:200]}
        raw.setdefault("E6", []).append({"effective": verdicts, "model": rawv})
        record("E6", verdicts.get(0) in ("overstated", "unsupported") and verdicts.get(1) == "supported",
               f"effective verdicts={verdicts} (model's own={rawv})")


# ---------------------------------------------------------------- E8 fault injection
async def case_e8(repeats: int):
    topics = [CASE["E2"]["input"], CASE["E1"]["input"]]   # artist (faulted) + news (control)
    for rep in range(repeats):
        print(f"\n##### E8 repeat {rep + 1}/{repeats} (MusicBrainz -> 503)", flush=True)
        log_start = MCP_LOG.stat().st_size if MCP_LOG.exists() else 0
        os.environ["SIGNALBRIEF_FAULT"] = "musicbrainz.org"
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as mem:
                sections = await run_topics(topics, Path(mem))
        except Exception as exc:
            record("E8", False, f"pipeline crashed: {exc!r}"[:300])
            continue
        finally:
            os.environ.pop("SIGNALBRIEF_FAULT", None)
        injected = 0
        if MCP_LOG.exists():
            with open(MCP_LOG, encoding="utf-8", errors="replace") as f:
                f.seek(log_start)
                injected = f.read().count("fault injected")
        art, news = sections
        raw.setdefault("E8", []).append(sections)
        art_ok = (art["stats"]["bad_refs"] == 0
                  and ("search_news" in art.get("tools", []) or no_updates(art)
                       or art["markdown"].startswith(COULD_NOT)))
        news_ok = base_ok(news) and "search_news" in news.get("tools", [])
        record("E8", art_ok and news_ok and injected > 0,
               f"faults injected={injected}; artist: {summary(art)} fell_back_to_news="
               f"{'search_news' in art.get('tools', [])}; other topic: {summary(news)}")


# ---------------------------------------------------------------- E9 full newsletter
async def case_e9(repeats: int):
    topics = CASES["e9_topics"]
    for rep in range(repeats):
        print(f"\n##### E9 repeat {rep + 1}/{repeats}: {len(topics)} topics", flush=True)
        t0 = time.time()
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as mem:
                sections = await run_topics(topics, Path(mem))
        except Exception as exc:
            record("E9", False, f"pipeline crashed after {time.time() - t0:.0f}s: {exc!r}"[:300])
            continue
        wall = time.time() - t0
        total = sum(tokens(s) for s in sections)
        errors = [s["topic"]["name"] for s in sections if "error" in s]
        bad = sum(s["stats"]["bad_refs"] for s in sections)
        kept = sum(s["stats"]["kept"] for s in sections)
        raw.setdefault("E9", []).append({"wall_s": wall, "tokens": total, "sections": sections})
        for s in sections:
            for b in published_bullets(s):
                bullets_to_judge.append({"case": "E9", "run": rep + 1, "topic": s["topic"]["name"], **b})
        record("E9", len(sections) == 10 and not errors and total <= TOKEN_LIMIT and wall <= WALL_LIMIT_S,
               f"sections={len(sections)} agent_errors={errors or 0} total_tokens={total:,} "
               f"(limit {TOKEN_LIMIT:,}) wall={wall / 60:.1f} min (limit 15) bullets={kept} bad_refs={bad}")


# ---------------------------------------------------------------- E10 grounding critic
JUDGE_SYSTEM = """You are an independent grounding judge for a news newsletter. You did not write
the bullet. You get one newsletter bullet and the source(s) it cites. You only know each source's
headline, outlet, date and type - not the article text.

Decide whether every factual claim in the bullet is supported by the cited headline(s).
A short phrase about why it matters to the reader (e.g. "worth a look for producers") is not a
factual claim. Specific numbers, rankings, dates, names, outcomes or features that are not in
the headline are NOT supported.

Score: 5 = every claim is in the headline; 4 = faithful paraphrase, harmless wording;
3 = one small detail not in the headline; 2 = a key claim not in the headline;
1 = contradicts the headline or invents the story.

Reply with JSON only:
{"score": 1-5, "unsupported_claims": ["..."], "reason": "one sentence"}"""


def parse_judge(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    data = json.loads(m.group(0))
    score = int(data["score"])
    if not 1 <= score <= 5:
        raise ValueError(f"score {score} out of range")
    return {"score": score, "supported": score >= 4, "reason": str(data.get("reason", ""))[:300],
            "unsupported_claims": data.get("unsupported_claims", [])}


async def judge(item: dict) -> dict:
    srcs = "\n".join(f"- headline: {s.get('title')!r} | outlet: {s.get('source')} | "
                     f"date: {s.get('published')} | type: {s.get('type') or 'news'}"
                     for s in item["sources"])
    user = f"Bullet:\n{bullet_text(item['bullet'])}\n\nCited source(s):\n{srcs}\n\n/no_think"
    last = ""
    for _ in range(2):
        try:
            resp = await sb.client.chat.completions.create(
                model=JUDGE_MODEL, temperature=0, max_tokens=2000,
                messages=[{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}])
            last = resp.choices[0].message.content or ""
            return parse_judge(last)
        except Exception as exc:
            last = f"{exc!r} | {last[:200]}"
    return {"score": None, "supported": None, "reason": f"judge error: {last[:250]}", "unsupported_claims": []}


async def case_e10():
    print(f"\n##### E10: grounding judge ({JUDGE_MODEL}) on {len(bullets_to_judge)} published bullets", flush=True)
    for i, item in enumerate(bullets_to_judge, 1):
        item["judge"] = await judge(item)
        j = item["judge"]
        print(f"  [{i}/{len(bullets_to_judge)}] {item['case']} score={j['score']} "
              f"{bullet_text(item['bullet'])[:90]!r} -> {j['reason'][:100]}", flush=True)
    judged = [b for b in bullets_to_judge if b["judge"]["score"] is not None]
    sup = sum(b["judge"]["supported"] for b in judged)
    pct = 100 * sup / len(judged) if judged else 0.0
    errors = len(bullets_to_judge) - len(judged)
    if not judged:
        record("E10", False, f"no bullets could be judged (published={len(bullets_to_judge)}, judge errors={errors})")
    else:
        mean = sum(b["judge"]["score"] for b in judged) / len(judged)
        record("E10", pct >= 90, f"{sup}/{len(judged)} bullets rated supported ({pct:.0f}%, threshold 90%); "
                                 f"mean score {mean:.2f}/5; judge errors={errors}")


def critic_for(cid: str) -> str:
    """Critic score column: grounding judge on that case's bullets; fact-checker accuracy for E6."""
    if cid == "E6":
        r = runs.get("E6", [])
        return f"fact-checker correct on {sum(x['ok'] for x in r)}/{len(r)} repeats" if r else ""
    if cid not in ("E1", "E2", "E3", "E9", "E10"):
        return "n/a"
    items = [b for b in bullets_to_judge if (cid == "E10" or b["case"] == cid)
             and b.get("judge", {}).get("score") is not None]
    if not items:
        return "no bullets published" if cid != "E10" else ""
    sup = sum(b["judge"]["supported"] for b in items)
    mean = sum(b["judge"]["score"] for b in items) / len(items)
    return f"{100 * sup / len(items):.0f}% supported ({sup}/{len(items)}), mean {mean:.2f}/5 ({JUDGE_MODEL})"


# ---------------------------------------------------------------- report
def fmt_input(v) -> str:
    if isinstance(v, dict):
        return f"{v['name']} | kind={v['kind']} | query={v['query']!r} | days={v['days']}"
    return str(v)


def need(cid: str) -> int:
    n = len(runs.get(cid, []))
    if cid == "E6":
        return max(1, -(-4 * n // 5))   # >= 4/5
    if n >= 3:
        return -(-2 * n // 3)           # >= 2/3
    return n                            # 1 or 2 runs: all must pass


def write_reports(started: str, args) -> dict:
    OUT.mkdir(exist_ok=True)
    (OUT / "raw").mkdir(exist_ok=True)
    rows = []
    for c in CASES["cases"]:
        cid, r = c["id"], runs.get(c["id"], [])
        passed = sum(x["ok"] for x in r)
        verdict = "NOT RUN" if not r else ("PASS" if passed >= need(cid) else "FAIL")
        notes = ""
        if cid == "E10":
            notes = ("Agent part only: the human spot-check (20 bullets, >= 85% agreement) is pending; "
                     "fill the human_agrees column in eval/grounding_bullets.csv.")
        if cid == "E3":
            notes = "'Framed as single studies' still needs human review; code checks tool order + wording."
        if cid == "E9" and len(r) < 3:
            notes = f"Ran {len(r)}x (not 3x) to keep the suite near an hour."
        rows.append({
            "test_case_id": cid, "name": c["name"], "input": fmt_input(c["input"]),
            "expected_output": c["expected_output"],
            "actual_output": " || ".join(f"run {i}: {'PASS' if x['ok'] else 'FAIL'} - {x['detail']}"
                                         for i, x in enumerate(r, 1)) or "not run",
            "runs_passed": f"{passed}/{len(r)} (needs {need(cid)})" if r else "",
            "pass_fail": verdict, "critic_score": critic_for(cid),
            "judged_by": c["judged_by"], "notes": notes,
        })
    with open(OUT / "results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    with open(OUT / "grounding_bullets.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["case", "run", "topic", "bullet", "cited_headlines", "judge_score",
                    "judge_supported", "judge_reason", "human_agrees (y/n)"])
        for b in bullets_to_judge:
            j = b.get("judge", {})
            w.writerow([b["case"], b["run"], b["topic"], bullet_text(b["bullet"]),
                        " || ".join(f"{s.get('title')} ({s.get('source')}, {s.get('published')})"
                                    for s in b["sources"]),
                        j.get("score"), j.get("supported"), j.get("reason"), ""])

    ran = [r for r in rows if r["pass_fail"] != "NOT RUN"]
    n_pass = sum(r["pass_fail"] == "PASS" for r in ran)
    all_sections = []
    for cid, items in raw.items():
        for it in items:
            if cid == "E5":
                all_sections += [it["run1"], it["run2"]]
            elif cid == "E9":
                all_sections += it["sections"]
            elif cid == "E8":
                all_sections += it
            elif isinstance(it, dict) and "stats" in it:
                all_sections.append(it)
    bad_refs = sum(s["stats"]["bad_refs"] for s in all_sections)
    e4 = runs.get("E4", [])
    summary_ = {"started": started, "finished": datetime.now().isoformat(timespec="seconds"),
                "model": sb.MODEL, "judge_model": JUDGE_MODEL, "cases_run": len(ran), "cases_passed": n_pass,
                "pass_rate": f"{100 * n_pass / len(ran):.0f}%" if ran else "n/a",
                "gate_bad_refs_zero": bad_refs == 0, "bad_refs_total": bad_refs,
                "sections_checked": len(all_sections),
                "gate_e4_never_hallucinates": bool(e4) and all(x["ok"] for x in e4),
                "repeats": args.repeats, "e9_runs": args.e9_runs}

    md = [f"# SignalBrief evaluation results (M4)", "",
          f"Run {summary_['started']} to {summary_['finished']} · system model `{sb.MODEL}` · "
          f"critic (grounding judge) `{JUDGE_MODEL}`", "",
          f"**Overall pass rate: {n_pass}/{len(ran)} = {summary_['pass_rate']}** "
          f"(threshold: >= 8/10)", "",
          f"- Hard gate, zero invented citations: **{'PASS' if summary_['gate_bad_refs_zero'] else 'FAIL'}** "
          f"(bad_refs = {bad_refs} across {len(all_sections)} topic sections)",
          f"- Hard gate, E4 never hallucinates: **{'PASS' if summary_['gate_e4_never_hallucinates'] else 'FAIL'}** "
          f"({sum(x['ok'] for x in e4)}/{len(e4)} runs)", "",
          "| ID | Name | Input | Expected | Runs passed | Pass/Fail | Critic score |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append("| " + " | ".join(str(r[k]).replace("|", "/") for k in
                  ("test_case_id", "name", "input", "expected_output", "runs_passed", "pass_fail",
                   "critic_score")) + " |")
    md += ["", "## Per-run details (actual output)", ""]
    for r in rows:
        md.append(f"**{r['test_case_id']} {r['name']}: {r['pass_fail']}**")
        for i, x in enumerate(runs.get(r["test_case_id"], []), 1):
            md.append(f"- run {i} {'PASS' if x['ok'] else 'FAIL'}: `{x['detail']}`")
        if r["notes"]:
            md.append(f"- note: {r['notes']}")
        md.append("")
    (OUT / "results.md").write_text("\n".join(md), encoding="utf-8")

    stamp = started.replace(":", "").replace("-", "")
    (OUT / "raw" / f"eval_{stamp}.json").write_text(
        json.dumps({"summary": summary_, "runs": runs, "raw": raw, "grounding": bullets_to_judge},
                   indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    return summary_


async def main_async(args):
    global OUT
    OUT = ROOT / args.out          # e.g. eval/e9_run2 keeps reruns from overwriting the baseline
    started = datetime.now().isoformat(timespec="seconds")
    want = lambda cid: not args.only or cid in args.only
    batch = [c for c in ("E1", "E2", "E3", "E4", "E7") if want(c)]
    if batch:
        await batch_cases(batch, args.repeats)
    if want("E5"):
        await case_e5(args.repeats)
    if want("E6"):
        await case_e6(5 if args.repeats >= 3 else args.repeats)
    if want("E8"):
        await case_e8(args.repeats)
    if want("E9"):
        await case_e9(args.e9_runs)
    if want("E10"):
        await case_e10()
    s = write_reports(started, args)
    print("\n" + json.dumps(s, indent=1))
    print(f"\nWrote {OUT / 'results.csv'}, {OUT / 'results.md'}, {OUT / 'grounding_bullets.csv'}")


def main():
    ap = argparse.ArgumentParser(description="SignalBrief M4 evaluation (E1-E10)")
    ap.add_argument("--only", nargs="+", type=str.upper, metavar="ID", help="e.g. --only E4 E6")
    ap.add_argument("--repeats", type=int, default=3, help="runs per live case (plan: 3)")
    ap.add_argument("--e9-runs", type=int, default=1, help="runs of the 10-topic newsletter")
    ap.add_argument("--out", default="eval", help="output folder, relative to the repo (default: eval)")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
