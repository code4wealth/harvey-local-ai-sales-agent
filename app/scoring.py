"""Deterministic, input-only prospect scoring and evidence verification."""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

logger = logging.getLogger("harvey.scoring")

SCORE_WEIGHTS: dict[str, float] = {
    "icp_similarity": 0.35,
    "signal_score": 0.35,
    "size_fit": 0.15,
    "title_fit": 0.15,
}

# Baseline weights already specified in docs/WORKFLOWS.md. Unknown signal types
# are uncomputable rather than silently assigned a guessed weight.
SIGNAL_WEIGHTS: dict[str, float] = {
    "funding": 30.0,
    "hiring": 25.0,
    "expansion": 20.0,
    "pain_mention": 25.0,
    "leadership_change": 15.0,
    "tech_change": 15.0,
}

_TITLE_CONNECTORS = {"a", "an", "and", "at", "for", "in", "of", "on", "the", "to"}
_TITLE_MODIFIERS = {"intern", "assistant", "associate", "junior", "former", "ex", "student"}
_TITLE_SENIORITY = {"vp", "director", "head", "manager", "chief", "senior", "lead"}
_TITLE_TOKEN_RE = re.compile(r"[^\w]+", flags=re.UNICODE)
MIN_VERIFIED_QUOTE_CHARS = 8
MIN_VERIFIED_QUOTE_WORDS = 2


def cosine_similarity(left: Sequence[float] | None, right: Sequence[float] | None) -> float | None:
    """Return cosine similarity, or ``None`` when vectors are unavailable/invalid."""
    if left is None or right is None:
        return None
    if isinstance(left, (str, bytes)) or isinstance(right, (str, bytes)):
        return None
    try:
        a = [float(value) for value in left]
        b = [float(value) for value in right]
    except (TypeError, ValueError, OverflowError):
        return None
    if not a or len(a) != len(b):
        return None
    if any(not math.isfinite(value) for value in a + b):
        return None
    norm_a = math.sqrt(sum(value * value for value in a))
    norm_b = math.sqrt(sum(value * value for value in b))
    if (
        norm_a == 0.0
        or norm_b == 0.0
        or not math.isfinite(norm_a)
        or not math.isfinite(norm_b)
    ):
        return None
    similarity = sum(x * y for x, y in zip(a, b)) / (norm_a * norm_b)
    if not math.isfinite(similarity):
        return None
    return max(-1.0, min(1.0, similarity))


def map_cosine_to_icp_similarity(cosine: float | None) -> float | None:
    """Map cosine 0.15–0.65 linearly to 0–1 and clamp outside that range."""
    if cosine is None:
        return None
    try:
        value = float(cosine)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value):
        return None
    return max(0.0, min(1.0, (value - 0.15) / (0.65 - 0.15)))


def icp_similarity(
    icp_embedding: Sequence[float] | None,
    prospect_embedding: Sequence[float] | None,
) -> float | None:
    """Compute mapped ICP similarity from two local embedding vectors."""
    return map_cosine_to_icp_similarity(cosine_similarity(icp_embedding, prospect_embedding))


def _signal_field(signal: Any, name: str) -> Any:
    if isinstance(signal, Mapping):
        return signal.get(name)
    try:
        return signal[name]
    except (KeyError, IndexError, TypeError):
        return getattr(signal, name, None)


