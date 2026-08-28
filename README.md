# AI Trail Reporter

A location-first field guide knowledge system. Three projects:

- [`backend/`](backend/README.md) — FastAPI + PostgreSQL/PostGIS API. See its README
  for setup, migrations, and the full API reference.
- [`mobile/`](mobile/README.md) — Offline-first React Native/Expo guide app, backed
  by a local SQLite database, syncing to the backend. See its README for setup and
  the local data model.
- [`admin/`](admin/README.md) — React/Vite web app for content curation and
  moderation: the human-review layer between field submissions and any future
  public-facing app. Talks to the backend only through `/api/v1/admin/*`, never
  directly to PostgreSQL. See its README, and
  [`backend/README.md`'s admin section](backend/README.md#admin-dashboard--content-curation--moderation-layer-step-18)
  for the moderation model.
