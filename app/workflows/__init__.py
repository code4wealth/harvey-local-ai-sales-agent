"""Local-only, product-scoped AI workflows."""

from . import icp, profile, signals


def register_workflow_handlers() -> None:
    """Register product and prospect workflow tasks for the persistent queue worker."""
    profile.register_profile_handler()
    icp.register_icp_handler()
    signals.register_signals_handler()


__all__ = ["icp", "profile", "signals", "register_workflow_handlers"]
