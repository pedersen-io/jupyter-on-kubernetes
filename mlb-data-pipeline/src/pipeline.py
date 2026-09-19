from datetime import date, datetime
from typing import List, Optional, Tuple

import pandas as pd

from config import Config, get_config
from lahman import build_lahman_player_season_aggregates, build_lahman_team_season_aggregates
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


def build_manifest(
    config: Config,
    snapshot_id: str,
    window_start_date: str,
    window_end_date: str,
    source_datasets: List[str],
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
    config = get_config()
    snapshot_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    client = create_s3_client(config)

    windows, window_start_date, window_end_date = build_refresh_windows(config, client)

    base_output = config.output_dir / config.dataset_prefix / snapshot_id
    detail_dir = base_output / "detail"
    aggregates_dir = base_output / "aggregates"
    base_output.mkdir(parents=True, exist_ok=True)

    detail_df = fetch_detail_dataframe(config, windows) if windows else pd.DataFrame()
    detail_rows = write_detail_dataset(detail_df, detail_dir)

    player_season_df = build_player_season_aggregates(detail_df, source_system="statcast")
    team_season_df = build_team_season_aggregates(detail_df, source_system="statcast")

    source_datasets = ["statcast"] if not detail_df.empty else []

    if config.lahman_enabled:
        lahman_start = max(config.start_season, config.lahman_start_season)
        if config.lahman_include_overlap:
            lahman_end = min(config.end_season, config.lahman_end_season)
        else:
            lahman_end = min(config.end_season, config.lahman_end_season, config.statcast_start_season - 1)

        if lahman_start <= lahman_end:
            lahman_player_season = build_lahman_player_season_aggregates(
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

    player_career_df = build_player_career_aggregates(player_season_df)
    team_career_df = build_team_career_aggregates(team_season_df)
    player_career_df = add_career_source_column(player_career_df, player_season_df, ["batter", "player_name"])
    team_career_df = add_career_source_column(team_career_df, team_season_df, ["team"])

    source_datasets = sorted(set(source_datasets))
    write_aggregate_tables(player_season_df, player_career_df, team_season_df, team_career_df, aggregates_dir)

    manifest = build_manifest(
        config=config,
        snapshot_id=snapshot_id,
        window_start_date=window_start_date,
        window_end_date=window_end_date,
        source_datasets=source_datasets,
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

    if client is None:
        print("Spaces variables not set, skipping upload.")
        return

    assert config.spaces_bucket is not None

    snapshot_prefix = f"{config.dataset_prefix}/snapshots/{snapshot_id}"
    upload_directory(client, config.spaces_bucket, detail_dir, f"{snapshot_prefix}/detail")
    upload_directory(client, config.spaces_bucket, aggregates_dir, f"{snapshot_prefix}/aggregates")
    upload_manifest(client, config.spaces_bucket, manifest, f"{snapshot_prefix}/manifest.json")
    upload_manifest(client, config.spaces_bucket, local_latest_pointer, f"{config.dataset_prefix}/latest.json")
    print(f"Uploaded snapshot {snapshot_id} to bucket {config.spaces_bucket}")
