# Global IoT Career Radar

A map-first job finder tailored to IoT / IIoT / industrial connectivity, cloud IoT, EV charging, telemetry, SCADA / OT, embedded systems and IoT solutions roles. It is designed around an engineer based in Kerala, India who prioritizes India-eligible remote work and international opportunities.

## What is integrated

- **Greenhouse public job boards**: public published jobs via `boards-api.greenhouse.io`.
- **Lever public postings**: public postings via `api.lever.co`.
- **Ashby public job boards**: public listings via `api.ashbyhq.com`.
- **Public remote-job feeds**: Remote OK JSON, Jobicy public API (cursor pagination), Himalayas public API (cursor pagination), and the official We Work Remotely RSS feed. Canonical source links and attribution are retained on each card.
- **Search-link integrations**: LinkedIn Jobs, Indeed (including India), Arc and Cutshort. These open source-native or targeted search results rather than scraping restricted pages.
- **Scheduled ingestion**: GitHub Actions runs every six hours and can also be started manually. It normalizes job cards, deduplicates records, filters for IoT / industrial / connected-device keywords, updates `data/jobs.json` and writes `data/metadata.json`.
- **Static web app**: interactive world map, region/role/work-model filters, keyword search, saved jobs in browser localStorage, CSV export, direct employer application links.
- **No API secrets required** for these public board endpoints. The app does not submit applications or store resumes.

## Important coverage limits

There is no single universal, free, public API for every job website. The configured ATS boards in `data/sources.json` are a curated seed list, not all employers in the world. Some board names may no longer exist or may be private/unavailable; those endpoints are skipped and recorded in `data/metadata.json`. Add more public Greenhouse board tokens, Lever site names, and Ashby board slugs to expand coverage. LinkedIn, Indeed, Arc and Cutshort are linked through search pages because this project does not have authorized bulk-search API access. It does not bypass logins, paywalls, robots rules or access controls. The remote feeds are fetched with bounded pagination, filtered for configured IoT/industrial/connectivity keywords, and deduplicated.

The first packaged `data/jobs.json` contains previously gathered research leads; some may be expired. After deployment, run **Actions → Refresh global IoT job feeds → Run workflow** for the first live refresh. The refresh script builds a current list from currently returned public API/RSS matches; the visible search links supplement these feeds rather than pretending every board is fully indexed. If all feeds fail, it avoids overwriting a previously successful live feed with an empty result.

## Local run

Python 3.10+ is required for the ingestion script. For the site only, open `index.html` or run:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000`. The cards are paginated 50 at a time (there is no 10-job UI cap). A local browser does not run the scheduled refresh; run `python scripts/update_jobs.py` manually if your environment has internet access. Run the offline adapter tests with `python -m unittest discover -s tests -v`.

## Publish on GitHub Pages

This project is intended to stay in your existing `roshanmthomas/jobs-portal` repository. Test locally first, review the changed files, and then commit/push them from your local checkout only when you are ready. Do not create a separate repository just for these feed changes.

1. In the existing repository, open **Settings → Pages → Build and deployment → Source** and select **GitHub Actions** if it is not already selected.
2. Open **Actions**, choose **Refresh global IoT job feeds**, and run it once. Review the log for successful and unavailable boards.
3. The existing **Deploy Global IoT Career Radar** workflow publishes the static website on pushes to `main`.

The job refresh workflow needs repository `contents: write` permission to commit the generated JSON. If the run fails on permissions, go to **Settings → Actions → General → Workflow permissions** and allow read/write permissions. Do not put private API keys or personal information in the public repository.

## Feed source documentation

- Greenhouse Job Board API: https://support.greenhouse.io/hc/en-us/articles/10568627186203-Greenhouse-API-overview
- Lever Postings API: https://github.com/lever/postings-api
- Remote OK public JSON: https://remoteok.com/api
- Jobicy Remote Jobs API: https://jobicy.com/jobs-rss-feed
- Himalayas Remote Jobs API: https://himalayas.app/docs/remote-jobs-api
- We Work Remotely public RSS: https://weworkremotely.com/remote-job-rss-feed
- GitHub Pages + Actions deployment: https://docs.github.com/en/get-started/start-your-journey/deploying-your-website-automatically

## Accuracy and privacy

Only published public ATS listings matching the configured keyword list are included in the live feed. Search terms can miss relevant jobs and may include false positives. Remote labels do not automatically mean a role can legally hire from India. Salary is shown only when explicitly provided; otherwise it is marked undisclosed. Map markers use broad location/region centroids rather than exact office coordinates. Saved jobs stay in the current browser's localStorage; there is no account or cross-device sync.

Independent project, not affiliated with any employer or job-board vendor.
