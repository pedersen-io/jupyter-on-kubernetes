from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_helpers  # noqa: F401

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    pd = None

from transforms import build_player_season_aggregates, build_team_season_aggregates, fetch_detail_dataframe
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

    def test_team_season_aggregates_include_rate_stats(self):
        detail_df = pd.DataFrame(
            [
                {
                    "events": "single",
                    "game_pk": 1,
                    "at_bat_number": 1,
                    "season": 2024,
                    "inning_topbot": "Top",
                    "home_team": "SEA",
                    "away_team": "NYY",
                },
                {
                    "events": "double",
                    "game_pk": 1,
                    "at_bat_number": 2,
                    "season": 2024,
                    "inning_topbot": "Top",
                    "home_team": "SEA",
                    "away_team": "NYY",
                },
                {
                    "events": "walk",
                    "game_pk": 1,
                    "at_bat_number": 3,
                    "season": 2024,
                    "inning_topbot": "Top",
                    "home_team": "SEA",
                    "away_team": "NYY",
                },
                {
                    "events": "home_run",
                    "game_pk": 1,
                    "at_bat_number": 4,
                    "season": 2024,
                    "inning_topbot": "Top",
                    "home_team": "SEA",
                    "away_team": "NYY",
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
                    "inning_topbot": "Top",
                    "home_team": "SEA",
                    "away_team": "NYY",
                },
                {
                    "events": "single",
                    "game_pk": 1,
                    "at_bat_number": 2,
                    "season": 2024,
                    "inning_topbot": "Top",
                    "home_team": "SEA",
                    "away_team": "NYY",
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
