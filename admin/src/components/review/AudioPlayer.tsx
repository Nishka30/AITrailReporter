import { useEffect, useState } from 'react';

import { fetchMediaBlobUrl } from '../../api/client';
import { ErrorState, LoadingState } from '../ui/States';

/** Evidence audio player for Review Detail. Fetches the file as a blob
 * (see api/client.ts:fetchMediaBlobUrl) since the media route requires an
 * auth header a plain <audio src> can't send, then hands it to a native
 * <audio controls> element -- which already gives play/pause/duration/seek/
 * error handling for free. */
export default function AudioPlayer({ submissionId }: { submissionId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    fetchMediaBlobUrl(`/api/v1/admin/submissions/${submissionId}/audio`)
      .then((blobUrl) => {
        if (cancelled) {
          URL.revokeObjectURL(blobUrl);
          return;
        }
        objectUrl = blobUrl;
        setUrl(blobUrl);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load audio'));

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [submissionId]);

  if (error) return <ErrorState message={error} />;
  if (!url) return <LoadingState label="Loading audio…" />;

  return (
    <div className="rounded-lg border border-border bg-paper-muted p-3">
      <audio src={url} controls className="w-full" />
    </div>
  );
}
