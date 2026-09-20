from __future__ import annotations

import sys
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None


class LocalProgressReporter:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._color = enabled and sys.stdout.isatty()
        self._start = time.time()

    def _paint(self, text: str, code: str) -> str:
        if not self._color:
            return text
        return f"\033[{code}m{text}\033[0m"

    def _bar(self, current: int, total: int, width: int = 28) -> str:
        if total <= 0:
            return "[" + ("-" * width) + "]"
        ratio = max(0.0, min(1.0, current / total))
        filled = int(width * ratio)
        return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"

    def phase(self, title: str, detail: str = "") -> None:
        if not self.enabled:
            return
        prefix = self._paint("[phase]", "1;36")
        if detail:
            print(f"{prefix} {title} - {detail}")
        else:
            print(f"{prefix} {title}")

    def info(self, message: str) -> None:
        if not self.enabled:
            return
        print(f"{self._paint('[info]', '36')} {message}")

    def success(self, message: str) -> None:
        if not self.enabled:
            return
        print(f"{self._paint('[ok]', '1;32')} {message}")

    def warn(self, message: str) -> None:
        if not self.enabled:
            return
        print(f"{self._paint('[warn]', '1;33')} {message}")

    def progress(self, label: str, current: int, total: int, extra: str = "") -> None:
        if not self.enabled:
            return
        bar = self._bar(current, total)
        pct = 0.0 if total <= 0 else (100.0 * current / total)
        line = f"{self._paint('[progress]', '1;35')} {label} {bar} {current}/{total} ({pct:5.1f}%)"
        if extra:
            line += f" | {extra}"
        print(line)

    def metric_bar(self, label: str, value: int, total: int) -> None:
        if not self.enabled:
            return
        bar = self._bar(value, total, width=20)
        pct = 0.0 if total <= 0 else (100.0 * value / total)
        print(f"{self._paint('[metric]', '34')} {label:<10} {bar} {value} ({pct:5.1f}%)")

    def elapsed(self) -> float:
        return max(0.0, time.time() - self._start)

    def resource_snapshot(self, label: str = "") -> dict:
        """Capture current memory and optionally disk metrics."""
        snap = {"elapsed_sec": self.elapsed()}

        if psutil:
            try:
                proc = psutil.Process()
                mem_info = proc.memory_info()
                snap["rss_mb"] = mem_info.rss / (1024 * 1024)
                snap["vms_mb"] = mem_info.vms / (1024 * 1024)
            except Exception:
                pass

        if label:
            snap["label"] = label
        return snap

    def resource_summary(self, snapshots: list, data_volume_gb: float = 0.0, output_dir: Path = None) -> None:
        """Log resource usage summary."""
        if not snapshots:
            return

        rss_values = [s.get("rss_mb", 0) for s in snapshots if "rss_mb" in s]
        peak_rss = max(rss_values) if rss_values else 0.0

        summary_lines = []
        summary_lines.append(f"elapsed_sec={self.elapsed():.1f}")
        if peak_rss > 0:
            summary_lines.append(f"peak_rss_mb={peak_rss:.1f}")
        if data_volume_gb > 0:
            summary_lines.append(f"data_volume_gb={data_volume_gb:.2f}")

        disk_usage = 0.0
        if output_dir and output_dir.exists():
            try:
                for fpath in output_dir.rglob("*"):
                    if fpath.is_file():
                        disk_usage += fpath.stat().st_size
            except Exception:
                pass

        if disk_usage > 0:
            disk_gb = disk_usage / (1024 * 1024 * 1024)
            summary_lines.append(f"disk_usage_gb={disk_gb:.3f}")

        text = " | ".join(summary_lines)
        if self.enabled:
            self.success(f"resource summary: {text}")
        else:
            print(f"METRIC resource_summary {text}")
