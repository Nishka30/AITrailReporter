import { API_BASE_URL, ApiError, NetworkError, apiRequest } from './client';
import type {
  AdminOverview,
  AdminQuestionSummary,
  ContributorDetail,
  ContributorSummary,
  ObservationModeration,
  PlaceDetail,
  PlaceSummary,
  ReviewDetail,
  ReviewQueueFilters,
  ReviewQueueResult,
  RejectionReason,
} from './types';

function toQueryString(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

export function verifyAdminToken(): Promise<{ ok: boolean; name: string }> {
  return apiRequest('/api/v1/admin/auth/verify', { method: 'POST' });
}

/** Verifies a token BEFORE it's stored anywhere (the login screen calls this
 * with whatever was just typed, not whatever readStoredAuth() would return --
 * apiRequest's storage-based header injection doesn't apply here). */
export async function verifyAdminTokenExplicit(
  token: string,
  name: string
): Promise<{ ok: boolean; name: string }> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/admin/auth/verify`, {
      method: 'POST',
      headers: { 'X-Admin-Token': token, 'X-Admin-Name': name },
    });
  } catch (err) {
    throw new NetworkError(err);
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && typeof payload.detail === 'string'
        ? payload.detail
        : `Request failed with status ${response.status}`;
    throw new ApiError(response.status, detail, payload);
  }
  return payload;
}

export function getOverview(): Promise<AdminOverview> {
  return apiRequest('/api/v1/admin/overview');
}

export function getReviewQueue(filters: ReviewQueueFilters): Promise<ReviewQueueResult> {
  return apiRequest(`/api/v1/admin/review-queue${toQueryString(filters)}`);
}

export function getKnowledge(filters: ReviewQueueFilters): Promise<ReviewQueueResult> {
  return apiRequest(`/api/v1/admin/knowledge${toQueryString(filters)}`);
}

export function getReviewDetail(observationId: string): Promise<ReviewDetail> {
  return apiRequest(`/api/v1/admin/reviews/${observationId}`);
}

export function approveObservation(observationId: string): Promise<ObservationModeration> {
  return apiRequest(`/api/v1/admin/reviews/${observationId}/approve`, { method: 'POST' });
}

export function rejectObservation(
  observationId: string,
  reason: RejectionReason,
  note?: string
): Promise<ObservationModeration> {
  return apiRequest(`/api/v1/admin/reviews/${observationId}/reject`, {
    method: 'POST',
    body: { reason, note: note || null },
  });
}

export function changeObservationDecision(
  observationId: string,
  status: 'approved' | 'rejected',
  reason?: RejectionReason,
  note?: string
): Promise<ObservationModeration> {
  return apiRequest(`/api/v1/admin/reviews/${observationId}/change-decision`, {
    method: 'POST',
    body: { status, reason: reason || null, note: note || null },
  });
}

export function getPlaces(): Promise<PlaceSummary[]> {
  return apiRequest('/api/v1/admin/places');
}

export function getPlaceDetail(locationId: string): Promise<PlaceDetail> {
  return apiRequest(`/api/v1/admin/places/${locationId}`);
}

export function getContributors(): Promise<ContributorSummary[]> {
  return apiRequest('/api/v1/admin/contributors');
}

export function getContributorDetail(guideId: string): Promise<ContributorDetail> {
  return apiRequest(`/api/v1/admin/contributors/${guideId}`);
}

export function getAdminQuestions(filters: {
  status?: string;
  assignment_status?: string;
  safety_critical?: boolean;
}): Promise<AdminQuestionSummary[]> {
  return apiRequest(`/api/v1/admin/questions${toQueryString(filters)}`);
}
