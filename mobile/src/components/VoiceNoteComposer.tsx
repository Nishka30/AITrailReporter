import { useEffect, useRef, useState } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, View } from 'react-native';
import { useAudioPlayer, useAudioPlayerStatus, useAudioRecorder, useAudioRecorderState } from 'expo-audio';
import { File } from 'expo-file-system';
import { Ionicons } from '@expo/vector-icons';

import {
  RECORDING_OPTIONS,
  restorePlaybackAudioMode,
  startRecording,
  stopRecording,
  type RecordedAudio,
} from '../audio/audioRecordingService';
import { formatDurationMillis, formatDurationSeconds } from '../audio/duration';
import { colors, minTouchSize, radii, spacing, type } from '../theme/theme';

type Props = {
  /** The recording currently attached, or null. This is a CONTROLLED component:
   * it never persists anything itself — the parent owns the value and decides
   * when it is written to SQLite. */
  value: RecordedAudio | null;
  onChange: (audio: RecordedAudio | null) => void;
  /** Context-aware invitation shown in the idle state, e.g. "Tell us what it
   * looks like right now". Derived from the actual Explore prompt by the caller
   * — never a fabricated place name. */
  idleCopy: string;
  /** Disables every control (e.g. while the parent is saving). */
  disabled?: boolean;
};

type UiState = 'idle' | 'recording' | 'stopping';

/**
 * Voice note composer for Explore contributions (Step 17).
 *
 * HOW THIS DIFFERS FROM VoiceRecorderCard, and why both exist:
 * VoiceRecorderCard (Home) is a complete, self-contained flow — record, stop,
 * and it immediately creates a standalone 'voice' capture in SQLite. That is
 * the right shape there, because the recording IS the whole contribution.
 *
 * Here the recording is one OPTIONAL part of a larger composition (text +
 * photo + voice) that the guide has not committed yet, so this component
 * deliberately persists nothing. It hands the recorded file up and the parent
 * writes one row when "Save discovery" is pressed. Both share the same
 * src/audio/audioRecordingService.ts — permission handling, audio-mode setup,
 * start/stop semantics and result shaping all live there, not duplicated here.
 * There is exactly one recording implementation in this app.
 *
 * Because nothing is saved until the parent saves, a recording that is replaced
 * or removed here is deleted from disk immediately — it can never be referenced
 * by anything, so leaving it would be a pure orphan.
 */
