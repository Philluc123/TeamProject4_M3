"""
SignalBrief M3 pipeline logic: tool budget, ReAct trace, handoffs, verdicts.
============================================================================
Everything here is plain Python (no model calls), so it is unit-tested
offline in tests/run_tests.py. signalbrief_agent.py wires it to the agents.

Per topic:
  Scout (ReAct, MCP tools) --HANDOFF 1: ResearchPacket--> Editor
  Editor (writes bullets)   --HANDOFF 2: FactCheckRequest--> Fact-checker
  Fact-checker verdicts --> apply_verdicts() --> citations.verify_and_link()

Both handoff payloads are BUILT BY CODE from records the MCP tools actually
returned. The models only choose (Scout picks ref ids, Editor writes text,
Fact-checker judges); they never get to inject a source of their own.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Literal

from pydantic import BaseModel, Field

from citations import BULLET_PATTERN, REF_PATTERN, REF_GROUP_PATTERN

SOURCE_TOOLS = {"search_news", "search_research_papers", "get_artist_releases"}
MEMORY_TOOLS = {"recall_coverage"}


# ---------------------------------------------------------------- tool budget
@dataclass
class ToolBudget:
    """Per-topic tool budget, enforced in code (M2 only asked nicely in the prompt).

    Passed as the run `context`; the MCP tool filter hides a tool once its
    budget is spent, so the model physically cannot call it again.
    """
    max_source_calls: int = 3
    max_memory_calls: int = 1
    source_calls: int = 0
    memory_calls: int = 0

    def allows(self, tool_name: str) -> bool:
        if tool_name in SOURCE_TOOLS:
            return self.source_calls < self.max_source_calls
        if tool_name in MEMORY_TOOLS:
            return self.memory_calls < self.max_memory_calls
        return True

    def record(self, tool_name: str) -> None:
        if tool_name in SOURCE_TOOLS:
            self.source_calls += 1
        elif tool_name in MEMORY_TOOLS:
            self.memory_calls += 1


def budget_tool_filter(filter_context, tool) -> bool:
    """MCP dynamic tool filter: show a tool only while the run's budget allows it."""
    budget = getattr(filter_context.run_context, "context", None)
    if isinstance(budget, ToolBudget):
        return budget.allows(tool.name)
    return True


# ---------------------------------------------------------------- ReAct trace
def _observation_summary(output: str) -> str:
    try:
        data = json.loads(output)
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            data = json.loads(data["text"])
    except (json.JSONDecodeError, TypeError):
        return output[:120]
    if not isinstance(data, dict):
        return str(data)[:120]
    if data.get("error"):
        return f"error: {data['error']}"
    for key in ("articles", "papers", "releases", "already_sent"):
        if key in data:
            return f"{len(data[key])} {key.replace('_', ' ')}"
    return str(data)[:120]


def react_trace(steps: list[tuple[str, object]]) -> list[dict]:
    """Group a run's items into Thought -> Action -> Observation steps.

    `steps` is a simplified list of (kind, payload) built from the SDK's
    run items: ("thought", text), ("action", (name, args)), ("observation", text),
    ("answer", text). Thoughts come from gpt-oss's own reasoning output.
    """
    trace: list[dict] = []
    current: dict = {}
    for kind, payload in steps:
        if kind == "thought":
            if current.get("action") or current.get("thought"):
                trace.append(current)
                current = {}
            current["thought"] = str(payload).strip()
        elif kind == "action":
            name, args = payload
            if current.get("action"):
                trace.append(current)
                current = {}
            current["action"] = f"{name}({args})"
        elif kind == "observation":
            current["observation"] = _observation_summary(str(payload))
            trace.append(current)
            current = {}
        elif kind == "answer":
            if current:
                trace.append(current)
                current = {}
            trace.append({"answer": str(payload).strip()[:300]})
    if current:
        trace.append(current)
    return trace


# ---------------------------------------------------------------- handoff 1
def build_research_packet(topic: dict, scout_text: str, sources: dict,
                          memory_match: Callable[[dict], dict | None] | None = None) -> dict:
    """HANDOFF 1 payload (Scout -> Editor), built from real tool records.

    - Each ref the Scout selected must exist in `sources` (what tools returned
      this run); anything else is counted as invented and dropped.
    - Each surviving record is checked against coverage memory; repeats are
      moved to `already_covered` and NOT passed to the Editor.
    """
    candidates, covered, invented = [], [], []
    seen: set[str] = set()
    for line in scout_text.splitlines():
        refs = REF_PATTERN.findall(line)
        why = REF_GROUP_PATTERN.sub("", BULLET_PATTERN.sub("", line.strip())).strip(" -:–—")
        for ref in refs:
            if ref in seen:
                continue
            seen.add(ref)
            rec = sources.get(ref)
            if rec is None:
                invented.append(ref)
                continue
            item = {
                "ref": ref,
                "title": rec.get("title", ""),
                "source": rec.get("source") or rec.get("journal") or "MusicBrainz",
                "published": rec.get("published", ""),
                "type": rec.get("type", ""),
                "why_relevant": why[:300],
            }
            match = memory_match(rec) if memory_match else None
            if match:
                covered.append({**item, "covered_by": match.get("title", ""),
                                "sent_on": match.get("sent_on", ""), "match": match.get("match")})
            else:
                candidates.append(item)
    return {
        "topic": {k: topic.get(k) for k in ("name", "kind", "days", "why")},
        "candidates": candidates,
        "already_covered": covered,
        "invented_refs": invented,
        "sources_returned": len(sources),
    }


