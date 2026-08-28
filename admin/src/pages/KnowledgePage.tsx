import { getKnowledge } from '../api/admin';
import ObservationListView from '../components/review/ObservationListView';

export default function KnowledgePage() {
  return (
    <ObservationListView
      queryKey="knowledge"
      fetchFn={getKnowledge}
      title="Knowledge"
      description="Every extracted observation, at every moderation status -- not just what's pending."
      defaultStatus=""
      showStatusFilter
    />
  );
}
