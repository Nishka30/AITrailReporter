"""Admin API namespace (Content Curation & Moderation layer). Every route
here requires the minimal dev-safe admin token (see app/core/admin_auth.py).
This is additive to the existing API surface -- nothing here modifies or
depends on mobile-facing routes, and nothing here creates a second knowledge
database: every read goes through the existing PostgreSQL tables via
SQLAlchemy, joined explicitly in app/services/admin_*.py, the same way every
other service in this codebase works.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPrincipal, require_admin
from app.db.session import get_db
from app.schemas.admin import (
    AdminOverview,
    AdminQuestionQueueResult,
    ContributionDetail,
    ContributionQueueResult,
    ContributorDetail,
    ContributorQueueResult,
    PlaceCategoryGroup,
    PlaceDetail,
    PlaceQueueResult,
    ReviewDetail,
    ReviewQueueResult,
)
from app.schemas.admin_rewards import (
    RewardRuleAdminRead,
    RewardRuleChangeRead,
    RewardRuleCreateRequest,
    RewardRuleUpdateRequest,
)
from app.schemas.observation_moderation import (
    ChangeModerationDecisionRequest,
    ObservationModerationRead,
    RejectObservationRequest,
)
from app.schemas.submission_review import RejectSubmissionRequest, SubmissionReviewRead
from app.services import admin_contributors as contributor_service
from app.services import admin_overview as overview_service
from app.services import admin_places as place_service
from app.services import admin_questions as question_service
from app.services import admin_review as review_service
from app.services import admin_rewards as admin_reward_service
from app.services import admin_submission_reviews as contribution_service
from app.services import observation_moderation as moderation_service
from app.services import submission_review as submission_review_service
from app.services import submissions as submission_service
from app.services.storage import get_audio_storage, get_photo_storage

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/auth/verify")
def verify_admin_token(admin: AdminPrincipal = Depends(require_admin)):
    """Used by the admin frontend's login screen to check a token before
    storing it -- performs no side effect beyond the auth check itself."""
    return {"ok": True, "name": admin.name}


@router.get("/overview", response_model=AdminOverview)
def get_overview(
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return overview_service.get_overview(db)


@router.get("/review-queue", response_model=ReviewQueueResult)
def get_review_queue(
    status: str = Query(default="pending_review"),
    knowledge_type: str | None = Query(default=None),
    safety_critical: bool | None = Query(default=None),
    guide_id: UUID | None = Query(default=None),
    place_id: UUID | None = Query(default=None),
    source_type: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=255),
    sort: str = Query(default="created_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = review_service.ReviewQueueFilters(
        status=status or None,
        knowledge_type=knowledge_type,
        safety_critical=safety_critical,
        guide_id=guide_id,
        place_id=place_id,
        source_type=source_type,
        q=q,
        sort=sort,
    )
    return review_service.list_review_queue(db, filters, page, page_size)


@router.get("/knowledge", response_model=ReviewQueueResult)
def get_knowledge(
    status: str | None = Query(default=None),
    knowledge_type: str | None = Query(default=None),
    safety_critical: bool | None = Query(default=None),
    guide_id: UUID | None = Query(default=None),
    place_id: UUID | None = Query(default=None),
    source_type: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=255),
    sort: str = Query(default="observed_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Browses ALL observations regardless of moderation status (unlike
    /review-queue, which defaults to 'pending_review') -- the same knowledge
    a future public app would eventually read a filtered ('approved') slice
    of, see app/services/admin_review.py."""
    filters = review_service.ReviewQueueFilters(
        status=status,
        knowledge_type=knowledge_type,
        safety_critical=safety_critical,
        guide_id=guide_id,
        place_id=place_id,
        source_type=source_type,
        q=q,
        sort=sort,
    )
    return review_service.list_review_queue(db, filters, page, page_size)


