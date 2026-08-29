from pydantic import BaseModel


class PlaceSearchResult(BaseModel):
    """One candidate the guide might mean, from app/services/geocoding.py.
    `label` is the full human-readable name to show in the suggestion list --
    the mobile app never constructs its own display string from raw parts."""

    label: str
    latitude: float
    longitude: float


class PlaceSearchResponse(BaseModel):
    results: list[PlaceSearchResult]
