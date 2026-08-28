from app.core.config import settings
from app.services.storage.base import AudioStorage, MediaStorage, StoredAudio, StoredFile
from app.services.storage.local_filesystem import (
    PHOTO_EXTENSIONS,
    LocalFilesystemAudioStorage,
    LocalFilesystemMediaStorage,
)
from app.services.storage.supabase_storage import SupabaseAudioStorage, SupabasePhotoStorage

_audio_storage: MediaStorage | None = None
_photo_storage: MediaStorage | None = None


def _use_supabase() -> bool:
    """True when both Supabase credentials are present in config — i.e. we are
    running in production (APP_ENVIRONMENT=production on Render) or a dev
    environment that has been explicitly pointed at Supabase Storage."""
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def get_audio_storage() -> MediaStorage:
    """Returns the process-wide audio MediaStorage instance, created on first
    use.

    - **Production** (Supabase credentials set): uses SupabaseAudioStorage,
      uploading files to the ``SUPABASE_AUDIO_BUCKET`` bucket.
    - **Development** (no Supabase credentials): uses LocalFilesystemAudioStorage,
      writing files to ``AUDIO_STORAGE_DIR`` on the local filesystem.

    Nothing outside this module needs to know which backend is active.
    """
    global _audio_storage
    if _audio_storage is None:
        if _use_supabase():
            _audio_storage = SupabaseAudioStorage(
                supabase_url=settings.supabase_url,  # type: ignore[arg-type]
                supabase_key=settings.supabase_service_role_key,  # type: ignore[arg-type]
                bucket=settings.supabase_audio_bucket,
            )
        else:
            _audio_storage = LocalFilesystemAudioStorage(settings.audio_storage_dir)
    return _audio_storage


def get_photo_storage() -> MediaStorage:
    """Returns the process-wide photo MediaStorage instance (Step 16).

    Same dev/production split as get_audio_storage() above — separate bucket
    (``SUPABASE_PHOTO_BUCKET``) so audio and photo files can be given different
    retention/quota treatment without any code change.
    """
    global _photo_storage
    if _photo_storage is None:
        if _use_supabase():
            _photo_storage = SupabasePhotoStorage(
                supabase_url=settings.supabase_url,  # type: ignore[arg-type]
                supabase_key=settings.supabase_service_role_key,  # type: ignore[arg-type]
                bucket=settings.supabase_photo_bucket,
            )
        else:
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
