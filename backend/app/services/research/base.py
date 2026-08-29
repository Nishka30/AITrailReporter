"""The contract between "something researched the web" and everything that
consumes research.

Deliberately small. A finding is: what was asked, what came back, and where it
came from. Anything richer would encode one provider's response shape into the
rest of the system, which is the coupling this boundary exists to prevent.

SOURCES ARE NOT DECORATION. Every downstream consumer is required to attach
real citations to anything it asserts about a place, so a finding with no
sources is treated as no finding at all (see `is_usable`). That rule is the
reason provenance survives all the way to a question a guide sees.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class ResearchProviderError(Exception):
    """Any failure that prevents producing a finding. `message` is always safe
    to persist, log and show: never an API key, never raw provider internals."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ResearchSource:
    """One citation. `url` is always a real http(s) URL -- providers are
    responsible for discarding anything else before constructing this."""

    url: str
    title: str | None = None
    published_date: str | None = None


@dataclass(frozen=True)
class ResearchFinding:
    """One answered research query.

    `summary` is UNTRUSTED TEXT: it is assembled from arbitrary web pages and
    must never be interpolated into a prompt without going through
    sanitize.as_untrusted_block first. It is stored so we can always answer
    "why did TrailMind ask this?", not because it is believed.
    """

    topic: str
    query: str
    summary: str
    provider: str
    model: str
    retrieved_at: datetime
    sources: list[ResearchSource] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        """A finding worth reasoning over: it says something, and that
        something is attributable. Length 40 is a floor for "an actual
        statement" rather than a refusal or a stub."""
        return bool(self.sources) and len(self.summary.strip()) >= 40

    @property
    def source_urls(self) -> list[str]:
        return [s.url for s in self.sources]

    @property
    def source_titles(self) -> list[str]:
        return [s.title or "" for s in self.sources]


class ResearchProvider(Protocol):
    """What a research backend must offer.

    `run_query` either returns a finding or raises ResearchProviderError. It
    must never return a fabricated or sourceless result to paper over a
    failure -- callers rely on "no finding" being a truthful outcome, and the
    whole anti-hallucination chain rests on that being honest here.
    """

    name: str

    def run_query(
        self,
        query: str,
        *,
        topic: str,
        recency: str | None = None,
    ) -> ResearchFinding: ...
