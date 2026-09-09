/**
 * Phone number handling for the guide profile (Step 17).
 *
 * Guides are Indian mobile users, so this validates against the Indian mobile
 * numbering plan specifically: exactly 10 national digits, starting 6-9.
 * A country code may be written or omitted -- +91, 91 and a leading 0 are all
 * accepted and stripped before counting, because all three are things people
 * genuinely type and none of them change the number.
 *
 * The tighter rule earns its keep at the point of entry: a typo'd number is
 * only discovered when somebody tries to call the guide about a report, long
 * after the moment it could have been corrected. Catching a 9- or 11-digit
 * number while they are still looking at the field is the entire point.
 *
 * The value is still STORED as typed (see normalizePhoneNumber) -- validation
 * decides what to accept, not what to rewrite.
 */

/** Characters that legitimately appear in a written number. */
const ALLOWED_PATTERN = /^[0-9+\-()\s.]+$/;

/** Matches the backend's Guide.phone_number column width — validated here so
 * the guide is told immediately rather than by a failed sync much later. */
const MAX_LENGTH = 32;

/** Indian mobile numbers are 10 digits and never start below 6. */
const NATIONAL_DIGITS = 10;
const VALID_FIRST_DIGIT = /^[6-9]/;

export type PhoneValidation = { valid: true } | { valid: false; message: string };

export function countDigits(value: string): number {
  return (value.match(/\d/g) ?? []).length;
}

/**
 * The 10 national digits, with any country code or trunk prefix removed.
 * Returns the digits as typed when nothing recognisable can be stripped, so
 * the caller can report the real length back to the guide.
 */
export function nationalDigits(raw: string): string {
  const digits = (raw.match(/\d/g) ?? []).join('');
  if (digits.length === 12 && digits.startsWith('91')) return digits.slice(2);
  if (digits.length === 11 && digits.startsWith('0')) return digits.slice(1);
  return digits;
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

  const national = nationalDigits(value);
  if (national.length !== NATIONAL_DIGITS) {
    // Says which way they are wrong and by how much -- "enter 10 digits" alone
    // leaves someone staring at a field they believe already has 10.
    const diff = national.length - NATIONAL_DIGITS;
    const detail =
      diff < 0
        ? `${national.length} so far, ${-diff} more to go`
        : `that's ${national.length}`;
    return { valid: false, message: `Enter the 10-digit mobile number (${detail}).` };
  }
  if (!VALID_FIRST_DIGIT.test(national)) {
    return { valid: false, message: 'An Indian mobile number starts with 6, 7, 8 or 9.' };
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
