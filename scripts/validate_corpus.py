#!/usr/bin/env python3
"""Validate the labelled offline corpus against the current importer contract."""

from __future__ import annotations

import csv
import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db, prospects  # noqa: E402

DATA_DIR = ROOT / "data"
PRODUCT_CSVS = {
    "relaycue": DATA_DIR / "prospects" / "SAMPLE_relaycue.csv",
    "fieldnest": DATA_DIR / "prospects" / "SAMPLE_fieldnest.csv",
}
PRODUCT_NAMES = {"relaycue": "RelayCue", "fieldnest": "FieldNest"}
PRODUCT_MOTIFS = {
    "relaycue": ("support", "case", "queue"),
    "fieldnest": ("maintenance", "equipment", "workshop", "plant", "fabrication"),
}
EXPECTED_PRODUCT_COUNTS = {"relaycue": 21, "fieldnest": 20}
EXPECTED_SHARED_IDS = {"P029", "P030", "P031", "P032"}
EXPECTED_REPLY_LABELS = Counter(
    {
        "interested": 8,
        "meeting_request": 7,
        "not_interested": 9,
        "out_of_office": 8,
        "wrong_person": 7,
        "unsubscribe": 7,
        "question": 7,
        "other": 7,
    }
)
EXPECTED_DEVELOPMENT_LABELS = Counter(
    {
        "interested": 5,
        "meeting_request": 4,
        "not_interested": 6,
        "out_of_office": 5,
        "wrong_person": 4,
        "unsubscribe": 4,
        "question": 4,
        "other": 4,
    }
)
EXPECTED_HELD_OUT_LABELS = Counter({label: 3 for label in EXPECTED_REPLY_LABELS})
EXPECTED_DIFFICULTY_COUNTS = {
    "development": Counter({"clear": 26, "ambiguous": 10}),
    "held_out": Counter({"clear": 14, "ambiguous": 10}),
}


