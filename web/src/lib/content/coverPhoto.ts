import { content } from "./index";

/** Best-effort cover photo for a location: the most recent approved
 * observation near it that happens to carry a photo. Not a backend field
 * (see plan) -- composed here via a small, bounded number of extra calls,
 * used only for a handful of cards on the home/explore pages. */
export async function coverPhotoFor(locationId: string): Promise<string | null> {
  const result = await content.listObservations({ locationId, hasPhoto: true, limit: 1 });
  return result.items[0]?.photo_url ?? null;
}
