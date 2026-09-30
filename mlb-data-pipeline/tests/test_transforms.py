from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_helpers  # noqa: F401

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    pd = None

from transforms import (
    build_detail_storage_tables,
    build_player_dimension_table,
    build_player_season_aggregates,
    build_team_season_aggregates,
    fetch_detail_dataframe,
    normalize_detail_dataframe,
)
from transforms import _format_window_label, _preview_windows, _summarize_window_years, _window_queue_entries


@unittest.skipIf(pd is None, "pandas is not installed in this environment")
class TransformTests(unittest.TestCase):
    def test_window_summary_helpers(self):
        windows = [
            (2024, 1, "2024-01-01", "2024-01-31"),
            (2024, 2, "2024-02-01", "2024-02-29"),
            (2025, 1, "2025-01-01", "2025-01-31"),
        ]

        self.assertEqual(_format_window_label(windows[0]), "2024-01")
        self.assertEqual(_preview_windows(windows, limit=2), "2024-01, 2024-02, ... (+1 more)")
        self.assertEqual(_summarize_window_years(windows), "2024(2), 2025(1)")
        entries = dict(_window_queue_entries(windows))
        self.assertEqual(entries["years"], "2024(2), 2025(1)")
        self.assertEqual(entries["planned"], "3")
        self.assertEqual(entries["first"], "2024-01")
        self.assertEqual(entries["last"], "2025-01")

    def test_fetch_detail_dataframe_suppresses_third_party_noise_for_pretty_local_output(self):
        config = SimpleNamespace(
            pretty_local_output=True,
            sample_mode=False,
            sample_max_rows=20000,
            sample_random_state=42,
        )

        with patch("transforms._fetch_statcast_window", return_value=pd.DataFrame()) as fetch_window:
            fetch_detail_dataframe(config, [(2024, 3, "2024-03-01", "2024-03-31")])

        fetch_window.assert_called_once_with("2024-03-01", "2024-03-31", suppress_noise=True)

    def test_fetch_detail_dataframe_leaves_noise_handling_off_for_plain_logs(self):
        config = SimpleNamespace(
            pretty_local_output=False,
            sample_mode=False,
            sample_max_rows=20000,
            sample_random_state=42,
        )

        with patch("transforms._fetch_statcast_window", return_value=pd.DataFrame()) as fetch_window:
            fetch_detail_dataframe(config, [(2024, 3, "2024-03-01", "2024-03-31")])

        fetch_window.assert_called_once_with("2024-03-01", "2024-03-31", suppress_noise=False)

    def test_normalize_detail_dataframe_prunes_columns_and_compacts_types(self):
        detail_df = pd.DataFrame(
            [
                {
                    "game_date": "2024-03-28",
                    "game_pk": "746321",
                    "at_bat_number": "12",
                    "pitch_number": "3",
                    "season": 2024,
                    "month": "03",
                    "inning": 7,
                    "home_team": "SEA",
                    "away_team": "NYY",
                    "inning_topbot": "Top",
                    "outs_when_up": 1,
                    "balls": 2,
                    "strikes": 1,
                    "batter": "123456",
                    "pitcher": "654321",
                    "player_name": "Player A",
                    "stand": "R",
                    "pitch_type": "FF",
                    "events": "single",
                    "bb_type": "line_drive",
                    "zone": 5,
                    "release_speed": "95.1",
                    "launch_speed": "101.2",
                    "pitch_name": "4-Seam Fastball",
                    "game_year": 2024,
                }
            ]
        )

        result = normalize_detail_dataframe(detail_df)

        self.assertNotIn("pitch_name", result.columns)
        self.assertNotIn("game_year", result.columns)
        self.assertIn("events", result.columns)
        self.assertEqual(str(result["game_pk"].dtype), "Int32")
        self.assertEqual(str(result["at_bat_number"].dtype), "Int16")
        self.assertEqual(str(result["pitch_number"].dtype), "Int8")
        self.assertEqual(str(result["season"].dtype), "Int16")
        self.assertEqual(str(result["batting_team"].dtype), "category")
        self.assertEqual(str(result["pitch_type"].dtype), "category")
        self.assertEqual(str(result["player_name"].dtype), "string")
        self.assertEqual(str(result["release_speed"].dtype), "Float32")
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result["game_date"]))

    def test_fetch_detail_dataframe_returns_canonical_detail_schema(self):
        config = SimpleNamespace(
            pretty_local_output=False,
            sample_mode=False,
            sample_max_rows=20000,
            sample_random_state=42,
        )
        fetched = pd.DataFrame(
            [
                {
                    "game_date": "2024-03-28",
                    "game_pk": 1,
                    "at_bat_number": 1,
                    "pitch_number": 1,
                    "home_team": "SEA",
                    "away_team": "NYY",
                    "inning_topbot": "Top",
                    "events": "single",
                    "player_name": "Player A",
                    "batter": 100,
                    "pitch_name": "4-Seam Fastball",
                }
            ]
        )

        with patch("transforms._fetch_statcast_window", return_value=fetched):
            result = fetch_detail_dataframe(config, [(2024, 3, "2024-03-01", "2024-03-31")])

        self.assertNotIn("pitch_name", result.columns)
        self.assertEqual(result.iloc[0]["month"], "03")
        self.assertEqual(str(result["events"].dtype), "category")
        self.assertEqual(str(result["batting_team"].dtype), "category")
        self.assertEqual(str(result["pitch_type"].dtype), "category")
        self.assertEqual(int(result.iloc[0]["season"]), 2024)

    def test_build_detail_storage_tables_splits_core_tracking_and_dimensions(self):
        detail_df = pd.DataFrame(
            [
                {
                    "game_date": pd.Timestamp("2024-03-28"),
                    "game_pk": 1,
                    "at_bat_number": 1,
                    "pitch_number": 1,
                    "season": 2024,
                    "month": "03",
                    "inning": 1,
                    "outs_when_up": 0,
                    "balls": 0,
                    "strikes": 0,
                    "batter": 100,
                    "pitcher": 200,
                    "player_name": "Player A",
                    "stand": "R",
                    "batting_team": "NYY",
                    "pitch_type": "FF",
                    "events": "single",
                    "bb_type": "line_drive",
                    "zone": 5,
                    "release_speed": 95.1,
                    "launch_speed": 101.2,
                }
            ]
        )

        bundle = build_detail_storage_tables(detail_df)

        self.assertNotIn("player_name", bundle["detail"].columns)
        self.assertNotIn("batting_team", bundle["detail"].columns)
        self.assertIn("batting_team_id", bundle["detail"].columns)
        self.assertIn("event_code", bundle["detail"].columns)
        self.assertIn("release_speed", bundle["detail_tracking"].columns)
        self.assertEqual(str(bundle["detail"]["batting_team_id"].dtype), "Int8")
        self.assertEqual(str(bundle["detail"]["event_code"].dtype), "Int8")
        self.assertEqual(str(bundle["detail"]["pitch_type_code"].dtype), "Int8")
        self.assertEqual(str(bundle["detail"]["bb_type_code"].dtype), "Int8")
        self.assertEqual(list(bundle["players"].columns), ["batter", "player_name", "stand"])
        self.assertEqual(list(bundle["teams"].columns), ["team_id", "team"])
        self.assertEqual(bundle["players"].iloc[0]["player_name"], "Player A")
        self.assertEqual(bundle["teams"].iloc[0]["team"], "NYY")

    def test_player_dimension_drives_aggregate_name_resolution(self):
        detail_df = pd.DataFrame(
            [
                {
                    "game_date": pd.Timestamp("2024-03-27"),
                    "game_pk": 1,
                    "at_bat_number": 1,
                    "pitch_number": 1,
                    "season": 2024,
                    "month": "03",
                    "batter": 100,
                    "player_name": "Player Old",
                    "stand": "R",
                    "events": "single",
                },
                {
                    "game_date": pd.Timestamp("2024-03-28"),
                    "game_pk": 2,
                    "at_bat_number": 1,
                    "pitch_number": 1,
                    "season": 2024,
                    "month": "03",
                    "batter": 100,
                    "player_name": "Player New",
                    "stand": "R",
                    "events": "double",
                },
            ]
        )

        player_dimension = build_player_dimension_table(detail_df)
        result = build_player_season_aggregates(detail_df, player_dimension_df=player_dimension)

        self.assertEqual(result.iloc[0]["player_name"], "Player New")

    def test_team_season_aggregates_include_rate_stats(self):
        detail_df = pd.DataFrame(
            [
                {
                    "events": "single",
                    "game_pk": 1,
                    "at_bat_number": 1,
                    "season": 2024,
                    "batting_team": "NYY",
                },
                {
                    "events": "double",
                    "game_pk": 1,
                    "at_bat_number": 2,
                    "season": 2024,
                    "batting_team": "NYY",
                },
                {
                    "events": "walk",
                    "game_pk": 1,
                    "at_bat_number": 3,
                    "season": 2024,
                    "batting_team": "NYY",
                },
                {
                    "events": "home_run",
                    "game_pk": 1,
                    "at_bat_number": 4,
                    "season": 2024,
                    "batting_team": "NYY",
                },
            ]
        )

        result = build_team_season_aggregates(detail_df)
        nyy = result[result["team"] == "NYY"].iloc[0]

        self.assertEqual(int(nyy["hits"]), 3)
        self.assertEqual(int(nyy["singles"]), 1)
        self.assertEqual(int(nyy["doubles"]), 1)
        self.assertEqual(int(nyy["triples"]), 0)
        self.assertEqual(int(nyy["home_runs"]), 1)
        self.assertEqual(int(nyy["walks"]), 1)
        self.assertEqual(int(nyy["at_bats"]), 3)

        # AVG=3/3, OBP=(3+1)/(3+1), SLG=(1+2+4)/3, OPS=OBP+SLG
        self.assertAlmostEqual(float(nyy["avg"]), 1.0, places=6)
        self.assertAlmostEqual(float(nyy["obp"]), 1.0, places=6)
        self.assertAlmostEqual(float(nyy["slg"]), 7.0 / 3.0, places=6)
        self.assertAlmostEqual(float(nyy["ops"]), 1.0 + (7.0 / 3.0), places=6)
        self.assertAlmostEqual(float(nyy["bb_rate"]), 1.0 / 4.0, places=6)
        self.assertAlmostEqual(float(nyy["k_rate"]), 0.0, places=6)
        self.assertAlmostEqual(float(nyy["k_bb_ratio"]), 0.0, places=6)
        self.assertAlmostEqual(float(nyy["iso"]), (7.0 / 3.0) - 1.0, places=6)
        self.assertAlmostEqual(float(nyy["xbh_rate"]), 2.0 / 3.0, places=6)
        self.assertAlmostEqual(float(nyy["hr_rate"]), 1.0 / 4.0, places=6)
        self.assertAlmostEqual(float(nyy["bb_minus_k_rate"]), 1.0 / 4.0, places=6)
        self.assertAlmostEqual(float(nyy["babip"]), 1.0, places=6)
        self.assertAlmostEqual(float(nyy["contact_rate"]), 1.0, places=6)
        self.assertAlmostEqual(float(nyy["runs_created"]), ((3.0 + 1.0) * 7.0) / (3.0 + 1.0), places=6)

    def test_player_season_aggregates_ignore_missing_events(self):
        detail_df = pd.DataFrame(
            [
                {
                    "batter": "100",
                    "player_name": "Player A",
                    "events": pd.NA,
                    "game_pk": 1,
                    "at_bat_number": 1,
                    "season": 2024,
                },
                {
                    "batter": "100",
                    "player_name": "Player A",
                    "events": "single",
                    "game_pk": 1,
                    "at_bat_number": 2,
                    "season": 2024,
                },
            ]
        )

        result = build_player_season_aggregates(detail_df)
        player = result.iloc[0]

        self.assertEqual(int(player["plate_appearances"]), 2)
        self.assertEqual(int(player["at_bats"]), 1)
        self.assertEqual(int(player["hits"]), 1)
        self.assertEqual(int(player["singles"]), 1)
        self.assertEqual(int(player["walks"]), 0)

    def test_team_season_aggregates_ignore_missing_events(self):
        detail_df = pd.DataFrame(
            [
                {
                    "events": pd.NA,
                    "game_pk": 1,
                    "at_bat_number": 1,
                    "season": 2024,
                    "batting_team": "NYY",
                },
                {
                    "events": "single",
                    "game_pk": 1,
                    "at_bat_number": 2,
                    "season": 2024,
                    "batting_team": "NYY",
                },
            ]
        )

        result = build_team_season_aggregates(detail_df)
        team = result[result["team"] == "NYY"].iloc[0]

        self.assertEqual(int(team["plate_appearances"]), 2)
        self.assertEqual(int(team["at_bats"]), 1)
        self.assertEqual(int(team["hits"]), 1)
        self.assertEqual(int(team["singles"]), 1)


if __name__ == "__main__":
    unittest.main()