class CorpusValidationError(RuntimeError):
    """A corpus invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CorpusValidationError(message)


def format_counts(counts: Counter[str]) -> str:
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts))


def iter_mappings(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_mappings(child)


def validate_sample_labels(files: list[Path]) -> None:
    require(bool(files), "data/ contains no corpus files")
    for path in files:
        if path.suffix.casefold() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                fields = reader.fieldnames or []
            if "sample_label" in fields:
                require(
                    bool(rows) and all(row.get("sample_label", "").strip() == "SAMPLE" for row in rows),
                    f"CSV records are not all labelled SAMPLE: {path.relative_to(ROOT)}",
                )
            else:
                require(
                    path.name.casefold().startswith("sample_"),
                    f"CSV file has no SAMPLE record label or SAMPLE filename: {path.relative_to(ROOT)}",
                )
        elif path.suffix.casefold() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = list(iter_mappings(payload))
            require(
                bool(records) and all(record.get("sample_label") == "SAMPLE" for record in records),
                f"JSON objects are not all labelled SAMPLE: {path.relative_to(ROOT)}",
            )
        else:
            text = path.read_text(encoding="utf-8")
            require(
                re.search(r"\bSAMPLE\b", text, flags=re.IGNORECASE) is not None,
                f"Text file is not labelled SAMPLE: {path.relative_to(ROOT)}",
            )
    print(f"PASS: SAMPLE labels present on all {len(files)} corpus files")


def load_prospects() -> tuple[dict[str, list[dict[str, str]]], dict[str, Path]]:
    expected_fields = list(prospects.CSV_FIELDS)
    grouped: dict[str, list[dict[str, str]]] = {}
    page_paths: dict[str, Path] = {}
    ids_by_product: dict[str, set[str]] = {}

    for product_id, csv_path in PRODUCT_CSVS.items():
        require(csv_path.is_file(), f"missing product prospect CSV: {csv_path.relative_to(ROOT)}")
        require(
            csv_path.name.casefold().startswith("sample_"),
            f"prospect CSV filename is not labelled SAMPLE: {csv_path.relative_to(ROOT)}",
        )
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames or []
            rows = list(reader)
        require(
            fields == expected_fields,
            f"{csv_path.relative_to(ROOT)} columns must exactly match app.prospects.CSV_FIELDS; "
            f"expected {expected_fields}, got {fields}",
        )
        require(
            len(rows) == EXPECTED_PRODUCT_COUNTS[product_id],
            f"{product_id} should contain {EXPECTED_PRODUCT_COUNTS[product_id]} prospects, got {len(rows)}",
        )

        product_ids: set[str] = set()
        for row in rows:
            require(bool(row["company_name"].strip()), f"empty company_name in {csv_path.name}")
            require(
                row["company_domain"].casefold().endswith(".example"),
                f"company_domain is not a reserved .example domain for {row['company_name']}",
            )
            require(
                row["employee_count"].isdigit(),
                f"employee_count is not a non-negative integer for {row['company_name']}",
            )
            relative_page = row["page_text_path"].replace("\\", "/")
            require(
                relative_page.startswith("data/prospect_pages/"),
                f"page_text_path must be repository-root-relative: {relative_page}",
            )
            resolved = prospects.resolve_page_path(row["page_text_path"])
            expected_path = (ROOT / relative_page).resolve()
            require(
                resolved == expected_path and resolved.is_relative_to(DATA_DIR / "prospect_pages")
                and resolved.is_file(),
                f"page_text_path does not resolve to a corpus page from the repository root: {relative_page}",
            )
            prospect_id = Path(relative_page).stem.upper()
            require(
                re.fullmatch(r"P\d{3}", prospect_id) is not None,
                f"page filename does not map to a prospect ID: {relative_page}",
            )
            require(prospect_id not in product_ids, f"duplicate prospect ID in {product_id}: {prospect_id}")
            product_ids.add(prospect_id)
            previous_path = page_paths.get(prospect_id)
            require(
                previous_path is None or previous_path == resolved,
                f"shared prospect ID points to different page files: {prospect_id}",
            )
            page_paths[prospect_id] = resolved
        grouped[product_id] = rows
        ids_by_product[product_id] = product_ids

    all_rows = [row for rows in grouped.values() for row in rows]
    require(len(all_rows) == 41, f"expected 41 product-prospect rows, got {len(all_rows)}")
    require(
        len(page_paths) == 37,
        f"expected 37 unique prospect sources, got {len(page_paths)}",
    )
    shared_ids = ids_by_product["relaycue"] & ids_by_product["fieldnest"]
    require(
        shared_ids == EXPECTED_SHARED_IDS,
        f"expected four specified prospects to be shared, got {sorted(shared_ids)}",
    )
    for product_id, rows in grouped.items():
        names = [row["company_name"].casefold() for row in rows]
        require(len(set(names)) == len(names), f"duplicate company within product {product_id}")
    print(
        "PASS: prospect CSV headers exactly match app.prospects.CSV_FIELDS "
        f"({len(expected_fields)} fields; {len(all_rows)} product rows)"
    )
    print(
        "PASS: repository-root page paths resolve "
        f"({len(page_paths)} unique sources across {len(all_rows)} product rows)"
    )
    return grouped, page_paths


def validate_real_import(grouped: dict[str, list[dict[str, str]]]) -> None:
    with tempfile.TemporaryDirectory(prefix="harvey-corpus-validation-") as temp_dir:
        conn = db.connect(str(Path(temp_dir) / "corpus.sqlite3"))
        try:
            db.init_db(conn)
            totals = Counter()
            for product_id, csv_path in PRODUCT_CSVS.items():
                product_db_id = db.create_product(
                    conn,
                    name=PRODUCT_NAMES[product_id],
                    docs_path=str(DATA_DIR / "company_info" / f"{product_id}.md"),
                )
                conn.commit()
                inserted, skipped = prospects.import_prospects_csv_file(
                    conn, product_id=product_db_id, csv_path=csv_path
                )
                imported_rows = db.list_prospects(conn, product_db_id)
                require(
                    inserted == len(grouped[product_id]) and skipped == 0
                    and len(imported_rows) == len(grouped[product_id]),
                    f"real importer result for {product_id}: inserted={inserted}, skipped={skipped}, "
                    f"stored={len(imported_rows)}",
                )
                totals["inserted"] += inserted
                totals["skipped"] += skipped
                print(f"PASS: real importer {PRODUCT_NAMES[product_id]} inserted={inserted}, skipped={skipped}")
            require(totals["inserted"] == 41 and totals["skipped"] == 0, "corpus import totals are incorrect")
            print(f"PASS: real import total inserted={totals['inserted']}, skipped={totals['skipped']}")
        finally:
            conn.close()


def validate_noisy_pages(page_paths: dict[str, Path]) -> None:
    expected_ids = {"P033", "P034", "P035"}
    noise_markers = {
        "navigation": ("navigation", "nav:"),
        "cookie banner": ("cookie",),
        "footer": ("footer",),
    }
    present: set[str] = set()
    for prospect_id in expected_ids:
        text = page_paths[prospect_id].read_text(encoding="utf-8").casefold()
        for marker, variants in noise_markers.items():
            if any(variant in text for variant in variants):
                present.add(marker)
    require(
        present == set(noise_markers),
        f"three noisy page samples must include navigation, cookie banner, and footer; found {sorted(present)}",
    )
    print("PASS: three prospect pages include navigation, cookie-banner, and footer noise")


def validate_replies() -> None:
    path = DATA_DIR / "sample_replies.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    replies = payload.get("replies", [])
    require(payload.get("sample_label") == "SAMPLE", "sample_replies.json root is not labelled SAMPLE")
    require(
        len(replies) == 60 and all(reply.get("sample_label") == "SAMPLE" for reply in replies),
        "sample_replies.json must contain 60 SAMPLE-labelled replies",
    )
    require(len({reply.get("reply_id") for reply in replies}) == 60, "reply IDs are not unique")
    require(
        all(reply.get("split") in {"development", "held_out"} for reply in replies),
        "reply split must be development or held_out",
    )
    require(
        all(reply.get("difficulty") in {"clear", "ambiguous"} for reply in replies),
        "every reply must have difficulty clear or ambiguous",
    )
    all_labels = Counter(reply.get("ground_truth_label", "") for reply in replies)
    held_out = [reply for reply in replies if reply.get("split") == "held_out"]
    development = [reply for reply in replies if reply.get("split") == "development"]
    held_out_labels = Counter(reply.get("ground_truth_label", "") for reply in held_out)
    development_labels = Counter(reply.get("ground_truth_label", "") for reply in development)
    require(
        len(development) == 36 and len(held_out) == 24,
        "reply split must be 36 development / 24 held_out",
    )
    require(all_labels == EXPECTED_REPLY_LABELS, f"unexpected all-reply labels: {dict(all_labels)}")
    require(
        development_labels == EXPECTED_DEVELOPMENT_LABELS,
        f"unexpected development labels: {dict(development_labels)}",
    )
    require(
        held_out_labels == EXPECTED_HELD_OUT_LABELS,
        f"held-out labels must include at least three examples of every label: {dict(held_out_labels)}",
    )
    difficulty_counts = {
        split: Counter(reply["difficulty"] for reply in split_replies)
        for split, split_replies in (("development", development), ("held_out", held_out))
    }
    require(
        difficulty_counts == EXPECTED_DIFFICULTY_COUNTS,
        f"unexpected reply difficulty counts: { {split: dict(counts) for split, counts in difficulty_counts.items()} }",
    )
    require(
        difficulty_counts["held_out"]["ambiguous"] * 3 >= len(held_out),
        "at least one third of held-out replies must be ambiguous",
    )
    print(f"Reply label counts (all {len(replies)}): {format_counts(all_labels)}")
    print(f"Reply label counts (development {len(development)}): {format_counts(development_labels)}")
    print(f"Reply label counts (held_out {len(held_out)}): {format_counts(held_out_labels)}")
    for split, split_replies in (("development", development), ("held_out", held_out)):
        print(
            f"Reply difficulty counts ({split} {len(split_replies)}): "
            f"{format_counts(difficulty_counts[split])}"
        )
    print("PASS: reply IDs, SAMPLE labels, difficulty annotations, and 36/24 development/held_out split")


def validate_product_distinction(
    grouped: dict[str, list[dict[str, str]]], page_paths: dict[str, Path]
) -> None:
    company_sets = {
        product_id: {row["company_name"].casefold() for row in rows}
        for product_id, rows in grouped.items()
    }
    rows_by_product_and_id = {
        product_id: {
            Path(row["page_text_path"]).stem.upper(): row
            for row in rows
        }
        for product_id, rows in grouped.items()
    }
    shared_ids = set(rows_by_product_and_id["relaycue"]) & set(rows_by_product_and_id["fieldnest"])
    require(shared_ids == EXPECTED_SHARED_IDS, "the expected four shared prospects are missing")
    for prospect_id in shared_ids:
        relaycue_row = rows_by_product_and_id["relaycue"][prospect_id]
        fieldnest_row = rows_by_product_and_id["fieldnest"][prospect_id]
        require(
            relaycue_row["company_name"].casefold() == fieldnest_row["company_name"].casefold()
            and relaycue_row["company_domain"].casefold() == fieldnest_row["company_domain"].casefold(),
            f"shared prospect {prospect_id} does not have matching company records",
        )
    expected_shared_names = {
        rows_by_product_and_id["relaycue"][prospect_id]["company_name"].casefold()
        for prospect_id in shared_ids
    }
    require(
        company_sets["relaycue"] & company_sets["fieldnest"] == expected_shared_names,
        "only the four specified prospects may be shared by the products",
    )
    motif_counts: dict[str, int] = {}
    for product_id, rows in grouped.items():
        profile_path = DATA_DIR / "company_info" / f"{product_id}.md"
        profile = profile_path.read_text(encoding="utf-8").casefold()
        profile_terms = {
            "relaycue": ("support", "handoff"),
            "fieldnest": ("maintenance", "equipment"),
        }[product_id]
        require(
            all(term in profile for term in profile_terms),
            f"{PRODUCT_NAMES[product_id]} company information lacks its product-specific profile terms",
        )
        hits = 0
        for row in rows:
            prospect_id = Path(row["page_text_path"]).stem.upper()
            text = page_paths[prospect_id].read_text(encoding="utf-8").casefold()
            hits += int(any(term in text for term in PRODUCT_MOTIFS[product_id]))
        motif_counts[product_id] = hits
        minimum_hits = (3 * len(rows) + 3) // 4
        require(
            hits >= minimum_hits,
            f"{PRODUCT_NAMES[product_id]} prospects lack a distinguishing source-page motif ({hits}/{len(rows)})",
        )
    print(
        "PASS: product prospect sets are distinguishable; "
        f"RelayCue support/case/queue motif={motif_counts['relaycue']}/{len(grouped['relaycue'])}, "
        f"FieldNest maintenance/equipment/workshop/plant/fabrication motif="
        f"{motif_counts['fieldnest']}/{len(grouped['fieldnest'])}; "
        f"{len(shared_ids)} company sources are deliberately shared"
    )


def validate_corpus() -> None:
    files = sorted(
        [
            DATA_DIR / "README.md",
            *PRODUCT_CSVS.values(),
            DATA_DIR / "sample_replies.json",
            *sorted((DATA_DIR / "company_info").glob("*.md")),
            *sorted((DATA_DIR / "prospect_pages").glob("*.txt")),
        ]
    )
    print("SAMPLE corpus validation (offline; no model or network calls)")
    validate_sample_labels(files)
    grouped, page_paths = load_prospects()
    validate_real_import(grouped)
    validate_noisy_pages(page_paths)
    validate_replies()
    validate_product_distinction(grouped, page_paths)
    print("CORPUS VALIDATION PASSED")


def main() -> int:
    try:
        validate_corpus()
    except (CorpusValidationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CORPUS VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
