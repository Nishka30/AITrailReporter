from pathlib import Path

# Content types the mobile app actually produces (expo-audio's HIGH_QUALITY
# preset records .m4a on both iOS and Android), plus a few common equivalents.
# Not "any audio/*" on purpose — this is a real allow-list, not a rubber stamp.
ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/m4a",
    "audio/x-m4a",
    "audio/mp4",
    "audio/aac",
    "audio/wav",
    "audio/x-wav",
    "audio/3gpp",
    "audio/webm",
}

ALLOWED_AUDIO_EXTENSIONS = {".m4a", ".mp4", ".aac", ".wav", ".3gp", ".webm"}


class InvalidAudioUploadError(Exception):
    """Raised when an audio upload fails validation. `status_code` lets the route
    return the right HTTP status without the route needing to know validation
    internals."""

    def __init__(self, message: str, status_code: int = 415):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def validate_audio_upload(
    content_type: str | None,
    filename: str | None,
    size_bytes: int,
    max_size_bytes: int,
) -> None:
    """Validation practical for this step: non-empty, under the configured size
    cap, and a recognized audio content type + extension. This does NOT decode or
    inspect audio frame data — that level of verification is deferred (see
    backend/README.md)."""
    if size_bytes <= 0:
        raise InvalidAudioUploadError("Uploaded audio file is empty.", status_code=400)
    if size_bytes > max_size_bytes:
        raise InvalidAudioUploadError(
            f"Uploaded audio exceeds the maximum allowed size of {max_size_bytes} bytes.",
            status_code=413,
        )
    if not content_type or content_type.lower() not in ALLOWED_AUDIO_CONTENT_TYPES:
        raise InvalidAudioUploadError(
            f"Unsupported audio content type: {content_type!r}", status_code=415
        )
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise InvalidAudioUploadError(
            f"Unsupported audio file extension: {extension!r}", status_code=415
        )
