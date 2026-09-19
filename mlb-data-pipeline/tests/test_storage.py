import json
import tempfile
from pathlib import Path
import unittest

import test_helpers  # noqa: F401

from config import Config
from storage import (
    latest_processed_end_date,
    list_local_captured_months,
    local_latest_pointer_path,
    read_json_file,
    resolve_local_manifest_path,
    write_json_file,
)


class StorageTests(unittest.TestCase):
    def build_config(self, output_dir: Path) -> Config:
        return Config(
            start_season=2024,
            end_season=2024,
            output_dir=output_dir,
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

    def test_read_and_write_json_file_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "file.json"
            content = {"hello": "world"}
            write_json_file(path, content)
            self.assertEqual(read_json_file(path), content)

    def test_local_latest_pointer_path(self):
        config = self.build_config(Path("/tmp/output"))
        self.assertEqual(local_latest_pointer_path(config), Path("/tmp/output/baseball/latest.json"))

    def test_list_local_captured_months(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            detail_dir = Path(tmpdir) / "baseball" / "snapshots" / "snap-1" / "detail"
            (detail_dir / "season=2024" / "month=01").mkdir(parents=True)
            (detail_dir / "season=2024" / "month=01" / "part-0.parquet").write_text("x", encoding="utf-8")
            (detail_dir / "season=2024" / "month=02").mkdir(parents=True)
            (detail_dir / "season=2024" / "month=02" / "part-0.parquet").write_text("x", encoding="utf-8")

            self.assertEqual(list_local_captured_months(detail_dir), {(2024, 1), (2024, 2)})

    def test_latest_processed_end_date_local(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            config = self.build_config(output_dir)
            manifest_path = resolve_local_manifest_path(config, "baseball/snapshots/snap-1/manifest.json")
            write_json_file(
                manifest_path,
                {
                    "generated_at_utc": "2024-04-12T10:11:12Z",
                    "source": {"window_end_date": "2024-04-30"},
                },
            )
            write_json_file(
                local_latest_pointer_path(config),
                {
                    "snapshot_id": "snap-1",
                    "manifest_path": "baseball/snapshots/snap-1/manifest.json",
                    "detail_path": "baseball/snapshots/snap-1/detail/",
                    "window_start_date": "2024-04-01",
                    "window_end_date": "2024-04-30",
                    "updated_at_utc": "2024-05-01T00:00:00Z",
                },
            )

            self.assertEqual(latest_processed_end_date(None, config), "2024-04-30")


if __name__ == "__main__":
    unittest.main()
