from app.core.config import settings
from app.services.storage.base import AudioStorage, StoredAudio
from app.services.storage.local_filesystem import LocalFilesystemAudioStorage

_storage: AudioStorage | None = None


def get_audio_storage() -> AudioStorage:
    """Returns the process-wide AudioStorage instance, created on first use. A
    single local-filesystem implementation for this step — see
    app/services/storage/local_filesystem.py for why, and base.py for the
    interface a future object-storage adapter would implement instead."""
    global _storage
    if _storage is None:
        _storage = LocalFilesystemAudioStorage(settings.audio_storage_dir)
    return _storage


__all__ = ["AudioStorage", "StoredAudio", "get_audio_storage"]
