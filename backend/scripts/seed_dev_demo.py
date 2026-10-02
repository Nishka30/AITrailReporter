"""DEV-ONLY demo content for designing the Travelers website against the real
public API. Refuses to run unless APP_ENVIRONMENT=development AND the active
database host is localhost -- it can never write to production.

Two parts:
  A) Real geography: the Everest Base Camp villages, via
     scripts/seed_route_villages.py (the production-safe version), marked as
     demo rows so --remove can take them away again.
  B) Demo guide activity: four demo guides, approved observations at Lukla,
     Thamel and the route villages, verified CategoryKnowledge behind the
     category reports, and approved answers to a few curated questions.
     Fictional demo content -- every row is removable with --remove.

    python scripts/seed_dev_demo.py           # seed (idempotent)
    python scripts/seed_dev_demo.py --remove  # delete exactly what it created
"""

import argparse
import logging
import pathlib
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.geo import make_point
from app.db.models.category_knowledge import CategoryKnowledge
from app.db.models.guide import Guide
from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.db.models.location import Location
from app.db.models.location_category import LocationCategory, LocationCategoryAssignment
from app.db.models.observation import Observation
from app.db.models.observation_moderation import ObservationModeration
from app.db.models.place_question import PlaceQuestion
from app.db.models.submission import Submission
from app.db.models.submission_review import SubmissionReview
from app.db.session import SessionLocal
from app.services import rewards as reward_service

import seed_route_villages  # noqa: E402  (scripts/ is on sys.path when run directly)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed_dev_demo")

DEMO_PROVIDER = "dev_demo"
DEMO_PHONE_PREFIX = "+000-DEMO-"
DEMO_CLIENT_PREFIX = "dev-demo-"
DEMO_DECIDER = "seed_dev_demo"


def _assert_dev_database() -> None:
    host = urlsplit(settings.database_url.replace("+psycopg", "")).hostname
    if settings.app_environment != "development" or host not in {"localhost", "127.0.0.1"}:
        raise SystemExit(
            f"Refusing to run: app_environment={settings.app_environment!r}, database host={host!r}. "
            "This script only writes to a local development database."
        )
    logger.info("Target database host: %s (development)", host)


# ---------------------------------------------------------------------------
# A) Real geography
# ---------------------------------------------------------------------------


def _category(db: Session, slug: str, kind: str) -> LocationCategory:
    category = db.execute(
        select(LocationCategory).where(LocationCategory.slug == slug, LocationCategory.kind == kind)
    ).scalars().first()
    if category is None:
        raise SystemExit(f"Catalog category {slug!r} ({kind}) not found")
    return category


def _assign(db: Session, location: Location, slug: str, kind: str, relevance: int, primary: bool) -> LocationCategoryAssignment:
    category = _category(db, slug, kind)
    existing = db.execute(
        select(LocationCategoryAssignment).where(
            LocationCategoryAssignment.location_id == location.id,
            LocationCategoryAssignment.category_id == category.id,
        )
    ).scalars().first()
    if existing is not None:
        return existing
    assignment = LocationCategoryAssignment(
        location_id=location.id,
        category_id=category.id,
        kind=kind,
        relevance=relevance,
        confidence=0.9,
        is_primary=primary,
        source="manual",
        rationale="dev demo seed",
    )
    db.add(assignment)
    db.flush()
    return assignment


def seed_villages(db: Session) -> None:
    # Same real villages as the production-safe script, marked as demo rows
    # here so --remove takes them away again.
    seed_route_villages.seed_villages(db, provider=DEMO_PROVIDER, rationale="dev demo seed")


# ---------------------------------------------------------------------------
# B) Demo guide activity
# ---------------------------------------------------------------------------

GUIDES = ("Pemba Sherpa", "Mingma Sherpa", "Lakpa Sherpa", "Dawa Sherpa")


@dataclass(frozen=True)
class _Report:
    key: str
    place: str
    guide: str
    hours_ago: float
    evidence: str
    label: str | None = None
    knowledge_type: str | None = None
    value: dict = field(default_factory=dict)
    # Category report: (category slug, verified knowledge text, volatility hours)
    category: tuple[str, str, int] | None = None


