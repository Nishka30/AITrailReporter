import mimetypes
import uuid
from pathlib import Path

from supabase import Client, create_client

from app.services.storage.base import MediaStorage, StoredFile

# Mirrors the extension sets in local_filesystem.py — used only to pick a
# sensible MIME type for the Content-Type header on upload. The actual
# validation (rejecting anything outside the allow-list) still happens in
# audio_validation.py / photo_validation.py before save() is ever called.
_FALLBACK_MIME = "application/octet-stream"


def _mime_for(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or _FALLBACK_MIME


class SupabaseMediaStorage(MediaStorage):
    """Production storage backend: files live in a Supabase Storage bucket.

    Buckets are public (no signed URLs needed) — the storage_key stored on the
    Submission row is the path within the bucket, e.g. ``abc123.m4a``. Callers
    retrieve the public URL via the Supabase dashboard or the Storage JS client;
    the Python backend only ever *writes* (save) and *reads* (read_bytes) files.

    Thread-safety: create_client() returns a synchronous client; one instance
    per storage singleton (see storage/__init__.py) is safe for concurrent use
    within a single-process Uvicorn worker because the underlying httpx session
    is not shared across threads when used synchronously.
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        bucket: str,
        known_extensions: frozenset[str],
    ) -> None:
        self._client: Client = create_client(supabase_url, supabase_key)
        self._bucket = bucket
        self._known_extensions = known_extensions

    def _safe_extension(self, original_filename: str) -> str:
        ext = Path(original_filename).suffix.lower()
        return ext if ext in self._known_extensions else ".bin"

    # ------------------------------------------------------------------
    # MediaStorage interface
    # ------------------------------------------------------------------

    def save(self, content: bytes, original_filename: str) -> StoredFile:
        """Uploads `content` to the bucket and returns a StoredFile whose
        storage_key is a server-generated UUID path (never the client filename).
        """
        ext = self._safe_extension(original_filename)
        storage_key = f"{uuid.uuid4().hex}{ext}"
        mime = _mime_for(f"file{ext}")

        self._client.storage.from_(self._bucket).upload(
            path=storage_key,
            file=content,
            file_options={
                "content-type": mime,
                "cache-control": "3600",
                "upsert": "false",
            },
        )
        return StoredFile(storage_key=storage_key, size_bytes=len(content))

    def read_bytes(self, storage_key: str) -> bytes:
        """Downloads and returns the raw bytes for a previously saved file.
        Raises FileNotFoundError if the object does not exist in the bucket.
        """
        try:
            data: bytes = self._client.storage.from_(self._bucket).download(storage_key)
        except Exception as exc:
            # supabase-py raises a generic StorageException on 404; wrap it so
            # callers can catch FileNotFoundError uniformly regardless of backend.
            raise FileNotFoundError(
                f"Object {storage_key!r} not found in bucket {self._bucket!r}"
            ) from exc
        return data

    def resolve_path(self, storage_key: str) -> Path:  # type: ignore[override]
        """Not supported for cloud storage — use read_bytes() instead."""
        raise NotImplementedError(
            "SupabaseMediaStorage does not support resolve_path(). Use read_bytes()."
        )


class SupabaseAudioStorage(SupabaseMediaStorage):
    """Convenience subclass pre-configured with audio extensions.
    Mirrors the LocalFilesystemAudioStorage pattern so construction sites
    in storage/__init__.py remain symmetrical."""

    _AUDIO_EXTENSIONS = frozenset({".m4a", ".mp4", ".aac", ".wav", ".3gp", ".webm"})

    def __init__(self, supabase_url: str, supabase_key: str, bucket: str) -> None:
        super().__init__(supabase_url, supabase_key, bucket, self._AUDIO_EXTENSIONS)


class SupabasePhotoStorage(SupabaseMediaStorage):
    """Convenience subclass pre-configured with photo extensions."""

    _PHOTO_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic"})

    def __init__(self, supabase_url: str, supabase_key: str, bucket: str) -> None:
        super().__init__(supabase_url, supabase_key, bucket, self._PHOTO_EXTENSIONS)
