from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoredAudio:
    """What the caller needs after a successful save: the durable reference to
    persist on the Submission row, and the size actually written (source of
    truth for audio_size_bytes, not whatever the client claimed)."""

    storage_key: str
    size_bytes: int


class AudioStorage(ABC):
    """Durable storage for uploaded voice-note audio, independent of the request
    that uploaded it. This step's only implementation is local filesystem storage
    for development (see local_filesystem.py) — production would swap in an
    S3-compatible implementation of this same interface; nothing in
    services/submissions.py or the API routes would need to change."""

    @abstractmethod
    def save(self, content: bytes, original_filename: str) -> StoredAudio:
        """Persists `content` durably and returns a server-generated reference to
        it. Must never use `original_filename` as, or as part of, a filesystem
        path — it is client-supplied and untrusted."""
        raise NotImplementedError

    @abstractmethod
    def resolve_path(self, storage_key: str) -> Path:
        """Resolves a previously returned storage_key back to a readable path.
        storage_key is always server-generated (see save()), but implementations
        must still reject a value that would resolve outside the storage root."""
        raise NotImplementedError
