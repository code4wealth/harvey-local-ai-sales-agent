"""Remove Qwen-style reasoning text before application code consumes a reply.

Qwen3 responses may include a complete ``<think>...</think>`` block or plain
reasoning that ends with a lone ``</think>``. In either case, only the answer
following the closing marker is returned. If the opening marker is unclosed,
the remainder is discarded rather than risking reasoning being treated as an
answer.
"""

from __future__ import annotations

import re

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_OPEN_THINK = re.compile(r"<think>", re.IGNORECASE)
_CLOSE_THINK = re.compile(r"</think>", re.IGNORECASE)


def clean_reply(text: str | None) -> str:
    """Return only answer text, discarding complete or malformed think blocks."""
    if not text:
        return ""

    # In some builds the model emits the reasoning without an opening tag.
    close_match = None
    for match in _CLOSE_THINK.finditer(text):
        close_match = match
    if close_match is not None:
        text = text[close_match.end() :]

    # Remove any complete blocks that remain, then drop an unclosed block.
    text = _THINK_BLOCK.sub("", text)
    open_match = _OPEN_THINK.search(text)
    if open_match is not None:
        text = text[: open_match.start()]
    return text.strip()


def had_reasoning(raw: str | None) -> bool:
    """Report whether the raw output contained a visible think marker."""
    if not raw:
        return False
    return _OPEN_THINK.search(raw) is not None or _CLOSE_THINK.search(raw) is not None
