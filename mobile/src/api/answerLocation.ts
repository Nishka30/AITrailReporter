import type { LocalAnswer } from '../types/models';

/**
 * The per-answer location provenance both answer endpoints accept, in the
 * backend's wire shape.
 *
 * One module rather than two copies because knowledge-gap answers
 * (POST /questions/{id}/answers) and place-question answers
 * (POST /place-questions/{id}/answers) take the identical optional block --
 * and because the rule that a coordinate is only ever sent as 'gps_live'
 * when there genuinely IS a device fix behind it has to hold for both.
 */
export interface AnswerLocationWire {
  latitude?: number;
  longitude?: number;
  location_source?: string;
  location_accuracy_meters?: number;
  location_captured_at?: string;
  location_label?: string;
  external_place_id?: string;
}

/**
 * Builds the wire block for an answer, or `{}` when the guide never captured
 * a location for it.
 *
 * Omits the fields entirely rather than sending nulls: an absent block means
 * "the client has nothing to say about where this happened", which is exactly
 * what makes the server keep its existing derivation (the knowledge gap's
 * target coordinates, or the place a place question is about). Sending
 * `location_source: 'gps_live'` with no coordinates would be a claim the data
 * cannot back up -- the backend rejects that combination on purpose
 * (see backend/app/schemas/submission.py).
 */
export function answerLocationWire(answer: LocalAnswer): AnswerLocationWire {
  if (answer.latitude == null || answer.longitude == null) {
    return {};
  }
  return {
    latitude: answer.latitude,
    longitude: answer.longitude,
    // 'gps_live' for a real device fix, 'user_selected' when this came from
    // the guide's currently selected TrailMind Location instead (see
    // AnswerQuestionScreen's placeToCapturedLocation). Falls back to
    // 'gps_live' for any answer synced before locationSource existed on
    // LocalAnswer -- every one of those WAS a live GPS fix in practice,
    // since LocationCaptureField was the only source of a captured answer
    // location at the time.
    location_source: answer.locationSource ?? 'gps_live',
    ...(answer.locationAccuracyMeters != null
      ? { location_accuracy_meters: answer.locationAccuracyMeters }
      : {}),
    ...(answer.locationCapturedAt ? { location_captured_at: answer.locationCapturedAt } : {}),
    ...(answer.locationLabel ? { location_label: answer.locationLabel } : {}),
    ...(answer.externalPlaceId ? { external_place_id: answer.externalPlaceId } : {}),
  };
}