export default function VoiceNoteComposer({ value, onChange, idleCopy, disabled }: Props) {
  const recorder = useAudioRecorder(RECORDING_OPTIONS);
  const recorderState = useAudioRecorderState(recorder, 200);

  // Playback of the just-made recording. expo-audio is already this app's audio
  // library, so previewing costs no new dependency and no new architecture —
  // `useAudioPlayer` rebuilds its player when the source changes, so passing
  // the current URI (or null when there is none) is all that's required.
  const player = useAudioPlayer(value?.uri ?? null);
  const playerStatus = useAudioPlayerStatus(player);

  const [uiState, setUiState] = useState<UiState>('idle');
  const [message, setMessage] = useState<string | null>(null);

  const recording = uiState === 'recording';

  // A slow breathing pulse behind the record indicator. Purely decorative
  // feedback that recording is genuinely live — it is driven by the UI state,
  // never by fake audio levels (expo-audio's metering is not enabled here, and
  // animating imaginary levels would be dishonest).
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!recording) {
      pulse.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 900,
          easing: Easing.out(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: 900,
          easing: Easing.in(Easing.ease),
          useNativeDriver: true,
        }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [recording, pulse]);

  // Playback stops at the end rather than sitting at the final frame reporting
  // "playing", and rewinds so a second tap replays from the start.
  useEffect(() => {
    if (playerStatus.didJustFinish) {
      player.pause();
      player.seekTo(0);
    }
  }, [playerStatus.didJustFinish, player]);

  /** Best-effort removal of a recording that was never committed to SQLite. */
  function discardFile(uri: string) {
    try {
      const file = new File(uri);
      if (file.exists) file.delete();
    } catch (err) {
      console.error('[VoiceNoteComposer] Failed to delete discarded recording:', err);
    }
  }

  async function handleStartPress() {
    if (disabled || uiState !== 'idle') return;
    setMessage(null);
    const result = await startRecording(recorder);
    if (result.status === 'started') {
      setUiState('recording');
    } else if (result.status === 'permission-denied') {
      setMessage(
        result.canAskAgain
          ? 'Microphone access is needed to record. Please allow it and try again.'
          : 'Microphone access was denied. You can enable it for this app in your device settings.'
      );
    } else {
      setMessage(result.message);
    }
  }

  async function handleStopPress() {
    if (uiState !== 'recording') return;
    setUiState('stopping');
    const lastKnownDuration = recorderState.durationMillis ?? null;
    const result = await stopRecording(recorder, lastKnownDuration);
    // Put the session back into playback routing so the preview below is
    // actually audible on iOS.
    await restorePlaybackAudioMode();

    if (result.status === 'error') {
      setUiState('idle');
      setMessage(result.message);
      return;
    }

    // Replacing an existing recording: the old file is now unreachable.
    if (value?.uri && value.uri !== result.audio.uri) discardFile(value.uri);

    onChange(result.audio);
    setUiState('idle');
  }

  function handleRemovePress() {
    if (disabled) return;
    if (playerStatus.playing) player.pause();
    if (value?.uri) discardFile(value.uri);
    onChange(null);
    setMessage(null);
  }

  async function handlePlayPress() {
    if (!value) return;
    if (playerStatus.playing) {
      player.pause();
      return;
    }
    await restorePlaybackAudioMode();
    player.play();
  }

  // ---------- RECORDING ----------
  if (recording || uiState === 'stopping') {
    const elapsed = formatDurationMillis(recorderState.durationMillis ?? 0);
    return (
      <View style={styles.liveCard}>
        <View style={styles.liveHeaderRow}>
          <View style={styles.liveDotWrap}>
            <Animated.View
              style={[
                styles.livePulse,
                {
                  opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.45, 0] }),
                  transform: [
                    { scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 2.4] }) },
                  ],
                },
              ]}
            />
            <View style={styles.liveDot} />
          </View>
          <Text style={styles.liveLabel}>
            {uiState === 'stopping' ? 'Finishing…' : 'Recording'}
          </Text>
        </View>

        <Text style={styles.liveTimer}>{elapsed}</Text>
        <Text style={styles.liveHint}>Speak naturally — you can re-record if you want to.</Text>

        <Pressable
          onPress={handleStopPress}
          disabled={uiState === 'stopping'}
          accessibilityRole="button"
          accessibilityLabel="Stop recording"
          style={({ pressed }) => [
            styles.stopButton,
            pressed && styles.pressed,
            uiState === 'stopping' && styles.disabled,
          ]}
        >
          <Ionicons name="stop" size={16} color={colors.white} />
          <Text style={styles.stopButtonText}>
            {uiState === 'stopping' ? 'Saving…' : 'Stop recording'}
          </Text>
        </Pressable>
      </View>
    );
  }

  // ---------- ATTACHED ----------
  if (value) {
    const playing = playerStatus.playing;
    // Prefer the player's own duration once it has loaded the file: it is
    // measured from the actual audio. Fall back to what the recorder reported.
    const durationLabel =
      playerStatus.duration > 0
        ? formatDurationSeconds(playerStatus.duration)
        : formatDurationMillis(value.durationMillis);
    const positionLabel = formatDurationSeconds(playerStatus.currentTime);
    const progress =
      playerStatus.duration > 0
        ? Math.min(1, Math.max(0, playerStatus.currentTime / playerStatus.duration))
        : 0;

    return (
      <View style={styles.attachedCard}>
        <View style={styles.attachedRow}>
          <Pressable
            onPress={handlePlayPress}
            disabled={disabled}
            accessibilityRole="button"
            accessibilityLabel={playing ? 'Pause voice note' : 'Play voice note'}
            style={({ pressed }) => [
              styles.playButton,
              pressed && styles.pressed,
              disabled && styles.disabled,
            ]}
          >
            <Ionicons
              name={playing ? 'pause' : 'play'}
              size={20}
              color={colors.ink}
              // Nudges the play triangle to look optically centred in its circle.
              style={playing ? undefined : styles.playIconNudge}
            />
          </Pressable>

          <View style={styles.attachedTextWrap}>
            <View style={styles.attachedTitleRow}>
              <Ionicons name="checkmark-circle" size={14} color={colors.ok} />
              <Text style={styles.attachedTitle}>Voice note ready</Text>
            </View>
            <Text style={styles.attachedMeta}>
              {playing || playerStatus.currentTime > 0
                ? `${positionLabel} / ${durationLabel}`
                : durationLabel}
            </Text>
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
            </View>
          </View>

          <Pressable
            onPress={handleRemovePress}
            disabled={disabled}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="Remove voice note"
            style={({ pressed }) => [
              styles.removeButton,
              pressed && styles.pressed,
              disabled && styles.disabled,
            ]}
          >
            <Ionicons name="trash-outline" size={17} color={colors.fix} />
          </Pressable>
        </View>

        <Pressable
          onPress={handleStartPress}
          disabled={disabled}
          accessibilityRole="button"
          accessibilityLabel="Record again, replacing this voice note"
          style={({ pressed }) => [styles.reRecordRow, pressed && styles.pressed]}
        >
          <Ionicons name="refresh" size={14} color={colors.marigoldDeep} />
          <Text style={styles.reRecordText}>Record again</Text>
        </Pressable>

        {message ? <Text style={styles.message}>{message}</Text> : null}
      </View>
    );
  }

  // ---------- IDLE ----------
  return (
    <>
      <Pressable
        onPress={handleStartPress}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel="Record a voice note"
        accessibilityHint="Optional. Records audio to attach to this discovery."
        style={({ pressed }) => [
          styles.idleCard,
          pressed && styles.idleCardPressed,
          disabled && styles.disabled,
        ]}
      >
        <View style={styles.micCircle}>
          <Ionicons name="mic" size={22} color={colors.ink} />
        </View>
        <View style={styles.idleTextWrap}>
          <Text style={styles.idleTitle}>{idleCopy}</Text>
          <Text style={styles.idleSubtitle}>Tap to record · optional</Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={colors.inkFaint} />
      </Pressable>
      {message ? <Text style={styles.message}>{message}</Text> : null}
    </>
  );
}

