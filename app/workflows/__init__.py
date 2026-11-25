"""Local-only, product-scoped AI workflows."""

from . import draft, icp, pipeline, profile, problem_statement, replies, signals


def register_workflow_handlers() -> None:
    """Register product and prospect workflow tasks for the persistent queue worker."""
    profile.register_profile_handler()
    icp.register_icp_handler()
    signals.register_signals_handler()
    replies.register_reply_handler()
    draft.register_draft_handler()
    problem_statement.register_problem_statement_handler()
    pipeline.register_pipeline_handler()


__all__ = [
    "draft",
    "icp",
    "profile",
    "pipeline",
    "problem_statement",
    "replies",
    "signals",
    "register_workflow_handlers",
]
