"""Radial grid centered on the Sortido darkstore (Arroios, Lisboa)."""
import math

SORTIDO_LAT = 38.7201
SORTIDO_LON = -9.1376

_LAT_KM = 111.0
_LON_KM = 111.0 * math.cos(math.radians(SORTIDO_LAT))

STOP_RINGS = 3  # consecutive empty rings before sweep stops

def radial_rings(step_km=0.5, max_km=20.0):
    """
    Yield (ring_index, [(lat, lon), ...]) from center outward.
    Points per ring spaced ~step_km apart angularly.
    ring 0 = just the center point.
    """
    yield 0, [(round(SORTIDO_LAT, 5), round(SORTIDO_LON, 5))]
    r_km = step_km
    idx = 1
    while r_km <= max_km + 1e-9:
        n = max(8, round(2 * math.pi * r_km / step_km))
        ring = []
        for i in range(n):
            angle = 2 * math.pi * i / n
            lat = SORTIDO_LAT + (r_km / _LAT_KM) * math.sin(angle)
            lon = SORTIDO_LON + (r_km / _LON_KM) * math.cos(angle)
            ring.append((round(lat, 5), round(lon, 5)))
        yield idx, ring
        r_km = round(r_km + step_km, 9)
        idx += 1
