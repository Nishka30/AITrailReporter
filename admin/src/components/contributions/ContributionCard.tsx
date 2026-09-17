import { HelpCircle, Image as ImageIcon, Mic, DollarSign, MapPin } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

import type { ContributionQueueItem } from '../../api/types';
import StatusBadge, { moderationLabel, moderationTone } from '../ui/StatusBadge';

/**
 * One row in the Contribution Review queue -- one Submission/answer being
 * reviewed for PAYMENT. Deliberately a separate card from ObservationCard:
 * this reviews a CONTRIBUTION (what a guide did and whether it's worth
 * paying for), not an extracted knowledge fact -- see
 * backend/app/db/models/submission_review.py for why these are two
 * different reviews of two different things.
 */
export default function ContributionCard({ item }: { item: ContributionQueueItem }) {
  // Carries the queue's current filters into the detail page so that
  // approve/reject there can advance to the next PENDING item under the
  // same filter/search the admin was working through, not an unfiltered one.
  const [searchParams] = useSearchParams();
  const search = searchParams.toString();

  return (
    <Link
      to={{ pathname: `/contributions/${item.submission_id}`, search }}
      className="block rounded-lg border border-border bg-paper-elevated p-4 shadow-card transition-shadow hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-heading text-base font-bold text-ink">{item.guide_name}</span>
            <StatusBadge
              label={moderationLabel(item.review.status)}
              tone={moderationTone(item.review.status)}
            />
            <span className="flex items-center gap-1 text-xs font-bold text-marigold-deep">
              <DollarSign className="h-3.5 w-3.5" />
              {item.review.status === 'approved'
                ? `${item.review.reward_points_awarded} pts paid`
                : `${item.current_rule_points} pts if approved`}
            </span>
          </div>
          {item.question_text ? (
            <div className="mt-1 flex items-start gap-1 text-sm text-ink-faint">
              <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span className="line-clamp-1 italic">{item.question_text}</span>
            </div>
          ) : null}
          {item.raw_text ? (
            <div className="mt-1 line-clamp-2 text-sm text-ink-soft">{item.raw_text}</div>
          ) : (
            <div className="mt-1 text-sm italic text-ink-faint">No text content</div>
          )}
          {item.location_name ? (
            <div className="mt-1 flex items-center gap-1 text-xs text-ink-faint">
              <MapPin className="h-3.5 w-3.5" /> {item.location_name}
            </div>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1 text-xs text-ink-faint">
          <span className="rounded-full bg-paper-muted px-2 py-0.5">{item.submission_type}</span>
          <span>{new Date(item.submitted_at).toLocaleString()}</span>
          <span className="flex items-center gap-2">
            {item.has_audio ? <Mic className="h-3.5 w-3.5" /> : null}
            {item.has_photo ? <ImageIcon className="h-3.5 w-3.5" /> : null}
          </span>
        </div>
      </div>
    </Link>
  );
}
