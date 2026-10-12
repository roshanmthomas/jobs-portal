#!/usr/bin/env python3
"""Refresh the public IoT job feed from supported public ATS job-board endpoints.
No credentials are used. Unsupported/unreachable boards are skipped and recorded in metadata.
"""
from __future__ import annotations
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HEADERS = {"User-Agent": "Global-IoT-Career-Radar/1.0 (+public job-board aggregator)", "Accept": "application/json"}

REGION_CENTERS = {
    "India": (22.5, 79.0, "Asia"), "United States": (39.5, -98.35, "North America"),
    "Canada": (56.1, -106.3, "North America"), "United Kingdom": (54.5, -3.0, "Europe"),
    "Germany": (51.2, 10.4, "Europe"), "France": (46.2, 2.2, "Europe"),
    "Netherlands": (52.1, 5.3, "Europe"), "Ireland": (53.1, -8.0, "Europe"),
    "Sweden": (60.1, 18.6, "Europe"), "Australia": (-25.3, 133.8, "Oceania"),
    "New Zealand": (-40.9, 174.9, "Oceania"), "Singapore": (1.35, 103.82, "Asia"),
    "United Arab Emirates": (24.2, 54.5, "Asia"), "Japan": (36.2, 138.2, "Asia"),
    "South Korea": (36.5, 127.9, "Asia"), "China": (35.9, 104.2, "Asia"),
    "Israel": (31.0, 34.8, "Asia"), "Brazil": (-14.2, -51.9, "South America"),
    "Mexico": (23.6, -102.5, "North America"), "South Africa": (-30.6, 22.9, "Africa"),
    "Europe": (51.0, 10.0, "Europe"), "North America": (39.0, -98.0, "North America"),
    "Asia Pacific": (20.0, 105.0, "Asia"), "Worldwide": (20.0, 0.0, "Global"),
}
COUNTRY_ALIASES = [
    ("india", "India"), ("united states", "United States"), ("usa", "United States"), ("u.s.", "United States"),
    ("canada", "Canada"), ("united kingdom", "United Kingdom"), ("uk", "United Kingdom"), ("london", "United Kingdom"),
    ("germany", "Germany"), ("berlin", "Germany"), ("france", "France"), ("paris", "France"),
    ("netherlands", "Netherlands"), ("amsterdam", "Netherlands"), ("ireland", "Ireland"), ("dublin", "Ireland"),
    ("sweden", "Sweden"), ("australia", "Australia"), ("sydney", "Australia"), ("melbourne", "Australia"),
    ("new zealand", "New Zealand"), ("singapore", "Singapore"), ("united arab emirates", "United Arab Emirates"),
    ("uae", "United Arab Emirates"), ("dubai", "United Arab Emirates"), ("japan", "Japan"), ("south korea", "South Korea"),
    ("china", "China"), ("israel", "Israel"), ("brazil", "Brazil"), ("mexico", "Mexico"), ("south africa", "South Africa"),
]


