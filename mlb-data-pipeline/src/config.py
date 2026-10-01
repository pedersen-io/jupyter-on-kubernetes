import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: Optional[str], default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def parse_parquet_compression(value: Optional[str]) -> str:
    if value is None:
        return "snappy"

    normalized = value.strip().lower()
    if normalized in {"", "none", "uncompressed"}:
        return "none"

    valid = {"snappy", "gzip", "brotli", "lz4", "zstd"}
    if normalized not in valid:
        raise ValueError("PARQUET_COMPRESSION must be one of: none, snappy, gzip, brotli, lz4, zstd")
    return normalized


def parse_partition_mode(value: Optional[str]) -> str:
    if value is None:
        return "season_month"

    normalized = value.strip().lower().replace("-", "_")
    valid = {"season", "season_month"}
    if normalized not in valid:
        raise ValueError("PARTITION_MODE must be one of: season, season_month")
    return normalized


@dataclass
class Config:
    start_season: int
    end_season: int
    output_dir: Path
    dataset_prefix: str
    upload_enabled: bool
    incremental_mode: bool
    require_existing_snapshot: bool
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
    statcast_start_season: int = 2015
    lahman_enabled: bool = False
    lahman_start_season: int = 1871
    lahman_end_season: int = 2014
    lahman_player_mapping_path: Optional[Path] = None
    lahman_include_overlap: bool = False
    source_overlap_policy: str = "statcast_preferred"
    pretty_local_output: bool = False
    parquet_compression: str = "snappy"
    partition_mode: str = "season_month"
    include_detail_dataset: bool = True
    include_aggregate_datasets: bool = True
    include_player_aggregates: bool = True
    include_team_aggregates: bool = True
    include_manager_aggregates: bool = True
    include_season_aggregates: bool = True
    include_career_aggregates: bool = True


def get_config() -> Config:
    current_year = datetime.now(timezone.utc).year
    start_season = int(os.getenv("START_SEASON", "2015"))
    end_season = int(os.getenv("END_SEASON", str(current_year)))
    upload_enabled = parse_bool(os.getenv("UPLOAD_ENABLED", "false"))
    incremental_mode = parse_bool(os.getenv("INCREMENTAL_MODE", "true"))
    require_existing_snapshot = parse_bool(os.getenv("REQUIRE_EXISTING_SNAPSHOT", "false"))
    trailer_months = parse_int(os.getenv("TRAILER_MONTHS"), 1)
    sample_mode = parse_bool(os.getenv("SAMPLE_MODE", "false"))
    sample_start_date = os.getenv("SAMPLE_START_DATE")
    sample_end_date = os.getenv("SAMPLE_END_DATE")
    sample_max_rows = int(os.getenv("SAMPLE_MAX_ROWS", "20000"))
    sample_max_windows = int(os.getenv("SAMPLE_MAX_WINDOWS", "2"))
    sample_random_state = int(os.getenv("SAMPLE_RANDOM_STATE", "42"))
    statcast_start_season = int(os.getenv("STATCAST_START_SEASON", "2015"))
    lahman_enabled = parse_bool(os.getenv("LAHMAN_ENABLED", "false"))
    lahman_start_season = int(os.getenv("LAHMAN_START_SEASON", "1871"))
    lahman_end_season = int(os.getenv("LAHMAN_END_SEASON", "2014"))
    lahman_player_mapping_path_raw = os.getenv("LAHMAN_PLAYER_MAPPING_PATH")
    lahman_include_overlap = parse_bool(os.getenv("LAHMAN_INCLUDE_OVERLAP", "false"))
    source_overlap_policy = os.getenv("SOURCE_OVERLAP_POLICY", "statcast_preferred").strip().lower()
    pretty_local_output = parse_bool(os.getenv("PRETTY_LOCAL_OUTPUT", "false"))
    parquet_compression = parse_parquet_compression(os.getenv("PARQUET_COMPRESSION", "snappy"))
    partition_mode = parse_partition_mode(os.getenv("PARTITION_MODE", "season_month"))
    include_detail_dataset = parse_bool(os.getenv("INCLUDE_DETAIL_DATASET", "true"))
    include_aggregate_datasets = parse_bool(os.getenv("INCLUDE_AGGREGATE_DATASETS", "true"))
    include_player_aggregates = parse_bool(os.getenv("INCLUDE_PLAYER_AGGREGATES", "true"))
    include_team_aggregates = parse_bool(os.getenv("INCLUDE_TEAM_AGGREGATES", "true"))
    include_manager_aggregates = parse_bool(os.getenv("INCLUDE_MANAGER_AGGREGATES", "true"))
    include_season_aggregates = parse_bool(os.getenv("INCLUDE_SEASON_AGGREGATES", "true"))
    include_career_aggregates = parse_bool(os.getenv("INCLUDE_CAREER_AGGREGATES", "true"))

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
    if statcast_start_season < 1871:
        raise ValueError("STATCAST_START_SEASON must be >= 1871")
    if lahman_start_season > lahman_end_season:
        raise ValueError("LAHMAN_START_SEASON cannot be greater than LAHMAN_END_SEASON")
    if source_overlap_policy not in {"statcast_preferred", "lahman_preferred"}:
        raise ValueError("SOURCE_OVERLAP_POLICY must be one of: statcast_preferred, lahman_preferred")
    if not include_detail_dataset and not include_aggregate_datasets:
        raise ValueError("At least one of INCLUDE_DETAIL_DATASET or INCLUDE_AGGREGATE_DATASETS must be true")
    if include_aggregate_datasets and not (
        include_player_aggregates or include_team_aggregates or include_manager_aggregates
    ):
        raise ValueError(
            "INCLUDE_AGGREGATE_DATASETS=true requires at least one of INCLUDE_PLAYER_AGGREGATES, "
            "INCLUDE_TEAM_AGGREGATES, or INCLUDE_MANAGER_AGGREGATES"
        )
    if include_aggregate_datasets and not (include_season_aggregates or include_career_aggregates):
        raise ValueError(
            "INCLUDE_AGGREGATE_DATASETS=true requires INCLUDE_SEASON_AGGREGATES or INCLUDE_CAREER_AGGREGATES"
        )

    lahman_player_mapping_path = Path(lahman_player_mapping_path_raw) if lahman_player_mapping_path_raw else None

    return Config(
        start_season=start_season,
        end_season=end_season,
        output_dir=Path(os.getenv("OUTPUT_DIR", "/tmp/output")),
        dataset_prefix=os.getenv("DATASET_PREFIX", "baseball"),
        upload_enabled=upload_enabled,
        incremental_mode=incremental_mode,
        require_existing_snapshot=require_existing_snapshot,
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
        statcast_start_season=statcast_start_season,
        lahman_enabled=lahman_enabled,
        lahman_start_season=lahman_start_season,
        lahman_end_season=lahman_end_season,
        lahman_player_mapping_path=lahman_player_mapping_path,
        lahman_include_overlap=lahman_include_overlap,
        source_overlap_policy=source_overlap_policy,
        pretty_local_output=pretty_local_output,
        parquet_compression=parquet_compression,
        partition_mode=partition_mode,
        include_detail_dataset=include_detail_dataset,
        include_aggregate_datasets=include_aggregate_datasets,
        include_player_aggregates=include_player_aggregates,
        include_team_aggregates=include_team_aggregates,
        include_manager_aggregates=include_manager_aggregates,
        include_season_aggregates=include_season_aggregates,
        include_career_aggregates=include_career_aggregates,
    )
