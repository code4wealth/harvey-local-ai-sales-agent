from __future__ import annotations

import json

import httpx
import pytest

from app import db, llm_client
from scripts import eval_replies


def _use_mock_transport(monkeypatch, handler) -> None:
    def factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(llm_client, "_client", factory)


def _response(label: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "message": {
                "content": json.dumps(
                    {
                        "label": label,
                        "confidence": 0.91,
                        "rationale": "A concise synthetic evaluation rationale.",
                    }
                )
            },
            "prompt_eval_count": 100,
            "eval_count": 18,
        },
    )


def test_development_evaluation_defaults_to_36_and_saves_redacted_metrics(
    db_path, monkeypatch, tmp_path
):
    run_dir = tmp_path / "real_run"
    monkeypatch.setattr(eval_replies, "RUN_DIR", run_dir)
    monkeypatch.setattr(
        eval_replies,
        "FROZEN_PROMPT_PATH",
        tmp_path / "frozen_reply_prompt.sha256",
    )
    monkeypatch.setenv("DEFAULT_MODEL", "mock-reply-evaluator")
    label_rows = [
        row
        for row in eval_replies.load_reply_labels(print_summary=False)
        if row["split"] == "development"
    ]
    expected = {row["reply_id"]: row["ground_truth_label"] for row in label_rows}
    text_by_id = {
        row["reply_id"]: row["text"]
        for row in eval_replies.import_replies.load_reply_rows(eval_replies.REPLIES_PATH)
    }
    calls = 0
    prompts = []

    def handler(request):
        nonlocal calls
        request_payload = json.loads(request.content)
        prompt = request_payload["messages"][-1]["content"]
        reply_id = label_rows[calls]["reply_id"]
        calls += 1
        prompts.append(prompt)
        assert text_by_id[reply_id] in prompt
        assert reply_id not in prompt
        assert "ground_truth_label" not in prompt
        assert "difficulty" not in prompt
        assert "held_out" not in prompt
        # One intentionally incorrect development prediction exercises the metrics.
        predicted = "other" if reply_id == "R001" else expected[reply_id]
        return _response(predicted)

    _use_mock_transport(monkeypatch, handler)
    output_path = run_dir / "mocked-development.json"
    result = eval_replies.run_evaluation(
        model=None,
        db_path=str(db_path),
        output_path=str(output_path),
    )

    assert result == 1
    assert calls == 36
    assert len(prompts) == 36
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["mode"] == "development"
    assert report["selected_count"] == 36
    assert report["run_config"]["model"] == "mock-reply-evaluator"
    assert report["run_config"]["temperature"] == 0.0
    assert report["run_config"]["seed"] == 42
    assert report["run_config"]["repeat_penalty"] == 1.0
    assert report["run_config"]["retry_temperature"] == 0.2
    assert report["run_config"]["reply_prompt_sha256"] == eval_replies.reply_prompt_hash()
    assert report["run_config"]["frozen_reply_prompt_sha256"] is None
    assert report["overall_accuracy"] == {
        "correct": 35,
        "total": 36,
        "accuracy": pytest.approx(35 / 36),
    }
    assert report["misclassified_ids"] == ["R001"]
    assert report["unresolved_count"] == 0
    assert report["per_label_accuracy"]["interested"] == {
        "correct": 4,
        "total": 5,
        "accuracy": pytest.approx(0.8),
    }
    assert report["per_difficulty_accuracy"]["clear"] == {
        "correct": 25,
        "total": 26,
        "accuracy": pytest.approx(25 / 26),
    }
    assert report["per_difficulty_accuracy"]["ambiguous"] == {
        "correct": 10,
        "total": 10,
        "accuracy": 1.0,
    }
    matrix = report["confusion_matrix"]
    assert matrix["counts"]["interested"]["other"] == 1
    assert matrix["counts"]["interested"]["interested"] == 4
    assert not any(key in report for key in ("predictions", "reply_text", "rationale", "error"))
    serialized = output_path.read_text(encoding="utf-8")
    assert all(text not in serialized for text in text_by_id.values())
    assert "A concise synthetic evaluation rationale." not in serialized

    conn = db.connect(str(db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM sample_replies").fetchone()[0] == 36
        reply_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(sample_replies)")
        }
        assert "ground_truth_label" not in reply_columns
        assert "difficulty" not in reply_columns
        assert conn.execute("SELECT COUNT(*) FROM reply_classifications").fetchone()[0] == 36
    finally:
        conn.close()


def test_frozen_prompt_is_standalone_and_requires_explicit_refreeze(
    monkeypatch, tmp_path
):
    frozen = tmp_path / "frozen.sha256"
    monkeypatch.setattr(eval_replies, "FROZEN_PROMPT_PATH", frozen)
    monkeypatch.setattr(
        eval_replies,
        "_selected_rows",
        lambda **_kwargs: pytest.fail("freezing must not load reply labels or texts"),
    )
    monkeypatch.setattr(
        llm_client,
        "resolve_model_name",
        lambda *_args: pytest.fail("freezing must not resolve a model"),
    )

    current_hash = eval_replies.reply_prompt_hash()
    assert eval_replies.main(["--freeze-prompt"]) == 0
    assert frozen.read_text(encoding="utf-8") == current_hash + "\n"

    prior = "0" * 64 + "\n"
    frozen.write_text(prior, encoding="utf-8")
    assert eval_replies.main(["--freeze-prompt"]) == 2
    assert frozen.read_text(encoding="utf-8") == prior
    assert eval_replies.main(["--freeze-prompt", "--refreeze"]) == 0
    assert frozen.read_text(encoding="utf-8") == current_hash + "\n"


def test_held_out_evaluation_refuses_missing_or_changed_prompt_before_loading_data(
    monkeypatch, tmp_path
):
    frozen = tmp_path / "frozen.sha256"
    monkeypatch.setattr(eval_replies, "FROZEN_PROMPT_PATH", frozen)
    monkeypatch.setattr(
        eval_replies,
        "_selected_rows",
        lambda **_kwargs: pytest.fail("held-out data must not load before hash verification"),
    )
    current_hash = eval_replies.reply_prompt_hash()
    with pytest.raises(ValueError, match="hash is missing"):
        eval_replies.run_evaluation(
            model="mock-model",
            db_path=str(tmp_path / "eval.db"),
            held_out=True,
        )
    frozen.write_text("0" * 64 + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from the frozen"):
        eval_replies.run_evaluation(
            model="mock-model",
            db_path=str(tmp_path / "eval.db"),
            held_out=True,
        )
    frozen.write_text(current_hash + "\n", encoding="utf-8")
    assert eval_replies._check_frozen_prompt(current_hash) == current_hash


def test_reply_evaluation_only_parser_is_split_checked():
    assert eval_replies._parse_only("R003,R021") == {"R003", "R021"}
    with pytest.raises(ValueError, match="comma-separated"):
        eval_replies._parse_only("R3,not-an-id")
    held_out_id = next(
        row["reply_id"]
        for row in eval_replies.load_reply_labels(print_summary=False)
        if row["split"] == "held_out"
    )
    with pytest.raises(ValueError, match="not in the development set"):
        eval_replies._selected_rows(held_out=False, only=held_out_id)
