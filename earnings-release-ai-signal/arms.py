"""The four arms. Each takes release text and returns {"label", "confidence", "raw", "tokens_in", "ms"}.

    rules      keyword baseline, word lists fixed BEFORE any outcome was looked at (see RULES below)
    always_up  control: always "bullish" (captures market drift)
    qwen3-14b  local Ollama, think off, schema-constrained label, temperature 0
    jev        TypeSafe Jev API (paid). The client enforces a hard dollar cap BEFORE every request.

The key is read from TYPESAFE_API_KEY only; it is never printed, logged or written to results.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = ["bullish", "neutral", "bearish"]
MAX_CHARS = 6_000  # about 1,500 tokens (chars / 4), identical for every arm. Was 12,000; halved on 2026-10-03 BEFORE any
#                    outcome data, because the local arm measured 30-35 s per 3,000-token prompt (about 4 h for 479 events).

INSTRUCTION = (
    "You are reading a company's quarterly earnings press release. Judge how an investor would likely "
    "react to this release in the next trading session. bullish: results or outlook are better than "
    "the market is likely expecting. bearish: results or outlook are worse than expected. neutral: "
    "in line, mixed, or no clear signal."
)
CRITERIA = {
    "bullish": "Results or guidance are clearly positive for the stock, e.g. strong growth, raised outlook, record results.",
    "neutral": "Results are in line, mixed, or give no clear signal.",
    "bearish": "Results or guidance are clearly negative for the stock, e.g. declines, missed targets, lowered or withdrawn outlook.",
}

# ---- rules baseline (fixed before any outcome data was examined) ------------------------------
POS = ["record", "exceeded", "strong", "growth", "beat", "outperform", "accelerat", "improved", "increase", "expand", "raised", "raises", "upgrade"]
NEG = ["decline", "decrease", "lowered", "lowers", "missed", "weak", "headwind", "impairment", "withdraw", "below", "reduced", "restructuring", "uncertain", "slowdown"]
GUIDE_UP = re.compile(r"(rais(?:e|es|ed|ing)|increas(?:e|es|ed|ing)) [^.]{0,40}(guidance|outlook)", re.I)
GUIDE_DOWN = re.compile(r"(lower(?:s|ed|ing)?|reduc(?:e|es|ed|ing)|cut(?:s|ting)?|withdr(?:aw|aws|ew|awing)) [^.]{0,40}(guidance|outlook)", re.I)
RULES_THRESHOLD = 3
RULES_VERSION = hashlib.sha256(json.dumps([POS, NEG, GUIDE_UP.pattern, GUIDE_DOWN.pattern, RULES_THRESHOLD]).encode()).hexdigest()[:12]


def truncate(text: str) -> str:
    return text[:MAX_CHARS]


def rules(text: str) -> dict:
    t0, low = time.time(), truncate(text).lower()
    score = sum(low.count(w) for w in POS) - sum(low.count(w) for w in NEG)
    score += 3 * len(GUIDE_UP.findall(low)) - 3 * len(GUIDE_DOWN.findall(low))
    label = "bullish" if score >= RULES_THRESHOLD else "bearish" if score <= -RULES_THRESHOLD else "neutral"
    return {"label": label, "confidence": min(1.0, abs(score) / 10), "score": score, "raw": {"score": score, "rules": RULES_VERSION},
            "tokens_in": 0, "ms": (time.time() - t0) * 1000}


def always_up(text: str) -> dict:
    return {"label": "bullish", "confidence": 1.0, "raw": {}, "tokens_in": 0, "ms": 0.0}


# ---- local model -----------------------------------------------------------------------------
def qwen(text: str, model: str = "qwen3:14b", host: str = "http://localhost:11434") -> dict:
    body = {"model": model, "stream": False, "think": False, "keep_alive": "20m",
            "options": {"temperature": 0, "num_predict": 24},
            "format": {"type": "object", "properties": {"label": {"type": "string", "enum": LABELS}}, "required": ["label"]},
            "messages": [{"role": "user", "content": INSTRUCTION + "\n\nPress release:\n" + truncate(text) +
                          '\n\nAnswer with JSON: {"label": "bullish" | "neutral" | "bearish"}'}]}
    t0 = time.time()
    req = urllib.request.Request(host + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    label = json.loads(d["message"]["content"])["label"]
    return {"label": label, "confidence": None, "raw": {"content": d["message"]["content"], "eval_count": d.get("eval_count")},
            "tokens_in": d.get("prompt_eval_count", 0), "ms": (time.time() - t0) * 1000}


# ---- Jev with a hard spend cap ----------------------------------------------------------------
JEV_URL = "https://api.typesafe.ai/v1/systemone"
USD_PER_MTOK_IN = 0.042  # vendor price, output free; verify against the console after the probe


class SpendCap(Exception):
    pass


class Spend:
    """Running estimate of Jev spend, persisted so a restart cannot reset it."""

    def __init__(self, path: str, cap_usd: float):
        self.path, self.cap = path, cap_usd
        self.tokens = json.load(open(path))["tokens"] if os.path.exists(path) else 0

    @property
    def usd(self) -> float:
        return self.tokens * USD_PER_MTOK_IN / 1e6

    def check(self, est_tokens: int) -> None:
        if (self.tokens + est_tokens) * USD_PER_MTOK_IN / 1e6 > self.cap:
            raise SpendCap(f"next call (~{est_tokens} tokens) would pass the ${self.cap:.2f} cap (spent ~${self.usd:.4f})")

    def add(self, tokens: int) -> None:
        self.tokens += tokens
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        json.dump({"tokens": self.tokens, "usd_est": round(self.usd, 6)}, open(self.path, "w"))


def est_tokens(text: str) -> int:
    # chars/3 is deliberately an over-estimate (English text is about 4 chars per token) so the pre-send cap check errs safe
    return math.ceil((len(INSTRUCTION) + len(json.dumps(CRITERIA)) + len(text)) / 3)


def jev(text: str, spend: Spend, transport=None) -> dict:
    """One Jev call. `transport(url, headers, body_bytes) -> dict` is injectable for tests."""
    state = truncate(text)
    spend.check(est_tokens(state))                                   # refuse BEFORE sending
    body = {"state": state, "model": "jev-latest",
            "questions": {"tone": {"type": "choice", "instructions": INSTRUCTION, "criteria": CRITERIA}}}
    key = os.environ.get("TYPESAFE_API_KEY")
    if transport is None and not key:
        raise RuntimeError("TYPESAFE_API_KEY is not set")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    t0 = time.time()
    if transport:
        d = transport(JEV_URL, headers, json.dumps(body).encode())
    else:
        req = urllib.request.Request(JEV_URL, json.dumps(body).encode(), headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:                          # never echo headers (they carry the key)
            raise RuntimeError(f"Jev HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None
    ms = (time.time() - t0) * 1000
    ans = d["answers"]["tone"]
    tokens = d.get("usage", {}).get("input_tokens") or est_tokens(state)
    spend.add(tokens)
    return {"label": ans["choice"], "confidence": ans.get("confidence"), "probabilities": ans.get("probabilities"),
            "raw": {k: v for k, v in d.items() if k != "key"}, "tokens_in": tokens, "ms": ms}
