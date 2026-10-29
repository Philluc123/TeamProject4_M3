"""
SignalBrief memory MCP server (read-only)
=========================================
Exposes the ChromaDB coverage memory (memory_store.py) to the Scout agent as
an MCP tool, so the agent can see what this reader was already told before
it decides what to search for.

Tool
----
- recall_coverage(topic, days) -> what SignalBrief already sent for this topic

Writing to memory is deliberately NOT a tool: only signalbrief_agent.py
writes, and only bullets that passed the fact-checker and citation guardrail.

Run standalone (for debugging):  python memory_mcp_server.py
"""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from memory_store import DEFAULT_PATH, CoverageMemory

mcp = FastMCP("SignalBrief Memory")
memory = CoverageMemory(os.getenv("SIGNALBRIEF_MEMORY_DIR", DEFAULT_PATH))


@mcp.tool()
def recall_coverage(topic: str, days: int = 30) -> str:
    """List what SignalBrief already sent this reader about a topic.

    Call this ONCE, before searching, with the exact topic name. Returns JSON
    with past items (title, source, published date, date sent). Do not select
    a story again if it is the same as one listed here, unless there is a
    genuinely new development. An empty list means nothing was sent yet.
    """
    days = max(1, min(90, int(days)))
    items = memory.recent(topic, days=days)
    return json.dumps({
        "topic": topic,
        "days": days,
        "already_sent": [
            {"title": m["title"], "source": m["source"],
             "published": m["published"], "sent_on": m["sent_on"]}
            for m in items[:15]
        ],
    }, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