const styles = StyleSheet.create({
  pressed: { opacity: 0.75 },
  disabled: { opacity: 0.5 },
  message: { ...type.small, color: colors.inkSoft, marginTop: spacing.xs, lineHeight: 18 },

  // Idle
  idleCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    minHeight: 78,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderStyle: 'dashed',
    backgroundColor: colors.paperMuted,
  },
  idleCardPressed: { opacity: 0.8, backgroundColor: colors.marigoldSoft },
  micCircle: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: colors.marigoldSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  idleTextWrap: { flex: 1 },
  idleTitle: { ...type.bodyBold, color: colors.ink, lineHeight: 21 },
  idleSubtitle: { ...type.caption, color: colors.inkFaint, marginTop: 2 },

  // Recording
  liveCard: {
    backgroundColor: colors.ink,
    borderRadius: radii.md,
    padding: spacing.md,
  },
  liveHeaderRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  liveDotWrap: { width: 12, height: 12, alignItems: 'center', justifyContent: 'center' },
  liveDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.fix },
  livePulse: {
    position: 'absolute',
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.fix,
  },
  liveLabel: {
    ...type.captionBold,
    color: colors.white,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  liveTimer: {
    ...type.display,
    fontSize: 40,
    lineHeight: 48,
    color: colors.white,
    marginTop: spacing.xs,
  },
  liveHint: { ...type.small, color: 'rgba(255,255,255,0.65)', marginBottom: spacing.md },
  stopButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    minHeight: minTouchSize,
    backgroundColor: colors.fix,
    borderRadius: radii.pill,
    paddingHorizontal: spacing.lg,
  },
  stopButtonText: { ...type.button, color: colors.white },

  // Attached
  attachedCard: {
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.paperElevated,
    padding: spacing.sm,
  },
  attachedRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  playButton: {
    width: minTouchSize,
    height: minTouchSize,
    borderRadius: minTouchSize / 2,
    backgroundColor: colors.marigoldSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  playIconNudge: { marginLeft: 3 },
  attachedTextWrap: { flex: 1 },
  attachedTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  attachedTitle: { ...type.smallBold, color: colors.ink },
  attachedMeta: { ...type.caption, color: colors.inkFaint, marginTop: 1, marginBottom: 5 },
  progressTrack: {
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.paperMuted,
    overflow: 'hidden',
  },
  progressFill: { height: 4, borderRadius: 2, backgroundColor: colors.marigold },
  removeButton: {
    width: minTouchSize - 8,
    height: minTouchSize - 8,
    borderRadius: (minTouchSize - 8) / 2,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.fixSoft,
  },
  reRecordRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    alignSelf: 'flex-start',
    minHeight: 36,
    paddingTop: spacing.xs,
    paddingRight: spacing.sm,
  },
  reRecordText: { ...type.smallBold, color: colors.marigoldDeep },
});
