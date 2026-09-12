import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { ApiError, NetworkError } from '../api/client';
import {
  describeCandidateDistance,
  describeCandidateKind,
  listPlaceCandidates,
  type PlaceCandidate,
} from '../api/placeCandidates';
import { Button, EmptyState, ErrorState, LoadingState, Screen } from '../components/ui';
import { captureCurrentLocation } from '../location/locationService';
import { colors, radii, spacing, type } from '../theme/theme';
import type { LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  onSelect: (place: PlaceCandidate) => void;
  /** Shown only when a place is ALREADY chosen — i.e. the guide opened this
   * deliberately to change it, and backing out must leave the old choice
   * intact rather than clearing it. */
  onCancel?: () => void;
  /** Continue with NO chosen place. Offered only when choosing is genuinely
   * impossible right now — offline, permission denied, or nowhere mapped
   * nearby — never as an easier alternative to picking. Explore and Questions
   * then fall back to resolving the place from GPS exactly as they did before
   * this step existed, so a guide is never locked out of contributing by a
   * dropped connection. */
  onSkip: () => void;
};

/** One icon per TrailMind category, so the list is scannable without reading
 * every label. Falls back to a neutral pin rather than guessing. */
function iconForCandidate(candidate: PlaceCandidate): keyof typeof Ionicons.glyphMap {
  if (candidate.isArea) return 'map-outline';
  switch (candidate.category) {
    case 'Food & Drink':
      return 'restaurant-outline';
    case 'Lodging':
      return 'bed-outline';
    case 'Shopping':
      return 'bag-handle-outline';
    case 'Transport':
      return 'train-outline';
    case 'Culture & Heritage':
      return 'library-outline';
    case 'Nature':
      return 'leaf-outline';
    case 'Trail':
      return 'trail-sign-outline';
    case 'Scenic Spot':
      return 'eye-outline';
    default:
      return 'location-outline';
  }
}

