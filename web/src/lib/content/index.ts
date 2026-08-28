import { apiContentSource } from "./api";
import { mockContentSource } from "./mock";
import type { ContentSource } from "./types";

/**
 * The single seam between "real backend" and "demo data" -- every page
 * imports `content` from here and never touches api.ts/mock.ts directly,
 * so switching NEXT_PUBLIC_USE_MOCK_DATA is a one-line environment change,
 * not a code change. See .env.example.
 */
export const content: ContentSource =
  process.env.NEXT_PUBLIC_USE_MOCK_DATA === "true" ? mockContentSource : apiContentSource;

export const usingMockData = process.env.NEXT_PUBLIC_USE_MOCK_DATA === "true";

export * from "./types";
