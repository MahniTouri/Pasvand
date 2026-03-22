import json
import threading
import webbrowser
from html import escape

import requests
from flask import Flask, request, render_template_string

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>OSM Suffix search Iran</title>
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
    input[type="text"] {
      padding: 8px;
      font-size: 16px;
      min-width: 280px;
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
  </style>
</head>
<body>
  <div class="container">
    <div class="topbar">
      <form method="get" action="/">
        <div class="form-row">
          <label for="suffix"><strong>Suffix:</strong></label>
          <input
            id="suffix"
            name="suffix"
            type="text"
            value="{{ suffix }}"
            placeholder="e. g. آباد"
            required
          >
          <button type="submit">Search</button>
        </div>
      </form>

      <div class="info">
        Search in Iran for
        cities, towns, villages, hamlets, suburbs, quarters, and neighbourhoods,
        ending with this suffix.
      </div>

      {% if error %}
        <div class="info error">{{ error }}</div>
      {% elif searched %}
        <div class="info">Places found: {{ count }}</div>
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
          radius: 5
        }).addTo(map);

        const popup = `
          <b>${m.name}</b><br>
          place: ${m.place}<br>
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


def build_query_for_suffix(suffix: str) -> str:
    escaped_suffix = escape_overpass_regex(suffix)
    return f"""
[out:json][timeout:180];

area["ISO3166-1"="IR"]["boundary"="administrative"]["admin_level"="2"]->.ir;

(
  node(area.ir)
    ["place"~"^(city|town|village|hamlet|suburb|quarter|neighbourhood)$"]
    ["name"~"{escaped_suffix}$"];

  node(area.ir)
    ["place"~"^(city|town|village|hamlet|suburb|quarter|neighbourhood)$"]
    ["name:fa"~"{escaped_suffix}$"];

  node(area.ir)
    ["place"~"^(city|town|village|hamlet|suburb|quarter|neighbourhood)$"]
    ["name:ar"~"{escaped_suffix}$"];
);
out body;
"""


def run_overpass(suffix: str) -> list[dict]:
    query = build_query_for_suffix(suffix)

    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        timeout=300,
        headers={"User-Agent": "osm-suffix-map/1.0"}
    )
    response.raise_for_status()

    data = response.json()
    elements = data.get("elements", [])

    results = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:fa") or tags.get("name:ar") or "Ohne Namen"
        results.append({
            "id": el.get("id"),
            "name": name,
            "place": tags.get("place", ""),
            "lat": el.get("lat"),
            "lon": el.get("lon"),
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
    suffix = request.args.get("suffix", "").strip()
    markers = []
    error = None
    searched = False

    if suffix:
        searched = True
        try:
            markers = run_overpass(suffix)
        except requests.HTTPError as e:
            error = f"HTTP-Fehler bei Overpass: {e}"
        except requests.RequestException as e:
            error = f"Netzwerkfehler: {e}"
        except Exception as e:
            error = f"Unerwarteter Fehler: {e}"

    return render_template_string(
        HTML_TEMPLATE,
        suffix=escape(suffix),
        markers_json=json.dumps(markers, ensure_ascii=False),
        count=len(markers),
        error=error,
        searched=searched,
    )
def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")


if __name__ == "__main__":
    threading.Timer(1.0, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)