def get_json(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def clean_text(value) -> str:
    if not value:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_loc_text(loc) -> str:
    if isinstance(loc, dict):
        return clean_text(loc.get("name") or loc.get("location") or loc.get("city") or "")
    if isinstance(loc, list):
        return ", ".join(filter(None, (get_loc_text(x) for x in loc)))
    return clean_text(loc)


def country_region(location: str, remote: bool):
    low = location.lower()
    for alias, country in COUNTRY_ALIASES:
        if alias in low:
            lat, lon, cont = REGION_CENTERS[country]
            return country, country, cont, lat, lon
    if any(x in low for x in ("emea", "europe, middle east", "europe / middle east")):
        lat, lon, cont = REGION_CENTERS["Europe"]
        return "EMEA (country not specified)", "Europe / EMEA", cont, lat, lon
    if "north america" in low or "americas" in low:
        lat, lon, cont = REGION_CENTERS["North America"]
        return "North America (country not specified)", "North America", cont, lat, lon
    if any(x in low for x in ("apac", "asia pacific", "asia-pacific")):
        lat, lon, cont = REGION_CENTERS["Asia Pacific"]
        return "Asia Pacific (country not specified)", "Asia Pacific", cont, lat, lon
    if remote or any(x in low for x in ("worldwide", "anywhere", "global")):
        lat, lon, cont = REGION_CENTERS["Worldwide"]
        return "Remote / location not specified", "Worldwide", cont, lat, lon
    lat, lon, cont = REGION_CENTERS["Worldwide"]
    return (location or "Location not specified"), "Unspecified", cont, lat, lon


def is_remote(text: str) -> str:
    low = text.lower()
    if "hybrid" in low:
        return "Hybrid (as listed)"
    if any(w in low for w in ("remote", "work from anywhere", "distributed", "home-based")):
        return "Remote (as listed)"
    if any(w in low for w in ("on-site", "onsite", "in office", "in-office")):
        return "On-site (as listed)"
    return "Not specified"


def role_family(title: str, desc: str) -> str:
    t = (title + " " + desc[:1800]).lower()
    if any(k in t for k in ("scada", "opc ua", "industrial automation", "operational technology", "ot security", "plc")):
        return "Industrial IoT / OT"
    if any(k in t for k in ("embedded", "firmware", "rtos", "device driver")):
        return "IoT / Embedded"
    if any(k in t for k in ("connectivity", "lorawan", "mqtt", "telematics", "wireless", "cellular")):
        return "IoT Connectivity / Operations"
    if any(k in t for k in ("solutions engineer", "field applications", "solution architect", "presales", "pre-sales")):
        return "IoT Solutions / Architecture"
    if any(k in t for k in ("platform", "cloud", "telemetry", "edge computing", "data pipeline")):
        return "IoT Platform / Cloud"
    return "IoT Engineering"


def seniority(title: str) -> str:
    t = title.lower()
    if any(x in t for x in ("principal", "staff", "distinguished", "architect")):
        return "Staff / Principal / Architect"
    if any(x in t for x in ("senior", "sr.", "lead", "manager")):
        return "Senior / Lead"
    if any(x in t for x in ("junior", "entry level", "graduate", "intern")):
        return "Entry / Junior"
    return "Engineer / unspecified level"


def skills_for(text: str, keywords: list[str]) -> list[str]:
    low = text.lower()
    aliases = [("python", "Python"), ("azure", "Azure"), ("aws", "AWS"), ("mqtt", "MQTT"),
               ("lorawan", "LoRaWAN"), ("scada", "SCADA"), ("opc ua", "OPC UA"), ("sparkplug b", "Sparkplug B"),
               ("telemetry", "Telemetry"), ("embedded", "Embedded"), ("firmware", "Firmware"),
               ("kubernetes", "Kubernetes"), ("sql", "SQL"), ("iot", "IoT"), ("industrial", "Industrial IoT"),
               ("connectivity", "Connectivity"), ("edge", "Edge Computing"), ("ev charging", "EV Charging"),
               ("modbus", "Modbus"), ("opc", "OPC"), ("c++", "C++"), ("linux", "Linux"),
               ("network", "Networking"), ("cloud", "Cloud")]
    out=[]
    for needle, label in aliases:
        if needle in low and label not in out:
            out.append(label)
    return out[:8] or ["IoT", "Engineering"]


def score(title: str, desc: str, remote: str, location: str) -> int:
    text = (title + " " + desc[:3000]).lower()
    s = 3
    if any(k in text for k in ("iot", "iiot", "mqtt", "lorawan", "scada", "opc ua", "industrial automation", "telemetry", "telematics", "device connectivity")):
        s += 1
    if any(k in text for k in ("senior", "lead", "architect", "platform", "solutions engineer", "connectivity")):
        s += 1
    if "remote" in remote.lower() and any(k in location.lower() for k in ("worldwide", "global", "anywhere", "india", "emea", "apac")):
        s += 0
    return min(5, s)


def salary_from_text(text: str) -> str:
    """Return a salary range only when an explicit currency/range appears in source text."""
    plain = clean_text(text)
    patterns = [
        r"(?i)(?:USD|US\$|\$)\s?\d[\d,.]*(?:\s?(?:k|K))?\s*(?:-|–|to)\s*(?:(?:USD|US\$|\$)\s?)?\d[\d,.]*(?:\s?(?:k|K))?",
        r"(?i)(?:INR|₹)\s?\d[\d,.]*(?:\s?(?:lpa|lakh|crore))?\s*(?:-|–|to)\s*(?:(?:INR|₹)\s?)?\d[\d,.]*(?:\s?(?:lpa|lakh|crore))?",
        r"(?i)(?:GBP|£|EUR|€|AUD|CAD)\s?\d[\d,.]*\s*(?:-|–|to)\s*(?:(?:GBP|£|EUR|€|AUD|CAD)\s?)?\d[\d,.]*",
    ]
    for pattern in patterns:
        match = re.search(pattern, plain)
        if match:
            return match.group(0)[:120]
    return "Not disclosed in public feed"


def normalize(company: str, title: str, location: str, url: str, description: str, source: str, source_id: str, keywords: list[str]):
    combined = f"{title} {description}"
    low = combined.lower()
    if not any(k.lower() in low for k in keywords):
        return None
    if not title or not url:
        return None
    remote = is_remote(location + " " + description[:2500])
    country, region, continent, lat, lon = country_region(location, remote.startswith("Remote"))
    # Never infer country eligibility from a remote label alone.
    eligibility = "Not stated by source; verify work authorization and country eligibility"
    if "india" in location.lower():
        eligibility = "India location listed; confirm role-specific eligibility"
    elif any(k in location.lower() for k in ("worldwide", "global", "anywhere")):
        eligibility = "Worldwide wording found; confirm India eligibility and employment arrangement"
    elif "remote" in remote.lower():
        eligibility = "Remote wording found; permitted countries not established"
    description_short = clean_text(description)[:320]
    return {
        "id": f"{source}-{source_id}", "title": title, "company": company,
        "region": region, "country": country, "city": location or "Not specified",
        "continent": continent, "lat": lat, "lon": lon, "workModel": remote,
        "roleFamily": role_family(title, description), "seniority": seniority(title),
        "salary": salary_from_text(combined), "eligibility": eligibility,
        "status": "Live public ATS listing — recheck before applying", "applyUrl": url,
        "skills": skills_for(combined, keywords), "fit": score(title, description, remote, location),
        "note": description_short or f"Published listing retrieved from the {source.title()} public job feed.",
        "source": source.title(), "sourceType": "live_api", "sourceId": str(source_id),
        "lastSeenAt": datetime.now(timezone.utc).isoformat(timespec="seconds")
    }


def greenhouse(cfg, keywords):
    board = cfg["board"]
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(board)}/jobs?content=true")
    for item in data.get("jobs", []):
        loc = get_loc_text(item.get("location"))
        yield normalize(cfg["company"], clean_text(item.get("title")), loc, item.get("absolute_url", ""), item.get("content", ""), "greenhouse", item.get("id", ""), keywords)


