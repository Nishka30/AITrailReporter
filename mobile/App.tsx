import { View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SQLiteProvider } from 'expo-sqlite';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { DATABASE_NAME, migrateDbIfNeeded } from './src/db/database';
import RootNavigator from './src/RootNavigator';
import { useAppFonts } from './src/theme/fonts';
import { colors } from './src/theme/theme';

export default function App() {
  const fontsLoaded = useAppFonts();

  // Every screen renders text using theme.ts's custom font families — wait
  // for both font sets before mounting RootNavigator so nothing ever
  // flashes in (or silently falls back to) the platform default font.
  if (!fontsLoaded) {
    return <View style={{ flex: 1, backgroundColor: colors.paper }} />;
  }

  return (
    <SafeAreaProvider>
      <SQLiteProvider databaseName={DATABASE_NAME} onInit={migrateDbIfNeeded}>
        <RootNavigator />
        <StatusBar style="dark" />
      </SQLiteProvider>
    </SafeAreaProvider>
  );
}
