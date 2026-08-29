"""Prompt and output schema for POI discovery.

Given a coordinate, find the REAL named places around it. This is the step that
lets the rest of the system be specific: with no Location rows near a guide,
`geographic_context` resolves nothing, place research never runs, and Explore
falls back to generic prompts no matter how good the downstream prompts are.

THE HARD PART IS NOT FINDING PLACES, IT IS NOT INVENTING THEM.

A language model asked "what is near 12.93, 77.63" will happily produce a
plausible cafe with plausible coordinates, because plausible is what it is
good at. A fabricated Location is worse than no Location: it becomes a
permanent anchor that later research, invitations, observations and rewards all
attach themselves to, and it is indistinguishable from a real one once stored.

So the defences are layered, and the prompt is only the first:
  - this prompt demands search-grounded results and real citations
  - validation.py structurally requires a name, coordinates and >=1 real URL
  - poi_discovery.py rejects any place whose coordinates fall outside a sane
    radius of the query point, which is what actually catches invented
    coordinates (a hallucinated lat/lon is rarely nearby by luck)
  - every stored row is marked source='discovered' with its citations, so it
    stays auditable and separable from curated data forever
"""

DISCOVERY_TOOL_MAX_SEARCHES = 5

SYSTEM_PROMPT = """You find the REAL, named, specific places that exist near a \
given coordinate, so that a field app can recognise where its users are standing.

You will be given a latitude and longitude and a search radius.

WHAT COUNTS AS A PLACE
Specific, named, physically-present things a person could walk to and point at:
  - landmarks, monuments, memorials, statues
  - bridges, gates, steps, crossings, junctions with real names
  - viewpoints, summits, lakes, waterfalls, springs, notable trees
  - temples, mosques, churches, shrines, monasteries, stupas
  - parks, gardens, lakes, trailheads, specific trail sections
  - well-known cafes, restaurants, tea stalls, bakeries, markets, shops
  - museums, galleries, libraries, stadiums, theatres
  - specific stations, terminals and stops, if they are genuinely named landmarks

WHAT DOES NOT COUNT -- never return these:
  - a city, suburb, neighbourhood, district, locality or postcode. "Koramangala"
    and "Thamel" are AREAS, not places. They are far too broad to stand at.
  - a road, street or highway on its own
  - a chain outlet with no specific local significance
  - a category rather than an instance ("some cafes", "several temples")
  - anything you cannot find in search results

RULES YOU MUST FOLLOW EXACTLY

1. SEARCH FIRST. Use web search to find what is actually at and around this
   coordinate. Do not answer from general knowledge about the region.

2. NEVER INVENT A PLACE. If search does not establish that a place exists, and
   roughly where it is, leave it out. Returning an empty list is a correct,
   expected and useful answer -- much of the world has no documented named
   places, and saying so honestly is far better than filling the list.

3. NEVER GUESS COORDINATES. Give the place's real latitude and longitude as
   established by your sources. If you found the place but cannot establish
   where it actually is, leave it out. Do not copy the query coordinate, do not
   approximate from the area name, and do not nudge a number to make a place
   look closer than it is.

4. EVERY place must have at least one real source URL from your search results
   that supports its existence, its name and its location.

5. Only include places within the given radius of the query coordinate. A
   famous place 40km away is not where this person is standing.

6. Give each place a SHORT factual description of what it actually is, based on
   your sources -- not marketing copy, not an invented history.

7. Prefer places that are distinctive and recognisable on the ground over
   generic ones. A named bridge beats an unnamed shop.

8. Do not return the same place twice under different names.

Return between 0 and 8 places. Fewer, certain places beat more, uncertain ones."""


def build_user_message(latitude: float, longitude: float, radius_meters: int) -> str:
    return (
        f"Coordinate: {latitude:.5f}, {longitude:.5f}\n"
        f"Search radius: {radius_meters} metres\n"
        "\n"
        "Search the web for the real, named places that exist within this radius "
        "of this coordinate. Return only places your search results actually "
        "establish, each with its real coordinates and at least one source URL."
    )


# Structured output via `output_config.format` rather than a forced tool call,
# for the same reason as place-question research: tool_choice cannot be pinned
# to a custom tool while the web_search server tool must also be free to run.
OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            # No `maxItems`: the structured-output validator rejects it for
            # arrays. The cap is enforced server-side in poi_discovery.py.
            "places": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "The specific place's real name, as it appears in sources. "
                                "Never an area, neighbourhood, city or road."
                            ),
                        },
                        "place_kind": {
                            "type": "string",
                            "description": (
                                "What kind of place it is, lowercase: bridge, viewpoint, "
                                "cafe, temple, park, market, museum, trailhead, ..."
                            ),
                        },
                        "latitude": {
                            "type": "number",
                            "description": (
                                "The place's REAL latitude from your sources. Never the query "
                                "coordinate, never an estimate from the area name."
                            ),
                        },
                        "longitude": {
                            "type": "number",
                            "description": "The place's REAL longitude from your sources.",
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "One short factual sentence about what this place is, "
                                "supported by your sources."
                            ),
                        },
                        "source_urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "REQUIRED, at least one real URL from search establishing this "
                                "place's existence, name and location."
                            ),
                        },
                    },
                    "required": [
                        "name",
                        "place_kind",
                        "latitude",
                        "longitude",
                        "description",
                        "source_urls",
                    ],
                    "additionalProperties": False,
                },
            },
            "found_information": {
                "type": "boolean",
                "description": (
                    "True only if search returned real information about places at this "
                    "coordinate. False means the places list should be empty."
                ),
            },
        },
        "required": ["places", "found_information"],
        "additionalProperties": False,
    },
}
