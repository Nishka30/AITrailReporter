/**
 * Phone number handling for the guide profile (Step 17).
 *
 * DELIBERATELY MINIMAL. This app has no existing country/locale logic anywhere,
 * and the backend stores phone_number as a plain `String(32)` with no format
 * constraint of its own (see backend/app/db/models/guide.py). Inventing
 * country-code rules here would be a guess about users this project has not
 * defined, and would reject legitimate numbers from guides in regions the
 * assumption didn't cover — a much worse failure than accepting an unusual
 * format.
 *
 * So the rules are only the ones that are true regardless of country:
 *   - it must contain enough digits to be a phone number at all
 *   - it must not contain characters no phone number uses
 *   - it must fit the backend's 32-character column
 */

/** Characters that legitimately appear in internationally-written numbers. */
const ALLOWED_PATTERN = /^[0-9+\-()\s.]+$/;

/** Matches the backend's Guide.phone_number column width — validated here so
 * the guide is told immediately rather than by a failed sync much later. */
const MAX_LENGTH = 32;

const MIN_DIGITS = 6;
const MAX_DIGITS = 15; // E.164's global maximum; safe as an upper bound anywhere.

export type PhoneValidation = { valid: true } | { valid: false; message: string };

export function countDigits(value: string): number {
  return (value.match(/\d/g) ?? []).length;
}

/**
 * Validates a REQUIRED phone number. Returns a specific, actionable message
 * rather than a generic "invalid" so the guide knows what to change.
 */
export function validatePhoneNumber(raw: string): PhoneValidation {
  const value = raw.trim();
  if (!value) {
    return { valid: false, message: 'Please enter your phone number.' };
  }
  if (value.length > MAX_LENGTH) {
    return { valid: false, message: `Phone number must be ${MAX_LENGTH} characters or fewer.` };
  }
  if (!ALLOWED_PATTERN.test(value)) {
    return {
      valid: false,
      message: 'Phone number can only contain digits and + - ( ) or spaces.',
    };
  }
  const digits = countDigits(value);
  if (digits < MIN_DIGITS) {
    return { valid: false, message: 'That does not look like a complete phone number.' };
  }
  if (digits > MAX_DIGITS) {
    return { valid: false, message: 'That phone number has too many digits.' };
  }
  return { valid: true };
}

/**
 * Normalizes for storage: trims and collapses internal whitespace runs, but
 * does NOT strip formatting characters. The number the guide typed is the
 * number a human will read back and dial — silently rewriting it into a
 * canonical form we cannot reliably compute would be worse than keeping theirs.
 */
export function normalizePhoneNumber(raw: string): string {
  return raw.trim().replace(/\s+/g, ' ');
}
