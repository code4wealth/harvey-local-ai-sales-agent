from __future__ import annotations

import json

from app.text_clean import clean_reply, had_reasoning

LONE = (
    'Hmm, the user wants me to reply with exactly "READY". Strictly following instructions.\n'
    '</think>\n\nREADY'
)
BLOCK = "<think>\nplanning...\n</think>\n\n{\"a\": 1}"


def test_lone_closing_tag():
    assert clean_reply(LONE) == "READY"
    assert had_reasoning(LONE)


def test_wellformed_block():
    assert clean_reply(BLOCK) == '{"a": 1}'
    assert had_reasoning(BLOCK)


def test_plain_answer_untouched():
    assert clean_reply("READY") == "READY"
    assert not had_reasoning("READY")


def test_unclosed_think_is_dropped():
    assert clean_reply("<think>cut off mid-thought") == ""
    assert had_reasoning("<think>cut off mid-thought")


def test_empty():
    assert clean_reply("") == ""
    assert clean_reply(None) == ""
    assert not had_reasoning(None)


def test_json_after_reasoning_parses():
    raw = 'Let me think {braces} here.\n</think>\n\n{"label": "interested", "confidence": 0.9}'
    assert json.loads(clean_reply(raw))["label"] == "interested"
