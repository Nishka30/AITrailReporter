"""Unit coverage for parsing Perplexity's cost/usage fields onto a
ResearchFinding (see app/services/research/perplexity_provider.py). No network:
httpx.post is monkeypatched to return canned response shapes, since the point
here is the parsing logic's own defensiveness, not the live API.
"""

from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.services.research import perplexity_provider


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _base_payload(**usage_overrides) -> dict:
    payload = {
        "model": "sonar",
        "choices": [{"message": {"content": "A" * 50}}],
        "citations": ["https://example.com/a"],
    }
    if usage_overrides is not None:
        payload["usage"] = usage_overrides
    return payload


@pytest.fixture(autouse=True)
def _ensure_key(monkeypatch):
    # PerplexityResearchProvider.__init__ requires a configured key; doesn't
    # matter that it's not a real one since httpx.post is stubbed below.
    monkeypatch.setattr(settings, "perplexity_api_key", "test-key-not-real")


def test_usage_and_cost_are_parsed_when_present(monkeypatch):
    payload = _base_payload(
        prompt_tokens=1200,
        completion_tokens=340,
        total_tokens=1540,
        cost={"input_tokens_cost": 0.0012, "output_tokens_cost": 0.00034, "total_cost": 0.00954},
    )
    monkeypatch.setattr(
        perplexity_provider.httpx, "post", lambda *a, **k: _FakeResponse(payload)
    )

    finding = perplexity_provider.get_provider().run_query("query text", topic="interest")

    assert finding.input_tokens == 1200
    assert finding.output_tokens == 340
    assert finding.cost_usd == pytest.approx(0.00954)


def test_missing_usage_degrades_to_none_without_raising(monkeypatch):
    payload = _base_payload()
    del payload["usage"]
    monkeypatch.setattr(
        perplexity_provider.httpx, "post", lambda *a, **k: _FakeResponse(payload)
    )

    finding = perplexity_provider.get_provider().run_query("query text", topic="interest")

    assert finding.input_tokens is None
    assert finding.output_tokens is None
    assert finding.cost_usd is None


def test_malformed_usage_shape_degrades_to_none_without_raising(monkeypatch):
    payload = _base_payload()
    payload["usage"] = {"prompt_tokens": "not-a-number", "cost": "also-not-a-dict"}
    monkeypatch.setattr(
        perplexity_provider.httpx, "post", lambda *a, **k: _FakeResponse(payload)
    )

    finding = perplexity_provider.get_provider().run_query("query text", topic="interest")

    assert finding.input_tokens is None
    assert finding.output_tokens is None
    assert finding.cost_usd is None