REPORTS = (
    _Report("lukla-airport-flights", "Tenzing-Hillary Airport (Lukla Airport)", "Pemba Sherpa", 26,
            "Morning flights landed and left from 06:40. Cloud moved in after 10:00 and the later flights were held for the rest of the morning.",
            label="Lukla Airport",
            category=("transport", "Flights run in the early morning; later departures are often held once cloud builds in the valley.", 168),
            value={"status": "operating_morning_only"}),
    _Report("lukla-airport-weather", "Tenzing-Hillary Airport (Lukla Airport)", "Pemba Sherpa", 5,
            "Clear at first light, cloud filling the valley from the south by mid-morning.",
            label="Lukla Airport", knowledge_type="weather", value={"condition": "cloud_building", "temperature_c": 9}),
    _Report("lukla-lodging-rooms", "Lukla", "Mingma Sherpa", 30,
            "Two lodges near the main street had rooms for the same night. Neither held a room for a later arrival.",
            label="Lukla main street",
            category=("lodging", "Main-street lodges had rooms for same-night arrivals at the last check.", 168),
            value={"availability": "rooms_available"}),
    _Report("lukla-lodging-extras", "Lukla", "Lakpa Sherpa", 74,
            "One lodge charged NPR 500 for a hot shower and NPR 300 to charge a phone. Wi-Fi speed was not tested.",
            label="Lukla lodge area",
            category=("lodging", "One main-street lodge charged NPR 500 for a hot shower and NPR 300 per phone charge.", 168),
            value={"hot_shower_npr": 500, "phone_charge_npr": 300}),
    _Report("lukla-trail", "Lukla", "Lakpa Sherpa", 50,
            "The stone-paved main street is dry. The path down toward Chaurikharka is muddy for the first stretch after the gate.",
            label="Pasang Lhamu Gate", knowledge_type="trail_condition", value={"condition": "muddy_in_places", "surface": "stone"}),
    _Report("lukla-signal", "Lukla", "Dawa Sherpa", 98,
            "Ncell 4G worked along the main street; it dropped to one bar beyond Pasang Lhamu Gate.",
            label="Lukla main street", knowledge_type="mobile_signal", value={"carrier": "Ncell", "strength": "good"}),
    _Report("lukla-gompa", "Lukla Gompa", "Mingma Sherpa", 140,
            "The courtyard was open in the afternoon. A caretaker asked visitors to walk clockwise and not to photograph inside the prayer hall.",
            category=("culture_heritage", "Courtyard open to visitors in the afternoon; no photography inside the prayer hall.", 1080),
            value={"open": True}),
    _Report("lukla-gate", "Pasang Lhamu Gate", "Dawa Sherpa", 22,
            "The gate is where most groups meet before walking out of town. It was busiest between 07:00 and 08:30.",
            category=("culture_heritage", "The usual meeting point for groups leaving Lukla; busiest 07:00–08:30.", 168),
            value={"busy_hours": "07:00-08:30"}),
    _Report("buddha-lodge", "Buddha Lodge", "Mingma Sherpa", 215,
            "The dining room was heated in the evening. Rooms with an attached bathroom were available.",
            category=("lodging", "Heated dining room in the evening; rooms with attached bathroom available.", 168),
            value={"availability": "rooms_available"}),
    _Report("hikers-inn", "Hikers Inn Lukla", "Lakpa Sherpa", 290,
            "Charging was only possible in the dining room, NPR 300 per device.",
            category=("lodging", "Charging in the dining room only, NPR 300 per device.", 168),
            value={"phone_charge_npr": 300}),
    _Report("phakding-trail", "Phakding", "Lakpa Sherpa", 20,
            "The trail along the Dudh Koshi is dry. The suspension bridges were busy with porter traffic mid-morning, so we waited for gaps.",
            knowledge_type="trail_condition", value={"condition": "dry", "surface": "dirt"}),
    _Report("phakding-lodge", "Phakding", "Lakpa Sherpa", 52,
            "Riverside lodges had rooms. One lodge offered boiled-water refills at NPR 150 a litre.",
            category=("lodging", "Riverside lodges had rooms; boiled-water refills NPR 150 a litre at one lodge.", 168),
            value={"water_refill_npr": 150}),
    _Report("namche-weather", "Namche Bazaar", "Dawa Sherpa", 8,
            "Clear morning with views toward Thamserku. A cold wind came up the valley after 15:00.",
            knowledge_type="weather", value={"condition": "clear", "temperature_c": 6}),
    _Report("namche-wifi", "Namche Bazaar", "Lakpa Sherpa", 96,
            "Two lodges sold 24-hour Wi-Fi cards for NPR 600. The connection speed was not tested.",
            category=("lodging", "24-hour Wi-Fi cards sold at two lodges for NPR 600 (speed not tested).", 168),
            value={"wifi_card_npr": 600}),
    _Report("namche-trail", "Namche Bazaar", "Pemba Sherpa", 70,
            "The climb up from the Hillary Bridge is dry and dusty, with little shade after 10:00.",
            knowledge_type="trail_condition", value={"condition": "dry", "surface": "dirt"}),
    _Report("tengboche-monastery", "Tengboche", "Mingma Sherpa", 210,
            "An attendant said the afternoon ceremony was expected at 15:00. We did not attend; confirm visiting times when you arrive.",
            category=("culture_heritage", "Afternoon ceremony expected around 15:00 at the last check; confirm on arrival.", 168),
            value={"ceremony_time": "15:00"}),
    _Report("tengboche-snow", "Tengboche", "Mingma Sherpa", 46,
            "Light snow overnight. It had melted off the trail by 09:00.",
            knowledge_type="snow_ice", value={"condition": "light_snow", "extent": "melted_by_morning"}),
    _Report("dingboche-water", "Dingboche", "Pemba Sherpa", 118,
            "Lodges were selling boiled water. The stream beside the trail is untreated.",
            knowledge_type="water_source", value={"type": "lodge_boiled", "potable": True}),
    _Report("dingboche-frost", "Dingboche", "Pemba Sherpa", 290,
            "Frost on the path above the village before 08:00, gone by mid-morning.",
            knowledge_type="snow_ice", value={"condition": "frost", "extent": "early_morning"}),
    _Report("lobuche-prices", "Lobuche", "Mingma Sherpa", 150,
            "One lodge quoted NPR 400 for a litre of hot water and NPR 500 to charge a phone.",
            category=("lodging", "One lodge quoted NPR 400 per litre of hot water and NPR 500 per phone charge.", 168),
            value={"hot_water_npr": 400, "phone_charge_npr": 500}),
    _Report("lobuche-trail", "Lobuche", "Dawa Sherpa", 28,
            "The moraine section toward Gorak Shep is loose underfoot and slow with a pack.",
            knowledge_type="trail_condition", value={"condition": "loose", "surface": "moraine"}),
    _Report("gorakshep-lodges", "Gorak Shep", "Dawa Sherpa", 14,
            "All four lodges I visited had rooms available that afternoon. Availability changes quickly as groups arrive.",
            category=("lodging", "All four lodges visited had rooms that afternoon.", 168),
            value={"availability": "rooms_available"}),
    _Report("ebc-day", "Everest Base Camp", "Dawa Sherpa", 26,
            "Lobuche to Gorak Shep, on to Base Camp and back to Gorak Shep took our group 7 h 40 min including lunch and rests.",
            knowledge_type="trail_condition", value={"condition": "dry", "surface": "glacier_moraine"}),
    _Report("ebc-weather", "Everest Base Camp", "Dawa Sherpa", 25,
            "Clear until noon. Cloud and wind came over the glacier by 13:00.",
            knowledge_type="weather", value={"condition": "cloud_afternoon", "temperature_c": -4}),
    _Report("thamel-gear", "Thamel", "Mingma Sherpa", 54,
            "Gear shops on the main lane were open by 10:00. Two quoted NPR 150–200 a day to rent poles, plus a refundable deposit.",
            label="Thamel main lane",
            category=("trekking", "Gear shops rent trekking poles for NPR 150–200 a day plus a refundable deposit.", 168),
            value={"pole_rental_npr_per_day": "150-200"}),
    _Report("durbar-square", "Kathmandu Durbar Square", "Lakpa Sherpa", 78,
            "The ticket counter at the south entrance was open. Foreign visitors need a ticket to enter.",
            category=("culture_heritage", "Foreign visitors need a ticket, sold at the south entrance.", 1080),
            value={"ticket_required": True}),
    _Report("fire-and-ice", "Fire And Ice Pizzeria", "Lakpa Sherpa", 120,
            "Open for lunch from 11:00. By 19:00 there was a short wait for a table.",
            category=("food_drink", "Open from 11:00; a short wait for a table by 19:00.", 168),
            value={"opens": "11:00"}),
)