@router.get("/reviews/{observation_id}", response_model=ReviewDetail)
@router.get("/knowledge/{observation_id}", response_model=ReviewDetail)
def get_review_detail(
    observation_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    detail = review_service.get_review_detail(db, observation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return detail


@router.post("/reviews/{observation_id}/approve", response_model=ObservationModerationRead)
def approve_observation(
    observation_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return moderation_service.approve(db, observation_id, admin.name)
    except moderation_service.ModerationNotFoundError:
        raise HTTPException(status_code=404, detail="Observation not found")
    except moderation_service.AlreadyDecidedError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "This observation was already rejected. Use "
                "POST /reviews/{observation_id}/change-decision to switch it."
            ),
        )


@router.post("/reviews/{observation_id}/reject", response_model=ObservationModerationRead)
def reject_observation(
    observation_id: UUID,
    payload: RejectObservationRequest,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return moderation_service.reject(
            db, observation_id, admin.name, payload.reason, payload.note
        )
    except moderation_service.ModerationNotFoundError:
        raise HTTPException(status_code=404, detail="Observation not found")
    except moderation_service.AlreadyDecidedError:
        raise HTTPException(
            status_code=409,
            detail=(
                "This observation was already approved. Use "
                "POST /reviews/{observation_id}/change-decision to switch it."
            ),
        )


@router.post("/reviews/{observation_id}/change-decision", response_model=ObservationModerationRead)
def change_observation_decision(
    observation_id: UUID,
    payload: ChangeModerationDecisionRequest,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Explicitly switches an already-decided observation to the opposite
    decision -- a deliberate, separate action from approve/reject (see
    app/services/observation_moderation.py:change_decision)."""
    try:
        return moderation_service.change_decision(
            db, observation_id, admin.name, payload.status, payload.reason, payload.note
        )
    except moderation_service.ModerationNotFoundError:
        raise HTTPException(status_code=404, detail="Observation not found")
    except moderation_service.NotYetDecidedError:
        raise HTTPException(
            status_code=409,
            detail=(
                "This observation has not been decided yet. Use "
                "POST /reviews/{observation_id}/approve or /reject instead."
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/contribution-queue", response_model=ContributionQueueResult)
def get_contribution_queue(
    status: str | None = Query(default="pending_review"),
    guide_id: UUID | None = Query(default=None),
    submission_type: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Contributions awaiting a PAYMENT decision -- deliberately separate from
    /review-queue above, which reviews extracted knowledge for accuracy, not
    contributions for reward eligibility. See
    app/db/models/submission_review.py for why these are two different
    reviews of two different things. Defaults to pending_review; pass
    status='' (empty) to browse all decisions, same convention as /knowledge
    vs /review-queue."""
    filters = contribution_service.ContributionQueueFilters(
        status=status or None,
        guide_id=guide_id,
        submission_type=submission_type,
        q=q,
    )
    return contribution_service.list_contribution_queue(db, filters, page, page_size)


@router.get("/contribution-queue/{submission_id}", response_model=ContributionDetail)
def get_contribution_detail(
    submission_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    detail = contribution_service.get_contribution_detail(db, submission_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Contribution not found")
    return detail


@router.post("/contribution-queue/{submission_id}/approve", response_model=SubmissionReviewRead)
def approve_contribution(
    submission_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Approves a contribution AND pays it, atomically, exactly once -- see
    app/services/submission_review.py:approve. Safe to call repeatedly: a
    retried/duplicate request returns the same approved state with no
    additional reward_ledger row."""
    try:
        review, _points = submission_review_service.approve(db, submission_id, admin.name)
        return review
    except submission_review_service.SubmissionReviewNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="No pending contribution review exists for this submission.",
        )
    except submission_review_service.AlreadyDecidedError:
        raise HTTPException(
            status_code=409,
            detail=(
                "This contribution was already rejected. Rewards cannot be "
                "reversed once a decision has been made."
            ),
        )


@router.post("/contribution-queue/{submission_id}/reject", response_model=SubmissionReviewRead)
def reject_contribution(
    submission_id: UUID,
    payload: RejectSubmissionRequest,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return submission_review_service.reject(
            db, submission_id, admin.name, payload.reason, payload.note
        )
    except submission_review_service.SubmissionReviewNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="No pending contribution review exists for this submission.",
        )
    except submission_review_service.AlreadyDecidedError:
        raise HTTPException(
            status_code=409,
            detail=(
                "This contribution was already approved and paid. Rewards "
                "cannot be reversed once a decision has been made."
            ),
        )


@router.get("/places", response_model=PlaceQueueResult)
def list_places(
    q: str | None = Query(default=None),
    category: str | None = Query(
        default=None, description="Comma-separated place_type slugs, e.g. 'restaurant,cafe'."
    ),
    group: str | None = Query(
        default=None, description="Comma-separated UI group keys, e.g. 'food_drink,shopping'."
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = place_service.PlaceFilters(q=q, category=category, group=group)
    return place_service.list_places(db, filters, page, page_size)


@router.get("/places/categories", response_model=list[PlaceCategoryGroup])
def list_place_categories(
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Grouped, counted place_type filter options for the Places page
    sidebar -- see app/services/places/category_ui_groups.py. Registered
    ABOVE /places/{location_id} so 'categories' is never swallowed as a
    location_id path parameter."""
    return place_service.list_category_filter_options(db)


@router.get("/places/{location_id}", response_model=PlaceDetail)
def get_place(
    location_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    place = place_service.get_place_detail(db, location_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


@router.get("/contributors", response_model=ContributorQueueResult)
def list_contributors(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return contributor_service.list_contributors(db, page, page_size)


@router.get("/contributors/{guide_id}", response_model=ContributorDetail)
def get_contributor(
    guide_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    contributor = contributor_service.get_contributor_detail(db, guide_id)
    if contributor is None:
        raise HTTPException(status_code=404, detail="Contributor not found")
    return contributor


@router.get("/questions", response_model=AdminQuestionQueueResult)
def list_questions(
    status: str | None = Query(default=None),
    assignment_status: str | None = Query(default=None),
    safety_critical: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return question_service.list_admin_questions(
        db, status, assignment_status, safety_critical, page, page_size
    )


@router.get("/submissions/{submission_id}/audio")
def get_submission_audio(
    submission_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Streams a submission's audio evidence for the Review Detail player.
    Never exposes the raw storage_key/path to the client -- read server-side
    through the same MediaStorage abstraction used for upload. Uses
    read_bytes() (not resolve_path()), the interface both the local-
    filesystem AND Supabase Storage backends actually implement -- see
    app/services/storage/base.py."""
    submission = submission_service.get_submission(db, submission_id)
    if submission is None or submission.audio is None:
        raise HTTPException(status_code=404, detail="No audio attached to this submission")
    try:
        content = get_audio_storage().read_bytes(submission.audio_storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio file is missing on the server")
    return Response(content=content, media_type=submission.audio.content_type)


@router.get("/submissions/{submission_id}/photo")
def get_submission_photo(
    submission_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    submission = submission_service.get_submission(db, submission_id)
    if submission is None or submission.photo is None:
        raise HTTPException(status_code=404, detail="No photo attached to this submission")
    try:
        content = get_photo_storage().read_bytes(submission.photo_storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Photo file is missing on the server")
    return Response(content=content, media_type=submission.photo.content_type)


@router.get("/reward-rules", response_model=list[RewardRuleAdminRead])
def list_reward_rules(
    q: str | None = Query(default=None, max_length=255),
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Every reward rule, active or not -- the source of truth this same
    table already feeds to reward_service.award() (what a guide is actually
    paid) and to GET /api/v1/rewards/config (what mobile displays). Editing a
    rule here takes effect for both immediately; there is no separate
    mobile/admin config to keep in sync."""
    return admin_reward_service.list_all_rules(db, q=q)


@router.post("/reward-rules", response_model=RewardRuleAdminRead, status_code=201)
def create_reward_rule(
    payload: RewardRuleCreateRequest,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return admin_reward_service.create_rule(
            db,
            changed_by=admin.name,
            rule_key=payload.rule_key,
            points=payload.points,
            description=payload.description,
            active=payload.active,
        )
    except admin_reward_service.DuplicateRuleKeyError:
        raise HTTPException(
            status_code=409,
            detail=f"A reward rule with key '{payload.rule_key}' already exists.",
        )


@router.patch("/reward-rules/{rule_id}", response_model=RewardRuleAdminRead)
def update_reward_rule(
    rule_id: UUID,
    payload: RewardRuleUpdateRequest,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    fields_set = payload.model_fields_set
    try:
        return admin_reward_service.update_rule(
            db,
            rule_id,
            changed_by=admin.name,
            points=payload.points,
            description=payload.description,
            active=payload.active,
            description_set="description" in fields_set,
        )
    except admin_reward_service.RewardRuleNotFoundError:
        raise HTTPException(status_code=404, detail="Reward rule not found")


@router.get("/reward-rules/{rule_id}/history", response_model=list[RewardRuleChangeRead])
def get_reward_rule_history(
    rule_id: UUID,
    admin: AdminPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_reward_service.get_rule_or_404(db, rule_id)
    return admin_reward_service.list_rule_changes(db, rule_id)
