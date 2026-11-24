"""Persistence and error helpers shared by product-specific workflows."""

from __future__ import annotations

import json
from typing import Any

from app import db


class ProductNotFound(LookupError):
    """A requested workflow product does not exist."""


class WorkflowInputError(ValueError):
    """The required product-scoped source is missing or invalid."""


class WorkflowRunError(RuntimeError):
    """A workflow failed after a run row was created."""

    def __init__(self, run_id: int, message: str):
        super().__init__(message)
        self.run_id = int(run_id)
        self.error = str(message)


def create_run(
    product_id: int,
    workflow: str,
    model_name: str | None,
    *,
    temperature: float = 0.0,
    seed: int = 42,
) -> int:
    conn = db.connect()
    try:
        if db.get_product(conn, product_id) is None:
            raise ProductNotFound(f"product {product_id} not found")
        return db.create_workflow_run(
            conn,
            product_id=product_id,
            workflow=workflow,
            model_name=model_name,
            temperature=temperature,
            seed=seed,
        )
    finally:
        conn.close()


def update_run(
    run_id: int,
    *,
    status: str,
    error: str | None = None,
    model_name: str | None = None,
    queue_task_id: int | None = None,
) -> None:
    conn = db.connect()
    try:
        db.update_workflow_run(
            conn,
            run_id,
            status=status,
            error=error,
            model_name=model_name,
            queue_task_id=queue_task_id,
        )
    finally:
        conn.close()


def complete_run(
    *,
    run_id: int,
    product_id: int,
    workflow: str,
    result: dict[str, Any],
    model_name: str,
) -> None:
    conn = db.connect()
    try:
        db.save_workflow_output(
            conn,
            run_id=run_id,
            product_id=product_id,
            workflow=workflow,
            result=result,
            model_name=model_name,
        )
    finally:
        conn.close()


def queue_run(
    *,
    run_id: int,
    product_id: int,
    workflow: str,
    task_type: str,
    model_name: str,
    error: str,
) -> int:
    conn = db.connect()
    try:
        row = db.get_workflow_run(conn, run_id)
        if row is None or int(row["product_id"]) != int(product_id) or row["workflow"] != workflow:
            raise ValueError("workflow run does not match the queue task's product and workflow")
        task_id = db.enqueue_task(
            conn,
            task_type,
            {
                "product_id": int(product_id),
                "workflow_run_id": int(run_id),
                "model_name": model_name,
            },
        )
        db.update_workflow_run(
            conn,
            run_id,
            status="queued",
            error=error,
            model_name=model_name,
            queue_task_id=task_id,
        )
        return task_id
    finally:
        conn.close()


def set_run_failure(run_id: int, error: str, model_name: str | None) -> None:
    update_run(run_id, status="failed", error=error, model_name=model_name)


def workflow_run_payload(row) -> dict[str, Any]:
    if row is None:
        raise ValueError("workflow run not found")
    raw_result = row["result_json"]
    result = json.loads(raw_result) if raw_result is not None else None
    return {
        "id": int(row["id"]),
        "product_id": int(row["product_id"]),
        "workflow": row["workflow"],
        "status": row["status"],
        "result": result,
        "error": row["error"],
        "model_name": row["model_name"],
        "temperature": row["temperature"],
        "seed": row["seed"],
        "queue_task_id": row["queue_task_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def read_run_payload(run_id: int) -> dict[str, Any]:
    conn = db.connect()
    try:
        row = db.get_workflow_run(conn, run_id)
        if row is None:
            raise ValueError(f"workflow run {run_id} not found")
        return workflow_run_payload(row)
    finally:
        conn.close()
