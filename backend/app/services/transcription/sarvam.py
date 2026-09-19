import glob
import json
import logging
import os
import re
import tempfile
import uuid
from dataclasses import dataclass

from sarvamai import SarvamAI
from sarvamai.core.api_error import ApiError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Saaras' "mixed Nepali/English guide speech" case is exactly what 'codemix' mode
# is for: "Code-mixed text with English words in English and Indic words in
# native script" (per Sarvam's own docs) — this app's guides are expected to
# code-switch between Nepali and English, and there is no UI today that collects
# a per-recording language hint from the guide, so a fixed single language_code
# would be a guess this app has no basis for. 'unknown' asks Saaras to
# auto-detect instead of guessing on our side. Sherpa is NOT a supported
# language_code in this SDK version — nothing here pretends otherwise.
SARVAM_MODE = "codemix"
SARVAM_LANGUAGE_CODE = "unknown"

# Sarvam's SYNCHRONOUS speech-to-text endpoint hard-rejects audio longer than
# 30 seconds with HTTP 400 "Audio duration exceeds the maximum limit of 30
# seconds. Please use the batch API for longer audio files." — verified against
# the real API with the exact recordings that failed in production (17.8s and
# 12.1s succeeded; 30.6s and 55.4s were both rejected). This app never capped
# recording length, so any guide talking for more than half a minute silently
# lost their transcript. Anything at or over this bound goes to the batch job
# API instead, which has no such limit.
SYNC_MAX_DURATION_SECONDS = 30.0

# expo-audio's reported duration is the client's own measurement and can differ
# slightly from what Sarvam measures server-side, so the routing decision backs
# off from the hard limit rather than sitting exactly on it. A recording a
# fraction under 30s that Sarvam measures as a fraction over would otherwise
# take the (handled, but slower) 400-then-retry path on every single attempt.
SYNC_DURATION_SAFETY_MARGIN_SECONDS = 2.0

# How Sarvam spells the duration-limit rejection. Matched loosely (lowercased
# substring) so a reworded message still routes to batch rather than surfacing
# as a dead-end failure; the explicit duration check above is the primary
# mechanism, and this is the fallback for when the client-reported duration is
# missing or wrong.
_DURATION_LIMIT_MARKERS = ("duration exceeds", "batch api")

# Sarvam's speech-to-text endpoint validates the file's content type against
# its OWN allow-list, which is narrower/spelled differently than this
# project's own (see app/services/audio_validation.py) -- confirmed against
# the real API: it rejects the literal string "audio/m4a" (HTTP 400,
# "Invalid file type: audio/m4a... Only [...] are allowed"), even though that
# is exactly what expo-audio's HIGH_QUALITY preset reports and what this
# backend's own upload validation correctly accepts as real M4A audio.
# Sarvam's allow-list does include "audio/x-m4a", an equally valid MIME alias
# for the same format -- so this is purely a spelling mismatch between the two
# APIs' allow-lists, not a real difference in the audio. Only entries this
# app's recording pipeline can actually produce are mapped here (see
# RECORDED_CONTENT_TYPE in mobile's src/audio/audioRecordingService.ts) --
# not a speculative full mapping table for content types nothing here ever
# generates.
_SARVAM_CONTENT_TYPE_ALIASES = {
    "audio/m4a": "audio/x-m4a",
}

# Kept in sync with audio_validation.ALLOWED_AUDIO_EXTENSIONS. Only used to give
# the temporary file handed to the batch uploader a sane extension — the batch
# API infers the container from it.
_BATCH_EXTENSIONS = frozenset({".m4a", ".mp4", ".aac", ".wav", ".3gp", ".webm"})
_BATCH_FALLBACK_EXTENSION = ".m4a"

# Upper bound on a persisted/displayed provider message. Long enough for any
# real Sarvam error, short enough that a pathological provider response can
# never bloat the row or the admin UI.
_MAX_PROVIDER_MESSAGE_CHARS = 300


