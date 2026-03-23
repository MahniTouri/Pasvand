import json
import re
import threading
import webbrowser

import requests
from flask import Flask, request, render_template_string

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>OSM Pas o Pishvand Iran</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">

  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    crossorigin=""
  />

  <style>
    html, body {
      height: 100%;
      margin: 0;
      font-family: Arial, sans-serif;
    }

    .container {
      display: flex;
      flex-direction: column;
      height: 100%;
    }

    .topbar {
      padding: 12px;
      border-bottom: 1px solid #ccc;
      background: #f8f8f8;
    }

    .form-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }

    input[type="text"], select {
      padding: 8px;
      font-size: 16px;
      min-width: 180px;
    }

    .checkbox-wrap {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 14px;
      white-space: nowrap;
    }

    button {
      padding: 8px 14px;
      font-size: 16px;
      cursor: pointer;
    }

    .info {
      margin-top: 8px;
      font-size: 14px;
      color: #333;
    }

    #map {
      flex: 1;
      min-height: 500px;
    }

    .error {
      color: #b00020;
      font-weight: bold;
    }

    .legend {
      margin-top: 8px;
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      font-size: 14px;
    }

    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .legend-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      display: inline-block;
    }

    .legend-match {
      background: #d81b60;
    }

    .legend-nonmatch {
      background: #666666;
    }

    /* Fullscreen mode: show only the map */
    body.fullscreen-mode .topbar {
      display: none;
    }

    body.fullscreen-mode .container {
      height: 100vh;
    }

    body.fullscreen-mode #map {
      min-height: 100vh;
      height: 100vh;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="topbar">
      <form method="get" action="/">
        <div class="form-row">
          <label for="mode"><strong>Search for:</strong></label>
          <select id="mode" name="mode">
            <option value="suffix" {% if mode == "suffix" %}selected{% endif %}>Suffix</option>
            <option value="prefix" {% if mode == "prefix" %}selected{% endif %}>Prefix</option>
            <option value="contains" {% if mode == "contains" %}selected{% endif %}>Contains</option>
          </select>

          <label for="text"><strong>Text:</strong></label>
          <input
            id="text"
            name="text"
            type="text"
            value="{{ text }}"
            placeholder="e. g. ا or آباد"
            required
          >

          <label class="checkbox-wrap" for="show_non_matches">
            <input
              id="show_non_matches"
              name="show_non_matches"
              type="checkbox"
              value="1"
              {% if show_non_matches %}checked{% endif %}
            >
            Show non-matching places too
          </label>

          <button type="submit">Search</button>
        </div>
      </form>

      <div class="info">
        Search in Iran for cities, towns, villages, hamlets, suburbs,
        quarters and neighbourhoods whose names start with, end with,
        or contain the entered text.
      </div>

      {% if error %}
        <div class="info error">{{ error }}</div>
      {% elif searched %}
        <div class="info">
          Matching places: {{ match_count }}
          {% if show_non_matches %}
            | Non-matching places shown too: {{ non_match_count }}
            | Total displayed: {{ total_count }}
          {% endif %}
        </div>

        <div class="legend">
          <span class="legend-item">
            <span class="legend-dot legend-match"></span>
            Matching
          </span>
          {% if show_non_matches %}
          <span class="legend-item">
            <span class="legend-dot legend-nonmatch"></span>
            Non-matching
          </span>
          {% endif %}
        </div>
      {% endif %}
    </div>

    <div id="map"></div>
  </div>

  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    crossorigin=""
  ></script>

  <script>
    const map = L.map('map');
    const markers = {{ markers_json|safe }};

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap-Mitwirkende'
    }).addTo(map);

    if (markers.length > 0) {
      const bounds = [];

      for (const m of markers) {
        const marker = L.circleMarker([m.lat, m.lon], {
          radius: m.matched ? 5 : 4,
          color: m.matched ? '#d81b60' : '#666666',
          fillColor: m.matched ? '#d81b60' : '#666666',
          fillOpacity: m.matched ? 0.9 : 0.45,
          weight: 1
        }).addTo(map);

        const popup = `
          <b>${m.name}</b><br>
          place: ${m.place}<br>
          match: ${m.matched ? 'yes' : 'no'}<br>
          lat: ${m.lat}<br>
          lon: ${m.lon}
        `;
        marker.bindPopup(popup);
        marker.bindTooltip(m.name);
        bounds.push([m.lat, m.lon]);
      }

      map.fitBounds(bounds, { padding: [20, 20] });
    } else {
      map.setView([32.0, 53.0], 5);
    }

    function isFullscreenActive() {
      return !!document.fullscreenElement ||
             (window.innerHeight === screen.height && window.innerWidth === screen.width);
    }

    function updateFullscreenLayout() {
      if (isFullscreenActive()) {
        document.body.classList.add('fullscreen-mode');
      } else {
        document.body.classList.remove('fullscreen-mode');
      }

      setTimeout(() => {
        map.invalidateSize();
      }, 100);
    }

    document.addEventListener('fullscreenchange', updateFullscreenLayout);
    window.addEventListener('resize', updateFullscreenLayout);

    updateFullscreenLayout();
  </script>
