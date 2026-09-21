import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { listPlaceCandidatesCached } from '../api/placeCandidates';
import { captureCurrentLocation } from '../location/locationService';
import { colors, radii, spacing, type } from '../theme/theme';

/**
 * Where the guide actually was when they made ONE specific contribution.
 *
 * Deliberately separate from the app-level position the Home screen records
 * (a GuideLocation ping): that one answers "where is this guide lately", goes
 * stale the moment they walk on, and is what the backend falls back to when a
 * contribution carries no coordinate of its own
 * (extractions._resolve_observation_coordinates, tier 3). This type is the
 * per-contribution answer that makes that fallback unnecessary.
 */
export interface CapturedContributionLocation {
  latitude: number;
  longitude: number;
  accuracyMeters: number | null;
  /** ISO-8601 — when the DEVICE fixed this position, not when it synced. Null
   * when this value did not come from a live device fix at all (e.g. it was
   * pre-filled from an explicitly selected Location) — inventing a capture
   * timestamp for a non-GPS value would overstate what's actually known. */
  capturedAt: string | null;
  /** Human-readable place name, best-effort. Null when the lookup failed or
   * the guide is somewhere with no known/discoverable place — the coordinate
   * is still perfectly valid and is what actually matters. */
  label: string | null;
  /** Google Place id of the resolved place, when there was one. Lets the
   * backend reuse the exact same shared Location row rather than re-deriving
   * one from proximity alone. */
  externalPlaceId: string | null;
  /** Where THIS value came from -- 'gps_live' for a real device fix taken by
   * this control, 'user_selected' for a value seeded from an explicitly
   * chosen TrailMind Location (e.g. AnswerQuestionScreen pre-filling from the
   * guide's currently selected place). Callers use this to set the
   * Submission's own location_source honestly instead of assuming every
   * captured value is a live GPS reading. */
  locationSource: 'gps_live' | 'user_selected';
}

type Status = 'idle' | 'capturing' | 'denied' | 'error';

/**
 * "Capture Location" for a single contribution.
 *
 * Reuses the app's existing location workflow end to end rather than adding a
 * second one: captureCurrentLocation() for the device fix (permission
 * handling, denial and device failure all already honest there), then the
 * existing GET /api/v1/locations/candidates lookup to NAME that coordinate —
 * the same endpoint that reuses known Locations by proximity and falls
 * through to Google Places discovery when nothing is known yet.
 *
 * The naming step is strictly best-effort and never blocks the capture: a
 * guide offline, or somewhere with no known place, still gets a fully valid
 * coordinate recorded, just without a label. Nothing here ever falls back to
 * a previously known position — an un-captured contribution stays honestly
 * un-captured rather than silently inheriting a stale one.
 */
