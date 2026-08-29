"""Reward points (Step 18): resolving what a contribution is worth, awarding
it exactly once, and reporting a guide's totals.

Two rules govern everything in this module:

1. THE BACKEND DECIDES WHAT THINGS ARE WORTH. Point values come from the
   reward_rules table, never from a constant here and never from the mobile
   app. The app is told the number and displays it.

2. AN AWARD HAPPENS AT MOST ONCE PER REAL-WORLD ACTION. Enforced by the
   UNIQUE constraint on reward_ledger.idempotency_key, not by a "have we
   already awarded this?" SELECT -- a check-then-insert would still race two
   concurrent syncs of the same offline answer. See `award` below.
"""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.question_answer import QuestionAnswer
from app.db.models.reward import RewardLedger, RewardRule
from app.db.models.submission import Submission
from app.schemas.reward import (
    GuideRewardSummary,
    RewardConversion,
    RewardLedgerEntry,
    RewardRuleRead,
)

logger = logging.getLogger(__name__)


def get_rule(db: Session, rule_key: str) -> RewardRule | None:
    """The ACTIVE rule for this key, or None. An inactive/absent rule means
    'this action currently earns nothing' -- callers must treat that as a
    legitimate outcome and award nothing, never fall back to a hardcoded
    default (which would let the app pay out a number no operator configured)."""
    stmt = select(RewardRule).where(
        RewardRule.rule_key == rule_key, RewardRule.active.is_(True)
    )
    return db.execute(stmt).scalar_one_or_none()


def resolve_points(db: Session, rule_key: str) -> int:
    """Points for a rule key, or 0 when no active rule exists."""
    rule = get_rule(db, rule_key)
    return rule.points if rule is not None else 0


# The generic rate, used when a kind has no rule of its own.
PLACE_QUESTION_FALLBACK_RULE_KEY = "place_question_answer"


def place_question_rule_key(db: Session, contribution_kind: str | None) -> str:
    """The rule key a place-question contribution of this kind is paid under.

    Per-kind rates exist because the kinds differ in real effort -- taking and
    describing a photo is more work than confirming a tea stall is open. Falls
    back to the generic rate when a kind has no active rule yet, so adding a new
    contribution kind cannot silently pay zero: it pays the configured generic
    rate until an operator seeds a rate for it.
    """
    if contribution_kind:
        specific = f"place_question_{contribution_kind}"
        if get_rule(db, specific) is not None:
            return specific
    return PLACE_QUESTION_FALLBACK_RULE_KEY


def resolve_place_question_points(db: Session, contribution_kind: str | None) -> int:
    """What a place-question contribution of this kind is currently worth."""
    return resolve_points(db, place_question_rule_key(db, contribution_kind))


def list_rules(db: Session) -> list[RewardRuleRead]:
    stmt = select(RewardRule).where(RewardRule.active.is_(True)).order_by(RewardRule.points.desc())
    return [
        RewardRuleRead(
            rule_key=r.rule_key,
            points=r.points,
            description=r.description,
        )
        for r in db.execute(stmt).scalars().all()
    ]


def get_conversion() -> RewardConversion:
    return RewardConversion(
        points_per_currency_unit=settings.reward_points_per_currency_unit,
        currency_code=settings.reward_currency_code,
        currency_symbol=settings.reward_currency_symbol,
    )


def award(
    db: Session,
    guide_id: UUID,
    rule_key: str,
    idempotency_key: str,
    source_type: str,
    source_id: UUID | None = None,
) -> int:
    """Records a reward, exactly once. Returns the points actually awarded by
    THIS call -- 0 if the rule is inactive/absent, or if this idempotency_key
    was already awarded.

    Does NOT commit: the caller is expected to be inside the same transaction
    that persists the answer/submission being rewarded, so "the contribution
    was saved" and "the guide was paid for it" commit together or not at all.
    There is deliberately no path that awards points for something that was
    never stored.

    Idempotency is the DB's UNIQUE constraint via ON CONFLICT DO NOTHING, not
    an application-level pre-check. That matters for the offline flow: two
    concurrent syncs of the same queued answer both miss a SELECT, but only one
    INSERT can win -- the loser silently no-ops instead of double-paying.

    `idempotency_key` must be the stable client-generated id of the action
    being rewarded (client_answer_id / client_submission_id), never a freshly
    generated value -- a new uuid here would defeat the entire mechanism.
    """
    rule = get_rule(db, rule_key)
    if rule is None:
        # Not an error: an operator can legitimately deactivate a rule. Logged
        # because a MISSING (never-seeded) rule is worth noticing.
        logger.info("No active reward rule for %r -- awarding nothing.", rule_key)
        return 0

    stmt = (
        pg_insert(RewardLedger)
        .values(
            guide_id=guide_id,
            points=rule.points,
            rule_key=rule.rule_key,
            idempotency_key=idempotency_key,
            source_type=source_type,
            source_id=source_id,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(RewardLedger.id)
    )
    inserted = db.execute(stmt).scalar_one_or_none()
    if inserted is None:
        # Already awarded for this exact action -- an idempotent replay of a
        # retried sync. Correct and expected, not a failure.
        return 0
    return rule.points


def get_guide_rewards(db: Session, guide_id: UUID, recent_limit: int = 20) -> GuideRewardSummary:
    """A guide's authoritative reward state. Every number is computed from the
    ledger at request time -- there is no cached balance column to drift."""
    totals = db.execute(
        select(
            func.coalesce(func.sum(RewardLedger.points), 0),
            func.count(RewardLedger.id),
        ).where(RewardLedger.guide_id == guide_id)
    ).one()
    total_points, total_awards = int(totals[0]), int(totals[1])

    questions_answered = db.execute(
        select(func.count(QuestionAnswer.id)).where(QuestionAnswer.guide_id == guide_id)
    ).scalar_one()

    # Every submission this guide has made, of any type. Counted from the
    # submissions table rather than the ledger so contributions made before
    # rewards existed (or under a now-inactive rule) still count -- they were
    # real work regardless of whether they happened to earn points.
    contributions_count = db.execute(
        select(func.count(Submission.id)).where(Submission.guide_id == guide_id)
    ).scalar_one()

    recent_stmt = (
        select(RewardLedger)
        .where(RewardLedger.guide_id == guide_id)
        .order_by(RewardLedger.awarded_at.desc())
        .limit(recent_limit)
    )
    recent = [
        RewardLedgerEntry(
            points=e.points,
            rule_key=e.rule_key,
            source_type=e.source_type,
            awarded_at=e.awarded_at,
        )
        for e in db.execute(recent_stmt).scalars().all()
    ]

    return GuideRewardSummary(
        guide_id=guide_id,
        # current_points equals total_points because nothing spends points yet
        # -- no redemption/payout mechanism exists in this system. Kept as two
        # distinct fields so that when redemption does arrive, the app already
        # renders the right one and this becomes a backend-only change.
        current_points=total_points,
        total_points_earned=total_points,
        total_awards=total_awards,
        questions_answered=int(questions_answered),
        contributions_count=int(contributions_count),
        conversion=get_conversion(),
        recent=recent,
    )
