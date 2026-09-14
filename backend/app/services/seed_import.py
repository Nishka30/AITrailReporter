"""Imports curated seed data (a human-vetted spreadsheet of real places and
starter questions) into the EXISTING Location/PlaceQuestion system.

WHAT THIS IS AND IS NOT: this is not a new place-identification backend
alongside Google/OSM -- it is a THIRD way a Location can come to exist
(`provider='seed'`, `source='manual'`, both already-supported values, see
db/models/location.py), and a way PlaceQuestion rows can come to exist
(`source='seed'`, see db/models/place_question.py) without ever having been
produced by the Perplexity+Claude pipeline. Everything downstream --
geographic matching, the picker, "About this place", reward resolution,
extraction -- treats a seed Location and a seed question exactly like any
other, because they ARE ordinary rows in the same tables.

TWO SHAPES OF INPUT, because the source spreadsheet has two:

  1. Per-venue rows (one CSV row per real place, each with its OWN
     latitude/longitude and up to 4 starter questions specific to that
     venue). These become ordinary Locations, found-or-created through the
     SAME dedup primitive discovery already uses
     (poi_discovery.find_similar_nearby_location) so a venue that already
     exists in this environment's database -- discovered by Google, or
     entered by hand -- is matched and reused rather than duplicated. Their
     questions are ordinary PlaceQuestion rows on that Location.

  2. Hub-level rows (a flat list of generic questions per named hub --
     "Thamel", "Lukla" -- with NO per-question coordinate at all: the
     question is about the AREA, not one venue). These attach to the hub's
     own Location -- for this launch data, that Location already exists,
     because Google's reverse-geocode area mechanism
     (poi_discovery.maybe_resolve_area_place) independently resolves both
     names from real coordinates inside them. `ensure_curated_hub` finds
     that SAME Area Location and marks it as a hub with its own eligibility
     radius (db/models/curated_hub.py); nothing here invents a new place
     concept for "the hub" -- it reuses the one Locations already has.

COORDINATE TRUST: a curated row's own stated confidence
("High"/"Medium"/"Low") widens the dedup search radius for Low-confidence
rows only -- a pin that might be a little off should look a LITTLE further
before concluding "this is a new place", never a lot further, and never for
rows the curator was already sure about. This is the only place confidence
changes behaviour at import time; services/place_candidates.py separately
uses the STORED value to rank a Low-confidence place slightly below an
equally-distant one we're more sure of, in the picker.

IDEMPOTENT AND ADDITIVE, always: re-running this importer against the same
spreadsheet reconciles in place (an existing seed Location's fields are
refreshed, an existing seed question's text/kind/context are refreshed) and
never deactivates or deletes a seed question that a later run's input simply
doesn't mention. Nothing here ever touches an `ai_research` PlaceQuestion, a
non-seed Location, or the knowledge-gap pipeline at all.
"""

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.curated_hub import DEFAULT_HUB_RADIUS_METERS, CuratedHub
from app.db.models.location import Location
from app.db.models.place_question import PlaceQuestion
from app.services.place_questions import normalize_question
from app.services.places import categories, category_assignment
from app.services.poi_discovery import find_similar_nearby_location

logger = logging.getLogger(__name__)

# A starter question that is actually a photo-capture instruction rather than
# an interrogative ("Take photos of the outside, menu, seating and something
# you ordered.") -- consistent across the launch data for restaurant/shop/
# gift-shop/attraction/tour-operator/nightlife rows. Detected by pattern
# rather than by a spreadsheet column that doesn't exist, so this is the one
# place a wrong guess is possible; the raw text always survives regardless of
# which contribution_kind it's filed under.
_PHOTO_INSTRUCTION_RE = re.compile(r"\btake\s+photos?\b", re.IGNORECASE)

_CONFIDENCE_CANONICAL = ("High", "Medium", "Low")


@dataclass(frozen=True)
class SeedPlaceRow:
    """One venue from a per-venue CSV -- see module docstring, shape 1."""

    name: str
    area_street: str | None
    summary: str | None
    raw_type: str | None
    questions: list[str]
    latitude: float
    longitude: float
    confidence: str | None
    coordinate_type: str | None


