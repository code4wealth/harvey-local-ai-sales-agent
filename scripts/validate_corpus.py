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
EXPECTED_FIT_TIERS = {"poor_fit": 10, "not_marked_poor_fit": 27}
EXPECTED_SIGNAL_COUNTS = {"no_signal": 7, "implied_signal": 2}
EXPECTED_NEW_CASES = {
    "explicit_funding": 1,
    "leadership_change": 1,
    "pain_mention": 1,
    "mixed_multi_signal": 1,
    "negated_signal": 1,
    "stale_signal": 1,
    "third_party_signal": 1,
}


class CorpusValidationError(RuntimeError):
    """A corpus invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CorpusValidationError(message)


def format_counts(counts: Counter[str]) -> str:
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts))


def normalized_phrase(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def contains_phrase(text: str, phrase: str) -> bool:
    haystack = f" {normalized_phrase(text)} "
    needle = normalized_phrase(phrase)
    return bool(needle) and f" {needle} " in haystack


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


def load_case_notes(prospect_ids: set[str]) -> dict[str, dict[str, str]]:
    path = DATA_DIR / "sample_case_notes.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    require(
        reader.fieldnames == ["sample_label", "prospect_id", "case_type", "annotation"],
        "sample_case_notes.csv columns changed unexpectedly",
    )
    require(
        all(row["sample_label"] == "SAMPLE" for row in rows),
        "sample_case_notes.csv contains an unlabelled record",
    )
    notes = {row["prospect_id"]: row for row in rows}
    require(len(notes) == len(rows) == 37, "sample case notes must have 37 unique prospect annotations")
    require(set(notes) == prospect_ids, "sample case-note IDs do not match prospect page IDs")
    return notes


def validate_labels_and_signals(
    notes: dict[str, dict[str, str]], page_paths: dict[str, Path]
) -> None:
    case_counts = Counter(row["case_type"] for row in notes.values())
    unexpected_new_cases = {
        case_type: case_counts[case_type]
        for case_type, expected_count in EXPECTED_NEW_CASES.items()
        if case_counts[case_type] != expected_count
    }
    require(
        not unexpected_new_cases,
        f"new prospect signal and evidence-trap annotations are incorrect: {unexpected_new_cases}",
    )
    fit_tiers = Counter(
        "poor_fit" if row["case_type"].startswith("poor_fit") else "not_marked_poor_fit"
        for row in notes.values()
    )
    require(dict(fit_tiers) == EXPECTED_FIT_TIERS, f"unexpected fit-tier counts: {dict(fit_tiers)}")
    no_signal = sum(case_type.startswith("no_signal") for case_type in case_counts.elements())
    implied_signal = case_counts["implied_not_stated"]
    require(
        {"no_signal": no_signal, "implied_signal": implied_signal} == EXPECTED_SIGNAL_COUNTS,
        "unexpected no-signal / implied-signal counts",
    )
    print(f"Prospect case annotations: {format_counts(case_counts)}")
    print(
        "Prospects per fit tier (derived from case notes: poor_fit* vs not marked poor-fit): "
        f"{format_counts(fit_tiers)}"
    )
    print(f"No-signal prospects: {no_signal}; implied-not-stated prospects: {implied_signal}")

    expected_phrases = set(case_counts) | set(fit_tiers)
    filenames = [path.relative_to(DATA_DIR).as_posix() for path in DATA_DIR.rglob("*") if path.is_file()]
    leaked_names = [
        filename
        for filename in filenames
        if any(contains_phrase(filename, phrase) for phrase in expected_phrases)
    ]
    leaked_pages = []
    for prospect_id, page_path in page_paths.items():
        text = page_path.read_text(encoding="utf-8")
        leaked = [phrase for phrase in expected_phrases if contains_phrase(text, phrase)]
        if leaked:
            leaked_pages.append(f"{page_path.relative_to(ROOT)}: {sorted(leaked)}")
    require(not leaked_names, f"expected labels/tiers appear in filenames: {leaked_names}")
    require(not leaked_pages, f"expected labels/tiers appear in page text: {leaked_pages}")
    print(
        "PASS: no expected case label or fit tier appears in any corpus filename "
        f"or prospect page text ({len(page_paths)} pages checked)"
    )
    validate_case_evidence(page_paths)
    validate_noisy_pages(page_paths)


def validate_case_evidence(page_paths: dict[str, Path]) -> None:
    required_phrases = {
        "P026": ("series b", "$18 million"),
        "P027": ("maya calder", "chief customer officer"),
        "P028": ("requests often arrive", "handoff"),
        "P029": ("appointed", "second production line"),
        "P030": ("decided against", "no current plan"),
        "P031": ("april 2023", "service-center expansion"),
        "P032": ("baytree fabricators", "does not describe a change at ashdown metering"),
        "P037": ("october 6, 2026", "two maintenance mechanics"),
    }
    for prospect_id, phrases in required_phrases.items():
        text = page_paths[prospect_id].read_text(encoding="utf-8")
        missing = [phrase for phrase in phrases if not contains_phrase(text, phrase)]
        require(
            not missing,
            f"required scenario evidence is missing from {prospect_id}: {missing}",
        )
    print(
        "PASS: requested funding, leadership, pain, mixed-signal, negated, stale, "
        "third-party, and hiring evidence is present"
    )


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
    files = sorted(path for path in DATA_DIR.rglob("*") if path.is_file())
    print("SAMPLE corpus validation (offline; no model or network calls)")
    validate_sample_labels(files)
    grouped, page_paths = load_prospects()
    notes = load_case_notes(set(page_paths))
    validate_real_import(grouped)
    validate_labels_and_signals(notes, page_paths)
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
