import { Navigate, Route, Routes } from 'react-router-dom';

import { useAdminAuth } from './auth/AdminAuthContext';
import AdminShell from './components/layout/AdminShell';
import ContributorDetailPage from './pages/ContributorDetailPage';
import ContributorsPage from './pages/ContributorsPage';
import KnowledgePage from './pages/KnowledgePage';
import LoginPage from './pages/LoginPage';
import OverviewPage from './pages/OverviewPage';
import PlaceDetailPage from './pages/PlaceDetailPage';
import PlacesPage from './pages/PlacesPage';
import QuestionsPage from './pages/QuestionsPage';
import ReviewDetailPage from './pages/ReviewDetailPage';
import ReviewQueuePage from './pages/ReviewQueuePage';

function RequireAuth({ children }: { children: React.ReactElement }) {
  const { auth } = useAdminAuth();
  if (!auth) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AdminShell />
          </RequireAuth>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="review-queue" element={<ReviewQueuePage />} />
        <Route path="review/:observationId" element={<ReviewDetailPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="knowledge/:observationId" element={<ReviewDetailPage />} />
        <Route path="places" element={<PlacesPage />} />
        <Route path="places/:locationId" element={<PlaceDetailPage />} />
        <Route path="contributors" element={<ContributorsPage />} />
        <Route path="contributors/:guideId" element={<ContributorDetailPage />} />
        <Route path="questions" element={<QuestionsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