</body>
</html>
"""


def escape_overpass_regex(text: str) -> str:
    special_chars = r'\\.^$|?*+()[]{}'
    escaped = []
    for ch in text:
        if ch in special_chars:
            escaped.append("\\" + ch)
        else:
            escaped.append(ch)
    return "".join(escaped)


def build_name_regex(text: str, mode: str) -> str:
    escaped_text = escape_overpass_regex(text)

    if mode == "prefix":
        return f"^{escaped_text}"
    if mode == "suffix":
        return f"{escaped_text}$"
    if mode == "contains":
        return escaped_text

    raise ValueError("Invalid search mode. Allowed: 'prefix', 'suffix', 'contains'.")


def build_query(text: str, mode: str, show_non_matches: bool) -> str:
    place_filter = '["place"~"^(city|town|village|hamlet|suburb|quarter|neighbourhood)$"]'

    if show_non_matches:
        return f"""
[out:json][timeout:180];

area["ISO3166-1"="IR"]["boundary"="administrative"]["admin_level"="2"]->.ir;

node(area.ir)
  {place_filter};

out body;
"""

    regex = build_name_regex(text, mode)

    return f"""
[out:json][timeout:180];

area["ISO3166-1"="IR"]["boundary"="administrative"]["admin_level"="2"]->.ir;

(
  node(area.ir)
    {place_filter}
    ["name"~"{regex}"];

  node(area.ir)
    {place_filter}
    ["name:fa"~"{regex}"];

  node(area.ir)
    {place_filter}
    ["name:ar"~"{regex}"];
);
out body;
"""


def tags_match(tags: dict, pattern: re.Pattern) -> bool:
    for key in ("name", "name:fa", "name:ar"):
        value = tags.get(key)
        if value and pattern.search(value):
            return True
    return False


def run_overpass(text: str, mode: str, show_non_matches: bool) -> list[dict]:
    query = build_query(text, mode, show_non_matches)

    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        timeout=300,
        headers={"User-Agent": "osm-prefix-suffix-contains-map/1.3"}
    )
    response.raise_for_status()

    data = response.json()
    elements = data.get("elements", [])

    pattern = re.compile(build_name_regex(text, mode))

    results = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:fa") or tags.get("name:ar") or "Unnamed"

        matched = True if not show_non_matches else tags_match(tags, pattern)

        results.append({
            "id": el.get("id"),
            "name": name,
            "place": tags.get("place", ""),
            "lat": el.get("lat"),
            "lon": el.get("lon"),
            "matched": matched,
        })

    seen = set()
    unique_results = []
    for item in results:
        key = (item["lat"], item["lon"], item["name"], item["place"])
        if key not in seen:
            seen.add(key)
            unique_results.append(item)

    return unique_results


@app.route("/", methods=["GET"])
def index():
    text = request.args.get("text", "").strip()
    mode = request.args.get("mode", "suffix").strip().lower()
    show_non_matches = request.args.get("show_non_matches") == "1"

    if mode not in {"suffix", "prefix", "contains"}:
        mode = "suffix"

    markers = []
    error = None
    searched = False
    match_count = 0
    non_match_count = 0

    if text:
        searched = True
        try:
            markers = run_overpass(text, mode, show_non_matches)
            match_count = sum(1 for m in markers if m["matched"])
            non_match_count = sum(1 for m in markers if not m["matched"])
        except requests.HTTPError as e:
            error = f"HTTP error from Overpass: {e}"
        except requests.RequestException as e:
            error = f"Network error: {e}"
        except Exception as e:
            error = f"Unexpected error: {e}"

    return render_template_string(
        HTML_TEMPLATE,
        text=text,
        mode=mode,
        show_non_matches=show_non_matches,
        markers_json=json.dumps(markers, ensure_ascii=False),
        match_count=match_count,
        non_match_count=non_match_count,
        total_count=len(markers),
        error=error,
        searched=searched,
    )


def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")


if __name__ == "__main__":
    threading.Timer(1.0, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)