def signal_score_details(
    signals: Sequence[Mapping[str, Any]] | None,
    *,
    weights: Mapping[str, float] = SIGNAL_WEIGHTS,
) -> dict[str, Any]:
    """Explain the weighted signal score; invalid or absent input remains unknown."""
    empty = {
        "score": None,
        "uncapped_score": None,
        "cap": 100.0,
        "contributions": [],
        "reason": "Signal input is missing or contains an invalid type/confidence.",
    }
    if signals is None or isinstance(signals, (str, bytes)):
        return empty
    best_by_type: dict[str, tuple[float, Any]] = {}
    for signal in signals:
        signal_type = _signal_field(signal, "type")
        if not isinstance(signal_type, str) or not signal_type.strip():
            return empty
        signal_type = signal_type.strip().lower()
        if signal_type == "none":
            continue
        if signal_type not in weights:
            return empty
        confidence = _signal_field(signal, "confidence")
        if isinstance(confidence, bool):
            return empty
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError, OverflowError):
            return empty
        if not math.isfinite(confidence_value) or not 0.0 <= confidence_value <= 1.0:
            return empty
        previous = best_by_type.get(signal_type)
        if previous is None or confidence_value > previous[0]:
            best_by_type[signal_type] = (confidence_value, signal)

    contributions: list[dict[str, Any]] = []
    total = 0.0
    for signal_type in sorted(best_by_type):
        confidence, signal = best_by_type[signal_type]
        try:
            weight = float(weights[signal_type])
        except (TypeError, ValueError, OverflowError):
            return empty
        if not math.isfinite(weight) or weight < 0.0:
            return empty
        contribution = weight * confidence
        total += contribution
        item = {
            "type": signal_type,
            "confidence": confidence,
            "weight": weight,
            "contribution": contribution,
        }
        evidence = _signal_field(signal, "evidence")
        if isinstance(evidence, str):
            item["evidence"] = evidence
        contributions.append(item)
    return {
        "score": min(100.0, total),
        "uncapped_score": total,
        "cap": 100.0,
        "contributions": contributions,
        "reason": "Highest confidence is used once per type; the total is capped at 100.",
    }


def signal_score(
    signals: Sequence[Mapping[str, Any]] | None,
    *,
    weights: Mapping[str, float] = SIGNAL_WEIGHTS,
) -> float | None:
    """Use the highest confidence once per type; return ``None`` if uncomputable."""
    return signal_score_details(signals, weights=weights)["score"]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def size_fit(employee_count: int | float | None, company_size: Mapping[str, Any] | None) -> float | None:
    """Score an ICP employee-size fit with a logarithmic decay to 3× out of range."""
    count = _number(employee_count)
    if count is None or count < 0 or company_size is None:
        return None
    if not isinstance(company_size, Mapping):
        return None
    minimum = _number(company_size.get("min"))
    maximum = _number(company_size.get("max"))
    if minimum is None or maximum is None or minimum < 0 or maximum < 0 or minimum > maximum:
        return None
    if maximum == 0:
        return 100.0 if minimum == 0 and count == 0 else 0.0
    if minimum <= count <= maximum:
        return 100.0
    if count > maximum:
        ratio = count / maximum
    else:
        if count == 0 or minimum == 0:
            return 0.0
        ratio = minimum / count
    if ratio >= 3.0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (1.0 - math.log(ratio) / math.log(3.0))))


def _title_tokens(value: str) -> list[str]:
    return [
        token
        for token in _TITLE_TOKEN_RE.sub(" ", value.casefold()).split()
        if token and token not in _TITLE_CONNECTORS
    ]


def title_fit(contact_title: str | None, buyer_titles: Sequence[str] | None) -> float | None:
    """Score 100 for a buyer-title phrase, 60 for keyword overlap, else 20."""
    if not isinstance(contact_title, str) or not contact_title.strip():
        return None
    if buyer_titles is None or isinstance(buyer_titles, (str, bytes)):
        return None
    targets = [title for title in buyer_titles if isinstance(title, str) and title.strip()]
    if not targets:
        return None
    candidate_tokens = _title_tokens(contact_title)
    if not candidate_tokens:
        return None
    if _TITLE_MODIFIERS.intersection(candidate_tokens):
        return 20.0
    candidate = set(candidate_tokens)
    candidate_keywords = candidate - _TITLE_SENIORITY
    target_tokens = [_title_tokens(target) for target in targets]
    target_tokens = [tokens for tokens in target_tokens if tokens]
    if not target_tokens:
        return None

    for tokens in target_tokens:
        width = len(tokens)
        if not set(tokens) - _TITLE_SENIORITY:
            continue
        if any(candidate_tokens[index : index + width] == tokens for index in range(len(candidate_tokens) - width + 1)):
            return 100.0
    if any(candidate_keywords.intersection(set(tokens) - _TITLE_SENIORITY) for tokens in target_tokens):
        return 60.0
    return 20.0


