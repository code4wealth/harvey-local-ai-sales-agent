from __future__ import annotations

import asyncio

import httpx

from app import db, llm_client, prospects
from app.main import app
from app.queue_worker import QueueWorker
from app.workflows import common, pipeline
from app.workflows import draft as draft_workflow
from app.workflows import icp as icp_workflow
from app.workflows import problem_statement as problem_workflow
from app.workflows import profile as profile_workflow
from app.workflows import ranking as ranking_workflow
from app.workflows import signals as signal_workflow
import app.queue_worker as queue_worker


PROFILE_RESULT = {
    "summary": "A local service team coordinates customer handoffs.",
    "value_proposition": "Keeps customer handoffs organized.",
    "key_features": ["handoff tracking"],
    "pain_points_solved": ["missed customer handoffs"],
    "differentiators": ["not stated"],
    "typical_buyer": "support operations director",
    "typical_team_size": "not stated",
    "working_situation": "Support teams coordinate customer handoffs.",
    "not_for": ["not stated"],
}
ICP_RESULT = {
    "industries": ["customer support"],
    "company_size": {"min": None, "max": None},
    "buyer_titles": ["support operations director"],
    "pain_points": ["missed customer handoffs"],
    "trigger_events": ["not stated"],
    "disqualifiers": ["not stated"],
}
SIGNAL = {
    "type": "hiring",
    "evidence": "The company hired five support specialists this month.",
    "confidence": 0.8,
    "about_company": True,
}


def _create_product(*, prospects: int = 1) -> tuple[int, list[int]]:
    conn = db.connect()
    try:
        product_id = db.create_product(conn, name="Pipeline product")
        prospect_ids = [
            db.create_prospect(
                conn,
                product_id=product_id,
                company_name=f"Prospect {index}",
                contact_title="Support Operations Director",
            )
            for index in range(1, prospects + 1)
        ]
        conn.commit()
        return product_id, prospect_ids
    finally:
        conn.close()


def _request(method: str, path: str) -> httpx.Response:
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            return await client.request(method, path)

    return asyncio.run(send())


def _complete_workflow(product_id: int, run_id: int, workflow: str, result: dict) -> None:
    common.complete_run(
        run_id=run_id,
        product_id=product_id,
        workflow=workflow,
        result=result,
        model_name="mock-local-model",
        prompt_hash="test-prompt-hash",
        commit_hash="test-commit-hash",
        temperature=0.0,
        seed=42,
        repeat_penalty=1.0,
    )


def _patch_successful_steps(monkeypatch, *, signals: list[dict] | None = None) -> None:
    def profile_run(product_id: int, run_id: int, model_name: str):
        _complete_workflow(product_id, run_id, "profile", PROFILE_RESULT)

    def icp_run(product_id: int, run_id: int, model_name: str):
        _complete_workflow(product_id, run_id, "icp", ICP_RESULT)

    def signal_run(prospect_id: int, run_id: int, model_name: str):
        conn = db.connect()
        try:
            row = db.get_signal_run(conn, run_id)
            db.save_signal_run(
                conn,
                run_id=run_id,
                prospect_id=prospect_id,
                product_id=int(row["product_id"]),
                signals=list(signals if signals is not None else [SIGNAL]),
                drop_counts={},
                removed_content={},
                model_name=model_name,
                prompt_hash="test-signal-prompt",
                commit_hash="test-commit-hash",
            )
        finally:
            conn.close()

    def problem_run(run_id: int, model_name: str):
        conn = db.connect()
        try:
            db.update_problem_statement_run(
                conn,
                run_id,
                status="succeeded",
                statement="The company hired five support specialists this month.",
                evidence=["company hired five support specialists this month"],
                model_name=model_name,
                prompt_hash="test-problem-prompt",
                commit_hash="test-commit-hash",
            )
        finally:
            conn.close()

    def draft_run(run_id: int, model_name: str):
        conn = db.connect()
        try:
            db.save_draft_output(
                conn,
                run_id,
                subject="A brief note",
                body='"company hired five support specialists this month"',
                evidence_used=["company hired five support specialists this month"],
                model_name=model_name,
                prompt_hash="test-draft-prompt",
                commit_hash="test-commit-hash",
            )
        finally:
            conn.close()

    def rank_product(product_id: int):
        return {
            "product_id": product_id,
            "icp_status": "available",
            "prospect_count": 1,
            "prospects": [{"prospect_id": 1, "score": 81.0}],
        }

    monkeypatch.setattr(profile_workflow, "execute_profile_run", profile_run)
    monkeypatch.setattr(icp_workflow, "execute_icp_run", icp_run)
    monkeypatch.setattr(signal_workflow, "execute_signal_run", signal_run)
    monkeypatch.setattr(problem_workflow, "execute_problem_statement_run", problem_run)
    monkeypatch.setattr(draft_workflow, "execute_draft_run", draft_run)
    monkeypatch.setattr(ranking_workflow, "rank_product", rank_product)


