import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';

import type { PlaceQuestion } from './api/placeQuestions';
import type { Question } from './api/questions';
import { colors, spacing, type } from './theme/theme';
import { LoadingState, TabBar, type TabKey } from './components/ui';
import type { ExplorePrompt } from './explore/explorePrompts';
import { placeQuestionToExplorePrompt } from './explore/placeQuestionPrompts';
import { useLocalActivityCount } from './hooks/useLocalActivityCount';
import { getCurrentLocalGuide } from './repositories/guideRepository';
import AnswerQuestionScreen, {
  targetFromPlaceQuestion,
  targetFromQuestion,
  type AnswerTarget,
} from './screens/AnswerQuestionScreen';
import CreateNoteScreen from './screens/CreateNoteScreen';
import ExploreContributeScreen from './screens/ExploreContributeScreen';
import ExploreScreen from './screens/ExploreScreen';
import HomeScreen from './screens/HomeScreen';
import MemoryContributeScreen from './screens/MemoryContributeScreen';
import PendingItemsScreen from './screens/PendingItemsScreen';
import ProfileScreen from './screens/ProfileScreen';
import QuestionsScreen from './screens/QuestionsScreen';
import RewardsScreen from './screens/RewardsScreen';
import SetupScreen from './screens/SetupScreen';
import { useAutoSync } from './sync/autoSync';
import type { LocalGuide } from './types/models';

type PushedScreen =
  | 'createNote'
  | 'answerQuestion'
  | 'exploreContribute'
  | 'memoryContribute'
  | 'profile'
  | 'rewards'
  | null;

/**
 * Navigation shell (Step 15): a persistent bottom TabBar (Home / Questions /
 * Activity) for the three top-level areas, plus a simple "pushed screen"
 * concept (CreateNote, AnswerQuestion) that takes over the full screen
 * without the tab bar — a lightweight stack-push feel built from plain state,
 * not a navigation library (Part E). Setup remains its own pre-tab gate.
 *
 * `refreshKey` is bumped whenever the user returns to a tab root or closes a
 * pushed screen — each tab screen's own mount effect already re-reads its
 * data on remount (the established pattern from Step 4 onward), and this
 * hook drives the same "did something change locally?" signal for the
 * Activity tab's badge count without polling or a global store.
 */
