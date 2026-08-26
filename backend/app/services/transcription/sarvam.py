import logging
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


@dataclass
class TranscriptionResult:
    """Normalized view of a successful Sarvam transcription — only the fields
    this app actually uses, not a dump of the raw provider response (see
    app/db/models/transcription.py for why no raw-response column exists)."""

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


def transcribe_audio(
    audio_bytes: bytes, filename: str, content_type: str | None
) -> TranscriptionResult:
    """Sends audio to Sarvam's Saaras speech-to-text API (client.speech_to_text.
    transcribe — the actual installed SDK's real method, not assumed) and returns
    a normalized result. Raises TranscriptionProviderError on any failure;
    never returns a fabricated transcript."""
    client = _get_client()
    try:
        response = client.speech_to_text.transcribe(
            file=(filename, audio_bytes, _sarvam_content_type(content_type)),
            model=settings.sarvam_transcription_model,
            mode=SARVAM_MODE,
            language_code=SARVAM_LANGUAGE_CODE,
        )
    except ApiError as exc:
        # exc.status_code/exc.body may echo request details but never the
        # Authorization header/API key itself — safe to log and to persist.
        logger.warning("Sarvam API error: status=%s", exc.status_code)
        raise TranscriptionProviderError(
            f"Sarvam API request failed (status {exc.status_code})."
        ) from exc
    except Exception as exc:
        # Network failure, DNS failure, timeout, or anything else the SDK's
        # underlying httpx client raises that isn't a typed ApiError subclass.
        # Deliberately logs only the exception TYPE, not str(exc) — an httpx
        # transport error's message can echo request details, and there is no
        # need to risk it for a log line this generic.
        logger.warning("Sarvam request failed: %s", type(exc).__name__)
        raise TranscriptionProviderError(
            "Could not reach the transcription service."
        ) from exc

    transcript = (response.transcript or "").strip()
    if not transcript:
        raise TranscriptionProviderError("Transcription service returned an empty transcript.")

    return TranscriptionResult(
        transcript=transcript,
        language_code=response.language_code,
        language_probability=response.language_probability,
        request_id=response.request_id,
        model=settings.sarvam_transcription_model,
        mode=SARVAM_MODE,
    )
