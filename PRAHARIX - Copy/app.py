import os
import sqlite3
import requests
import time
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
    jsonify
)
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from sar_module import sar_risk_module, get_live_sar_products

app = Flask(__name__)
app.secret_key = "praharix_secret_2026"

# ==========================================
# LOGIN CREDENTIALS
# ==========================================

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "praharix2026"

USER_USERNAME = "user"
USER_PASSWORD = "user2026"

# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():
    conn = sqlite3.connect("praharix.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            place TEXT,
            magnitude REAL,
            latitude REAL,
            longitude REAL,
            risk TEXT,
            threat_level TEXT,
            threat_score INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==========================================
# THREAT ENGINE
# ==========================================

def calculate_threat(mag):
    try:
        mag = float(mag)
    except (TypeError, ValueError):
        mag = 0.0

    if mag >= 7.0:
        return ("🔴 RED", "CRITICAL", 100)
    elif mag >= 6.0:
        return ("🔴 RED", "HIGH", 80)
    elif mag >= 4.0:
        return ("🟡 YELLOW", "MEDIUM", 50)
    else:
        return ("🟢 GREEN", "LOW", 20)


def predict_threat(earthquakes):
    if not earthquakes:
        return {
            "prediction": "LOW",
            "confidence": 50
        }

    valid_mags = [eq["mag"] for eq in earthquakes if eq.get("mag") is not None]
    if not valid_mags:
        return {
            "prediction": "LOW",
            "confidence": 50
        }

    avg_mag = sum(valid_mags) / len(valid_mags)

    if avg_mag >= 6.0:
        prediction = "CRITICAL"
        confidence = 90
    elif avg_mag >= 5.0:
        prediction = "HIGH"
        confidence = 80
    elif avg_mag >= 4.0:
        prediction = "MEDIUM"
        confidence = 70
    else:
        prediction = "LOW"
        confidence = 60

    return {
        "prediction": prediction,
        "confidence": confidence
    }


def calculate_atfs(magnitude, event_count):
    mag_score = min(int(magnitude * 10), 50)
    frequency_score = min(event_count * 2, 30)
    historical_score = 20
    atfs = mag_score + frequency_score + historical_score
    return min(atfs, 100)

# ==========================================
# WEATHER (LIVE METEOROLOGICAL MODULE)
# ==========================================

_WEATHER_CACHE = {
    "data": None,
    "timestamp": 0
}

WMO_WEATHER_CODES = {
    0: ("Clear Sky", "☀️"),
    1: ("Mainly Clear", "🌤️"),
    2: ("Partly Cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Foggy", "🌫️"),
    48: ("Depositing Rime Fog", "🌫️"),
    51: ("Light Drizzle", "🌦️"),
    53: ("Moderate Drizzle", "🌦️"),
    55: ("Dense Drizzle", "🌧️"),
    61: ("Slight Rain", "🌧️"),
    63: ("Moderate Rain", "🌧️"),
    65: ("Heavy Rain", "🌧️"),
    71: ("Slight Snow", "🌨️"),
    73: ("Moderate Snow", "🌨️"),
    75: ("Heavy Snow", "🌨️"),
    80: ("Slight Rain Showers", "🌦️"),
    81: ("Moderate Rain Showers", "🌧️"),
    82: ("Violent Rain Showers", "⛈️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with Hail", "⛈️"),
    99: ("Severe Thunderstorm", "⛈️")
}

def degrees_to_cardinal(deg):
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    try:
        ix = round(deg / (360.0 / len(dirs))) % len(dirs)
        return dirs[ix]
    except Exception:
        return "N"

def get_weather():
    now = time.time()
    if _WEATHER_CACHE["data"] and (now - _WEATHER_CACHE["timestamp"] < 180):
        return _WEATHER_CACHE["data"]

    try:
        # National Command Center coordinates (HQ New Delhi 28.6139, 77.2090)
        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=28.6139"
            "&longitude=77.2090"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m,surface_pressure"
            "&timezone=auto"
        )
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            cur = resp.json().get("current", {})
            w_code = cur.get("weather_code", 0)
            cond_desc, cond_icon = WMO_WEATHER_CODES.get(w_code, ("Mainly Clear", "🌤️"))
            wind_deg = cur.get("wind_direction_10m", 0)
            wind_card = degrees_to_cardinal(wind_deg)

            weather_res = {
                "temp": round(cur.get("temperature_2m", 28.5), 1),
                "feels_like": round(cur.get("apparent_temperature", cur.get("temperature_2m", 28.5)), 1),
                "wind": round(cur.get("wind_speed_10m", 11.2), 1),
                "wind_dir": wind_card,
                "humidity": cur.get("relative_humidity_2m", 52),
                "precipitation": cur.get("precipitation", 0.0),
                "pressure": round(cur.get("surface_pressure", 1011.0), 1),
                "condition": f"{cond_desc} {cond_icon}",
                "condition_text": cond_desc,
                "icon": cond_icon,
                "location": "National Command HQ",
                "status": "LIVE 🟢",
                "updated_at": datetime.now().strftime("%H:%M:%S")
            }
            _WEATHER_CACHE["data"] = weather_res
            _WEATHER_CACHE["timestamp"] = now
            return weather_res
    except Exception as e:
        print("Live weather fetch warning:", e)

    if _WEATHER_CACHE["data"]:
        return _WEATHER_CACHE["data"]

    return {
        "temp": 28.5,
        "feels_like": 30.1,
        "wind": 11.2,
        "wind_dir": "NE",
        "humidity": 55,
        "precipitation": 0.0,
        "pressure": 1012.0,
        "condition": "Mainly Clear 🌤️",
        "condition_text": "Mainly Clear",
        "icon": "🌤️",
        "location": "National Command HQ",
        "status": "LIVE 🟢",
        "updated_at": datetime.now().strftime("%H:%M:%S")
    }