def _run_worker_once(monkeypatch) -> int:
    pipeline.register_pipeline_handler()
    monkeypatch.setattr(queue_worker, "ollama_up", lambda: True)
    return QueueWorker().run_once()


def _fetch_task_and_run(db_path, run_id: int):
    conn = db.connect()
    try:
        task = conn.execute(
            "SELECT * FROM task_queue WHERE task_type = ? ORDER BY id DESC LIMIT 1",
            (pipeline.TASK_TYPE,),
        ).fetchone()
        run = db.get_pipeline_run(conn, run_id)
        return dict(task), dict(run)
    finally:
        conn.close()


def test_pipeline_api_queues_ordered_product_steps_and_deduplicates_active_run(
    db_path, monkeypatch
):
    monkeypatch.setenv("DEFAULT_MODEL", "pipeline-test-model")
    monkeypatch.setattr(app.state, "queue_worker", None, raising=False)
    product_id, prospect_ids = _create_product(prospects=2)

    response = _request("POST", f"/api/products/{product_id}/pipeline")
    assert response.status_code == 202
    payload = response.json()
    assert payload["pipeline"] is True
    assert payload["status"] == "queued"
    assert payload["model_name"] == "pipeline-test-model"
    assert [step["step_name"] for step in payload["steps"]] == [
        "profile",
        "icp",
        f"signals:{prospect_ids[0]}",
        f"problem_statement:{prospect_ids[0]}",
        f"draft:{prospect_ids[0]}",
        f"signals:{prospect_ids[1]}",
        f"problem_statement:{prospect_ids[1]}",
        f"draft:{prospect_ids[1]}",
        "ranking",
    ]
    assert payload["steps"][2]["label"] == "Signals and research · Prospect 1"

    duplicate = _request("POST", f"/api/products/{product_id}/pipeline")
    assert duplicate.status_code == 202
    assert duplicate.json()["id"] == payload["id"]
    latest = _request("GET", f"/api/products/{product_id}/pipeline")
    by_id = _request("GET", f"/api/pipeline-runs/{payload['id']}")
    assert latest.json() == by_id.json() == payload
    assert latest.json()["step_counts"]["queued"] == 9

    conn = db.connect()
    try:
        tasks = conn.execute(
            "SELECT COUNT(*) FROM task_queue WHERE task_type = ?", (pipeline.TASK_TYPE,)
        ).fetchone()[0]
        assert tasks == 1
    finally:
        conn.close()


def test_full_pipeline_runs_profile_icp_signals_problem_draft_and_ranking(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "pipeline-test-model")
    monkeypatch.setattr(app.state, "queue_worker", None, raising=False)
    page_dir = tmp_path / "pages"
    monkeypatch.setattr(prospects, "DEFAULT_PAGE_DIR", page_dir)
    product_id, prospect_ids = _create_product()
    conn = db.connect()
    try:
        prospects.store_prospect_page(
            conn,
            prospect_id=prospect_ids[0],
            text=SIGNAL["evidence"],
            page_dir=page_dir,
        )
    finally:
        conn.close()
    _patch_successful_steps(monkeypatch)

    queued = _request("POST", f"/api/products/{product_id}/pipeline").json()
    assert _run_worker_once(monkeypatch) == 1

    finished = _request("GET", f"/api/pipeline-runs/{queued['id']}").json()
    assert finished["status"] == "done"
    assert finished["step_counts"] == {
        "queued": 0,
        "running": 0,
        "done": 6,
        "failed": 0,
        "skipped": 0,
    }
    assert [step["status"] for step in finished["steps"]] == ["done"] * 6
    assert finished["steps"][2]["result"]["signal_count"] == 1
    assert finished["steps"][3]["result"]["status"] == "succeeded"
    assert finished["steps"][4]["result"]["status"] == "succeeded"
    assert finished["steps"][5]["result"]["scored_count"] == 1
    assert _request("GET", f"/api/products/{product_id}/pipeline").json() == finished

    conn = db.connect()
    try:
        assert db.latest_business_profile(conn, product_id) is not None
        assert db.latest_icp(conn, product_id) is not None
        assert db.latest_signal_run(conn, prospect_ids[0])["status"] == "succeeded"
        assert db.latest_problem_statement_run(
            conn, product_id=product_id, prospect_id=prospect_ids[0]
        )["status"] == "succeeded"
        assert db.latest_draft_run(
            conn, product_id=product_id, prospect_id=prospect_ids[0]
        )["status"] == "succeeded"
        task = conn.execute(
            "SELECT status FROM task_queue WHERE task_type = ?", (pipeline.TASK_TYPE,)
        ).fetchone()
        assert task["status"] == "done"
    finally:
        conn.close()


