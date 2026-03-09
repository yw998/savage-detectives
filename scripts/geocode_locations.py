#!/usr/bin/env python3
"""
Geocode locations in savage_detectives.db using Nominatim (OpenStreetMap).
Strategy per location:
  1. Hardcoded known coords (fast, reliable for common Chinese city names)
  2. Nominatim: "name, city, country"
  3. Nominatim: "city, country"
  4. Nominatim: "country"
  5. Give up (lat/lng stays NULL)
"""
import sqlite3, json, time, urllib.request, urllib.parse, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_PATH = r"C:\Users\admin\savage-detectives\data\savage_detectives.db"

# Hardcoded fallbacks for city/country names common in the novel
KNOWN_COORDS = {
    # Mexico
    "墨西哥城":      (19.4326, -99.1332),
    "Mexico City":   (19.4326, -99.1332),
    "墨西哥":        (23.6345, -102.5528),
    "Mexico":        (23.6345, -102.5528),
    "索诺拉":        (29.2972, -110.3309),
    "Sonora":        (29.2972, -110.3309),
    "蒂华纳":        (32.5149, -117.0382),
    "Tijuana":       (32.5149, -117.0382),
    "瓜达拉哈拉":    (20.6597, -103.3496),
    "Guadalajara":   (20.6597, -103.3496),
    # Spain
    "巴塞罗那":      (41.3851, 2.1734),
    "Barcelona":     (41.3851, 2.1734),
    "马德里":        (40.4168, -3.7038),
    "Madrid":        (40.4168, -3.7038),
    "西班牙":        (40.4637, -3.7492),
    "Spain":         (40.4637, -3.7492),
    # France
    "巴黎":          (48.8566, 2.3522),
    "Paris":         (48.8566, 2.3522),
    "法国":          (46.2276, 2.2137),
    "France":        (46.2276, 2.2137),
    # Chile
    "圣地亚哥":      (-33.4489, -70.6693),
    "Santiago":      (-33.4489, -70.6693),
    "智利":          (-35.6751, -71.5430),
    "Chile":         (-35.6751, -71.5430),
    # Israel / Middle East
    "以色列":        (31.0461, 34.8516),
    "Israel":        (31.0461, 34.8516),
    "特拉维夫":      (32.0853, 34.7818),
    "Tel Aviv":      (32.0853, 34.7818),
    # Austria
    "奥地利":        (47.5162, 14.5501),
    "Austria":       (47.5162, 14.5501),
    "维也纳":        (48.2082, 16.3738),
    "Vienna":        (48.2082, 16.3738),
    # USA
    "美国":          (37.0902, -95.7129),
    "USA":           (37.0902, -95.7129),
    "洛杉矶":        (34.0522, -118.2437),
    "Los Angeles":   (34.0522, -118.2437),
    # Africa
    "非洲":          (8.7832, 34.5085),
    "Africa":        (8.7832, 34.5085),
    # Nicaragua
    "尼加拉瓜":      (12.8654, -85.2072),
    "Nicaragua":     (12.8654, -85.2072),
    # Italy
    "罗马":          (41.9028, 12.4964),
    "Rome":          (41.9028, 12.4964),
    "意大利":        (41.8719, 12.5674),
    "Italy":         (41.8719, 12.5674),
    # Germany
    "德国":          (51.1657, 10.4515),
    "Germany":       (51.1657, 10.4515),
    "柏林":          (52.5200, 13.4050),
    "Berlin":        (52.5200, 13.4050),
    # UK
    "英国":          (55.3781, -3.4360),
    "UK":            (55.3781, -3.4360),
    "伦敦":          (51.5074, -0.1278),
    "London":        (51.5074, -0.1278),
    # Argentina
    "阿根廷":        (-38.4161, -63.6167),
    "Argentina":     (-38.4161, -63.6167),
    "布宜诺斯艾利斯": (-34.6037, -58.3816),
    "Buenos Aires":  (-34.6037, -58.3816),
    # Venezuela
    "委内瑞拉":      (6.4238, -66.5897),
    "Venezuela":     (6.4238, -66.5897),
}


def nominatim_geocode(query):
    try:
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "q": query, "format": "json", "limit": 1
        })
        req = urllib.request.Request(url, headers={"User-Agent": "savage-detectives-map/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"  Nominatim error for '{query}': {e}")
    return None, None


def geocode(name, city, country):
    # 1. Check hardcoded known coords
    for key in [name, city, country]:
        if key and key.strip() in KNOWN_COORDS:
            return KNOWN_COORDS[key.strip()]

    # 2. Nominatim: name + city
    if name and city:
        lat, lng = nominatim_geocode(f"{name}, {city}")
        time.sleep(1.1)
        if lat is not None:
            return lat, lng

    # 3. Nominatim: city + country
    if city:
        lat, lng = nominatim_geocode(f"{city}, {country or ''}")
        time.sleep(1.1)
        if lat is not None:
            return lat, lng

    # 4. Nominatim: country only
    if country:
        lat, lng = nominatim_geocode(country)
        time.sleep(1.1)
        if lat is not None:
            return lat, lng

    return None, None


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT id, name, city, country FROM locations
        WHERE lat IS NULL
        ORDER BY id
    """).fetchall()

    print(f"Locations to geocode: {len(rows)}")

    ok = fail = 0
    for row in rows:
        name    = (row['name']    or '').strip()
        city    = (row['city']    or '').strip()
        country = (row['country'] or '').strip()

        lat, lng = geocode(name, city, country)

        if lat is not None:
            cur.execute("UPDATE locations SET lat=?, lng=? WHERE id=?", (lat, lng, row['id']))
            conn.commit()
            print(f"  ✓ {name!r} → ({lat:.4f}, {lng:.4f})")
            ok += 1
        else:
            print(f"  ✗ {name!r}  (city={city!r}, country={country!r})")
            fail += 1

    print(f"\nDone: {ok} geocoded, {fail} still missing")

    total = cur.execute("SELECT COUNT(*) FROM locations WHERE lat IS NOT NULL").fetchone()[0]
    grand = cur.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    print(f"Coverage: {total}/{grand} locations have coordinates")
    conn.close()


if __name__ == "__main__":
    main()
