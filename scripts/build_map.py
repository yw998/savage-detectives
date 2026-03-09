#!/usr/bin/env python3
"""
Build map/index.html — a self-contained interactive map of
荒野侦探 (The Savage Detectives) using Leaflet.js.

Run AFTER geocode_locations.py so that locations have lat/lng filled in.
"""
import sqlite3, json, os, math, sys, hashlib

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_PATH  = r"C:\Users\admin\savage-detectives\data\savage_detectives.db"
OUT_PATH = r"C:\Users\admin\savage-detectives\map\index.html"

TOP_N = 12  # characters to feature with journey paths + sidebar

COLORS = [
    "#e74c3c",  # red
    "#3498db",  # blue
    "#2ecc71",  # green
    "#f39c12",  # amber
    "#9b59b6",  # purple
    "#1abc9c",  # teal
    "#e67e22",  # orange
    "#e91e63",  # pink
    "#00bcd4",  # cyan
    "#cddc39",  # lime
    "#ff5722",  # deep orange
    "#607d8b",  # blue-grey
]


def parse_date(date_str):
    """Return decimal year (float) or None."""
    if not date_str:
        return None
    try:
        parts = date_str.split('-')
        year  = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 6
        day   = int(parts[2]) if len(parts) > 2 else 15
        return year + ((month - 1) * 30.44 + day) / 365.25
    except Exception:
        return None


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Top characters (by event appearances) ──────────────────────────────
    top_chars = cur.execute("""
        SELECT c.id, c.name, c.role, c.nationality, COUNT(ec.event_id) AS cnt
        FROM characters c
        JOIN event_characters ec ON ec.character_id = c.id
        GROUP BY c.id
        ORDER BY cnt DESC
        LIMIT ?
    """, (TOP_N,)).fetchall()

    char_map = {
        c['id']: {
            'id':          c['id'],
            'name':        c['name'],
            'role':        c['role'] or '',
            'nationality': c['nationality'] or '',
            'color':       COLORS[i % len(COLORS)],
            'event_count': c['cnt'],
        }
        for i, c in enumerate(top_chars)
    }

    # ── One representative quote per character ─────────────────────────────
    char_quotes = {}
    for char_id in char_map:
        row = cur.execute(
            "SELECT text FROM quotes WHERE character_id=? ORDER BY id LIMIT 1",
            (char_id,)
        ).fetchone()
        if row:
            char_quotes[char_id] = row['text']

    # ── Events that have geocoded locations ────────────────────────────────
    events_raw = cur.execute("""
        SELECT e.id, e.date, e.date_approx, e.description, e.chapter,
               e.page_number, e.narrator_id,
               l.name  AS loc_name,  l.lat,  l.lng,
               cn.name AS narrator_name
        FROM events e
        JOIN  locations  l  ON e.location_id = l.id
        LEFT JOIN characters cn ON e.narrator_id = cn.id
        WHERE l.lat IS NOT NULL AND l.lng IS NOT NULL
        ORDER BY e.date ASC NULLS LAST, e.id ASC
    """).fetchall()

    # Characters per event
    ec_rows = cur.execute("""
        SELECT ec.event_id, c.id AS char_id, c.name
        FROM event_characters ec
        JOIN characters c ON ec.character_id = c.id
    """).fetchall()
    event_chars = {}
    for r in ec_rows:
        event_chars.setdefault(r['event_id'], []).append(r['name'])

    def jitter(event_id, lat, lng, radius=0.04):
        """Deterministic small offset so events at the same city don't stack."""
        h = int(hashlib.md5(str(event_id).encode()).hexdigest(), 16)
        angle = (h % 3600) / 3600 * 2 * math.pi
        dist  = ((h >> 12) % 100) / 100 * radius
        return lat + dist * math.cos(angle), lng + dist * math.sin(angle)

    events = []
    for e in events_raw:
        nid   = e['narrator_id']
        color = char_map[nid]['color'] if nid in char_map else '#95a5a6'
        jlat, jlng = jitter(e['id'], e['lat'], e['lng'])
        events.append({
            'id':          e['id'],
            'date':        e['date'] or '',
            'date_float':  parse_date(e['date']),
            'description': e['description'],
            'chapter':     e['chapter'] or '',
            'lat':         round(jlat, 6),
            'lng':         round(jlng, 6),
            'location':    e['loc_name'] or '',
            'narrator':    e['narrator_name'] or '',
            'narrator_id': nid,
            'color':       color,
            'characters':  event_chars.get(e['id'], []),
            'quote':       char_quotes.get(nid, ''),
        })

    # ── Journey paths: per top character, events with date + location ──────
    journeys = {}
    for char_id in char_map:
        pts = cur.execute("""
            SELECT e.id, e.date, l.lat, l.lng
            FROM event_characters ec
            JOIN events    e ON ec.event_id    = e.id
            JOIN locations l ON e.location_id  = l.id
            WHERE ec.character_id = ?
              AND l.lat IS NOT NULL
              AND e.date IS NOT NULL
            ORDER BY e.date ASC, e.id ASC
        """, (char_id,)).fetchall()
        if len(pts) >= 2:
            journeys[char_id] = [
                {'lat': p['lat'], 'lng': p['lng'],
                 'date_float': parse_date(p['date']), 'event_id': p['id']}
                for p in pts
            ]

    # Clamp slider to the novel's main timeline; events outside this range
    # are surfaced via the "show undated" toggle.
    SLIDER_MIN, SLIDER_MAX = 1970, 1998
    min_date = SLIDER_MIN
    max_date = SLIDER_MAX

    # Mark events outside slider range as undated for display purposes
    for e in events:
        df = e['date_float']
        if df is not None and (df < SLIDER_MIN or df > SLIDER_MAX):
            e['date_float'] = None

    js_data = {
        'events':     events,
        'characters': list(char_map.values()),
        'journeys':   {str(k): v for k, v in journeys.items()},
        'min_date':   min_date,
        'max_date':   max_date,
    }

    conn.close()

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    html = build_html(js_data)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Generated: {OUT_PATH}")
    print(f"  Mapped events   : {len(events)}")
    print(f"  Journey paths   : {len(journeys)}")
    print(f"  Date range      : {min_date}–{max_date}")


