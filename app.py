from flask import Flask, request, jsonify
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)
import requests, os, time
from datetime import datetime

app = Flask(__name__)
CORS(app, origins="*", allow_headers="*", methods=["GET","POST","OPTIONS"])

GEMH_KEY = os.environ.get("GEMH_KEY", "gpajEUg9mdTnlIz17DkQEgi4XtNqgHA4")
BASE_URL = "https://opendata-api.businessportal.gr/api/opendata/v1"

HEADERS = {
    "Accept": "application/json",
    "api-key": GEMH_KEY
}

cache = {}


@app.route("/")
def home():
    return jsonify({"status": "ok", "service": "CAMA Ocean GEMH Scraper v3"})


@app.route("/health")
def health():
    try:
        r = requests.get(f"{BASE_URL}/health", headers=HEADERS, timeout=10)
        return jsonify({"proxy": "ok", "gemh_status": r.status_code, "gemh": r.json() if r.ok else r.text[:200]})
    except Exception as e:
        return jsonify({"proxy": "ok", "gemh_error": str(e)})


@app.route("/company/afm/<afm>")
def company_by_afm(afm):
    try:
        params = {"afmGemi": afm, "size": 5}
        r = requests.get(f"{BASE_URL}/companies", headers=HEADERS, params=params, timeout=12)
        if r.ok:
            data = r.json()
            items = data.get("searchResults") or data.get("data") or data.get("results") or []
            if items:
                return jsonify({"ok": True, "afm": afm, "data": items[0]})
        return jsonify({"ok": False, "afm": afm, "status": r.status_code, "error": r.text[:300]}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/company/gemh/<arGemi>")
def company_by_gemh(arGemi):
    try:
        r = requests.get(f"{BASE_URL}/companies/{arGemi}", headers=HEADERS, timeout=12)
        if r.ok:
            return jsonify({"ok": True, "arGemi": arGemi, "data": r.json()})
        return jsonify({"ok": False, "status": r.status_code, "error": r.text[:300]}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/scrape/kad")
def scrape_kad():
    kad = request.args.get("kad", "56")
    size = int(request.args.get("size", 20))
    attempts = [
        {"activityId": kad, "size": size},
        {"kad": kad, "size": size},
        {"activityCode": kad, "size": size},
    ]
    for params in attempts:
        try:
            r = requests.get(f"{BASE_URL}/companies", headers=HEADERS, params=params, timeout=15)
            if r.ok:
                data = r.json()
                items = data.get("searchResults") or data.get("data") or data.get("results") or []
                if items:
                    return jsonify({"ok": True, "kad": kad, "count": len(items), "leads": items})
            time.sleep(0.3)
        except Exception:
            continue
    return jsonify({"ok": False, "kad": kad, "error": "No results", "leads": []})


@app.route("/metadata/activities")
def get_activities():
    try:
        r = requests.get(f"{BASE_URL}/metadata/activities", headers=HEADERS, timeout=12)
        return jsonify({"ok": r.ok, "status": r.status_code, "data": r.json() if r.ok else r.text[:500]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/webhook/lead", methods=["POST", "GET"])
def webhook_lead():
    data = request.json or request.form.to_dict() or {}
    lead = {
        "name": data.get("company_name") or data.get("name", ""),
        "email": data.get("email", ""),
        "phone": data.get("phone", ""),
        "area": data.get("city") or data.get("area", ""),
        "afm": data.get("afm", ""),
        "source": "oceanswimmingproducts.gr",
        "timestamp": datetime.now().isoformat()
    }
    if "webhook_leads" not in cache:
        cache["webhook_leads"] = []
    cache["webhook_leads"].append(lead)
    return jsonify({"ok": True, "lead": lead})


@app.route("/webhook/leads")
def get_webhook_leads():
    leads = cache.get("webhook_leads", [])
    return jsonify({"ok": True, "count": len(leads), "leads": leads})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)
