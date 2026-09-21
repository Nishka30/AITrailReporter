"""The ONE canonical definition of "is this a real, usable coordinate" for a
CONTRIBUTION's own location -- used by every schema that accepts client-
supplied latitude/longitude (SubmissionCreate, AnswerLocationFields,
LocationCreate), so the rule lives in exactly one place rather than being
re-implemented, and potentially re-drifted, per schema.

Distinct from Pydantic's own `ge=-90, le=90` / `ge=-180, le=180` Field
constraints, which stay on those fields too (they reject a wildly out-of-
range value with a clearer per-field error) -- this module adds the one
check that a plain numeric range can never express: (0, 0) is mathematically
a valid point (the Gulf of Guinea), but in THIS application it is never a
real contribution location. It is what a zeroed EXIF GPS placeholder block
decodes to, and what a numeric-parsing bug commonly coerces null/undefined
into (see mobile/src/location/coordinateValidation.ts's docstring for the
production incident this was written from: two 'memory' submissions stored
as exactly latitude=0, longitude=0, one of which went on to carry that fake
coordinate onto two Observations).

NOT used for: GuideLocation pings (a real device GPS fix -- (0,0) there
would mean the phone's GPS chip itself reported Null Island, an entirely
different failure with an entirely different fix), or any coordinate the
backend derives on its own (a knowledge gap's target, a place's own stored
coordinate) -- those are never client input and don't need re-validating
against client-input rules.
"""

import math


def is_valid_coordinate_pair(latitude: float | None, longitude: float | None) -> bool:
    """True only for a coordinate this application will accept as a
    contribution's real location. False for None, non-finite (NaN/Infinity),
    out-of-range, or the exact placeholder pair (0, 0).

    Deliberately does NOT reject a coordinate merely because ONE component is
    zero -- (0, 78.4) is a legitimate real-world point on the Prime Meridian.
    Only the exact pair (0, 0) is excluded.
    """
    if latitude is None or longitude is None:
        return False
    if not (isinstance(latitude, (int, float)) and isinstance(longitude, (int, float))):
        return False
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return False
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return False
    if latitude == 0 and longitude == 0:
        return False
    return True


class InvalidCoordinateError(ValueError):
    """Raised by schema validators below when a client supplies a coordinate
    pair that fails is_valid_coordinate_pair -- most usefully (0, 0), which
    Pydantic's own ge/le range constraints cannot catch since it is
    mathematically in-range. A clear 422 here is what stops a bad client
    coordinate from ever reaching the database, rather than silently storing
    it and hoping something downstream notices."""

    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude
        super().__init__(
            f"Invalid coordinate ({latitude}, {longitude}) -- (0, 0) is treated as a "
            "missing/placeholder location, not a real one, and is never accepted as a "
            "contribution's location."
        )


def validate_optional_coordinate_pair(latitude: float | None, longitude: float | None) -> None:
    """Raises InvalidCoordinateError only for the specific case a plain
    ge/le range check cannot express: both present, both finite, both in
    range, but exactly (0, 0). Callers that already separately require
    latitude/longitude to be supplied together (a different, pre-existing
    rule) should run that check first -- this one only judges the pair once
    both are known to be present."""
    if latitude is None or longitude is None:
        return
    if not is_valid_coordinate_pair(latitude, longitude):
        raise InvalidCoordinateError(latitude, longitude)
