from flask import Flask, render_template, request, jsonify, send_file
import requests
import pandas as pd
import io
import re

app = Flask(__name__)

API_URL = "https://www.microburbs.com.au/report_generator/api/suburb/properties"

def parse_land_size(land_raw):
    """Return land size as float (sqm) or None."""
    if land_raw is None:
        return None
    s = str(land_raw).strip()
    # common forms: "556 m²", "556 m2", "708.0", "None", "nan"
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    if m:
        try:
            return float(m.group(1))
        except:
            return None
    return None

@app.route('/')
def home():
    return render_template('index.html')

# Replace your existing get_properties with this function
import json
import io

SAMPLE_FALLBACK_JSON = {
  "results": [
    {
      "address": {"street":"301 Pacific Highway","sal":"Belmont North","state":"NSW"},
      "coordinates": {"latitude": -33.01533954, "longitude": 151.66960709},
      "attributes": {"bedrooms": 4, "bathrooms": 2, "land_size": "556 m²"},
      "price": 950000,
      "listing_date": "2025-11-12",
      "property_type": "House"
    },
    {
      "address": {"street":"82 Old Belmont Road","sal":"Belmont North","state":"NSW"},
      "coordinates": {"latitude": -33.01774677, "longitude": 151.67214997},
      "attributes": {"bedrooms": 4, "bathrooms": 3, "land_size": "940 m²"},
      "price": 1300000,
      "listing_date": "2025-11-05",
      "property_type": "House"
    },
    {
      "address": {"street":"6 Brabham Close","sal":"Belmont North","state":"NSW"},
      "coordinates": {"latitude": -33.01752803, "longitude": 151.67557993},
      "attributes": {"bedrooms": 3, "bathrooms": 1, "land_size": "708.0"},
      "price": 900000,
      "listing_date": "2025-11-03",
      "property_type": "House"
    }
  ]
}

@app.route('/get_properties', methods=['POST'])
def get_properties():
    suburb = request.form.get('suburb', '').strip()
    if not suburb:
        return jsonify({"error": "Please provide a suburb"}), 400

    headers = {
        "Authorization": "Bearer test",
        "Content-Type": "application/json"
    }
    params = {"suburb": suburb}

    # 1) Call API and log response for debugging
    try:
        resp = requests.get(API_URL, params=params, headers=headers, timeout=10)
        print("==== API DEBUG ====")
        print("Requested URL:", resp.url)
        print("Status code:", resp.status_code)
        text_snippet = resp.text[:1500] if resp.text else "<empty>"
        print("Response snippet (first 1500 chars):", text_snippet)
        try:
            data = resp.json()
        except Exception as e:
            print("JSON decode error:", e)
            # set data to empty to trigger fallback
            data = {"results": []}
    except Exception as e:
        print("HTTP request failed:", e)
        data = {"results": []}

    raw_results = data.get("results", [])
    # 2) If sandbox returned zero results, use local sample fallback (makes UI work offline)
    if not raw_results:
        print("API returned 0 results — using SAMPLE_FALLBACK_JSON for demo.")
        data = SAMPLE_FALLBACK_JSON
        raw_results = data["results"]

    # 3) Parse and normalize results (ensure no 'null' strings are returned)
    props = []
    for r in raw_results:
        addr_obj = r.get("address", {}) or {}
        street = addr_obj.get("street") or r.get("area_name") or addr_obj.get("sal") or "N/A"
        price = r.get("price")
        bedrooms = r.get("attributes", {}).get("bedrooms")
        bathrooms = r.get("attributes", {}).get("bathrooms")
        land_raw = r.get("attributes", {}).get("land_size")
        lat = r.get("coordinates", {}).get("latitude")
        lon = r.get("coordinates", {}).get("longitude")

        # parse land safely
        land_sqm = parse_land_size(land_raw)
        price_per_sqm = None
        if price is not None and land_sqm:
            try:
                price_per_sqm = round(price / land_sqm, 2)
            except Exception:
                price_per_sqm = None

        props.append({
            "address": street if street is not None else "N/A",
            "price": price if price is not None else None,
            "bedrooms": bedrooms if bedrooms is not None else None,
            "bathrooms": bathrooms if bathrooms is not None else None,
            "land": f"{land_sqm:.0f} m²" if land_sqm else None,
            "land_sqm": land_sqm,
            "latitude": lat,
            "longitude": lon,
            "price_per_sqm": price_per_sqm
        })

    df = pd.DataFrame(props)
    if df.empty:
        summary = {"avg_price": "N/A", "avg_beds": "N/A", "avg_land": "N/A"}
    else:
        avg_price = df["price"].dropna().mean() if not df["price"].dropna().empty else None
        avg_beds = df["bedrooms"].dropna().mean() if not df["bedrooms"].dropna().empty else None
        avg_land = df["land_sqm"].dropna().mean() if not df["land_sqm"].dropna().empty else None
        summary = {
            "avg_price": f"${avg_price:,.0f}" if avg_price else "N/A",
            "avg_beds": round(avg_beds, 2) if avg_beds else "N/A",
            "avg_land": f"{avg_land:.0f} m²" if avg_land else "N/A"
        }

    # CSV for download (string)
    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    csv_buf.seek(0)
    csv_string = csv_buf.getvalue()

    return jsonify({
        "suburb": suburb,
        "raw_api_results_count": len(raw_results),
        "properties": props,
        "summary": summary,
        "csv": csv_string
    })


@app.route('/download_csv', methods=['POST'])
def download_csv():
    csv_text = request.form.get('csv')
    if not csv_text:
        return "No CSV data", 400
    buf = io.BytesIO()
    buf.write(csv_text.encode('utf-8'))
    buf.seek(0)
    return send_file(buf, mimetype='text/csv', as_attachment=True, download_name='properties.csv')

if __name__ == '__main__':
    app.run(debug=True)
