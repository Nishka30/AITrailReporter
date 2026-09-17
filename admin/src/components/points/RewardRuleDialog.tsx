import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { getRewardRuleHistory } from '../../api/admin';
import type { RewardRule } from '../../api/types';

export type RewardRuleFormPayload = {
  rule_key: string;
  points: number;
  description: string | null;
  active: boolean;
};

const RULE_KEY_PATTERN = /^[a-z][a-z0-9_]*$/;

/**
 * Create/edit form for one reward rule. `rule_key` is only editable when
 * creating a new rule -- every award() call site in the backend resolves a
 * LITERAL key baked into code, so renaming an existing key here would
 * silently orphan whatever still references the old one (see
 * backend/app/services/admin_rewards.py's update_rule docstring).
 *
 * A points CHANGE on an existing rule requires an extra confirmation step
 * before it saves, since it's the one edit here with a real financial
 * effect on future approvals.
 */
export default function RewardRuleDialog({
  rule,
  onSave,
  onClose,
}: {
  rule: RewardRule | null;
  onSave: (payload: RewardRuleFormPayload) => Promise<void>;
  onClose: () => void;
}) {
  const isEditing = rule !== null;
  const [ruleKey, setRuleKey] = useState(rule?.rule_key ?? '');
  const [points, setPoints] = useState(rule ? String(rule.points) : '');
  const [description, setDescription] = useState(rule?.description ?? '');
  const [active, setActive] = useState(rule?.active ?? true);
  const [confirmingPointsChange, setConfirmingPointsChange] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: history } = useQuery({
    queryKey: ['reward-rule-history', rule?.id],
    queryFn: () => getRewardRuleHistory(rule!.id),
    enabled: isEditing,
  });

  const trimmedKey = ruleKey.trim();
  const pointsNum = Number(points);
  const ruleKeyValid = RULE_KEY_PATTERN.test(trimmedKey);
  const pointsValid = points.trim() !== '' && Number.isInteger(pointsNum) && pointsNum >= 0;
  const canSubmit = ruleKeyValid && pointsValid;
  const pointsChanged = isEditing && rule.points !== pointsNum;

  const doSave = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onSave({
        rule_key: trimmedKey,
        points: pointsNum,
        description: description.trim() || null,
        active,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
      setConfirmingPointsChange(false);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSaveClick = () => {
    if (!canSubmit) return;
    if (pointsChanged && !confirmingPointsChange) {
      setConfirmingPointsChange(true);
      return;
    }
    doSave();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-6" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-lg bg-paper-elevated p-6 shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="font-heading text-lg font-bold text-ink">
          {isEditing ? 'Edit point rule' : 'Add point rule'}
        </h2>

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-sm font-bold text-ink-soft" htmlFor="rule-key">
              Rule key
            </label>
            <input
              id="rule-key"
              value={ruleKey}
              onChange={(e) => setRuleKey(e.target.value)}
              disabled={isEditing}
              placeholder="e.g. place_question_hazard"
              className="mt-1 w-full rounded-lg border border-border bg-paper p-2.5 text-sm disabled:bg-paper-muted disabled:text-ink-faint"
            />
            <p className="mt-1 text-xs text-ink-faint">
              {isEditing
                ? "The stable identifier this rule resolves against -- can't be changed once created."
                : 'Lowercase letters, numbers, and underscores only, starting with a letter.'}
            </p>
            {!isEditing && ruleKey.trim() && !ruleKeyValid ? (
              <p className="mt-1 text-xs text-fix">Use lowercase snake_case, e.g. "explore_contribution".</p>
            ) : null}
          </div>

          <div>
            <label className="text-sm font-bold text-ink-soft" htmlFor="rule-description">
              Description
            </label>
            <textarea
              id="rule-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="What earns this reward, in plain language…"
              className="mt-1 w-full rounded-lg border border-border bg-paper p-2.5 text-sm"
            />
          </div>

          <div>
            <label className="text-sm font-bold text-ink-soft" htmlFor="rule-points">
              Points
            </label>
            <input
              id="rule-points"
              type="number"
              min={0}
              step={1}
              value={points}
              onChange={(e) => {
                setPoints(e.target.value);
                setConfirmingPointsChange(false);
              }}
              className="mt-1 w-full rounded-lg border border-border bg-paper p-2.5 text-sm"
            />
            {points.trim() !== '' && !pointsValid ? (
              <p className="mt-1 text-xs text-fix">Points must be a whole number, 0 or greater.</p>
            ) : null}
          </div>

          <label className="flex items-center gap-2 text-sm font-bold text-ink-soft">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
            Active (counts toward live reward calculations)
          </label>
        </div>

        {isEditing && history && history.length > 0 ? (
          <div className="mt-4 border-t border-border pt-3">
            <div className="mb-1.5 text-xs font-bold uppercase text-ink-faint">Points history</div>
            <div className="max-h-24 space-y-1 overflow-y-auto text-xs text-ink-soft">
              {history.map((change) => (
                <div key={change.id}>
                  <span className="font-bold">{change.changed_by}</span>{' '}
                  {change.previous_points === null ? (
                    <>
                      created it at <span className="font-bold">{change.new_points}</span> points
                    </>
                  ) : (
                    <>
                      changed <span className="font-bold">{change.previous_points}</span> {'→'}{' '}
                      <span className="font-bold">{change.new_points}</span> points
                    </>
                  )}
                  {' · '}
                  {new Date(change.changed_at).toLocaleString()}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {confirmingPointsChange ? (
          <div className="mt-4 rounded-lg border border-marigold bg-marigold-soft p-3 text-sm text-marigold-deep">
            Change <span className="font-bold">{rule?.rule_key}</span> from{' '}
            <span className="font-bold">{rule?.points} points</span> to{' '}
            <span className="font-bold">{pointsNum} points</span>? This affects future approvals only --
            contributions already paid keep the points they were actually awarded.
          </div>
        ) : null}

        {error ? <div className="mt-3 text-sm text-fix">{error}</div> : null}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-full border border-border px-4 py-2 text-sm font-bold text-ink-soft"
          >
            Cancel
          </button>
          <button
            onClick={handleSaveClick}
            disabled={submitting || !canSubmit}
            className="rounded-full bg-ink px-4 py-2 text-sm font-bold text-marigold-soft disabled:opacity-50"
          >
            {submitting
              ? 'Saving…'
              : confirmingPointsChange
                ? 'Yes, save changes'
                : isEditing
                  ? 'Save changes'
                  : 'Add rule'}
          </button>
        </div>
      </div>
    </div>
  );
}
