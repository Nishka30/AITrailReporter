import { AlertTriangle, Inbox, Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';

/** LoadingState, EmptyState, ErrorState in one file -- three small, related
 * primitives, not worth splitting into three files each holding a few lines. */

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-ink-faint">
      <Loader2 className="h-6 w-6 animate-spin text-marigold" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border-strong py-16 text-center">
      <div className="text-ink-faint">{icon ?? <Inbox className="h-8 w-8" />}</div>
      <div className="font-heading text-lg font-bold text-ink">{title}</div>
      {description ? <div className="max-w-sm text-sm text-ink-soft">{description}</div> : null}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-fix-soft bg-fix-soft/40 py-16 text-center">
      <AlertTriangle className="h-8 w-8 text-fix" />
      <div className="max-w-sm text-sm text-ink-soft">{message}</div>
      {onRetry ? (
        <button
          onClick={onRetry}
          className="rounded-full bg-ink px-4 py-2 text-sm font-bold text-marigold-soft hover:opacity-90"
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}
