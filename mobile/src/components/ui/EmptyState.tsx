import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { colors, spacing, type } from '../../theme/theme';
import Button from './Button';

type Props = {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
};

/** A calm, intentional "nothing here" state — never a blank ScrollView. */
export default function EmptyState({ icon, title, message, actionLabel, onAction }: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.iconCircle}>
        <Ionicons name={icon} size={26} color={colors.inkFaint} />
      </View>
      <Text style={styles.title}>{title}</Text>
      {message ? <Text style={styles.message}>{message}</Text> : null}
      {actionLabel && onAction ? (
        <View style={styles.actionWrap}>
          <Button label={actionLabel} onPress={onAction} variant="secondary" fullWidth={false} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', paddingVertical: spacing.xxl, paddingHorizontal: spacing.lg },
  iconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.paperMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  title: { ...type.subtitle, color: colors.ink, textAlign: 'center' },
  message: {
    ...type.small,
    color: colors.inkFaint,
    textAlign: 'center',
    marginTop: spacing.xs,
    maxWidth: 280,
  },
  actionWrap: { marginTop: spacing.md },
});
