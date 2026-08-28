# AI Trail Reporter — Admin Console

A standalone React + TypeScript + Vite web app: the content curation and
moderation layer between field-collected data and any future public-facing
app. It is a **separate deployable** from `mobile/` and `backend/` — it does
not touch either, and connects to the backend only through the existing
FastAPI API (`/api/v1/admin/*`), never directly to PostgreSQL.

See [`backend/README.md`](../backend/README.md#admin-dashboard--content-curation--moderation-layer-step-18)
for the moderation model, database changes, and full endpoint reference —
this file covers only the frontend.

## Why this exists

Nothing about a submission existing, transcription succeeding, AI extraction
succeeding, or knowledge being "fresh" makes it publicly visible. **AI
assists. Humans curate.** This app is where that human decision happens —
per observation, with full source evidence (original text, audio, photo)
always attached, never rewritten or discarded.

## Setup

1. Copy `.env.example` to `.env` and point `VITE_API_BASE_URL` at your
   backend (defaults to `http://127.0.0.1:8000`).
2. Install dependencies:

   ```
   npm install
   ```

3. Make sure the backend has `ADMIN_API_TOKEN` set (see
   [`backend/README.md`](../backend/README.md#authentication-development-safe-not-production-grade)) —
   this app has no admin functionality without it.

## Run

```
npm run dev
```

Opens at `http://localhost:5173`. On first load you'll see a login screen
asking for the admin token (from `ADMIN_API_TOKEN` on the backend) and a
display name (used only to label decisions you make — not a verified
identity). Both are stored in this browser's `localStorage`, never in the
built bundle.

## Build

```
npm run build   # tsc --noEmit && vite build, output in dist/
npm run preview # serve the production build locally
```

## Design system

This app deliberately reuses the mobile app's exact visual identity —
`tailwind.config.js` mirrors `mobile/src/theme/theme.ts`'s color palette
value-for-value (warm cream/paper background, marigold accent, dark ink
text, `Bricolage Grotesque` headings, `Atkinson Hyperlegible` body text) —
so the two apps read as the same product, not a generic admin template
bolted onto a different brand. The **layout** is intentionally different:
mobile is field-first (large touch targets, one task per screen); this app
is desktop-first, information-dense, and review-focused (tables, filters,
multi-panel detail views) — same brand, different job.

## Architecture

```
src/
  api/client.ts          Fetch wrapper (mirrors mobile/src/api/client.ts's
                          conventions) — attaches the admin token/name headers,
                          times out, normalizes errors into ApiError/NetworkError
  api/admin.ts            One typed function per backend admin endpoint
  api/types.ts             TS types mirroring backend/app/schemas/admin.py
                          and observation_moderation.py field-for-field
  auth/AdminAuthContext.tsx  Token/name storage (localStorage) + React context
  components/layout/      AdminShell, Sidebar, PageHeader
  components/ui/          StatusBadge, StatCard, Pagination, loading/empty/error states
  components/review/      ObservationCard, AudioPlayer, ImageViewer,
                          DecisionDialog, ModerationActions, ObservationListView
                          (shared by Review Queue and Knowledge)
  pages/                  One file per route (see App.tsx for the route table)
  theme/tokens.ts          Plain-TS mirror of the Tailwind palette, for the
                          rare spot needing a raw color value
```

`ObservationListView` is the one shared component behind both the **Review
Queue** (`/review-queue`, defaults to `status=pending_review`) and the
**Knowledge** browser (`/knowledge`, defaults to all statuses) — same
filters, same card, same pagination, because they are the same underlying
query with a different default filter (see
`backend/app/services/admin_review.py`).

**Review Detail** (`/review/:observationId`) renders the full provenance
chain in four panels: Source (original text/audio/photo, never rewritten) →
AI Extracted Knowledge (the observation's structured value + evidence +
confidence) → Knowledge Context (live freshness state at that coordinate,
plus other nearby reports of the same knowledge type — the honest stand-in
for conflict detection, which does not exist in this system) → Admin
Decision (`ModerationActions`).

Audio/photo evidence is fetched as an authenticated blob (`fetchMediaBlobUrl`
in `api/client.ts`) rather than linked directly, because `<audio>`/`<img>`
elements can't send the `X-Admin-Token` header the media routes require.

## What was NOT tested

No browser was available in the environment this was built in, so the UI was
verified via: a clean `npm run build` (TypeScript + Vite bundling), and the
backend endpoints it calls were exercised end-to-end via `curl` (create
guide → submit → extract → appears in review queue → approve → change
decision → reject), including the concurrent-decision-locking and
invalid-reason-rejection paths. The actual rendered pages, click-through
flows, and responsive behavior have not been visually verified in a real
browser — do that before relying on this for real moderation work.
