import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useAudioRecorder, useAudioRecorderState } from 'expo-audio';
import { File } from 'expo-file-system';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { RECORDING_OPTIONS, startRecording, stopRecording } from '../audio/audioRecordingService';
import { createVoiceCapture } from '../repositories/captureRepository';
import { colors, radii, spacing, type } from '../theme/theme';
import Card from './ui/Card';
import type { LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  /** Called once a voice note has been saved locally, so the parent screen can
   * refresh its "waiting to send" counts. */
  onSaved: () => void;
};

type UiState = 'idle' | 'recording' | 'saving';

function formatDuration(ms: number | null): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '0:00';
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

/**
 * The recorder instance MUST be created via expo-audio's useAudioRecorder hook,
 * which only works inside a React component — that's the one piece of raw
 * expo-audio API usage that can't live in src/audio/audioRecordingService.ts.
 * Every actual decision (permission handling, start/stop behavior, result
 * shaping) still lives in that service; this component only calls into it
 * and (Step 15) presents it using the shared design system.
 */
export default function VoiceRecorderCard({ guide, onSaved }: Props) {
  const db = useSQLiteContext();
  const recorder = useAudioRecorder(RECORDING_OPTIONS);
  const recorderState = useAudioRecorderState(recorder, 200);

  const [uiState, setUiState] = useState<UiState>('idle');
  const [message, setMessage] = useState<string | null>(null);

  async function handleRecordPress() {
    setMessage(null);
    const result = await startRecording(recorder);
    if (result.status === 'started') {
      setUiState('recording');
    } else if (result.status === 'permission-denied') {
      setMessage(
        result.canAskAgain
          ? 'Microphone permission is required to record a voice note. Please allow it and try again.'
          : 'Microphone permission was denied. Enable it for this app in your device settings to record.'
      );
    } else {
      setMessage(result.message);
    }
  }

  async function handleStopPress() {
    setUiState('saving');
    const lastKnownDuration = recorderState.durationMillis ?? null;
    const result = await stopRecording(recorder, lastKnownDuration);

    if (result.status === 'error') {
      setUiState('idle');
      setMessage(result.message);
      return;
    }

    try {
      await createVoiceCapture(
        db,
        guide.id,
        result.audio.uri,
        result.audio.durationMillis,
        result.audio.contentType
      );
      setMessage('Voice note saved on this device — waiting to send.');
      onSaved();
    } catch (err) {
      console.error('[VoiceRecorderCard] Failed to save local voice capture metadata:', err);
      // The audio file was created but its SQLite metadata wasn't — best-effort
      // cleanup so it doesn't sit on disk unreferenced by anything. Never treat
      // this as a successfully saved observation.
      try {
        const file = new File(result.audio.uri);
        if (file.exists) {
          file.delete();
        }
      } catch (cleanupErr) {
        console.error('[VoiceRecorderCard] Failed to clean up orphaned audio file:', cleanupErr);
      }
      setMessage('Could not save this voice note on your device. Please try again.');
    } finally {
      setUiState('idle');
    }
  }

  const recording = uiState === 'recording';

  return (
    <Card style={[styles.card, recording && styles.cardRecording]}>
      <Text style={[styles.title, recording && styles.titleRecording]}>Voice update</Text>

      {recording ? (
        <>
          <View style={styles.recordingRow}>
            <View style={styles.recDot} />
            <Text style={styles.recordingLabel}>Recording…</Text>
          </View>
          <Text style={styles.timer}>{formatDuration(recorderState.durationMillis ?? null)}</Text>
          <Pressable
            style={styles.stopButton}
            onPress={handleStopPress}
            accessibilityRole="button"
            accessibilityLabel="Stop recording"
          >
            <Ionicons name="stop" size={18} color={colors.white} />
            <Text style={styles.stopButtonText}>Stop</Text>
          </Pressable>
        </>
      ) : (
        <Pressable
          style={[styles.recordButton, uiState === 'saving' && styles.buttonDisabled]}
          onPress={handleRecordPress}
          disabled={uiState === 'saving'}
          accessibilityRole="button"
          accessibilityLabel="Record a voice update"
        >
          <View style={styles.micCircle}>
            <Ionicons name="mic" size={20} color={colors.ink} />
          </View>
          <Text style={styles.recordButtonText}>
            {uiState === 'saving' ? 'Saving…' : 'Tap to record'}
          </Text>
        </Pressable>
      )}

      {message ? <Text style={[styles.message, recording && styles.messageRecording]}>{message}</Text> : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { alignItems: 'stretch' },
  cardRecording: { backgroundColor: colors.ink },
  title: { ...type.captionBold, color: colors.inkFaint, letterSpacing: 0.4, marginBottom: spacing.sm },
  titleRecording: { color: 'rgba(255,255,255,0.6)' },
  recordButton: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  micCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.marigoldSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  recordButtonText: { ...type.bodyBold, color: colors.ink },
  recordingRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  recDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: colors.fix },
  recordingLabel: { ...type.smallBold, color: colors.white },
  timer: { ...type.display, fontSize: 34, color: colors.white, marginTop: spacing.xs, marginBottom: spacing.md },
  stopButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    backgroundColor: colors.fix,
    borderRadius: radii.pill,
    paddingVertical: spacing.sm,
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.lg,
  },
  stopButtonText: { ...type.button, color: colors.white },
  buttonDisabled: { opacity: 0.6 },
  message: { ...type.small, color: colors.inkSoft, marginTop: spacing.sm, lineHeight: 18 },
  messageRecording: { color: 'rgba(255,255,255,0.75)' },
});