@dataclass
class ImportStats:
    locations_created: int = 0
    locations_matched: int = 0
    questions_created: int = 0
    questions_updated: int = 0
    hubs_configured: list[str] = field(default_factory=list)
    hub_questions_created: int = 0
    hub_questions_updated: int = 0
    hub_missing: list[str] = field(default_factory=list)
    rows_failed: list[tuple[str, str]] = field(default_factory=list)
    # A NEW Location was created (nothing matched within the dedup radius),
    # but something with the exact same name exists further away than that
    # radius -- name, existing-row provider, and the real PostGIS distance.
    # Never auto-merged (see import_seed_place's docstring: blind widening
    # risks false-positive merges in dense areas far more than it saves),
    # but never silent either -- a same-name pair this far apart is either
    # two genuinely different places sharing a common name, or the same
    # place that moved, and only a human standing there can tell which.
    possible_duplicates: list[tuple[str, str, float]] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"Locations: {self.locations_created} created, {self.locations_matched} matched to existing",
            f"Venue questions: {self.questions_created} created, {self.questions_updated} updated",
            f"Hub questions: {self.hub_questions_created} created, {self.hub_questions_updated} updated",
            f"Hubs configured: {', '.join(self.hubs_configured) or '(none)'}",
        ]
        if self.possible_duplicates:
            lines.append(
                f"!! {len(self.possible_duplicates)} possible duplicate(s) -- same name, "
                f"too far apart to auto-merge -- worth a human look:"
            )
            for name, existing_provider, distance in self.possible_duplicates:
                lines.append(
                    f"     {name!r}: an existing {existing_provider}-sourced Location with this "
                    f"exact name is {distance:.0f}m away (outside the dedup radius)"
                )
        if self.hub_missing:
            lines.append(
                f"!! Hubs NOT found (no existing Location with this name -- see run_full_import's docstring): "
                f"{', '.join(self.hub_missing)}"
            )
        if self.rows_failed:
            lines.append(f"!! {len(self.rows_failed)} row(s) failed:")
            for name, error in self.rows_failed:
                lines.append(f"     {name}: {error}")
        return "\n".join(lines)


def _normalize_confidence(raw: str | None) -> str | None:
    """Canonicalizes to Title Case for the known values; preserves anything
    else verbatim rather than discarding it -- an unexpected value is still
    real information a human wrote down, not noise to drop."""
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    for canonical in _CONFIDENCE_CANONICAL:
        if cleaned.lower() == canonical.lower():
            return canonical
    return cleaned


def _dedup_radius_for(confidence: str | None) -> float:
    """How far to look for an existing match before concluding this is a new
    place. Widened only for Low confidence, and only modestly -- see the
    module docstring's "COORDINATE TRUST" section."""
    base = settings.poi_discovery_dedup_radius_meters
    if confidence == "Low":
        return base * 2
    return base


def _contribution_kind_for(question_text: str) -> str:
    if _PHOTO_INSTRUCTION_RE.search(question_text):
        return "photo"
    return "experience"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_thamel_csv(path: Path) -> list[SeedPlaceRow]:
    """Column layout: Place name, Area / street, Short summary, Type,
    Starter question 1-4, Latitude, Longitude, Coordinate confidence,
    Coordinate type."""
    rows = []
    for raw in _read_csv_rows(path):
        questions = [
            raw[f"Starter question {n}"].strip()
            for n in (1, 2, 3, 4)
            if raw.get(f"Starter question {n}", "").strip()
        ]
        rows.append(
            SeedPlaceRow(
                name=raw["Place name"].strip(),
                area_street=(raw.get("Area / street") or "").strip() or None,
                summary=(raw.get("Short summary") or "").strip() or None,
                raw_type=(raw.get("Type") or "").strip() or None,
                questions=questions,
                latitude=float(raw["Latitude"]),
                longitude=float(raw["Longitude"]),
                confidence=_normalize_confidence(raw.get("Coordinate confidence")),
                coordinate_type=(raw.get("Coordinate type") or "").strip() or None,
            )
        )
    return rows


