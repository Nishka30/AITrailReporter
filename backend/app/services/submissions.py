from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.place_question import PlaceQuestion
from app.db.models.submission import (
    DEFAULT_DATE_SOURCE,
    DEFAULT_LOCATION_SOURCE,
    Submission,
)
from app.schemas.submission import SubmissionCreate
from app.services import extractions as extraction_service
from app.services import rewards as reward_service
from app.services import transcriptions as transcription_service
from app.services.storage.base import AudioStorage, MediaStorage


class SubmissionConflictError(Exception):
    """Raised when a client_submission_id is reused with a payload that doesn't
    match the original submission it was first used for."""

    def __init__(self, existing: Submission):
        self.existing = existing
        super().__init__(
            f"client_submission_id {existing.client_submission_id!r} was already used "
            "with different submission data"
        )


class AudioConflictError(Exception):
    """Raised when a submission that already has audio attached receives another
    audio upload with a different client_audio_id — i.e. an attempt to attach a
    second, distinct recording rather than retry the same one."""

    def __init__(self, existing: Submission):
        self.existing = existing
        super().__init__(
            f"submission {existing.id} already has audio attached under a "
            "different client_audio_id"
        )


class PhotoConflictError(Exception):
    """Photo equivalent of AudioConflictError (Step 16): the submission already
    has a photo attached under a DIFFERENT client_photo_id. Replacing an
    already-attached photo is deliberately not supported, matching audio."""

    def __init__(self, existing: Submission):
        self.existing = existing
        super().__init__(
            f"submission {existing.id} already has a photo attached under a "
            "different client_photo_id"
        )


def _award_media_bonus(db: Session, submission: Submission) -> None:
    """Adds the Explore media bonus once, when a photo or voice note is
    attached to an Explore contribution.

    Idempotency key is the submission's client id with a ':media' suffix -- a
    DIFFERENT key from the base award (which uses the bare client id), so the
    two coexist, while re-uploading the same media can never pay the bonus
    twice. Attaching both a photo AND a voice note to one contribution also
    pays the bonus once, deliberately: the bonus is for enriching a
    contribution with media, not per file.

    Only 'explore' and 'memory' submissions qualify -- a plain voice note is
    not an Explore contribution and never received the base award either.
    Memories are paid at the SAME rate as a generic Explore contribution
    (there is no separate memory reward rule to invent or maintain); only the
    ledger's `source_type` distinguishes the two afterwards for Admin.

    A place-question contribution is EXCLUDED even though it is an 'explore'
    submission (never applies to 'memory' -- see schemas/submission.py's
    validator, which forbids source_place_question_id outside 'explore'). It
    was already paid at its own kind-specific rate, and a photo request is
    paid the photo rate precisely because it asks for a photo -- adding the
    generic media bonus on top would pay twice for the one thing the question
    asked for.
    """
    if submission.submission_type not in ("explore", "memory") or submission.client_submission_id is None:
        return
    if submission.source_place_question_id is not None:
        return
    reward_service.award(
        db,
        guide_id=submission.guide_id,
        rule_key="explore_contribution_media_bonus",
        idempotency_key=f"{submission.client_submission_id}:media",
        source_type=(
            "memory_submission" if submission.submission_type == "memory" else "explore_submission"
        ),
        source_id=submission.id,
    )


def get_submission_by_client_id(db: Session, client_submission_id: str) -> Submission | None:
    stmt = select(Submission).where(Submission.client_submission_id == client_submission_id)
    return db.execute(stmt).scalar_one_or_none()


def get_submission(db: Session, submission_id: UUID) -> Submission | None:
    return db.get(Submission, submission_id)


def _ensure_compatible(existing: Submission, data: SubmissionCreate) -> None:
    if (
        existing.guide_id != data.guide_id
        or existing.submission_type != data.capture_type
        or existing.raw_text != data.text_content
        # Provenance is part of the payload's identity: the same client id
        # arriving once as a free-form discovery and once as an answer to a
        # place question is a genuine conflict, not an idempotent replay.
        or existing.source_place_question_id != data.source_place_question_id
    ):
        raise SubmissionConflictError(existing)


