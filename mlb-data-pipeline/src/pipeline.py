from datetime import date, datetime
import os
import sys
import resource
import time
from typing import List, Optional, Tuple

import pandas as pd

from config import Config, get_config
from lahman import build_lahman_player_season_aggregates_with_quality, build_lahman_team_season_aggregates
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


def log_metric(name: str, **values) -> None:
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    print(f"METRIC {name} {fields}".rstrip())


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


def build_manifest(
    config: Config,
    snapshot_id: str,
    window_start_date: str,
    window_end_date: str,
    source_datasets: List[str],
    lahman_mapping_quality: Optional[dict],
    detail_rows: int,
    player_season_rows: int,
    player_career_rows: int,
    team_season_rows: int,
    team_career_rows: int,
) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        },
        "outputs": {
            "detail": {
                "path": f"{config.dataset_prefix}/snapshots/{snapshot_id}/detail/",
                "rows": detail_rows,
                "partitioning": ["season", "month"],
            },
            "aggregates": {
                "player_season_metrics": f"{config.dataset_prefix}/snapshots/{snapshot_id}/aggregates/player_season_metrics.parquet",
                "player_career_metrics": f"{config.dataset_prefix}/snapshots/{snapshot_id}/aggregates/player_career_metrics.parquet",
                "team_season_metrics": f"{config.dataset_prefix}/snapshots/{snapshot_id}/aggregates/team_season_metrics.parquet",
                "team_career_metrics": f"{config.dataset_prefix}/snapshots/{snapshot_id}/aggregates/team_career_metrics.parquet",
                "player_season_rows": player_season_rows,
                "player_career_rows": player_career_rows,
                "team_season_rows": team_season_rows,
                "team_career_rows": team_career_rows,
            },
        },
    }


