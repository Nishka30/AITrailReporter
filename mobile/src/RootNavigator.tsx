import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';

import type { Question } from './api/questions';
import { colors, spacing, type } from './theme/theme';
import { LoadingState, TabBar, type TabKey } from './components/ui';
import { useLocalActivityCount } from './hooks/useLocalActivityCount';
import { getCurrentLocalGuide } from './repositories/guideRepository';
import AnswerQuestionScreen from './screens/AnswerQuestionScreen';
import CreateNoteScreen from './screens/CreateNoteScreen';
import HomeScreen from './screens/HomeScreen';
import PendingItemsScreen from './screens/PendingItemsScreen';
import QuestionsScreen from './screens/QuestionsScreen';
import SetupScreen from './screens/SetupScreen';
import type { LocalGuide } from './types/models';

type PushedScreen = 'createNote' | 'answerQuestion' | null;

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
  const [selectedQuestion, setSelectedQuestion] = useState<Question | null>(null);
  const [questionBadgeCount, setQuestionBadgeCount] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const activityCount = useLocalActivityCount(db, guide?.id ?? null, refreshKey);

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
    setSelectedQuestion(null);
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

  if (pushed === 'answerQuestion' && selectedQuestion) {
    return (
      <AnswerQuestionScreen
        guide={guide}
        question={selectedQuestion}
        onDone={() => closePushed('questions')}
      />
    );
  }

  return (
    <View style={styles.shell}>
      <View style={styles.content}>
        {activeTab === 'home' ? (
          <HomeScreen
            guide={guide}
            onCreateNote={() => setPushed('createNote')}
            onViewQuestions={() => goToTab('questions')}
            onViewActivity={() => goToTab('activity')}
            refreshKey={refreshKey}
          />
        ) : activeTab === 'questions' ? (
          <QuestionsScreen
            guide={guide}
            onSelectQuestion={(question) => {
              setSelectedQuestion(question);
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
