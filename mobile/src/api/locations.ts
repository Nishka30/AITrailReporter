import { apiRequest } from './client';

export interface CreateLocationRequest {
  guideId: string;
  /** Makes this call idempotent — see backend GuideLocation.client_location_id. */
  clientLocationId: string;
  latitude: number;
  longitude: number;
  accuracyMeters: number | null;
  /** ISO-8601, timezone-aware — when the device captured this fix. */
  recordedAt: string;
}

export interface LocationResponse {
  id: string;
  guideId: string;
  clientLocationId: string | null;
  latitude: number;
  longitude: number;
  accuracyMeters: number | null;
  recordedAt: string;
  receivedAt: string;
  createdAt: string;
}

interface LocationResponseWire {
  id: string;
  guide_id: string;
  client_location_id: string | null;
  latitude: number;
  longitude: number;
  accuracy_meters: number | null;
  recorded_at: string;
  received_at: string;
  created_at: string;
}

function fromWire(wire: LocationResponseWire): LocationResponse {
  return {
    id: wire.id,
    guideId: wire.guide_id,
    clientLocationId: wire.client_location_id,
    latitude: wire.latitude,
    longitude: wire.longitude,
    accuracyMeters: wire.accuracy_meters,
    recordedAt: wire.recorded_at,
    receivedAt: wire.received_at,
    createdAt: wire.created_at,
  };
}

/**
 * POST /api/v1/guides/{guide_id}/locations. Idempotent on clientLocationId:
 * calling this again with the same clientLocationId and the same data returns the
 * same server location instead of creating another. A 409 (ApiError with status
 * 409) means the same clientLocationId was already used for a different sample —
 * a real conflict, not something a plain retry will resolve.
 */
export async function createOrGetLocation(
  req: CreateLocationRequest
): Promise<LocationResponse> {
  const wire = await apiRequest<LocationResponseWire>(
    `/api/v1/guides/${req.guideId}/locations`,
    {
      method: 'POST',
      body: {
        latitude: req.latitude,
        longitude: req.longitude,
        accuracy_meters: req.accuracyMeters,
        recorded_at: req.recordedAt,
        client_location_id: req.clientLocationId,
      },
    }
  );
  return fromWire(wire);
}
