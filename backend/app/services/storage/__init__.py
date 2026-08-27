from app.core.config import settings
from app.services.storage.base import AudioStorage, MediaStorage, StoredAudio, StoredFile
from app.services.storage.local_filesystem import (
    PHOTO_EXTENSIONS,
    LocalFilesystemAudioStorage,
    LocalFilesystemMediaStorage,
)

_audio_storage: MediaStorage | None = None
_photo_storage: MediaStorage | None = None


def get_audio_storage() -> MediaStorage:
    """Returns the process-wide audio MediaStorage instance, created on first
    use. A single local-filesystem implementation for this step — see
    app/services/storage/local_filesystem.py for why, and base.py for the
    interface a future object-storage adapter would implement instead."""
    global _audio_storage
    if _audio_storage is None:
        _audio_storage = LocalFilesystemAudioStorage(settings.audio_storage_dir)
    return _audio_storage


def get_photo_storage() -> MediaStorage:
    """Returns the process-wide photo MediaStorage instance (Step 16). A
    SEPARATE instance and a separate configured directory from audio — same
    class, same guarantees, different root — so photo and audio uploads can be
    given different retention/backup/quota treatment operationally without any
    code change."""
    global _photo_storage
    if _photo_storage is None:
        _photo_storage = LocalFilesystemMediaStorage(
            settings.photo_storage_dir, PHOTO_EXTENSIONS
        )
    return _photo_storage


__all__ = [
    "AudioStorage",
    "MediaStorage",
    "StoredAudio",
    "StoredFile",
    "get_audio_storage",
    "get_photo_storage",
]
