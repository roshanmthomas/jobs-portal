"""Offline unit tests for public job-feed adapters; no external network required."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_jobs.py"
spec = importlib.util.spec_from_file_location("update_jobs", SCRIPT)
feed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feed)
KEYWORDS = ["iot", "iiot", "mqtt", "telemetry", "industrial connectivity", "scada", "opc ua", "cloud integration"]


class FeedAdapterTests(unittest.TestCase):
    def test_remote_ok_keeps_source_link_and_skips_metadata_row(self):
        original = feed.get_json
        try:
            feed.get_json = lambda _: [
                {"notice": "metadata"},
                {"id": 123, "position": "Senior IoT Platform Engineer", "company": "Example", "location": "Worldwide", "description": "MQTT telemetry platform", "url": "https://remoteok.com/remote-jobs/123-example"},
            ]
            jobs = list(feed.remote_ok({}, KEYWORDS))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["sourceType"], "public_feed")
            self.assertEqual(jobs[0]["sourceUrl"], "https://remoteok.com/remote-jobs/123-example")
        finally:
            feed.get_json = original

    def test_jobicy_maps_salary_and_listing_attribution(self):
        original = feed.get_json
        try:
            feed.get_json = lambda _: {"success": True, "jobs": [{"id": 42, "jobTitle": "IoT Connectivity Engineer", "companyName": "Example", "jobGeo": "Anywhere", "jobDescription": "MQTT device connectivity and telemetry", "url": "https://jobicy.com/jobs/example", "salaryMin": 100000, "salaryMax": 130000, "salaryCurrency": "USD", "salaryPeriod": "yearly"}], "nextCursor": None}
            jobs = list(feed.jobicy({"max_pages": 1}, KEYWORDS))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["sourceUrl"], "https://jobicy.com/jobs/example")
            self.assertIn("100000", jobs[0]["salary"])
        finally:
            feed.get_json = original

    def test_himalayas_separates_apply_and_source_links(self):
        original = feed.get_json
        try:
            feed.get_json = lambda _: {"jobs": [{"guid": "https://himalayas.app/jobs/example-role", "title": "Industrial IoT Solutions Architect", "companyName": "Example", "locationRestrictions": ["India"], "description": "SCADA and OPC UA cloud integration", "applicationLink": "https://employer.example/apply", "minSalary": 90000, "maxSalary": 120000, "currency": "USD", "salaryPeriod": "annual"}], "nextCursor": None}
            jobs = list(feed.himalayas({"max_pages": 1}, KEYWORDS))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["applyUrl"], "https://employer.example/apply")
            self.assertEqual(jobs[0]["sourceUrl"], "https://himalayas.app/jobs/example-role")
        finally:
            feed.get_json = original

    def test_we_work_remotely_rss_parsing_and_attribution(self):
        original = feed.get_text
        try:
            feed.get_text = lambda _: '<rss><channel><item><title>Example Co: Senior MQTT Engineer</title><link>https://weworkremotely.com/remote-jobs/example</link><description>IoT telemetry platform with MQTT</description></item></channel></rss>'
            jobs = list(feed.we_work_remotely({}, KEYWORDS))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["company"], "Example Co")
            self.assertEqual(jobs[0]["sourceUrl"], "https://weworkremotely.com/remote-jobs/example")
        finally:
            feed.get_text = original

    def test_irrelevant_jobs_are_filtered_out(self):
        job = feed.normalize("Example", "Graphic Designer", "Remote", "https://example.com/job", "Design illustrations", "jobicy", "1", KEYWORDS)
        self.assertIsNone(job)


if __name__ == "__main__":
    unittest.main()
