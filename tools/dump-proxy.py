#!/usr/bin/env python3
"""dump-proxy.py — record Claude Code's request bodies to answer E1.

Sits between Claude Code and llama-server, forwards everything untouched, and
writes each /v1/messages request body to disk plus a manifest of per-message
hashes. The hashes are the point: when a divergence happens, comparing two
manifests names the exact message index that changed, without diffing 500 KB of
JSON by eye.

    Claude Code  ->  :8004 (this)  ->  :8003 (llama-server)

Streaming is preserved. Prefill can take 7+ minutes before the first SSE byte,
so nothing may be buffered and no timeout may be short.

    ./dump-proxy.py                       # 8004 -> 8003, dumps to ~/e1-dumps
    DP_PORT=9000 DP_UPSTREAM=8003 ./dump-proxy.py

Then point the client at port 8004 instead of 8003 and run a normal session.
Analyse with ./analyze-divergence.py once a divergence appears.

Captures are append-only: numbering resumes past whatever is already in DUMP_DIR
and files are created exclusively, so a restart can never overwrite an earlier
session's requests.

WARNING: these files are raw session transcripts. They contain whatever you were
working on -- source, paths, and anything you typed. Do not commit them.
"""

import hashlib
import http.client
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("DP_PORT", 8004))
UP_HOST = os.environ.get("DP_UPSTREAM_HOST", "127.0.0.1")
UP_PORT = int(os.environ.get("DP_UPSTREAM", 8003))
DUMP_DIR = os.environ.get("DP_DIR", "/home/linux/e1-dumps")
# A cold prefill on a 117k-token prompt runs ~7 min before the first byte.
# Anything short here would manufacture the very failure we are studying.
TIMEOUT = int(os.environ.get("DP_TIMEOUT", 3600))

os.makedirs(DUMP_DIR, exist_ok=True)
_lock = threading.Lock()
MANIFEST = os.path.join(DUMP_DIR, "manifest.jsonl")


def _resume_seq():
    """Continue numbering after whatever is already on disk.

    This used to start at 0 unconditionally, so restarting the proxy silently
    overwrote req-00001.json onward IN PLACE. A capture set believed to be one
    session would quietly become a mix of two, and nothing surfaced it -- the
    files still parsed, still had plausible message counts, and only stopped
    matching when their token counts were re-derived days later. Eight requests
    of an unrelated session were published before it was caught.
    """
    high = 0
    for name in os.listdir(DUMP_DIR):
        m = re.fullmatch(r"req-(\d{5})\.json", name)
        if m:
            high = max(high, int(m.group(1)))
    if high:
        print(f"resuming at #{high + 1} ({high} existing captures preserved)")
    return high


_seq = _resume_seq()


def _next_seq():
    global _seq
    with _lock:
        _seq += 1
        return _seq


def _hash(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12]


def record(body: bytes) -> None:
    """Persist one request body and a per-message hash manifest entry."""
    n = _next_seq()
    path = os.path.join(DUMP_DIR, f"req-{n:05d}.json")
    # "xb", not "wb": exclusive create. Even if the sequence were somehow wrong,
    # an existing capture can never be clobbered -- it raises instead.
    try:
        with open(path, "xb") as f:
            f.write(body)
    except FileExistsError:
        print(f"  ! refusing to overwrite {path}", file=sys.stderr, flush=True)
        return

    entry = {
        "seq": n,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": len(body),
        "file": os.path.basename(path),
    }
    try:
        d = json.loads(body)
        msgs = d.get("messages", [])
        entry["n_messages"] = len(msgs)
        entry["system_hash"] = _hash(d.get("system", ""))
        entry["tools_hash"] = _hash(d.get("tools", []))
        # Per-message hashes: the first index where two requests differ is the
        # divergence point, and whether the tail merely SHIFTED (same hashes,
        # new offset) or was REWRITTEN is exactly the E1 question.
        entry["msg_hashes"] = [_hash(m) for m in msgs]
    except Exception as e:  # a malformed body is still worth having on disk
        entry["parse_error"] = str(e)

    with _lock, open(MANIFEST, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"[{entry['ts']}] #{n} {len(body):>9,}B "
          f"msgs={entry.get('n_messages','?')}", flush=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # keep stdout to our own records
        pass

    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        # Substring match, NOT endswith: the client may append a query string
        # (e.g. /v1/messages?beta=true), and an endswith() test silently
        # forwarded every request unrecorded — the whole rig looked healthy
        # while capturing nothing.
        if body and "/v1/messages" in self.path:
            try:
                record(body)
            except Exception as e:
                print(f"  ! record failed: {e}", file=sys.stderr, flush=True)
        elif body:
            print(f"  (not recorded) {method} {self.path} {len(body):,}B",
                  flush=True)

        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length",
                                        "transfer-encoding", "connection")}
        if body:
            headers["Content-Length"] = str(len(body))

        try:
            conn = http.client.HTTPConnection(UP_HOST, UP_PORT, timeout=TIMEOUT)
            conn.request(method, self.path, body=body, headers=headers)
            resp = conn.getresponse()
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"proxy upstream error: {e}".encode())
            return

        self.send_response(resp.status)
        for k, v in resp.getheaders():
            # We re-frame the body ourselves, so drop upstream framing headers.
            if k.lower() not in ("content-length", "transfer-encoding",
                                 "connection"):
                self.send_header(k, v)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        try:
            while True:
                # read1(), NOT read(): read() blocks until it has the full 8192
                # bytes, and SSE events are ~150 B each, so it would sit on ~50
                # tokens before forwarding any. Measured: read() gave a 0.0 ms
                # median inter-delta gap (one burst) against 53.9 ms direct.
                chunk = resp.read1(8192)
                if not chunk:
                    break
                # Chunked framing, flushed immediately: SSE must not be buffered.
                self.wfile.write(f"{len(chunk):x}\r\n".encode())
                self.wfile.write(chunk)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # client hung up mid-stream; upstream keeps going, that is fine
        finally:
            conn.close()

    def do_POST(self):
        self._proxy("POST")

    def do_GET(self):
        self._proxy("GET")


if __name__ == "__main__":
    print(f"dump-proxy  :{PORT} -> {UP_HOST}:{UP_PORT}")
    print(f"dumps       {DUMP_DIR}")
    print(f"point the client at  http://<this-host>:{PORT}\n", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
