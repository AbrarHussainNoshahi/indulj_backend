import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

KNOWN_CITIES = {
    "pakpattan": (30.3410, 73.3850),
    "kot bahawal": (30.1850, 73.2600),
    "kot balochan": (31.0372, 73.9505),
    "houston": (29.7604, -95.3698),
    "austin": (30.2672, -97.7431),
    "dallas": (32.7767, -96.7970),
    "atlanta": (33.7490, -84.3880),
    "los angeles": (34.0522, -118.2437),
    "san diego": (32.7157, -117.1611),
    "seattle": (47.6062, -122.3321),
    "nashville": (36.1627, -86.7816),
    "miami": (25.7617, -80.1918),
    "miami-dade": (25.5628, -80.2468),
    "brickell": (25.7635, -80.1974),
    "new york": (40.7128, -74.0060),
    "chicago": (41.8781, -87.6298),
    "lahore": (31.5204, 74.3587),
    "karachi": (24.8607, 67.0011),
    "islamabad": (33.6844, 73.0479),
}


def geocode_online(query):
    if not query or len(str(query).strip()) < 3:
        return None, None
    clean_query = str(query).strip()
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(clean_query)}&format=json&limit=1"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "InduljPlatform/1.0 (admin@indulj.com)"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and len(data) > 0:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        logger.debug(f"Geocoding error for {clean_query}: {e}")
    return None, None


def resolve_coordinates(address="", city="", seed_id=None):
    """
    Resolves latitude and longitude for an address or city.
    Uses known city cache first, then online geocoding, then sensible defaults.
    """
    text_to_check = f"{address or ''} {city or ''}".lower().strip()

    # 1. Check known cities and test queries
    base_coords = None
    if any(w in text_to_check for w in ["testing", "test loc", "test address", "sample"]):
        base_coords = (30.1799, 73.2530)
    else:
        for key, coords in KNOWN_CITIES.items():
            if key in text_to_check:
                base_coords = coords
                break

    # 2. If not found in known cities, try online geocoding
    if not base_coords:
        if city and len(str(city).strip()) >= 3:
            base_coords = geocode_online(f"{city}")
            if not base_coords or not base_coords[0]:
                base_coords = None

    if not base_coords and address and len(str(address).strip()) >= 3:
        base_coords = geocode_online(address)
        if not base_coords or not base_coords[0]:
            base_coords = None

    # 3. Fallback: Pakpattan / Houston default depending on context
    if not base_coords:
        if any(w in text_to_check for w in ["pakistan", "kot", "testing", "punjab"]):
            base_coords = (30.1799, 73.2530)
        else:
            base_coords = (29.7604, -95.3698)

    lat, lng = base_coords
    # Apply small deterministic jitter so restaurants in the same city don't land on exact same pixel
    if seed_id is not None:
        try:
            sid = int(seed_id)
            offset_lat = ((sid % 7) - 3) * 0.0018
            offset_lng = (((sid * 3) % 7) - 3) * 0.0018
            lat = round(lat + offset_lat, 6)
            lng = round(lng + offset_lng, 6)
        except (ValueError, TypeError):
            pass

    return lat, lng


def ensure_restaurant_coordinates(restaurant):
    """
    Ensures the given restaurant instance has valid latitude and longitude.
    Saves to DB if coordinates were missing.
    """
    if restaurant.latitude is not None and restaurant.longitude is not None:
        return restaurant

    lat, lng = resolve_coordinates(
        restaurant.address,
        restaurant.city,
        restaurant.id,
    )
    if lat is not None and lng is not None:
        restaurant.latitude = lat
        restaurant.longitude = lng
        restaurant.save(update_fields=["latitude", "longitude"])

    return restaurant