ANSWERS = (
    ("Lukla", "Where can a visitor buy or rent trekking poles?", "Mingma Sherpa", 60,
     "At one gear shop on the main street, poles were for sale and for rent. Sizes and condition weren't checked."),
    ("Lukla", "What is the best place for guests to wait during a long flight delay?", "Pemba Sherpa", 27,
     "During a weather hold, groups waited in lodge dining rooms near the airport gate rather than in the terminal. Ask your lodge whether you can stay seated there."),
    ("Lukla", "Where can trekkers get laundry done or take a hot shower in Lukla?", "Lakpa Sherpa", 75,
     "One main-street lodge offered hot showers for NPR 500. Laundry wasn't asked about."),
    ("Lukla", "Which ATM in Lukla works most reliably with international cards?", "Lakpa Sherpa", 330,
     "On one attempt the main-street ATM did not complete a withdrawal with a foreign card. Bring enough cash from Kathmandu."),
    ("Thamel", "Can trekking poles be rented in Kathmandu? Find a shop and record the daily rate and deposit.", "Mingma Sherpa", 55,
     "Yes — two shops on the main Thamel lane quoted NPR 150–200 a day plus a refundable deposit."),
    ("Thamel", "Where can tourists buy water-purification tablets or a filter?", "Lakpa Sherpa", 80,
     "Gear shops near Thamel Chowk stocked purification tablets, and one had a filter bottle. Prices weren't compared."),
)


