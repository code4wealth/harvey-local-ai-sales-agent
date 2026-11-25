from __future__ import annotations

from app import db
from scripts import run_live


def test_live_evidence_metrics_capture_options_for_each_attempt(db_path):
    conn = db.connect()
    try:
        for index, (temperature, seed) in enumerate(((0.0, 42), (0.2, 43), (0.2, 44))):
            db.log_inference(
                conn,
                task="profile:9",
                model="mock-model",
                host="http://127.0.0.1:11434",
                eval_tokens=10 + index,
                seconds=0.5,
                temperature=temperature,
                seed=seed,
                repeat_penalty=1.0,
            )
    finally:
        conn.close()

    eval_count, model_seconds, attempt_options = run_live._metrics("profile:9")

    assert eval_count == 33
    assert model_seconds == 1.5
    assert attempt_options == [
        {"temperature": 0.0, "seed": 42, "repeat_penalty": 1.0},
        {"temperature": 0.2, "seed": 43, "repeat_penalty": 1.0},
        {"temperature": 0.2, "seed": 44, "repeat_penalty": 1.0},
    ]
