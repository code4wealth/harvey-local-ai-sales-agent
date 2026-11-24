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


def test_model_empty_list_and_exercised_trap_diagnostics():
    empty_payload = {
        "status": "succeeded",
        "signals": [],
        "drop_counts": {key: 0 for key in eval_signals.DROP_KEYS},
    }
    exercised_payload = {
        "status": "succeeded",
        "signals": [],
        "drop_counts": {"quote": 0, "type": 0, "negated": 1, "stale": 0, "other_company": 0},
    }
    legacy_type_drop_payload = {
        "status": "succeeded",
        "signals": [],
        "drop_counts": {"quote": 0, "type": 1, "negated": 0, "stale": 0, "other_company": 0},
    }
    empty_diagnostics = {"parsed_signals": []}
    filtered_diagnostics = {
        "parsed_signals": [{"type": "expansion", "evidence": "not stored in report"}]
    }

    assert eval_signals._model_none_count(empty_payload, empty_diagnostics) == 1
    assert eval_signals._model_none_count(empty_payload, {}) == 0
    assert eval_signals._model_none_count(legacy_type_drop_payload, {}) == 0
    assert eval_signals._model_none_count(exercised_payload, filtered_diagnostics) == 0
    assert eval_signals._trap_outcome(empty_payload, empty_diagnostics) == "empty-list"
    assert eval_signals._trap_outcome(exercised_payload, filtered_diagnostics) == "exercised"
    assert eval_signals._trap_outcome({"status": "failed"}, {}) == "unresolved"


def test_freeze_prompt_is_standalone_and_refreeze_is_required_to_replace(tmp_path, monkeypatch):
    frozen = tmp_path / "frozen.sha256"
    monkeypatch.setattr(eval_signals, "FROZEN_PROMPT_PATH", frozen)

    def evaluation_must_not_start():
        raise AssertionError("standalone freeze must not load evaluation data")

    monkeypatch.setattr(eval_signals, "_load_expected_annotations", evaluation_must_not_start)
    monkeypatch.setattr(eval_signals, "_load_unique_prospect_rows", evaluation_must_not_start)
    monkeypatch.setattr(
        llm_client,
        "resolve_model_name",
        lambda _model: (_ for _ in ()).throw(AssertionError("freeze must not resolve a model")),
    )

    current_hash = eval_signals.signal_prompt_hash()
    assert eval_signals.main(["--freeze-prompt", "--model", "qwen3:4b"]) == 0
    assert frozen.read_text(encoding="utf-8") == current_hash + "\n"

    previous = "0" * 64 + "\n"
    frozen.write_text(previous, encoding="utf-8")
    assert eval_signals.main(["--freeze-prompt"]) == 2
    assert frozen.read_text(encoding="utf-8") == previous

    assert eval_signals.main(["--freeze-prompt", "--refreeze"]) == 0
    assert frozen.read_text(encoding="utf-8") == current_hash + "\n"


def test_missing_frozen_hash_refuses_held_out_before_loading_cases(tmp_path, monkeypatch):
    missing = tmp_path / "missing.sha256"
    monkeypatch.setattr(eval_signals, "FROZEN_PROMPT_PATH", missing)
    monkeypatch.setattr(
        eval_signals,
        "_load_held_out_cases",
        lambda: pytest.fail("held-out pages/labels should not load before the hash check"),
    )

    with pytest.raises(ValueError, match="hash is missing"):
        eval_signals.run_evaluation(
            model="qwen3:4b",
            db_path=str(tmp_path / "signals.sqlite3"),
            held_out=True,
        )
    assert not missing.exists()


