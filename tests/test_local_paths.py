from __future__ import annotations

from pathlib import Path

import pytest

from app import db, local_paths
from app.local_paths import normalize_company_info_path, resolve_company_info_path
from app.workflows import common, profile


def test_company_info_path_is_normalized_and_repository_anchored(tmp_path):
    allowed = tmp_path / "data" / "company_info"
    allowed.mkdir(parents=True)
    source = allowed / "relaycue.md"
    source.write_text("Local product notes", encoding="utf-8")

    assert normalize_company_info_path(
        r"data\company_info\relaycue.md", repository_root=tmp_path
    ) == "data/company_info/relaycue.md"
    assert resolve_company_info_path(
        "data/company_info/not-yet-created.md", repository_root=tmp_path
    ) == allowed / "not-yet-created.md"


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../secrets.txt",
        "data/company_info/../../secrets.txt",
        "/etc/passwd",
        r"C:\Windows\win.ini",
        "https://example.invalid/company.md",
        "file:///etc/passwd",
        "data/company_info/../prospect_pages/p001.txt",
    ],
)
def test_company_info_path_rejects_absolute_urls_and_traversal(tmp_path, unsafe_path):
    with pytest.raises(ValueError, match="company-info path"):
        resolve_company_info_path(unsafe_path, repository_root=tmp_path)


def test_company_info_path_rejects_symlink_escape_and_directories(tmp_path):
    allowed = tmp_path / "data" / "company_info"
    allowed.mkdir(parents=True)
    outside = tmp_path / "private"
    outside.mkdir()
    (outside / "secret.md").write_text("private", encoding="utf-8")
    try:
        (allowed / "escape").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("platform does not permit creating symlinks")

    with pytest.raises(ValueError, match="inside data/company_info"):
        resolve_company_info_path(
            "data/company_info/escape/secret.md", repository_root=tmp_path
        )
    with pytest.raises(ValueError, match="refer to a file"):
        resolve_company_info_path("data/company_info", repository_root=tmp_path)


def test_profile_input_loader_refuses_unsafe_legacy_database_paths(
    db_path, tmp_path, monkeypatch
):
    monkeypatch.setattr(local_paths, "REPOSITORY_ROOT", tmp_path)
    outside_secret = tmp_path / "secrets.md"
    outside_secret.write_text("Never load this text", encoding="utf-8")
    conn = db.connect()
    try:
        product_id = db.create_product(
            conn, name="Legacy unsafe path", docs_path="../secrets.md"
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(common.WorkflowInputError, match="safe path under data/company_info"):
        profile._profile_inputs(product_id)


def test_profile_input_loader_caps_company_info_file_size(db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(local_paths, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(profile, "MAX_DOCUMENT_BYTES", 8)
    source = tmp_path / "data" / "company_info" / "large.md"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"012345678")
    conn = db.connect()
    try:
        product_id = db.create_product(
            conn,
            name="Oversized local document",
            docs_path="data/company_info/large.md",
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(common.WorkflowInputError, match="exceeds 8 bytes"):
        profile._profile_inputs(product_id)