# ── HTML template ──────────────────────────────────────────────────────────

def build_html(data):
    data_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>荒野侦探 — The Savage Detectives</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ height:100%; overflow:hidden; }}
body {{
  font-family: 'Georgia', serif;
  background: #0d0d1a;
  color: #ddd;
  display: flex;
  flex-direction: column;
  height: 100vh;
}}

/* ── Layout ── */
#app {{ display:flex; flex:1; overflow:hidden; min-height:0; }}
#map {{ flex:1; }}

/* ── Sidebar ── */
#sidebar {{
  width: 230px;
  min-width: 230px;
  background: rgba(8, 8, 22, 0.97);
  border-right: 1px solid rgba(255,255,255,0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 1000;
}}
#sidebar-header {{
  padding: 14px 14px 10px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}}
#sidebar-header h1 {{
  font-size: 15px;
  font-weight: normal;
  letter-spacing: 1px;
  color: #eee;
  margin-bottom: 2px;
}}
#sidebar-header p {{
  font-size: 10px;
  color: #555;
  letter-spacing: 2px;
  text-transform: uppercase;
}}
#char-list {{ padding: 8px 10px; overflow-y: auto; flex:1; }}
#char-list h2 {{
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: #555;
  margin: 6px 4px 8px;
}}
.char-item {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
  user-select: none;
}}
.char-item:hover {{ background: rgba(255,255,255,0.05); }}
.char-dot {{
  width: 9px; height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: opacity 0.2s;
}}
.char-label {{ font-size: 12px; flex:1; line-height: 1.3; transition: color 0.2s; }}
.char-count {{ font-size: 10px; color: #555; }}
.char-item.off .char-dot   {{ opacity: 0.2; }}
.char-item.off .char-label {{ color: #555; }}
#sidebar-footer {{
  padding: 10px 14px;
  border-top: 1px solid rgba(255,255,255,0.08);
  font-size: 10px;
  color: #555;
  line-height: 1.7;
}}

/* ── Timeline ── */
#timeline {{
  background: rgba(6, 6, 18, 0.98);
  border-top: 1px solid rgba(255,255,255,0.08);
  padding: 10px 18px 14px;
  z-index: 1000;
}}
#tl-top {{
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}}
#play-btn {{
  background: none;
  border: 1px solid rgba(255,255,255,0.25);
  color: #ccc;
  width: 26px; height: 26px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}}
