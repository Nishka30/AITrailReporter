import StatusBadge, { type BadgeTone } from '../ui/StatusBadge';
import type { TranscriptionRead } from '../../api/types';

/** Mirrors the backend's transcription state machine exactly (see
 * backend/app/db/models/transcription.py). Deliberately NOT the same vocabulary
 * as the mobile app's guide-facing wording ("Listening…") -- an admin needs to
 * know which stage of the pipeline a recording is actually sitting in. */
function present(status: string): { label: string; tone: BadgeTone } {
  switch (status) {
    case 'pending':
      return { label: 'Pending', tone: 'neutral' };
    case 'processing':
      return { label: 'Processing', tone: 'info' };
    case 'completed':
      return { label: 'Completed', tone: 'success' };
    case 'failed':
      return { label: 'Failed', tone: 'danger' };
    default:
      return { label: status, tone: 'neutral' };
  }
}

/**
 * One transcription's state for an admin, shared by the contribution-review and
 * content-review detail pages so both report it identically.
 *
 * On failure it shows the provider's OWN message. That message is already
 * sanitized where it is produced (see backend's
 * services/transcription/sarvam.py: whitespace-collapsed, length-capped, and
 * scrubbed of the API key defensively) and the backend never writes a
 * credential, token, or raw provider internals into it -- so what reaches here
 * is safe to display. Showing it matters: "Sarvam: Audio duration exceeds the
 * maximum limit of 30 seconds (status 400)" is immediately actionable, whereas
 * the bare "Failed" it replaced left an operator with nothing to go on.
 */
export default function TranscriptionPanel({ transcript }: { transcript: TranscriptionRead }) {
  const status = present(transcript.status);
  const retried = transcript.attempt_count > 1;

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-bold text-ink-faint">Transcript</span>
        <StatusBadge label={status.label} tone={status.tone} />
        {retried ? (
          <span className="text-xs text-ink-faint">{transcript.attempt_count} attempts</span>
        ) : null}
      </div>

      {transcript.transcript ? (
        <p className="mt-1 whitespace-pre-wrap rounded-lg bg-paper-muted p-3 text-sm text-ink">
          {transcript.transcript}
        </p>
      ) : null}

      {transcript.status === 'failed' ? (
        <p className="mt-1 rounded-lg bg-fix-soft p-3 text-sm text-fix">
          {transcript.error_message ?? 'Transcription failed without a recorded reason.'}
        </p>
      ) : null}

      {transcript.status === 'pending' || transcript.status === 'processing' ? (
        <p className="mt-1 text-sm italic text-ink-faint">
          Transcription is still running in the background — reload to see the result.
        </p>
      ) : null}
    </div>
  );
}
