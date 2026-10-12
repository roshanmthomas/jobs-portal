#!/usr/bin/env python3
"""Refresh the public IoT job feed from supported public ATS job-board endpoints.
No credentials are used. Unsupported/unreachable boards are skipped and recorded in metadata.
"""
from __future__ import annotations
import html
import json
import re
import time
import xml.etree.ElementTree as ET
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HEADERS = {"User-Agent": "Global-IoT-Career-Radar/1.1 (public job discovery; source attribution preserved)", "Accept": "application/json, application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"}

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


def get_text(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def get_json(url: str):
    return json.loads(get_text(url))


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


def normalize(company: str, title: str, location: str, url: str, description: str, source: str, source_id: str, keywords: list[str], source_url: str | None = None):
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
        "status": "Live public listing — recheck before applying", "applyUrl": url, "sourceUrl": source_url or url,
        "skills": skills_for(combined, keywords), "fit": score(title, description, remote, location),
        "note": description_short or f"Published listing retrieved from the {source.title()} public job feed.",
        "source": source.title(), "sourceType": "public_feed" if source in ("remoteok", "jobicy", "himalayas", "weworkremotely") else "live_api", "sourceId": str(source_id),
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



def remote_location(value) -> str:
    if isinstance(value, list):
        return ", ".join(clean_text(v) for v in value if clean_text(v))
    if isinstance(value, dict):
        return get_loc_text(value)
    return clean_text(value)


def remote_ok(cfg, keywords):
    """Remote OK public JSON feed; preserve the original Remote OK listing URL."""
    url = cfg.get("url", "https://remoteok.com/api")
    data = get_json(url)
    if not isinstance(data, list):
        raise ValueError("Remote OK response was not a JSON list")
    for item in data:
        if not isinstance(item, dict) or not item.get("position"):
            continue  # the feed may begin with a metadata/notice object
        title = clean_text(item.get("position"))
        company = clean_text(item.get("company") or "Remote OK employer")
        location = clean_text(item.get("location") or item.get("candidate_required_location") or "Remote / location not specified")
        desc = clean_text(item.get("description") or "")
        listing_url = item.get("url") or item.get("apply_url") or ""
        yield normalize(company, title, location, listing_url, desc, "remoteok", item.get("id") or listing_url, keywords, listing_url)


def jobicy(cfg, keywords):
    """Jobicy public API, with bounded cursor pagination and source attribution."""
    base = cfg.get("url", "https://jobicy.com/api/v2/remote-jobs")
    max_pages = max(1, min(int(cfg.get("max_pages", 3)), 10))
    params = {"count": min(200, max(1, int(cfg.get("page_size", 200))))}
    cursor = None
    for _ in range(max_pages):
        query = dict(params)
        if cursor:
            query["cursor"] = cursor
        url = base + "?" + urllib.parse.urlencode(query)
        data = get_json(url)
        if not isinstance(data, dict) or data.get("success") is False:
            raise ValueError("Jobicy returned an invalid or unsuccessful response")
        for item in data.get("jobs", []):
            if not isinstance(item, dict):
                continue
            title = clean_text(item.get("jobTitle"))
            company = clean_text(item.get("companyName") or "Jobicy employer")
            location = clean_text(item.get("jobGeo") or "Remote / location not specified")
            desc = clean_text(item.get("jobDescription") or item.get("jobExcerpt") or "")
            listing_url = item.get("url") or ""
            salary = ""
            lo, hi, currency = item.get("salaryMin"), item.get("salaryMax"), item.get("salaryCurrency")
            period = clean_text(item.get("salaryPeriod") or "yearly")
            if lo is not None or hi is not None:
                salary = f"{currency or ''} {lo if lo is not None else '?'}–{hi if hi is not None else '?'} ({period})".strip()
            job = normalize(company, title, location, listing_url, desc, "jobicy", item.get("id") or listing_url, keywords, listing_url)
            if job:
                if salary:
                    job["salary"] = salary[:160]
                job["publishedAt"] = clean_text(item.get("pubDate"))
                yield job
        cursor = data.get("nextCursor")
        if not cursor:
            break
        time.sleep(0.35)


def himalayas(cfg, keywords):
    """Himalayas public remote jobs API; preserve attribution and source listing links."""
    base = cfg.get("url", "https://himalayas.app/jobs/api")
    max_pages = max(1, min(int(cfg.get("max_pages", 10)), 20))
    cursor = None
    for _ in range(max_pages):
        params = {"limit": min(20, max(1, int(cfg.get("page_size", 20))))}
        if cursor:
            params["cursor"] = cursor
        data = get_json(base + "?" + urllib.parse.urlencode(params))
        if not isinstance(data, dict):
            raise ValueError("Himalayas response was not a JSON object")
        for item in data.get("jobs", []):
            if not isinstance(item, dict):
                continue
            title = clean_text(item.get("title"))
            company = clean_text(item.get("companyName") or "Himalayas employer")
            restrictions = item.get("locationRestrictions") or []
            if isinstance(restrictions, list):
                location = ", ".join(clean_text(x) for x in restrictions if clean_text(x))
            else:
                location = clean_text(restrictions)
            if not location:
                location = "Remote / location not specified"
            desc = clean_text(item.get("description") or item.get("excerpt") or "")
            apply_url = item.get("applicationLink") or ""
            # The public schema's guid may be a canonical source URL. If not, link to Himalayas' job index.
            guid = clean_text(item.get("guid") or "")
            source_url = guid if guid.startswith(("https://", "http://")) else "https://himalayas.app/jobs"
            job = normalize(company, title, location, apply_url or source_url, desc, "himalayas", item.get("guid") or item.get("id") or apply_url or title, keywords, source_url)
            if job:
                salary_min, salary_max = item.get("minSalary"), item.get("maxSalary")
                currency = clean_text(item.get("currency") or "")
                period = clean_text(item.get("salaryPeriod") or "annual")
                if salary_min is not None or salary_max is not None:
                    job["salary"] = f"{currency} {salary_min if salary_min is not None else '?'}–{salary_max if salary_max is not None else '?'} ({period})".strip()[:160]
                job["employmentType"] = clean_text(item.get("employmentType") or "")
                job["publishedAt"] = clean_text(item.get("pubDate") or "")
                yield job
        cursor = data.get("nextCursor")
        if not cursor:
            break
        time.sleep(0.35)


def we_work_remotely(cfg, keywords):
    """Official public RSS feed. WWR asks consumers to attribute links back to WWR."""
    url = cfg.get("url", "https://weworkremotely.com/remote-jobs.rss")
    root = ET.fromstring(get_text(url))
    for item in root.findall(".//item"):
        title_line = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        description = clean_text(item.findtext("description") or "")
        category = " ".join(clean_text(x.text or "") for x in item.findall("category"))
        # WWR item titles are commonly "Company: Role"; split only once.
        if ":" in title_line:
            company, title = [clean_text(x) for x in title_line.split(":", 1)]
        else:
            company, title = "We Work Remotely employer", title_line
        location = "Remote / location not specified"
        text_blob = " ".join((description, category, title_line))
        job = normalize(company, title, location, link, text_blob, "weworkremotely", link, keywords, link)
        if job:
            job["publishedAt"] = clean_text(item.findtext("pubDate") or "")
            yield job

def main():
    cfg = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    keywords = cfg.get("keywords", [])
    jobs, errors = {}, []
    successes = {k: 0 for k in ("greenhouse", "lever", "ashby", "remoteok", "jobicy", "himalayas", "weworkremotely")}
    configured = {}
    fetchers = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
    for source_name, fetcher in fetchers.items():
        source_cfgs = cfg.get(source_name, [])
        configured[source_name] = len(source_cfgs)
        for source_cfg in source_cfgs:
            try:
                found = 0
                for job in fetcher(source_cfg, keywords):
                    if job:
                        key = (job["company"].lower(), re.sub(r"\W+", " ", job["title"].lower()).strip(), job["applyUrl"].rstrip("/").lower())
                        jobs[key] = job
                        found += 1
                successes[source_name] += 1
            except Exception as exc:
                errors.append({"source": source_name, "company": source_cfg.get("company"), "board": source_cfg.get("board") or source_cfg.get("site"), "error": str(exc)[:180]})
            time.sleep(0.15)

    for source_name, fetcher in (("remoteok", remote_ok), ("jobicy", jobicy), ("himalayas", himalayas), ("weworkremotely", we_work_remotely)):
        source_cfg = cfg.get(source_name)
        configured[source_name] = 1 if source_cfg else 0
        if not source_cfg:
            continue
        try:
            for job in fetcher(source_cfg, keywords):
                if job:
                    key = (job["company"].lower(), re.sub(r"\W+", " ", job["title"].lower()).strip(), job["applyUrl"].rstrip("/").lower())
                    # Prefer the canonical listing URL and preserve multiple source labels for duplicates.
                    existing = jobs.get(key)
                    if existing:
                        existing_sources = set(existing.get("sourceNames", [existing.get("source", "")]))
                        existing_sources.add(job.get("source", ""))
                        existing["sourceNames"] = sorted(x for x in existing_sources if x)
                        continue
                    jobs[key] = job
            successes[source_name] += 1
        except Exception as exc:
            errors.append({"source": source_name, "company": source_cfg.get("company"), "board": source_cfg.get("url", source_name), "error": str(exc)[:180]})
        time.sleep(0.25)

    output = sorted(jobs.values(), key=lambda j: (-int(j.get("fit", 0)), -int(bool(j.get("publishedAt"))), j["company"].lower(), j["title"].lower()))
    retained_previous_data = False
    # Keep the existing dataset if all sources fail or no source returned a single relevant result.
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
        "totalListings": len(output),
        "totalLiveListings": sum(1 for j in output if j.get("sourceType") == "live_api" or j.get("sourceType") == "public_feed"),
        "retainedPreviousDataAfterFeedErrors": retained_previous_data,
        "successfulSources": successes,
        "configuredSources": configured,
        "boardsWithErrors": errors,
        "note": "Listings are filtered for configured IoT/industrial/connected-device keywords and deduplicated. Search-link integrations are provided for sources without an authorized public feed. Always verify source listing, country eligibility and work authorization before applying.",
        "attribution": {"jobicy": "https://jobicy.com", "himalayas": "https://himalayas.app", "weworkremotely": "https://weworkremotely.com", "remoteok": "https://remoteok.com"}
    }
    (DATA / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(output)} matching jobs ({meta['totalLiveListings']} live/public-feed listings); successful sources: {successes}; errors: {len(errors)}")

if __name__ == "__main__":
    main()
