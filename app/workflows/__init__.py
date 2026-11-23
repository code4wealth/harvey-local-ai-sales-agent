"""Local-only, product-scoped AI workflows."""

from . import icp, profile


def register_workflow_handlers() -> None:
    """Register the profile and ICP tasks for the persistent queue worker."""
    profile.register_profile_handler()
    icp.register_icp_handler()


__all__ = ["icp", "profile", "register_workflow_handlers"]
