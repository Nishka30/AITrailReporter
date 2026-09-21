import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';

import type { PlaceCandidate } from './api/placeCandidates';
import type { PlaceQuestion } from './api/placeQuestions';
import type { Question } from './api/questions';
import { colors, spacing, type } from './theme/theme';
import { LoadingState, TabBar, type TabKey } from './components/ui';
import type { ExplorePrompt } from './explore/explorePrompts';
import { placeQuestionToExplorePrompt } from './explore/placeQuestionPrompts';
import { useLocalActivityCount } from './hooks/useLocalActivityCount';
import { getCurrentLocalGuide } from './repositories/guideRepository';
import AnswerQuestionScreen, {
  targetFromQuestion,
  type AnswerTarget,
} from './screens/AnswerQuestionScreen';
import CreateNoteScreen from './screens/CreateNoteScreen';
import ExploreContributeScreen from './screens/ExploreContributeScreen';
import ExploreScreen from './screens/ExploreScreen';
import HomeScreen from './screens/HomeScreen';
import MemoryContributeScreen from './screens/MemoryContributeScreen';
import PendingItemsScreen from './screens/PendingItemsScreen';
import PlacePickerScreen from './screens/PlacePickerScreen';
import ProfileScreen from './screens/ProfileScreen';
import QuestionsScreen from './screens/QuestionsScreen';
import RewardsScreen from './screens/RewardsScreen';
import SetupScreen from './screens/SetupScreen';
import { attemptAutoSync, useAutoSync } from './sync/autoSync';
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

  // The place the guide CHOSE to contribute to -- the subject of everything
  // Explore and Questions then show. Null means "not chosen yet", which is
  // what puts the picker in front of those two tabs.
  //
  // Session state rather than a stored preference, deliberately: a guide who
  // reopens the app has usually moved, and silently reusing yesterday's
  // choice would attach today's reports to somewhere they have left. Home and
  // Activity stay reachable without choosing, because neither is about a
  // place -- Home is about this device, Activity about what it holds.
  const [selectedPlace, setSelectedPlace] = useState<PlaceCandidate | null>(null);
  // Set when the guide opens the picker to CHANGE an existing choice, so
  // backing out returns them to where they were instead of clearing it.
  const [changingPlace, setChangingPlace] = useState(false);
  // The guide got as far as the picker and could not choose -- offline, no
  // location permission, or nowhere mapped nearby. Remembering that stops the
  // picker reappearing on every tab switch and trapping them in a loop they
  // have no way to satisfy. Explore and Questions then behave exactly as they
  // did before this step existed, resolving the place from GPS.
  const [skippedPlace, setSkippedPlace] = useState(false);

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
    // Leaving the tab abandons an in-progress "change place" -- otherwise the
    // picker would follow the guide to Home, since `changingPlace` is not
    // tab-scoped. The existing choice is untouched, exactly as if they had
    // tapped "Keep current place".
    setChangingPlace(false);
    setRefreshKey((k) => k + 1);
  }, []);

  const closePushed = useCallback((returnTo?: TabKey) => {
    setPushed(null);
    setAnswerTarget(null);
    setSelectedPrompt(null);
    if (returnTo) setActiveTab(returnTo);
    setRefreshKey((k) => k + 1);
    // Closing a pushed screen (note/voice/explore/memory/answer) is the
    // moment right after a local save — the natural trigger for "auto sync
    // means I don't have to think about it" while already online, not only
    // on the next Wi-Fi reconnect (see attemptAutoSync's own doc).
    attemptAutoSync(db);
  }, [db]);

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
        // The guide's currently selected Location, if any -- lets the answer
        // screen pre-fill (visibly, removably) the same place Explore/
        // Questions are already scoped to, instead of leaving every answer's
        // own location to depend solely on a fresh GPS capture. See
        // AnswerQuestionScreen's Props.place doc for why this is a pre-fill,
        // never a forced overwrite of the question's own target.
        place={selectedPlace}
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
        // What the guide CHOSE, so the saved capture records the subject they
        // picked rather than leaving Activity unable to say what the report
        // was about. Never a device guess: this is a real backend Location.
        place={selectedPlace}
        onDone={() => closePushed(explorePromptOrigin)}
      />
    );
  }

  if (pushed === 'memoryContribute') {
    return <MemoryContributeScreen guide={guide} onDone={() => closePushed('explore')} />;
  }

  // The place-selection step. Applies ONLY to the two place-scoped tabs:
  // putting it in front of Home or Activity would make a guide choose a
  // subject before they can even see what is waiting to sync, which has
  // nothing to do with where they are standing.
  //
  // Rendered INSIDE the tab shell, below, rather than as a full-screen
  // takeover -- it keeps the tab bar. It is a state of Explore/Questions, not
  // a destination the guide asked for, so removing their way out would strand
  // anyone who cannot choose right now (offline, no permission, nowhere
  // mapped) with no route back to Home or Activity. Pushed screens still take
  // the full screen, and should: those are tasks the guide deliberately
  // started, where focus is the point.
  const needsPlace =
    (activeTab === 'explore' || activeTab === 'questions') && !selectedPlace && !skippedPlace;
  const showPlacePicker = needsPlace || changingPlace;

  return (
    <View style={styles.shell}>
      <View style={styles.content}>
        {showPlacePicker ? (
          <PlacePickerScreen
            guide={guide}
            // Which tab asked, so the picker can say what choosing will do
            // next instead of appearing as an unexplained interruption.
            forTab={activeTab === 'questions' ? 'questions' : 'explore'}
            onSelect={(place) => {
              setSelectedPlace(place);
              setChangingPlace(false);
              setSkippedPlace(false);
              // Both place-scoped tabs re-read on refreshKey, so this is what
              // makes them reload against the NEW subject rather than keep
              // showing the previous place's questions.
              setRefreshKey((k) => k + 1);
            }}
            onSkip={() => {
              setSkippedPlace(true);
              setChangingPlace(false);
              setRefreshKey((k) => k + 1);
            }}
            onCancel={changingPlace ? () => setChangingPlace(false) : undefined}
          />
        ) : activeTab === 'home' ? (
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
            place={selectedPlace}
            onChangePlace={() => setChangingPlace(true)}
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
            place={selectedPlace}
            onChangePlace={() => setChangingPlace(true)}
            onSelectQuestion={(question) => {
              setAnswerTarget(targetFromQuestion(question));
              setPushed('answerQuestion');
            }}
            onSelectPopularQuestion={(question, placeName) => {
              // EVERY place question goes to the compose screen with media,
              // not just the ones whose kind literally asks for a photo or a
              // voice note. Standing in front of the thing being asked about
              // is exactly when a picture or a spoken answer is easiest and
              // most useful, and which of those a guide reaches for is their
              // call, not something the question's `contributionKind` should
              // decide for them -- that field says what we ASKED for, not what
              // they are allowed to send. Photo and voice remain optional
              // here; the kind still drives the placeholder and whether the
              // photo control is foregrounded (see placeQuestionToExplorePrompt).
              setSelectedPrompt(placeQuestionToExplorePrompt(question, placeName));
              setExplorePromptOrigin('questions');
              setPushed('exploreContribute');
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
