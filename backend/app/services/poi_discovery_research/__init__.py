"""POI discovery research (provider-isolated, mirrors place_question_research).

Two steps, deliberately split by what each source is actually authoritative
about:

    osm_provider  -- FACTS:     what named places exist here, and exactly where
    selection     -- JUDGEMENT: which of those are worth asking a guide about

No name and no coordinate ever originates from a language model. See
osm_provider's header for why that split replaced the earlier
LLM-supplies-coordinates design.
"""
