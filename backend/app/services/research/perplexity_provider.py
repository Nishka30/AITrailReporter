"""The ONLY file in this codebase that talks to Perplexity.

Same isolation rule as every other provider here (Sarvam, Anthropic, Overpass):
the SDK/wire format lives in exactly one module, and the rest of the system
depends on the neutral contract in base.py. Swapping research providers is a
one-file change.

WHAT PERPLEXITY IS FOR HERE
Given a place this system ALREADY KNOWS EXISTS, find what people actually say
about it, with citations. It is very good at this. Asked about a specific named
temple in a named locality it returned its local nickname, a festival-day detail
about the idol, and the fact that published opening times disagree between
listings -- all sourced, and all things a person standing there can check.

WHAT PERPLEXITY IS NOT FOR HERE, AND WHY THIS IS ENFORCED BY DESIGN
It is NOT used to discover what exists near a coordinate. This was measured,
not assumed: asked "what is within a few hundred metres of me right now?" with
`web_search_options.user_location` set to a Bengaluru coordinate, it replied
that it had no location and then answered about temples in CHENNAI -- a
different city roughly 300km away. A search API has no way to resolve a
lat/lon to what is physically nearby, and confidently guessing is worse than
refusing.

So the two capabilities are split by what each source can actually be trusted
for, and the split is structural:

    OpenStreetMap  ->  what is here, and exactly where     (poi_discovery_research/)
    Perplexity     ->  what the web says about that thing  (this module)
    Claude         ->  what is worth asking a guide        (place_question_research/)

A place name therefore never originates from a web search, and a coordinate
never originates from a language model.

COST: each call is a paid web search. Callers are responsible for caching and
for not asking twice; see place_questions.ensure_researched, which researches a
place once per refresh window.
"""

import logging
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.services.research import sanitize
from app.services.research.base import (
    ResearchFinding,
    ResearchProviderError,
    ResearchSource,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "perplexity"

# How many citations to keep per finding. Enough to show a claim is corroborated
# and to let a human audit it; not a copy of the result page.
_MAX_SOURCES = 8

# Perplexity's own instruction to itself. Kept short and strict: the research
# step must report what sources say and must not fill gaps, because everything
# downstream treats a finding as evidence of what is written about a place.
_RESEARCH_SYSTEM_PROMPT = (
    "You are a research assistant. Report ONLY what the search results actually "
    "say. Be specific and concrete: names, physical features, what visitors "
    "mention noticing, what varies or changes, what is currently true. Do not "
    "generalise from the type of place, do not add plausible-sounding detail, "
    "and do not pad. If the results say little about the specific place asked "
    "about, say so plainly and briefly rather than substituting information "
    "about the wider area."
)


def _extract_sources(payload: dict) -> list[ResearchSource]:
    """Citations from `search_results` when present, falling back to the flat
    `citations` URL list. Anything that is not a real http(s) URL is dropped
    rather than stored -- a citation that cannot be opened is not provenance.
    """
    sources: list[ResearchSource] = []
    seen: set[str] = set()

    for item in payload.get("search_results") or []:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if url in seen:
            continue
        seen.add(url)
        title = item.get("title")
        sources.append(
            ResearchSource(
                url=url,
                title=(title.strip()[:300] if isinstance(title, str) else None),
                published_date=(
                    item.get("date") if isinstance(item.get("date"), str) else None
                ),
            )
        )
        if len(sources) >= _MAX_SOURCES:
            return sources

    for url in payload.get("citations") or []:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if url in seen:
            continue
        seen.add(url)
        sources.append(ResearchSource(url=url))
        if len(sources) >= _MAX_SOURCES:
            break

    return sources


class PerplexityResearchProvider:
    """Implements base.ResearchProvider against Perplexity's chat completions
    endpoint (verified live: POST https://api.perplexity.ai/chat/completions,
    Bearer auth, `citations` + `search_results` returned alongside the answer)."""

    name = PROVIDER_NAME

    def __init__(self) -> None:
        if not settings.perplexity_api_key:
            # Same convention as the Sarvam and Anthropic providers: a missing
            # key is a clean, reportable configuration state, not a crash, and
            # never leaks whether some other key is present.
            raise ResearchProviderError("Web research is not configured on the server.")
        self._key = settings.perplexity_api_key
        self._model = settings.perplexity_model

    def run_query(
        self,
        query: str,
        *,
        topic: str,
        recency: str | None = None,
    ) -> ResearchFinding:
        body: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _RESEARCH_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            "max_tokens": 900,
            # Low temperature: this step is retrieval and faithful reporting,
            # not writing. Creativity here would be fabrication.
            "temperature": 0.1,
            "web_search_options": {"search_context_size": "medium"},
        }
        if recency:
            body["search_recency_filter"] = recency

        try:
            response = httpx.post(
                settings.perplexity_api_url,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=settings.perplexity_request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            # Status code only. The response body can echo request content and
            # the Authorization header must never reach a log line.
            logger.warning("Perplexity returned status %s", exc.response.status_code)
            raise ResearchProviderError(
                f"Web research request failed (status {exc.response.status_code})."
            ) from exc
        except Exception as exc:
            logger.warning("Perplexity request failed: %s", type(exc).__name__)
            raise ResearchProviderError("Could not reach the web research service.") from exc

        try:
            raw_summary = payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ResearchProviderError("Web research returned an unexpected response.") from exc

        # Scrubbed HERE, at the edge, so no untrusted web text ever exists
        # inside this system in a form that could reach a prompt unprocessed --
        # including the copy that gets persisted for provenance.
        summary = sanitize.scrub(
            raw_summary, max_chars=settings.place_research_max_summary_chars
        )
        sources = _extract_sources(payload)

        logger.info(
            "Research [%s]: %d chars, %d source(s).", topic, len(summary), len(sources)
        )
        return ResearchFinding(
            topic=topic,
            query=query,
            summary=summary,
            provider=self.name,
            model=str(payload.get("model") or self._model),
            retrieved_at=datetime.now(timezone.utc),
            sources=sources,
        )


def get_provider() -> PerplexityResearchProvider:
    """The configured research provider. A single call site to change when a
    second provider is added."""
    return PerplexityResearchProvider()