def parse_lukla_csv(path: Path) -> list[SeedPlaceRow]:
    """Column layout: name, category, latitude, longitude,
    coordinate_confidence, summary, question_1-4. No area/street column, no
    coordinate_type column -- both are None for every row from this sheet."""
    rows = []
    for raw in _read_csv_rows(path):
        questions = [
            raw[f"question_{n}"].strip()
            for n in (1, 2, 3, 4)
            if raw.get(f"question_{n}", "").strip()
        ]
        rows.append(
            SeedPlaceRow(
                name=raw["name"].strip(),
                area_street=None,
                summary=(raw.get("summary") or "").strip() or None,
                raw_type=(raw.get("category") or "").strip() or None,
                questions=questions,
                latitude=float(raw["latitude"]),
                longitude=float(raw["longitude"]),
                confidence=_normalize_confidence(raw.get("coordinate_confidence")),
                coordinate_type=None,
            )
        )
    return rows


def parse_hub_questions_txt(path: Path) -> dict[str, list[str]]:
    """A plain-text file laid out as blank-line-separated BLOCKS, each block
    being one hub: its name alone on the first line, then one question per
    line until the next blank line (or end of file). Returns
    {hub_name: [question, ...]}, preserving file order, which becomes
    display_order.

    Parsed structurally (blank line = block boundary, first line of a block
    = the name) rather than by guessing which lines "look like" a header --
    a guess would be one more thing to get subtly wrong for a hub name this
    parser has never seen; this format has exactly one rule, and any file
    that follows it parses correctly regardless of what the hubs are called.
    """
    with open(path, encoding="utf-8") as handle:
        raw_lines = [line.strip() for line in handle]

    blocks: list[list[str]] = [[]]
    for line in raw_lines:
        if not line:
            if blocks[-1]:
                blocks.append([])
            continue
        blocks[-1].append(line)

    sections: dict[str, list[str]] = {}
    for block in blocks:
        if not block:
            continue
        name, *questions = block
        sections[name] = questions
    return sections


# How far to search for an EXACT-name collision worth flagging for human
# review, once auto-merge has already ruled out anything close enough to
# safely reuse. Wider than any dedup radius on purpose -- this never creates
# or merges anything, it only decides whether to print a warning, so a wide
# net costs nothing but a review-list line and catches genuinely useful
# cases like a place that moved a few hundred metres (see
# import_seed_place's docstring).
_DUPLICATE_REVIEW_RADIUS_METERS = 2_000


def _flag_possible_duplicate(db: Session, row: SeedPlaceRow, stats: ImportStats) -> None:
    target = make_point(row.latitude, row.longitude)
    match = db.execute(
        select(Location, func.ST_Distance(Location.geog, target).label("distance_meters"))
        .where(
            func.lower(Location.name) == row.name.strip().lower(),
            func.ST_DWithin(Location.geog, target, _DUPLICATE_REVIEW_RADIUS_METERS),
        )
        .order_by("distance_meters")
        .limit(1)
    ).first()
    if match is not None:
        existing_location, distance_meters = match
        stats.possible_duplicates.append((row.name, existing_location.provider or "manual", distance_meters))