def _sarvam_content_type(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    return _SARVAM_CONTENT_TYPE_ALIASES.get(content_type.lower(), content_type)


class TranscriptionProviderError(Exception):
    """Raised for any failure that prevents a usable transcript — auth, network,
    provider-side error, or an empty/unusable result. `message` is always safe to
    persist and show (in TASK J's terms: no API key, no raw provider internals
    beyond a short, safe description)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class _DurationTooLongError(Exception):
    """Internal only: the synchronous endpoint refused this audio for being
    longer than its 30s limit. Never escapes this module — it is the signal to
    retry the same audio through the batch job API instead."""


@dataclass
class TranscriptionResult:
    """Normalized view of a successful Sarvam transcription — only the fields
    this app actually uses, not a dump of the raw provider response (see
    app/db/models/transcription.py for why no raw-response column exists).

    Identical regardless of which Sarvam endpoint produced it: the batch job's
    output JSON carries the same transcript/language_code/language_probability/
    request_id fields as the synchronous response, so nothing downstream needs
    to know which path ran. `mode` records that difference for operators.
    """

    transcript: str
    language_code: str | None
    language_probability: float | None
    request_id: str | None
    model: str
    mode: str


def _get_client() -> SarvamAI:
    if not settings.sarvam_api_key:
        raise TranscriptionProviderError("Sarvam API key is not configured on the server.")
    return SarvamAI(
        api_subscription_key=settings.sarvam_api_key,
        timeout=settings.sarvam_request_timeout_seconds,
    )


def _sanitize(text: str) -> str:
    """Makes a provider-supplied string safe to persist and show to an admin.

    Sarvam's error bodies do not contain the subscription key (it travels in a
    header), but this strips it anyway if it ever appears: a provider that
    echoes the request back is exactly the kind of surprise that turns an error
    message into a credential leak, and the check costs nothing.
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    key = settings.sarvam_api_key
    if key:
        cleaned = cleaned.replace(key, "[redacted]")
    if len(cleaned) > _MAX_PROVIDER_MESSAGE_CHARS:
        cleaned = cleaned[: _MAX_PROVIDER_MESSAGE_CHARS - 1].rstrip() + "…"
    return cleaned


def _provider_message(exc: ApiError) -> str | None:
    """Pulls Sarvam's OWN error text out of an ApiError body.

    Before this existed, every provider rejection was flattened to
    "Sarvam API request failed (status 400)" — which is how a plain, fully
    self-describing "Audio duration exceeds the maximum limit of 30 seconds"
    stayed invisible in production for days. Shape-tolerant on purpose: the
    body is provider-controlled, so every level is type-checked rather than
    assumed, and an unrecognized shape simply yields None (the caller then
    falls back to the status-code-only message).
    """
    body = exc.body
    if isinstance(body, str):
        return _sanitize(body) or None
    if not isinstance(body, dict):
        return None

    error = body.get("error")
    candidate: object = None
    if isinstance(error, dict):
        candidate = error.get("message") or error.get("code")
    elif isinstance(error, str):
        candidate = error
    if candidate is None:
        candidate = body.get("message") or body.get("detail")
    if not isinstance(candidate, str):
        return None
    return _sanitize(candidate) or None


def _is_duration_limit(message: str | None) -> bool:
    if not message:
        return False
    lowered = message.lower()
    return any(marker in lowered for marker in _DURATION_LIMIT_MARKERS)


def _api_error_to_provider_error(exc: ApiError) -> TranscriptionProviderError:
    # exc.status_code/exc.body may echo request details but never the
    # Authorization header/API key itself — safe to log and to persist, and
    # _sanitize() defends against that changing.
    message = _provider_message(exc)
    logger.warning("Sarvam API error: status=%s message=%s", exc.status_code, message)
    if message:
        return TranscriptionProviderError(f"Sarvam: {message} (status {exc.status_code})")
    return TranscriptionProviderError(f"Sarvam API request failed (status {exc.status_code}).")


