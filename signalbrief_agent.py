"""
SignalBrief - a personal daily newsletter, multi-agent (Team Project 4, M3)
===========================================================================
Reads up to 10 topics a user cares about (topics.json) and, for each topic,
runs three agents with two explicit, code-built handoffs:

  1. Scout (ReAct)   Thought -> Action (MCP tool) -> Observation, max 3 source
                     calls (enforced in code). Checks coverage memory first,
                     then picks the sources worth reporting by ref id.
     HANDOFF 1  ->   ResearchPacket: the real tool records for the refs the
                     Scout picked, minus invented refs and minus stories the
                     reader already got (ChromaDB memory). Only fires if at
                     least one fresh, verified candidate is left.
  2. Editor          Writes 0-4 plain-English bullets citing [ref] ids.
     HANDOFF 2  ->   FactCheckRequest: each bullet + the records it cites.
  3. Fact-checker    Chain-of-thought verdict per bullet: supported /
                     overstated (rewritten) / unsupported (dropped).
  Code:              citations.py links refs to URLs; published bullets are
                     written to memory so tomorrow's run won't repeat them.

Usage (from the repo folder, with the course venv active):
  python signalbrief_agent.py                      # all topics in topics.json
  python signalbrief_agent.py --only VST           # topics whose name matches
  python signalbrief_agent.py --topics my_topics.json --memory-dir memory_test
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

from agents import (
    Agent,
    ModelSettings,
    RunHooks,
    Runner,
    set_default_openai_api,
    set_default_openai_client,
    set_trace_processors,
)
from agents.items import ReasoningItem, ToolCallItem, ToolCallOutputItem
from agents.mcp import MCPServerStdio, MCPServerStdioParams
from agents.tracing import TracingProcessor
from dotenv import load_dotenv
from openai import AsyncOpenAI

from citations import REF_PATTERN, sources_from_tool_outputs, verify_and_link
from memory_store import DEFAULT_PATH as DEFAULT_MEMORY_DIR
from memory_store import CoverageMemory
from pipeline import (
    FactCheckReport,
    ToolBudget,
    apply_verdicts,
    budget_tool_filter,
    build_factcheck_request,
    build_research_packet,
    editor_input,
    effective_verdict,
    handoff_to_editor,
    react_trace,
    split_bullets,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
NEWS_SERVER = HERE / "news_mcp_server.py"
MEMORY_SERVER = HERE / "memory_mcp_server.py"
OUTPUT_DIR = HERE / "output"
MAX_TOPICS = 10
MAX_BULLETS = 4

# .env next to this script first, then any .env further up (e.g. course repo)
load_dotenv(HERE / ".env")
load_dotenv()

MODEL = os.getenv("SIGNALBRIEF_MODEL", "gpt-oss")

if not os.getenv("NRP_API_KEY") or os.getenv("NRP_API_KEY") == "your-nrp-token-here":
    sys.exit("NRP_API_KEY not found. Create a file named .env in this folder "
             "(copy .env.example to .env) and put your NRP key in it.")

client = AsyncOpenAI(
    base_url=os.getenv("NRP_BASE_URL", "https://ellm.nrp-nautilus.io/v1"),
    api_key=os.getenv("NRP_API_KEY"),
)
set_default_openai_client(client, use_for_tracing=False)
set_default_openai_api("chat_completions")


class ConsoleTracingProcessor(TracingProcessor):
    """Prints the agent trace (LLM calls, MCP tool calls, token usage)."""

    def on_trace_start(self, trace):
        print(f"\n[trace] '{trace.name}' started")

    def on_trace_end(self, trace):
        print(f"[trace] '{trace.name}' finished")

    def on_span_start(self, span):
        pass

    def on_span_end(self, span):
        data = span.span_data.export()
        summary = f"  [span] {data.get('type', 'unknown')}"
        if data.get("name"):
            summary += f" - {data['name']}"
        if data.get("usage"):
            summary += f" | usage={data['usage']}"
        print(summary)

    def shutdown(self):
        pass

    def force_flush(self):
        pass


set_trace_processors([ConsoleTracingProcessor()])


class BudgetHooks(RunHooks):
    """Counts every tool call against the run's ToolBudget (the run context)."""

    async def on_tool_start(self, context, agent, tool):
        if isinstance(context.context, ToolBudget):
            context.context.record(tool.name)


