import { AlertTriangle, Mic, Image as ImageIcon, MessageSquare, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { ReviewQueueItem } from '../../api/types';
import StatusBadge, { moderationLabel, moderationTone } from '../ui/StatusBadge';

const SOURCE_ICON: Record<string, typeof Mic> = {
  voice: Mic,
  explore: ImageIcon,
  note: MessageSquare,
  answer: MessageSquare,
};

function formatValue(value: Record<string, unknown>): string {
  try {
    const entries = Object.entries(value);
    if (entries.length === 0) return '—';
    return entries.map(([k, v]) => `${k}: ${String(v)}`).join(' · ');
  } catch {
    return '—';
  }
}

export default function ObservationCard({ item }: { item: ReviewQueueItem }) {
  const SourceIcon = SOURCE_ICON[item.submission_type] ?? MessageSquare;

  return (
    <Link
      to={`/review/${item.observation_id}`}
      className="block rounded-lg border border-border bg-paper-elevated p-4 shadow-card transition-shadow hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-heading text-base font-bold text-ink">{item.display_name}</span>
            {item.safety_critical ? (
              <span title="Safety critical">
                <AlertTriangle className="h-4 w-4 text-fix" />
              </span>
            ) : null}
            {item.knowledge_type_is_new ? <StatusBadge label="New type" tone="info" /> : null}
            <StatusBadge
              label={moderationLabel(item.moderation.status)}
              tone={moderationTone(item.moderation.status)}
            />
          </div>
          <div className="mt-1 truncate text-sm text-ink-soft">{formatValue(item.value)}</div>
          {item.evidence ? (
            <div className="mt-1 line-clamp-2 text-sm italic text-ink-faint">“{item.evidence}”</div>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1 text-xs text-ink-faint">
          <span className="flex items-center gap-1">
            <SourceIcon className="h-3.5 w-3.5" /> {item.guide_name}
          </span>
          <span>{new Date(item.observed_at).toLocaleString()}</span>
          {item.confidence !== null ? (
            <span className="flex items-center gap-1">
              <Sparkles className="h-3.5 w-3.5" /> {(item.confidence * 100).toFixed(0)}% confidence
            </span>
          ) : null}
        </div>
      </div>
    </Link>
  );
}
