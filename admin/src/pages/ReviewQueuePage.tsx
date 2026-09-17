import { getReviewQueue } from '../api/admin';
import ObservationListView from '../components/review/ObservationListView';

export default function ReviewQueuePage() {
  return (
    <ObservationListView
      queryKey="review-queue"
      fetchFn={getReviewQueue}
      title="Content Review Queue"
      description="Extracted observations awaiting a moderation decision before they can ever be publicly visible -- switch the status filter above to browse approved or rejected ones too."
      defaultStatus="pending_review"
      showStatusFilter
    />
  );
}
