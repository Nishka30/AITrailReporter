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
 *
 * Note that "returns the existing guide" means exactly that — the backend does
 * NOT update name/phone from a repeat call (see backend
 * services/guides.py:create_or_get_guide). Later edits therefore go through
 * updateGuideProfile below, not by re-POSTing here.
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

export interface UpdateGuideProfileRequest {
  /** The SERVER guide id — this endpoint edits an existing server record, so
   * unlike createOrGetGuide it cannot be called until the guide has synced. */
  serverGuideId: string;
  name: string;
  phoneNumber: string | null;
}

/**
 * PATCH /api/v1/guides/{serverGuideId} (Step 17).
 *
 * Pushes locally-edited identity fields to the backend. Sends ONLY name and
 * phone_number: the profile's "About you" text and profile photo are local to
 * the device and are deliberately never transmitted — they are personal
 * metadata, not field knowledge, and the backend has no column, no use, and no
 * business holding them.
 *
 * Naturally idempotent (it sets absolute values rather than applying a delta),
 * so it needs no client-generated id the way submission/answer creation does —
 * re-running it after a lost response converges on the same state. A 404 means
 * the server no longer has this guide, which a retry cannot fix.
 */
export async function updateGuideProfile(
  req: UpdateGuideProfileRequest
): Promise<GuideResponse> {
  const wire = await apiRequest<GuideResponseWire>(`/api/v1/guides/${req.serverGuideId}`, {
    method: 'PATCH',
    body: {
      name: req.name,
      phone_number: req.phoneNumber,
    },
  });
  return fromWire(wire);
}
