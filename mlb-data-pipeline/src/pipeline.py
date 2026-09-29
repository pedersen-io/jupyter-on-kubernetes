from datetime import date, datetime, timezone
import os
import sys
import resource
import time
from typing import List, Optional, Tuple

import pandas as pd

from config import Config, get_config
from lahman import (
    build_lahman_manager_career_aggregates,
    build_lahman_manager_season_aggregates,
    build_lahman_player_season_aggregates_with_quality,
    build_lahman_team_season_aggregates,
)
from progress import LocalProgressReporter
from storage import (
    create_s3_client,
    latest_processed_end_date,
    list_bucket_captured_months,
    list_local_captured_months,
    local_latest_pointer_path,
    read_latest_pointer,
    resolve_local_manifest_path,
    upload_directory,
    upload_manifest,
    write_json_file,
)
from transforms import (
    build_player_career_aggregates,
    build_player_season_aggregates,
    build_team_career_aggregates,
    build_team_season_aggregates,
    fetch_detail_dataframe,
    write_aggregate_tables,
    write_detail_dataset,
)
from windows import add_months, full_refresh_windows, iter_date_windows, month_start, parse_date


STRUCTURED_METRICS_ENABLED = True


def log_metric(name: str, **values) -> None:
    if not STRUCTURED_METRICS_ENABLED:
        return
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    print(f"METRIC {name} {fields}".rstrip())


def set_structured_metrics_enabled(enabled: bool) -> None:
    global STRUCTURED_METRICS_ENABLED
    STRUCTURED_METRICS_ENABLED = enabled


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def bytes_to_gb(value: int) -> float:
    return value / float(1024 ** 3)


