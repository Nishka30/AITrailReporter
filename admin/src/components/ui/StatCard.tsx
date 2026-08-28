import type { ReactNode } from 'react';

export default function StatCard({
  label,
  value,
  icon,
  tone = 'default',
}: {
  label: string;
  value: number | string;
  icon?: ReactNode;
  tone?: 'default' | 'warning' | 'danger';
}) {
  const valueClass =
    tone === 'warning' ? 'text-marigold-deep' : tone === 'danger' ? 'text-fix' : 'text-ink';
  return (
    <div className="rounded-lg border border-border bg-paper-elevated p-5 shadow-card">
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold text-ink-soft">{label}</span>
        {icon ? <span className="text-marigold">{icon}</span> : null}
      </div>
      <div className={`mt-2 font-heading text-3xl font-extrabold ${valueClass}`}>{value}</div>
    </div>
  );
}
