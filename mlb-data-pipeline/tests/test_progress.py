import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
import unittest

import test_helpers  # noqa: F401

from progress import LocalProgressReporter


class ProgressTests(unittest.TestCase):
    def test_bar_rendering_variants(self):
        reporter = LocalProgressReporter(enabled=False)
        self.assertEqual(reporter._bar(0, 0), "[----------------------------]")
        self.assertEqual(reporter._bar(0, 10), "[............................]")
        self.assertEqual(reporter._bar(10, 10), "[============================]")

    def test_resource_snapshot_includes_label_without_psutil(self):
        reporter = LocalProgressReporter(enabled=False)
        with patch("progress.psutil", None):
            snap = reporter.resource_snapshot(label="detail")

        self.assertIn("elapsed_sec", snap)
        self.assertEqual(snap["label"], "detail")
        self.assertNotIn("rss_mb", snap)

    def test_resource_summary_prints_metric_when_disabled(self):
        reporter = LocalProgressReporter(enabled=False)
        snapshots = [{"rss_mb": 128.0}]

        with tempfile.TemporaryDirectory() as tmpdir:
            sample_file = Path(tmpdir) / "part-0.parquet"
            sample_file.write_text("x" * 1024, encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                reporter.resource_summary(snapshots, data_volume_gb=1.25, output_dir=Path(tmpdir))

        text = output.getvalue()
        self.assertIn("METRIC resource_summary", text)
        self.assertIn("peak_rss_mb=128.0", text)
        self.assertIn("data_volume_gb=1.25", text)
        self.assertIn("disk_usage_gb=", text)

    def test_resource_summary_uses_success_when_enabled(self):
        reporter = LocalProgressReporter(enabled=True)
        reporter.success = Mock()

        reporter.resource_summary([{"rss_mb": 64.0}], data_volume_gb=0.0, output_dir=None)

        reporter.success.assert_called_once()
        self.assertIn("resource summary:", reporter.success.call_args[0][0])


if __name__ == "__main__":
    unittest.main()