export default function LocationCaptureField({
  value,
  onChange,
  disabled = false,
  /** Shown under the heading when nothing has been captured yet. */
  hint = 'Record where you are right now, so this contribution is tied to the right place.',
}: {
  value: CapturedContributionLocation | null;
  onChange: (next: CapturedContributionLocation | null) => void;
  disabled?: boolean;
  hint?: string;
}) {
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState<string | null>(null);

  async function handleCapture() {
    if (status === 'capturing' || disabled) return;
    setStatus('capturing');
    setMessage(null);

    const fix = await captureCurrentLocation();
    if (fix.status === 'permission-denied') {
      setStatus('denied');
      setMessage(
        fix.canAskAgain
          ? 'Location permission is needed to attach a place to this contribution. Please allow it and try again.'
          : 'Location permission is off for this app. Enable it in your device settings to attach a place to this contribution.'
      );
      return;
    }
    if (fix.status === 'error') {
      setStatus('error');
      setMessage(fix.message);
      return;
    }

    const { latitude, longitude, accuracyMeters, recordedAt } = fix.location;

    // Best-effort naming only. A failure here must never discard a perfectly
    // good coordinate -- the guide is frequently offline in exactly the
    // places this app exists for.
    let label: string | null = null;
    let externalPlaceId: string | null = null;
    try {
      const result = await listPlaceCandidatesCached(latitude, longitude);
      const nearest = result.candidates[0];
      if (nearest) {
        label = nearest.name;
        externalPlaceId = nearest.externalPlaceId;
      }
    } catch {
      // Stays null -- see above. Not surfaced as an error: the capture
      // itself succeeded, which is what this control promises.
    }

    onChange({
      latitude,
      longitude,
      accuracyMeters,
      capturedAt: recordedAt,
      label,
      externalPlaceId,
      locationSource: 'gps_live',
    });
    setStatus('idle');
    setMessage(null);
  }

  const capturing = status === 'capturing';

  return (
    <View style={styles.container}>
      <View style={styles.headingRow}>
        <Ionicons name="location-outline" size={14} color={colors.inkFaint} />
        <Text style={styles.heading}>Location</Text>
      </View>

      {value ? (
        <View style={styles.capturedRow}>
          <Ionicons name="location" size={16} color={colors.ok} />
          <View style={styles.capturedTextBlock}>
            <Text style={styles.capturedLabel}>{value.label ?? 'Current location'}</Text>
            <Text style={styles.capturedDetail}>
              {formatCoordinate(value.latitude)}, {formatCoordinate(value.longitude)}
              {value.accuracyMeters != null ? ` · ±${Math.round(value.accuracyMeters)}m` : ''}
            </Text>
          </View>
          <Pressable
            onPress={handleCapture}
            disabled={disabled || capturing}
            hitSlop={8}
            style={styles.recaptureButton}
            accessibilityRole="button"
            accessibilityLabel="Recapture location"
          >
            <Text style={styles.recaptureText}>{capturing ? 'Updating…' : 'Update'}</Text>
          </Pressable>
          {/* Never a forced attachment -- this matters most for a value this
              control didn't itself capture (e.g. pre-filled from a selected
              Location): the guide must be able to remove it, not just
              overwrite it with a fresh GPS fix. */}
          <Pressable
            onPress={() => onChange(null)}
            disabled={disabled || capturing}
            hitSlop={8}
            style={styles.removeButton}
            accessibilityRole="button"
            accessibilityLabel="Remove location"
          >
            <Text style={styles.removeText}>Remove</Text>
          </Pressable>
        </View>
      ) : (
        <>
          <Pressable
            onPress={handleCapture}
            disabled={disabled || capturing}
            style={({ pressed }) => [
              styles.captureButton,
              (disabled || capturing) && styles.captureButtonDisabled,
              pressed && styles.captureButtonPressed,
            ]}
            accessibilityRole="button"
            accessibilityLabel="Capture location"
          >
            <Ionicons name="locate-outline" size={16} color={colors.ink} />
            <Text style={styles.captureButtonText}>
              {capturing ? 'Capturing…' : 'Capture Location'}
            </Text>
          </Pressable>
          <Text style={styles.hint}>{hint}</Text>
        </>
      )}

      {message ? <Text style={styles.message}>{message}</Text> : null}
    </View>
  );
}

function formatCoordinate(value: number): string {
  return value.toFixed(5);
}

const styles = StyleSheet.create({
  container: { gap: spacing.xs },
  headingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  heading: { ...type.captionBold, color: colors.inkFaint, letterSpacing: 0.3 },
  captureButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.paper,
  },
  captureButtonPressed: { opacity: 0.7 },
  captureButtonDisabled: { opacity: 0.5 },
  captureButtonText: { ...type.bodyBold, color: colors.ink },
  hint: { ...type.caption, color: colors.inkFaint },
  capturedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.paper,
  },
  capturedTextBlock: { flex: 1 },
  capturedLabel: { ...type.bodyBold, color: colors.ink },
  capturedDetail: { ...type.caption, color: colors.inkFaint },
  recaptureButton: { paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  recaptureText: { ...type.captionBold, color: colors.info },
  removeButton: { paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  removeText: { ...type.captionBold, color: colors.fix },
  message: { ...type.caption, color: colors.fix },
});