def _location(db: Session, name: str) -> Location:
    location = db.execute(select(Location).where(Location.name == name).order_by(Location.created_at)).scalars().first()
    if location is None:
        raise SystemExit(f"Location {name!r} not found")
    return location


def _guides(db: Session) -> dict[str, Guide]:
    guides = {}
    for i, name in enumerate(GUIDES):
        phone = f"{DEMO_PHONE_PREFIX}{i + 1:02d}"
        guide = db.execute(select(Guide).where(Guide.phone_number == phone)).scalars().first()
        if guide is None:
            guide = Guide(name=name, phone_number=phone, client_guide_id=f"{DEMO_CLIENT_PREFIX}guide-{i + 1}")
            db.add(guide)
            db.flush()
        guides[name] = guide
    return guides


def _jitter(location: Location, key: str) -> tuple[float, float]:
    h = uuid.uuid5(uuid.NAMESPACE_URL, key).int
    return (
        float(location.latitude) + ((h % 200) - 100) * 0.0000015,
        float(location.longitude) + (((h >> 8) % 200) - 100) * 0.0000015,
    )


def seed_reports(db: Session, now: datetime) -> None:
    guides = _guides(db)
    knowledge_types = {k.knowledge_type: k for k in db.execute(select(KnowledgeTypeConfig)).scalars()}
    for report in REPORTS:
        client_id = f"{DEMO_CLIENT_PREFIX}{report.key}"
        if db.execute(select(Submission.id).where(Submission.client_submission_id == client_id)).first():
            continue
        location = _location(db, report.place)
        guide = guides[report.guide]
        observed_at = now - timedelta(hours=report.hours_ago)
        lat, lon = _jitter(location, report.key)
        submission = Submission(
            guide_id=guide.id,
            client_submission_id=client_id,
            latitude=lat,
            longitude=lon,
            location_source="gps_live",
            location_label=report.label or location.name,
            occurred_at=observed_at,
            occurred_at_precision="exact",
            date_source="device",
            submitted_at=observed_at + timedelta(minutes=20),
            submission_type="note",
            raw_text=report.evidence,
            status="received",
        )
        db.add(submission)
        db.flush()

        category_knowledge_id = None
        knowledge_type_id = None
        if report.category is not None:
            slug, text, freshness_hours = report.category
            assignment = db.execute(
                select(LocationCategoryAssignment)
                .join(LocationCategory, LocationCategory.id == LocationCategoryAssignment.category_id)
                .where(
                    LocationCategoryAssignment.location_id == location.id,
                    LocationCategory.slug == slug,
                    LocationCategory.kind == "theme",
                )
            ).scalars().first()
            if assignment is None:
                assignment = _assign(db, location, slug, "theme", 70, False)
            knowledge = CategoryKnowledge(
                location_id=location.id,
                category_assignment_id=assignment.id,
                knowledge_text=text,
                volatility="HIGH" if freshness_hours <= 168 else "MEDIUM",
                freshness_duration_hours=freshness_hours,
                last_verified_at=observed_at,
                source="seed",
                active=True,
            )
            db.add(knowledge)
            db.flush()
            category_knowledge_id = knowledge.id
        else:
            knowledge_type_id = knowledge_types[report.knowledge_type].id

        observation = Observation(
            submission_id=submission.id,
            guide_id=guide.id,
            knowledge_type_id=knowledge_type_id,
            category_knowledge_id=category_knowledge_id,
            latitude=lat,
            longitude=lon,
            geog=make_point(lat, lon),
            location_source="gps_live",
            value=report.value,
            confidence=0.9,
            evidence=report.evidence,
            observed_at=observed_at,
        )
        db.add(observation)
        db.flush()
        db.add(
            ObservationModeration(
                observation_id=observation.id, status="approved", decided_by=DEMO_DECIDER, decided_at=observed_at + timedelta(hours=2)
            )
        )
    logger.info("Reports: %d defined", len(REPORTS))