SCOUT_INSTRUCTIONS = """
You are the SignalBrief Scout, a research agent. You find what is NEW about one
topic a reader follows. You do not write the newsletter; you pick the sources.

Work in a ReAct loop. Before every action, think: what do I know so far, what
is missing, which ONE tool call fills the gap? After each result, read it and
decide whether to search again or stop.

1. First call recall_coverage once with the exact topic name, to see what the
   reader was already sent. Do not pick the same story again.
2. Then pick source tools by kind:
   - kind "artist"   -> get_artist_releases, then search_news for
                        "<artist> feature" or "<artist> new song".
   - kind "research" -> search_research_papers first; search_news optional.
   - kind "news"     -> search_news; if results are thin, retry ONCE with a
                        simpler or alternative query.
   You have at most 3 source-tool calls. Tools disappear once the budget is spent.
3. Use the lookback window from the prompt as the `days` argument.

Final answer: one line per selected source, 0 to 6 lines, best first:
- [ref] one short sentence on why it matters to this reader
Copy ref ids exactly from the `ref` field of tool results. Skip off-topic
items, duplicates, ads and sale/deal posts, and stories already sent. If
nothing qualifies, answer exactly: NONE
""".strip()

EDITOR_INSTRUCTIONS = """
You are the SignalBrief Editor, a careful research editor who writes one
section of a personal daily newsletter. You receive JSON from the Scout:
the topic, why the reader cares, and candidate sources (ref, title, source,
published date, why relevant). Accuracy beats volume.

Writing rules:
- Output 0 to 4 bullets, most important first. Each bullet is ONE line:
  - **Short headline.** One or two plain-English sentences on what happened and why it matters to this reader. [ref]
- Every bullet MUST end with one or more ref ids from the candidates, in
  square brackets, e.g. [n-3f2a9] or [p-81c0d][n-77b10].
- Only state facts that appear in the candidate titles and metadata. Never add
  numbers, rankings, dates, quotes or "first/biggest/best-selling" claims that
  the titles don't state. Never type URLs.
- For research papers, say plainly that it is a single study, and what kind
  only if the title makes it clear. Never imply a cure.
- If no candidate is worth a bullet, output exactly:
  _No notable updates in this window._
Do not add a heading, intro, or sign-off - just the bullets.
""".strip()

CHECKER_INSTRUCTIONS = """
You are the SignalBrief Fact-checker. You receive newsletter bullets, each with
the sources it cites (headline, outlet, date, type). You only see headlines and
metadata, so a claim is supported only if the cited headline/metadata states it
or directly implies it.

For EACH item, think step by step:
  1. In `claims`, list every factual claim in the bullet (what happened, who,
     numbers, dates, rankings, "first", "new", study type, outcomes), each with
     in_source = true only if a cited headline/metadata states or implies it.
  2. In `reasoning`, say which cited headline supports each claim, or that none does.
  3. Then decide (the verdict must agree with your claims list):
     - "supported": every factual claim is backed. A short, hedged note on why
       it matters to the reader is fine and is not a factual claim.
     - "overstated": the core news is backed but the bullet adds a detail the
       sources don't state. Write `revised_bullet`: the same bullet with the
       unsupported detail removed, same format, keeping its [ref] ids.
     - "unsupported": the main claim is not in the cited sources.
Return one verdict per item id. Be strict about invented specifics; do not
penalize plain-English paraphrase.
""".strip()


def build_agents(news_server, memory_server) -> tuple[Agent, Agent, Agent]:
    scout = Agent(
        name="SignalBrief Scout",
        instructions=SCOUT_INSTRUCTIONS,
        mcp_servers=[memory_server, news_server],
        model=MODEL,
        # one tool call per step: keeps the ReAct loop sequential and lets the
        # budget filter hide a tool before the model can call it again
        model_settings=ModelSettings(parallel_tool_calls=False),
    )
    editor = Agent(name="SignalBrief Editor", instructions=EDITOR_INSTRUCTIONS, model=MODEL)
    checker = Agent(
        name="SignalBrief Fact-checker",
        instructions=CHECKER_INSTRUCTIONS,
        model=MODEL,
        output_type=FactCheckReport,  # safe here: the checker has no tools
    )
    return scout, editor, checker


