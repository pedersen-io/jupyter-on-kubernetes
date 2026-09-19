import calendar
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Tuple

from config import Config


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def month_end(value: date) -> date:
    next_month = date(value.year + 1, 1, 1) if value.month == 12 else date(value.year, value.month + 1, 1)
    return next_month - timedelta(days=1)


def add_months(value: date, months: int) -> date:
    total_months = (value.year * 12) + (value.month - 1) + months
    year = total_months // 12
    month = (total_months % 12) + 1
    return date(year, month, 1)


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_date_windows(start_date: date, end_date: date, max_windows: Optional[int] = None) -> Iterable[Tuple[int, int, str, str]]:
    windows = 0
    current = month_start(start_date)

    while current <= end_date:
        if max_windows is not None and windows >= max_windows:
            return

        window_start = max(current, start_date)
        last_day = month_end(current)
        window_end = min(last_day, end_date)
        windows += 1
        yield current.year, current.month, window_start.strftime("%Y-%m-%d"), window_end.strftime("%Y-%m-%d")
        current = add_months(current, 1)


def full_refresh_windows(config: Config) -> List[Tuple[int, int, str, str]]:
    start_date = date(config.start_season, 1, 1)
    end_year = min(config.end_season, datetime.utcnow().year)
    end_date = min(date(end_year, 12, 31), date.today())
    return list(iter_date_windows(start_date, end_date, max_windows=config.sample_max_windows if config.sample_mode else None))


def iter_sample_range(sample_start_date: str, sample_end_date: str) -> Iterable[Tuple[int, int, str, str]]:
    start = parse_date(sample_start_date)
    yield start.year, start.month, sample_start_date, sample_end_date


def trailer_refresh_windows(config: Config, latest_end_date: date) -> List[Tuple[int, int, str, str]]:
    refresh_start = month_start(add_months(latest_end_date, -config.trailer_months))
    refresh_start = max(refresh_start, date(config.start_season, 1, 1))
    refresh_end = date.today()
    return list(iter_date_windows(refresh_start, refresh_end))


def select_windows(config: Config, latest_end_date: Optional[date]) -> List[Tuple[int, int, str, str]]:
    if config.sample_start_date and config.sample_end_date:
        return list(iter_sample_range(config.sample_start_date, config.sample_end_date))
    if latest_end_date is None:
        return full_refresh_windows(config)
    return trailer_refresh_windows(config, latest_end_date)


def window_bounds(windows: List[Tuple[int, int, str, str]]) -> Tuple[str, str]:
    if not windows:
        raise ValueError("No refresh windows were planned")
    return windows[0][2], windows[-1][3]
