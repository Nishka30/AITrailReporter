import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { DatePrecision } from '../types/models';
import { colors, radii, spacing, type } from '../theme/theme';

export interface ApproximateDateValue {
  occurredAt: string | null;
  precision: DatePrecision;
}

type Props = {
  value: ApproximateDateValue;
  onChange: (value: ApproximateDateValue) => void;
  disabled?: boolean;
};

const PRECISION_OPTIONS: { key: DatePrecision; label: string }[] = [
  { key: 'exact', label: 'Exact date' },
  { key: 'month', label: 'Month & year' },
  { key: 'year', label: 'Year only' },
  { key: 'unknown', label: "I'm not sure" },
];

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/** Splits an ISO string back into the pieces this field edits, defensively —
 * a malformed or missing value just yields empty fields rather than throwing. */
function toParts(iso: string | null): { year: string; month: string; day: string } {
  if (!iso) return { year: '', month: '', day: '' };
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { year: '', month: '', day: '' };
  return { year: String(d.getFullYear()), month: pad(d.getMonth() + 1), day: pad(d.getDate()) };
}

/**
 * "When was this?" — deliberately NOT a calendar widget. This app has no
 * existing date-picker pattern to follow and no device available to verify a
 * new native picker dependency on, so this is built from plain text entry
 * with the precision the guide actually has, never more than that.
 *
 * THE HONESTY RULE THIS EXISTS TO SERVE: a guide who only remembers "sometime
 * in 2024" must be able to say exactly that, rather than being forced to
 * invent a specific day just to satisfy a form. Selecting a coarser
 * precision hides the fields a guide can't fill and stores only what was
 * actually said (see occurredAtPrecision on the resulting Submission) — a
 * guessed day-of-month would be exactly the fabricated confidence this whole
 * feature exists to prevent.
 */
export default function ApproximateDateField({ value, onChange, disabled }: Props) {
  const parts = useMemo(() => toParts(value.occurredAt), [value.occurredAt]);
  const [year, setYear] = useState(parts.year);
  const [month, setMonth] = useState(parts.month);
  const [day, setDay] = useState(parts.day);

  function commit(precision: DatePrecision, y: string, mo: string, d: string) {
    if (precision === 'unknown') {
      onChange({ occurredAt: null, precision: 'unknown' });
      return;
    }
    const yearNum = Number(y);
    if (!y || !Number.isInteger(yearNum) || yearNum < 1900 || yearNum > 2100) {
      // Incomplete/invalid entry — not yet a value, but not an error either;
      // the guide is still typing. Nothing is stored until it parses.
      onChange({ occurredAt: null, precision });
      return;
    }
    const monthNum = precision !== 'year' ? Number(mo) : 1;
    const dayNum = precision === 'exact' ? Number(d) : 1;
    if (precision !== 'year' && (!mo || monthNum < 1 || monthNum > 12)) {
      onChange({ occurredAt: null, precision });
      return;
    }
    if (precision === 'exact' && (!d || dayNum < 1 || dayNum > 31)) {
      onChange({ occurredAt: null, precision });
      return;
    }
    // Constructed at local noon, not midnight: keeps the date stable across
    // this device's own timezone without implying a time-of-day that was
    // never actually known — this field only ever claims day-level precision
    // at most.
    const iso = new Date(yearNum, monthNum - 1, dayNum, 12, 0, 0).toISOString();
    onChange({ occurredAt: iso, precision });
  }

  function handlePrecisionSelect(precision: DatePrecision) {
    commit(precision, year, month, day);
  }

  return (
    <View>
      <View style={styles.pillRow}>
        {PRECISION_OPTIONS.map((opt) => {
          const active = value.precision === opt.key;
          return (
            <Pressable
              key={opt.key}
              onPress={() => handlePrecisionSelect(opt.key)}
              disabled={disabled}
              style={({ pressed }) => [
                styles.pill,
                active && styles.pillActive,
                pressed && styles.pillPressed,
                disabled && styles.pillDisabled,
              ]}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
            >
              <Text style={[styles.pillLabel, active && styles.pillLabelActive]}>{opt.label}</Text>
            </Pressable>
          );
        })}
      </View>

      {value.precision !== 'unknown' ? (
        <View style={styles.fieldsRow}>
          {value.precision === 'exact' ? (
            <TextInput
              style={[styles.numberInput, styles.dayInput]}
              placeholder="DD"
              placeholderTextColor={colors.inkFaint}
              keyboardType="number-pad"
              maxLength={2}
              value={day}
              editable={!disabled}
              onChangeText={(t) => {
                setDay(t);
                commit('exact', year, month, t);
              }}
            />
          ) : null}
          {value.precision !== 'year' ? (
            <TextInput
              style={[styles.numberInput, styles.monthInput]}
              placeholder="MM"
              placeholderTextColor={colors.inkFaint}
              keyboardType="number-pad"
              maxLength={2}
              value={month}
              editable={!disabled}
              onChangeText={(t) => {
                setMonth(t);
                commit(value.precision, year, t, day);
              }}
            />
          ) : null}
          <TextInput
            style={[styles.numberInput, styles.yearInput]}
            placeholder="YYYY"
            placeholderTextColor={colors.inkFaint}
            keyboardType="number-pad"
            maxLength={4}
            value={year}
            editable={!disabled}
            onChangeText={(t) => {
              setYear(t);
              commit(value.precision, t, month, day);
            }}
          />
        </View>
      ) : (
        <Text style={styles.unknownNote}>No problem — we'll just leave this one undated.</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  pillRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  pill: {
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.paperElevated,
    paddingHorizontal: spacing.sm,
    paddingVertical: 7,
  },
  pillActive: { backgroundColor: colors.ink, borderColor: colors.ink },
  pillPressed: { opacity: 0.8 },
  pillDisabled: { opacity: 0.5 },
  pillLabel: { ...type.small, color: colors.inkSoft },
  pillLabelActive: { color: colors.marigoldSoft },

  fieldsRow: { flexDirection: 'row', gap: spacing.xs, marginTop: spacing.sm },
  numberInput: {
    backgroundColor: colors.paperElevated,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.sm,
    height: 42,
    ...type.body,
    color: colors.ink,
    textAlign: 'center',
  },
  dayInput: { width: 56 },
  monthInput: { width: 56 },
  yearInput: { width: 76 },

  unknownNote: { ...type.caption, color: colors.inkFaint, marginTop: spacing.sm },
});
