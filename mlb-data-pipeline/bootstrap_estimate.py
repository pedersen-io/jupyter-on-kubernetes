from __future__ import annotations

from collections import Counter
import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import get_config
from pipeline import build_refresh_windows


ACTIVE_MONTHS = {3, 4, 5, 6, 7, 8, 9, 10}
ACTIVE_WINDOW_SECONDS = (18, 30)
LIGHT_WINDOW_SECONDS = (5, 12)


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{secs:02d}s"


def main() -> int:
    config = get_config()
    windows, start_date, end_date = build_refresh_windows(config, client=None)

    year_counts = Counter(year for year, _month, _start_dt, _end_dt in windows)
    active_windows = sum(1 for _year, month, _start_dt, _end_dt in windows if month in ACTIVE_MONTHS)
    light_windows = len(windows) - active_windows

    low_seconds = (active_windows * ACTIVE_WINDOW_SECONDS[0]) + (light_windows * LIGHT_WINDOW_SECONDS[0])
    high_seconds = (active_windows * ACTIVE_WINDOW_SECONDS[1]) + (light_windows * LIGHT_WINDOW_SECONDS[1])

    print("MLB Data Pipeline Bootstrap Estimate")
    print(f"Configured seasons : {config.start_season}-{config.end_season}")
    print(f"Planned window span: {start_date} -> {end_date}")
    print(f"Statcast windows   : {len(windows)} monthly windows")
    print("Years in plan      : " + ", ".join(f"{year}({count})" for year, count in sorted(year_counts.items())))
    print(f"Heavier windows    : {active_windows} (Mar-Oct)")
    print(f"Lighter windows    : {light_windows} (Nov-Feb)")
    print(f"Fetch estimate     : {format_duration(low_seconds)} to {format_duration(high_seconds)}")
    print("Full bootstrap     : allow roughly 30-60 minutes on this Mac; use 60-90 minutes as a conservative upper bound.")
    if config.upload_enabled:
        print("Upload note        : remote upload can add extra time depending on network throughput.")
    if config.lahman_enabled:
        print(f"Lahman coverage    : {config.lahman_start_season}-{config.lahman_end_season} aggregate-only seasons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())