def handoff_to_editor(packet: dict) -> bool:
    """Trigger for HANDOFF 1: at least one verified, not-yet-covered candidate."""
    return len(packet["candidates"]) > 0


def editor_input(packet: dict) -> str:
    """What the Editor actually receives (no URLs, no covered items)."""
    return json.dumps({"topic": packet["topic"], "candidates": packet["candidates"]},
                      ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- handoff 2
def split_bullets(text: str) -> list[str]:
    """Normalize the Editor's output to '- ...' bullets.

    A line that cites a ref counts as a bullet even without a '- ' marker:
    gpt-oss sometimes drops the dash when it writes a single bullet, and M2
    silently threw those lines away.
    """
    out = []
    for line in text.strip().splitlines():
        s = line.strip()
        m = BULLET_PATTERN.match(s)
        if m:
            out.append("- " + s[m.end():].strip())
        elif REF_PATTERN.search(s):
            out.append("- " + s)
    return out


def build_factcheck_request(bullets: list[str], packet: dict) -> dict:
    """HANDOFF 2 payload (Editor -> Fact-checker): each bullet + the records it cites."""
    by_ref = {c["ref"]: c for c in packet["candidates"]}
    items = []
    for i, b in enumerate(bullets):
        cited = [by_ref[r] for r in dict.fromkeys(REF_PATTERN.findall(b)) if r in by_ref]
        items.append({
            "id": i,
            "bullet": b,
            "cited_sources": [{k: c[k] for k in ("ref", "title", "source", "published", "type")}
                              for c in cited],
        })
    return {"topic": packet["topic"]["name"], "items": items}


class Claim(BaseModel):
    claim: str = Field(description="One factual claim made by the bullet")
    in_source: bool = Field(description="True only if a cited headline/metadata states it or "
                                        "directly implies it")


class Verdict(BaseModel):
    id: int = Field(description="id of the bullet being checked")
    claims: list[Claim] = Field(default_factory=list,
                                description="Every factual claim in the bullet, checked one by one")
    reasoning: str = Field(description="Step by step: list each claim in the bullet and "
                                       "whether the cited headline/metadata states it.")
    verdict: Literal["supported", "overstated", "unsupported"]
    revised_bullet: str = Field(default="", description="For 'overstated' only: the bullet "
                                "rewritten to claim only what the sources state, keeping its [ref] ids.")


class FactCheckReport(BaseModel):
    verdicts: list[Verdict]


# Phrases that mean the checker itself found a claim missing from the source.
NOT_IN_SOURCE = re.compile(
    r"not (?:mentioned|stated|present|supported by|in the (?:headline|source|title))"
    r"|does(?:n['’]t| not) (?:mention|state|say|support)|no mention", re.I)


def effective_verdict(v: Verdict) -> tuple[str, str]:
    """The verdict code will act on, plus why it differs from the model's (if it does).

    Seen in live test L6: gpt-oss wrote "top-selling track of the week - not
    mentioned" in its reasoning and still answered "supported". A "supported"
    verdict is only accepted if the checker's own claim list and reasoning agree.
    """
    if v.verdict == "supported":
        missing = [c.claim for c in v.claims if not c.in_source]
        if missing:
            return "overstated", f"claims marked not in source: {missing}"
        if NOT_IN_SOURCE.search(v.reasoning):
            return "overstated", "reasoning says a claim is not in the source"
    return v.verdict, ""


def apply_verdicts(bullets: list[str], report: FactCheckReport | None) -> tuple[list[str], dict]:
    """Keep supported bullets, swap in revisions for overstated ones, drop unsupported.

    A bullet with no verdict (checker failed or skipped it) is kept but counted
    as `unchecked`, and the newsletter footer says so. A "supported" verdict that
    contradicts the checker's own reasoning is treated as overstated (counted in
    `overridden`); with no rewrite offered, that bullet is dropped.
    """
    stats = {"supported": 0, "overstated": 0, "unsupported": 0, "unchecked": 0, "overridden": 0}
    verdicts = {v.id: v for v in (report.verdicts if report else [])}
    kept = []
    for i, b in enumerate(bullets):
        v = verdicts.get(i)
        verdict, override = effective_verdict(v) if v else (None, "")
        if override:
            stats["overridden"] += 1
        if v is None:
            stats["unchecked"] += 1
            kept.append(b)
        elif verdict == "supported":
            stats["supported"] += 1
            kept.append(b)
        elif verdict == "overstated":
            stats["overstated"] += 1
            revised = v.revised_bullet.strip()
            if not revised:
                continue  # no safe rewrite offered -> drop rather than publish the overstatement
            if not REF_PATTERN.search(revised):  # checker dropped the citation; restore it
                refs = " ".join(f"[{r}]" for r in dict.fromkeys(REF_PATTERN.findall(b)))
                revised = f"{revised} {refs}"
            kept.append(revised if BULLET_PATTERN.match(revised) else "- " + revised)
        else:
            stats["unsupported"] += 1
    return kept, stats