export default function RootNavigator() {
  const db = useSQLiteContext();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [guide, setGuide] = useState<LocalGuide | null>(null);

  const [activeTab, setActiveTab] = useState<TabKey>('home');
  const [pushed, setPushed] = useState<PushedScreen>(null);
  // A normalized target rather than a Question: the answer screen serves BOTH
  // question sources (Step 18), and resolving the difference once here keeps
  // that branch out of the screen itself.
  const [answerTarget, setAnswerTarget] = useState<AnswerTarget | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<ExplorePrompt | null>(null);
  // Which tab pushed the Explore composer — a photo/voice place question can
  // now open it from Questions, not only from Explore itself, and closing
  // should return to wherever the guide actually came from.
  const [explorePromptOrigin, setExplorePromptOrigin] = useState<TabKey>('explore');
  const [questionBadgeCount, setQuestionBadgeCount] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const activityCount = useLocalActivityCount(db, guide?.id ?? null, refreshKey);

  // Best-effort background sync on reconnect, gated on the guide's own
  // preference (see HomeScreen's toggle). Runs for the whole app session,
  // not just while Home is mounted — a guide should not have to be looking
  // at the Home tab for auto-sync to fire.
  useAutoSync(db);

  const reloadGuide = useCallback(async () => {
    try {
      const current = await getCurrentLocalGuide(db);
      setGuide(current);
      setLoadError(null);
    } catch (err) {
      console.error('[RootNavigator] Failed to load local guide profile:', err);
      setLoadError('Could not read local data on this device.');
    } finally {
      setLoading(false);
    }
  }, [db]);

  useEffect(() => {
    reloadGuide();
  }, [reloadGuide]);

  const goToTab = useCallback((tab: TabKey) => {
    setActiveTab(tab);
    setRefreshKey((k) => k + 1);
  }, []);

  const closePushed = useCallback((returnTo?: TabKey) => {
    setPushed(null);
    setAnswerTarget(null);
    setSelectedPrompt(null);
    if (returnTo) setActiveTab(returnTo);
    setRefreshKey((k) => k + 1);
  }, []);

  if (loading) {
    return (
      <View style={styles.center}>
        <LoadingState message="Loading your profile…" />
      </View>
    );
  }

  if (loadError) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{loadError}</Text>
      </View>
    );
  }

  if (!guide) {
    return <SetupScreen onGuideCreated={reloadGuide} />;
  }

  if (pushed === 'createNote') {
    return <CreateNoteScreen guide={guide} onDone={() => closePushed('home')} />;
  }

  if (pushed === 'answerQuestion' && answerTarget) {
    return (
      <AnswerQuestionScreen
        guide={guide}
        target={answerTarget}
        onDone={() => closePushed('questions')}
      />
    );
  }

  if (pushed === 'rewards') {
    return <RewardsScreen guide={guide} onDone={() => setPushed('profile')} />;
  }

  if (pushed === 'profile') {
    return (
      <ProfileScreen
        guide={guide}
        // Re-reads the guide row before closing, so the Home avatar, the
        // greeting and every initial reflect the save immediately. Without
        // this the navigator would keep serving the stale `guide` object it
        // loaded at mount.
        onDone={async () => {
          await reloadGuide();
          closePushed('home');
        }}
        onOpenRewards={() => setPushed('rewards')}
      />
    );
  }

  if (pushed === 'exploreContribute' && selectedPrompt) {
    return (
      <ExploreContributeScreen
        guide={guide}
        prompt={selectedPrompt}
        onDone={() => closePushed(explorePromptOrigin)}
      />
    );
  }

  if (pushed === 'memoryContribute') {
    return <MemoryContributeScreen guide={guide} onDone={() => closePushed('explore')} />;
  }

  return (
    <View style={styles.shell}>
      <View style={styles.content}>
        {activeTab === 'home' ? (
          <HomeScreen
            guide={guide}
            onCreateNote={() => setPushed('createNote')}
            onViewQuestions={() => goToTab('questions')}
            onViewExplore={() => goToTab('explore')}
            onViewActivity={() => goToTab('activity')}
            onOpenProfile={() => setPushed('profile')}
            refreshKey={refreshKey}
          />
        ) : activeTab === 'explore' ? (
          <ExploreScreen
            guide={guide}
            onStartContribution={(prompt) => {
              setSelectedPrompt(prompt);
              setExplorePromptOrigin('explore');
              setPushed('exploreContribute');
            }}
            onStartMemory={() => setPushed('memoryContribute')}
            refreshKey={refreshKey}
          />
        ) : activeTab === 'questions' ? (
          <QuestionsScreen
            guide={guide}
            onSelectQuestion={(question) => {
              setAnswerTarget(targetFromQuestion(question));
              setPushed('answerQuestion');
            }}
            onSelectPopularQuestion={(question, placeName) => {
              // A place question asking for a photo or a voice note needs
              // actual media capture, which only ExploreContributeScreen has
              // — AnswerQuestionScreen is text-only by design (Step 13). Every
              // other kind (observation/experience/status) is a short text
              // report and keeps using the lighter, already-built answer
              // screen, exactly like a priority question.
              if (question.contributionKind === 'photo' || question.contributionKind === 'voice') {
                setSelectedPrompt(placeQuestionToExplorePrompt(question, placeName));
                setExplorePromptOrigin('questions');
                setPushed('exploreContribute');
                return;
              }
              setAnswerTarget(targetFromPlaceQuestion(question, placeName));
              setPushed('answerQuestion');
            }}
            onCountChange={setQuestionBadgeCount}
            refreshKey={refreshKey}
          />
        ) : (
          <PendingItemsScreen guide={guide} refreshKey={refreshKey} />
        )}
      </View>
      <TabBar active={activeTab} onChange={goToTab} badges={{ questions: questionBadgeCount, activity: activityCount }} />
    </View>
  );
}

const styles = StyleSheet.create({
  shell: { flex: 1, backgroundColor: colors.paper },
  content: { flex: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.paper },
  errorText: { ...type.body, color: colors.fix, paddingHorizontal: spacing.xl, textAlign: 'center' },
});
