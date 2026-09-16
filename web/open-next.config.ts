import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// Minimal config: the default in-memory ISR cache is fine at this site's
// current scale (the backend's own 60s `revalidate` window in
// lib/content/api.ts already keeps requests bounded). Swap in
// `@opennextjs/cloudflare/overrides/incremental-cache/r2-incremental-cache`
// later if page traffic grows enough to want a durable, shared ISR cache
// across Worker instances.
export default defineCloudflareConfig({});
