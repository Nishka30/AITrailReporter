import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { searchPlaces, type PlaceSearchResult } from '../api/placeSearch';
import { colors, radii, spacing, type } from '../theme/theme';

type Props = {
  guideId: string;
  /** Called with a real, chosen place. The caller is responsible for setting
   * location_source: 'user_selected' — this component only resolves
   * candidates, it never decides provenance semantics. */
  onSelect: (place: PlaceSearchResult) => void;
  placeholder?: string;
  disabled?: boolean;
};

// Debounced so typing doesn't fire a request per keystroke — this hits a
// real (free, but rate-limited) geocoding service, and a guide typing
// "Kedarnath" should cost roughly one request, not nine.
const DEBOUNCE_MS = 350;
const MIN_QUERY_LENGTH = 2;

/**
 * Place-name search-as-you-type for describing a memory without exact
 * coordinates (see the backend's app/services/geocoding.py). Built from this
 * app's existing typography/spacing tokens — there is no prior autocomplete
 * pattern in this codebase to follow, so this establishes one rather than
 * introducing a different visual language.
 *
 * OFFLINE-AWARE, NOT OFFLINE-CAPABLE: a search that fails (no connection, or
 * the free geocoding service is briefly down) degrades to "no suggestions
 * right now" rather than an error the guide has to dismiss — selecting a
 * place is always optional, never a blocker to saving a memory (see the
 * offline-first rule in the parent screen).
 */
export default function PlaceAutocomplete({ guideId, onSelect, placeholder, disabled }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PlaceSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Guards against a slow earlier request overwriting a faster later one's
  // results — a real risk with debounced network search, not a theoretical one.
  const requestIdRef = useRef(0);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  function handleChangeText(text: string) {
    setQuery(text);
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = text.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      const thisRequestId = ++requestIdRef.current;
      try {
        const found = await searchPlaces(guideId, trimmed);
        if (requestIdRef.current === thisRequestId) {
          setResults(found);
        }
      } catch {
        // A failed search is a normal, expected outcome offline or on a flaky
        // trail connection — degrade to "no suggestions", never an error banner
        // for what is an optional convenience.
        if (requestIdRef.current === thisRequestId) {
          setResults([]);
        }
      } finally {
        if (requestIdRef.current === thisRequestId) {
          setLoading(false);
        }
      }
    }, DEBOUNCE_MS);
  }

  function handleSelect(place: PlaceSearchResult) {
    onSelect(place);
    setQuery('');
    setResults([]);
  }

  return (
    <View>
      <View style={styles.inputRow}>
        <Ionicons name="search-outline" size={16} color={colors.inkFaint} style={styles.searchIcon} />
        <TextInput
          style={styles.input}
          placeholder={placeholder ?? 'Search for a place…'}
          placeholderTextColor={colors.inkFaint}
          value={query}
          onChangeText={handleChangeText}
          editable={!disabled}
          autoCorrect={false}
        />
        {loading ? <ActivityIndicator size="small" color={colors.inkFaint} /> : null}
      </View>

      {results.length > 0 ? (
        <View style={styles.results}>
          {results.map((place, index) => (
            <Pressable
              key={`${place.latitude},${place.longitude},${index}`}
              onPress={() => handleSelect(place)}
              style={({ pressed }) => [styles.resultRow, pressed && styles.resultRowPressed]}
              accessibilityRole="button"
            >
              <Ionicons name="location-outline" size={15} color={colors.marigoldDeep} />
              <Text style={styles.resultLabel} numberOfLines={2}>
                {place.label}
              </Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.paperElevated,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    height: 46,
    gap: spacing.xs,
  },
  searchIcon: { marginRight: 2 },
  input: { flex: 1, ...type.body, color: colors.ink, paddingVertical: 0 },
  results: {
    marginTop: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    backgroundColor: colors.paperElevated,
    overflow: 'hidden',
  },
  resultRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  resultRowPressed: { backgroundColor: colors.paperMuted },
  resultLabel: { ...type.small, color: colors.ink, flexShrink: 1, lineHeight: 18 },
});
