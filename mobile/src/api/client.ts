/**
 * Base URL for the FastAPI backend. Configurable via the EXPO_PUBLIC_API_BASE_URL
 * env var (see mobile/.env.example and the README) — never hardcode a host
 * elsewhere in the app. The default below only works from a web build or an iOS
 * simulator on the same machine as the backend; a physical device or an Android
 * emulator needs an explicit override.
 */
const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

export const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(
  /\/+$/,
  ''
);

/** The backend responded, but with a non-2xx status. */
export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

/** The request never reached the backend (offline, wrong URL, backend down, etc). */
export class NetworkError extends Error {
  originalError: unknown;

  constructor(originalError: unknown) {
    super('Could not reach the server. Check your connection and API URL.');
    this.name = 'NetworkError';
    this.originalError = originalError;
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST';
  body?: unknown;
};

/** Exported so api/audio.ts's multipart upload (which can't go through
 * apiRequest() — see that file) can format errors the same way as every other
 * endpoint module. */
export function extractDetailMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return fallback;
}

/** React Native's fetch() has no built-in timeout: on a flaky mobile
 * connection (WiFi dropping mid-request, a dead TCP socket that never resets)
 * it can stay pending forever, neither resolving nor rejecting. Every caller
 * of apiRequest() awaits it inside a try/finally that only releases its
 * loading state once the awaited promise SETTLES — so a promise that never
 * settles means that loading state never terminates, exactly the "keeps
 * loading indefinitely" failure mode. Aborting after a bounded time turns
 * that hang into an honest NetworkError, which every existing caller already
 * catches and surfaces truthfully. Value chosen generously for a slow trail
 * connection, not tuned to this app's fastest expected request. */
const REQUEST_TIMEOUT_MS = 20_000;

/**
 * Minimal fetch wrapper shared by every endpoint module in src/api/. Screens and
 * the sync engine never call fetch() directly — everything goes through this (or
 * the per-resource functions built on it) so error handling and the base URL stay
 * in one place.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? 'GET',
      headers: { 'Content-Type': 'application/json' },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    throw new NetworkError(err);
  } finally {
    clearTimeout(timeoutId);
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractDetailMessage(payload, `Request failed with status ${response.status}`),
      payload
    );
  }

  return payload as T;
}
