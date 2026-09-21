"""Where the guide actually was when they answered a question.

WHY THIS EXISTS: an answer's Submission has always had its coordinates
derived server-side -- from the knowledge gap's own target coordinates
(app/services/question_answers.py) or from the place a place question is
about (app/services/place_question_answers.py). Neither is where the guide
stood, and when a guide has moved on, extraction's own fallback (their most
recent GuideLocation ping) is staler still: a guide who recorded a position
in a park and walked two kilometres before answering would have the answer
filed against the park.

So the client may now say where it actually was. Optional throughout: an
answer that carries no coordinates keeps exactly the pre-existing server-side
derivation, which is what every older app build sends and what a guide who
declines the location prompt still gets.

Validation deliberately mirrors SubmissionCreate's (app/schemas/submission.py)
rather than inventing a second dialect -- same tolerant unknown-source
degrading, same "coordinates are the evidence for a source label" rule.
"""

import logging
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.models.submission import DEFAULT_LOCATION_SOURCE, SUBMISSION_LOCATION_SOURCES
from app.services.geo_validation import validate_optional_coordinate_pair

logger = logging.getLogger(__name__)


class AnswerLocationFields(BaseModel):
    """Mixed into both answer-create schemas. Every field optional."""

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_source: str | None = None
    location_accuracy_meters: float | None = Field(default=None, gt=0)
    location_captured_at: datetime | None = None
    location_label: str | None = Field(default=None, max_length=255)
    external_place_id: str | None = Field(default=None, max_length=255)

    @field_validator("location_source")
    @classmethod
    def known_location_source(cls, value: str | None) -> str | None:
        # Tolerant, exactly like SubmissionCreate: an unrecognised label from
        # a newer/older app degrades to "unknown" rather than rejecting a
        # real answer over a provenance string.
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned not in SUBMISSION_LOCATION_SOURCES:
            logger.info(
                "Unknown location_source %r on an answer -- using %r.",
                value,
                DEFAULT_LOCATION_SOURCE,
            )
            return DEFAULT_LOCATION_SOURCE
        return cleaned

    @model_validator(mode="after")
    def validate_coordinate_pair(self) -> "AnswerLocationFields":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        # Same (0, 0)-is-a-placeholder rule as SubmissionCreate -- see
        # app/services/geo_validation.py. A captured location that decodes to
        # exactly (0, 0) is rejected here rather than silently accepted as
        # 'gps_live'/'photo_exif' evidence it never actually was.
        validate_optional_coordinate_pair(self.latitude, self.longitude)
        if (
            self.location_source is not None
            and self.location_source != DEFAULT_LOCATION_SOURCE
            and self.latitude is None
        ):
            raise ValueError(
                f"location_source {self.location_source!r} requires latitude/longitude"
            )
        return self

    def has_captured_location(self) -> bool:
        """True only when a real coordinate pair arrived. `location_label` or
        `external_place_id` alone is not enough -- the coordinate is the
        evidence, and without it there is nothing to place the answer at."""
        return self.latitude is not None and self.longitude is not None

    def submission_location_kwargs(self) -> dict:
        """The Submission fields to use for a captured location. Callers use
        this ONLY when has_captured_location() is true, keeping their existing
        derivation untouched otherwise."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "location_source": self.location_source or DEFAULT_LOCATION_SOURCE,
            "location_accuracy_meters": self.location_accuracy_meters,
            "location_captured_at": self.location_captured_at,
            "location_label": self.location_label,
            "location_evidence": (
                "Captured by the guide on their device at the moment they answered."
            ),
            "external_place_id": self.external_place_id,
        }
