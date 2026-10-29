"""
Coverage memory for SignalBrief (M3 knowledge / memory layer).
=================================================================
A persistent ChromaDB vector store of every bullet SignalBrief has already
published. It answers one question: "did we already tell this reader about
this story?" so the same news doesn't show up two days in a row.

- One record per published source: id = hash of the source URL.
- The embedded text is the source headline (plus the bullet headline), so a
  re-worded headline about the same story still lands close in vector space.
- Embeddings come from Chroma's built-in all-MiniLM-L6-v2 ONNX model, which
  runs locally (no API key; ~80 MB download on first use).

Writes happen only in signalbrief_agent.py, AFTER the fact-checker and the
citation guardrail, so nothing invented can ever be stored as "already covered".
The agent reads memory through memory_mcp_server.py (MCP tool), and the
handoff code reads it directly to mark repeats.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path

import chromadb

DEFAULT_PATH = Path(__file__).resolve().parent / "memory"
COLLECTION = "signalbrief_coverage"
# Cosine distance at or below this counts as "same story". Measured with the
# default embedder: a re-worded Serum 2 headline scored 0.21, unrelated
# music/medical headlines scored ~0.7.
SAME_STORY_DISTANCE = 0.35


def topic_key(name: str) -> str:
    return " ".join(name.lower().split())


def url_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


class CoverageMemory:
    def __init__(self, path: Path | str = DEFAULT_PATH, client=None):
        self.client = client or chromadb.PersistentClient(path=str(path))
        self.col = self.client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"})

    # ------------------------------------------------------------ write
    def remember(self, topic: str, record: dict, bullet: str, sent_on: str | None = None) -> None:
        """Store one published source (record = a tool result with url/title/published)."""
        sent_on = sent_on or date.today().isoformat()
        doc = f"{record.get('title', '')} | {bullet}".strip(" |")
        self.col.upsert(
            ids=[url_id(record["url"])],
            documents=[doc],
            metadatas=[{
                "topic": topic_key(topic),
                "title": record.get("title", ""),
                "url": record["url"],
                "source": record.get("source") or record.get("journal") or "MusicBrainz",
                "published": record.get("published", ""),
                "sent_on": sent_on,
            }],
        )

    # ------------------------------------------------------------ read
    def count(self) -> int:
        return self.col.count()

    def recent(self, topic: str, days: int = 30, today: date | None = None) -> list[dict]:
        """Everything already sent for a topic in the last `days` days, newest first."""
        cutoff = ((today or date.today()) - timedelta(days=days)).isoformat()
        got = self.col.get(where={"topic": topic_key(topic)})
        rows = [m for m in got["metadatas"] if m.get("sent_on", "") >= cutoff]
        return sorted(rows, key=lambda m: m.get("sent_on", ""), reverse=True)

    def find_match(self, topic: str, record: dict, days: int = 30,
                   today: date | None = None) -> dict | None:
        """Return the remembered item this record repeats, or None if it is new.

        Exact URL first (cheap, certain), then nearest headline in the same
        topic within the window (semantic, catches the same story from a
        different outlet or a re-worded title).
        """
        cutoff = ((today or date.today()) - timedelta(days=days)).isoformat()
        exact = self.col.get(ids=[url_id(record["url"])])
        if exact["ids"] and exact["metadatas"][0].get("sent_on", "") >= cutoff:
            return {**exact["metadatas"][0], "match": "same_url", "distance": 0.0}
        if self.col.count() == 0 or not record.get("title"):
            return None
        res = self.col.query(query_texts=[record["title"]], n_results=3,
                             where={"topic": topic_key(topic)})
        for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
            if dist <= SAME_STORY_DISTANCE and meta.get("sent_on", "") >= cutoff:
                return {**meta, "match": "same_story", "distance": round(dist, 3)}
        return None
