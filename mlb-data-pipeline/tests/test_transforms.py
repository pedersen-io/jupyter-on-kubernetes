from pathlib import Path
import unittest

import test_helpers  # noqa: F401

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    pd = None

from transforms import build_team_season_aggregates


@unittest.skipIf(pd is None, "pandas is not installed in this environment")
class TransformTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
