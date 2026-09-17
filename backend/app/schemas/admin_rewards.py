"""Admin-only request/response shapes for managing reward_rules -- separate
from app/schemas/reward.py (RewardRuleRead etc.), which is the guide-facing
shape returned by the public GET /api/v1/rewards/config endpoint and
deliberately exposes no id/active/timestamps. These schemas are for the
admin CRUD surface only (see app/services/admin_rewards.py), which needs the
full row -- including inactive rules, which the guide-facing endpoint never
returns.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RewardRuleAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_key: str
    points: int
    description: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class RewardRuleCreateRequest(BaseModel):
    # Lowercase snake_case, matching every rule_key already seeded (see
    # app/db/models/reward.py's REWARD_RULE_KEYS) -- award()/get_rule() match
    # this string exactly against whatever a call site passes, so a stray
    # space or a different case would silently create a rule nothing ever
    # resolves to.
    rule_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    points: int = Field(ge=0)
    description: str | None = Field(default=None, max_length=2000)
    active: bool = True


class RewardRuleUpdateRequest(BaseModel):
    """Partial update -- only fields the admin actually changed are sent.
    Points cannot be negative; rule_key is intentionally NOT editable here
    (see admin_rewards.update_rule's docstring for why renaming a live key
    is refused rather than silently breaking every call site that resolves
    against the old one)."""

    points: int | None = Field(default=None, ge=0)
    description: str | None = None
    active: bool | None = None


class RewardRuleChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_id: UUID
    rule_key: str
    previous_points: int | None
    new_points: int
    changed_by: str
    changed_at: datetime
