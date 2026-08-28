import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowLeft, Sparkles } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { getReviewDetail } from '../api/admin';
import type { KnowledgeTypeState } from '../api/types';
import AudioPlayer from '../components/review/AudioPlayer';
import ImageViewer from '../components/review/ImageViewer';
import ModerationActions from '../components/review/ModerationActions';
import StatusBadge, { moderationLabel, moderationTone } from '../components/ui/StatusBadge';
import { ErrorState, LoadingState } from '../components/ui/States';

const GAP_STATE_TONE: Record<KnowledgeTypeState['state'], 'success' | 'warning' | 'danger' | 'neutral'> = {
  fresh: 'success',
  aging: 'warning',
  stale: 'danger',
  missing: 'neutral',
};

export default function ReviewDetailPage() {
  const { observationId } = useParams<{ observationId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: detail, isLoading, isError, refetch } = useQuery({
    queryKey: ['review-detail', observationId],
    queryFn: () => getReviewDetail(observationId!),
    enabled: !!observationId,
  });

  if (isLoading) return <LoadingState />;
  if (isError || !detail) return <ErrorState message="Could not load this observation." onRetry={() => refetch()} />;

  const { observation, source, knowledge_context, related_observations, sibling_observations } = detail;

  return (
    <div className="max-w-4xl">
      <button
        onClick={() => navigate(-1)}
        className="mb-4 flex items-center gap-1 text-sm font-bold text-ink-soft hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-heading text-2xl font-extrabold text-ink">{observation.display_name}</h1>
            {observation.safety_critical ? (
              <span className="flex items-center gap-1 text-fix">
                <AlertTriangle className="h-4 w-4" /> Safety critical
              </span>
            ) : null}
          </div>
          <div className="mt-1 text-sm text-ink-soft">
            Reported by {observation.guide_name} · {new Date(observation.observed_at).toLocaleString()}
          </div>
        </div>
        <StatusBadge
          label={moderationLabel(observation.moderation.status)}
          tone={moderationTone(observation.moderation.status)}
        />
      </div>

      <div className="space-y-5">
        {/* 1. Source */}
        <section className="rounded-lg border border-border bg-paper-elevated p-5 shadow-card">
          <h2 className="mb-3 font-heading text-base font-bold text-ink">Source</h2>
          <div className="text-xs text-ink-faint">
            Submission type: {source.submission_type} · Submitted{' '}
            {new Date(source.submitted_at).toLocaleString()}
          </div>
          {source.raw_text ? (
            <p className="mt-2 whitespace-pre-wrap rounded-lg bg-paper-muted p-3 text-sm text-ink">
              {source.raw_text}
            </p>
          ) : null}
          {source.transcript ? (
            <div className="mt-3">
              <div className="text-xs font-bold text-ink-faint">Transcript ({source.transcript.status})</div>
              {source.transcript.transcript ? (
                <p className="mt-1 whitespace-pre-wrap rounded-lg bg-paper-muted p-3 text-sm text-ink">
                  {source.transcript.transcript}
                </p>
              ) : null}
            </div>
          ) : null}
          {source.audio ? (
            <div className="mt-3">
              <AudioPlayer submissionId={source.submission_id} />
            </div>
          ) : null}
          {source.photo ? (
            <div className="mt-3 max-w-sm">
              <ImageViewer submissionId={source.submission_id} />
            </div>
          ) : null}

          {sibling_observations.length > 0 ? (
            <div className="mt-4 border-t border-border pt-3 text-sm text-ink-soft">
              This submission also produced {sibling_observations.length} other observation
              {sibling_observations.length === 1 ? '' : 's'}:{' '}
              {sibling_observations.map((sib, i) => (
                <span key={sib.observation_id}>
                  {i > 0 ? ', ' : ''}
                  <Link to={`/review/${sib.observation_id}`} className="font-bold text-marigold-deep hover:underline">
                    {sib.display_name}
                  </Link>{' '}
                  ({moderationLabel(sib.moderation_status)})
                </span>
              ))}
            </div>
          ) : null}
        </section>

        {/* 2. AI Extracted Knowledge */}
        <section className="rounded-lg border border-border bg-paper-elevated p-5 shadow-card">
          <h2 className="mb-3 flex items-center gap-2 font-heading text-base font-bold text-ink">
            <Sparkles className="h-4 w-4 text-marigold" /> AI Extracted Knowledge
          </h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            {Object.entries(observation.value).map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs font-bold uppercase text-ink-faint">{k}</dt>
                <dd className="text-ink">{String(v)}</dd>
              </div>
            ))}
          </dl>
          {observation.evidence ? (
            <p className="mt-3 border-l-2 border-marigold pl-3 text-sm italic text-ink-soft">
              “{observation.evidence}”
            </p>
          ) : null}
          {observation.confidence !== null ? (
            <div className="mt-2 text-xs text-ink-faint">
              Confidence: {(observation.confidence * 100).toFixed(0)}%
            </div>
          ) : null}
        </section>

        {/* 3. Knowledge Context */}
        <section className="rounded-lg border border-border bg-paper-elevated p-5 shadow-card">
          <h2 className="mb-3 font-heading text-base font-bold text-ink">Knowledge Context</h2>
          {!knowledge_context ? (
            <p className="text-sm text-ink-faint">
              No coordinate is known for this observation, so live knowledge state can't be evaluated here.
            </p>
          ) : (
            <div className="space-y-2">
              {knowledge_context.knowledge_types.map((kt) => (
                <div key={kt.knowledge_type_id} className="flex items-center justify-between text-sm">
                  <span className="text-ink-soft">{kt.display_name}</span>
                  <StatusBadge label={kt.state} tone={GAP_STATE_TONE[kt.state]} />
                </div>
              ))}
            </div>
          )}

          {related_observations.length > 0 ? (
            <div className="mt-4 border-t border-border pt-3">
              <div className="mb-2 text-xs font-bold uppercase text-ink-faint">
                Other reports of {observation.display_name} nearby
              </div>
              <p className="mb-2 text-xs text-ink-faint">
                No automatic conflict detection exists yet -- review these yourself for
                duplicates or contradictions.
              </p>
              <div className="space-y-2">
                {related_observations.map((rel) => (
                  <div key={rel.observation_id} className="rounded-lg bg-paper-muted p-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-ink">{rel.guide_name}</span>
                      <StatusBadge label={moderationLabel(rel.moderation_status)} tone={moderationTone(rel.moderation_status)} />
                    </div>
                    <div className="text-ink-soft">{JSON.stringify(rel.value)}</div>
                    <div className="text-xs text-ink-faint">
                      {new Date(rel.observed_at).toLocaleString()}
                      {rel.distance_meters !== null ? ` · ${Math.round(rel.distance_meters)}m away` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>

        {/* 4. Admin Decision */}
        <section className="rounded-lg border border-border bg-paper-elevated p-5 shadow-card">
          <h2 className="mb-3 font-heading text-base font-bold text-ink">Admin Decision</h2>
          {observation.moderation.decided_by ? (
            <div className="mb-3 text-sm text-ink-soft">
              Decided by <span className="font-bold">{observation.moderation.decided_by}</span> on{' '}
              {observation.moderation.decided_at
                ? new Date(observation.moderation.decided_at).toLocaleString()
                : '—'}
              {observation.moderation.rejection_reason ? (
                <span> · Reason: {observation.moderation.rejection_reason}</span>
              ) : null}
              {observation.moderation.rejection_note ? (
                <div className="mt-1 italic">“{observation.moderation.rejection_note}”</div>
              ) : null}
            </div>
          ) : null}
          <ModerationActions
            observationId={observation.observation_id}
            moderation={observation.moderation}
            onChanged={() => queryClient.invalidateQueries({ queryKey: ['review-detail', observationId] })}
          />
        </section>
      </div>
    </div>
  );
}
