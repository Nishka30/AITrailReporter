import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Coins, Pencil, Plus, Search } from 'lucide-react';
import { useState } from 'react';

import { createRewardRule, getRewardRules, updateRewardRule } from '../api/admin';
import type { RewardRule } from '../api/types';
import PageHeader from '../components/layout/PageHeader';
import RewardRuleDialog from '../components/points/RewardRuleDialog';
import StatusBadge from '../components/ui/StatusBadge';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';

/**
 * The admin-facing view of reward_rules -- the SAME table
 * reward_service.award() resolves at approval time and GET
 * /api/v1/rewards/config serves to the mobile app (see
 * backend/app/services/admin_rewards.py). There is no separate
 * points/config system here: editing a rule's points on this page changes
 * what the backend actually pays, immediately, for every future approval.
 */
export default function PointsPage() {
  const [q, setQ] = useState('');
  const [dialogRule, setDialogRule] = useState<RewardRule | 'new' | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['reward-rules', q],
    queryFn: () => getRewardRules({ q: q || undefined }),
  });

  return (
    <div>
      <PageHeader
        title="Points Rules"
        description="The reward rules that decide how many points a contribution earns. Changes here apply to future approvals immediately -- mobile and Contribution Review both read these same values."
        actions={
          <button
            onClick={() => setDialogRule('new')}
            className="flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-bold text-marigold-soft hover:opacity-90"
          >
            <Plus className="h-4 w-4" /> Add Point Rule
          </button>
        }
      />

      <div className="mb-4 flex items-center gap-2 rounded-lg border border-border bg-paper-elevated p-3">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-paper px-3 py-1.5">
          <Search className="h-4 w-4 text-ink-faint" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search rules by key or description…"
            className="w-64 bg-transparent text-sm outline-none"
          />
        </div>
      </div>

      {isLoading ? <LoadingState /> : null}
      {isError ? <ErrorState message="Could not load reward rules." onRetry={() => refetch()} /> : null}
      {data && data.length === 0 ? (
        <EmptyState
          title="No reward rules"
          description={q ? 'No rules match this search.' : 'No reward rules have been configured yet.'}
          icon={<Coins className="h-8 w-8" />}
        />
      ) : null}

      {data && data.length > 0 ? (
        <div className="overflow-hidden rounded-lg border border-border bg-paper-elevated shadow-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-paper-muted text-xs font-bold uppercase text-ink-faint">
              <tr>
                <th className="px-4 py-3 text-left">Rule</th>
                <th className="px-4 py-3 text-right">Points</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Last updated</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {data.map((rule) => (
                <tr key={rule.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3">
                    <div className="font-bold text-ink">{rule.description || rule.rule_key}</div>
                    <div className="text-xs text-ink-faint">{rule.rule_key}</div>
                  </td>
                  <td className="px-4 py-3 text-right font-bold text-marigold-deep">{rule.points}</td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      label={rule.active ? 'Active' : 'Inactive'}
                      tone={rule.active ? 'success' : 'neutral'}
                    />
                  </td>
                  <td className="px-4 py-3 text-xs text-ink-faint">
                    {new Date(rule.updated_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setDialogRule(rule)}
                      className="flex items-center gap-1 rounded-full border border-border px-3 py-1.5 text-xs font-bold text-ink-soft hover:bg-paper-muted"
                    >
                      <Pencil className="h-3.5 w-3.5" /> Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {dialogRule ? (
        <RewardRuleDialog
          rule={dialogRule === 'new' ? null : dialogRule}
          onClose={() => setDialogRule(null)}
          onSave={async (payload) => {
            if (dialogRule === 'new') {
              await createRewardRule(payload);
            } else {
              await updateRewardRule(dialogRule.id, {
                points: payload.points,
                description: payload.description,
                active: payload.active,
              });
            }
            queryClient.invalidateQueries({ queryKey: ['reward-rules'] });
            queryClient.invalidateQueries({ queryKey: ['reward-rule-history'] });
          }}
        />
      ) : null}
    </div>
  );
}
