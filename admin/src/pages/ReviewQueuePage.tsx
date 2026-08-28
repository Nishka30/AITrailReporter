import { getReviewQueue } from '../api/admin';
import ObservationListView from '../components/review/ObservationListView';

export default function ReviewQueuePage() {
  return (
    <ObservationListView
      queryKey="review-queue"
      fetchFn={getReviewQueue}
      title="Review Queue"
      description="Observations awaiting a human decision before they can ever be publicly visible."
      defaultStatus="pending_review"
      showStatusFilter
    />
  );
}
