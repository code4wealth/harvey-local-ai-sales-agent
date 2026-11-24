"""Constrain user-controlled local file references to repository data roots."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPANY_INFO_RELATIVE_ROOT = PurePosixPath("data/company_info")


def resolve_company_info_path(
    value: str, *, repository_root: str | Path | None = None
) -> Path:
    """Resolve a company-info path strictly inside the repository data directory.

    Inputs are repository-relative (for example
    ``data/company_info/relaycue.md``). Absolute paths, URLs, traversal
    components, and symlinks resolving outside the allowed directory are
    rejected. A not-yet-created file is allowed so products can be configured
    before their local document is written.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("company-info path must be a non-empty repository-relative path")

    raw_value = value.strip()
    normalized = raw_value.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(raw_value)
    if (
        "\x00" in raw_value
        or "://" in raw_value
        or Path(raw_value).is_absolute()
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in posix_path.parts
    ):
        raise ValueError("company-info path must be a safe path under data/company_info")

    try:
        root = Path(REPOSITORY_ROOT if repository_root is None else repository_root).resolve()
        allowed_root = (root / Path(*COMPANY_INFO_RELATIVE_ROOT.parts)).resolve()
        candidate = (root / Path(*posix_path.parts)).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError("company-info path could not be resolved safely") from exc
    if candidate == allowed_root:
        raise ValueError("company-info path must refer to a file inside data/company_info")
    if not candidate.is_relative_to(allowed_root):
        raise ValueError("company-info path must remain inside data/company_info")
    if candidate.exists() and not candidate.is_file():
        raise ValueError("company-info path must refer to a file")
    return candidate


def normalize_company_info_path(
    value: str, *, repository_root: str | Path | None = None
) -> str:
    """Return a validated repository-relative path, or an empty optional value."""
    if isinstance(value, str) and not value.strip():
        return ""
    root = Path(REPOSITORY_ROOT if repository_root is None else repository_root).resolve()
    candidate = resolve_company_info_path(value, repository_root=root)
    return candidate.relative_to(root).as_posix()