def load_topics(path: Path) -> list[dict]:
    """Load and validate the user's topic list (max 10 topics)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    topics = data["topics"] if isinstance(data, dict) else data
    if not topics:
        raise ValueError("topics file has no topics")
    if len(topics) > MAX_TOPICS:
        print(f"[warn] {len(topics)} topics given; SignalBrief keeps the first {MAX_TOPICS}.")
        topics = topics[:MAX_TOPICS]
    for t in topics:
        t.setdefault("kind", "news")
        t.setdefault("days", 3)
        t.setdefault("query", t["name"])
    return topics


def read_scout_items(result) -> tuple[list, list[str], list[str]]:
    """Turn the Scout's run items into ReAct steps, raw tool outputs and tool names."""
    steps, outputs, tools_called = [], [], []
    for item in result.new_items:
        if isinstance(item, ReasoningItem):
            raw = item.raw_item
            text = " ".join([c.text for c in (raw.content or []) if getattr(c, "text", None)]
                            + [s.text for s in (raw.summary or []) if getattr(s, "text", None)])
            if text.strip():
                steps.append(("thought", text))
        elif isinstance(item, ToolCallItem):
            name = getattr(item.raw_item, "name", "tool")
            tools_called.append(name)
            steps.append(("action", (name, getattr(item.raw_item, "arguments", ""))))
        elif isinstance(item, ToolCallOutputItem):
            out = item.output if isinstance(item.output, str) else json.dumps(item.output)
            outputs.append(out)
            steps.append(("observation", out))
    steps.append(("answer", str(result.final_output)))
    return steps, outputs, tools_called


