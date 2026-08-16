#!/usr/bin/env python3
"""stub-server.py — measure Claude Code's first-byte budget without a model.

#5 asserts a 1800 s first-byte budget and that one timeout becomes "10 retries,
each re-prefilling for ~30 minutes". The env var names check out in the 2.1.228
binary; the numbers never have.

Bisecting by trial would cost one full timeout per probe. Instead this stub accepts
/v1/messages, never answers, and watches the socket: when the client gives up it
closes the connection, and select() on the request socket reports EOF. That timestamp
IS the budget, measured exactly, in a single trial.

Retries then arrive as fresh POSTs. Same body hash = the client is re-sending the
identical prompt, which is what makes a timeout expensive on a real server.

    ./stub-server.py                       # :8020, waits up to 2400 s
    SS_PORT=9000 SS_MAX=600 ./stub-server.py

    # in another shell:
    ANTHROPIC_BASE_URL=http://127.0.0.1:8020 ANTHROPIC_API_KEY=x \\
      claude -p 'hi' --model deepseek-v4-flash
"""

import hashlib
import json
import os
import select
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("SS_PORT", 8020))
MAX_WAIT = int(os.environ.get("SS_MAX", 2400))

T0 = time.time()
_lock = threading.Lock()
_seen = {}          # body hash -> first-seen sequence number
_n = 0


def log(msg):
    print(f"[{time.time()-T0:8.1f}s] {msg}", flush=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        global _n
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        h = hashlib.sha256(body).hexdigest()[:12]

        with _lock:
            _n += 1
            seq = _n
            first = _seen.setdefault(h, seq)

        kind = "NEW" if first == seq else f"RETRY of #{first}"
        try:
            n_msgs = len(json.loads(body).get("messages", []))
        except Exception:
            n_msgs = "?"
        log(f"#{seq} POST {self.path}  {len(body):,}B  msgs={n_msgs}  body={h}  {kind}")

        # Never send a byte. Sit here and watch for the client to hang up; the
        # moment it does is the first-byte budget. Reading the socket is safe:
        # the request body is fully consumed, so anything readable is either a
        # pipelined request or EOF.
        sock = self.connection
        start = time.time()
        while time.time() - start < MAX_WAIT:
            r, _, _ = select.select([sock], [], [], 1.0)
            if r:
                try:
                    if sock.recv(1, 0x02) == b"":   # MSG_PEEK
                        log(f"#{seq} CLIENT GAVE UP after {time.time()-start:.1f}s"
                            f"  <-- first-byte budget")
                        return
                except OSError:
                    log(f"#{seq} socket error after {time.time()-start:.1f}s")
                    return
        log(f"#{seq} still connected at SS_MAX={MAX_WAIT}s — budget is larger")

    def do_GET(self):
        # Claude Code probes /v1/models on some paths; answer so startup proceeds.
        payload = json.dumps({"data": [{"id": "deepseek-v4-flash",
                                        "type": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    print(f"stub :{PORT}  never answers /v1/messages, max wait {MAX_WAIT}s")
    print("point ANTHROPIC_BASE_URL here and watch for 'CLIENT GAVE UP'\n", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
