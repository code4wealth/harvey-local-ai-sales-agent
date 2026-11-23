from __future__ import annotations

import json

import httpx
import pytest

from app import llm_client
from scripts import eval_signals


def _use_mock_transport(monkeypatch, handler) -> None:
    def factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(llm_client, "_client", factory)


def test_held_out_selection_has_all_requested_signal_and_trap_cases():
    annotations, rows = eval_signals._load_held_out_cases()
    assert set(annotations) == {f"P{number:03d}" for number in range(38, 50)}
    assert set(rows) == set(annotations)
    signal_types = {
        signal_type
        for annotation in annotations.values()
        for signal_type in annotation["expected_types"]
    }
    trap_types = {
        trap_type
        for annotation in annotations.values()
        for trap_type in annotation["trap_types"]
    }
    assert signal_types == {
        "funding", "hiring", "expansion", "tech_change", "leadership_change", "pain_mention"
    }
    assert trap_types == {"no_signal", "implied", "negated", "stale", "other_company"}


def test_only_selection_and_frozen_prompt_hash_are_strict(tmp_path, monkeypatch):
    assert eval_signals._parse_only("P012,P028") == {"P012", "P028"}
    with pytest.raises(ValueError, match="comma-separated"):
        eval_signals._parse_only("P12,not-an-id")

    frozen = tmp_path / "frozen.sha256"
    current_hash = eval_signals.signal_prompt_hash()
    frozen.write_text("0" * 64 + "\n", encoding="utf-8")
    monkeypatch.setattr(eval_signals, "FROZEN_PROMPT_PATH", frozen)
    with pytest.raises(ValueError, match="differs from the frozen"):
        eval_signals._check_frozen_prompt(current_hash)
    frozen.write_text(current_hash + "\n", encoding="utf-8")
    assert eval_signals._check_frozen_prompt(current_hash) == current_hash


def test_model_none_and_exercised_trap_diagnostics():
    none_payload = {
        "status": "succeeded",
        "signals": [],
        "drop_counts": {"type": 1, "quote": 0, "negated": 0, "stale": 0, "other_company": 0},
    }
    exercised_payload = {
        "status": "succeeded",
        "signals": [],
        "drop_counts": {"type": 0, "quote": 0, "negated": 1, "stale": 0, "other_company": 0},
    }
    assert eval_signals._model_none_count(none_payload) == 1
    assert eval_signals._trap_outcome(none_payload) == "none"
    assert eval_signals._trap_outcome(exercised_payload) == "exercised"
    assert eval_signals._trap_outcome({"status": "failed"}) == "unresolved"


def test_only_development_run_evaluates_exactly_the_requested_ids(db_path, monkeypatch, tmp_path):
    run_dir = tmp_path / "real_run"
    monkeypatch.setattr(eval_signals, "RUN_DIR", run_dir)
    frozen_path = tmp_path / "frozen.sha256"
    prompt_hash = eval_signals.signal_prompt_hash()
    frozen_path.write_text(prompt_hash + "\n", encoding="utf-8")
    monkeypatch.setattr(eval_signals, "FROZEN_PROMPT_PATH", frozen_path)
    replies = iter(
        [
            {
                "signals": [
                    {
                        "type": "expansion",
                        "evidence": "a second customer-support shift will begin next quarter",
                        "about_company": True,
                    }
                ]
            },
            {
                "signals": [
                    {
                        "type": "pain_mention",
                        "evidence": "the prior shift's handoff is missing",
                        "about_company": True,
                    }
                ]
            },
        ]
    )

    def handler(request):
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(next(replies))}, "prompt_eval_count": 90, "eval_count": 20},
        )

    _use_mock_transport(monkeypatch, handler)
    result = eval_signals.run_evaluation(
        model="qwen3:4b",
        db_path=str(tmp_path / "signals.sqlite3"),
        only="P012,P028",
        freeze_prompt=True,
        output_path="only.json",
    )

    assert result == 0
    report = json.loads((run_dir / "only.json").read_text(encoding="utf-8"))
    assert report["selected_ids"] == ["P012", "P028"]
    assert report["passed"] == report["total"] == 2


def test_mocked_held_out_run_saves_diagnostics_under_real_run_dir(db_path, monkeypatch, tmp_path):
    run_dir = tmp_path / "real_run"
    monkeypatch.setattr(eval_signals, "RUN_DIR", run_dir)
    frozen_path = tmp_path / "frozen.sha256"
    prompt_hash = eval_signals.signal_prompt_hash()
    frozen_path.write_text(prompt_hash + "\n", encoding="utf-8")
    monkeypatch.setattr(eval_signals, "FROZEN_PROMPT_PATH", frozen_path)
    evidence = "closed a $14 million Series B financing on October 5, 2026"
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        assert payload["think"] is False
        assert payload["options"]["num_ctx"] == 4096
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {"signals": [{"type": "funding", "evidence": evidence, "about_company": True}]}
                    )
                },
                "prompt_eval_count": 110,
                "eval_count": 25,
                "total_duration": 75_000_000,
            },
        )

    _use_mock_transport(monkeypatch, handler)
    result = eval_signals.run_evaluation(
        model="qwen3:4b",
        db_path=str(tmp_path / "signals.sqlite3"),
        held_out=True,
        only="P038",
        freeze_prompt=True,
        verbose=True,
        output_path="mocked-held-out.json",
    )

    assert result == 0
    assert len(seen) == 1
    report_path = run_dir / "mocked-held-out.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "held-out"
    assert report["model"] == "qwen3:4b"
    assert report["think"] is False
    assert report["num_ctx"] == 4096
    assert report["signal_prompt_sha256"] == prompt_hash
    assert report["frozen_signal_prompt_sha256"] == prompt_hash
    assert report["passed"] == report["total"] == 1
    assert report["results"]["P038"]["signals"][0]["type"] == "funding"
    assert report["results"]["P038"]["inference"][0]["prompt_tokens"] == 110
