"""SignalBrief web UI: set topics, run the 3-agent pipeline, read the newsletter.

Standard library only. The page posts its topics here; we write them to
output/web_topics.json, run signalbrief_agent.py as a subprocess (so the CLI
stays the single source of truth) and stream its console output back line by line.

Usage (from the repo folder, with the course venv active):
  python web_app.py              # then open http://127.0.0.1:8000
  python web_app.py --port 8080
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE / "web" / "index.html"
OUTPUT_DIR = HERE / "output"
WEB_TOPICS = OUTPUT_DIR / "web_topics.json"
KINDS = {"news", "artist", "research"}
MAX_TOPICS = 10
run_lock = threading.Lock()  # one pipeline run at a time


def clean_topics(raw: list) -> list[dict]:
    """Keep only well-formed topics; clamp days so a typo can't blow up the search window."""
    topics = []
    for t in raw[:MAX_TOPICS]:
        name = str(t.get("name", "")).strip()
        if not name:
            continue
        kind = t.get("kind") if t.get("kind") in KINDS else "news"
        try:
            days = max(1, min(int(t.get("days", 3)), 60))
        except (TypeError, ValueError):
            days = 3
        topics.append({"name": name, "kind": kind,
                       "query": str(t.get("query") or name).strip(),
                       "days": days, "why": str(t.get("why", "")).strip()})
    return topics


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the server console quiet
        pass

    def send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/topics":
            self.send(200, (HERE / "topics.json").read_bytes(), "application/json")
        elif self.path.startswith("/api/newsletter"):
            files = sorted(OUTPUT_DIR.glob("newsletter_*.md"))
            if files:
                self.send(200, files[-1].read_bytes(), "text/markdown; charset=utf-8")
            else:
                self.send(404, b"No newsletter yet.", "text/plain")
        else:
            self.send(404, b"Not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/run":
            return self.send(404, b"Not found", "text/plain")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            topics = clean_topics(body.get("topics", []))
        except (ValueError, AttributeError):
            return self.send(400, b"Bad request body.", "text/plain")
        if not topics:
            return self.send(400, b"Add at least one topic.", "text/plain")
        if not run_lock.acquire(blocking=False):
            return self.send(409, b"A run is already in progress.", "text/plain")
        try:
            OUTPUT_DIR.mkdir(exist_ok=True)
            reader = str(body.get("reader") or "reader").strip()
            WEB_TOPICS.write_text(json.dumps({"reader": reader, "topics": topics}, indent=2),
                                  encoding="utf-8")
            cmd = [sys.executable, "-u", str(HERE / "signalbrief_agent.py"), "--topics", str(WEB_TOPICS)]
            if body.get("no_memory_write"):
                cmd.append("--no-memory-write")

            # HTTP/1.0 response with no Content-Length: the stream ends when we close.
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            proc = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", bufsize=1)
            try:
                for line in proc.stdout:
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
                code = proc.wait()
                self.wfile.write(f"\n[web] pipeline exited with code {code}\n".encode())
            except (BrokenPipeError, ConnectionResetError):
                proc.kill()  # browser left: stop spending tokens
        finally:
            run_lock.release()


def main():
    parser = argparse.ArgumentParser(description="SignalBrief web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"SignalBrief UI on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
