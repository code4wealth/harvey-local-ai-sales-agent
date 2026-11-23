from __future__ import annotations

import math

import pytest

from app import scoring


def test_icp_similarity_maps_cosine_linearly_and_clamps():
    assert scoring.map_cosine_to_icp_similarity(0.15) == pytest.approx(0.0)
    assert scoring.map_cosine_to_icp_similarity(0.4) == pytest.approx(0.5)
    assert scoring.map_cosine_to_icp_similarity(0.65) == pytest.approx(1.0)
    assert scoring.map_cosine_to_icp_similarity(-0.5) == 0.0
    assert scoring.map_cosine_to_icp_similarity(1.0) == 1.0
    assert scoring.map_cosine_to_icp_similarity(None) is None


def test_icp_similarity_uses_cosine_of_vectors_and_missing_vectors_stay_null():
    assert scoring.cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert scoring.icp_similarity([1, 0], [1, 0]) == 1.0
    assert scoring.icp_similarity([1, 0], [0, 1]) == 0.0
    assert scoring.icp_similarity(None, [1, 0]) is None
    assert scoring.icp_similarity([0, 0], [1, 0]) is None
    assert scoring.icp_similarity([1], [1, 0]) is None


def test_signal_score_uses_highest_confidence_once_per_type_and_caps_at_100():
    assert scoring.signal_score(
        [
            {"type": "funding", "confidence": 0.2},
            {"type": "funding", "confidence": 0.8},
            {"type": "hiring", "confidence": 0.5},
            {"type": "none", "confidence": 1.0},
        ]
    ) == pytest.approx(36.5)
    assert scoring.signal_score(
        [
            {"type": signal_type, "confidence": 1.0}
            for signal_type in scoring.SIGNAL_WEIGHTS
        ]
    ) == 100.0
    assert scoring.signal_score([]) == 0.0
    assert scoring.signal_score(None) is None
    assert scoring.signal_score([{"type": "unweighted", "confidence": 1.0}]) is None
    assert scoring.signal_score([{"type": "funding", "confidence": 1.1}]) is None


def test_size_fit_is_full_in_range_and_logarithmic_to_zero_at_three_x():
    bounds = {"min": 100, "max": 1000}
    assert scoring.size_fit(100, bounds) == 100.0
    assert scoring.size_fit(500, bounds) == 100.0
    assert scoring.size_fit(1000, bounds) == 100.0
    assert scoring.size_fit(3000, bounds) == 0.0
    assert scoring.size_fit(100 / 3, bounds) == 0.0
    assert scoring.size_fit(1000 * math.sqrt(3), bounds) == pytest.approx(50.0)
    assert scoring.size_fit(None, bounds) is None
    assert scoring.size_fit(500, None) is None
    assert scoring.size_fit(0, {"min": 0, "max": 100}) == 100.0
    assert scoring.size_fit(0, {"min": 0, "max": 0}) == 100.0
    assert scoring.size_fit(1, {"min": 0, "max": 0}) == 0.0
    assert scoring.size_fit(500, {"min": 100, "max": None}) is None
    assert scoring.size_fit(500, {"min": 1000, "max": 100}) is None


def test_title_fit_uses_only_icp_buyer_title_keywords():
    buyer_titles = ["VP of Sales", "Head of Operations"]
    assert scoring.title_fit("Senior VP Sales, North America", buyer_titles) == 100.0
    assert scoring.title_fit("Sales Operations Manager", buyer_titles) == 60.0
    assert scoring.title_fit("Chief Financial Officer", buyer_titles) == 20.0
    assert scoring.title_fit("", buyer_titles) is None
    assert scoring.title_fit("VP Sales", []) is None


def test_score_keeps_missing_components_null_and_marks_partial():
    result = scoring.score_prospect(
        icp_similarity=0.5,
        signal_score=40,
        size_fit=None,
        title_fit=100,
    )
    assert result["score"] == pytest.approx(46.5)
    assert result["partial"] is True
    assert result["breakdown"]["size_fit"] is None
    assert result["breakdown"]["weighted_contributions"]["size_fit"] == 0.0
    assert result["breakdown"]["missing_components"] == ["size_fit"]

    empty = scoring.score_prospect(
        icp_similarity=None,
        signal_score=None,
        size_fit=None,
        title_fit=None,
    )
    assert empty["score"] == 0.0
    assert empty["partial"] is True
    assert empty["breakdown"]["missing_components"] == [
        "icp_similarity", "signal_score", "size_fit", "title_fit"
    ]
    assert set(empty["breakdown"]["weighted_contributions"].values()) == {0.0}

    complete = scoring.score_prospect(
        icp_similarity=0.5,
        signal_score=40,
        size_fit=80,
        title_fit=100,
    )
    assert complete["score"] == pytest.approx(58.5)
    assert complete["partial"] is False


def test_quote_verification_normalizes_text_and_rejects_empty_or_short_quotes():
    source = (
        "‘The café—team’s　size is １０’ and launch–ready workflow. "
        "superlongsingleword."
    )
    quotes, dropped = scoring.verify_quotes(
        source,
        [
            "'the café-team's size is 10'",
            "LAUNCH–READY workflow.",
            "not in the source",
            17,
            "   ",
            "",
            "the",
            "superlongsingleword",
        ],
    )
    assert quotes == ["'the café-team's size is 10'", "launch-ready workflow."]
    assert dropped == 6
    assert scoring.MIN_VERIFIED_QUOTE_CHARS == 8
    assert scoring.MIN_VERIFIED_QUOTE_WORDS == 2
