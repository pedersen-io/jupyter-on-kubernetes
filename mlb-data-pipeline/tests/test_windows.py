from datetime import date
from pathlib import Path
import unittest

import test_helpers  # noqa: F401

from config import Config
from windows import full_refresh_windows, iter_date_windows, select_windows, trailer_refresh_windows, window_bounds


class WindowPlanningTests(unittest.TestCase):
    def test_iter_date_windows_truncates_edges(self):
        windows = list(iter_date_windows(date(2024, 4, 15), date(2024, 6, 3)))
        self.assertEqual(
            windows,
            [
                (2024, 4, "2024-04-15", "2024-04-30"),
                (2024, 5, "2024-05-01", "2024-05-31"),
                (2024, 6, "2024-06-01", "2024-06-03"),
            ],
        )

    def test_full_refresh_windows_uses_season_bounds(self):
        config = Config(
            start_season=2024,
            end_season=2024,
            output_dir=Path("/tmp/output"),
            dataset_prefix="baseball",
            upload_enabled=False,
            incremental_mode=False,
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

        windows = full_refresh_windows(config)
        self.assertEqual(windows[0], (2024, 1, "2024-01-01", "2024-01-31"))
        self.assertEqual(windows[-1], (2024, 12, "2024-12-01", "2024-12-31"))

    def test_trailer_refresh_windows_rewinds_one_month(self):
        config = Config(
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

        windows = trailer_refresh_windows(config, date(2024, 3, 31))
        self.assertEqual(windows[0], (2024, 2, "2024-02-01", "2024-02-29"))
        self.assertEqual(windows[-1][0:2], (date.today().year, date.today().month))

    def test_select_windows_prefers_sample_dates(self):
        config = Config(
            start_season=2024,
            end_season=2024,
            output_dir=Path("/tmp/output"),
            dataset_prefix="baseball",
            upload_enabled=False,
            incremental_mode=True,
            require_existing_snapshot=False,
            trailer_months=1,
            sample_mode=False,
            sample_start_date="2024-04-01",
            sample_end_date="2024-04-07",
            sample_max_rows=20000,
            sample_max_windows=2,
            sample_random_state=42,
            spaces_bucket=None,
            spaces_region=None,
            spaces_endpoint=None,
            spaces_access_key_id=None,
            spaces_secret_access_key=None,
        )

        windows = select_windows(config, latest_end_date=None)
        self.assertEqual(windows, [(2024, 4, "2024-04-01", "2024-04-07")])

    def test_window_bounds(self):
        windows = [(2024, 1, "2024-01-01", "2024-01-31"), (2024, 2, "2024-02-01", "2024-02-29")]
        self.assertEqual(window_bounds(windows), ("2024-01-01", "2024-02-29"))


if __name__ == "__main__":
    unittest.main()
