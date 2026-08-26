import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { colors, spacing, type } from '../../theme/theme';
import Button from './Button';

type Props = {
  message: string;
  onRetry?: () => void;
  retrying?: boolean;
};

/** A genuine error with a real retry action wired to the actual failed
 * operation — never a dead-end message (Part K). */
export default function ErrorState({ message, onRetry, retrying = false }: Props) {
  return (
    <View style={styles.container}>
      <Ionicons name="alert-circle-outline" size={22} color={colors.fix} />
      <Text style={styles.message}>{message}</Text>
      {onRetry ? (
        <View style={styles.actionWrap}>
          <Button label="Try again" onPress={onRetry} variant="secondary" loading={retrying} fullWidth={false} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', paddingVertical: spacing.xl, paddingHorizontal: spacing.lg },
  message: { ...type.small, color: colors.ink, textAlign: 'center', marginTop: spacing.sm },
  actionWrap: { marginTop: spacing.md },
});
