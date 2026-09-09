from pydantic import BaseModel


class PlaceSearchResult(BaseModel):
    """One candidate the guide might mean, from
    app/services/places/google_provider.py. `label` is the full
    human-readable name to show in the suggestion list -- the mobile app
    never constructs its own display string from raw parts."""

    label: str
    latitude: float
    longitude: float
    # The provider's own id for this place, when picking THIS specific
    # candidate is unambiguous enough to carry through as
    # location_source='user_selected' provenance (see Submission.
    # external_place_id). None when the provider couldn't supply one.
    place_id: str | None = None


class PlaceSearchResponse(BaseModel):
    results: list[PlaceSearchResult]
