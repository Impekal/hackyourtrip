"""Straight-line-distance flight duration estimate.

Used only as a fallback where a real data source gives a price but no
schedule (see providers/travelpayouts.py): distance / average block speed +
a fixed overhead for taxi/climb/descent is a common rule-of-thumb for
estimating direct-flight duration without real timetable data.

Deliberately limited to non-stop flights: a connecting itinerary's total
duration is dominated by however long the layover happens to be, which has
no relationship to the great-circle distance between origin and final
destination - estimating it would produce a specific-looking number with no
real basis. Callers should leave connecting flights' duration as unknown
(0.0) rather than call this for them.
"""
from __future__ import annotations

import math

# Average block speed (cruise speed minus the reality of not flying an exact
# great circle, headwinds, etc.) and a fixed taxi/climb/descent overhead -
# both are rough industry rules of thumb, not measured data.
AVERAGE_BLOCK_SPEED_KMH = 750.0
FIXED_OVERHEAD_HOURS = 0.5

# Coordinates for airports likely to show up in routes tracked by this tool
# (dense across Europe, sparser worldwide hubs for international routes).
# Not exhaustive - unknown codes simply get no duration estimate.
AIRPORT_COORDS: dict[str, tuple[float, float]] = {
    # Germany
    "BER": (52.3667, 13.5033), "MUC": (48.3538, 11.7861), "FRA": (50.0379, 8.5622),
    "DUS": (51.2895, 6.7668), "HAM": (53.6304, 9.9882), "STR": (48.6899, 9.2220),
    "CGN": (50.8659, 7.1427), "HAJ": (52.4611, 9.6851), "NUE": (49.4987, 11.0669),
    "LEJ": (51.4239, 12.2364), "DTM": (51.5183, 7.6122), "BRE": (53.0475, 8.7867),
    # Austria / Switzerland
    "VIE": (48.1103, 16.5697), "ZRH": (47.4647, 8.5492), "GVA": (46.2381, 6.1090),
    "SZG": (47.7933, 13.0043), "INN": (47.2602, 11.3440), "BSL": (47.5896, 7.5299),
    # Western/Southern Europe
    "LHR": (51.4700, -0.4543), "LGW": (51.1537, -0.1821), "STN": (51.8860, 0.2389),
    "LTN": (51.8747, -0.3683), "MAN": (53.3537, -2.2750), "EDI": (55.9500, -3.3725),
    "GLA": (55.8642, -4.4331), "DUB": (53.4213, -6.2701),
    "CDG": (49.0097, 2.5479), "ORY": (48.7233, 2.3794), "NCE": (43.6584, 7.2159),
    "LYS": (45.7256, 5.0811), "MRS": (43.4393, 5.2214), "TLS": (43.6291, 1.3638),
    "BOD": (44.8283, -0.7156), "NTE": (47.1532, -1.6110),
    "AMS": (52.3086, 4.7639), "BRU": (50.9014, 4.4844),
    "MAD": (40.4983, -3.5676), "BCN": (41.2971, 2.0785), "PMI": (39.5517, 2.7388),
    "VLC": (39.4893, -0.4816), "SVQ": (37.4180, -5.8931), "BIO": (43.3011, -2.9106),
    "IBZ": (38.8729, 1.3731), "AGP": (36.6749, -4.4991),
    "FCO": (41.8003, 12.2389), "MXP": (45.6306, 8.7281), "LIN": (45.4451, 9.2767),
    "VCE": (45.5053, 12.3519), "NAP": (40.8860, 14.2908),
    "LIS": (38.7813, -9.1359), "OPO": (41.2481, -8.6814),
    "CPH": (55.6180, 12.6560), "ARN": (59.6519, 17.9186), "OSL": (60.1976, 11.1004),
    "HEL": (60.3172, 24.9633), "KEF": (63.9850, -22.6056),
    # Central / Eastern Europe
    "WAW": (52.1657, 20.9671), "PRG": (50.1008, 14.2600), "BUD": (47.4298, 19.2610),
    "OTP": (44.5711, 26.0850), "SOF": (42.6952, 23.4062), "ZAG": (45.7429, 16.0688),
    "LJU": (46.2237, 14.4576), "RIX": (56.9236, 23.9711), "TLL": (59.4133, 24.8328),
    "VNO": (54.6341, 25.2858), "BEG": (44.8184, 20.3091),
    # Southeast Europe / Turkey
    "ATH": (37.9364, 23.9445), "SKG": (40.5197, 22.9709), "IST": (41.2753, 28.7519),
    # UK/Ireland already covered above
    # Middle East / Asia / Oceania hubs
    "DXB": (25.2532, 55.3657), "DOH": (25.2731, 51.6081), "AUH": (24.4330, 54.6511),
    "SIN": (1.3644, 103.9915), "HKG": (22.3080, 113.9185), "NRT": (35.7720, 140.3929),
    "HND": (35.5494, 139.7798), "ICN": (37.4602, 126.4407), "BKK": (13.6900, 100.7501),
    "KUL": (2.7456, 101.7099), "DEL": (28.5562, 77.1000), "BOM": (19.0887, 72.8679),
    "CAI": (30.1219, 31.4056), "JNB": (-26.1392, 28.2460), "CPT": (-33.9715, 18.6021),
    "SYD": (-33.9399, 151.1753), "MEL": (-37.6690, 144.8410), "AKL": (-37.0082, 174.7850),
    # North / South America
    "JFK": (40.6413, -73.7781), "EWR": (40.6895, -74.1745), "LAX": (33.9416, -118.4085),
    "ORD": (41.9742, -87.9073), "MIA": (25.7959, -80.2870), "SFO": (37.6213, -122.3790),
    "YYZ": (43.6777, -79.6248), "YUL": (45.4706, -73.7408),
    "GRU": (-23.4356, -46.4731), "EZE": (-34.8222, -58.5358),
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def estimate_direct_flight_duration_hours(origin: str, destination: str) -> float | None:
    """None if either airport code isn't in the table - callers should treat
    that the same as "no estimate available", not zero."""
    origin_coords = AIRPORT_COORDS.get(origin.upper())
    dest_coords = AIRPORT_COORDS.get(destination.upper())
    if not origin_coords or not dest_coords:
        return None
    distance_km = _haversine_km(*origin_coords, *dest_coords)
    return round(distance_km / AVERAGE_BLOCK_SPEED_KMH + FIXED_OVERHEAD_HOURS, 1)
