import { Ionicons } from '@expo/vector-icons';

import type { PlaceContributionKind, PlaceQuestion } from '../api/placeQuestions';
import type { ExplorePrompt } from './explorePrompts';

/**
 * Bridges a backend-researched place question into the shapes the Explore
 * composer and card already understand.
 *
 * WHY A BRIDGE RATHER THAN A SEPARATE COMPONENT: a place question and a
 * device-built Explore prompt end up being answered through the exact same
 * screen (ExploreContributeScreen) and the exact same offline capture ->
 * sync -> extraction pipeline. The only genuine differences are (1) the copy
 * is backend-authored instead of templated, and (2) the reward is a specific
 * server-resolved number rather than one derived from rewardConfig client-side.
 * ExplorePrompt already carries optional `placeQuestionId` /
 * `resolvedRewardPoints` fields for exactly this -- see explorePrompts.ts.
 */

const KIND_ICON: Record<PlaceContributionKind, keyof typeof Ionicons.glyphMap> = {
  photo: 'camera-outline',
  voice: 'mic-outline',
  observation: 'eye-outline',
  experience: 'sparkles-outline',
  status: 'time-outline',
};

/** Icon used wherever a place question is listed compactly (Questions tab
 * rows) -- distinguishing kinds at a glance without reading the full text. */
export function placeQuestionKindIcon(kind: PlaceContributionKind): keyof typeof Ionicons.glyphMap {
  return KIND_ICON[kind] ?? 'help-circle-outline';
}

const PLACEHOLDER: Record<PlaceContributionKind, string> = {
  photo: 'Say what the photo shows…',
  voice: 'Type a few words, or just record your voice note…',
  observation: 'Describe what you see…',
  experience: 'What was it actually like?',
  status: 'What did you find when you got here?',
};

const VOICE_COPY: Record<PlaceContributionKind, string> = {
  photo: 'Describe the photo out loud',
  voice: 'Tell us about it in your own words',
  observation: 'Say what you notice here',
  experience: 'Share what it was like',
  status: 'Say what you found',
};

/** ExplorePrompt.kind drives only the card's icon/tint in ExploreScreen — see
 * KIND_STYLE there. Mapped to the closest visual match; it has no effect on
 * behaviour (contribution routing is driven by wantsPhoto / placeQuestionId). */
const CARD_KIND: Record<PlaceContributionKind, ExplorePrompt['kind']> = {
  photo: 'photo',
  voice: 'story',
  observation: 'conditions',
  experience: 'culture',
  status: 'conditions',
};

/**
 * Builds the ExplorePrompt for one place question. `resolvedRewardPoints` is
 * the backend's own number for THIS question's contribution kind (see
 * PlaceQuestion.rewardPoints) — ExploreScreen's rewardForPrompt() and
 * ExploreContributeScreen both prefer it over the generic rewardConfig-derived
 * value once it is set.
 */
export function placeQuestionToExplorePrompt(
  question: PlaceQuestion,
  placeName: string | null
): ExplorePrompt {
  const kind = question.contributionKind;
  return {
    id: `place:${question.id}`,
    kind: CARD_KIND[kind] ?? 'conditions',
    title: placeName ? `You're at ${placeName}` : "You're here",
    body: question.questionText,
    placeholder: PLACEHOLDER[kind] ?? PLACEHOLDER.observation,
    voiceCopy: VOICE_COPY[kind] ?? VOICE_COPY.observation,
    wantsPhoto: kind === 'photo',
    // The grounded "why we're asking" line from research — never invented,
    // null when research found nothing specific enough to state honestly.
    reason: question.contextNote,
    placeQuestionId: question.id,
    resolvedRewardPoints: question.rewardPoints,
  };
}