def import_seed_place(db: Session, row: SeedPlaceRow, stats: ImportStats) -> Location:
    """Finds-or-creates the Location for one curated venue row.

    Reuses find_similar_nearby_location -- the SAME dedup primitive
    discovery already uses -- so a venue Google (or a human) already put in
    this database is matched and reused, never duplicated. No identity
    (provider, external_place_id) match is attempted first, unlike
    discovery's own find-or-create: a curated row has no external id at all,
    only a name and a coordinate, so name+proximity is the only signal
    there is -- exactly what "match using existing identifiers/coordinates/
    name/address where possible" means when no identifier exists.
    """
    existing = find_similar_nearby_location(
        db, row.latitude, row.longitude, row.name, radius_meters=_dedup_radius_for(row.confidence)
    )
    if existing is not None:
        # Reconcile in place -- a re-run refreshes curated fields on the
        # matched row (including one Google/a human already created) without
        # touching anything about it this importer doesn't own, like its
        # discovery/provenance columns.
        existing.description = row.summary or existing.description
        existing.place_kind = row.raw_type or existing.place_kind
        if row.raw_type:
            category, subcategory = categories.classify_seed_type(row.raw_type)
            existing.category = category
            existing.subcategory = subcategory
        existing.formatted_address = row.area_street or existing.formatted_address
        existing.coordinate_confidence = row.confidence or existing.coordinate_confidence
        existing.coordinate_type = row.coordinate_type or existing.coordinate_type
        # Curated data is better evidence than whatever originally classified
        # this row, so re-run multi-category classification too. A curator's
        # own manual assignments still win -- see category_assignment.
        category_assignment.maybe_assign_categories(db, existing)
        stats.locations_matched += 1
        return existing

    # Nothing close enough to auto-merge -- but if something with the EXACT
    # same name exists further away, that ambiguity is worth a human's
    # attention rather than silence. See ImportStats.possible_duplicates.
    _flag_possible_duplicate(db, row, stats)

    category, subcategory = categories.classify_seed_type(row.raw_type)
    location = Location(
        name=row.name,
        description=row.summary,
        latitude=row.latitude,
        longitude=row.longitude,
        geog=make_point(row.latitude, row.longitude),
        source="manual",
        provider="seed",
        external_place_id=None,
        place_kind=row.raw_type,
        category=category,
        subcategory=subcategory,
        formatted_address=row.area_street,
        coordinate_confidence=row.confidence,
        coordinate_type=row.coordinate_type,
    )
    db.add(location)
    db.flush()
    category_assignment.maybe_assign_categories(db, location)
    stats.locations_created += 1
    return location