def build_latest_pointer(config: Config, snapshot_id: str, manifest_path: str, window_start_date: str, window_end_date: str) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "manifest_path": manifest_path,
        "detail_path": f"{config.dataset_prefix}/snapshots/{snapshot_id}/detail/",
        "window_start_date": window_start_date,
        "window_end_date": window_end_date,
        "updated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    snapshot_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    client = create_s3_client(config)

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

    base_output = config.output_dir / config.dataset_prefix / snapshot_id
    detail_dir = base_output / "detail"
    aggregates_dir = base_output / "aggregates"
    base_output.mkdir(parents=True, exist_ok=True)
    fs_free_before = filesystem_free_bytes(base_output)

    reporter.phase("Detail Dataset", "fetch and write")
    detail_df = fetch_detail_dataframe(config, windows) if windows else pd.DataFrame()
    detail_rows = write_detail_dataset(detail_df, detail_dir)
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
    reporter.info(
        f"detail_df={bytes_to_gb(detail_df_bytes):0.3f}GB detail_disk={bytes_to_gb(detail_disk_bytes):0.3f}GB "
        f"rss={(f'{bytes_to_gb(rss_after_detail):0.3f}GB' if rss_after_detail is not None else 'na')}"
    )
    reporter.success(f"detail rows written: {detail_rows}")

    reporter.phase("Aggregates", "build statcast + optional lahman")
    player_season_df = build_player_season_aggregates(detail_df, source_system="statcast")
    team_season_df = build_team_season_aggregates(detail_df, source_system="statcast")

    source_datasets = ["statcast"] if not detail_df.empty else []
    if not detail_df.empty:
        log_metric("statcast_aggregate_seed_rows", rows=len(detail_df))
    lahman_mapping_quality = None

    if config.lahman_enabled:
        lahman_start = max(config.start_season, config.lahman_start_season)
        if config.lahman_include_overlap:
            lahman_end = min(config.end_season, config.lahman_end_season)
        else:
            lahman_end = min(config.end_season, config.lahman_end_season, config.statcast_start_season - 1)

        if lahman_start <= lahman_end:
            reporter.info(f"Lahman enabled for seasons {lahman_start}-{lahman_end}")
            lahman_player_season, lahman_mapping_quality = build_lahman_player_season_aggregates_with_quality(
                start_season=lahman_start,
                end_season=lahman_end,
                mapping_path=config.lahman_player_mapping_path,
            )
            lahman_team_season = build_lahman_team_season_aggregates(lahman_start, lahman_end)

            player_season_df = merge_season_aggregates(
                player_season_df,
                lahman_player_season,
                key_cols=["batter", "season"],
                overlap_policy=config.source_overlap_policy,
            )
            team_season_df = merge_season_aggregates(
                team_season_df,
                lahman_team_season,
                key_cols=["team", "season"],
                overlap_policy=config.source_overlap_policy,
            )

            if not lahman_player_season.empty or not lahman_team_season.empty:
                source_datasets.append("lahman")
                log_metric(
                    "lahman_rows_merged",
                    player_rows=len(lahman_player_season),
                    team_rows=len(lahman_team_season),
                    start_season=lahman_start,
                    end_season=lahman_end,
                )
                reporter.success(
                    f"lahman rows merged: player={len(lahman_player_season)} team={len(lahman_team_season)}"
                )

            if lahman_mapping_quality is not None:
                log_metric("lahman_mapping_quality", **lahman_mapping_quality)

    player_career_df = build_player_career_aggregates(player_season_df)
    team_career_df = build_team_career_aggregates(team_season_df)
    player_career_df = add_career_source_column(player_career_df, player_season_df, ["batter", "player_name"])
    team_career_df = add_career_source_column(team_career_df, team_season_df, ["team"])

    source_datasets = sorted(set(source_datasets))

    if reporter.enabled and "source_system" in player_season_df.columns and not player_season_df.empty:
        reporter.phase("Source Coverage", "player_season rows by source")
        total = int(len(player_season_df))
        for source_name, count in player_season_df["source_system"].value_counts().items():
            reporter.metric_bar(str(source_name), int(count), total)

    if "source_system" in player_season_df.columns and not player_season_df.empty:
        for source_name, count in player_season_df["source_system"].value_counts().items():
            log_metric("player_season_source_rows", source=source_name, rows=int(count), total=int(len(player_season_df)))

    write_aggregate_tables(player_season_df, player_career_df, team_season_df, team_career_df, aggregates_dir)
    player_season_bytes = dataframe_bytes(player_season_df)
    player_career_bytes = dataframe_bytes(player_career_df)
    team_season_bytes = dataframe_bytes(team_season_df)
    team_career_bytes = dataframe_bytes(team_career_df)
    aggregate_df_bytes = player_season_bytes + player_career_bytes + team_season_bytes + team_career_bytes
    aggregate_disk_bytes = directory_size_bytes(aggregates_dir)
    total_output_disk_bytes = directory_size_bytes(base_output)
    rss_after_aggregates = process_rss_bytes()
    fs_free_after = filesystem_free_bytes(base_output)

    log_metric(
        "aggregate_rows_written",
        player_season=len(player_season_df),
        player_career=len(player_career_df),
        team_season=len(team_season_df),
        team_career=len(team_career_df),
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
    reporter.success(
        "aggregate rows written: "
        f"player_season={len(player_season_df)} player_career={len(player_career_df)} "
        f"team_season={len(team_season_df)} team_career={len(team_career_df)}"
    )

    manifest = build_manifest(
        config=config,
        snapshot_id=snapshot_id,
        window_start_date=window_start_date,
        window_end_date=window_end_date,
        source_datasets=source_datasets,
        lahman_mapping_quality=lahman_mapping_quality,
        detail_rows=detail_rows,
        player_season_rows=len(player_season_df),
        player_career_rows=len(player_career_df),
        team_season_rows=len(team_season_df),
        team_career_rows=len(team_career_df),
    )

    local_manifest_path = base_output / "manifest.json"
    write_json_file(local_manifest_path, manifest)

    local_latest_pointer = build_latest_pointer(
        config=config,
        snapshot_id=snapshot_id,
        manifest_path=f"{config.dataset_prefix}/snapshots/{snapshot_id}/manifest.json",
        window_start_date=window_start_date,
        window_end_date=window_end_date,
    )
    write_json_file(local_latest_pointer_path(config), local_latest_pointer)

    print(f"Wrote local snapshot to {base_output}")
    log_metric("snapshot_written", snapshot_id=snapshot_id, path=base_output)
    reporter.success(f"snapshot local path: {base_output}")

    if client is None:
        print("Spaces variables not set, skipping upload.")
        elapsed_total = time.time() - run_started
        log_metric("run_complete", uploaded="false", elapsed_s=f"{elapsed_total:0.1f}")
        print(
            f"SUMMARY elapsed={elapsed_total:0.1f}s detail_rows={detail_rows} "
            f"player_season={len(player_season_df)} team_season={len(team_season_df)} "
            f"datasets={','.join(source_datasets) if source_datasets else 'none'} "
            f"processed_gb={bytes_to_gb(detail_df_bytes + aggregate_df_bytes):0.3f} "
            f"snapshot_disk_gb={bytes_to_gb(total_output_disk_bytes):0.3f} "
            f"rss_gb={(f'{bytes_to_gb(rss_after_aggregates):0.3f}' if rss_after_aggregates is not None else 'na')}"
        )
        return

    assert config.spaces_bucket is not None

    snapshot_prefix = f"{config.dataset_prefix}/snapshots/{snapshot_id}"
    upload_directory(client, config.spaces_bucket, detail_dir, f"{snapshot_prefix}/detail")
    upload_directory(client, config.spaces_bucket, aggregates_dir, f"{snapshot_prefix}/aggregates")
    upload_manifest(client, config.spaces_bucket, manifest, f"{snapshot_prefix}/manifest.json")
    upload_manifest(client, config.spaces_bucket, local_latest_pointer, f"{config.dataset_prefix}/latest.json")
    print(f"Uploaded snapshot {snapshot_id} to bucket {config.spaces_bucket}")
    elapsed_total = time.time() - run_started
    log_metric("run_complete", uploaded="true", elapsed_s=f"{elapsed_total:0.1f}")
    print(
        f"SUMMARY elapsed={elapsed_total:0.1f}s detail_rows={detail_rows} "
        f"player_season={len(player_season_df)} team_season={len(team_season_df)} "
        f"datasets={','.join(source_datasets) if source_datasets else 'none'} "
        f"processed_gb={bytes_to_gb(detail_df_bytes + aggregate_df_bytes):0.3f} "
        f"snapshot_disk_gb={bytes_to_gb(total_output_disk_bytes):0.3f} "
        f"rss_gb={(f'{bytes_to_gb(rss_after_aggregates):0.3f}' if rss_after_aggregates is not None else 'na')}"
    )
    reporter.success(f"upload complete: snapshot={snapshot_id}")