#play-btn:hover {{ background: rgba(255,255,255,0.1); border-color: rgba(255,255,255,0.5); }}
#date-label {{
  font-size: 14px;
  color: #ddd;
  letter-spacing: 1px;
  min-width: 110px;
}}
#event-label {{
  font-size: 10px;
  color: #555;
  margin-left: auto;
}}
#undated-toggle {{
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: #666;
  cursor: pointer;
  margin-left: 12px;
}}
#undated-toggle input {{ cursor: pointer; accent-color: #888; }}
#tl-track {{ position: relative; }}
#timeline-slider {{
  width: 100%;
  height: 4px;
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  outline: none;
  cursor: pointer;
  position: relative;
  z-index: 2;
}}
#track-bg {{
  position: absolute;
  top: 50%; left: 0; right: 0;
  height: 4px;
  transform: translateY(-50%);
  background: rgba(255,255,255,0.1);
  border-radius: 2px;
  pointer-events: none;
}}
#track-fill {{
  position: absolute;
  top: 50%; left: 0;
  height: 4px;
  transform: translateY(-50%);
  background: #e74c3c;
  border-radius: 2px;
  pointer-events: none;
  transition: width 0.05s;
}}
#timeline-slider::-webkit-slider-thumb {{
  -webkit-appearance: none;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #e74c3c;
  cursor: pointer;
  box-shadow: 0 0 8px rgba(231,76,60,0.6);
  border: 2px solid #fff;
}}
#timeline-slider::-moz-range-thumb {{
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #e74c3c;
  cursor: pointer;
  border: 2px solid #fff;
}}
#year-ticks {{
  display: flex;
  justify-content: space-between;
  margin-top: 5px;
  font-size: 9px;
  color: #444;
  letter-spacing: 1px;
}}

