import uuid
from pathlib import Path

from app.services.storage.base import AudioStorage, StoredAudio

# Kept in sync with app/services/audio_validation.py's ALLOWED_AUDIO_EXTENSIONS.
# Only used here to pick a sane extension for the server-generated filename — the
# actual upload validation (rejecting anything else) happens in audio_validation.
_KNOWN_EXTENSIONS = {".m4a", ".mp4", ".aac", ".wav", ".3gp", ".webm"}
_FALLBACK_EXTENSION = ".bin"


def _safe_extension(original_filename: str) -> str:
    extension = Path(original_filename).suffix.lower()
    return extension if extension in _KNOWN_EXTENSIONS else _FALLBACK_EXTENSION


class LocalFilesystemAudioStorage(AudioStorage):
    """Development/demo audio storage: files live under a directory on the
    backend host's own filesystem. Durable across requests (the directory is not
    request-scoped or temporary), but NOT durable across hosts/deployments or
    horizontally-scaled backend instances — that upgrade is a future
    S3-compatible AudioStorage implementation, deliberately deferred for this
    step (see backend/README.md)."""

    def __init__(self, base_dir: str):
        self._base_dir = Path(base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, original_filename: str) -> StoredAudio:
        extension = _safe_extension(original_filename)
        # Server-generated name only. The client-supplied filename is never used
        # as, or as part of, a filesystem path, which rules out path traversal by
        # construction rather than by sanitizing untrusted input.
        storage_key = f"{uuid.uuid4().hex}{extension}"
        path = self._base_dir / storage_key
        path.write_bytes(content)
        return StoredAudio(storage_key=storage_key, size_bytes=len(content))

    def resolve_path(self, storage_key: str) -> Path:
        path = (self._base_dir / storage_key).resolve()
        if path.parent != self._base_dir:
            raise ValueError(f"Invalid storage key: {storage_key!r}")
        return path
