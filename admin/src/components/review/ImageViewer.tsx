import { X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { fetchMediaBlobUrl } from '../../api/client';
import { ErrorState, LoadingState } from '../ui/States';

/** Evidence photo preview for Review Detail -- a thumbnail that opens a
 * larger view on click. Same blob-fetch approach as AudioPlayer, for the
 * same reason (the media route needs an auth header). */
export default function ImageViewer({ submissionId }: { submissionId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    fetchMediaBlobUrl(`/api/v1/admin/submissions/${submissionId}/photo`)
      .then((blobUrl) => {
        if (cancelled) {
          URL.revokeObjectURL(blobUrl);
          return;
        }
        objectUrl = blobUrl;
        setUrl(blobUrl);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load photo'));

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [submissionId]);

  if (error) return <ErrorState message={error} />;
  if (!url) return <LoadingState label="Loading photo…" />;

  return (
    <>
      <button onClick={() => setExpanded(true)} className="block overflow-hidden rounded-lg border border-border">
        <img src={url} alt="Submitted evidence" className="max-h-64 w-full object-cover" />
      </button>
      {expanded ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/80 p-8"
          onClick={() => setExpanded(false)}
        >
          <button
            className="absolute right-6 top-6 rounded-full bg-paper-elevated p-2"
            onClick={() => setExpanded(false)}
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
          <img src={url} alt="Submitted evidence, enlarged" className="max-h-full max-w-full rounded-lg" />
        </div>
      ) : null}
    </>
  );
}
