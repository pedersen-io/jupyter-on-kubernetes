import os
from pathlib import Path
from unittest.mock import patch
import unittest

import test_helpers  # noqa: F401

from config import get_config, parse_bool, parse_int


class ConfigTests(unittest.TestCase):
    def test_parse_bool_accepts_common_truthy_values(self):
        for value in ["1", "true", "TRUE", " yes ", "Y", "On"]:
            self.assertTrue(parse_bool(value))

        for value in ["0", "false", "off", "n", ""]:
            self.assertFalse(parse_bool(value))

    def test_parse_int_uses_default_when_missing(self):
        self.assertEqual(parse_int(None, 7), 7)
        self.assertEqual(parse_int("", 7), 7)
        self.assertEqual(parse_int("5", 7), 5)

    def test_get_config_applies_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = get_config()

        self.assertEqual(config.start_season, 2015)
        self.assertEqual(config.statcast_start_season, 2015)
        self.assertEqual(config.output_dir, Path("/tmp/output"))
        self.assertEqual(config.dataset_prefix, "baseball")
        self.assertFalse(config.upload_enabled)
        self.assertTrue(config.incremental_mode)
        self.assertEqual(config.source_overlap_policy, "statcast_preferred")
        self.assertTrue(config.include_detail_dataset)
        self.assertTrue(config.include_aggregate_datasets)
        self.assertTrue(config.include_player_aggregates)
        self.assertTrue(config.include_team_aggregates)
        self.assertTrue(config.include_manager_aggregates)
        self.assertTrue(config.include_season_aggregates)
        self.assertTrue(config.include_career_aggregates)

    def test_get_config_normalizes_overlap_policy_and_mapping_path(self):
        with patch.dict(
            os.environ,
            {
                "SOURCE_OVERLAP_POLICY": "  LAHMAN_PREFERRED  ",
                "LAHMAN_PLAYER_MAPPING_PATH": "/tmp/mapping.csv",
            },
            clear=True,
        ):
            config = get_config()

        self.assertEqual(config.source_overlap_policy, "lahman_preferred")
        self.assertEqual(config.lahman_player_mapping_path, Path("/tmp/mapping.csv"))

    def test_get_config_rejects_invalid_ranges_and_flags(self):
        with patch.dict(os.environ, {"START_SEASON": "2025", "END_SEASON": "2024"}, clear=True):
            with self.assertRaisesRegex(ValueError, "START_SEASON"):
                get_config()

        with patch.dict(os.environ, {"TRAILER_MONTHS": "-1"}, clear=True):
            with self.assertRaisesRegex(ValueError, "TRAILER_MONTHS"):
                get_config()

        with patch.dict(os.environ, {"SOURCE_OVERLAP_POLICY": "unknown"}, clear=True):
            with self.assertRaisesRegex(ValueError, "SOURCE_OVERLAP_POLICY"):
                get_config()

    def test_get_config_requires_sample_dates_as_pair(self):
        with patch.dict(os.environ, {"SAMPLE_START_DATE": "2024-04-01"}, clear=True):
            with self.assertRaisesRegex(ValueError, "must be set together"):
                get_config()

    def test_get_config_rejects_when_all_outputs_disabled(self):
        with patch.dict(
            os.environ,
            {
                "INCLUDE_DETAIL_DATASET": "false",
                "INCLUDE_AGGREGATE_DATASETS": "false",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "At least one of"):
                get_config()

    def test_get_config_rejects_invalid_aggregate_switch_combinations(self):
        with patch.dict(
            os.environ,
            {
                "INCLUDE_AGGREGATE_DATASETS": "true",
                "INCLUDE_PLAYER_AGGREGATES": "false",
                "INCLUDE_TEAM_AGGREGATES": "false",
                "INCLUDE_MANAGER_AGGREGATES": "false",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "requires at least one"):
                get_config()

        with patch.dict(
            os.environ,
            {
                "INCLUDE_AGGREGATE_DATASETS": "true",
                "INCLUDE_SEASON_AGGREGATES": "false",
                "INCLUDE_CAREER_AGGREGATES": "false",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "requires INCLUDE_SEASON_AGGREGATES"):
                get_config()

        with patch.dict(os.environ, {"SAMPLE_END_DATE": "2024-04-30"}, clear=True):
            with self.assertRaisesRegex(ValueError, "must be set together"):
                get_config()


if __name__ == "__main__":
    unittest.main()