def _upsert_question(
    db: Session,
    *,
    location_id,
    text: str,
    display_order: int,
    context_note: str | None,
    stats: ImportStats,
    is_hub: bool,
) -> None:
    """Creates or refreshes ONE PlaceQuestion row for a Location, keyed on
    the same (location_id, normalized_text) the database's own UNIQUE
    constraint uses. If an ACTIVE non-seed (ai_research) row already holds
    this exact text, the seed question is skipped entirely rather than
    creating a same-text duplicate under one Location -- the AI-researched
    version is left as the single source of truth for that text, and the
    curated row is redundant with it.

    Never deactivates anything -- see the module docstring's "IDEMPOTENT AND
    ADDITIVE" section.
    """
    key = normalize_question(text)
    if not key:
        return

    existing = db.execute(
        select(PlaceQuestion).where(
            PlaceQuestion.location_id == location_id,
            PlaceQuestion.normalized_text == key,
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.source != "seed":
            # An AI-researched question already occupies this exact text for
            # this Location -- nothing to add, and overwriting it would mean
            # a spreadsheet import silently replacing research provenance.
            return
        existing.question_text = text
        existing.contribution_kind = _contribution_kind_for(text)
        existing.context_note = context_note
        existing.display_order = display_order
        existing.active = True
        if is_hub:
            stats.hub_questions_updated += 1
        else:
            stats.questions_updated += 1
        return

    db.add(
        PlaceQuestion(
            location_id=location_id,
            question_text=text,
            normalized_text=key,
            contribution_kind=_contribution_kind_for(text),
            context_note=context_note,
            display_order=display_order,
            source_urls=None,
            source_finding_id=None,
            research_batch_id=None,
            source="seed",
            active=True,
        )
    )
    if is_hub:
        stats.hub_questions_created += 1
    else:
        stats.questions_created += 1


def import_seed_questions_for_location(
    db: Session, location: Location, row: SeedPlaceRow, stats: ImportStats
) -> None:
    """The up-to-4 starter questions for one venue row -- context_note comes
    from the row's OWN summary, which is real, curator-written grounding,
    not a fabricated reason (see PlaceQuestion.context_note's own
    contract)."""
    for order, text in enumerate(row.questions):
        _upsert_question(
            db,
            location_id=location.id,
            text=text,
            display_order=order,
            context_note=row.summary,
            stats=stats,
            is_hub=False,
        )


def ensure_curated_hub(
    db: Session, hub_name: str, radius_meters: int, stats: ImportStats
) -> Location | None:
    """Finds the EXISTING Location named `hub_name` and marks it as a
    curated hub. Never creates a new Location for a hub -- see the module
    docstring's shape-2 explanation: for Thamel/Lukla this Location already
    exists (Google's own reverse-geocode area resolution independently
    produces it -- see poi_discovery.maybe_resolve_area_place), and a hub
    with no matching Location is reported as missing rather than invented,
    so a typo or an area Google genuinely doesn't recognise fails loudly
    instead of silently anchoring hub questions to a fabricated place.

    Matched by exact name -- deliberately stricter than the fuzzy
    name-similarity dedup venue rows use, because there are only ever a
    handful of hubs and picking the WRONG one silently would misattach an
    entire hub's worth of questions.
    """
    existing = db.execute(
        select(Location).where(Location.name == hub_name)
    ).scalars().first()
    if existing is None:
        stats.hub_missing.append(hub_name)
        return None

    hub = db.execute(
        select(CuratedHub).where(CuratedHub.location_id == existing.id)
    ).scalar_one_or_none()
    if hub is None:
        hub = CuratedHub(location_id=existing.id, radius_meters=radius_meters)
        db.add(hub)
    else:
        hub.radius_meters = radius_meters
    stats.hubs_configured.append(hub_name)
    return existing


def import_hub_questions(
    db: Session, hub_location: Location, questions: list[str], stats: ImportStats
) -> None:
    """The hub-level generic questions -- no per-question context_note,
    because none was supplied and PlaceQuestion.context_note's own contract
    is null-when-nothing-specific-was-established rather than a fabricated
    filler line."""
    for order, text in enumerate(questions):
        _upsert_question(
            db,
            location_id=hub_location.id,
            text=text,
            display_order=order,
            context_note=None,
            stats=stats,
            is_hub=True,
        )


def run_full_import(
    db: Session,
    *,
    thamel_csv: Path,
    lukla_csv: Path,
    hub_questions_txt: Path,
    hub_radius_meters: int = DEFAULT_HUB_RADIUS_METERS,
) -> ImportStats:
    """Runs the complete Thamel/Lukla curated import: venue rows from both
    CSVs, then hub-level questions from the text file, against whichever
    hub Location(s) it finds by name. Commits ONCE at the end -- either the
    whole run lands or none of it does, never a partial import left for a
    later run to reconcile against inconsistent state.

    Safe to re-run: see the module docstring's "IDEMPOTENT AND ADDITIVE"
    section. Never touches a Location or PlaceQuestion this importer didn't
    itself create in an earlier run.
    """
    stats = ImportStats()

    # Each row runs inside its own SAVEPOINT (begin_nested), not the outer
    # transaction directly: a failure rolls back only THAT row's uncommitted
    # work, leaving every earlier successful row in this same run intact and
    # still pending in the one final commit below. A bare db.rollback() here
    # would have discarded the whole run's progress on the first bad row,
    # which is the opposite of "one bad row must not sink the run".
    for row in parse_thamel_csv(thamel_csv) + parse_lukla_csv(lukla_csv):
        try:
            with db.begin_nested():
                location = import_seed_place(db, row, stats)
                import_seed_questions_for_location(db, location, row, stats)
        except Exception as exc:  # noqa: BLE001 -- one bad row must not sink the run
            stats.rows_failed.append((row.name, f"{type(exc).__name__}: {exc}"))
            logger.exception("Seed import failed for row %r", row.name)

    hub_sections = parse_hub_questions_txt(hub_questions_txt)
    for hub_name, questions in hub_sections.items():
        try:
            with db.begin_nested():
                hub_location = ensure_curated_hub(db, hub_name, hub_radius_meters, stats)
                if hub_location is not None:
                    import_hub_questions(db, hub_location, questions, stats)
        except Exception as exc:  # noqa: BLE001 -- one bad hub must not sink the run
            stats.rows_failed.append((hub_name, f"{type(exc).__name__}: {exc}"))
            logger.exception("Seed import failed for hub %r", hub_name)

    db.commit()
    return stats
