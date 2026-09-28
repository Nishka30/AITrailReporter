"""Orchestrates producing and storing a reusable, structured summary of a
Location for the future Travelers website -- see
app/db/models/location_research_summary.py for the trust-boundary rationale.

This module has exactly one caller: place_questions.ensure_researched, right
after it persists this run's Perplexity findings. It deliberately runs NO web
search of its own; `findings` is the SAME list ensure_researched already
retrieved, reused here at zero extra Perplexity cost. That is what "avoid
duplicating the existing Perplexity research system" and "avoid
re-researching the same Location unnecessarily" mean in practice here: one
Perplexity run now feeds both question generation and this summary, and both
inherit ensure_researched's own concurrency lock and
place_question_refresh_days cooldown for free.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.location import Location
from app.db.models.location_research_summary import LocationResearchSummary
from app.services.place_summary import anthropic_provider
from app.services.place_summary.anthropic_provider import PlaceSummaryProviderError
from app.services.place_summary.validation import (
    PlaceSummaryValidationError,
    validate_summary_output,
)
from app.schemas.place_summary import PlaceResearchSummaryRead

logger = logging.getLogger(__name__)


def get_summary(db: Session, location_id: UUID) -> LocationResearchSummary | None:
    return db.execute(
        select(LocationResearchSummary).where(LocationResearchSummary.location_id == location_id)
    ).scalar_one_or_none()


def to_read(row: LocationResearchSummary | None) -> PlaceResearchSummaryRead | None:
    """None when this Location has never had a summary attempt -- distinct
    from status='pending'/'failed', both of which still return a (mostly
    empty) row so a caller can tell "we tried and got nothing" apart from
    "we've never tried"."""
    if row is None:
        return None
    return PlaceResearchSummaryRead(
        status=row.status,
        description=row.description,
        known_for=row.known_for,
        highlights=row.highlights or [],
        things_to_do=row.things_to_do or [],
        important_facts=row.important_facts or [],
        practical_info=row.practical_info,
        warnings=row.warnings or [],
        source_urls=row.source_urls or [],
        source_titles=row.source_titles or [],
        researched_at=row.researched_at,
    )


def _get_or_create_row(db: Session, location_id: UUID) -> LocationResearchSummary:
    existing = get_summary(db, location_id)
    if existing is not None:
        return existing
    row = LocationResearchSummary(location_id=location_id, status="pending")
    db.add(row)
    db.flush()
    return row


def _clear_content(row: LocationResearchSummary) -> None:
    row.description = None
    row.known_for = None
    row.highlights = None
    row.things_to_do = None
    row.important_facts = None
    row.practical_info = None
    row.warnings = None
    row.source_urls = None
    row.source_titles = None


def maybe_generate_summary(
    db: Session,
    location: Location,
    findings: list,
    *,
    allowed_urls: set[str],
) -> None:
    """Best-effort. NEVER RAISES: a summary-generation failure must never
    break the whole-location research run it piggybacks on.

    One row per Location, upserted in place (see LocationResearchSummary's
    docstring) -- a regeneration always overwrites the previous content
    rather than appending, since only the current summary is ever useful to a
    reader.
    """
    try:
        row = _get_or_create_row(db, location.id)

        raw = anthropic_provider.generate_place_summary(
            location.name,
            float(location.latitude),
            float(location.longitude),
            location.description,
            location.locality,
            findings,
            location.category,
            location.subcategory,
        )
        validated = validate_summary_output(raw, allowed_urls)

        row.provider = "anthropic"
        row.model = settings.anthropic_model
        row.researched_at = datetime.now(timezone.utc)

        if validated is None:
            # An honest, common outcome: research existed but supported
            # nothing citable to summarize. Recorded as a successful run with
            # no content, not a failure -- a failure would be retried on
            # every future research run for no reason, since this piggybacks
            # entirely on ensure_researched's own cooldown.
            row.status = "completed"
            row.error_message = None
            _clear_content(row)
            db.commit()
            logger.info("No usable summary content for location %s.", location.id)
            return

        row.status = "completed"
        row.error_message = None
        row.description = validated.description
        row.known_for = validated.known_for
        row.highlights = validated.highlights or None
        row.things_to_do = validated.things_to_do or None
        row.important_facts = validated.important_facts or None
        row.practical_info = validated.practical_info
        row.warnings = validated.warnings or None
        row.source_urls = validated.source_urls or None
        # Titles for the kept URLs, looked up from the findings' own source
        # lists rather than trusting anything the model said about a title.
        url_titles = {
            url: title
            for finding in findings
            for url, title in zip(finding.source_urls, finding.source_titles)
        }
        row.source_titles = [url_titles.get(u, "") for u in validated.source_urls] or None
        db.commit()
        logger.info("Generated place summary for location %s.", location.id)
    except (PlaceSummaryProviderError, PlaceSummaryValidationError) as exc:
        db.rollback()
        row = _get_or_create_row(db, location.id)
        row.status = "failed"
        row.error_message = str(getattr(exc, "message", exc))[:500]
        db.commit()
        logger.warning(
            "Place summary generation failed for location %s: %s", location.id, type(exc).__name__
        )
    except Exception as exc:  # noqa: BLE001 -- deliberate best-effort boundary
        db.rollback()
        logger.warning(
            "Unexpected failure generating place summary for location %s: %s",
            location.id, type(exc).__name__,
        )
