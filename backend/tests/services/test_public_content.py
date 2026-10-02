"""Tests for the new public-content composers in
app/services/public_content.py: popular questions with approved answers, and
the route strip. (The researched-summary section is covered by
`place_summary_service`/`LocationResearchSummary`, which already existed
before this file was written -- see test_place_summary.py.)

Two layers, same split as test_place_candidates.py:
  - Pure unit tests of `_bucket_route_stop_freshness` -- no DB.
  - Composer tests against a FakeSession that returns pre-queued results in
    call order, so the SERVICE's own composition logic (grouping/ordering/
    filtering/omission) is exercised without a real Postgres/PostGIS
    connection. SQLAlchemy's own query correctness is not what these test --
    that's exercised by running the actual query against a real database,
    which this test suite does not have a fixture for (see
    test_place_candidates.py's identical convention).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.config import settings
from app.services import public_content as pc


# ---------------------------------------------------------------------------
# _bucket_route_stop_freshness: pure, no DB
# ---------------------------------------------------------------------------


def test_bucket_missing_when_no_observation():
    status, age_hours = pc._bucket_route_stop_freshness(None, datetime.now(timezone.utc))
    assert status == "missing"
    assert age_hours is None


def test_bucket_fresh_within_window(monkeypatch):
    monkeypatch.setattr(settings, "route_stop_freshness_window_hours", 72.0)
    monkeypatch.setattr(settings, "route_stop_aging_threshold_hours", 96.0)
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    observed_at = now - timedelta(hours=72)  # exactly at the boundary -- still fresh

    status, age_hours = pc._bucket_route_stop_freshness(observed_at, now)

    assert status == "fresh"
    assert age_hours == 72.0


def test_bucket_aging_just_past_freshness_window(monkeypatch):
    monkeypatch.setattr(settings, "route_stop_freshness_window_hours", 72.0)
    monkeypatch.setattr(settings, "route_stop_aging_threshold_hours", 96.0)
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    observed_at = now - timedelta(hours=72, minutes=1)

    status, _age_hours = pc._bucket_route_stop_freshness(observed_at, now)

    assert status == "aging"


def test_bucket_stale_past_aging_window(monkeypatch):
    monkeypatch.setattr(settings, "route_stop_freshness_window_hours", 72.0)
    monkeypatch.setattr(settings, "route_stop_aging_threshold_hours", 96.0)
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    observed_at = now - timedelta(hours=72 + 96, minutes=1)

    status, _age_hours = pc._bucket_route_stop_freshness(observed_at, now)

    assert status == "stale"


# ---------------------------------------------------------------------------
# Fake ORM rows + a minimal fake Session
# ---------------------------------------------------------------------------


@dataclass
class _FakeLocation:
    id: object
    name: str
    latitude: float = 27.68
    longitude: float = 86.72


@dataclass
class _FakeRoute:
    id: object
    slug: str
    name: str
    description: str | None = None


@dataclass
class _FakeRouteStop:
    id: object
    route_id: object
    location_id: object
    sequence_order: int
    stop_label: str | None = None
    elevation_meters: int | None = None


@dataclass
class _FakePlaceQuestion:
    id: object
    question_text: str
    context_note: str | None = None
    display_order: int = 0
    source: str = "seed"


@dataclass
class _FakeSubmission:
    id: object
    source_place_question_id: object
    raw_text: str
    submitted_at: datetime


@dataclass
class _FakeGuide:
    id: object
    name: str


class _FakeScalars:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return _FakeScalars(self._items)

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


class FakeSession:
    """Returns pre-queued `db.execute(...)` results in call order, and
    pre-registered `db.get(Model, id)` results -- never builds or runs a real
    query. `execute_queue` items are each a plain list of rows/tuples, one
    list per expected `db.execute` call, popped in order."""

    def __init__(self, execute_queue=None, get_results=None):
        self._execute_queue = list(execute_queue or [])
        self._get_results = dict(get_results or {})

    def execute(self, _stmt):
        return _FakeResult(self._execute_queue.pop(0))

    def get(self, _model, id_):
        return self._get_results.get(id_)


# ---------------------------------------------------------------------------
# list_public_place_questions
# ---------------------------------------------------------------------------


def test_questions_with_zero_approved_answers_are_omitted(monkeypatch):
    answered = _FakePlaceQuestion(id=uuid4(), question_text="Is the lodge open?")
    unanswered = _FakePlaceQuestion(id=uuid4(), question_text="Is Wi-Fi free?")
    monkeypatch.setattr(
        pc, "_active_place_questions", lambda db, location_id: [answered, unanswered]
    )
    guide = _FakeGuide(id=uuid4(), name="Pemba Sherpa")
    submission = _FakeSubmission(
        id=uuid4(), source_place_question_id=answered.id, raw_text="Yes, open as of today.",
        submitted_at=datetime(2026, 9, 27, tzinfo=timezone.utc),
    )
    db = FakeSession(execute_queue=[[(submission, guide)]])

    questions = pc.list_public_place_questions(db, uuid4())

    assert len(questions) == 1
    assert questions[0].place_question_id == answered.id
    assert questions[0].answers[0].guide_name == "Pemba Sherpa"


def test_questions_answers_capped_and_most_recent_first(monkeypatch):
    question = _FakePlaceQuestion(id=uuid4(), question_text="Is the lodge open?")
    monkeypatch.setattr(
        pc, "_active_place_questions", lambda db, location_id: [question]
    )
    guide = _FakeGuide(id=uuid4(), name="Mingma Sherpa")
    # Already ordered most-recent-first, as the real query does.
    submissions = [
        _FakeSubmission(
            id=uuid4(), source_place_question_id=question.id, raw_text=f"Answer {i}",
            submitted_at=datetime(2026, 9, 27 - i, tzinfo=timezone.utc),
        )
        for i in range(5)
    ]
    db = FakeSession(execute_queue=[[(s, guide) for s in submissions]])

    questions = pc.list_public_place_questions(db, uuid4())

    assert len(questions) == 1
    assert len(questions[0].answers) == pc._ANSWERS_PER_QUESTION_LIMIT
    assert questions[0].answers[0].answer_text == "Answer 0"


def test_questions_returns_empty_when_location_has_none(monkeypatch):
    monkeypatch.setattr(pc, "_active_place_questions", lambda db, location_id: [])
    db = FakeSession(execute_queue=[])

    assert pc.list_public_place_questions(db, uuid4()) == []


def test_split_keeps_only_unanswered_seed_questions_open():
    answered = _FakePlaceQuestion(id=uuid4(), question_text="Is the lodge open?")
    open_seed = _FakePlaceQuestion(id=uuid4(), question_text="Where can I change cash?")
    open_ai = _FakePlaceQuestion(
        id=uuid4(), question_text="Standing here, how does it look today?", source="ai_research"
    )
    answer = pc.PublicPlaceQuestionAnswer(
        submission_id=uuid4(), answer_text="Yes.", guide_name="Pemba Sherpa",
        answered_at=datetime(2026, 9, 27, tzinfo=timezone.utc),
    )

    popular, open_ = pc._split_place_questions([answered, open_seed, open_ai], {answered.id: [answer]})

    assert [q.place_question_id for q in popular] == [answered.id]
    assert [q.place_question_id for q in open_] == [open_seed.id]


# ---------------------------------------------------------------------------
# list_public_research_findings
# ---------------------------------------------------------------------------


@dataclass
class _FakeFinding:
    id: object
    location_id: object
    topic: str
    summary: str
    retrieved_at: datetime
    source_urls: list | None = None
    source_titles: list | None = None


def test_findings_keep_latest_per_topic_in_topic_order():
    place = _FakeLocation(id=uuid4(), name="Lukla Airport")
    older_interest = _FakeFinding(uuid4(), place.id, "interest", "old", datetime(2026, 8, 1, tzinfo=timezone.utc))
    newer_interest = _FakeFinding(uuid4(), place.id, "interest", "new", datetime(2026, 9, 1, tzinfo=timezone.utc))
    current = _FakeFinding(
        uuid4(), place.id, "current", "open daily", datetime(2026, 9, 2, tzinfo=timezone.utc),
        source_urls=["https://a.example", "https://b.example"], source_titles=["A"],
    )
    # Real query orders by retrieved_at desc.
    rows = [(f, place.name) for f in (current, newer_interest, older_interest)]

    findings = pc.list_public_research_findings(FakeSession(execute_queue=[rows]), place)

    assert [(f.topic, f.summary) for f in findings] == [("interest", "new"), ("current", "open daily")]
    assert [(s.url, s.title) for s in findings[1].sources] == [("https://a.example", "A"), ("https://b.example", None)]
    assert findings[0].location_name == "Lukla Airport"


def test_area_findings_put_the_hub_first_then_places_by_name():
    hub = _FakeLocation(id=uuid4(), name="Lukla")
    airport_id, gompa_id = uuid4(), uuid4()
    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = [
        (_FakeFinding(uuid4(), gompa_id, "interest", "g", when), "Lukla Gompa"),
        (_FakeFinding(uuid4(), airport_id, "current", "a-current", when), "Airport"),
        (_FakeFinding(uuid4(), hub.id, "interest", "h", when), "Lukla"),
        (_FakeFinding(uuid4(), airport_id, "interest", "a-interest", when), "Airport"),
    ]

    findings = pc.list_public_research_findings(FakeSession(execute_queue=[rows]), hub, 2000.0)

    assert [f.summary for f in findings] == ["h", "a-interest", "a-current", "g"]


def test_findings_empty_when_never_researched():
    place = _FakeLocation(id=uuid4(), name="Phakding")
    assert pc.list_public_research_findings(FakeSession(execute_queue=[[]]), place) == []


# ---------------------------------------------------------------------------
# get_public_route_for_location
# ---------------------------------------------------------------------------


def test_route_returns_none_when_location_is_not_a_stop():
    db = FakeSession(execute_queue=[[]])  # membership lookup: no route_id

    assert pc.get_public_route_for_location(db, uuid4(), datetime.now(timezone.utc)) is None


def test_route_returns_all_stops_ordered_with_status(monkeypatch):
    route_id = uuid4()
    route = _FakeRoute(id=route_id, slug="everest-base-camp-trek", name="Everest Base Camp Trek")
    lukla = _FakeLocation(id=uuid4(), name="Lukla")
    phakding = _FakeLocation(id=uuid4(), name="Phakding")
    stop_lukla = _FakeRouteStop(id=uuid4(), route_id=route_id, location_id=lukla.id, sequence_order=1)
    stop_phakding = _FakeRouteStop(
        id=uuid4(), route_id=route_id, location_id=phakding.id, sequence_order=2, elevation_meters=2610
    )

    db = FakeSession(
        execute_queue=[
            [route_id],  # membership lookup
            [(stop_lukla, lukla), (stop_phakding, phakding)],  # stops+location join
        ],
        get_results={route_id: route},
    )
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    monkeypatch.setattr(
        pc,
        "_latest_approved_observation_at_by_location",
        lambda db, location_ids: {lukla.id: now - timedelta(hours=10), phakding.id: None},
    )

    result = pc.get_public_route_for_location(db, lukla.id, now)

    assert result is not None
    assert result.route_id == route_id
    assert [s.name for s in result.stops] == ["Lukla", "Phakding"]
    assert result.stops[0].status == "fresh"
    assert result.stops[1].status == "missing"
    assert result.stops[1].elevation_meters == 2610


def test_route_is_deterministic(monkeypatch):
    route_id = uuid4()
    route = _FakeRoute(id=route_id, slug="s", name="Route")
    location = _FakeLocation(id=uuid4(), name="Lukla")
    stop = _FakeRouteStop(id=uuid4(), route_id=route_id, location_id=location.id, sequence_order=1)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(pc, "_latest_approved_observation_at_by_location", lambda db, ids: {location.id: None})

    def run():
        db = FakeSession(
            execute_queue=[[route_id], [(stop, location)]],
            get_results={route_id: route},
        )
        return pc.get_public_route_for_location(db, location.id, now)

    first, second = run(), run()
    assert first == second


# ---------------------------------------------------------------------------
# list_public_location_categories: category_knowledge.get_location_coverage
# monkeypatched -- this function's job is only the public trust reduction.
# ---------------------------------------------------------------------------


@dataclass
class _FakeKnowledgeItem:
    id: object
    knowledge_text: str
    last_verified_at: datetime | None
    freshness_duration_hours: int = 72
    active: bool = True


def _coverage(slug, items, *, kind="theme", state="missing", relevance=80, is_primary=False):
    from app.services.category_knowledge import CategoryCoverage

    return CategoryCoverage(
        category_assignment_id=uuid4(),
        category_id=uuid4(),
        slug=slug,
        kind=kind,
        display_name=slug.replace("_", " ").title(),
        relevance=relevance,
        is_primary=is_primary,
        state=state,
        items=items,
    )


def test_categories_expose_only_verified_active_knowledge(monkeypatch):
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    verified_old = _FakeKnowledgeItem(uuid4(), "Two lodges open", now - timedelta(hours=100))
    verified_new = _FakeKnowledgeItem(uuid4(), "Hot showers extra", now - timedelta(hours=5))
    pending = _FakeKnowledgeItem(uuid4(), "Unmoderated claim", None)
    retired = _FakeKnowledgeItem(uuid4(), "Superseded", now - timedelta(hours=1), active=False)
    monkeypatch.setattr(
        pc.category_knowledge_service,
        "get_location_coverage",
        lambda db, location_id, evaluation_time=None: [
            _coverage("lodging", [verified_old, pending, verified_new, retired], state="partially_stale")
        ],
    )

    [lodging] = pc.list_public_location_categories(None, uuid4(), now)

    texts = [k.knowledge_text for k in lodging.verified_knowledge]
    assert texts == ["Hot showers extra", "Two lodges open"]  # newest first, no pending/retired
    assert [k.fresh for k in lodging.verified_knowledge] == [True, False]
    assert lodging.state == "partially_stale"


def test_categories_keep_database_order_and_drop_catch_all(monkeypatch):
    monkeypatch.setattr(
        pc.category_knowledge_service,
        "get_location_coverage",
        lambda db, location_id, evaluation_time=None: [
            _coverage("area", [], kind="place_type", relevance=100, is_primary=True),
            _coverage("trekking", [], relevance=95),
            _coverage("other", [], relevance=70),
            _coverage("local_life", [], relevance=65),
        ],
    )

    categories = pc.list_public_location_categories(None, uuid4(), datetime.now(timezone.utc))

    assert [c.slug for c in categories] == ["area", "trekking", "local_life"]
    assert categories[0].kind == "place_type" and categories[0].is_primary
    assert all(c.verified_knowledge == [] for c in categories)


# ---------------------------------------------------------------------------
# _to_public_observation: both knowledge systems
# ---------------------------------------------------------------------------


@dataclass
class _ObsObservation:
    id: object = field(default_factory=uuid4)
    value: dict = field(default_factory=lambda: {"answer_text": "Lodge open"})
    evidence: str | None = "Lodge open"
    observed_at: datetime = field(default_factory=lambda: datetime(2026, 9, 28, tzinfo=timezone.utc))
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class _ObsSubmission:
    id: object = field(default_factory=uuid4)
    submission_type: str = "answer"
    location_label: str | None = None
    external_place_id: str | None = None
    audio: object = None


@dataclass
class _ObsGuide:
    name: str = "Pemba"


@dataclass
class _ObsKnowledgeType:
    knowledge_type: str = "trail_condition"
    display_name: str = "Trail Condition"
    safety_critical: bool = False


@dataclass
class _ObsCategory:
    slug: str = "lodging"
    display_name: str = "Lodging"


def test_category_observation_is_labelled_by_its_category(monkeypatch):
    monkeypatch.setattr(pc.submission_service, "list_submission_photos", lambda db, sid: [])

    obs = pc._to_public_observation(
        None, _ObsObservation(), None, _ObsSubmission(), _ObsGuide(), None, _ObsCategory()
    )

    assert (obs.knowledge_type, obs.display_name, obs.safety_critical) == ("lodging", "Lodging", False)
    assert (obs.category_slug, obs.category_display_name) == ("lodging", "Lodging")


def test_hazard_observation_has_no_category(monkeypatch):
    monkeypatch.setattr(pc.submission_service, "list_submission_photos", lambda db, sid: [])

    obs = pc._to_public_observation(
        None, _ObsObservation(), _ObsKnowledgeType(), _ObsSubmission(), _ObsGuide(), None, None
    )

    assert obs.knowledge_type == "trail_condition"
    assert obs.category_slug is None and obs.category_display_name is None


# ---------------------------------------------------------------------------
# _category_labels_by_location: grouping + de-duplication of the one batched
# query's rows (the SQL itself runs against a real DB, see module docstring).
# ---------------------------------------------------------------------------


class _RowsSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _stmt):
        rows = self._rows

        class _R:
            def all(self_inner):
                return rows

        return _R()


def test_category_labels_group_per_location_and_dedupe_same_name():
    a, b = uuid4(), uuid4()
    db = _RowsSession(
        [
            (a, "area", "place_type", "Area"),
            (a, "area", "theme", "Area"),
            (a, "trekking", "theme", "Trekking"),
            (b, "lodge", "place_type", "Lodge"),
        ]
    )

    labels = pc._category_labels_by_location(db, [a, b])

    assert [(label.kind, label.display_name) for label in labels[a]] == [
        ("place_type", "Area"),
        ("theme", "Trekking"),
    ]
    assert [label.display_name for label in labels[b]] == ["Lodge"]


def test_category_labels_empty_ids_skip_the_query():
    class _NoQuery:
        def execute(self, _stmt):
            raise AssertionError("no query expected")

    assert pc._category_labels_by_location(_NoQuery(), []) == {}
