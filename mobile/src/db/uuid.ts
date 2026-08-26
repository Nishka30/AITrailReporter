import * as Crypto from 'expo-crypto';

/**
 * Generates a stable client-side identifier (RFC4122 v4 UUID string), used for
 * client_guide_id / client_submission_id. Centralized here so there is exactly one
 * place that decides how these ids are generated — callers must never regenerate
 * one for an existing row, only call this when a row is first created (or, during
 * the v1->v2 migration, once per pre-existing row that doesn't have one yet).
 */
export function generateClientId(): string {
  return Crypto.randomUUID();
}