def usage_of(result) -> dict:
    u = result.context_wrapper.usage
    return {"requests": u.requests, "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens, "total_tokens": u.total_tokens}


def empty_section(topic, note, **extra) -> dict:
    return {"topic": topic, "markdown": "_No notable updates in this window._", "note": note,
            "stats": {"kept": 0, "dropped": 0, "bad_refs": 0}, **extra}


async def brief_topic(agents: tuple[Agent, Agent, Agent], topic: dict,
                      memory: CoverageMemory) -> dict:
    scout, editor, checker = agents
    usage: dict[str, dict] = {}

    # ---- Agent 1: Scout (ReAct over MCP tools, budget enforced in code)
    prompt = (
        f"Today is {date.today().isoformat()}.\n"
        f"Topic name: {topic['name']}\n"
        f"Kind: {topic['kind']}\n"
        f"Search query to start with: {topic['query']}\n"
        f"Lookback window: last {topic['days']} days\n"
        f"Why the reader cares: {topic.get('why', 'not specified')}\n"
        "Research this topic now."
    )
    budget = ToolBudget(kind=topic.get("kind"))  # hides tools that don't fit the topic kind
    try:
        scout_result = await Runner.run(scout, prompt, context=budget, hooks=BudgetHooks(),
                                        max_turns=10)
    except Exception as exc:  # one bad topic should not kill the newsletter
        print(f"[error] Scout failed on '{topic['name']}': {exc}")
        return {**empty_section(topic, "scout error"), "error": str(exc),
                "markdown": "_Could not be researched today (agent error)._"}
    usage["scout"] = usage_of(scout_result)
    steps, outputs, tools_called = read_scout_items(scout_result)
    final = str(scout_result.final_output).strip()
    retried = False
    sources = sources_from_tool_outputs(outputs)
    if outputs and final != "NONE" and not REF_PATTERN.search(final):
        # Seen in testing: once the budget hides every tool, gpt-oss sometimes
        # "wants" another tool and ends with an empty answer. One retry, no tools.
        # M4: the retry gets a compact list of the records the tools returned instead of
        # the whole conversation (every raw tool result again, long Google News links
        # included); in the M4 baseline the Scout retried 2-3 times per E9 newsletter.
        print("[scout] empty/invalid final answer after tool budget -> one retry without tools")
        retried = True
        records = "\n".join(f"- [{r['ref']}] {r.get('title', '')} | {r.get('source', '')} | "
                            f"{r.get('published', '')}" for r in sources.values())
        try:
            retry = await Runner.run(
                scout.clone(mcp_servers=[]),
                f"{prompt}\n\nYour tool budget is spent. These are the records your tools "
                f"returned (ref | title | source | published):\n{records or '(none)'}\n\n"
                "Using ONLY these records, give your final answer now in the required "
                "format (- [ref] why), or NONE.",
                max_turns=1)
            usage["scout_retry"] = usage_of(retry)
            final = str(retry.final_output).strip()
            steps.append(("answer", final))
        except Exception as exc:
            print(f"[error] Scout retry failed on '{topic['name']}': {exc}")
    trace = react_trace(steps)
    for i, step in enumerate(trace, 1):
        for key in ("thought", "action", "observation", "answer"):
            if key in step:
                print(f"[react {i}] {key.upper()}: {step[key][:160]}")

    # ---- HANDOFF 1: Scout -> Editor (payload built in code from real tool records)
    packet = build_research_packet(
        topic, final, sources,
        memory_match=lambda rec: memory.find_match(topic["name"], rec))
    print(f"[handoff 1] Scout -> Editor: {len(packet['candidates'])} fresh candidates, "
          f"{len(packet['already_covered'])} already sent (memory), "
          f"{len(packet['invented_refs'])} invented refs dropped, "
          f"{packet['sources_returned']} records returned by tools")
    base = {"tools": tools_called, "budget": vars(budget), "react": trace, "packet": packet,
            "scout_retried": retried}
    if not handoff_to_editor(packet):
        print("[handoff 1] not triggered: nothing fresh and verified -> 'No notable updates'")
        return {**empty_section(topic, "no fresh candidates"), **base, "usage": usage}

    # ---- Agent 2: Editor
    try:
        editor_result = await Runner.run(editor, editor_input(packet), max_turns=2)
    except Exception as exc:
        print(f"[error] Editor failed on '{topic['name']}': {exc}")
        return {**empty_section(topic, "editor error"), **base, "usage": usage, "error": str(exc),
                "markdown": "_Could not be written today (agent error)._"}
    usage["editor"] = usage_of(editor_result)
    base["editor_raw"] = str(editor_result.final_output)
    bullets = split_bullets(base["editor_raw"])[:MAX_BULLETS]
    if not bullets:
        print(f"[editor] no bullets in output: {base['editor_raw'][:200]!r}")
        return {**empty_section(topic, "editor wrote no bullets"), **base, "usage": usage}

    # ---- HANDOFF 2: Editor -> Fact-checker
    request = build_factcheck_request(bullets, packet)
    print(f"[handoff 2] Editor -> Fact-checker: {len(bullets)} bullets, "
          f"{sum(len(i['cited_sources']) for i in request['items'])} cited sources attached")

    # ---- Agent 3: Fact-checker (chain-of-thought verdict per bullet)
    report = None
    try:
        checker_result = await Runner.run(checker, json.dumps(request, ensure_ascii=False),
                                          max_turns=2)
        usage["checker"] = usage_of(checker_result)
        report = checker_result.final_output
        for v in report.verdicts:
            verdict, override = effective_verdict(v)
            note = f" (model said {v.verdict.upper()}; overridden: {override})" if override else ""
            print(f"[check {v.id}] {verdict.upper()}{note}: {v.reasoning[:160]}")
    except Exception as exc:
        print(f"[error] Fact-checker failed on '{topic['name']}': {exc} (bullets kept as unchecked)")
    kept, fc_stats = apply_verdicts(bullets, report)

    # ---- Citation guardrail (code): only refs from this topic's packet can be linked
    packet_sources = {c["ref"]: sources[c["ref"]] for c in packet["candidates"]}
    markdown, stats = verify_and_link("\n".join(kept), packet_sources)
    print(f"[result] {topic['name']}: kept={stats['kept']} fact-check={fc_stats} "
          f"guardrail_dropped={stats['dropped']} bad_refs={stats['bad_refs']}")
    published_refs = dict.fromkeys(r for line in markdown_bullets(kept, packet_sources)
                                   for r in REF_PATTERN.findall(line))
    return {"topic": topic, "markdown": markdown, "stats": stats, "factcheck": fc_stats,
            "verdicts": [{**v.model_dump(), "effective_verdict": effective_verdict(v)[0],
                          "override": effective_verdict(v)[1]}
                         for v in report.verdicts] if report else [],
            "draft": bullets, "final_bullets": kept, **base, "usage": usage,
            "published": [packet_sources[r] for r in published_refs]}


def markdown_bullets(bullets: list[str], sources: dict) -> list[str]:
    """Bullets that survive the guardrail (cite at least one real source)."""
    return [b for b in bullets if any(r in sources for r in REF_PATTERN.findall(b))]


def render_newsletter(sections: list[dict], reader: str) -> str:
    today = date.today()
    kept = sum(s["stats"]["kept"] for s in sections)
    guard = sum(s["stats"]["dropped"] for s in sections)
    fc = {k: sum(s.get("factcheck", {}).get(k, 0) for s in sections)
          for k in ("overstated", "unsupported", "unchecked")}
    repeats = sum(len(s.get("packet", {}).get("already_covered", [])) for s in sections)
    active = [s["topic"]["name"] for s in sections if s["stats"]["kept"]]
    lines = [
        f"# SignalBrief - {today.strftime('%A, %B %d, %Y')}",
        f"*Your daily brief, {reader}: {len(sections)} topics checked, "
        f"{kept} cited updates.*",
        "",
    ]
    if active:
        lines += [f"**New today:** {', '.join(active)}", ""]
    for s in sections:
        t = s["topic"]
        lines += [f"## {t['name']}", f"<sub>last {t['days']} days</sub>", "", s["markdown"], ""]
    lines += [
        "---",
        f"*Verification: {kept} bullets linked to sources returned by live tools this run. "
        f"Fact-checker rewrote {fc['overstated']} overstated and removed {fc['unsupported']} "
        f"unsupported bullet(s); {fc['unchecked']} could not be checked. Citation guardrail "
        f"removed {guard} more. {repeats} story(ies) skipped because you already got them. "
        "Summaries are AI-generated from headlines - open the source before relying on them.*",
    ]
    return "\n".join(lines)


async def run(topics: list[dict], reader: str, memory_dir: Path, write_memory: bool = True):
    memory = CoverageMemory(memory_dir)
    print(f"[memory] {memory.count()} items remembered in {memory_dir}")
    news_server = MCPServerStdio(
        name="SignalBrief Sources",
        # pass the full env: the MCP client otherwise forwards only a few system vars,
        # and the eval's fault-injection switch (SIGNALBRIEF_FAULT) must reach the server
        params=MCPServerStdioParams(command=sys.executable, args=[str(NEWS_SERVER)],
                                    env=dict(os.environ)),
        client_session_timeout_seconds=90,
        cache_tools_list=True,
        tool_filter=budget_tool_filter,
    )
    memory_server = MCPServerStdio(
        name="SignalBrief Memory",
        params=MCPServerStdioParams(
            command=sys.executable, args=[str(MEMORY_SERVER)],
            env={**os.environ, "SIGNALBRIEF_MEMORY_DIR": str(memory_dir)}),
        client_session_timeout_seconds=90,
        cache_tools_list=True,
        tool_filter=budget_tool_filter,
    )
    async with news_server as news_srv, memory_server as mem_srv:
        agents = build_agents(news_srv, mem_srv)
        sections = []
        for topic in topics:  # sequential: keeps free APIs + NRP rate limits happy
            print(f"\n=== Researching: {topic['name']} ({topic['kind']}) ===")
            sections.append(await brief_topic(agents, topic, memory))

    # Memory is written only after every check, and only for published bullets.
    if write_memory:
        for s in sections:
            for rec in s.get("published", []):
                memory.remember(s["topic"]["name"], rec, rec.get("title", ""))
        print(f"[memory] now {memory.count()} items remembered")
    return sections


async def main():
    parser = argparse.ArgumentParser(description="SignalBrief multi-agent daily newsletter")
    parser.add_argument("--topics", default=str(HERE / "topics.json"))
    parser.add_argument("--only", help="only run topics whose name contains this text")
    parser.add_argument("--memory-dir", default=str(DEFAULT_MEMORY_DIR),
                        help="where the ChromaDB coverage memory lives")
    parser.add_argument("--no-memory-write", action="store_true",
                        help="read memory but don't record this run (for demos/tests)")
    parser.add_argument("--output", help="newsletter path (default: output/newsletter_<date>.md)")
    args = parser.parse_args()

    config = json.loads(Path(args.topics).read_text(encoding="utf-8"))
    reader = config.get("reader", "reader") if isinstance(config, dict) else "reader"
    topics = load_topics(Path(args.topics))
    if args.only:
        topics = [t for t in topics if args.only.lower() in t["name"].lower()]
        if not topics:
            sys.exit(f"No topic matches --only {args.only!r}")

    sections = await run(topics, reader, Path(args.memory_dir), not args.no_memory_write)

    newsletter = render_newsletter(sections, reader)
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = (Path(args.output) if args.output
                else OUTPUT_DIR / f"newsletter_{date.today().isoformat()}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(newsletter, encoding="utf-8")
    runs_dir = OUTPUT_DIR / "runs"
    runs_dir.mkdir(exist_ok=True)
    log_path = runs_dir / f"run_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
    log_path.write_text(json.dumps({"model": MODEL, "date": date.today().isoformat(),
                                    "sections": sections}, indent=1, default=str,
                                   ensure_ascii=False), encoding="utf-8")
    print("\n" + "=" * 70 + "\n" + newsletter + "\n" + "=" * 70)
    print(f"\nSaved newsletter to {out_path}")
    print(f"Saved run log (ReAct trace, handoff payloads, verdicts, token usage) to {log_path}")


if __name__ == "__main__":
    asyncio.run(main())
