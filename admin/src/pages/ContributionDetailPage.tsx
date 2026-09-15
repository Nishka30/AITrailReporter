import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, DollarSign, HelpCircle, MapPin, Phone } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { getContributionDetail } from '../api/admin';
import ContributionActions from '../components/contributions/ContributionActions';
import AudioPlayer from '../components/review/AudioPlayer';
import ImageViewer from '../components/review/ImageViewer';
import StatusBadge, { moderationLabel, moderationTone } from '../components/ui/StatusBadge';
import { ErrorState, LoadingState } from '../components/ui/States';

export default function ContributionDetailPage() {
  const { submissionId } = useParams<{ submissionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: detail, isLoading, isError, refetch } = useQuery({
    queryKey: ['contribution-detail', submissionId],
    queryFn: () => getContributionDetail(submissionId!),
    enabled: !!submissionId,
  });

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

          {item.location_id ? (
            <div className="mt-3 flex items-center gap-1 text-sm text-ink-soft">
              <MapPin className="h-4 w-4" />
              <Link to={`/places/${item.location_id}`} className="font-bold text-marigold-deep hover:underline">
                {item.location_name}
              </Link>
            </div>
          ) : null}
        </section>

        {/* 2. What it's worth */}
        <section className="rounded-lg border border-border bg-paper-elevated p-5 shadow-card">
          <h2 className="mb-3 flex items-center gap-2 font-heading text-base font-bold text-ink">
            <DollarSign className="h-4 w-4 text-marigold" /> Reward
          </h2>
          {item.review.status === 'approved' ? (
            <div className="text-sm text-ink">
              Paid <span className="font-bold text-ok">{item.review.reward_points_awarded} points</span> under
              rule <code className="rounded bg-paper-muted px-1.5 py-0.5 text-xs">{item.review.reward_rule_key}</code>.
            </div>
          ) : item.review.status === 'rejected' ? (
            <div className="text-sm text-ink-soft">
              No points were awarded. This decision cannot be reversed to pay it retroactively.
            </div>
          ) : (
            <div className="text-sm text-ink-soft">
              Currently worth{' '}
              <span className="font-bold text-marigold-deep">{item.current_rule_points} points</span> under rule{' '}
              <code className="rounded bg-paper-muted px-1.5 py-0.5 text-xs">{item.review.reward_rule_key}</code>{' '}
              if approved. No points have been granted yet.
            </div>
          )}
        </section>

        {/* 3. Admin decision */}
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
          <ContributionActions
            submissionId={item.submission_id}
            review={item.review}
            onChanged={() =>
              queryClient.invalidateQueries({ queryKey: ['contribution-detail', submissionId] })
            }
          />
        </section>
      </div>
    </div>
  );
}
