"""Offline GPT-OSS ordinary-text token counts and explicit request budgeting."""
import base64
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import threading

import tiktoken

VOCAB_PATH = Path(__file__).resolve().parents[1] / "assets/tokenizer/o200k_base.tiktoken"
VOCAB_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
CHAT_FRAMING_ALLOWANCE = 128
_lock = threading.Lock()


class RequestBudgetExceeded(ValueError):
    pass


@lru_cache(maxsize=1)
def _load_encoding():
    raw = VOCAB_PATH.read_bytes()
    if sha256(raw).hexdigest() != VOCAB_SHA256:
        raise ValueError("Tokenizer vocabulary integrity check failed")
    ranks = {base64.b64decode(token): int(rank) for token, rank in
             (line.split() for line in raw.splitlines() if line)}
    # Upstream tiktoken 0.12.0 o200k pattern; o200k_harmony shares ordinary ranks.
    pattern = "|".join([
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"\p{N}{1,3}", r" ?[^\s\p{L}\p{N}]+[\r\n/]*", r"\s*[\r\n]+", r"\s+(?!\S)", r"\s+",
    ])
    return tiktoken.Encoding(name="asklaw_o200k_ordinary", pat_str=pattern, mergeable_ranks=ranks, special_tokens={})


def encoding():
    # functools' cache may initialize twice under concurrent first use; avoid
    # allocating multiple large encodings on the small API container.
    with _lock:
        return _load_encoding()


def text_tokens(text):
    return len(encoding().encode_ordinary(text))


def request_measurement(messages, completion_tokens=2048):
    count = sum(text_tokens(message["content"]) for message in messages)
    return {"input_text_tokens": count, "framing_allowance_tokens": CHAT_FRAMING_ALLOWANCE,
            "completion_reservation_tokens": completion_tokens,
            "request_budget_tokens": count + CHAT_FRAMING_ALLOWANCE + completion_tokens,
            "tokenizer": "o200k ordinary text; server framing is an allowance, not billed usage"}


def enforce_request_budget(messages, limit, completion_tokens=2048):
    measurement = request_measurement(messages, completion_tokens)
    if measurement["request_budget_tokens"] > limit:
        raise RequestBudgetExceeded("Research context exceeds the request token budget")
    return measurement
