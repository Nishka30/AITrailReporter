import { apiRequest } from './client';

export interface CreateGuideRequest {
  name: string;
  phoneNumber: string | null;
  /** Makes this call idempotent — see backend Guide.client_guide_id. */
  clientGuideId: string;
}

export interface GuideResponse {
  id: string;
  name: string;
  phoneNumber: string | null;
  clientGuideId: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

// The backend's actual JSON shape (snake_case) — kept private to this module so the
// rest of the app only ever deals in camelCase.
interface GuideResponseWire {
  id: string;
  name: string;
  phone_number: string | null;
  client_guide_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

function fromWire(wire: GuideResponseWire): GuideResponse {
  return {
    id: wire.id,
    name: wire.name,
    phoneNumber: wire.phone_number,
    clientGuideId: wire.client_guide_id,
    isActive: wire.is_active,
    createdAt: wire.created_at,
    updatedAt: wire.updated_at,
  };
}

/**
 * POST /api/v1/guides. Idempotent on clientGuideId: calling this again with the
 * same clientGuideId returns the same server guide instead of creating another.
 */
export async function createOrGetGuide(req: CreateGuideRequest): Promise<GuideResponse> {
  const wire = await apiRequest<GuideResponseWire>('/api/v1/guides', {
    method: 'POST',
    body: {
      name: req.name,
      phone_number: req.phoneNumber,
      client_guide_id: req.clientGuideId,
    },
  });
  return fromWire(wire);
}
