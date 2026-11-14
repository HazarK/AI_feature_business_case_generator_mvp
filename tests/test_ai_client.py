"""Tests for the AI-client glue: JSON extraction, validation, retry — with a fake CLI runner
(no live Claude CLI call, so these run offline and fast)."""
from __future__ import annotations

import json

import pytest

from bizcase.ai_client import AnalysisError, analyze, extract_json, parse_case
from bizcase.examples import EXAMPLES
from bizcase.models import UserInputs

VALID_CASE_JSON = json.dumps(EXAMPLES["B2B SaaS — premium analytics upgrade"].model_dump(mode="json"))


def test_extract_json_handles_plain_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_handles_code_fence_and_prose():
    text = f"Sure, here is the analysis:\n```json\n{VALID_CASE_JSON}\n```\nLet me know if you need more."
    data = extract_json(text)
    assert data["mechanism"] == "upgrade"


def test_extract_json_raises_on_no_json():
    with pytest.raises(AnalysisError):
        extract_json("no json here at all")


def test_parse_case_validates_schema():
    case = parse_case(VALID_CASE_JSON)
    assert case.mechanism.value == "upgrade"


def test_parse_case_rejects_broken_schema():
    with pytest.raises(Exception):
        parse_case('{"company_summary": "x"}')  # missing required fields


def _inputs():
    return UserInputs(business_description="a" * 20, feature_description="b" * 20)


def test_analyze_succeeds_first_try_with_fake_runner():
    def fake_runner(prompt, **kw):
        return VALID_CASE_JSON

    case, notes = analyze(_inputs(), runner=fake_runner)
    assert case.mechanism.value == "upgrade"


def test_analyze_retries_once_on_bad_output_then_succeeds():
    calls = {"n": 0}

    def fake_runner(prompt, **kw):
        calls["n"] += 1
        return "not json at all" if calls["n"] == 1 else VALID_CASE_JSON

    case, notes = analyze(_inputs(), runner=fake_runner)
    assert calls["n"] == 2
    assert case.mechanism.value == "upgrade"


def test_analyze_raises_after_two_failures():
    def fake_runner(prompt, **kw):
        return "still not json"

    with pytest.raises(AnalysisError):
        analyze(_inputs(), runner=fake_runner)


def test_analyze_applies_user_overrides():
    def fake_runner(prompt, **kw):
        return VALID_CASE_JSON

    inputs = UserInputs(business_description="a" * 20, feature_description="b" * 20, known_active_users=12345)
    case, notes = analyze(inputs, runner=fake_runner)
    assert case.assumptions.base_population.value == 12345
    assert notes  # overriding a hypothetical value should produce a note