def _transcribe_sync(
    audio_bytes: bytes, filename: str, content_type: str | None
) -> TranscriptionResult:
    """One call to the synchronous endpoint. Fast (sub-second for a short clip)
    but capped at SYNC_MAX_DURATION_SECONDS of audio."""
    client = _get_client()
    try:
        response = client.speech_to_text.transcribe(
            file=(filename, audio_bytes, _sarvam_content_type(content_type)),
            model=settings.sarvam_transcription_model,
            mode=SARVAM_MODE,
            language_code=SARVAM_LANGUAGE_CODE,
        )
    except ApiError as exc:
        message = _provider_message(exc)
        if exc.status_code == 400 and _is_duration_limit(message):
            raise _DurationTooLongError() from exc
        raise _api_error_to_provider_error(exc) from exc
    except Exception as exc:
        # Network failure, DNS failure, timeout, or anything else the SDK's
        # underlying httpx client raises that isn't a typed ApiError subclass.
        # Deliberately logs only the exception TYPE, not str(exc) — an httpx
        # transport error's message can echo request details, and there is no
        # need to risk it for a log line this generic.
        logger.warning("Sarvam request failed: %s", type(exc).__name__)
        raise TranscriptionProviderError("Could not reach the transcription service.") from exc

    return _result_from(
        transcript=response.transcript,
        language_code=response.language_code,
        language_probability=response.language_probability,
        request_id=response.request_id,
        mode=SARVAM_MODE,
    )


def _batch_filename(filename: str, content_type: str | None) -> str:
    """A server-generated name for the temporary file the batch uploader reads.

    Never reuses the client-supplied filename as a path component: that name
    reaches a presigned upload URL, and the same "generate the name, don't
    sanitize theirs" rule the storage layer follows applies here for the same
    reason. Only the extension is carried over, and only from an allow-list.
    """
    extension = os.path.splitext(filename or "")[1].lower()
    if extension not in _BATCH_EXTENSIONS:
        aliased = (content_type or "").lower().rsplit("/", 1)[-1]
        candidate = f".{aliased}"
        extension = candidate if candidate in _BATCH_EXTENSIONS else _BATCH_FALLBACK_EXTENSION
    return f"{uuid.uuid4().hex}{extension}"


def _transcribe_batch(
    audio_bytes: bytes, filename: str, content_type: str | None
) -> TranscriptionResult:
    """Transcribes via Sarvam's batch job API, which has no 30-second cap.

    Deliberately NOT a different provider or a second transcription system —
    same account, same Saaras model, same mode/language settings, and the job's
    output JSON carries the same fields as the synchronous response, so it maps
    onto the identical TranscriptionResult. The flow is create job -> upload the
    audio to the presigned URL -> start -> poll until done -> download the
    output JSON.

    Measured against the real API with the 55.4s recording that production
    rejected: 4.9 seconds end to end. That is fast, but it is a POLLED flow with
    no guaranteed bound, which is precisely why transcription now runs in a
    background task rather than inside the upload request (see
    services/transcriptions.py).
    """
    client = _get_client()
    try:
        with tempfile.TemporaryDirectory(prefix="sarvam_batch_") as workdir:
            audio_path = os.path.join(workdir, _batch_filename(filename, content_type))
            with open(audio_path, "wb") as handle:
                handle.write(audio_bytes)

            job = client.speech_to_text_job.create_job(
                model=settings.sarvam_transcription_model,
                mode=SARVAM_MODE,
                language_code=SARVAM_LANGUAGE_CODE,
            )
            job.upload_files([audio_path])
            job.start()
            status = job.wait_until_complete(
                poll_interval=settings.sarvam_batch_poll_interval_seconds,
                timeout=int(settings.sarvam_batch_timeout_seconds),
            )

            state = str(getattr(status, "job_state", "") or "").lower()
            if state != "completed":
                raise TranscriptionProviderError(
                    "Sarvam batch transcription did not complete "
                    f"(job state: {_sanitize(state or 'unknown')})."
                )

            results = job.get_file_results() or {}
            failed = results.get("failed") or []
            if failed:
                detail = ""
                first = failed[0]
                if isinstance(first, dict):
                    detail = str(first.get("error_message") or "")
                raise TranscriptionProviderError(
                    f"Sarvam batch transcription failed: {_sanitize(detail)}"
                    if detail
                    else "Sarvam batch transcription failed for this recording."
                )

            output_dir = os.path.join(workdir, "output")
            os.makedirs(output_dir, exist_ok=True)
            job.download_outputs(output_dir)
            payloads = sorted(glob.glob(os.path.join(output_dir, "*.json")))
            if not payloads:
                raise TranscriptionProviderError(
                    "Sarvam batch transcription produced no output for this recording."
                )
            with open(payloads[0], encoding="utf-8") as handle:
                payload = json.load(handle)
    except TranscriptionProviderError:
        raise
    except ApiError as exc:
        raise _api_error_to_provider_error(exc) from exc
    except TimeoutError as exc:
        logger.warning(
            "Sarvam batch job timed out after %ss", settings.sarvam_batch_timeout_seconds
        )
        raise TranscriptionProviderError(
            "Sarvam batch transcription timed out for this recording."
        ) from exc
    except Exception as exc:
        # Same reasoning as the synchronous path: log the type only.
        logger.warning("Sarvam batch request failed: %s", type(exc).__name__)
        raise TranscriptionProviderError("Could not reach the transcription service.") from exc

    if not isinstance(payload, dict):
        raise TranscriptionProviderError("Transcription service returned an unreadable result.")

    return _result_from(
        transcript=payload.get("transcript"),
        language_code=payload.get("language_code"),
        language_probability=payload.get("language_probability"),
        request_id=payload.get("request_id"),
        mode=f"{SARVAM_MODE}:batch",
    )


