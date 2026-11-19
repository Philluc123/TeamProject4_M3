"""SignalBrief web UI: set topics, run the 3-agent pipeline, read the newsletter.

Standard library only (python-dotenv is used if present). The page posts its topics
here; we write them to output/web/<reader>/topics.json, run signalbrief_agent.py as a
subprocess (so the CLI stays the single source of truth) and stream its console
output back line by line.

Built to be shared with testers through a Cloudflare quick tunnel:
  - password-protected (HTTP Basic auth; testers can type any username),
  - each reader name gets its own coverage memory and newsletter,
  - one run at a time, at most MAX_TOPICS topics per run.

Usage (from the repo folder, with the venv active):
  python web_app.py --password <pick-one>     # or set SIGNALBRIEF_UI_PASSWORD in .env
  cloudflared tunnel --url http://localhost:8000     # in a second terminal
"""

from __future__ import annotations

import argparse
import base64
import hmac
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
PAGE = HERE / "web" / "index.html"
WEB_OUT = HERE / "output" / "web"          # per-reader topics + newsletters
WEB_MEMORY = HERE / "memory_web"           # per-reader coverage memory (gitignored)
KINDS = {"news", "artist", "research"}
MAX_TOPICS = 3
MINUTES_PER_TOPIC = 2                      # rough estimate shown to waiting testers

try:  # let the password live in .env next to the NRP key
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
except ImportError:
    pass

PASSWORD = ""                              # set in main()
run_lock = threading.Lock()                # one pipeline run at a time
current_run: dict = {}                     # who is running, since when, how many topics


def reader_slug(name: str) -> str:
    """Folder-safe id for a reader name: 'Sam O'Neil' -> 'sam-o-neil'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]


def clean_topics(raw: list) -> list[dict]:
    """Keep only well-formed topics; clamp days so a typo can't blow up the search window."""
    topics = []
    for t in raw:
        if not isinstance(t, dict):
            continue
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
    return topics[:MAX_TOPICS]


def busy_message() -> str:
    started = current_run.get("started", time.time())
    elapsed = int((time.time() - started) // 60)
    left = max(1, current_run.get("topics", 1) * MINUTES_PER_TOPIC - elapsed)
    return (f"Someone else's edition is on the presses right now (started {elapsed} min ago). "
            f"Please try again in about {left} minute{'s' if left != 1 else ''}.")


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.1 so the live run output can use chunked encoding: proxies such as Cloud Run
    # and Cloudflare pass chunks through as they arrive.
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the server console quiet
        pass

    def chunk(self, data: bytes) -> None:
        self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    def send(self, code: int, body: bytes, ctype: str, headers: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def authorized(self) -> bool:
        """HTTP Basic auth: any username, the right password. Browsers prompt for it."""
        if not PASSWORD:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                _, _, given = base64.b64decode(header[6:]).decode("utf-8").partition(":")
                if hmac.compare_digest(given.encode(), PASSWORD.encode()):
                    return True
            except ValueError:
                pass
        self.send(401, b"Password required.", "text/plain",
                  {"WWW-Authenticate": 'Basic realm="SignalBrief", charset="UTF-8"'})
        return False

    def do_GET(self):
        if not self.authorized():
            return
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/topics":
            # example topics only; never hand out the owner's reader name
            cfg = json.loads((HERE / "topics.json").read_text(encoding="utf-8"))
            body = {"topics": clean_topics(cfg.get("topics", [])), "max_topics": MAX_TOPICS}
            self.send(200, json.dumps(body).encode(), "application/json")
        elif url.path == "/api/newsletter":
            slug = reader_slug(parse_qs(url.query).get("reader", [""])[0])
            files = sorted((WEB_OUT / slug).glob("newsletter_*.md")) if slug else []
            if files:
                self.send(200, files[-1].read_bytes(), "text/markdown; charset=utf-8")
            else:
                self.send(404, b"No newsletter yet.", "text/plain")
        else:
            self.send(404, b"Not found", "text/plain")

    def do_POST(self):
        if not self.authorized():
            return
        if self.path != "/api/run":
            return self.send(404, b"Not found", "text/plain")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            topics = clean_topics(body.get("topics", []))
            reader = str(body.get("reader") or "").strip()[:60]
        except (ValueError, AttributeError):
            return self.send(400, b"Something went wrong sending your topics. Reload and try again.",
                             "text/plain; charset=utf-8")
        slug = reader_slug(reader)
        if not slug:
            return self.send(400, b"Please type your name first, so your news stays separate.",
                             "text/plain; charset=utf-8")
        if not topics:
            return self.send(400, b"Add at least one topic.", "text/plain; charset=utf-8")
        if not run_lock.acquire(blocking=False):
            return self.send(409, busy_message().encode("utf-8"), "text/plain; charset=utf-8")
        try:
            current_run.update(started=time.time(), topics=len(topics))
            out_dir = WEB_OUT / slug
            out_dir.mkdir(parents=True, exist_ok=True)
            topics_file = out_dir / "topics.json"
            topics_file.write_text(json.dumps({"reader": reader, "topics": topics}, indent=2),
                                   encoding="utf-8")
            newsletter = out_dir / f"newsletter_{time.strftime('%Y-%m-%d_%H%M%S')}.md"
            cmd = [sys.executable, "-u", str(HERE / "signalbrief_agent.py"),
                   "--topics", str(topics_file),
                   "--memory-dir", str(WEB_MEMORY / slug),
                   "--output", str(newsletter)]
            if body.get("no_memory_write"):
                cmd.append("--no-memory-write")
            print(f"[web] {time.strftime('%H:%M')} run for {reader!r}: "
                  + ", ".join(t["name"] for t in topics), flush=True)

            # Chunked stream; text/event-stream + no-cache keeps proxies from buffering it.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            # UTF-8 child output on Windows too (a pipe would otherwise default to cp1252)
            env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            proc = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", bufsize=1, env=env)
            try:
                for line in proc.stdout:
                    self.chunk(line.encode("utf-8"))
                code = proc.wait()
                self.chunk(f"\n[web] pipeline exited with code {code}\n".encode())
                self.wfile.write(b"0\r\n\r\n")  # end of chunked body
                self.wfile.flush()
                print(f"[web] {time.strftime('%H:%M')} run for {reader!r} finished (code {code})",
                      flush=True)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                proc.kill()  # browser left: stop spending tokens
                print(f"[web] {time.strftime('%H:%M')} {reader!r} closed the page; run stopped",
                      flush=True)
        finally:
            current_run.clear()
            run_lock.release()


def main():
    global PASSWORD
    parser = argparse.ArgumentParser(description="SignalBrief web UI")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--password", default=os.environ.get("SIGNALBRIEF_UI_PASSWORD", ""),
                        help="password testers type in (default: SIGNALBRIEF_UI_PASSWORD)")
    args = parser.parse_args()
    PASSWORD = args.password
    print(f"SignalBrief UI on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    if PASSWORD:
        print("Password protection is ON (any username + your password).")
    else:
        print("WARNING: no password set. Anyone with a tunnel link can run the agents on your "
              "NRP token. Use --password or SIGNALBRIEF_UI_PASSWORD before sharing.")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
