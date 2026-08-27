import { AudioModule, RecordingPresets, setAudioModeAsync, type AudioRecorder } from 'expo-audio';

/**
 * Recording configuration used everywhere in the app — a single source of truth
 * so the content type/extension assumptions below (see RECORDED_CONTENT_TYPE)
 * stay correct. `directory: 'document'` stores the file in the app's persistent
 * document directory rather than expo-audio's default cache directory, because
 * the OS may purge cache files under storage pressure — a recording pending sync
 * must survive that (see mobile/README.md, "Why recordings are saved to the
 * document directory").
 */
export const RECORDING_OPTIONS = {
  ...RecordingPresets.HIGH_QUALITY,
  directory: 'document' as const,
};

/** RecordingPresets.HIGH_QUALITY produces a .m4a container on both iOS and
 * Android (see RECORDING_OPTIONS) — this is a fixed, known fact about that
 * preset, not a guess. If RECORDING_OPTIONS ever changes, this must change too. */
export const RECORDED_CONTENT_TYPE = 'audio/m4a';
export const RECORDED_EXTENSION = '.m4a';

export interface RecordedAudio {
  /** On-device file URI. The file already exists on disk at this path — this
   * function does not move or copy it. */
  uri: string;
  /** Whatever expo-audio actually reported at the moment recording stopped.
   * Never fabricated — null if unavailable. */
  durationMillis: number | null;
  contentType: string;
}

export type MicrophonePermissionResult =
  | { granted: true }
  | { granted: false; canAskAgain: boolean };

export type StartRecordingResult =
  | { status: 'started' }
  | { status: 'permission-denied'; canAskAgain: boolean }
  | { status: 'error'; message: string };

export type StopRecordingResult =
  | { status: 'success'; audio: RecordedAudio }
  | { status: 'error'; message: string };

/**
 * Checks microphone permission, requesting it only if not already granted. Never
 * requests proactively — only called as a direct result of the user tapping
 * "Record voice note" (see startRecording below).
 */
export async function ensureMicrophonePermission(): Promise<MicrophonePermissionResult> {
  let permission = await AudioModule.getRecordingPermissionsAsync();
  if (!permission.granted) {
    permission = await AudioModule.requestRecordingPermissionsAsync();
  }
  if (!permission.granted) {
    return { granted: false, canAskAgain: permission.canAskAgain };
  }
  return { granted: true };
}

/**
 * Starts foreground recording using an AudioRecorder instance the caller owns
 * (expo-audio's recorder must be created via the useAudioRecorder hook inside a
 * React component — see src/components/VoiceRecorderCard.tsx — so it cannot be
 * constructed inside this plain service module). Everything else — permission
 * handling, audio-mode setup, and interpreting the result — lives here, not in
 * the screen/component.
 *
 * Never fabricates success: a denied permission or a device/API failure is
 * reported as such, and the caller must not treat either as a started recording.
 */
export async function startRecording(recorder: AudioRecorder): Promise<StartRecordingResult> {
  const permission = await ensureMicrophonePermission();
  if (!permission.granted) {
    return { status: 'permission-denied', canAskAgain: permission.canAskAgain };
  }

  try {
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
    return { status: 'started' };
  } catch (err) {
    console.error('[audioRecordingService] Failed to start recording:', err);
    return { status: 'error', message: 'Could not start recording. Please try again.' };
  }
}

/**
 * Returns the audio session to a playback-friendly mode (Step 17).
 *
 * Necessary because startRecording() sets `allowsRecording: true`, and on iOS
 * that routes output to the quiet earpiece speaker rather than the loudspeaker
 * — so playing a just-finished recording back would be almost inaudible. Called
 * after a recording is stopped, and before previewing one, wherever the app
 * offers playback.
 *
 * Best-effort by design: if it fails, playback may simply be quieter. Throwing
 * would fail a recording the guide has already successfully made, which is a
 * far worse outcome than suboptimal routing.
 */
export async function restorePlaybackAudioMode(): Promise<void> {
  try {
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
  } catch (err) {
    console.error('[audioRecordingService] Failed to restore playback audio mode:', err);
  }
}

/**
 * Stops recording and returns a stable description of the resulting audio file.
 * `lastKnownDurationMillis` is whatever the caller's live recorder state (from
 * useAudioRecorderState) last reported while recording was in progress — passed
 * in rather than re-derived here because it is UI-observed state, not something
 * this plain service function can read on its own; using it is reporting a real
 * API-provided value, not fabricating one.
 *
 * Recording successfully means: recorder.stop() succeeded AND a usable file URI
 * was produced. If either fails, the caller must not create a completed capture.
 */
export async function stopRecording(
  recorder: AudioRecorder,
  lastKnownDurationMillis: number | null
): Promise<StopRecordingResult> {
  try {
    await recorder.stop();
  } catch (err) {
    console.error('[audioRecordingService] Failed to stop recording:', err);
    return { status: 'error', message: 'Could not stop the recording cleanly.' };
  }

  const uri = recorder.uri;
  if (!uri) {
    return { status: 'error', message: 'Recording finished but no audio file was produced.' };
  }

  return {
    status: 'success',
    audio: {
      uri,
      durationMillis: lastKnownDurationMillis,
      contentType: RECORDED_CONTENT_TYPE,
    },
  };
}