def _result_from(
    transcript: object,
    language_code: object,
    language_probability: object,
    request_id: object,
    mode: str,
) -> TranscriptionResult:
    """Shared normalization for both endpoints. Every field is type-checked
    rather than trusted, because the batch path's values come from a parsed JSON
    file rather than the SDK's typed response object."""
    text = (transcript or "").strip() if isinstance(transcript, str) else ""
    if not text:
        raise TranscriptionProviderError("Transcription service returned an empty transcript.")
    return TranscriptionResult(
        transcript=text,
        language_code=language_code if isinstance(language_code, str) else None,
        language_probability=(
            float(language_probability) if isinstance(language_probability, (int, float)) else None
        ),
        request_id=request_id if isinstance(request_id, str) else None,
        model=settings.sarvam_transcription_model,
        mode=mode,
    )


def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str | None,
    duration_seconds: float | None = None,
) -> TranscriptionResult:
    """Sends audio to Sarvam's Saaras speech-to-text API and returns a
    normalized result. Raises TranscriptionProviderError on any failure; never
    returns a fabricated transcript.

    Picks the endpoint by recording length, because Sarvam's synchronous API
    rejects anything over SYNC_MAX_DURATION_SECONDS outright:

    - short (or unknown) duration -> synchronous endpoint, typically sub-second
    - known long duration         -> batch job API directly, no wasted 400
    - unknown duration that turns -> synchronous endpoint refuses it, and this
      out to be long                 falls back to batch automatically

    `duration_seconds` is the client-reported length stored on the Submission,
    which expo-audio cannot always produce — hence the fallback rather than
    trusting it as the only signal.
    """
    routes_to_batch = (
        duration_seconds is not None
        and duration_seconds >= SYNC_MAX_DURATION_SECONDS - SYNC_DURATION_SAFETY_MARGIN_SECONDS
    )
    if routes_to_batch:
        logger.info(
            "Routing %.1fs recording to Sarvam batch API (sync limit is %.0fs)",
            duration_seconds,
            SYNC_MAX_DURATION_SECONDS,
        )
        return _transcribe_batch(audio_bytes, filename, content_type)

    try:
        return _transcribe_sync(audio_bytes, filename, content_type)
    except _DurationTooLongError:
        logger.info(
            "Sarvam refused a recording as too long for the sync endpoint "
            "(client-reported duration: %s); retrying via the batch API",
            duration_seconds,
        )
        return _transcribe_batch(audio_bytes, filename, content_type)