def dataframe_bytes(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    return int(df.memory_usage(index=True, deep=True).sum())


def directory_size_bytes(path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def process_rss_bytes() -> Optional[int]:
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = usage.ru_maxrss
        if sys.platform == "darwin":
            return int(rss)
        return int(rss * 1024)
    except Exception:
        return None


def filesystem_free_bytes(path) -> Optional[int]:
    try:
        stats = os.statvfs(str(path))
        return int(stats.f_bavail * stats.f_frsize)
    except Exception:
        return None


def preflight_storage_target(config: Config, client) -> dict:
    spaces_fields = {
        "SPACES_BUCKET": config.spaces_bucket,
        "SPACES_REGION": config.spaces_region,
        "SPACES_ENDPOINT": config.spaces_endpoint,
        "SPACES_ACCESS_KEY_ID": config.spaces_access_key_id,
        "SPACES_SECRET_ACCESS_KEY": config.spaces_secret_access_key,
    }
    provided = sorted(name for name, value in spaces_fields.items() if value)
    missing = sorted(name for name, value in spaces_fields.items() if not value)

    if config.upload_enabled and provided and missing:
        raise ValueError(
            "Incomplete Spaces configuration. Set all SPACES_* variables or none. "
            f"Missing: {', '.join(missing)}"
        )

    if not config.upload_enabled:
        return {
            "mode": "local",
            "latest_snapshot_present": False,
            "latest_snapshot_id": None,
            "bucket": None,
            "upload_enabled": False,
        }

    if client is None:
        raise ValueError(
            "UPLOAD_ENABLED=true requires all SPACES_* variables to be set."
        )

    assert config.spaces_bucket is not None

    client.head_bucket(Bucket=config.spaces_bucket)
    latest_pointer = read_latest_pointer(config, client)
    return {
        "mode": "spaces",
        "latest_snapshot_present": latest_pointer is not None,
        "latest_snapshot_id": latest_pointer.get("snapshot_id") if latest_pointer is not None else None,
        "bucket": config.spaces_bucket,
        "upload_enabled": True,
    }


def build_manifest(
    config: Config,
    snapshot_id: str,
    window_start_date: str,
    window_end_date: str,
    source_datasets: List[str],
    lahman_mapping_quality: Optional[dict],
    detail_rows: Optional[int],
    player_season_rows: Optional[int],
    player_career_rows: Optional[int],
    team_season_rows: Optional[int],
    team_career_rows: Optional[int],
    manager_season_rows: Optional[int],
    manager_career_rows: Optional[int],
) -> dict:
    outputs: dict = {}

    if detail_rows is not None:
        outputs["detail"] = {
            "path": f"{config.dataset_prefix}/snapshots/{snapshot_id}/detail/",
            "rows": detail_rows,
            "partitioning": ["season"] if config.partition_mode == "season" else ["season", "month"],
            "compression": config.parquet_compression,
        }

    aggregates: dict = {}
    if player_season_rows is not None:
        aggregates["player_season_metrics"] = f"{config.dataset_prefix}/snapshots/{snapshot_id}/aggregates/player_season_metrics.parquet"
        aggregates["player_season_rows"] = player_season_rows
    if player_career_rows is not None:
        aggregates["player_career_metrics"] = f"{config.dataset_prefix}/snapshots/{snapshot_id}/aggregates/player_career_metrics.parquet"
        aggregates["player_career_rows"] = player_career_rows
    if team_season_rows is not None:
        aggregates["team_season_metrics"] = f"{config.dataset_prefix}/snapshots/{snapshot_id}/aggregates/team_season_metrics.parquet"
        aggregates["team_season_rows"] = team_season_rows
    if team_career_rows is not None:
        aggregates["team_career_metrics"] = f"{config.dataset_prefix}/snapshots/{snapshot_id}/aggregates/team_career_metrics.parquet"
        aggregates["team_career_rows"] = team_career_rows
    if manager_season_rows is not None:
        aggregates["manager_season_metrics"] = f"{config.dataset_prefix}/snapshots/{snapshot_id}/aggregates/manager_season_metrics.parquet"
        aggregates["manager_season_rows"] = manager_season_rows
    if manager_career_rows is not None:
        aggregates["manager_career_metrics"] = f"{config.dataset_prefix}/snapshots/{snapshot_id}/aggregates/manager_career_metrics.parquet"
        aggregates["manager_career_rows"] = manager_career_rows
    if aggregates:
        outputs["aggregates"] = aggregates

    return {
        "snapshot_id": snapshot_id,
        "generated_at_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "dataset": "statcast",
            "datasets": source_datasets,
            "start_season": config.start_season,
            "end_season": config.end_season,
            "statcast_start_season": config.statcast_start_season,
            "incremental_mode": config.incremental_mode,
            "trailer_months": config.trailer_months,
            "lahman_enabled": config.lahman_enabled,
            "lahman_start_season": config.lahman_start_season,
            "lahman_end_season": config.lahman_end_season,
            "source_overlap_policy": config.source_overlap_policy,
            "lahman_mapping_quality": lahman_mapping_quality,
            "window_start_date": window_start_date,
            "window_end_date": window_end_date,
            "sample_mode": config.sample_mode,
            "sample_start_date": config.sample_start_date,
            "sample_end_date": config.sample_end_date,
            "sample_max_rows": config.sample_max_rows,
            "sample_max_windows": config.sample_max_windows,
            "partition_mode": config.partition_mode,
            "include_detail_dataset": config.include_detail_dataset,
            "include_aggregate_datasets": config.include_aggregate_datasets,
            "parquet_compression": config.parquet_compression,
            "include_player_aggregates": config.include_player_aggregates,
            "include_team_aggregates": config.include_team_aggregates,
            "include_manager_aggregates": config.include_manager_aggregates,
            "include_season_aggregates": config.include_season_aggregates,
            "include_career_aggregates": config.include_career_aggregates,
        },
        "outputs": outputs,
    }


def build_latest_pointer(
    config: Config,
    snapshot_id: str,
    manifest_path: str,
    window_start_date: str,
    window_end_date: str,
    detail_included: bool = True,
) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "manifest_path": manifest_path,
        "detail_path": (f"{config.dataset_prefix}/snapshots/{snapshot_id}/detail/" if detail_included else None),
        "window_start_date": window_start_date,
        "window_end_date": window_end_date,
        "updated_at_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def build_refresh_windows(config: Config, client) -> Tuple[List[Tuple[int, int, str, str]], str, str]:
    statcast_floor = max(config.start_season, config.statcast_start_season)
    if config.end_season < statcast_floor:
        if config.lahman_enabled:
            return [], f"{config.start_season}-01-01", f"{config.end_season}-12-31"
        raise ValueError("No Statcast windows available for configured season range; enable Lahman for pre-Statcast coverage")

    statcast_start_date = date(statcast_floor, 1, 1)
    latest_end_date_value = latest_processed_end_date(client, config)

    if config.sample_start_date and config.sample_end_date:
        windows = list(iter_date_windows(parse_date(config.sample_start_date), parse_date(config.sample_end_date)))
    elif config.incremental_mode:
        if latest_end_date_value is None:
            if config.require_existing_snapshot:
                raise ValueError(
                    "INCREMENTAL_MODE requires an existing snapshot, but no latest snapshot was found. "
                    "Run an initial bootstrap build first or set REQUIRE_EXISTING_SNAPSHOT=false."
                )
            print("No previous snapshot found; running first-pass full historical build.")
            windows = full_refresh_windows(config)
        else:
            latest_end_date = parse_date(latest_end_date_value)
            refresh_start = month_start(add_months(latest_end_date, -config.trailer_months))
            refresh_start = max(refresh_start, date(config.start_season, 1, 1))
            refresh_end = date.today()
            print(
                f"Incremental refresh from {refresh_start.strftime('%Y-%m-%d')} through {refresh_end.strftime('%Y-%m-%d')} with {config.trailer_months} month trailer."
            )

            latest_pointer = read_latest_pointer(config, client)
            captured_months = set()
            if latest_pointer is not None:
                detail_path = latest_pointer.get("detail_path")
                if detail_path:
                    if client is not None and config.spaces_bucket:
                        captured_months = list_bucket_captured_months(client, config.spaces_bucket, detail_path)
                    else:
                        captured_months = list_local_captured_months(resolve_local_manifest_path(config, detail_path))

            historical_windows = list(iter_date_windows(statcast_start_date, refresh_end))
            trailer_windows = list(iter_date_windows(refresh_start, refresh_end))
            missing_windows = [window for window in historical_windows if (window[0], window[1]) not in captured_months]

            windows = []
            seen = set()
            for group in (missing_windows, trailer_windows):
                for window in group:
                    key = (window[0], window[1])
                    if key in seen:
                        continue
                    seen.add(key)
                    windows.append(window)
            windows.sort(key=lambda window: (window[0], window[1]))
    else:
        windows = full_refresh_windows(config)
        windows = [window for window in windows if window[0] >= statcast_floor]

    if not windows:
        if config.lahman_enabled:
            return [], f"{config.start_season}-01-01", f"{config.end_season}-12-31"
        raise ValueError("No refresh windows were planned")

    return windows, windows[0][2], windows[-1][3]


def merge_season_aggregates(
    primary_df: pd.DataFrame,
    secondary_df: pd.DataFrame,
    key_cols: List[str],
    overlap_policy: str,
) -> pd.DataFrame:
    if primary_df.empty:
        return secondary_df.copy()
    if secondary_df.empty:
        return primary_df.copy()

    combined = pd.concat([primary_df, secondary_df], ignore_index=True, sort=False)
    if "source_system" not in combined.columns:
        combined["source_system"] = "unknown"

    if overlap_policy == "lahman_preferred":
        priority = {"lahman": 0, "statcast": 1}
    else:
        priority = {"statcast": 0, "lahman": 1}

    combined["_source_priority"] = combined["source_system"].map(priority).fillna(99)
    deduped = combined.sort_values(key_cols + ["_source_priority"]).drop_duplicates(subset=key_cols, keep="first")
    deduped = deduped.drop(columns=["_source_priority"])
    return deduped.reset_index(drop=True)


def add_career_source_column(career_df: pd.DataFrame, season_df: pd.DataFrame, key_cols: List[str]) -> pd.DataFrame:
    if career_df.empty:
        career_df["source_system"] = pd.Series(dtype="string")
        return career_df

    if season_df.empty or "source_system" not in season_df.columns:
        career_df["source_system"] = "unknown"
        return career_df

    source_rollup = (
        season_df.groupby(key_cols, dropna=False)["source_system"]
        .agg(lambda s: "mixed" if s.dropna().nunique() > 1 else (s.dropna().iloc[0] if not s.dropna().empty else "unknown"))
        .reset_index()
    )
    return career_df.merge(source_rollup, on=key_cols, how="left")


def main() -> None:
    run_started = time.time()
    config = get_config()
    reporter = LocalProgressReporter(config.pretty_local_output)
    set_structured_metrics_enabled(not config.pretty_local_output)
    snapshot_id = utc_now().strftime("%Y%m%dT%H%M%SZ")
    client = create_s3_client(config)
    preflight = preflight_storage_target(config, client)

    reporter.phase("Storage Preflight", preflight["mode"])
    if preflight["mode"] == "local":
        reporter.info("Remote upload disabled; run will write locally only.")
        log_metric("storage_preflight", mode="local", upload_enabled="false", latest_snapshot="not_checked")
        reporter.card("Storage", [("mode", "local"), ("upload", "disabled"), ("latest", "not checked")], tone="34")
    else:
        latest_state = "present" if preflight["latest_snapshot_present"] else "absent"
        reporter.info(
            f"bucket={preflight['bucket']} latest_json={latest_state} "
            f"snapshot={preflight['latest_snapshot_id'] or 'none'}"
        )
        log_metric(
            "storage_preflight",
            mode="spaces",
            upload_enabled="true",
            bucket=preflight["bucket"],
            latest_snapshot=latest_state,
            snapshot_id=(preflight["latest_snapshot_id"] or "none"),
        )
        reporter.card(
            "Storage",
            [("mode", "spaces"), ("bucket", str(preflight["bucket"])), ("latest", latest_state), ("snapshot", str(preflight["latest_snapshot_id"] or "none"))],
            tone="34",
        )

    reporter.phase("Plan Refresh", f"start={config.start_season} end={config.end_season}")
    windows, window_start_date, window_end_date = build_refresh_windows(config, client)
    log_metric(
        "planned_windows",
        total=len(windows),
        start_date=window_start_date,
        end_date=window_end_date,
        statcast_start_season=config.statcast_start_season,
        incremental_mode=str(config.incremental_mode).lower(),
        trailer_months=config.trailer_months,
    )
    if windows:
        first_year, first_month = windows[0][0], windows[0][1]
        last_year, last_month = windows[-1][0], windows[-1][1]
        remaining_months = (last_year - first_year) * 12 + (last_month - first_month) + 1
        log_metric(
            "work_remaining_estimate",
            windows=len(windows),
            months=remaining_months,
            first=f"{first_year}-{first_month:02d}",
            last=f"{last_year}-{last_month:02d}",
        )
    else:
        log_metric("work_remaining_estimate", windows=0, months=0)
    reporter.info(
        f"window_start={window_start_date} window_end={window_end_date} statcast_windows={len(windows)}"
    )
    reporter.card(
        "Plan",
        [
            ("range", f"{window_start_date}..{window_end_date}"),
            ("windows", str(len(windows))),
            ("incremental", str(config.incremental_mode).lower()),
            ("trailer", str(config.trailer_months)),
        ],
        tone="36",
    )

    base_output = config.output_dir / config.dataset_prefix / snapshot_id
    detail_dir = base_output / "detail"
    aggregates_dir = base_output / "aggregates"
    base_output.mkdir(parents=True, exist_ok=True)
    fs_free_before = filesystem_free_bytes(base_output)

    need_statcast_detail = config.include_detail_dataset or (
        config.include_aggregate_datasets and (config.include_player_aggregates or config.include_team_aggregates)
    )

    reporter.phase("Detail Dataset", "fetch and write")
    if need_statcast_detail:
        detail_df = fetch_detail_dataframe(config, windows) if windows else pd.DataFrame()
    else:
        detail_df = pd.DataFrame()

    if config.include_detail_dataset:
        detail_rows = write_detail_dataset(
            detail_df,
            detail_dir,
            compression=config.parquet_compression,
            partition_mode=config.partition_mode,
        )
    else:
        detail_rows = 0
    detail_df_bytes = dataframe_bytes(detail_df)
    detail_disk_bytes = directory_size_bytes(detail_dir)
    rss_after_detail = process_rss_bytes()
    log_metric("detail_rows_written", rows=detail_rows)
    log_metric(
        "resource_usage",
        stage="after_detail_write",
        detail_df_bytes=detail_df_bytes,
        detail_df_gb=f"{bytes_to_gb(detail_df_bytes):0.3f}",
        detail_disk_bytes=detail_disk_bytes,
        detail_disk_gb=f"{bytes_to_gb(detail_disk_bytes):0.3f}",
        rss_bytes=(rss_after_detail if rss_after_detail is not None else "na"),
        rss_gb=(f"{bytes_to_gb(rss_after_detail):0.3f}" if rss_after_detail is not None else "na"),
    )
    if config.include_detail_dataset:
        reporter.info(
            f"detail_df={bytes_to_gb(detail_df_bytes):0.3f}GB detail_disk={bytes_to_gb(detail_disk_bytes):0.3f}GB "
            f"rss={(f'{bytes_to_gb(rss_after_detail):0.3f}GB' if rss_after_detail is not None else 'na')}"
        )
    else:
        reporter.info("detail dataset write skipped by INCLUDE_DETAIL_DATASET=false")
    reporter.card(
        "Detail Metrics",
        [
            ("rows", str(detail_rows)),
            ("frame", f"{bytes_to_gb(detail_df_bytes):0.3f} GB"),
            ("disk", f"{bytes_to_gb(detail_disk_bytes):0.3f} GB"),
            ("rss", f"{bytes_to_gb(rss_after_detail):0.3f} GB" if rss_after_detail is not None else "n/a"),
        ],
        tone="35",
    )
    reporter.success(f"detail rows written: {detail_rows}")

    reporter.phase("Aggregates", "build selected outputs")
    source_datasets = []
    lahman_mapping_quality = None
    player_season_df = pd.DataFrame()
    player_career_df = pd.DataFrame()
    team_season_df = pd.DataFrame()
    team_career_df = pd.DataFrame()
    manager_season_df = pd.DataFrame(
        columns=[
            "manager_id",
            "manager_name",
            "season",
            "teams_managed",
            "games",
            "wins",
            "losses",
            "games_above_500",
            "win_pct",
            "source_system",
        ]
    )
    manager_career_df = pd.DataFrame(
        columns=[
            "manager_id",
            "manager_name",
            "seasons",
            "career_teams_managed",
            "career_games",
            "career_wins",
            "career_losses",
            "career_games_above_500",
            "career_win_pct",
            "career_wins_rank",
            "source_system",
        ]
    )

    include_player = config.include_aggregate_datasets and config.include_player_aggregates
    include_team = config.include_aggregate_datasets and config.include_team_aggregates
    include_manager = config.include_aggregate_datasets and config.include_manager_aggregates
    include_season = config.include_aggregate_datasets and config.include_season_aggregates
    include_career = config.include_aggregate_datasets and config.include_career_aggregates

    need_player_seed = include_player and (include_season or include_career)
    need_team_seed = include_team and (include_season or include_career)
    need_manager_seed = include_manager and (include_season or include_career)

    if need_player_seed:
        player_season_df = build_player_season_aggregates(detail_df, source_system="statcast")
    if need_team_seed:
        team_season_df = build_team_season_aggregates(detail_df, source_system="statcast")

    if not detail_df.empty and (need_player_seed or need_team_seed):
        source_datasets.append("statcast")
        log_metric("statcast_aggregate_seed_rows", rows=len(detail_df))

    if config.lahman_enabled and (need_player_seed or need_team_seed or need_manager_seed):
        lahman_start = max(config.start_season, config.lahman_start_season)
        if config.lahman_include_overlap:
            lahman_end = min(config.end_season, config.lahman_end_season)
        else:
            lahman_end = min(config.end_season, config.lahman_end_season, config.statcast_start_season - 1)

        if lahman_start <= lahman_end:
            reporter.info(f"Lahman enabled for seasons {lahman_start}-{lahman_end}")
            lahman_player_season = pd.DataFrame()
            lahman_team_season = pd.DataFrame()

            if need_player_seed:
                lahman_player_season, lahman_mapping_quality = build_lahman_player_season_aggregates_with_quality(
                    start_season=lahman_start,
                    end_season=lahman_end,
                    mapping_path=config.lahman_player_mapping_path,
                )
                player_season_df = merge_season_aggregates(
                    player_season_df,
                    lahman_player_season,
                    key_cols=["batter", "season"],
                    overlap_policy=config.source_overlap_policy,
                )

            if need_team_seed:
                lahman_team_season = build_lahman_team_season_aggregates(lahman_start, lahman_end)
                team_season_df = merge_season_aggregates(
                    team_season_df,
                    lahman_team_season,
                    key_cols=["team", "season"],
                    overlap_policy=config.source_overlap_policy,
                )

            if need_manager_seed:
                manager_season_df = build_lahman_manager_season_aggregates(lahman_start, lahman_end)
                if include_career:
                    manager_career_df = build_lahman_manager_career_aggregates(manager_season_df)

            if not lahman_player_season.empty or not lahman_team_season.empty or not manager_season_df.empty:
                source_datasets.append("lahman")
                log_metric(
                    "lahman_rows_merged",
                    player_rows=len(lahman_player_season),
                    team_rows=len(lahman_team_season),
                    manager_rows=len(manager_season_df),
                    start_season=lahman_start,
                    end_season=lahman_end,
                )
                reporter.success(
                    f"lahman rows merged: player={len(lahman_player_season)} team={len(lahman_team_season)} manager={len(manager_season_df)}"
                )

            if lahman_mapping_quality is not None and need_player_seed:
                log_metric("lahman_mapping_quality", **lahman_mapping_quality)

    if include_player and include_career:
        player_career_df = build_player_career_aggregates(player_season_df)
        player_career_df = add_career_source_column(player_career_df, player_season_df, ["batter", "player_name"])

    if include_team and include_career:
        team_career_df = build_team_career_aggregates(team_season_df)
        team_career_df = add_career_source_column(team_career_df, team_season_df, ["team"])

    player_season_out = player_season_df if (include_player and include_season) else None
    player_career_out = player_career_df if (include_player and include_career) else None
    team_season_out = team_season_df if (include_team and include_season) else None
    team_career_out = team_career_df if (include_team and include_career) else None
    manager_season_out = manager_season_df if (include_manager and include_season) else None
    manager_career_out = manager_career_df if (include_manager and include_career) else None

    source_datasets = sorted(set(source_datasets))

    if reporter.enabled and "source_system" in player_season_df.columns and not player_season_df.empty:
        reporter.phase("Source Coverage", "player_season rows by source")
        total = int(len(player_season_df))
        for source_name, count in player_season_df["source_system"].value_counts().items():
            reporter.metric_bar(str(source_name), int(count), total)

    if "source_system" in player_season_df.columns and not player_season_df.empty:
        for source_name, count in player_season_df["source_system"].value_counts().items():
            log_metric("player_season_source_rows", source=source_name, rows=int(count), total=int(len(player_season_df)))

    if config.include_aggregate_datasets and any(
        df is not None
        for df in [
            player_season_out,
            player_career_out,
            team_season_out,
            team_career_out,
            manager_season_out,
            manager_career_out,
        ]
    ):
        write_aggregate_tables(
            player_season_out,
            player_career_out,
            team_season_out,
            team_career_out,
            manager_season_out,
            manager_career_out,
            aggregates_dir,
            compression=config.parquet_compression,
        )

    player_season_rows = len(player_season_out) if player_season_out is not None else 0
    player_career_rows = len(player_career_out) if player_career_out is not None else 0
    team_season_rows = len(team_season_out) if team_season_out is not None else 0
    team_career_rows = len(team_career_out) if team_career_out is not None else 0
    manager_season_rows = len(manager_season_out) if manager_season_out is not None else 0
    manager_career_rows = len(manager_career_out) if manager_career_out is not None else 0

    player_season_bytes = dataframe_bytes(player_season_out if player_season_out is not None else pd.DataFrame())
    player_career_bytes = dataframe_bytes(player_career_out if player_career_out is not None else pd.DataFrame())
    team_season_bytes = dataframe_bytes(team_season_out if team_season_out is not None else pd.DataFrame())
    team_career_bytes = dataframe_bytes(team_career_out if team_career_out is not None else pd.DataFrame())
    manager_season_bytes = dataframe_bytes(manager_season_out if manager_season_out is not None else pd.DataFrame())
    manager_career_bytes = dataframe_bytes(manager_career_out if manager_career_out is not None else pd.DataFrame())
    aggregate_df_bytes = (
        player_season_bytes
        + player_career_bytes
        + team_season_bytes
        + team_career_bytes
        + manager_season_bytes
        + manager_career_bytes
    )
    aggregate_disk_bytes = directory_size_bytes(aggregates_dir)
    total_output_disk_bytes = directory_size_bytes(base_output)
    rss_after_aggregates = process_rss_bytes()
    fs_free_after = filesystem_free_bytes(base_output)

    log_metric(
        "aggregate_rows_written",
        player_season=player_season_rows,
        player_career=player_career_rows,
        team_season=team_season_rows,
        team_career=team_career_rows,
        manager_season=manager_season_rows,
        manager_career=manager_career_rows,
    )
    log_metric(
        "resource_usage",
        stage="after_aggregate_write",
        aggregate_df_bytes=aggregate_df_bytes,
        aggregate_df_gb=f"{bytes_to_gb(aggregate_df_bytes):0.3f}",
        aggregate_disk_bytes=aggregate_disk_bytes,
        aggregate_disk_gb=f"{bytes_to_gb(aggregate_disk_bytes):0.3f}",
        snapshot_disk_bytes=total_output_disk_bytes,
        snapshot_disk_gb=f"{bytes_to_gb(total_output_disk_bytes):0.3f}",
        rss_bytes=(rss_after_aggregates if rss_after_aggregates is not None else "na"),
        rss_gb=(f"{bytes_to_gb(rss_after_aggregates):0.3f}" if rss_after_aggregates is not None else "na"),
        fs_free_before_bytes=(fs_free_before if fs_free_before is not None else "na"),
        fs_free_after_bytes=(fs_free_after if fs_free_after is not None else "na"),
    )
    reporter.info(
        f"aggregate_df={bytes_to_gb(aggregate_df_bytes):0.3f}GB aggregate_disk={bytes_to_gb(aggregate_disk_bytes):0.3f}GB "
        f"snapshot_disk={bytes_to_gb(total_output_disk_bytes):0.3f}GB"
    )
    reporter.card(
        "Aggregate Metrics",
        [
            ("player_season", str(player_season_rows)),
            ("player_career", str(player_career_rows)),
            ("team_season", str(team_season_rows)),
            ("team_career", str(team_career_rows)),
            ("manager_season", str(manager_season_rows)),
            ("manager_career", str(manager_career_rows)),
            ("snapshot", f"{bytes_to_gb(total_output_disk_bytes):0.3f} GB"),
        ],
        tone="33",
    )
    reporter.success(
        "aggregate rows written: "
        f"player_season={player_season_rows} player_career={player_career_rows} "
        f"team_season={team_season_rows} team_career={team_career_rows} "
        f"manager_season={manager_season_rows} manager_career={manager_career_rows}"
    )

    manifest = build_manifest(
        config=config,
        snapshot_id=snapshot_id,
        window_start_date=window_start_date,
        window_end_date=window_end_date,
        source_datasets=source_datasets,
        lahman_mapping_quality=lahman_mapping_quality,
        detail_rows=(detail_rows if config.include_detail_dataset else None),
        player_season_rows=(player_season_rows if player_season_out is not None else None),
        player_career_rows=(player_career_rows if player_career_out is not None else None),
        team_season_rows=(team_season_rows if team_season_out is not None else None),
        team_career_rows=(team_career_rows if team_career_out is not None else None),
        manager_season_rows=(manager_season_rows if manager_season_out is not None else None),
        manager_career_rows=(manager_career_rows if manager_career_out is not None else None),
    )

    local_manifest_path = base_output / "manifest.json"
    write_json_file(local_manifest_path, manifest)

    local_latest_pointer = build_latest_pointer(
        config=config,
        snapshot_id=snapshot_id,
        manifest_path=f"{config.dataset_prefix}/snapshots/{snapshot_id}/manifest.json",
        window_start_date=window_start_date,
        window_end_date=window_end_date,
        detail_included=config.include_detail_dataset,
    )
    write_json_file(local_latest_pointer_path(config), local_latest_pointer)

    if not config.pretty_local_output:
        print(f"Wrote local snapshot to {base_output}")
    log_metric("snapshot_written", snapshot_id=snapshot_id, path=base_output)
    reporter.success(f"snapshot local path: {base_output}")

    if client is None:
        if not config.pretty_local_output:
            print("Spaces variables not set, skipping upload.")
        elapsed_total = time.time() - run_started
        log_metric("run_complete", uploaded="false", elapsed_s=f"{elapsed_total:0.1f}")
        if config.pretty_local_output:
            reporter.summary(
                "Run Complete",
                [
                    ("mode", "local"),
                    ("elapsed", f"{elapsed_total:0.1f}s"),
                    ("detail_rows", str(detail_rows)),
                    ("datasets", ",".join(source_datasets) if source_datasets else "none"),
                    ("processed", f"{bytes_to_gb(detail_df_bytes + aggregate_df_bytes):0.3f} GB"),
                    ("snapshot", f"{bytes_to_gb(total_output_disk_bytes):0.3f} GB"),
                    ("rss", f"{bytes_to_gb(rss_after_aggregates):0.3f} GB" if rss_after_aggregates is not None else "n/a"),
                ],
            )
        else:
            print(
                f"SUMMARY elapsed={elapsed_total:0.1f}s detail_rows={detail_rows} "
                f"player_season={player_season_rows} team_season={team_season_rows} "
                f"manager_season={manager_season_rows} manager_career={manager_career_rows} "
                f"datasets={','.join(source_datasets) if source_datasets else 'none'} "
                f"processed_gb={bytes_to_gb(detail_df_bytes + aggregate_df_bytes):0.3f} "
                f"snapshot_disk_gb={bytes_to_gb(total_output_disk_bytes):0.3f} "
                f"rss_gb={(f'{bytes_to_gb(rss_after_aggregates):0.3f}' if rss_after_aggregates is not None else 'na')}"
            )
        return

    assert config.spaces_bucket is not None

    snapshot_prefix = f"{config.dataset_prefix}/snapshots/{snapshot_id}"
    if config.include_detail_dataset and detail_dir.exists():
        upload_directory(client, config.spaces_bucket, detail_dir, f"{snapshot_prefix}/detail")
    if config.include_aggregate_datasets and aggregates_dir.exists():
        upload_directory(client, config.spaces_bucket, aggregates_dir, f"{snapshot_prefix}/aggregates")
    upload_manifest(client, config.spaces_bucket, manifest, f"{snapshot_prefix}/manifest.json")
    upload_manifest(client, config.spaces_bucket, local_latest_pointer, f"{config.dataset_prefix}/latest.json")
    if not config.pretty_local_output:
        print(f"Uploaded snapshot {snapshot_id} to bucket {config.spaces_bucket}")
    elapsed_total = time.time() - run_started
    log_metric("run_complete", uploaded="true", elapsed_s=f"{elapsed_total:0.1f}")
    if config.pretty_local_output:
        reporter.summary(
            "Run Complete",
            [
                ("mode", "upload"),
                ("elapsed", f"{elapsed_total:0.1f}s"),
                ("detail_rows", str(detail_rows)),
                ("datasets", ",".join(source_datasets) if source_datasets else "none"),
                ("processed", f"{bytes_to_gb(detail_df_bytes + aggregate_df_bytes):0.3f} GB"),
                ("snapshot", f"{bytes_to_gb(total_output_disk_bytes):0.3f} GB"),
                ("rss", f"{bytes_to_gb(rss_after_aggregates):0.3f} GB" if rss_after_aggregates is not None else "n/a"),
            ],
        )
    else:
        print(
            f"SUMMARY elapsed={elapsed_total:0.1f}s detail_rows={detail_rows} "
            f"player_season={player_season_rows} team_season={team_season_rows} "
            f"datasets={','.join(source_datasets) if source_datasets else 'none'} "
            f"processed_gb={bytes_to_gb(detail_df_bytes + aggregate_df_bytes):0.3f} "
            f"snapshot_disk_gb={bytes_to_gb(total_output_disk_bytes):0.3f} "
            f"rss_gb={(f'{bytes_to_gb(rss_after_aggregates):0.3f}' if rss_after_aggregates is not None else 'na')}"
        )
    reporter.success(f"upload complete: snapshot={snapshot_id}")
