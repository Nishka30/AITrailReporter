"""Upload validation for Explore photos (Step 16). Mirrors
app/services/audio_validation.py's structure and error contract exactly, with
one deliberate addition: a magic-byte check.

Why photos get a content sniff and audio doesn't: the common image formats have
short, unambiguous, well-documented signatures at a fixed offset, so verifying
them is cheap and reliable. (Audio containers do not have an equivalently
simple story, which is why Step 7 documented that check as deferred rather than
faking one.) This means a file that merely CLAIMS image/jpeg but isn't one is
rejected here, instead of being stored and only failing later.
"""

from pathlib import Path

# Content types the mobile image picker actually produces, plus common
# equivalents. Not "any image/*" on purpose — a real allow-list, not a rubber
# stamp (same policy as ALLOWED_AUDIO_CONTENT_TYPES).
ALLOWED_PHOTO_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

# (offset, signature bytes) pairs. A file matches a format if ANY of that
# format's signatures is present at its offset.
#   JPEG  FF D8 FF                     at 0
#   PNG   89 50 4E 47 0D 0A 1A 0A      at 0
#   WEBP  'RIFF' at 0 and 'WEBP' at 8
#   HEIC  'ftyp' at 4 (ISO-BMFF brand box; heic/heix/mif1/msf1 all valid)
_MAGIC_SIGNATURES: list[tuple[int, bytes]] = [
    (0, b"\xff\xd8\xff"),
    (0, b"\x89PNG\r\n\x1a\n"),
    (0, b"RIFF"),
    (4, b"ftyp"),
]

# Enough bytes to cover the longest signature plus its offset.
_MAGIC_PREFIX_LENGTH = 16


class InvalidPhotoUploadError(Exception):
    """Raised when a photo upload fails validation. `status_code` lets the route
    return the right HTTP status without needing to know validation
    internals — identical contract to InvalidAudioUploadError."""

    def __init__(self, message: str, status_code: int = 415):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _looks_like_image(content: bytes) -> bool:
    prefix = content[:_MAGIC_PREFIX_LENGTH]
    for offset, signature in _MAGIC_SIGNATURES:
        if prefix[offset : offset + len(signature)] == signature:
            # RIFF alone is not enough — it's also WAV/AVI. Require the WEBP
            # brand so a WAV renamed to .webp is still rejected.
            if signature == b"RIFF":
                if prefix[8:12] != b"WEBP":
                    continue
            return True
    return False


def validate_photo_upload(
    content_type: str | None,
    filename: str | None,
    content: bytes,
    max_size_bytes: int,
) -> None:
    """Non-empty, under the configured size cap, a recognized image content type
    and extension, AND actually shaped like one of those image formats. Raises
    InvalidPhotoUploadError describing the first violation found.

    This does NOT fully decode the image or verify that its pixel data is
    well-formed — that would require an image library and is deliberately out of
    scope (see backend/README.md). The magic-byte check rejects the cheap,
    obvious cases (a text file or executable renamed to .jpg), not a crafted
    malformed image.
    """
    size_bytes = len(content)
    if size_bytes <= 0:
        raise InvalidPhotoUploadError("Uploaded photo is empty.", status_code=400)
    if size_bytes > max_size_bytes:
        raise InvalidPhotoUploadError(
            f"Uploaded photo exceeds the maximum allowed size of {max_size_bytes} bytes.",
            status_code=413,
        )
    if not content_type or content_type.lower() not in ALLOWED_PHOTO_CONTENT_TYPES:
        raise InvalidPhotoUploadError(
            f"Unsupported photo content type: {content_type!r}", status_code=415
        )
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_PHOTO_EXTENSIONS:
        raise InvalidPhotoUploadError(
            f"Unsupported photo file extension: {extension!r}", status_code=415
        )
    if not _looks_like_image(content):
        raise InvalidPhotoUploadError(
            "Uploaded file does not appear to be a valid image.", status_code=415
        )