def test_only_development_run_records_diagnostics_without_reading_or_writing_hash(
    db_path, monkeypatch, tmp_path, capsys
):
    run_dir = tmp_path / "real_run"
    monkeypatch.setattr(eval_signals, "RUN_DIR", run_dir)
    frozen_path = tmp_path / "frozen.sha256"
    frozen_path.write_text("deliberately not a hash\n", encoding="utf-8")
    monkeypatch.setattr(eval_signals, "FROZEN_PROMPT_PATH", frozen_path)
    replies = iter(
        [
            {
                "signals": [
                    {
                        "type": "expansion",
                        "evidence": "a second customer-support shift will begin next quarteX",
                        "about_company": True,
                    }
                ]
            },
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
            {
                "signals": [
                    {
                        "type": "expansion",
                        "evidence": "A board update from August 2026 says directors decided against adding a second shift after reviewing the proposal.",
                        "about_company": True,
                    }
                ]
            },
        ]
    )
    raw_responses = []

    def handler(request):
        content = json.dumps(next(replies))
        raw_responses.append(content)
        return httpx.Response(
            200,
            json={"message": {"content": content}, "prompt_eval_count": 90, "eval_count": 20},
        )

    _use_mock_transport(monkeypatch, handler)
    result = eval_signals.run_evaluation(
        model="qwen3:4b",
        db_path=str(tmp_path / "signals.sqlite3"),
        only="P012,P028,P030",
        verbose=True,
        output_path="only.json",
    )

    assert result == 0
    assert frozen_path.read_text(encoding="utf-8") == "deliberately not a hash\n"
    report = json.loads((run_dir / "only.json").read_text(encoding="utf-8"))
    assert report["selected_ids"] == ["P012", "P028", "P030"]
    assert report["counts"]["passed"] == report["counts"]["total"] == 3
    assert report["run_config"]["signal_prompt_sha256"] == eval_signals.signal_prompt_hash()
    assert report["run_config"]["temperature"] == 0.0
    assert report["run_config"]["seed"] == 42
    assert report["run_config"]["repeat_penalty"] == 1.0
    assert report["counts"]["quote_retries"] == 1
    assert report["results"]["P012"]["quote_retries"] == 1
    assert report["counts"]["signals_returned"] == 3
    assert report["counts"]["signals_returned_then_filtered"] == 1
    assert report["counts"]["aggregate_drop_counts"]["negated"] == 1
    assert report["results"]["P012"]["inference"][0]["temperature"] == 0.0
    assert report["results"]["P012"]["inference"][0]["seed"] == 42
    assert report["results"]["P012"]["inference"][0]["repeat_penalty"] == 1.0
    assert len(report["results"]["P012"]["inference"]) == 2
    assert report["results"]["P012"]["diagnostics"]["raw_replies"] == [
        raw_responses[0], raw_responses[1]
    ]
    assert report["results"]["P012"]["diagnostics"]["parsed_signals"][0]["type"] == "expansion"
    assert report["results"]["P030"]["diagnostics"]["drop_details"][0]["reason"] == "negated"
    stdout = capsys.readouterr().out
    assert "Run config: mode=development model=qwen3:4b think=false temperature=0 seed=42 repeat_penalty=1" in stdout
    assert "Quote verification retries: 1" in stdout
    assert "removed_lines=" in stdout
    assert "cleaned_text=" in stdout
    assert "raw_replies=" in stdout
    assert "parsed_signals=" in stdout
    assert "drops=" in stdout


def test_mocked_empty_list_is_counted_as_model_none(db_path, monkeypatch, tmp_path):
    run_dir = tmp_path / "real_run"
    monkeypatch.setattr(eval_signals, "RUN_DIR", run_dir)
    frozen_path = tmp_path / "frozen.sha256"
    frozen_path.write_text("not-read-by-development\n", encoding="utf-8")
    monkeypatch.setattr(eval_signals, "FROZEN_PROMPT_PATH", frozen_path)

    def handler(_request):
        return httpx.Response(200, json={"message": {"content": '{"signals":[]}'}})

    _use_mock_transport(monkeypatch, handler)
    result = eval_signals.run_evaluation(
        model="qwen3:4b",
        db_path=str(tmp_path / "empty-signals.sqlite3"),
        only="P003",
        output_path="empty-list.json",
    )

    assert result == 0
    assert frozen_path.read_text(encoding="utf-8") == "not-read-by-development\n"
    report = json.loads((run_dir / "empty-list.json").read_text(encoding="utf-8"))
    assert report["counts"]["model_none_runs"] == 1
    assert report["counts"]["signals_returned"] == 0
    assert report["counts"]["signals_returned_then_filtered"] == 0
    assert report["trap_outcomes"]["no-signal/implied"]["empty-list"] == 1
    assert report["results"]["P003"]["diagnostics"]["parsed_signals"] == []


