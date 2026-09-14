import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LocationCategory(Base):
    """One entry in TrailMind's controlled category vocabulary.

    A CATALOG, not per-place data -- roughly 230 rows, seeded from
    app/services/places/category_catalog.py (which is the authoring source of
    truth; this table is its persisted form). Nothing here is written by the
    classification pipeline; only `location_category_assignments` is.

    WHY A TABLE RATHER THAN JUST THE PYTHON CONSTANTS:
    Two reasons, both concrete. First, referential integrity -- an assignment
    FKs to a real catalog row, so a typo'd slug fails at write time instead of
    producing a silent orphan bucket that ranking would quietly ignore
    forever. Second, `default_priority` is policy, and policy should be
    tunable against real data without a deploy; the Python catalog seeds it,
    the table owns it thereafter.

    THE NATURAL KEY IS (kind, slug), NOT slug ALONE. Three slugs deliberately
    exist under both kinds because they name genuinely different things --
    'trail' the theme means "this concerns the walking route", 'trail' the
    place_type means "this place IS a trail"; likewise 'area' and 'other'.
    Forcing global uniqueness would have meant renaming one side of each pair
    to something worse than the concept it names.
    """

    __tablename__ = "location_categories"
    __table_args__ = (
        UniqueConstraint("kind", "slug", name="uq_location_categories_kind_slug"),
        CheckConstraint(
            "default_priority >= 0 AND default_priority <= 100",
            name="ck_location_categories_default_priority_range",
        ),
        # Supports "list the catalog for this kind", which both the admin UI
        # and the AI classifier's vocabulary builder do on every call.
        Index("ix_location_categories_kind", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Stable machine name, e.g. 'wildlife', 'temple', 'teahouse'. This is what
    # rules and the AI classifier emit; display_name is never matched on.
    slug: Mapped[str] = mapped_column(String(50), nullable=False)
    # 'theme' (what the place is ABOUT -- Nature, Religious, Practical) or
    # 'place_type' (what it literally IS -- Temple, Waterfall, Teahouse). See
    # category_catalog.py for why this split is what makes deterministic
    # multi-category assignment possible.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Human-facing name. For the 16 categories that already existed as
    # `Location.category` values this is byte-identical to the legacy string
    # ("Food & Drink", "Culture & Heritage"), so a Location's primary theme
    # always reads the same as its legacy category column.
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 0-100. How much this category matters IN GENERAL -- the fallback when
    # nothing location-specific is known. Distinct from an assignment's
    # `relevance`, which is how much it matters for ONE place: "Nature" is a
    # different strength of claim at a waterfall than at a city park.
    default_priority: Mapped[int] = mapped_column(Integer, nullable=False)
    # Plain-language meaning. Load-bearing rather than decorative: this is the
    # vocabulary definition shown to the AI classifier, so vague text here
    # produces vague classifications.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provenance back to the third-party inventory this vocabulary started
    # from. Never a foreign key and never required -- null marks a category
    # TrailMind added because that inventory lacked it (all of the practical,
    # safety and trekking vocabulary a guide actually reports on).
    touristlink_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Retire a category without deleting it: assignments FK to this table with
    # RESTRICT, so deletion would either fail or destroy history. Deactivating
    # stops it being newly assigned while leaving what it already explains
    # intact -- the same reasoning as PlaceQuestion.active.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class LocationCategoryAssignment(Base):
    """One category applied to one Location, with how much it matters there.

    THE POINT OF THIS TABLE: a place is rarely one thing. A rainforest is
    Nature and Wildlife and Adventure at once; a bazaar is Shopping and Food
    and Local Life. Collapsing that into a single column -- which is what
    `Location.category` does -- loses exactly the information needed to decide
    what to surface first about a place. So the relationship itself carries
    data: not merely THAT a category applies, but how strongly (`relevance`),
    how sure we are (`confidence`), and on whose authority (`source`).

    DELIBERATELY ADDITIVE: `Location.category`/`subcategory` are NOT replaced
    and keep being written by exactly the same code as before. Several things
    depend on those being single comparable strings -- area resolution filters
    `category = 'Area'` in SQL, the area reuse radius is keyed off the
    subcategory literal, the candidate picker penalises 'Other' and
    de-duplicates by category, and the mobile map-pin icon switches on the
    category string. This table sits alongside all of that; the legacy pair is
    simply the primary assignment, denormalised.
    """

    __tablename__ = "location_category_assignments"
    __table_args__ = (
        # A category applies to a place or it does not -- it cannot apply
        # twice. Enforced by the DATABASE, matching the discipline
        # place_questions already uses for (location_id, normalized_text).
        UniqueConstraint(
            "location_id", "category_id", name="uq_location_category_assignment"
        ),
        # At most ONE primary per (location, kind) -- one primary theme and
        # one primary place_type, mirroring the legacy
        # (category, subcategory) pair. A partial unique index is what makes
        # "at most one" true in the database rather than merely intended by
        # the service layer. This is the reason `kind` is denormalised onto
        # this row: the index cannot reach across to location_categories.
        Index(
            "uq_location_category_primary_per_kind",
            "location_id",
            "kind",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        CheckConstraint(
            "relevance >= 0 AND relevance <= 100",
            name="ck_location_category_assignments_relevance_range",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_location_category_assignments_confidence_range",
        ),
        # "What are this place's categories, most relevant first" -- the read
        # every consumer performs.
        Index(
            "ix_location_category_assignments_location_relevance",
            "location_id",
            "relevance",
        ),
        # The inverse read: "which places are in this category?" -- category
        # search/filtering.
        Index(
            "ix_location_category_assignments_category",
            "category_id",
            "relevance",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT, not CASCADE: deleting a catalog entry must never silently
    # delete the assignments that explain places. Retire via `active` instead.
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("location_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Denormalised from the catalog row, solely so the partial unique index
    # above can enforce one primary per kind. A category's kind is fixed at
    # creation and never edited, so this cannot drift in practice; the
    # assignment service copies it from the catalog row it just resolved.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # 0-100, how much this category matters FOR THIS PLACE. The place_type
    # assignment anchors the scale at 100; implied themes carry the relevance
    # the catalog declares for that implication. A human may override this
    # (source='manual'), and reclassification then leaves it alone.
    relevance: Mapped[int] = mapped_column(Integer, nullable=False)
    # 0-1, how much the EVIDENCE is trusted -- Google's own primaryType scores
    # higher than a guess from the place's name. Kept separate from relevance
    # on purpose: "definitely a cafe, and being a cafe barely matters here" and
    # "possibly a viewpoint, and if so that is the whole point of the place"
    # are different statements, and collapsing them loses both.
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # One of category_rules.ASSIGNMENT_SOURCES. 'manual' is privileged: a
    # human's judgement is never overwritten by a later automatic run, the
    # same protection seed questions have from AI research refreshes.
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # Why this was assigned, in words -- "Google type 'hindu_temple'",
    # "implied by place type 'Temple'". Provenance for a human reviewing an
    # assignment that looks wrong, so the fix can target the rule rather than
    # the row.
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