def lever(cfg, keywords):
    site = cfg["site"]
    data = get_json(f"https://api.lever.co/v0/postings/{urllib.parse.quote(site)}?mode=json&limit=500")
    for item in data if isinstance(data, list) else []:
        cats = item.get("categories") or {}
        loc = get_loc_text(cats.get("allLocations") or cats.get("location") or item.get("workplaceType") or "")
        desc = " ".join(clean_text(item.get(k, "")) for k in ("description", "additional", "lists"))
        yield normalize(cfg["company"], clean_text(item.get("text")), loc, item.get("hostedUrl", ""), desc, "lever", item.get("id", ""), keywords)


def ashby(cfg, keywords):
    board = cfg["board"]
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{urllib.parse.quote(board)}?includeCompensation=true")
    for item in data.get("jobs", []) if isinstance(data, dict) else []:
        loc = get_loc_text(item.get("location"))
        if item.get("isRemote") and "remote" not in loc.lower():
            loc = (loc + " · Remote").strip(" ·")
        desc = clean_text(item.get("descriptionHtml") or item.get("description") or "")
        job = normalize(cfg["company"], clean_text(item.get("title")), loc, item.get("jobUrl") or item.get("applyUrl", ""), desc, "ashby", item.get("id") or item.get("jobId", ""), keywords)
        if job:
            comp = clean_text(item.get("compensationTierSummary") or item.get("compensation") or "")
            if comp:
                job["salary"] = comp[:160]
        yield job


def main():
    cfg = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    keywords = cfg.get("keywords", [])
    jobs, errors, successes = {}, [], {"greenhouse": 0, "lever": 0, "ashby": 0}
    for source_name, fetcher in (("greenhouse", greenhouse), ("lever", lever), ("ashby", ashby)):
        for source_cfg in cfg.get(source_name, []):
            try:
                count = 0
                for job in fetcher(source_cfg, keywords):
                    if job:
                        # Preserve the first matching posting if it appears in multiple ATS boards.
                        key = (job["company"].lower(), re.sub(r"\W+", " ", job["title"].lower()).strip(), job["applyUrl"].rstrip("/").lower())
                        jobs[key] = job
                        count += 1
                successes[source_name] += 1
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
                errors.append({"source": source_name, "company": source_cfg.get("company"), "board": source_cfg.get("board") or source_cfg.get("site"), "error": str(exc)[:180]})
            except Exception as exc:
                errors.append({"source": source_name, "company": source_cfg.get("company"), "board": source_cfg.get("board") or source_cfg.get("site"), "error": str(exc)[:180]})
            time.sleep(0.15)
    output = sorted(jobs.values(), key=lambda j: (-int(j["fit"]), j["company"].lower(), j["title"].lower()))
    # Do not silently replace a useful prior feed with an empty result if all endpoints failed.
    retained_previous_data = False
    if not output and errors:
        old = DATA / "jobs.json"
        if old.exists():
            try:
                previous = json.loads(old.read_text(encoding="utf-8"))
                if previous:
                    output = previous
                    retained_previous_data = True
            except Exception:
                pass
    (DATA / "jobs.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totalLiveListings": sum(1 for j in output if j.get("sourceType") == "live_api"), "retainedPreviousDataAfterFeedErrors": retained_previous_data, "successfulBoards": successes,
        "configuredBoards": {k: len(cfg.get(k, [])) for k in ("greenhouse", "lever", "ashby")},
        "boardsWithErrors": errors,
        "note": "Only published public listings matching the configured IoT/industrial/connected-device keywords are included. A missing result does not prove that a company has no relevant jobs. Eligibility and work model are shown only when supported by listing text."
    }
    (DATA / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(output)} matching jobs ({sum(1 for j in output if j.get('sourceType') == 'live_api')} live API listings); board success counts: {successes}; errors: {len(errors)}")

if __name__ == "__main__":
    main()
