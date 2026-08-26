# AI Trail Reporter

A location-first field guide knowledge system. Two independent projects:

- [`backend/`](backend/README.md) — FastAPI + PostgreSQL/PostGIS API. See its README
  for setup, migrations, and the full API reference.
- [`mobile/`](mobile/README.md) — Offline-first React Native/Expo guide app, backed
  by a local SQLite database. See its README for setup and the local data model.

The two are not wired together yet — the mobile app does not call the backend, and
nothing needs to be running on one side for the other to work. Synchronization
between them is a later step.
