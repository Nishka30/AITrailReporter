import uuid
from pathlib import Path

from app.services.storage.base import MediaStorage, StoredFile

# Kept in sync with app/services/audio_validation.py's ALLOWED_AUDIO_EXTENSIONS
# and app/services/photo_validation.py's ALLOWED_PHOTO_EXTENSIONS. Only used to
# pick a sane extension for the server-generated filename — the actual upload
# validation (rejecting anything else) happens in those validation modules.
AUDIO_EXTENSIONS = frozenset({".m4a", ".mp4", ".aac", ".wav", ".3gp", ".webm"})
PHOTO_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic"})

_FALLBACK_EXTENSION = ".bin"


class LocalFilesystemMediaStorage(MediaStorage):
    """Development/demo storage: files live under a directory on the backend
    host's own filesystem. Durable across requests (the directory is not
    request-scoped or temporary), but NOT durable across hosts/deployments or
    horizontally-scaled backend instances — that upgrade is a future
    S3-compatible MediaStorage implementation, deliberately deferred (see
    backend/README.md).

    `known_extensions` only influences the extension of the server-generated
    filename; it is never a security control. Path traversal is prevented by
    construction — the client filename is never used as any part of a path.
    """

    def __init__(self, base_dir: str, known_extensions: frozenset[str]):
        self._base_dir = Path(base_dir).resolve()
        self._known_extensions = known_extensions
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_extension(self, original_filename: str) -> str:
        extension = Path(original_filename).suffix.lower()
        return extension if extension in self._known_extensions else _FALLBACK_EXTENSION

    def save(self, content: bytes, original_filename: str) -> StoredFile:
        extension = self._safe_extension(original_filename)
        # Server-generated name only. The client-supplied filename is never used
        # as, or as part of, a filesystem path, which rules out path traversal by
        # construction rather than by sanitizing untrusted input.
        storage_key = f"{uuid.uuid4().hex}{extension}"
        path = self._base_dir / storage_key
        path.write_bytes(content)
        return StoredFile(storage_key=storage_key, size_bytes=len(content))

    def read_bytes(self, storage_key: str) -> bytes:
        path = self.resolve_path(storage_key)
        if not path.is_file():
            raise FileNotFoundError(f"Stored file not found: {storage_key!r}")
        return path.read_bytes()

    def resolve_path(self, storage_key: str) -> Path:
        path = (self._base_dir / storage_key).resolve()
        if path.parent != self._base_dir:
            raise ValueError(f"Invalid storage key: {storage_key!r}")
        return path


class LocalFilesystemAudioStorage(LocalFilesystemMediaStorage):
    """Step 7's original class name, preserved as a thin audio-configured
    subclass so existing construction sites keep working unchanged."""

    def __init__(self, base_dir: str):
        super().__init__(base_dir, AUDIO_EXTENSIONS)