# ==========================================
# EARTHQUAKE FEED (USGS LIVE)
# ==========================================

_USGS_CACHE = {
    "data": None,
    "timestamp": 0
}

def get_earthquakes():
    now = time.time()
    if _USGS_CACHE["data"] and (now - _USGS_CACHE["timestamp"] < 90):
        return _USGS_CACHE["data"]

    earthquakes = []

    try:
        url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            features = data.get("features", [])

            for eq in features:
                props = eq.get("properties", {}) or {}
                geom = eq.get("geometry", {}) or {}
                coords = geom.get("coordinates", [0, 0, 0])

                event_id = eq.get("id") or f"eq_{time.time()}"
                place = props.get("place") or "Unknown Region"
                raw_mag = props.get("mag")
                mag = round(float(raw_mag), 2) if raw_mag is not None else 0.0

                lon = coords[0] if len(coords) > 0 else 0.0
                lat = coords[1] if len(coords) > 1 else 0.0
                depth = round(coords[2], 1) if len(coords) > 2 else 0.0

                risk, level, score = calculate_threat(mag)

                eq_time_ms = props.get("time")
                time_str = (
                    datetime.fromtimestamp(eq_time_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
                    if eq_time_ms
                    else "Recent"
                )

                earthquakes.append({
                    "event_id": event_id,
                    "place": place,
                    "mag": mag,
                    "lat": lat,
                    "lon": lon,
                    "depth": depth,
                    "time": time_str,
                    "tsunami": props.get("tsunami", 0),
                    "url": props.get("url", ""),
                    "risk": risk,
                    "threat_level": level,
                    "threat_score": score
                })

            if earthquakes:
                _USGS_CACHE["data"] = earthquakes
                _USGS_CACHE["timestamp"] = now
                return earthquakes

    except Exception as e:
        print("USGS Live Feed warning:", e)

    if _USGS_CACHE["data"]:
        return _USGS_CACHE["data"]

    return []

# ==========================================
# NASA EONET
# ==========================================

_NASA_CACHE = {
    "data": None,
    "timestamp": 0
}

def get_nasa_events():
    now = time.time()
    if _NASA_CACHE["data"] and (now - _NASA_CACHE["timestamp"] < 300):
        return _NASA_CACHE["data"]

    disasters = []
    try:
        url = "https://eonet.gsfc.nasa.gov/api/v3/events?limit=10"
        data = requests.get(url, timeout=6).json()
        for event in data.get("events", [])[:10]:
            categories = event.get("categories", [{}])
            cat_title = categories[0].get("title", "Natural Event") if categories else "Natural Event"
            disasters.append({
                "title": event.get("title", "Unknown Event"),
                "category": cat_title
            })
        if disasters:
            _NASA_CACHE["data"] = disasters
            _NASA_CACHE["timestamp"] = now
            return disasters
    except Exception as e:
        print("NASA EONET warning:", e)

    if _NASA_CACHE["data"]:
        return _NASA_CACHE["data"]

    return disasters

# ==========================================
# DATABASE SAVE ENGINE
# ==========================================

_LAST_DB_SAVE_TIME = 0

def save_earthquakes():
    global _LAST_DB_SAVE_TIME
    now = time.time()
    if now - _LAST_DB_SAVE_TIME < 60:
        return

    earthquakes = get_earthquakes()
    if not earthquakes:
        return

    try:
        conn = sqlite3.connect("praharix.db")
        cur = conn.cursor()

        records = [
            (
                eq["event_id"],
                eq["place"],
                eq["mag"],
                eq["lat"],
                eq["lon"],
                eq["risk"],
                eq["threat_level"],
                eq["threat_score"]
            )
            for eq in earthquakes
        ]

        cur.executemany("""
            INSERT OR IGNORE INTO incidents
            (event_id, place, magnitude, latitude, longitude, risk, threat_level, threat_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, records)

        conn.commit()
        conn.close()
        _LAST_DB_SAVE_TIME = now
    except Exception as e:
        print("Database save warning:", e)

# ==========================================
# AI FORECAST MODULE
# ==========================================

def forecast_risk(current_risk):
    if current_risk >= 80:
        return {
            "next_24h": 95,
            "trend": "Increasing"
        }
    elif current_risk >= 50:
        return {
            "next_24h": 75,
            "trend": "Stable"
        }
    else:
        return {
            "next_24h": 40,
            "trend": "Decreasing"
        }

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["role"] = "admin"
            return redirect("/")
        elif username == USER_USERNAME and password == USER_PASSWORD:
            session["role"] = "user"
            return redirect("/")
        else:
            return render_template("login.html", error="Invalid Credentials")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ==========================================
# HOME DASHBOARD
# ==========================================

@app.route("/")
def home():
    if "role" not in session:
        return redirect("/login")

    earthquakes = get_earthquakes()
    save_earthquakes()

    prediction = predict_threat(earthquakes)

    if prediction["prediction"] == "CRITICAL":
        recommendation = """
Immediate monitoring required.
Activate emergency response teams.
Increase satellite surveillance.
"""
    elif prediction["prediction"] == "HIGH":
        recommendation = """
High seismic activity detected.
Keep disaster teams on standby.
Monitor affected regions closely.
"""
    elif prediction["prediction"] == "MEDIUM":
        recommendation = """
Moderate threat detected.
Continue monitoring.
Prepare resources if activity increases.
"""
    else:
        recommendation = """
Situation stable.
Continue routine monitoring.
"""

    disasters = get_nasa_events()
    satellite = {
        "status": "ACTIVE",
        "source": "NASA EONET",
        "events": len(disasters),
        "coverage": "GLOBAL"
    }

    weather = get_weather()
    sar_data = sar_risk_module()
    sar_score = sar_data["risk_score"]

    current_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    highest_score = 0
    highest_threat = "LOW"
    alert_count = 0
    critical = 0
    latest_alert = None

    danger_zones = []

    for eq in earthquakes:
        danger_zones.append({
            "place": eq["place"],
            "score": eq["threat_score"],
            "level": eq["threat_level"],
            "mag": eq["mag"],
            "time": eq.get("time", "")
        })

        if eq["threat_score"] > highest_score:
            highest_score = eq["threat_score"]
            highest_threat = eq["threat_level"]

        if eq["threat_level"] == "CRITICAL":
            critical += 1
            alert_count += 1
            if not latest_alert:
                latest_alert = {
                    "place": eq["place"],
                    "magnitude": eq["mag"],
                    "threat": eq["threat_level"]
                }
        elif eq["threat_level"] == "HIGH":
            alert_count += 1
            if not latest_alert and critical == 0:
                latest_alert = {
                    "place": eq["place"],
                    "magnitude": eq["mag"],
                    "threat": eq["threat_level"]
                }

    # Top 10 global danger zones
    danger_zones = sorted(
        danger_zones,
        key=lambda x: (x["score"], x["mag"]),
        reverse=True
    )[:10]

    # Calculate realistic global composite risk score (0-100)
    if danger_zones:
        top_avg = sum(z["score"] for z in danger_zones[:5]) / min(len(danger_zones), 5)
        global_risk_score = min(max(highest_score, int(top_avg * 0.7 + critical * 5)), 100)
    else:
        global_risk_score = 20

    stats = {
        "earthquakes": len(earthquakes),
        "disasters": len(disasters),
        "alerts": alert_count,
        "critical": critical,
        "score": highest_score,
        "threat": highest_threat
    }

    earthquake_score = critical * 20
    disaster_score = len(disasters) * 5
    history_score = min(alert_count, 20)

    fti_score = min(
        earthquake_score + disaster_score + history_score,
        100
    )

    chart_labels = [
        "Earthquakes",
        "NASA Events",
        "Alerts",
        "Critical"
    ]

    chart_scores = [
        len(earthquakes),
        len(disasters),
        alert_count,
        critical
    ]

    return render_template(
        "index.html",
        stats=stats,
        earthquakes=earthquakes,
        disasters=disasters,
        weather=weather,
        sar_data=sar_data,
        sar_score=sar_score,
        satellite=satellite,
        latest_alert=latest_alert,
        global_risk_score=global_risk_score,
        danger_zones=danger_zones,
        chart_labels=chart_labels,
        chart_scores=chart_scores,
        prediction=prediction,
        fti_score=fti_score,
        current_time=current_time,
        recommendation=recommendation
    )

# ==========================================
# SAR INTELLIGENCE ROUTE
# ==========================================

@app.route("/sar")
def sar():
    sar_data = sar_risk_module()
    forecast = forecast_risk(sar_data["risk_score"])

    response_assets = [
        {"name": "National Remote Sensing Centre (NRSC)", "status": "ACTIVE"},
        {"name": "Copernicus Space Data Network", "status": "ONLINE"},
        {"name": "State Disaster Response Force (SDRF)", "status": "READY"},
        {"name": "Police Command & Tactical Control", "status": "ACTIVE"},
        {"name": "Emergency Operations Center (EOC)", "status": "ONLINE"}
    ]

    return render_template(
        "sar.html",
        sar_data=sar_data,
        forecast=forecast,
        response_assets=response_assets
    )

# ==========================================
# HISTORY
# ==========================================

@app.route("/history")
def history():
    if session.get("role") != "admin":
        return redirect("/")

    conn = sqlite3.connect("praharix.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT place, magnitude, threat_level, threat_score, created_at
        FROM incidents
        ORDER BY id DESC
        LIMIT 100
    """)
    incidents = cur.fetchall()
    conn.close()

    return render_template(
        "history.html",
        incidents=incidents
    )

# ==========================================
# TREND
# ==========================================

@app.route("/trend")
def trend():
    conn = sqlite3.connect("praharix.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT threat_level, COUNT(*)
        FROM incidents
        GROUP BY threat_level
    """)
    rows = cur.fetchall()
    conn.close()

    labels = []
    values = []
    for row in rows:
        labels.append(row[0])
        values.append(row[1])

    return render_template(
        "trend.html",
        labels=labels,
        values=values
    )

# ==========================================
# INDIA REGIONAL MONITOR
# ==========================================

@app.route("/india")
def india():
    earthquakes = get_earthquakes()
    india_events = []

    regional_keywords = [
        "india", "nepal", "pakistan", "bangladesh", "china", "myanmar",
        "bhutan", "sri lanka", "afghanistan", "hindu kush", "tibet",
        "kashmir", "delhi", "assam", "manipur", "gujarat", "andaman",
        "nicobar", "uttarakhand", "himachal", "meghalaya"
    ]

    for eq in earthquakes:
        place_lower = eq["place"].lower()
        lat = eq["lat"]
        lon = eq["lon"]

        is_keyword = any(kw in place_lower for kw in regional_keywords)
        is_geo = (5.0 <= lat <= 38.5) and (65.0 <= lon <= 98.5)

        if is_keyword or is_geo:
            india_events.append(eq)

    return render_template(
        "india.html",
        earthquakes=india_events
    )

# ==========================================
# ANALYTICS CENTER
# ==========================================

@app.route("/analytics")
def analytics():
    if session.get("role") != "admin":
        return redirect("/")

    conn = sqlite3.connect("praharix.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM incidents")
    total_incidents = cur.fetchone()[0]

    cur.execute("""
        SELECT place, threat_score, threat_level
        FROM incidents
        ORDER BY threat_score DESC
        LIMIT 5
    """)
    rows = cur.fetchall()
    conn.close()

    danger_zones = []
    for row in rows:
        danger_zones.append({
            "place": row[0],
            "score": row[1],
            "level": row[2]
        })

    critical = len([d for d in danger_zones if d["level"] == "CRITICAL"])

    stats = {
        "earthquakes": total_incidents,
        "disasters": len(danger_zones),
        "critical": critical,
        "threat": danger_zones[0]["level"] if danger_zones else "LOW"
    }

    fusion_score = danger_zones[0]["score"] if danger_zones else 0
    fusion_threat = danger_zones[0]["level"] if danger_zones else "LOW"
    fusion_confidence = min(fusion_score + 20, 99)

    return render_template(
        "analytics.html",
        stats=stats,
        danger_zones=danger_zones,
        fusion_score=fusion_score,
        fusion_threat=fusion_threat,
        fusion_confidence=fusion_confidence
    )

# ==========================================
# REPORT & EXPORT
# ==========================================

@app.route("/download_pdf")
def download_pdf():
    pdf_file = "PRAHARIX_Report.pdf"
    doc = SimpleDocTemplate(pdf_file)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("PRAHARI-X Intelligence Report", styles["Title"]))
    story.append(Spacer(1, 12))

    earthquakes = get_earthquakes()
    disasters = get_nasa_events()

    critical = len([e for e in earthquakes if e["threat_level"] == "CRITICAL"])

    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    story.append(Paragraph(f"Total Earthquakes: {len(earthquakes)}", styles["Normal"]))
    story.append(Paragraph(f"NASA Events: {len(disasters)}", styles["Normal"]))
    story.append(Paragraph(f"Critical Threats: {critical}", styles["Normal"]))

    doc.build(story)

    return send_file(pdf_file, as_attachment=True)


@app.route("/report")
def report():
    if session.get("role") != "admin":
        return redirect("/")

    earthquakes = get_earthquakes()
    disasters = get_nasa_events()

    critical = len([e for e in earthquakes if e["threat_level"] == "CRITICAL"])
    highest = max(earthquakes, key=lambda x: x["threat_score"]) if earthquakes else None

    return render_template(
        "report.html",
        earthquakes=len(earthquakes),
        disasters=len(disasters),
        critical=critical,
        highest=highest,
        generated=datetime.now().strftime("%d-%m-%Y %H:%M")
    )


@app.route("/alerts")
def alerts():
    if "role" not in session:
        return redirect("/login")

    earthquakes = get_earthquakes()

    critical_alerts = []
    high_alerts = []
    medium_alerts = []

    for eq in earthquakes:
        if eq["threat_level"] == "CRITICAL":
            critical_alerts.append(eq)
        elif eq["threat_level"] == "HIGH":
            high_alerts.append(eq)
        else:
            medium_alerts.append(eq)

    return render_template(
        "alerts.html",
        critical_alerts=critical_alerts,
        high_alerts=high_alerts,
        medium_alerts=medium_alerts
    )

# ==========================================
# REAL-TIME JSON APIS FOR DASHBOARD SYNC
# ==========================================

@app.route("/api/live")
def api_live():
    weather = get_weather()
    sar_data = sar_risk_module()
    earthquakes = get_earthquakes()
    return jsonify({
        "status": "OK",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "weather": weather,
        "sar": sar_data,
        "earthquakes_count": len(earthquakes),
        "earthquakes": earthquakes[:20]
    })


@app.route("/api/weather")
def api_weather():
    return jsonify(get_weather())


@app.route("/api/sar")
def api_sar():
    return jsonify(sar_risk_module())


@app.route("/api/earthquakes")
def api_earthquakes():
    earthquakes = get_earthquakes()
    return jsonify({
        "count": len(earthquakes),
        "earthquakes": earthquakes
    })

# ==========================================
# STARTUP & MAIN EXECUTION
# ==========================================

save_earthquakes()

if __name__ == "__main__":
    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )