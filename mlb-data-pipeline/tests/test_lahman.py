import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

import test_helpers  # noqa: F401

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    pd = None

from lahman import build_lahman_player_season_aggregates_with_quality, build_lahman_team_season_aggregates


@unittest.skipIf(pd is None, "pandas is not installed in this environment")
class LahmanTests(unittest.TestCase):
    def test_player_aggregates_with_mapping_quality_and_conflicts(self):
        batting = pd.DataFrame(
            [
                {
                    "playerID": "player_a",
                    "yearID": 2014,
                    "season": 2014,
                    "teamID": "BOS",
                    "AB": 10,
                    "H": 5,
                    "2B": 1,
                    "3B": 0,
                    "HR": 1,
                    "BB": 2,
                    "SO": 3,
                    "plate_appearances": 12,
                    "singles": 3,
                },
                {
                    "playerID": "player_b",
                    "yearID": 2014,
                    "season": 2014,
                    "teamID": "NYY",
                    "AB": 8,
                    "H": 2,
                    "2B": 0,
                    "3B": 0,
                    "HR": 0,
                    "BB": 1,
                    "SO": 2,
                    "plate_appearances": 9,
                    "singles": 2,
                },
            ]
        )
        people = pd.DataFrame(
            [
                {"playerID": "player_a", "player_name": "Player A"},
                {"playerID": "player_b", "player_name": "Player B"},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            mapping_path = Path(tmpdir) / "mapping.csv"
            pd.DataFrame(
                [
                    {"playerID": "player_a", "batter": "111"},
                    {"playerID": "player_a", "batter": "222"},
                    {"playerID": "player_b", "batter": None},
                ]
            ).to_csv(mapping_path, index=False)

            with patch("lahman._prepare_lahman_batting", return_value=batting), patch("lahman._load_player_names", return_value=people):
                result, quality = build_lahman_player_season_aggregates_with_quality(2014, 2014, mapping_path)

        self.assertEqual(len(result), 2)
        batter_map = {row["player_name"]: row["batter"] for _, row in result.iterrows()}
        self.assertEqual(str(batter_map["Player A"]), "111")
        self.assertEqual(str(batter_map["Player B"]), "lahman:player_b")

        self.assertEqual(quality["mapping_file_rows"], 3)
        self.assertEqual(quality["mapping_file_player_ids"], 2)
        self.assertEqual(quality["ambiguous_player_ids"], 1)
        self.assertEqual(quality["player_ids_in_output"], 2)
        self.assertEqual(quality["mapped_player_ids_in_output"], 1)
        self.assertEqual(quality["unmapped_player_ids_in_output"], 1)

    def test_team_aggregates_include_source_system(self):
        batting = pd.DataFrame(
            [
                {
                    "playerID": "player_a",
                    "yearID": 2014,
                    "season": 2014,
                    "teamID": "BOS",
                    "AB": 10,
                    "H": 5,
                    "2B": 1,
                    "3B": 0,
                    "HR": 1,
                    "BB": 2,
                    "SO": 3,
                    "plate_appearances": 12,
                    "singles": 3,
                },
                {
                    "playerID": "player_c",
                    "yearID": 2014,
                    "season": 2014,
                    "teamID": "BOS",
                    "AB": 5,
                    "H": 1,
                    "2B": 0,
                    "3B": 0,
                    "HR": 0,
                    "BB": 1,
                    "SO": 1,
                    "plate_appearances": 6,
                    "singles": 1,
                },
            ]
        )

        with patch("lahman._prepare_lahman_batting", return_value=batting):
            result = build_lahman_team_season_aggregates(2014, 2014)

        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["team"], "BOS")
        self.assertEqual(int(row["hits"]), 6)
        self.assertEqual(row["source_system"], "lahman")


if __name__ == "__main__":
    unittest.main()
