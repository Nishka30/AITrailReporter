import type { PublicConditionState, PublicObservation } from "@/lib/content";
import { timeAgoLabel } from "@/lib/content/freshness";

export function SafetyBanner({
  conditions,
  observations,
}: {
  conditions: PublicConditionState[];
  observations: PublicObservation[];
}) {
  const alerts = conditions.filter(
    (c) => c.safety_critical && (c.state === "aging" || c.state === "stale"),
  );
  if (alerts.length === 0) return null;

  return (
    <div className="mt-10 rounded-[28px] border border-fix/20 bg-gradient-to-br from-fix-soft to-fix-soft/50 p-5 shadow-warm sm:p-6">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-fix text-paper">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 9v4M12 17h.01M10.3 3.9 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
          </svg>
        </div>
        <div className="flex-1">
          <p className="font-heading text-base font-bold text-ink">Worth knowing before you go</p>
          <div className="mt-3 space-y-3">
            {alerts.map((a) => {
              const evidence = observations.find((o) => o.observation_id === a.latest_observation_id)?.evidence;
              return (
                <div key={a.knowledge_type} className="border-l-2 border-fix/40 pl-3">
                  <p className="text-sm font-semibold text-ink">
                    {a.display_name} — {timeAgoLabel(a.observed_at)}
                  </p>
                  {evidence && <p className="mt-0.5 text-sm text-ink-soft">{evidence}</p>}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
