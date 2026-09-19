import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: Optional[str], default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


@dataclass
class Config:
    start_season: int
    end_season: int
    output_dir: Path
    dataset_prefix: str
    incremental_mode: bool
    trailer_months: int
    sample_mode: bool
    sample_start_date: Optional[str]
    sample_end_date: Optional[str]
    sample_max_rows: int
    sample_max_windows: int
    sample_random_state: int
    spaces_bucket: Optional[str]
    spaces_region: Optional[str]
    spaces_endpoint: Optional[str]
    spaces_access_key_id: Optional[str]
    spaces_secret_access_key: Optional[str]


def get_config() -> Config:
    current_year = datetime.utcnow().year
    start_season = int(os.getenv("START_SEASON", "2015"))
    end_season = int(os.getenv("END_SEASON", str(current_year)))
    incremental_mode = parse_bool(os.getenv("INCREMENTAL_MODE", "true"))
    trailer_months = parse_int(os.getenv("TRAILER_MONTHS"), 1)
    sample_mode = parse_bool(os.getenv("SAMPLE_MODE", "false"))
    sample_start_date = os.getenv("SAMPLE_START_DATE")
    sample_end_date = os.getenv("SAMPLE_END_DATE")
    sample_max_rows = int(os.getenv("SAMPLE_MAX_ROWS", "20000"))
    sample_max_windows = int(os.getenv("SAMPLE_MAX_WINDOWS", "2"))
    sample_random_state = int(os.getenv("SAMPLE_RANDOM_STATE", "42"))

    if start_season > end_season:
        raise ValueError("START_SEASON cannot be greater than END_SEASON")
    if trailer_months < 0:
        raise ValueError("TRAILER_MONTHS must be >= 0")
    if (sample_start_date and not sample_end_date) or (sample_end_date and not sample_start_date):
        raise ValueError("SAMPLE_START_DATE and SAMPLE_END_DATE must be set together")
    if sample_start_date and sample_end_date:
        datetime.strptime(sample_start_date, "%Y-%m-%d")
        datetime.strptime(sample_end_date, "%Y-%m-%d")
    if sample_max_rows < 1:
        raise ValueError("SAMPLE_MAX_ROWS must be >= 1")
    if sample_max_windows < 1:
        raise ValueError("SAMPLE_MAX_WINDOWS must be >= 1")

    return Config(
        start_season=start_season,
        end_season=end_season,
        output_dir=Path(os.getenv("OUTPUT_DIR", "/tmp/output")),
        dataset_prefix=os.getenv("DATASET_PREFIX", "baseball"),
        incremental_mode=incremental_mode,
        trailer_months=trailer_months,
        sample_mode=sample_mode,
        sample_start_date=sample_start_date,
        sample_end_date=sample_end_date,
        sample_max_rows=sample_max_rows,
        sample_max_windows=sample_max_windows,
        sample_random_state=sample_random_state,
        spaces_bucket=os.getenv("SPACES_BUCKET"),
        spaces_region=os.getenv("SPACES_REGION"),
        spaces_endpoint=os.getenv("SPACES_ENDPOINT"),
        spaces_access_key_id=os.getenv("SPACES_ACCESS_KEY_ID"),
        spaces_secret_access_key=os.getenv("SPACES_SECRET_ACCESS_KEY"),
    )