def seed_answers(db: Session, now: datetime) -> None:
    guides = _guides(db)
    for hub_name, question_text, guide_name, hours_ago, answer in ANSWERS:
        hub = _location(db, hub_name)
        question = db.execute(
            select(PlaceQuestion).where(PlaceQuestion.location_id == hub.id, PlaceQuestion.question_text == question_text)
        ).scalars().first()
        if question is None:
            logger.warning("  question not found at %s: %s", hub_name, question_text)
            continue
        client_id = f"{DEMO_CLIENT_PREFIX}answer-{question.id}"
        if db.execute(select(Submission.id).where(Submission.client_submission_id == client_id)).first():
            continue
        guide = guides[guide_name]
        answered_at = now - timedelta(hours=hours_ago)
        submission = Submission(
            guide_id=guide.id,
            source_place_question_id=question.id,
            client_submission_id=client_id,
            latitude=float(hub.latitude),
            longitude=float(hub.longitude),
            location_source="gps_live",
            location_label=hub.name,
            occurred_at=answered_at,
            occurred_at_precision="exact",
            date_source="device",
            submitted_at=answered_at,
            submission_type="answer",
            raw_text=answer,
            status="received",
        )
        db.add(submission)
        db.flush()
        db.add(
            SubmissionReview(
                submission_id=submission.id,
                guide_id=guide.id,
                status="approved",
                decided_by=DEMO_DECIDER,
                decided_at=answered_at + timedelta(hours=3),
                reward_rule_key=reward_service.place_question_rule_key(db, question.contribution_kind),
                reward_idempotency_key=client_id,
                reward_source_type="place_question_answer",
                reward_source_id=submission.id,
            )
        )
    logger.info("Answers: %d defined", len(ANSWERS))


# ---------------------------------------------------------------------------
# Removal
# ---------------------------------------------------------------------------


def remove(db: Session) -> None:
    guide_ids = list(db.execute(select(Guide.id).where(Guide.phone_number.like(f"{DEMO_PHONE_PREFIX}%"))).scalars())
    knowledge_ids = list(
        db.execute(
            select(Observation.category_knowledge_id).where(
                Observation.guide_id.in_(guide_ids), Observation.category_knowledge_id.isnot(None)
            )
        ).scalars()
    )
    # Guides cascade to submissions, observations, moderation and reviews.
    db.execute(delete(Guide).where(Guide.id.in_(guide_ids)))
    db.execute(delete(CategoryKnowledge).where(CategoryKnowledge.id.in_(knowledge_ids)))
    demo_locations = list(db.execute(select(Location.id).where(Location.provider == DEMO_PROVIDER)).scalars())
    db.execute(delete(CategoryKnowledge).where(CategoryKnowledge.location_id.in_(demo_locations)))
    db.execute(delete(LocationCategoryAssignment).where(LocationCategoryAssignment.location_id.in_(demo_locations)))
    db.execute(delete(Location).where(Location.id.in_(demo_locations)))
    db.execute(delete(LocationCategoryAssignment).where(LocationCategoryAssignment.rationale == "dev demo seed"))
    logger.info(
        "Removed %d guides, %d knowledge items, %d locations", len(guide_ids), len(knowledge_ids), len(demo_locations)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    _assert_dev_database()

    db = SessionLocal()
    try:
        if args.remove:
            remove(db)
        else:
            now = datetime.now(timezone.utc)
            seed_villages(db)
            seed_reports(db, now)
            seed_answers(db, now)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
