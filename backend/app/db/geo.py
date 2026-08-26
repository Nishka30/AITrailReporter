from geoalchemy2.elements import WKTElement


def make_point(latitude: float, longitude: float) -> WKTElement:
    """Build a PostGIS point from latitude/longitude.

    PostGIS/WKT point order is (X Y) = (longitude latitude) — the reverse of how
    lat/lon is normally spoken. This is the single place that ordering happens.
    """
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)
