from datetime import date
from pathlib import Path
from unittest.mock import patch
import unittest

import test_helpers  # noqa: F401

from config import Config
from pipeline import build_latest_pointer, build_manifest, build_refresh_windows


class PipelineTests(unittest.TestCase):
    def build_config(self) -> Config:
        return Config(
            start_season=2024,
            end_season=2024,
            output_dir=Path("/tmp/output"),
            dataset_prefix="baseball",
            incremental_mode=True,
            trailer_months=1,
            sample_mode=False,
            sample_start_date=None,
            sample_end_date=None,
            sample_max_rows=20000,
            sample_max_windows=2,
            sample_random_state=42,
            spaces_bucket=None,
            spaces_region=None,
            spaces_endpoint=None,
            spaces_access_key_id=None,
            spaces_secret_access_key=None,
        )

    def test_build_manifest_includes_window_bounds(self):
        config = self.build_config()
        manifest = build_manifest(config, "snap-1", "2024-04-01", "2024-04-30", 10, 2, 1, 3, 2)
        self.assertEqual(manifest["source"]["window_start_date"], "2024-04-01")
        self.assertEqual(manifest["source"]["window_end_date"], "2024-04-30")
        self.assertEqual(manifest["outputs"]["detail"]["rows"], 10)
        self.assertIn("team_season_metrics", manifest["outputs"]["aggregates"])
        self.assertIn("team_career_metrics", manifest["outputs"]["aggregates"])
        self.assertEqual(manifest["outputs"]["aggregates"]["team_season_rows"], 3)
        self.assertEqual(manifest["outputs"]["aggregates"]["team_career_rows"], 2)

    def test_build_latest_pointer_includes_manifest_path(self):
        config = self.build_config()
        pointer = build_latest_pointer(config, "snap-1", "baseball/snapshots/snap-1/manifest.json", "2024-04-01", "2024-04-30")
        self.assertEqual(pointer["manifest_path"], "baseball/snapshots/snap-1/manifest.json")
        self.assertEqual(pointer["window_end_date"], "2024-04-30")

    def test_build_refresh_windows_full_first_pass_when_no_latest(self):
        config = self.build_config()
        with patch("pipeline.latest_processed_end_date", return_value=None):
            windows, start_date, end_date = build_refresh_windows(config, client=None)

        self.assertEqual(windows[0], (2024, 1, "2024-01-01", "2024-01-31"))
        self.assertEqual(start_date, "2024-01-01")
        self.assertEqual(end_date, "2024-12-31")

    def test_build_refresh_windows_incremental_adds_trailer_and_missing_months(self):
        config = self.build_config()
        latest_pointer = {
            "detail_path": "baseball/snapshots/snap-1/detail/",
            "manifest_path": "baseball/snapshots/snap-1/manifest.json",
        }

        with patch("pipeline.latest_processed_end_date", return_value="2024-03-31"), \
             patch("pipeline.read_latest_pointer", return_value=latest_pointer), \
             patch("pipeline.list_local_captured_months", return_value={(2024, 1), (2024, 2), (2024, 3)}):
            windows, start_date, end_date = build_refresh_windows(config, client=None)

        self.assertIn((2024, 2, "2024-02-01", "2024-02-29"), windows)
        self.assertIn((2024, 4, "2024-04-01", "2024-04-30"), windows)
        self.assertNotIn((2024, 1, "2024-01-01", "2024-01-31"), windows)
        self.assertEqual(start_date, "2024-02-01")
        self.assertEqual(end_date, date.today().strftime("%Y-%m-%d"))


if __name__ == "__main__":
    unittest.main()
