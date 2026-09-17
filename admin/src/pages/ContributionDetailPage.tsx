import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, CheckCircle2, DollarSign, HelpCircle, MapPin, Phone } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { getContributionDetail, getContributionQueue } from '../api/admin';
import ContributionActions from '../components/contributions/ContributionActions';
import AudioPlayer from '../components/review/AudioPlayer';
import ImageViewer from '../components/review/ImageViewer';
import StatusBadge, { moderationLabel, moderationTone } from '../components/ui/StatusBadge';
import { ErrorState, LoadingState } from '../components/ui/States';

export default function ContributionDetailPage() {
  const { submissionId } = useParams<{ submissionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  // The filters the admin had applied to the Contribution Review queue when
  // they opened this item (see ContributionCard, which forwards them here).
  // Reused below to find "the next pending item under the same filters"
  // rather than an unrelated one.
  const submissionTypeFilter = searchParams.get('submission_type') || undefined;
  const qFilter = searchParams.get('q') || undefined;
  const searchSuffix = searchParams.toString() ? `?${searchParams.toString()}` : '';

  const [advancing, setAdvancing] = useState(false);
  const [caughtUp, setCaughtUp] = useState(false);

  const { data: detail, isLoading, isError, refetch } = useQuery({
    queryKey: ['contribution-detail', submissionId],
    queryFn: () => getContributionDetail(submissionId!),
    enabled: !!submissionId && !caughtUp,
  });

  /**
   * Fires after ContributionActions successfully approves/rejects the
   * current item. Rather than sending the admin back to the queue list, this
   * looks up the next still-pending item under the same filters and jumps
   * straight to it, so the admin can keep processing the queue one item
   * after another. Falls back to a "caught up" state once none remain.
   */
  const advanceToNext = async () => {
    setAdvancing(true);
    try {
      queryClient.invalidateQueries({ queryKey: ['contribution-queue'] });
      const next = await getContributionQueue({
        status: 'pending_review',
        submission_type: submissionTypeFilter,
        q: qFilter,
        page: 1,
        page_size: 1,
      });
      const nextItem = next.items.find((i) => i.submission_id !== submissionId) ?? next.items[0];
      if (nextItem) {
        navigate(`/contributions/${nextItem.submission_id}${searchSuffix}`, { replace: true });
      } else {
        setCaughtUp(true);
      }
    } finally {
      setAdvancing(false);
    }
  };

  if (caughtUp) {
    return (
      <div className="max-w-3xl">
        <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-paper-elevated p-10 text-center shadow-card">
          <CheckCircle2 className="h-10 w-10 text-ok" />
          <h1 className="font-heading text-xl font-extrabold text-ink">You're all caught up!</h1>
          <p className="text-sm text-ink-soft">
            No more pending contributions match {submissionTypeFilter || qFilter ? 'your current filters' : 'the review queue'}.
          </p>
          <Link
            to={`/contributions${searchSuffix}`}
            className="mt-2 rounded-full bg-marigold px-4 py-2 text-sm font-bold text-white"
          >
            Back to Review Queue
          </Link>
        </div>
      </div>
    );
  }

  if (isLoading) return <LoadingState />;
  if (isError || !detail) {
    return <ErrorState message="Could not load this contribution." onRetry={() => refetch()} />;
  }

  const { item, audio, photo, transcript, guide_phone_number } = detail;

  return (
    <div className="max-w-3xl">
      <button
        onClick={() => navigate(-1)}
        className="mb-4 flex items-center gap-1 text-sm font-bold text-ink-soft hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-extrabold text-ink">{item.guide_name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-ink-soft">
            <span>{item.submission_type}</span>
            <span>{new Date(item.submitted_at).toLocaleString()}</span>
            {guide_phone_number ? (
              <span className="flex items-center gap-1">
                <Phone className="h-3.5 w-3.5" /> {guide_phone_number}
              </span>
            ) : null}
          </div>
        </div>
        <StatusBadge label={moderationLabel(item.review.status)} tone={moderationTone(item.review.status)} />
      </div>

      <div className="space-y-5">
        {/* 1. What was submitted */}
        <section className="rounded-lg border border-border bg-paper-elevated p-5 shadow-card">
          <h2 className="mb-3 font-heading text-base font-bold text-ink">Contribution</h2>

          {item.question_text ? (
            <div className="mb-3 flex items-start gap-2 rounded-lg bg-paper-muted p-3 text-sm">
              <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-marigold-deep" />
              <div>
                <div className="text-xs font-bold uppercase text-ink-faint">Answering</div>
                <div className="italic text-ink">{item.question_text}</div>
              </div>
            </div>
          ) : null}

          {item.raw_text ? (
            <p className="whitespace-pre-wrap rounded-lg bg-paper-muted p-3 text-sm text-ink">
              {item.raw_text}
            </p>
          ) : (
            <p className="text-sm italic text-ink-faint">No text content.</p>
          )}

          {transcript ? (
            <div className="mt-3">
              <div className="text-xs font-bold text-ink-faint">Transcript ({transcript.status})</div>
              {transcript.transcript ? (
                <p className="mt-1 whitespace-pre-wrap rounded-lg bg-paper-muted p-3 text-sm text-ink">
                  {transcript.transcript}
                </p>
              ) : null}
            </div>
          ) : null}

          {audio ? (
            <div className="mt-3">
              <AudioPlayer submissionId={item.submission_id} />
            </div>
          ) : null}
          {photo ? (
            <div className="mt-3 max-w-sm">
              <ImageViewer submissionId={item.submission_id} />
            </div>
          ) : null}
        </section>

        {/* 2. Admin decision -- placed right after the contribution's own
             content so the admin can decide without scrolling past Reward
             or any other section below. */}
        <section className="rounded-lg border border-border bg-paper-elevated p-5 shadow-card">
          <h2 className="mb-3 font-heading text-base font-bold text-ink">Decision</h2>
          {item.review.decided_by ? (
            <div className="mb-3 text-sm text-ink-soft">
              Decided by <span className="font-bold">{item.review.decided_by}</span> on{' '}
              {item.review.decided_at ? new Date(item.review.decided_at).toLocaleString() : '—'}
              {item.review.rejection_reason ? <span> · Reason: {item.review.rejection_reason}</span> : null}
              {item.review.rejection_note ? (
                <div className="mt-1 italic">“{item.review.rejection_note}”</div>
              ) : null}
            </div>
          ) : null}
          {advancing ? (
            <div className="text-sm font-bold text-ink-soft">Saving decision and loading the next item…</div>
          ) : (
            <ContributionActions
              submissionId={item.submission_id}
              review={item.review}
              onChanged={async () => {
                queryClient.invalidateQueries({ queryKey: ['contribution-detail', submissionId] });
                await advanceToNext();
              }}
            />
          )}
        </section>

        {/* 3. Location + what it's worth -- kept in one section, right next
             to each other, so the admin can see what this contribution
             concerns and what approving it pays in the same glance. */}
        <section className="rounded-lg border border-border bg-paper-elevated p-5 shadow-card">
          <h2 className="mb-1 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-ink-faint">
            <MapPin className="h-3.5 w-3.5" /> Location
          </h2>
          {item.location_id ? (
            <Link
              to={`/places/${item.location_id}`}
              className="font-bold text-marigold-deep hover:underline"
            >
              {item.location_name}
            </Link>
          ) : (
            <span className="text-sm italic text-ink-faint">Location not specified</span>
          )}

          <h2 className="mb-3 mt-5 flex items-center gap-2 font-heading text-base font-bold text-ink">
            <DollarSign className="h-4 w-4 text-marigold" /> Reward
          </h2>
          {item.review.status === 'approved' ? (
            <div className="text-sm text-ink">
              Paid <span className="font-bold text-ok">{item.review.reward_points_awarded} points</span> under
              rule <code className="rounded bg-paper-muted px-1.5 py-0.5 text-xs">{item.review.reward_rule_key}</code>.
            </div>
          ) : item.review.status === 'rejected' ? (
            <div className="text-sm text-ink-soft">
              0 points awarded. This decision cannot be reversed to pay it retroactively.
            </div>
          ) : item.reward_breakdown.length === 0 ? (
            <p className="text-sm text-ink-faint">
              No active reward rule is currently configured for this contribution -- it would earn 0 points
              if approved.
            </p>
          ) : item.reward_breakdown.length === 1 ? (
            <div className="text-sm text-ink-soft">
              <span className="font-bold text-marigold-deep">+{item.current_rule_points} points</span> under
              rule <code className="rounded bg-paper-muted px-1.5 py-0.5 text-xs">{item.review.reward_rule_key}</code>{' '}
              if approved. No points have been granted yet.
            </div>
          ) : (
            <div>
              <div className="space-y-1.5">
                {item.reward_breakdown.map((line) => (
                  <div key={line.label} className="flex items-center justify-between text-sm text-ink-soft">
                    <span>{line.label}</span>
                    <span className="font-bold text-ink">{line.points} points</span>
                  </div>
                ))}
              </div>
              <div className="mt-2 flex items-center justify-between border-t border-border pt-2 text-sm">
                <span className="font-bold text-ink">Total upon approval</span>
                <span className="font-bold text-marigold-deep">{item.current_rule_points} points</span>
              </div>
              <p className="mt-2 text-xs text-ink-faint">No points have been granted yet.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
