from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoredFile:
    """What the caller needs after a successful save: the durable reference to
    persist on the Submission row, and the size actually written (source of
    truth for the *_size_bytes column, not whatever the client claimed)."""

    storage_key: str
    size_bytes: int


class MediaStorage(ABC):
    """Durable storage for an uploaded binary attachment, independent of the
    request that uploaded it. Step 7 introduced this for voice-note audio;
    Step 16 generalized it (unchanged in behavior) so Explore photos reuse the
    identical contract rather than growing a second, parallel storage system.

    Two concrete implementations exist:
    - LocalFilesystemMediaStorage  — development, reads/writes local disk
    - SupabaseMediaStorage         — production, reads/writes Supabase Storage

    The storage abstraction deliberately separates save() / read_bytes() from
    resolve_path() so cloud backends (which have no local path concept) can
    implement only save() + read_bytes() and raise NotImplementedError for
    resolve_path(). All internal callers that previously used resolve_path()
    have been migrated to read_bytes().
    """

    @abstractmethod
    def save(self, content: bytes, original_filename: str) -> StoredFile:
        """Persists `content` durably and returns a server-generated reference to
        it. Must never use `original_filename` as, or as part of, a filesystem
        path — it is client-supplied and untrusted."""
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self, storage_key: str) -> bytes:
        """Reads and returns the raw bytes for a previously saved file.
        Raises FileNotFoundError if the key does not resolve to a stored file."""
        raise NotImplementedError

    def resolve_path(self, storage_key: str) -> Path:
        """Resolves a previously returned storage_key back to a readable path.
        Only supported by LocalFilesystemMediaStorage — cloud backends raise
        NotImplementedError. Prefer read_bytes() for new code."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support resolve_path(). Use read_bytes() instead."
        )


# Step 7 names, preserved so existing imports (app/services/submissions.py,
# app/api/routes/submissions.py) keep working unchanged. Audio storage is
# simply a MediaStorage whose configured extension allow-list is the audio one.
AudioStorage = MediaStorage
StoredAudio = StoredFile
