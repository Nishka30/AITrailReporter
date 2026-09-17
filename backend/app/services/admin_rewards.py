"""Admin management of reward_rules -- the missing piece on top of the
already-existing, already-data-driven reward system (see
app/db/models/reward.py and app/services/rewards.py). Nothing here is a
second reward mechanism: every rule this module creates/edits is read by the
SAME reward_service.get_rule()/award() call sites that already resolve
reward_rules live, and by the SAME public GET /api/v1/rewards/config the
mobile app already polls -- an admin changing a rule here takes effect for
both, immediately, with no separate config to keep in sync.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.reward import RewardRule, RewardRuleChange


class RewardRuleNotFoundError(Exception):
    def __init__(self, rule_id: UUID):
        self.rule_id = rule_id
        super().__init__(f"No reward rule exists with id {rule_id}")


class DuplicateRuleKeyError(Exception):
    """Raised when a rule_key collides with one that already exists (active
    or not) -- rule_key is the stable identifier every award() call site
    resolves against, so it must stay unique regardless of active status."""

    def __init__(self, rule_key: str):
        self.rule_key = rule_key
        super().__init__(f"A reward rule with key {rule_key!r} already exists")


def list_all_rules(db: Session, q: str | None = None) -> list[RewardRule]:
    """Every rule, active or not -- unlike reward_service.list_rules(), which
    the guide-facing endpoint uses and deliberately only returns active ones.
    An admin managing rates needs to see (and reactivate) inactive rules
    too."""
    stmt = select(RewardRule).order_by(RewardRule.rule_key)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            RewardRule.rule_key.ilike(like) | RewardRule.description.ilike(like)
        )
    return list(db.execute(stmt).scalars().all())


def get_rule_or_404(db: Session, rule_id: UUID) -> RewardRule:
    rule = db.get(RewardRule, rule_id)
    if rule is None:
        raise RewardRuleNotFoundError(rule_id)
    return rule


def create_rule(
    db: Session,
    *,
    changed_by: str,
    rule_key: str,
    points: int,
    description: str | None,
    active: bool,
) -> RewardRule:
    rule = RewardRule(rule_key=rule_key, points=points, description=description, active=active)
    db.add(rule)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DuplicateRuleKeyError(rule_key)

    db.add(
        RewardRuleChange(
            rule_id=rule.id,
            rule_key=rule.rule_key,
            previous_points=None,
            new_points=points,
            changed_by=changed_by,
        )
    )
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(
    db: Session,
    rule_id: UUID,
    *,
    changed_by: str,
    points: int | None,
    description: str | None,
    active: bool | None,
    description_set: bool,
) -> RewardRule:
    """Partial update. `description_set` distinguishes "the admin explicitly
    cleared the description" (description=None, description_set=True) from
    "the admin didn't touch this field" (description_set=False) -- a plain
    Optional field can't tell those apart on its own.

    Deliberately does not allow changing rule_key: every award() call site
    resolves a LITERAL string baked into backend code (see
    app/services/rewards.py's call sites) or a frozen
    SubmissionReview.reward_rule_key. Renaming the key here would silently
    orphan whichever of those a live deploy still references -- there is no
    safe way to do it without also auditing/updating every caller, which is
    a backend code change, not an admin-panel action.
    """
    rule = get_rule_or_404(db, rule_id)

    previous_points = rule.points
    points_changed = points is not None and points != previous_points

    if points is not None:
        rule.points = points
    if description_set:
        rule.description = description
    if active is not None:
        rule.active = active

    if points_changed:
        db.add(
            RewardRuleChange(
                rule_id=rule.id,
                rule_key=rule.rule_key,
                previous_points=previous_points,
                new_points=rule.points,
                changed_by=changed_by,
            )
        )

    db.commit()
    db.refresh(rule)
    return rule


def list_rule_changes(db: Session, rule_id: UUID) -> list[RewardRuleChange]:
    stmt = (
        select(RewardRuleChange)
        .where(RewardRuleChange.rule_id == rule_id)
        .order_by(RewardRuleChange.changed_at.desc())
    )
    return list(db.execute(stmt).scalars().all())