def score_prospect(
    *,
    icp_similarity: float | None,
    signal_score: float | None,
    size_fit: float | None,
    title_fit: float | None,
) -> dict[str, Any]:
    """Return components, missing flags, and a non-renormalized weighted total.

    Missing components stay null in the component breakdown, contribute zero,
    and are listed in ``missing_components``. The total uses original weights
    without re-normalization; ``partial`` is true whenever a component is missing.
    """
    components: dict[str, float | None] = {
        "icp_similarity": _bounded_component(
            icp_similarity, 0.0, 1.0, component="icp_similarity"
        ),
        "signal_score": _bounded_component(
            signal_score, 0.0, 100.0, component="signal_score"
        ),
        "size_fit": _bounded_component(size_fit, 0.0, 100.0, component="size_fit"),
        "title_fit": _bounded_component(title_fit, 0.0, 100.0, component="title_fit"),
    }
    contributions: dict[str, float] = {}
    missing_components = []
    for name, value in components.items():
        if value is None:
            missing_components.append(name)
            contributions[name] = 0.0
        else:
            contributions[name] = SCORE_WEIGHTS[name] * (
                value * 100.0 if name == "icp_similarity" else value
            )
    total = sum(contributions.values())
    partial = bool(missing_components)
    breakdown: dict[str, Any] = {
        **components,
        "weights": dict(SCORE_WEIGHTS),
        "weighted_contributions": contributions,
        "missing_components": missing_components,
        "partial": partial,
    }
    return {"score": total, "breakdown": breakdown, "partial": partial}


def _bounded_component(
    value: float | None,
    minimum: float,
    maximum: float,
    *,
    component: str = "score",
) -> float | None:
    parsed = _number(value)
    if parsed is None:
        if value is not None:
            logger.warning(
                "score component %s rejected non-numeric value %r",
                component,
                value,
            )
        return None
    if not minimum <= parsed <= maximum:
        logger.warning(
            "score component %s rejected out-of-range value %r (expected %s..%s)",
            component,
            value,
            minimum,
            maximum,
        )
        return None
    return parsed


def normalize_evidence_text(text: str) -> str:
    """Normalize Unicode compatibility forms, quotes, dashes, spaces, and case."""
    import unicodedata

    normalized = unicodedata.normalize("NFKC", text)
    replacements = {
        "‘": "'", "’": "'", "‚": "'", "‛": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"',
        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
        "―": "-", "−": "-", "﹘": "-", "﹣": "-", "－": "-",
    }
    normalized = normalized.translate(str.maketrans(replacements))
    return re.sub(r"\s+", " ", normalized).strip().lower()


def verify_quotes(source: str, quotes: Sequence[str]) -> tuple[list[str], int]:
    """Keep normalized quotes that occur in normalized source; return drop count."""
    if not isinstance(source, str):
        raise TypeError("source must be a string")
    if isinstance(quotes, (str, bytes)):
        raise TypeError("quotes must be a sequence of strings")
    normalized_source = normalize_evidence_text(source)
    verified: list[str] = []
    dropped = 0
    for quote in quotes:
        if not isinstance(quote, str):
            dropped += 1
            continue
        normalized_quote = normalize_evidence_text(quote)
        words = normalized_quote.split()
        if (
            len(normalized_quote) >= MIN_VERIFIED_QUOTE_CHARS
            and len(words) >= MIN_VERIFIED_QUOTE_WORDS
            and normalized_quote in normalized_source
        ):
            verified.append(normalized_quote)
        else:
            dropped += 1
    return verified, dropped


def verify_signals(
    source: str, signals: Sequence[Any] | None
) -> tuple[list[Any], int, int]:
    """Keep recognized signals whose evidence is source-backed.

    The original signal objects and evidence strings are retained. Returns the
    kept signals, invalid-quote count, and unsupported-type count.
    """
    if signals is None:
        return [], 0, 0
    if isinstance(signals, (str, bytes)):
        raise TypeError("signals must be a sequence of signal objects")
    kept: list[Any] = []
    quote_drops = 0
    type_drops = 0
    for signal in signals:
        signal_type = _signal_field(signal, "type")
        normalized_type = signal_type.strip().lower() if isinstance(signal_type, str) else ""
        if normalized_type == "none" or normalized_type not in SIGNAL_WEIGHTS:
            type_drops += 1
            continue
        evidence = _signal_field(signal, "evidence")
        verified, dropped = verify_quotes(source, [evidence])
        if dropped:
            quote_drops += dropped
            continue
        kept.append(signal)
    return kept, quote_drops, type_drops
