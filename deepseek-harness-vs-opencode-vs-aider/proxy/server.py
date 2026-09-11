"""Transparent logging reverse proxy in front of the host's Ollama server.

Every harness under test is configured to call this proxy instead of Ollama
directly. The proxy forwards the request byte-for-byte to the real Ollama
(reached via host.docker.internal from inside Docker), streams the response
back untouched, and — for any request with "stream": true — injects
stream_options.include_usage so Ollama's OpenAI-compatible endpoint appends a
final usage chunk. That chunk is scraped and appended to a JSONL log, tagged
with the HARNESS/TASK_ID this proxy instance was started for.

This is the one place token accounting happens, so all three harnesses are
measured the same way regardless of what each one's own CLI chooses to print.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("UPSTREAM", "http://host.docker.internal:11434")
LOG_PATH = os.environ.get("LOG_PATH", "/logs/proxy.jsonl")
HARNESS = os.environ.get("HARNESS", "unknown")
TASK_ID = os.environ.get("TASK_ID", "unknown")


def _extract_usage(raw: bytes) -> dict | None:
    """Handle both wire protocols Ollama speaks: the OpenAI-compatible
    /v1/chat/completions shape (usage nested under "usage") and Ollama's own
    native /api/generate|/api/chat shape (eval_count/prompt_eval_count on the
    final {"done": true, ...} line). Different harnesses pick different ones
    via their own provider config (e.g. Aider's "ollama/" prefix uses the
    native API; OpenCode/dsh's custom-provider config uses OpenAI-compatible)
    — this proxy normalizes both so token accounting is comparable.
    """
    text = raw.decode("utf-8", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[len("data:") :].strip()
        if not line or line == "[DONE]" or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue

        usage = obj.get("usage")
        if usage:
            return {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "api": "openai-compat",
            }

        if obj.get("done") and ("eval_count" in obj or "prompt_eval_count" in obj):
            prompt = obj.get("prompt_eval_count")
            completion = obj.get("eval_count")
            total = None
            if prompt is not None or completion is not None:
                total = (prompt or 0) + (completion or 0)
            return {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
                "api": "ollama-native",
            }
    return None


def _log(entry: dict) -> None:
    entry = {"ts": time.time(), "harness": HARNESS, "task": TASK_ID, **entry}
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silence default stderr logging
        pass

    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""

        if body:
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            if isinstance(payload, dict) and payload.get("stream") and "stream_options" not in payload:
                payload["stream_options"] = {"include_usage": True}
                body = json.dumps(payload).encode()

        req = urllib.request.Request(UPSTREAM + self.path, data=body or None, method=method)
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length"):
                req.add_header(k, v)
        if body:
            req.add_header("Content-Length", str(len(body)))

        started = time.time()
        try:
            with urllib.request.urlopen(req) as resp:
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                        self.send_header(k, v)
                self.end_headers()
                collected = bytearray()
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    collected.extend(chunk)
            usage = _extract_usage(bytes(collected))
            _log({
                "path": self.path,
                "status": resp.status,
                "duration_s": round(time.time() - started, 3),
                "usage": usage,
            })
        except Exception as exc:  # noqa: BLE001 - log and surface upstream, don't crash the proxy
            _log({
                "path": self.path,
                "error": str(exc),
                "duration_s": round(time.time() - started, 3),
            })
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(exc).encode())

    def do_GET(self) -> None:
        self._proxy("GET")

    def do_POST(self) -> None:
        self._proxy("POST")


if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", 11434), Handler).serve_forever()
