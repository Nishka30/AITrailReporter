import type { PublicConditionState, PublicObservation } from "@/lib/content";
import { timeAgoLabel } from "@/lib/content/freshness";
import { Icon } from "./guide/Icons";

/** Safety-critical conditions whose latest report is getting old -- shown
 * once, near the top of a place page, in the reference's quiet notice style. */
export function SafetyBanner({ conditions, observations }: { conditions: PublicConditionState[]; observations: PublicObservation[] }) {
  const alerts = conditions.filter((c) => c.safety_critical && (c.state === "aging" || c.state === "stale"));
  if (alerts.length === 0) return null;

  return (
    <div className="mt-8 flex gap-4 rounded-[8px] border border-[#ecd9a8] bg-[#fbf6e7] px-6 py-5">
      <Icon name="flag" size={20} className="mt-0.5 shrink-0 text-marigold-deep" />
      <div className="flex-1">
        <p className="text-[16px] font-bold text-ink">Worth checking before you go</p>
        <ul className="mt-2 space-y-2">
          {alerts.map((a) => {
            const evidence = observations.find((o) => o.observation_id === a.latest_observation_id)?.evidence;
            return (
              <li key={a.knowledge_type} className="text-[14.5px] leading-[1.7] text-ink-soft">
                <span className="font-semibold text-ink">{a.display_name}</span> — last reported {timeAgoLabel(a.observed_at).toLowerCase().replace(/^(updated|reported) /, "")}
                {evidence && <span>: {evidence}</span>}
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-[13px] text-ink-meta">These are safety-relevant and due for a fresh local check.</p>
      </div>
    </div>
  );
}