/* ── Popup ── */
.leaflet-popup-content-wrapper {{
  background: rgba(10, 10, 28, 0.97) !important;
  color: #ddd !important;
  border: 1px solid rgba(255,255,255,0.12) !important;
  border-radius: 6px !important;
  box-shadow: 0 6px 24px rgba(0,0,0,0.7) !important;
}}
.leaflet-popup-content {{ margin: 12px 14px !important; }}
.leaflet-popup-tip {{ background: rgba(10,10,28,0.97) !important; }}
.leaflet-popup-close-button {{ color: #888 !important; top: 6px !important; right: 8px !important; }}
.pop-date    {{ font-size: 10px; color: #888; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 1px; }}
.pop-chapter {{ font-size: 10px; color: #555; margin-bottom: 6px; }}
.pop-loc     {{ font-size: 11px; color: #aaa; margin-bottom: 7px; }}
.pop-desc    {{ font-size: 12px; line-height: 1.55; margin-bottom: 8px; color: #ddd; }}
.pop-chars   {{ font-size: 11px; color: #888; margin-bottom: 7px; }}
.pop-narrator {{ font-size: 10px; color: #666; margin-bottom: 6px; }}
.pop-quote   {{
  font-size: 11px; font-style: italic; color: #bbb;
  border-left: 2px solid #e74c3c;
  padding-left: 9px;
  line-height: 1.55;
  margin-top: 6px;
}}
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <div id="sidebar-header">
      <h1>荒野侦探</h1>
      <p>The Savage Detectives</p>
    </div>
    <div id="char-list">
      <h2>Characters</h2>
    </div>
    <div id="sidebar-footer" id="sidebar-footer"></div>
  </div>
  <div id="map"></div>
</div>

<div id="timeline">
  <div id="tl-top">
    <button id="play-btn" title="Play / Pause">▶</button>
    <div id="date-label">—</div>
    <label id="undated-toggle">
      <input type="checkbox" id="show-undated"> show undated
    </label>
    <div id="event-label"></div>
  </div>
  <div id="tl-track">
    <div id="track-bg"></div>
    <div id="track-fill"></div>
    <input type="range" id="timeline-slider" step="0.02">
  </div>
  <div id="year-ticks"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
'use strict';
const DATA = {data_json};

// ── Map ────────────────────────────────────────────────────────────────────
const map = L.map('map', {{
  center: [19.43, -99.13],
  zoom: 4,
  preferCanvas: true,
}});
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '© OpenStreetMap contributors © CARTO',
  subdomains: 'abcd',
  maxZoom: 19,
}}).addTo(map);

const markerLayer = L.layerGroup().addTo(map);
const pathLayer   = L.layerGroup().addTo(map);

// ── Character index ────────────────────────────────────────────────────────
const charById = {{}};
DATA.characters.forEach(c => {{ charById[c.id] = c; }});

const hiddenChars = new Set();
let showUndated = false;

// ── Sidebar ────────────────────────────────────────────────────────────────
const charList = document.getElementById('char-list');
DATA.characters.forEach(c => {{
  const el = document.createElement('div');
  el.className = 'char-item';
  el.dataset.id = c.id;
  el.innerHTML = `
    <div class="char-dot" style="background:${{c.color}}"></div>
    <div class="char-label">${{c.name}}</div>
    <div class="char-count">${{c.event_count}}</div>`;
  el.addEventListener('click', () => {{
    if (hiddenChars.has(c.id)) {{ hiddenChars.delete(c.id); el.classList.remove('off'); }}
    else                        {{ hiddenChars.add(c.id);    el.classList.add('off');    }}
    render(currentVal());
  }});
  charList.appendChild(el);
}});

document.getElementById('sidebar-footer').innerHTML =
  `${{DATA.events.length}} mapped events<br>${{DATA.characters.length}} featured characters`;

// ── Timeline slider ────────────────────────────────────────────────────────
const slider    = document.getElementById('timeline-slider');
const trackFill = document.getElementById('track-fill');
slider.min   = DATA.min_date;
slider.max   = DATA.max_date;
slider.value = DATA.min_date;

function currentVal() {{ return parseFloat(slider.value); }}

function updateTrackFill() {{
  const pct = (currentVal() - DATA.min_date) / (DATA.max_date - DATA.min_date) * 100;
  trackFill.style.width = pct + '%';
}}

// Year tick labels (every 5 years)
const ticksEl = document.getElementById('year-ticks');
for (let y = DATA.min_date; y <= DATA.max_date; y++) {{
  if (y % 5 === 0 || y === DATA.min_date || y === DATA.max_date) {{
    const span = document.createElement('span');
    span.textContent = y;
    const pct = (y - DATA.min_date) / (DATA.max_date - DATA.min_date) * 100;
    span.style.cssText = `position:absolute;left:${{pct}}%;transform:translateX(-50%)`;
    ticksEl.appendChild(span);
  }}
}}
ticksEl.style.cssText = 'position:relative;height:14px;';

function fmtDate(val) {{
  const year  = Math.floor(val);
  const frac  = val - year;
  const month = Math.min(11, Math.floor(frac * 12));
  return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][month] + ' ' + year;
}}

// ── Render ─────────────────────────────────────────────────────────────────
function makePopup(e) {{
  const chars = e.characters.filter(Boolean).slice(0, 6).join(', ');
  return `
    <div class="pop-date">${{e.date || 'date unknown'}}</div>
    <div class="pop-chapter">${{e.chapter}}</div>
    <div class="pop-loc">📍 ${{e.location}}</div>
    <div class="pop-desc">${{e.description}}</div>
    ${{e.narrator ? `<div class="pop-narrator">Narrator: ${{e.narrator}}</div>` : ''}}
    ${{chars       ? `<div class="pop-chars">Characters: ${{chars}}</div>` : ''}}
    ${{e.quote     ? `<div class="pop-quote">${{e.quote.slice(0,220)}}${{e.quote.length>220?'…':''}}</div>` : ''}}
  `;
}}

function render(val) {{
  markerLayer.clearLayers();
  pathLayer.clearLayers();

  // Filter events
  const visible = DATA.events.filter(e => {{
    if (e.date_float !== null) return e.date_float <= val;
    return showUndated;
  }});

  // "Active" window: events within the last 1.5 years of slider
  const activeThreshold = val - 1.5;

  visible.forEach(e => {{
    const isHidden  = e.narrator_id && hiddenChars.has(e.narrator_id);
    if (isHidden) return;

    const isActive  = e.date_float !== null && e.date_float >= activeThreshold;
    const size      = isActive ? 11 : 7;
    const opacity   = isActive ? 0.95 : 0.45;
    const glowColor = e.color;

    const icon = L.divIcon({{
      className: '',
      html: `<div style="
        width:${{size}}px;height:${{size}}px;border-radius:50%;
        background:${{e.color}};
        border:1px solid rgba(255,255,255,${{isActive ? 0.7 : 0.2}});
        opacity:${{opacity}};
        ${{isActive ? `box-shadow:0 0 7px ${{glowColor}};` : ''}}
      "></div>`,
      iconSize:    [size, size],
      iconAnchor:  [size/2, size/2],
      popupAnchor: [0, -size/2 - 2],
    }});

    L.marker([e.lat, e.lng], {{icon}})
      .bindPopup(makePopup(e), {{maxWidth: 300}})
      .addTo(markerLayer);
  }});

  // Journey paths
  Object.entries(DATA.journeys).forEach(([charIdStr, pts]) => {{
    const charId = parseInt(charIdStr);
    if (hiddenChars.has(charId)) return;
    const color = charById[charId]?.color || '#888';

    const visiblePts = pts.filter(p => p.date_float <= val);
    if (visiblePts.length < 2) return;

    L.polyline(visiblePts.map(p => [p.lat, p.lng]), {{
      color,
      weight: 1.8,
      opacity: 0.45,
      smoothFactor: 2,
    }}).addTo(pathLayer);
  }});

  // HUD
  document.getElementById('date-label').textContent = fmtDate(val);
  document.getElementById('event-label').textContent =
    `${{visible.length}} event${{visible.length !== 1 ? 's' : ''}}`;
  updateTrackFill();
}}

slider.addEventListener('input', () => render(currentVal()));

document.getElementById('show-undated').addEventListener('change', e => {{
  showUndated = e.target.checked;
  render(currentVal());
}});

// ── Play / Pause ───────────────────────────────────────────────────────────
let playing = false, playTimer = null;
const playBtn = document.getElementById('play-btn');

playBtn.addEventListener('click', () => {{
  if (playing) {{
    clearInterval(playTimer);
    playing = false;
    playBtn.textContent = '▶';
  }} else {{
    playing = true;
    playBtn.textContent = '⏸';
    if (currentVal() >= DATA.max_date) slider.value = DATA.min_date;
    playTimer = setInterval(() => {{
      const next = currentVal() + 0.06;
      if (next > DATA.max_date) {{
        slider.value = DATA.max_date;
        render(DATA.max_date);
        clearInterval(playTimer);
        playing = false;
        playBtn.textContent = '▶';
      }} else {{
        slider.value = next;
        render(next);
      }}
    }}, 80);
  }}
}});

// ── Initial render ─────────────────────────────────────────────────────────
render(currentVal());
</script>
</body>
</html>"""


if __name__ == '__main__':
    main()
