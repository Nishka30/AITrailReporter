import { readStoredAuth } from '../auth/AdminAuthContext';

/**
 * Base URL for the FastAPI backend. Configurable via the VITE_API_BASE_URL
 * env var (see admin/.env.example and the README) -- never hardcode a host
 * elsewhere in the app. Mirrors mobile/src/api/client.ts's
 * EXPO_PUBLIC_API_BASE_URL convention.
 */
const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(
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

/** The request never reached the backend (offline, wrong URL, CORS, backend down). */
export class NetworkError extends Error {
  originalError: unknown;

  constructor(originalError: unknown) {
    super('Could not reach the server. Check your connection and API URL.');
    this.name = 'NetworkError';
    this.originalError = originalError;
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
};

function extractDetailMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return fallback;
}

// Generous timeout for an admin desktop connection -- not tuned to the
// fastest expected request, just bounded so a dead connection resolves into
// an honest NetworkError instead of hanging a loading spinner forever
// (same reasoning as mobile/src/api/client.ts's REQUEST_TIMEOUT_MS).
const REQUEST_TIMEOUT_MS = 20_000;

/**
 * Minimal fetch wrapper shared by every admin API call (see api/admin.ts).
 * Attaches the admin token/display-name headers from whatever is currently
 * stored (see auth/AdminAuthContext.tsx) -- never bakes a token into this
 * file or the built bundle.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const auth = readStoredAuth();

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(auth ? { 'X-Admin-Token': auth.token, 'X-Admin-Name': auth.name } : {}),
      },
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

/**
 * Fetches an evidence media file (audio/photo) and returns a local blob: URL
 * for an <audio>/<img> element to point at. Media routes require the same
 * X-Admin-Token header as every other admin request, and an <audio>/<img>
 * src cannot attach custom headers -- so the file is fetched here (with
 * headers) and handed to the element as an object URL instead of a direct
 * backend URL. Callers must revoke the returned URL (URL.revokeObjectURL)
 * when done with it, e.g. in a useEffect cleanup.
 */
export async function fetchMediaBlobUrl(path: string): Promise<string> {
  const auth = readStoredAuth();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: auth ? { 'X-Admin-Token': auth.token, 'X-Admin-Name': auth.name } : {},
  });
  if (!response.ok) {
    throw new ApiError(response.status, `Failed to load media (status ${response.status})`, null);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}
