import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { colors, spacing, type } from '../../theme/theme';

type Props = {
  message?: string;
};

/** Real async loading only — never used to fake a delay (Part K). */
export default function LoadingState({ message = 'Loading…' }: Props) {
  return (
    <View style={styles.container}>
      <ActivityIndicator size="small" color={colors.marigoldDeep} />
      <Text style={styles.message}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', paddingVertical: spacing.xxl },
  message: { ...type.small, color: colors.inkFaint, marginTop: spacing.sm },
});
