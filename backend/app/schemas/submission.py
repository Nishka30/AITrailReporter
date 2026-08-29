import uuid as uuid_module
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 'note' (text), 'voice' (audio, Step 7) and 'explore' (Step 16: a proactive
# Explore-tab discovery contribution) are ingestable. Widen this tuple (and the
# Literal below) when another capture type is actually implemented — do not
# accept values the backend can't yet do anything useful with.
#
# 'explore' is a first-class submission_type rather than a flag on 'note'
# because the two mean genuinely different things about PROVENANCE: a note is
# an unprompted field report, an explore contribution answers a discovery
# prompt the app surfaced. Both carry their content in raw_text and share the
# identical extraction path (see app/services/source_text.py), so this costs no
# duplicated pipeline — but the distinction stays queryable forever.
#
# 'answer' is deliberately NOT here: answer submissions are created server-side
# by app/services/question_answers.py, never ingested through this endpoint.
SUPPORTED_CAPTURE_TYPES = ("note", "voice", "explore")

# Submission types that may carry an audio attachment, and therefore a
# Transcription. 'voice' is audio BY DEFINITION (its content is the recording);
# 'explore' MAY carry one as primary or supplementary content alongside optional
# text and an optional photo (Step 17).
#
# Defined ONCE here and imported by both the upload route
# (api/routes/submissions.py) and the transcription service
# (services/transcriptions.py) so the two can never drift apart into a state
# where audio can be uploaded but then never transcribed — which would be a
# silent dead end for the guide, not a visible error.
#
# Deliberately an allow-list rather than "any type": accepting audio on a 'note'
# or 'answer' submission would create a state no flow produces or renders.
AUDIO_CAPABLE_SUBMISSION_TYPES = ("voice", "explore")


class SubmissionCreate(BaseModel):
    guide_id: UUID
    # Stable client-generated id (e.g. a mobile app's local UUID). Submission
    # ingestion is idempotent on this value: a repeat request with the same
    # client_submission_id returns the already-created submission instead of making
    # another, as long as the resubmitted payload matches the original.
    client_submission_id: str = Field(min_length=1, max_length=255)
    capture_type: Literal["note", "voice", "explore"]
    # Required for 'note' (the text IS the submission). Must be omitted/null for
    # 'voice' — a voice submission's content is the audio, attached afterwards
    # via POST /api/v1/submissions/{submission_id}/audio.
    #
    # OPTIONAL for 'explore' (Step 17). Until Step 17 an Explore contribution
    # was always text, so text was required; now it may instead (or also) carry
    # a voice note, whose transcript becomes the source text exactly as it does
    # for 'voice' (see services/source_text.py). The server genuinely cannot
    # validate "text or audio" at creation time, because audio is attached by a
    # SEPARATE later request — precisely the same ordering that has always
    # applied to 'voice'. So an 'explore' submission with neither text nor a
    # subsequent audio upload is accepted here and then simply has no source
    # text to extract from, reported honestly by resolve_source_text() as
    # EmptySourceTextError. The mobile app enforces "text or voice" before
    # saving (see mobile/src/screens/ExploreContributeScreen.tsx); this is a
    # client-side product rule, not a server guarantee, and is documented as
    # such rather than pretended otherwise.
    text_content: str | None = Field(default=None, min_length=1)
    # When the device captured this, not when the server received it. Defaults to
    # server time if the client doesn't supply one.
    submitted_at: datetime | None = None
    # Set when this contribution answers a location-specific place question --
    # the "you're here right now, tell us about this place" invitations the
    # backend researched for a known Location.
    #
    # Only meaningful with capture_type 'explore', and validated as such below.
    # A place-question contribution IS an Explore contribution: it uses the same
    # composer, the same offline capture outbox, the same two-stage media upload
    # and the same extraction pipeline. This field is the ONLY difference, and it
    # exists so provenance stays queryable and so the reward can be paid at the
    # question's own kind-specific rate rather than the generic Explore rate
    # (see app/services/submissions.py).
    #
    # Deliberately not a separate endpoint: routing media through a second
    # answer path would mean duplicating audio attach, photo attach,
    # transcription triggering and their idempotency contracts.
    source_place_question_id: UUID | None = None

    @field_validator("client_submission_id")
    @classmethod
    def validate_client_submission_id(cls, value: str) -> str:
        try:
            uuid_module.UUID(value)
        except ValueError as exc:
            raise ValueError("client_submission_id must be a valid UUID string") from exc
        return value

    @field_validator("submitted_at")
    @classmethod
    def require_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.tzinfo.utcoffset(value) is None):
            raise ValueError("submitted_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_text_content_for_capture_type(self) -> "SubmissionCreate":
        if self.capture_type == "note" and not self.text_content:
            raise ValueError("text_content is required for capture_type 'note'")
        if self.capture_type == "voice" and self.text_content is not None:
            raise ValueError(
                "text_content must not be supplied for capture_type 'voice' — "
                "upload the audio separately via POST /api/v1/submissions/{id}/audio"
            )
        if self.source_place_question_id is not None and self.capture_type != "explore":
            raise ValueError(
                "source_place_question_id is only valid for capture_type 'explore'"
            )
        return self


class SubmissionAudioRead(BaseModel):
    """Durable audio metadata for a 'voice' submission. Deliberately omits the
    server storage key/path — that is an internal implementation detail, never
    exposed to clients (see app/services/storage/)."""

    model_config = ConfigDict(from_attributes=True)

    content_type: str
    original_filename: str
    size_bytes: int
    duration_seconds: float | None


class SubmissionPhotoRead(BaseModel):
    """Durable photo metadata for an 'explore' submission (Step 16). Like
    SubmissionAudioRead, deliberately omits the server storage key/path — that
    is an internal implementation detail, never exposed to clients."""

    model_config = ConfigDict(from_attributes=True)

    content_type: str
    original_filename: str
    size_bytes: int


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    guide_id: UUID
    client_submission_id: str | None
    submission_type: str
    raw_text: str | None
    status: str
    submitted_at: datetime
    created_at: datetime
    updated_at: datetime
    # Populated from the ORM's Submission.audio property (see db/models/submission.py)
    # — present only once audio has actually been uploaded for this submission.
    audio: SubmissionAudioRead | None = None
    # Same contract, from Submission.photo — null until a photo has actually
    # been uploaded (Step 16).
    photo: SubmissionPhotoRead | None = None
