"""Validates raw POI-discovery output before anything reaches PostgreSQL.

Same forgiving-per-item contract as place-question research: one malformed
place is dropped, the rest of the batch survives. A response that isn't the
agreed shape at all still raises.

What is NOT tolerated here, and is enforced structurally rather than by asking
the model nicely:
  - a place with no name, or a name that is really an AREA ("Koramangala")
  - a place with no coordinates
  - a place with no real http(s) source URL

The geographic sanity check -- is this coordinate actually near where we
searched? -- deliberately lives in poi_discovery.py instead, because only the
caller knows the query point. That check is the one that catches invented
coordinates, so it is applied to every place without exception.
"""

import logging
import re

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 500
MAX_PLACE_KIND_LENGTH = 50

# Words that mark a returned "place" as an AREA rather than something you can
# stand at and point to. The prompt rules these out, but they are the single
# most likely failure mode -- asking "what is near these coordinates?" invites
# the answer "Koramangala" -- so the rule is enforced in code as well.
#
# Matched as whole words against the lowercased name, so "Park Street" is not
# rejected for containing "park", while a bare "Koramangala Area" is.
_AREA_WORDS = frozenset(
    {
        "area",
        "neighbourhood",
        "neighborhood",
        "locality",
        "district",
        "suburb",
        "region",
        "province",
        "state",
        "county",
        "city",
        "town",
        "village",
        "municipality",
        "sector",
        "zone",
        "ward",
        "block",
        "layout",
        "colony",
        "township",
        "valley",
        "range",
        "country",
    }
)

# Latitude/longitude bounds. A value outside these isn't "far away", it is not
# a coordinate at all.
_LAT_RANGE = (-90.0, 90.0)
_LON_RANGE = (-180.0, 180.0)


class DiscoveredPlace(BaseModel):
    name: str = Field(min_length=2, max_length=MAX_NAME_LENGTH)
    place_kind: str = Field(default="", max_length=MAX_PLACE_KIND_LENGTH)
    latitude: float
    longitude: float
    description: str = Field(default="", max_length=MAX_DESCRIPTION_LENGTH)
    source_urls: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def must_be_a_specific_place(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("empty name")
        words = set(re.sub(r"[^a-z0-9\s]", " ", cleaned.lower()).split())
        # A single bare area word ("Koramangala Layout", "Thamel Area") is an
        # area. A longer name that merely contains one ("Cubbon Park Bandstand")
        # is not -- requiring the name to be short as well as area-flavoured
        # keeps real place names that happen to include these words.
        if len(words) <= 2 and words & _AREA_WORDS:
            raise ValueError(f"looks like an area rather than a specific place: {cleaned!r}")
        return cleaned

    @field_validator("latitude")
    @classmethod
    def valid_latitude(cls, value: float) -> float:
        if not (_LAT_RANGE[0] <= value <= _LAT_RANGE[1]):
            raise ValueError("latitude out of range")
        return value

    @field_validator("longitude")
    @classmethod
    def valid_longitude(cls, value: float) -> float:
        if not (_LON_RANGE[0] <= value <= _LON_RANGE[1]):
            raise ValueError("longitude out of range")
        return value

    @field_validator("place_kind")
    @classmethod
    def clean_kind(cls, value: str) -> str:
        return " ".join((value or "").split()).lower()[:MAX_PLACE_KIND_LENGTH]

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        return " ".join((value or "").split())[:MAX_DESCRIPTION_LENGTH]

    @field_validator("source_urls")
    @classmethod
    def require_real_sources(cls, value: list[str]) -> list[str]:
        cleaned = [
            u for u in value if isinstance(u, str) and u.startswith(("http://", "https://"))
        ][:8]
        if not cleaned:
            # A place with no traceable source is exactly the fabrication this
            # whole module exists to prevent. Dropped, never stored unsourced.
            raise ValueError("no real source URL")
        return cleaned


class DiscoveryEnvelope(BaseModel):
    """Outer shape only -- items are raw dicts here and validated individually
    below, so one malformed place cannot reject the whole batch."""

    places: list[dict] = Field(default_factory=list)
    found_information: bool


class DiscoveryValidationError(Exception):
    """The response was not the agreed shape at all (not merely a bad item)."""


def validate_discovery_output(raw: dict) -> list[DiscoveredPlace]:
    """Returns the structurally valid places, dropping malformed ones.

    An empty list is a legitimate outcome, not an error: plenty of coordinates
    genuinely have no documented named places nearby, and the caller records a
    successful run with zero discoveries rather than retrying forever.
    """
    if not isinstance(raw, dict):
        raise DiscoveryValidationError("Discovery output was not an object.")

    try:
        envelope = DiscoveryEnvelope.model_validate(
            {
                "places": raw.get("places") or [],
                "found_information": bool(raw.get("found_information", False)),
            }
        )
    except ValidationError as exc:
        raise DiscoveryValidationError(
            f"Discovery output had an unexpected shape: {exc.error_count()} errors"
        )

    if not envelope.found_information:
        return []

    valid: list[DiscoveredPlace] = []
    for item in envelope.places:
        try:
            valid.append(DiscoveredPlace.model_validate(item))
        except ValidationError as exc:
            logger.info("Dropped one malformed discovered place: %s", exc.error_count())
            continue
    return valid