function PlaceRow({
  candidate,
  onPress,
}: {
  candidate: PlaceCandidate;
  onPress: () => void;
}) {
  const kind = describeCandidateKind(candidate);
  const distance = describeCandidateDistance(candidate);

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${candidate.name}. ${kind ? `${kind}. ` : ''}${distance}.`}
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
    >
      <View style={[styles.rowIcon, candidate.isArea && styles.rowIconArea]}>
        <Ionicons
          name={iconForCandidate(candidate)}
          size={18}
          color={candidate.isArea ? colors.inkSoft : colors.marigoldDeep}
        />
      </View>
      <View style={styles.rowBody}>
        <Text style={styles.rowName} numberOfLines={2}>
          {candidate.name}
        </Text>
        <Text style={styles.rowMeta} numberOfLines={1}>
          {kind ? `${kind} · ${distance}` : distance}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={17} color={colors.inkFaint} />
    </Pressable>
  );
}

/**
 * "What would you like to contribute to?" — the step between having a
 * position and having a subject.
 *
 * WHY THIS SCREEN EXISTS: GPS can say where the guide is standing, but not
 * what they came to report on. The nearest listed POI is frequently the wrong
 * answer — a hotel that happens to be closest is not the subject when the
 * shop next door is. Choosing takes one tap and removes the guesswork
 * entirely.
 *
 * The list comes from the backend already filtered, de-duplicated and ranked
 * (see backend/app/services/place_candidates.py). Nothing is invented here:
 * when fewer than six real places exist, fewer are shown.
 *
 * Not blocked on research. Choosing a place returns immediately; Perplexity/
 * Claude question generation continues in the background exactly as before,
 * so a freshly discovered place is selectable straight away and its questions
 * fill in shortly after.
 */
export default function PlacePickerScreen({ guide, onSelect, onCancel, onSkip }: Props) {
  const [candidates, setCandidates] = useState<PlaceCandidate[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [gpsDenied, setGpsDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setGpsDenied(false);
    try {
      // Device GPS rather than the guide's last SERVER-recorded position:
      // this screen is answering "what is around me right now", and a
      // position recorded an hour and two kilometres ago would offer the
      // wrong places entirely.
      const fix = await captureCurrentLocation();
      if (fix.status === 'permission-denied') {
        setGpsDenied(true);
        setCandidates(null);
        return;
      }
      if (fix.status === 'error') {
        setError(fix.message);
        setCandidates(null);
        return;
      }
      const result = await listPlaceCandidates(
        fix.location.latitude,
        fix.location.longitude
      );
      setCandidates(result.candidates);
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof NetworkError
          ? err.message
          : 'Could not look up places near you.'
      );
      setCandidates(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={styles.title}>What would you like to contribute to?</Text>
        <Text style={styles.subtitle}>
          {candidates && candidates.length > 0
            ? 'We found these places near you.'
            : 'Checking what’s around you…'}
        </Text>
      </View>

      {loading ? (
        <View style={styles.stateWrap}>
          <LoadingState message="Finding places near you…" />
        </View>
      ) : gpsDenied ? (
        <View style={styles.stateWrap}>
          <EmptyState
            icon="location-outline"
            title="Location permission needed"
            message="TrailMind needs your location to find the places around you. You can allow it in your device settings, then try again."
          />
          <View style={styles.stateButton}>
            <Button label="Try again" onPress={load} variant="secondary" />
            <View style={styles.stateButtonSpacer}>
              <Button label="Continue without choosing" onPress={onSkip} variant="ghost" />
            </View>
          </View>
        </View>
      ) : error ? (
        <View style={styles.stateWrap}>
          <ErrorState message={error} onRetry={load} retrying={loading} />
          {/* Offline is the common cause here, and this app has always let a
              guide write and save with no connection at all. Blocking that
              behind a lookup that needs the network would be a step
              backwards. */}
          <View style={styles.stateButton}>
            <Button label="Continue without choosing" onPress={onSkip} variant="ghost" />
          </View>
        </View>
      ) : candidates && candidates.length > 0 ? (
        <>
          <View style={styles.list}>
            {candidates.map((candidate) => (
              <PlaceRow
                key={candidate.id}
                candidate={candidate}
                onPress={() => onSelect(candidate)}
              />
            ))}
          </View>
          <Text style={styles.footnote}>
            Not seeing the right place? Move a little closer to it and refresh — we only
            show places we can actually confirm are here.
          </Text>
          <View style={styles.actions}>
            <Button label="Refresh" onPress={load} variant="ghost" />
            {onCancel ? <Button label="Keep current place" onPress={onCancel} variant="ghost" /> : null}
          </View>
        </>
      ) : (
        <View style={styles.stateWrap}>
          <EmptyState
            icon="compass-outline"
            title="No places found here"
            message="We could not find any known places around you right now. This can happen somewhere genuinely unmapped, or if the connection dropped."
          />
          {/* Nothing is invented to fill the list. Continuing without a choice
              falls back to naming the area from GPS, which is exactly what the
              app did before this step existed -- an honest "somewhere around
              here" rather than a place we cannot confirm. */}
          <View style={styles.stateButton}>
            <Button label="Try again" onPress={load} variant="secondary" />
            <View style={styles.stateButtonSpacer}>
              <Button label="Continue without choosing" onPress={onSkip} variant="ghost" />
            </View>
            {onCancel ? (
              <View style={styles.stateButtonSpacer}>
                <Button label="Go back" onPress={onCancel} variant="ghost" />
              </View>
            ) : null}
          </View>
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { marginBottom: spacing.lg },
  title: { ...type.display, fontSize: 25, color: colors.ink, lineHeight: 33 },
  subtitle: { ...type.small, color: colors.inkFaint, marginTop: 6, lineHeight: 19 },

  // One grouped, recessed surface rather than N elevated cards — the same
  // treatment the Questions tab gives its place-question group, so the two
  // read as the same kind of list.
  list: {
    backgroundColor: colors.paperMuted,
    borderRadius: radii.lg,
    padding: spacing.xxs,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.md,
    minHeight: 62,
  },
  rowPressed: { backgroundColor: colors.neutralSoft },
  rowIcon: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.marigoldSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowIconArea: { backgroundColor: colors.neutralSoft },
  rowBody: { flex: 1 },
  rowName: { ...type.body, color: colors.ink, lineHeight: 21 },
  rowMeta: { ...type.caption, color: colors.inkFaint, marginTop: 3 },

  footnote: {
    ...type.caption,
    color: colors.inkFaint,
    marginTop: spacing.md,
    lineHeight: 17,
    textAlign: 'center',
  },
  actions: { marginTop: spacing.sm, gap: spacing.xxs },

  stateWrap: { marginTop: spacing.xl },
  stateButton: { marginTop: spacing.md },
  stateButtonSpacer: { marginTop: spacing.xxs },
});
