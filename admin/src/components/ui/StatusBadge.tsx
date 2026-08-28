import type { ReactNode } from 'react';

export type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'brand';

const TONE_CLASSES: Record<BadgeTone, string> = {
  success: 'bg-ok-soft text-ok',
  warning: 'bg-marigold-soft text-marigold-deep',
  danger: 'bg-fix-soft text-fix',
  info: 'bg-info-soft text-info',
  neutral: 'bg-neutral-soft text-ink-soft',
  brand: 'bg-ink text-marigold-soft',
};

/** The single status-communication primitive for the admin app -- mirrors
 * mobile/src/components/ui/Badge.tsx's tone system exactly, so a status
 * reads the same way in both apps. */
export default function StatusBadge({
  label,
  tone = 'neutral',
  icon,
}: {
  label: string;
  tone?: BadgeTone;
  icon?: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-bold ${TONE_CLASSES[tone]}`}
    >
      {icon}
      {label}
    </span>
  );
}

export function moderationTone(status: string): BadgeTone {
  if (status === 'approved') return 'success';
  if (status === 'rejected') return 'danger';
  return 'warning';
}

export function moderationLabel(status: string): string {
  if (status === 'approved') return 'Approved';
  if (status === 'rejected') return 'Rejected';
  return 'Pending review';
}
