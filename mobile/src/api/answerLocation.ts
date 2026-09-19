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
    // The only way an answer gets coordinates today is the guide explicitly
    // tapping "Capture Location", which is a live device fix by definition.
    location_source: 'gps_live',
    ...(answer.locationAccuracyMeters != null
      ? { location_accuracy_meters: answer.locationAccuracyMeters }
      : {}),
    ...(answer.locationCapturedAt ? { location_captured_at: answer.locationCapturedAt } : {}),
    ...(answer.locationLabel ? { location_label: answer.locationLabel } : {}),
    ...(answer.externalPlaceId ? { external_place_id: answer.externalPlaceId } : {}),
  };
}
