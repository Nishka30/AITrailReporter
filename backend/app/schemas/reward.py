"""Reward response shapes (Step 18). Nothing here exposes the ledger's
internal ids or idempotency keys -- the app needs totals, the conversion, and
enough recent history to show what was earned, not the plumbing."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RewardConversion(BaseModel):
    """How points map to money. Sent to the app so the conversion is stated by
    the BACKEND and can change without an app release. There is no payout
    mechanism in this system -- this drives an approximate-value display only.
    """

    points_per_currency_unit: int
    currency_code: str
    currency_symbol: str


class RewardRuleRead(BaseModel):
    """One way to earn points. The app renders its "how you earn" list from
    these, so what it advertises can never drift from what the backend
    actually awards."""

    rule_key: str
    points: int
    description: str | None


class RewardConfig(BaseModel):
    rules: list[RewardRuleRead]
    conversion: RewardConversion


class RewardLedgerEntry(BaseModel):
    points: int
    rule_key: str
    source_type: str
    awarded_at: datetime


class GuideRewardSummary(BaseModel):
    guide_id: UUID
    # Equal to total_points_earned until a redemption mechanism exists; kept
    # separate so adding one later is a backend-only change.
    current_points: int
    total_points_earned: int
    total_awards: int
    questions_answered: int
    # Everything this guide has actually contributed: notes, voice reports,
    # Explore discoveries and question answers -- i.e. one per Submission row.
    # Deliberately NOT total_awards: a contribution made before rewards existed,
    # or one whose rule is currently inactive, is still a real contribution and
    # should be counted as one. Counting ledger rows instead would silently
    # under-report the guide's actual work.
    contributions_count: int
    conversion: RewardConversion
    recent: list[RewardLedgerEntry]
