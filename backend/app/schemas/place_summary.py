"""Response shape for a Location's reusable, structured, WEB-RESEARCHED
summary (see app/db/models/location_research_summary.py). Deliberately its
own schema, not folded into LocationRead/PublicLocationSummary's fields
directly, so every consumer (admin, public) can tell at the type level that
this is research-derived content, distinct from TrailMind-verified knowledge
(CategoryKnowledgeItemRead) and from live/current data (PublicConditionState).
"""

from datetime import datetime

from pydantic import BaseModel


class PlaceResearchSummaryRead(BaseModel):
    status: str
    description: str | None = None
    known_for: str | None = None
    highlights: list[str] = []
    things_to_do: list[str] = []
    important_facts: list[str] = []
    practical_info: str | None = None
    warnings: list[str] = []
    source_urls: list[str] = []
    source_titles: list[str] = []
    # Researched-at, not created/updated-at: this is the age of the
    # EVIDENCE the summary is built from, mirroring
    # PlaceResearchFinding.retrieved_at / PlaceQuestionResearch.researched_at
    # -- only a successful generation moves it. Null when nothing has ever
    # completed successfully for this Location.
    researched_at: datetime | None = None
