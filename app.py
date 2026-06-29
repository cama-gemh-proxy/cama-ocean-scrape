"""
CAMA / Ocean — ΓΕΜΗ Scraper
Τρέχει στο Render.com δίπλα στο ΓΕΜΗ proxy.
Κάνει scrape το publicity.businessportal.gr ανά ΚΑΔ
και εμπλουτίζει με ΓΕΜΗ API.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import os, time, json, re
from datetime import datetime

app = Flask(__name__)
CORS(app)

GEMH_KEY  = os.environ.get("GEMH_KEY", "gpajEUg9mdTnlIz17DkQEgi4XtNqgHA4")
GEMH_BASE = BASE_URL  = "https://opendata-api.businessportal.gr/api/opendata/v1"
PORTAL    = "https://publicity.businessportal.gr"


    HEADERS = {
    "Accept": "application/json",
    "api-key": GEMH_KEY
}

# ── Cache in-memory ────────────────────────────────────
cache = {}  # {kad: {timestamp, leads: []}}

# ── KAD Config ────────────────────────────────────────
OCEAN_KADS = [
    {"kad":"47.78.89.04","desc":"Είδη κολύμβησης","type":"retail"},
    {"kad":"47.78.86.13","desc":"Παιχνίδια/leisure","type":"retail"},
    {"kad":"47.62.62.00","desc":"Αναψυχή/sport","type":"retail"},
    {"kad":"47.65.10",   "desc":"Παιχνίδια λιανικά","type":"retail"},
    {"kad":"47.19.10",   "desc":"Πολυκαταστήματα","type":"retail"},
    {"kad":"46.49.23.00","desc":"Παιχνίδια χονδρ.","type":"wholesale"},
    {"kad":"46493200",   "desc":"Αθλητικά χονδρ.","type":"wholesale"},
    {"kad":"46.39.00.00","desc":"Είδη πισίνας","type":"wholesale"},
    {"kad":"46.35.0000", "desc":"Αναψυχή χονδρ.","type":"wholesale"},
]

CAMA_KADS = [
    {"kad":"56",          "desc":"Εστιατόρια/Καφέ","type":"horeca"},
    {"kad":"55",          "desc":"Ξενοδοχεία","type":"horeca"},
    {"kad":"56.21",       "desc":"Catering","type":"horeca"},
    {"kad":"46.49.23.18", "desc":"Αναλώσιμα εστίασης","type":"wholesale"},
    {"kad":"46.49.23.05", "desc":"Συσκευασίες","type":"wholesale"},
    {"kad":"46.64.08.97", "desc":"Εξοπλισμός εστίασης","type":"wholesale"},
    {"kad":"46.44.11",    "desc":"Είδη οικ.χρήσης","type":"wholesale"},
]

# ══════════════════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════════════════
@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "CAMA/Ocean ΓΕΜΗ Scraper",
        "version": "1.0",
        "endpoints": [
            "/scrape/ocean",
            "/scrape/cama",
            "/scrape/kad?kad=56&size=50",
            "/enrich/afm/<afm>",
            "/cache/clear",
            "/status"
        ]
    })

@app.route("/status")
def status():
    return jsonify({
        "cached_kads": list(cache.keys()),
        "total_cached_leads": sum(len(v.get("leads",[])) for v in cache.values()),
        "gemh_key_set": bool(GEMH_KEY),
        "timestamp": datetime.now().isoformat()
    })

# ══════════════════════════════════════════════════════
# SCRAPE BY KAD
# ══════════════════════════════════════════════════════
@app.route("/scrape/kad")
def scrape_kad():
    kad  = request.args.get("kad","56")
    size = int(request.args.get("size", 50))
    refresh = request.args.get("refresh","false").lower() == "true"

    # Check cache (1 hour)
    if kad in cache and not refresh:
        cached = cache[kad]
        age = (datetime.now() - datetime.fromisoformat(cached["timestamp"])).seconds
        if age < 3600:
            leads = cached["leads"][:size]
            return jsonify({"ok":True,"source":"cache","kad":kad,"count":len(leads),"leads":leads})

    leads = []

    # ── Method 1: publicity.businessportal.gr ──
    try:
        leads = scrape_portal(kad, size)
    except Exception as e:
        print(f"Portal scrape error: {e}")

    # ── Method 2: ΓΕΜΗ API search ──
    if not leads:
        try:
            leads = search_gemh_api(kad, size)
        except Exception as e:
            print(f"ΓΕΜΗ API search error: {e}")

    # Enrich with ΓΕΜΗ API if we have AFMs
    enriched = []
    for lead in leads[:size]:
        if lead.get("afm"):
            gemh = enrich_from_gemh(lead["afm"])
            if gemh:
                lead.update(gemh)
        enriched.append(lead)
        time.sleep(0.3)  # rate limit

    cache[kad] = {"timestamp": datetime.now().isoformat(), "leads": enriched}

    return jsonify({
        "ok": True,
        "source": "scrape",
        "kad": kad,
        "count": len(enriched),
        "leads": enriched
    })

@app.route("/scrape/ocean")
def scrape_ocean():
    """Scrape όλα τα Ocean ΚΑΔ"""
    size = int(request.args.get("size", 20))
    all_leads = []
    errors = []

    for k in OCEAN_KADS:
        try:
            leads = scrape_portal(k["kad"], size)
            if not leads:
                leads = search_gemh_api(k["kad"], size)
            for l in leads:
                l["kadDesc"] = k["desc"]
                l["type"] = k["type"]
            all_leads.extend(leads[:size])
            time.sleep(1)
        except Exception as e:
            errors.append({"kad": k["kad"], "error": str(e)})

    return jsonify({
        "ok": True,
        "platform": "ocean",
        "total": len(all_leads),
        "leads": all_leads,
        "errors": errors
    })

@app.route("/scrape/cama")
def scrape_cama():
    """Scrape όλα τα CAMA ΚΑΔ"""
    size = int(request.args.get("size", 20))
    all_leads = []
    errors = []

    for k in CAMA_KADS:
        try:
            leads = scrape_portal(k["kad"], size)
            if not leads:
                leads = search_gemh_api(k["kad"], size)
            for l in leads:
                l["kadDesc"] = k["desc"]
                l["type"] = k["type"]
            all_leads.extend(leads[:size])
            time.sleep(1)
        except Exception as e:
            errors.append({"kad": k["kad"], "error": str(e)})

    return jsonify({
        "ok": True,
        "platform": "cama",
        "total": len(all_leads),
        "leads": all_leads,
        "errors": errors
    })

# ══════════════════════════════════════════════════════
# SCRAPER — publicity.businessportal.gr
# ══════════════════════════════════════════════════════
def scrape_portal(kad, size=50):
    leads = []
    page = 1

    while len(leads) < size:
        url = f"{PORTAL}/results?kad={kad}&page={page}&size=20"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break

            soup = BeautifulSoup(r.text, "html.parser")

            # Δοκιμάζουμε διαφορετικά selectors
            rows = (
                soup.select(".company-row") or
                soup.select(".result-item") or
                soup.select("tr.company") or
                soup.select(".search-result") or
                soup.select("[data-gemh]") or
                soup.select(".entity-row")
            )

            if not rows:
                # Try JSON response
                try:
                    data = r.json()
                    if isinstance(data, dict) and "results" in data:
                        for item in data["results"]:
                            leads.append(parse_json_item(item, kad))
                        if len(data["results"]) < 20:
                            break
                        page += 1
                        continue
                except:
                    pass
                break

            for row in rows:
                lead = parse_html_row(row, kad)
                if lead:
                    leads.append(lead)

            if len(rows) < 20:
                break
            page += 1
            time.sleep(0.5)

        except Exception as e:
            print(f"Scrape error page {page}: {e}")
            break

    return leads[:size]

def parse_html_row(row, kad):
    """Parse HTML row από το portal"""
    try:
        # Δοκιμάζουμε κοινά patterns
        name = (
            row.select_one(".company-name, .name, .title, h3, h4") or
            row.select_one("[class*='name'], [class*='title']")
        )
        afm = (
            row.select_one(".afm, .vat, [data-afm]") or
            row.find(string=re.compile(r'\d{9}'))
        )
        gemh_num = row.select_one(".gemh, [data-gemh], .registration-number")
        address = row.select_one(".address, .location, [class*='address']")

        if not name:
            return None

        return {
            "name": name.get_text(strip=True) if hasattr(name,'get_text') else str(name),
            "afm": afm.get_text(strip=True) if afm and hasattr(afm,'get_text') else (str(afm).strip() if afm else ""),
            "gemhNumber": gemh_num.get_text(strip=True) if gemh_num and hasattr(gemh_num,'get_text') else "",
            "address": address.get_text(strip=True) if address and hasattr(address,'get_text') else "",
            "kad": kad,
            "source": "portal_scrape"
        }
    except:
        return None

def parse_json_item(item, kad):
    """Parse JSON item από API response"""
    return {
        "name": item.get("name") or item.get("title") or item.get("companyName",""),
        "afm": item.get("afm") or item.get("vat") or item.get("tin",""),
        "gemhNumber": item.get("registrationNumber") or item.get("gemhNumber",""),
        "address": item.get("address") or item.get("headquarters",""),
        "legalForm": item.get("legalForm",""),
        "status": item.get("status",""),
        "foundedDate": item.get("foundedDate") or item.get("establishmentDate",""),
        "representative": item.get("representative") or item.get("legalRepresentative",""),
        "kad": kad,
        "source": "portal_api"
    }

# ══════════════════════════════════════════════════════
# ΓΕΜΗ API SEARCH
# ══════════════════════════════════════════════════════
def search_gemh_api(kad, size=50):
    """Αναζήτηση μέσω ΓΕΜΗ API"""
    leads = []

    # Δοκιμάζουμε διαφορετικά endpoints
    endpoints = [
        f"{GEMH_BASE}/search?api_key={GEMH_KEY}&kad={kad}&size={size}",
        f"{GEMH_BASE}/search?api_key={GEMH_KEY}&activityCode={kad}&size={size}",
        f"{GEMH_BASE}/companies?api_key={GEMH_KEY}&kad={kad}&size={size}",
        f"{GEMH_BASE}/search?api_key={GEMH_KEY}&activities={kad}&size={size}",
    ]

    for url in endpoints:
        try:
            r = requests.get(url, headers={"Accept":"application/json"}, timeout=12)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data,list) else data.get("results") or data.get("companies") or data.get("data") or []
                for item in items:
                    leads.append(parse_json_item(item, kad))
                if leads:
                    break
            time.sleep(0.5)
        except Exception as e:
            print(f"ΓΕΜΗ API error: {e}")

    return leads[:size]

# ══════════════════════════════════════════════════════
# ENRICH BY AFM
# ══════════════════════════════════════════════════════
@app.route("/enrich/afm/<afm>")
def enrich_afm(afm):
    result = enrich_from_gemh(afm)
    if result:
        return jsonify({"ok":True,"afm":afm,"data":result})
    return jsonify({"ok":False,"afm":afm,"error":"Not found"}), 404

def enrich_from_gemh(afm):
    """Enrich ΑΦΜ από ΓΕΜΗ API"""
    endpoints = [
        f"{GEMH_BASE}/search?api_key={GEMH_KEY}&query={afm}&size=1",
        f"{GEMH_BASE}/companies?api_key={GEMH_KEY}&afm={afm}",
        f"{GEMH_BASE}/company/{afm}?api_key={GEMH_KEY}",
    ]
    for url in endpoints:
        try:
            r = requests.get(url, headers={"Accept":"application/json"}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    data = data[0]
                if isinstance(data, dict) and data:
                    return {
                        "gemhNumber":     data.get("registrationNumber") or data.get("gemhNumber",""),
                        "name":           data.get("name") or data.get("title",""),
                        "legalForm":      data.get("legalForm",""),
                        "status":         data.get("status",""),
                        "foundedDate":    data.get("foundedDate") or data.get("establishmentDate",""),
                        "representative": data.get("representative") or data.get("legalRepresentative",""),
                        "address":        data.get("address") or data.get("headquarters",""),
                        "capital":        data.get("shareCapital",""),
                        "_raw_keys":      list(data.keys())[:15]
                    }
        except:
            pass
    return None

# ══════════════════════════════════════════════════════
# CACHE
# ══════════════════════════════════════════════════════
@app.route("/cache/clear")
def clear_cache():
    cache.clear()
    return jsonify({"ok":True,"message":"Cache cleared"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)
