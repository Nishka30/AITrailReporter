import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowLeft, CheckCircle2, MapPin, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { getReviewDetail, getReviewQueue } from '../api/admin';
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
  const [searchParams] = useSearchParams();

  // The filters the admin had applied to the Review Queue when they opened
  // this item (see ObservationCard, which forwards them here). Reused below
  // to find "the next pending item under the same filters" rather than an
  // unrelated one.
  const knowledgeTypeFilter = searchParams.get('knowledge_type') || undefined;
  const safetyCriticalFilter = searchParams.get('safety_critical')
    ? searchParams.get('safety_critical') === 'true'
    : undefined;
  const sourceTypeFilter = searchParams.get('source_type') || undefined;
  const qFilter = searchParams.get('q') || undefined;
  const sortFilter = searchParams.get('sort') || undefined;
  const searchSuffix = searchParams.toString() ? `?${searchParams.toString()}` : '';

  const [advancing, setAdvancing] = useState(false);
  const [caughtUp, setCaughtUp] = useState(false);

  const { data: detail, isLoading, isError, refetch } = useQuery({
    queryKey: ['review-detail', observationId],
    queryFn: () => getReviewDetail(observationId!),
    enabled: !!observationId && !caughtUp,
  });

  /**
   * Fires after ModerationActions successfully approves/rejects the current
   * item -- but only when it was the initial pending_review decision, not a
   * later change-decision reversal on an already-decided item (see the
   * onChanged call site below, which gates this on the PRE-decision status).
   * Looks up the next still-pending item under the same filters and jumps
   * straight to it, so the admin can keep processing the queue one item
   * after another. Falls back to a "caught up" state once none remain.
   */
  const advanceToNext = async () => {
    setAdvancing(true);
    try {
      queryClient.invalidateQueries({ queryKey: ['review-queue'] });
      const next = await getReviewQueue({
        status: 'pending_review',
        knowledge_type: knowledgeTypeFilter,
        safety_critical: safetyCriticalFilter,
        source_type: sourceTypeFilter,
        q: qFilter,
        sort: sortFilter,
        page: 1,
        page_size: 1,
      });
      const nextItem = next.items.find((i) => i.observation_id !== observationId) ?? next.items[0];
      if (nextItem) {
        navigate(`/review/${nextItem.observation_id}${searchSuffix}`, { replace: true });
      } else {
        setCaughtUp(true);
      }
    } finally {
      setAdvancing(false);
    }
  };

  if (caughtUp) {
    return (
      <div className="max-w-4xl">
        <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-paper-elevated p-10 text-center shadow-card">
          <CheckCircle2 className="h-10 w-10 text-ok" />
          <h1 className="font-heading text-xl font-extrabold text-ink">You're all caught up!</h1>
          <p className="text-sm text-ink-soft">
            No more pending observations match{' '}
            {knowledgeTypeFilter || safetyCriticalFilter || sourceTypeFilter || qFilter
              ? 'your current filters'
              : 'the review queue'}
            .
          </p>
          <Link
            to={`/review-queue${searchSuffix}`}
            className="mt-2 rounded-full bg-marigold px-4 py-2 text-sm font-bold text-white"
          >
            Back to Review Queue
          </Link>
        </div>
      </div>
    );
  }

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
          <div className="mt-1 flex items-center gap-1 text-xs text-ink-faint">
            <MapPin className="h-3.5 w-3.5" />
            {observation.nearest_known_place_name ? (
              <>
                Near {observation.nearest_known_place_name}
                {observation.nearest_known_place_distance_meters !== null &&
                observation.nearest_known_place_distance_meters !== undefined ? (
                  <span className="italic">
                    {' '}
                    (~{Math.round(observation.nearest_known_place_distance_meters)}m away)
                  </span>
                ) : null}
              </>
            ) : (
              <span className="italic">Location not specified</span>
            )}
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

        {/* 3. Admin Decision -- placed right after Source + AI Extracted
             Knowledge (the content actually being judged) so the admin can
             decide without scrolling past Knowledge Context below. */}
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
          {advancing ? (
            <div className="text-sm font-bold text-ink-soft">Saving decision and loading the next item…</div>
          ) : (
            <ModerationActions
              observationId={observation.observation_id}
              moderation={observation.moderation}
              onChanged={async () => {
                queryClient.invalidateQueries({ queryKey: ['review-detail', observationId] });
                // Only auto-advance on the initial pending_review decision --
                // not on a change-decision reversal of an already-decided item.
                if (observation.moderation.status === 'pending_review') {
                  await advanceToNext();
                }
              }}
            />
          )}
        </section>

        {/* 4. Knowledge Context */}
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
      </div>
    </div>
  );
}