def test_pipeline_skips_problem_and_draft_when_no_verified_signals(
    db_path, monkeypatch
):
    monkeypatch.setenv("DEFAULT_MODEL", "pipeline-test-model")
    monkeypatch.setattr(app.state, "queue_worker", None, raising=False)
    product_id, prospect_ids = _create_product()
    _patch_successful_steps(monkeypatch, signals=[])

    queued = _request("POST", f"/api/products/{product_id}/pipeline").json()
    assert _run_worker_once(monkeypatch) == 1
    finished = pipeline.read_pipeline_run_payload(queued["id"])

    assert finished["status"] == "done"
    assert finished["step_counts"]["done"] == 4
    assert finished["step_counts"]["skipped"] == 2
    assert finished["steps"][2]["result"]["signal_count"] == 0
    assert finished["steps"][3]["status"] == "skipped"
    assert finished["steps"][3]["error"] == "no verified evidence"
    assert finished["steps"][4]["status"] == "skipped"
    assert finished["steps"][4]["error"] == "no verified evidence"
    conn = db.connect()
    try:
        assert db.latest_problem_statement_run(
            conn, product_id=product_id, prospect_id=prospect_ids[0]
        )["status"] == "skipped"
        assert db.latest_draft_run(
            conn, product_id=product_id, prospect_id=prospect_ids[0]
        )["status"] == "skipped"
    finally:
        conn.close()


def test_pipeline_pauses_on_ollama_unavailable_and_resumes_same_run(
    db_path, monkeypatch
):
    monkeypatch.setenv("DEFAULT_MODEL", "pipeline-test-model")
    monkeypatch.setattr(app.state, "queue_worker", None, raising=False)
    product_id, _ = _create_product(prospects=0)
    queued = _request("POST", f"/api/products/{product_id}/pipeline").json()
    calls = 0

    def unavailable_then_succeed(product_id: int, run_id: int, model_name: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise llm_client.OllamaUnavailable("local Ollama stopped")
        _complete_workflow(product_id, run_id, "profile", PROFILE_RESULT)

    def icp_success(product_id: int, run_id: int, model_name: str):
        _complete_workflow(product_id, run_id, "icp", ICP_RESULT)

    monkeypatch.setattr(profile_workflow, "execute_profile_run", unavailable_then_succeed)
    monkeypatch.setattr(icp_workflow, "execute_icp_run", icp_success)
    monkeypatch.setattr(
        ranking_workflow,
        "rank_product",
        lambda product_id: {"product_id": product_id, "icp_status": "available", "prospect_count": 0, "prospects": []},
    )

    assert _run_worker_once(monkeypatch) == 1
    run = _request("GET", f"/api/pipeline-runs/{queued['id']}").json()
    assert run["status"] == "queued"
    assert run["steps"][0]["status"] == "queued"
    assert "OllamaUnavailable" in run["steps"][0]["error"]
    task, _ = _fetch_task_and_run(db_path, queued["id"])
    assert task["status"] == "queued"
    assert task["attempts"] == 0

    assert _run_worker_once(monkeypatch) == 1
    finished = _request("GET", f"/api/pipeline-runs/{queued['id']}").json()
    assert finished["status"] == "done"
    assert [step["status"] for step in finished["steps"]] == ["done", "done", "done"]
    assert calls == 2
    task, _ = _fetch_task_and_run(db_path, queued["id"])
    assert task["status"] == "done"


def test_pipeline_marks_failed_step_and_skips_dependent_product_work(
    db_path, monkeypatch
):
    monkeypatch.setenv("DEFAULT_MODEL", "pipeline-test-model")
    monkeypatch.setattr(app.state, "queue_worker", None, raising=False)
    product_id, _ = _create_product(prospects=0)
    queued = _request("POST", f"/api/products/{product_id}/pipeline").json()

    def invalid_profile(product_id: int, run_id: int, model_name: str):
        raise ValueError("company-info document is missing")

    monkeypatch.setattr(profile_workflow, "execute_profile_run", invalid_profile)
    monkeypatch.setattr(
        ranking_workflow,
        "rank_product",
        lambda product_id: {"product_id": product_id, "icp_status": "missing", "prospect_count": 0, "prospects": []},
    )

    assert _run_worker_once(monkeypatch) == 1
    finished = _request("GET", f"/api/pipeline-runs/{queued['id']}").json()
    assert finished["status"] == "failed"
    assert finished["steps"][0]["status"] == "failed"
    assert finished["steps"][1]["status"] == "skipped"
    assert "business profile" in finished["steps"][1]["error"].lower()
    assert finished["steps"][2]["status"] == "done"
    assert finished["steps"][0]["error"].startswith("ValueError:")


def test_pipeline_routes_return_404_for_missing_product_and_run(db_path):
    assert _request("POST", "/api/products/999/pipeline").status_code == 404
    assert _request("GET", "/api/products/999/pipeline").status_code == 404
    assert _request("GET", "/api/pipeline-runs/999").status_code == 404
    product_id, _ = _create_product(prospects=0)
    assert _request("GET", f"/api/products/{product_id}/pipeline").status_code == 404