def create_or_get_submission(db: Session, data: SubmissionCreate) -> tuple[Submission, bool]:
    """Create a submission, or return the existing one if client_submission_id was
    already used for an equivalent submission. Raises SubmissionConflictError if the
    same client_submission_id is reused with different data instead of silently
    overwriting the original.

    Race-safe the same way as guides.create_or_get_guide: the DB unique constraint
    on client_submission_id is the real guarantee, an IntegrityError on a concurrent
    duplicate insert is caught and resolved by re-fetching the winner's row.
    """
    existing = get_submission_by_client_id(db, data.client_submission_id)
    if existing is not None:
        _ensure_compatible(existing, data)
        return existing, False

    submitted_at = data.submitted_at or datetime.now(timezone.utc)

    # When occurred_at is absent, a LIVE capture's event time IS its submit
    # time -- that is what "live" means, not a guess. This default is only
    # applied here, at creation, for whatever moment this specific request
    # actually represents; it is never applied retroactively and never
    # overwrites a client-supplied value.
    #
    # Precision defaults to "exact" either way: a concrete instant is known in
    # both branches (either the client gave one, or it genuinely is this
    # request's submit time). Only the SOURCE of that instant is ambiguous
    # when the client didn't say -- "device" for the true live-capture default,
    # "unknown" when a specific timestamp arrived with no stated origin.
    occurred_at = data.occurred_at or submitted_at
    occurred_at_precision = data.occurred_at_precision or "exact"
    date_source = data.date_source or ("device" if data.occurred_at is None else DEFAULT_DATE_SOURCE)

    submission = Submission(
        guide_id=data.guide_id,
        client_submission_id=data.client_submission_id,
        submission_type=data.capture_type,
        raw_text=data.text_content,
        latitude=data.latitude,
        longitude=data.longitude,
        location_source=data.location_source or DEFAULT_LOCATION_SOURCE,
        location_accuracy_meters=data.location_accuracy_meters,
        location_captured_at=data.location_captured_at,
        location_label=data.location_label,
        location_evidence=data.location_evidence,
        occurred_at=occurred_at,
        occurred_at_precision=occurred_at_precision,
        date_source=date_source,
        submitted_at=submitted_at,
        status="received",
        # Null for an ordinary discovery; set when this answers a
        # location-specific place question. Coordinates are deliberately NOT
        # copied from the place here -- _resolve_observation_coordinates already
        # falls back to the guide's own GPS at submission time, which is where
        # the guide actually was (and is within the place's radius by
        # construction). Recording the place's coordinates instead would claim
        # a precision the report doesn't have.
        source_place_question_id=data.source_place_question_id,
    )
    db.add(submission)
    # Reward (Step 18) for an Explore or memory contribution, in the SAME
    # transaction as the submission itself. A 'note' is an unprompted field
    # report and 'voice' has no prompt provenance, so neither earns here; an
    # Explore contribution answers something the app actually asked for, and a
    # memory is the same kind of proactive field contribution without a live
    # prompt behind it -- paid at the identical base rate, distinguished only
    # by `source_type` in the ledger (see _award_media_bonus above).
    #
    # Awarded at the base rate now, because media is attached by a SEPARATE
    # later request -- attach_audio/photo_to_submission top this up to the
    # with-media rate once media genuinely arrives (see those functions). The
    # alternative, guessing up-front that media is coming, would credit a
    # richer contribution than the guide actually made.
    if data.capture_type in ("explore", "memory"):
        db.flush()
        if data.source_place_question_id is not None:
            # A place-question contribution is paid at the rate for that
            # question's own contribution kind (photo/voice/status/...), because
            # the app asked for something specific and the kinds differ in
            # effort. Resolved from the stored question, never from the request
            # -- the device does not get to choose what it is paid. Never
            # reachable for 'memory': the schema forbids the combination.
            place_question = db.get(PlaceQuestion, data.source_place_question_id)
            rule_key = reward_service.place_question_rule_key(
                db, place_question.contribution_kind if place_question is not None else None
            )
            source_type = "place_question_answer"
        else:
            rule_key = "explore_contribution"
            source_type = "memory_submission" if data.capture_type == "memory" else "explore_submission"
        reward_service.award(
            db,
            guide_id=data.guide_id,
            rule_key=rule_key,
            idempotency_key=data.client_submission_id,
            source_type=source_type,
            source_id=submission.id,
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = get_submission_by_client_id(db, data.client_submission_id)
        if existing is not None:
            _ensure_compatible(existing, data)
            return existing, False
        raise
    db.refresh(submission)
    # Automatic extraction (see extractions.py:maybe_trigger_extraction):
    # a 'note' always has text immediately; an 'explore' submission MAY --
    # resolve_source_text handles both, and a voice-only 'explore' (no text
    # yet) simply isn't ready, so this is a safe no-op for it. Never raises.
    extraction_service.maybe_trigger_extraction(db, submission.id)
    return submission, True


def attach_audio_to_submission(
    db: Session,
    submission_id: UUID,
    client_audio_id: str,
    audio_bytes: bytes,
    content_type: str,
    original_filename: str,
    duration_seconds: float | None,
    storage: AudioStorage,
) -> tuple[Submission, bool]:
    """Attaches durably-stored audio to a 'voice' submission. Idempotent on
    client_audio_id, mirroring the client_submission_id/client_location_id pattern
    used elsewhere:

    - No audio attached yet -> saves the file, records the reference, returns
      (submission, True).
    - Audio already attached under this SAME client_audio_id -> this is a retry of
      a request whose response was lost; returns the existing reference without
      writing another file, (submission, False).
    - Audio already attached under a DIFFERENT client_audio_id -> raises
      AudioConflictError (a real conflict — this step does not support replacing
      an already-attached recording).

    Race safety: the submission row is locked with SELECT ... FOR UPDATE for the
    duration of this function, so two concurrent attach attempts for the SAME
    submission are fully serialized — the second one to acquire the lock sees
    whatever the first one committed and takes the idempotent-replay or conflict
    path above, never a duplicate attachment. The one known gap (documented in
    README): if the process crashes between writing the file to disk and
    committing the row update, the file on disk is orphaned (never referenced by
    any submission) — acceptable for this step, not a correctness issue for the
    data that IS recorded.
    """
    stmt = select(Submission).where(Submission.id == submission_id).with_for_update()
    submission = db.execute(stmt).scalar_one_or_none()
    if submission is None:
        raise LookupError(f"Submission {submission_id} not found")

    if submission.client_audio_id is not None:
        if submission.client_audio_id == client_audio_id:
            db.commit()  # releases the row lock acquired above
            return submission, False
        db.commit()
        raise AudioConflictError(submission)

    stored = storage.save(audio_bytes, original_filename)
    submission.client_audio_id = client_audio_id
    submission.audio_storage_key = stored.storage_key
    submission.audio_content_type = content_type
    submission.audio_original_filename = original_filename
    submission.audio_size_bytes = stored.size_bytes
    submission.audio_duration_seconds = duration_seconds
    # Step 8: create the Transcription tracking row in the SAME transaction as
    # the audio attach, so "audio attached" and "transcription pending" commit
    # atomically together — no window where audio exists but nothing tracks its
    # transcription state.
    transcription_service.ensure_pending_transcription(db, submission_id)
    _award_media_bonus(db, submission)
    db.commit()
    db.refresh(submission)
    # Automatic transcription (see transcriptions.py:maybe_trigger_transcription)
    # -- called AFTER the commit above, so the Submission row lock held since
    # entry to this function has already been released before Sarvam is ever
    # called; start_transcription takes its own separate lock on the
    # Transcription row. Chains into automatic extraction on its own once
    # transcription completes (see the end of start_transcription) -- so a
    # voice/explore recording now goes from "uploaded" to "observations exist"
    # with zero taps, same as a text note already does above.
    transcription_service.maybe_trigger_transcription(db, submission_id)
    return submission, True


def attach_photo_to_submission(
    db: Session,
    submission_id: UUID,
    client_photo_id: str,
    photo_bytes: bytes,
    content_type: str,
    original_filename: str,
    storage: MediaStorage,
) -> tuple[Submission, bool]:
    """Attaches a durably-stored photo to an 'explore' or 'memory' submission
    (Step 16, extended to 'memory' -- see PHOTO_CAPABLE_SUBMISSION_TYPES).

    Structurally identical to attach_audio_to_submission above — same
    idempotency contract on client_photo_id, same SELECT ... FOR UPDATE row
    lock serializing concurrent attach attempts for the same submission, same
    documented orphaned-file-on-crash gap. Two deliberate differences:

    - No transcription row is created. A photo has no transcript, and inventing
      a pipeline stage that does nothing would be dishonest state.
    - No duration is recorded, for the same reason (see
      SubmissionPhotoMetadata).

    A photo does NOT by itself make a submission extractable: extraction reads
    source TEXT (app/services/source_text.py), and this step does not do image
    understanding. An Explore photo contribution therefore always carries the
    guide's own text alongside it — that text is what becomes observations,
    while the photo is durable evidence attached to the same submission. This
    is stated plainly rather than implying the image is being analysed.
    """
    stmt = select(Submission).where(Submission.id == submission_id).with_for_update()
    submission = db.execute(stmt).scalar_one_or_none()
    if submission is None:
        raise LookupError(f"Submission {submission_id} not found")

    if submission.client_photo_id is not None:
        if submission.client_photo_id == client_photo_id:
            db.commit()  # releases the row lock acquired above
            return submission, False
        db.commit()
        raise PhotoConflictError(submission)

    stored = storage.save(photo_bytes, original_filename)
    submission.client_photo_id = client_photo_id
    submission.photo_storage_key = stored.storage_key
    submission.photo_content_type = content_type
    submission.photo_original_filename = original_filename
    submission.photo_size_bytes = stored.size_bytes
    _award_media_bonus(db, submission)
    db.commit()
    db.refresh(submission)
    return submission, True
