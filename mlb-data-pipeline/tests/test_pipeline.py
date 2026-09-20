from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
import unittest

import test_helpers  # noqa: F401

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    pd = None

from config import Config
from pipeline import add_career_source_column, build_latest_pointer, build_manifest, build_refresh_windows, merge_season_aggregates, preflight_storage_target


class PipelineTests(unittest.TestCase):
    def build_config(self) -> Config:
        return Config(
            start_season=2024,
            end_season=2024,
            output_dir=Path("/tmp/output"),
            dataset_prefix="baseball",
            upload_enabled=False,
            incremental_mode=True,
            require_existing_snapshot=False,
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
        mapping_quality = {"mapped_player_ids_in_output": 10, "unmapped_player_ids_in_output": 2}
        manifest = build_manifest(
            config,
            "snap-1",
            "2024-04-01",
            "2024-04-30",
            ["statcast", "lahman"],
            mapping_quality,
            10,
            2,
            1,
            3,
            2,
        )
        self.assertEqual(manifest["source"]["window_start_date"], "2024-04-01")
        self.assertEqual(manifest["source"]["window_end_date"], "2024-04-30")
        self.assertEqual(manifest["source"]["datasets"], ["statcast", "lahman"])
        self.assertEqual(manifest["source"]["lahman_mapping_quality"], mapping_quality)
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

    def test_build_refresh_windows_requires_existing_snapshot_when_configured(self):
        config = self.build_config()
        config.require_existing_snapshot = True

        with patch("pipeline.latest_processed_end_date", return_value=None):
            with self.assertRaisesRegex(ValueError, "requires an existing snapshot"):
                build_refresh_windows(config, client=None)

    def test_build_refresh_windows_rejects_no_statcast_coverage_without_lahman(self):
        config = self.build_config()
        config.start_season = 2010
        config.end_season = 2014
        config.statcast_start_season = 2015
        config.lahman_enabled = False

        with self.assertRaisesRegex(ValueError, "No Statcast windows available"):
            build_refresh_windows(config, client=None)

    def test_build_refresh_windows_allows_pre_statcast_range_with_lahman_enabled(self):
        config = self.build_config()
        config.start_season = 2010
        config.end_season = 2014
        config.statcast_start_season = 2015
        config.lahman_enabled = True

        windows, start_date, end_date = build_refresh_windows(config, client=None)
        self.assertEqual(windows, [])
        self.assertEqual(start_date, "2010-01-01")
        self.assertEqual(end_date, "2014-12-31")

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

    def test_preflight_storage_target_rejects_partial_spaces_config(self):
        config = self.build_config()
        config.upload_enabled = True
        config.spaces_bucket = "baseball-bucket"

        with self.assertRaisesRegex(ValueError, "Incomplete Spaces configuration"):
            preflight_storage_target(config, client=None)

    def test_preflight_storage_target_checks_bucket_and_reports_latest_pointer_state(self):
        config = self.build_config()
        config.spaces_bucket = "baseball-bucket"
        config.spaces_region = "nyc3"
        config.spaces_endpoint = "https://nyc3.digitaloceanspaces.com"
        config.spaces_access_key_id = "key"
        config.spaces_secret_access_key = "secret"
        config.upload_enabled = True
        client = Mock()

        with patch("pipeline.read_latest_pointer", return_value=None):
            preflight = preflight_storage_target(config, client)

        client.head_bucket.assert_called_once_with(Bucket="baseball-bucket")
        self.assertEqual(preflight["mode"], "spaces")
        self.assertFalse(preflight["latest_snapshot_present"])
        self.assertIsNone(preflight["latest_snapshot_id"])

    def test_preflight_storage_target_reports_existing_latest_pointer(self):
        config = self.build_config()
        config.spaces_bucket = "baseball-bucket"
        config.spaces_region = "nyc3"
        config.spaces_endpoint = "https://nyc3.digitaloceanspaces.com"
        config.spaces_access_key_id = "key"
        config.spaces_secret_access_key = "secret"
        config.upload_enabled = True
        client = Mock()
        latest_pointer = {"snapshot_id": "snap-123"}

        with patch("pipeline.read_latest_pointer", return_value=latest_pointer):
            preflight = preflight_storage_target(config, client)

        client.head_bucket.assert_called_once_with(Bucket="baseball-bucket")
        self.assertTrue(preflight["latest_snapshot_present"])
        self.assertEqual(preflight["latest_snapshot_id"], "snap-123")

    def test_preflight_storage_target_stays_local_when_upload_disabled(self):
        config = self.build_config()
        config.spaces_bucket = "baseball-bucket"
        config.spaces_region = "nyc3"
        config.spaces_endpoint = "https://nyc3.digitaloceanspaces.com"
        config.spaces_access_key_id = "key"
        config.spaces_secret_access_key = "secret"

        preflight = preflight_storage_target(config, client=None)

        self.assertEqual(preflight["mode"], "local")
        self.assertFalse(preflight["upload_enabled"])

    @unittest.skipIf(pd is None, "pandas is not installed in this environment")
    def test_merge_season_aggregates_prefers_statcast(self):
        statcast = pd.DataFrame(
            [
                {"batter": "100", "season": 2015, "hits": 10, "source_system": "statcast"},
            ]
        )
        lahman = pd.DataFrame(
            [
                {"batter": "100", "season": 2015, "hits": 9, "source_system": "lahman"},
            ]
        )

        merged = merge_season_aggregates(statcast, lahman, ["batter", "season"], "statcast_preferred")
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged.iloc[0]["source_system"], "statcast")
        self.assertEqual(int(merged.iloc[0]["hits"]), 10)

    @unittest.skipIf(pd is None, "pandas is not installed in this environment")
    def test_merge_season_aggregates_prefers_lahman_when_configured(self):
        statcast = pd.DataFrame(
            [
                {"batter": "100", "season": 2015, "hits": 10, "source_system": "statcast"},
            ]
        )
        lahman = pd.DataFrame(
            [
                {"batter": "100", "season": 2015, "hits": 9, "source_system": "lahman"},
            ]
        )

        merged = merge_season_aggregates(statcast, lahman, ["batter", "season"], "lahman_preferred")
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged.iloc[0]["source_system"], "lahman")
        self.assertEqual(int(merged.iloc[0]["hits"]), 9)

    @unittest.skipIf(pd is None, "pandas is not installed in this environment")
    def test_add_career_source_column_marks_mixed_rows(self):
        career = pd.DataFrame(
            [
                {"batter": "100", "player_name": "Player A", "career_hits": 20},
                {"batter": "200", "player_name": "Player B", "career_hits": 8},
            ]
        )
        season = pd.DataFrame(
            [
                {"batter": "100", "player_name": "Player A", "season": 2014, "source_system": "lahman"},
                {"batter": "100", "player_name": "Player A", "season": 2015, "source_system": "statcast"},
                {"batter": "200", "player_name": "Player B", "season": 2013, "source_system": "lahman"},
            ]
        )

        with_source = add_career_source_column(career, season, ["batter", "player_name"])
        source_map = {(row["batter"], row["player_name"]): row["source_system"] for _, row in with_source.iterrows()}
        self.assertEqual(source_map[("100", "Player A")], "mixed")
        self.assertEqual(source_map[("200", "Player B")], "lahman")

    @unittest.skipIf(pd is None, "pandas is not installed in this environment")
    def test_add_career_source_column_defaults_unknown_without_source_column(self):
        career = pd.DataFrame(
            [
                {"batter": "100", "player_name": "Player A", "career_hits": 20},
            ]
        )
        season = pd.DataFrame(
            [
                {"batter": "100", "player_name": "Player A", "season": 2015},
            ]
        )

        with_source = add_career_source_column(career, season, ["batter", "player_name"])
        self.assertEqual(with_source.iloc[0]["source_system"], "unknown")


if __name__ == "__main__":
    unittest.main()