def test_mocked_held_out_run_redacts_text_from_stdout_and_report(db_path, monkeypatch, tmp_path, capsys):
    run_dir = tmp_path / "real_run"
    monkeypatch.setattr(eval_signals, "RUN_DIR", run_dir)
    frozen_path = tmp_path / "frozen.sha256"
    prompt_hash = eval_signals.signal_prompt_hash()
    frozen_path.write_text(prompt_hash + "\n", encoding="utf-8")
    monkeypatch.setattr(eval_signals, "FROZEN_PROMPT_PATH", frozen_path)
    evidence = "closed a $14 million Series B financing on October 5, 2026"
    raw_reply = json.dumps(
        {"signals": [{"type": "funding", "evidence": evidence, "about_company": True}]}
    )

    def handler(request):
        payload = json.loads(request.content)
        assert payload["think"] is False
        assert payload["options"] == {
            "temperature": 0.0,
            "seed": 42,
            "repeat_penalty": 1.0,
            "num_ctx": 4096,
        }
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={
                "message": {"content": raw_reply},
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
        verbose=True,
        output_path="mocked-held-out.json",
    )

    assert result == 0
    report_path = run_dir / "mocked-held-out.json"
    report_text = report_path.read_text(encoding="utf-8")
    report = json.loads(report_text)
    heldout_annotations, heldout_rows = eval_signals._load_held_out_cases()
    page_text = (eval_signals.ROOT / heldout_rows["P038"]["page_text_path"]).read_text(encoding="utf-8")
    assert report["mode"] == "held-out"
    assert report["run_config"]["model"] == "qwen3:4b"
    assert report["run_config"]["think"] is False
    assert report["run_config"]["temperature"] == 0.0
    assert report["run_config"]["seed"] == 42
    assert report["run_config"]["repeat_penalty"] == 1.0
    assert report["run_config"]["num_ctx"] == 4096
    assert report["run_config"]["signal_prompt_sha256"] == prompt_hash
    assert report["run_config"]["frozen_signal_prompt_sha256"] == prompt_hash
    assert frozen_path.read_text(encoding="utf-8") == prompt_hash + "\n"
    assert report["counts"]["passed"] == report["counts"]["total"] == 1
    assert report["results"]["P038"]["kept_signal_count"] == 1
    assert report["results"]["P038"]["inference_attempt_count"] == 1
    assert heldout_annotations["P038"]["expected_types"] == ("funding",)
    stdout = capsys.readouterr().out
    assert "Run config: mode=held-out model=qwen3:4b think=false temperature=0 seed=42" in stdout
    for secret in (raw_reply, evidence, page_text):
        assert secret not in report_text
        assert secret not in stdout
    assert "parsed_signals" not in report["results"]["P038"]


def test_development_report_counts_only_parsed_empty_lists():
    parsed_empty = {
        "status": "succeeded",
        "signals": [],
        "drop_counts": {key: 0 for key in eval_signals.DROP_KEYS},
    }
    filtered_candidate = {
        "status": "succeeded",
        "signals": [],
        "drop_counts": {"quote": 0, "type": 0, "other_company": 0, "negated": 1, "stale": 0},
    }
    assert eval_signals._model_none_count(parsed_empty, {"parsed_signals": []}) == 1
    assert eval_signals._model_none_count(filtered_candidate, {"parsed_signals": [{"type": "expansion"}]}) == 0
