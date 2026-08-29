"""Reward configuration and per-guide totals (Step 18)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.reward import RewardConfig
from app.services import rewards as reward_service

router = APIRouter(prefix="/api/v1/rewards", tags=["rewards"])


@router.get("/config", response_model=RewardConfig)
def get_reward_config(db: Session = Depends(get_db)):
    """Every active earning rule plus the points->money conversion.

    The mobile app reads this to label its Explore prompt cards and to render
    the Rewards screen's "how you earn" list. Because both come from the same
    rows the award path resolves against, what the app advertises can never
    drift from what the backend actually pays -- which is the reason the app
    holds no reward amounts of its own.
    """
    return RewardConfig(
        rules=reward_service.list_rules(db),
        conversion=reward_service.get_conversion(),
    )
