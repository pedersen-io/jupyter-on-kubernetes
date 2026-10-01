from __future__ import annotations

import time
import importlib
import warnings
from typing import Iterable, List, Tuple

HIT_EVENTS = {"single", "double", "triple", "home_run"}
AB_EXCLUDED_EVENTS = {
    "walk",
    "intent_walk",
    "hit_by_pitch",
    "sac_bunt",
    "sac_fly",
    "catcher_interf",
}

DETAIL_WORKING_COLUMNS = [
    "game_date",
    "game_pk",
    "at_bat_number",
    "pitch_number",
    "season",
    "month",
    "inning",
    "outs_when_up",
    "balls",
    "strikes",
    "batter",
    "pitcher",
    "player_name",
    "stand",
    "batting_team",
    "pitch_type",
    "events",
    "bb_type",
    "zone",
    "release_speed",
    "release_spin_rate",
    "release_pos_x",
    "release_pos_z",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "vx0",
    "vy0",
    "vz0",
    "ax",
    "ay",
    "az",
    "sz_top",
    "sz_bot",
    "effective_speed",
    "launch_speed",
    "launch_angle",
    "hit_distance_sc",
    "hc_x",
    "hc_y",
]

DETAIL_CORE_COLUMNS = [
    "game_date",
    "game_pk",
    "at_bat_number",
    "pitch_number",
    "season",
    "month",
    "inning",
    "outs_when_up",
    "balls",
    "strikes",
    "batter",
    "pitcher",
    "batting_team_id",
    "event_code",
    "pitch_type_code",
    "bb_type_code",
    "zone",
]

DETAIL_TRACKING_VALUE_COLUMNS = [
    "release_speed",
    "release_spin_rate",
    "release_pos_x",
    "release_pos_z",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "vx0",
    "vy0",
    "vz0",
    "ax",
    "ay",
    "az",
    "sz_top",
    "sz_bot",
    "effective_speed",
    "launch_speed",
    "launch_angle",
    "hit_distance_sc",
    "hc_x",
    "hc_y",
]

DETAIL_TRACKING_COLUMNS = [
    "game_pk",
    "at_bat_number",
    "pitch_number",
    "season",
    "month",
] + DETAIL_TRACKING_VALUE_COLUMNS

DETAIL_LOW_CARDINALITY_COLUMNS = {
    "month",
    "stand",
    "batting_team",
    "pitch_type",
    "events",
    "bb_type",
}

DETAIL_INTEGER_DTYPES = {
    "game_pk": "Int32",
    "at_bat_number": "Int16",
    "pitch_number": "Int8",
    "season": "Int16",
    "inning": "Int8",
    "outs_when_up": "Int8",
    "balls": "Int8",
    "strikes": "Int8",
    "batter": "Int32",
    "pitcher": "Int32",
    "zone": "Int8",
}

DETAIL_FLOAT_COLUMNS = set(DETAIL_TRACKING_VALUE_COLUMNS)


def add_rate_stats(df, hits_col: str, at_bats_col: str, walks_col: str, singles_col: str, doubles_col: str, triples_col: str, home_runs_col: str):
    # Use denominator guards to avoid divide-by-zero and keep outputs query friendly.
    at_bats = df[at_bats_col].astype(float)
    on_base_den = (df[at_bats_col] + df[walks_col]).astype(float)

    df["avg"] = (df[hits_col] / at_bats.where(at_bats > 0)).fillna(0.0)
    df["obp"] = ((df[hits_col] + df[walks_col]) / on_base_den.where(on_base_den > 0)).fillna(0.0)

    total_bases = (
        (df[singles_col] * 1)
        + (df[doubles_col] * 2)
        + (df[triples_col] * 3)
        + (df[home_runs_col] * 4)
    )
    df["slg"] = (total_bases / at_bats.where(at_bats > 0)).fillna(0.0)
    df["ops"] = df["obp"] + df["slg"]
    return df


def add_advanced_batting_stats(
    df,
    plate_appearances_col: str,
    at_bats_col: str,
    hits_col: str,
    walks_col: str,
    strikeouts_col: str,
    singles_col: str,
    doubles_col: str,
    triples_col: str,
    home_runs_col: str,
    sac_flies_col: str,
    avg_col: str,
    slg_col: str,
    prefix: str = "",
):
    pa = df[plate_appearances_col].astype(float)
    at_bats = df[at_bats_col].astype(float)
    hits = df[hits_col].astype(float)
    walks = df[walks_col].astype(float)
    strikeouts = df[strikeouts_col].astype(float)
    singles = df[singles_col].astype(float)
    doubles = df[doubles_col].astype(float)
    triples = df[triples_col].astype(float)
    home_runs = df[home_runs_col].astype(float)
    sac_flies = df[sac_flies_col].astype(float)

    total_bases = (singles * 1) + (doubles * 2) + (triples * 3) + (home_runs * 4)
    xbh = doubles + triples + home_runs

    df[f"{prefix}bb_rate"] = (walks / pa.where(pa > 0)).fillna(0.0)
    df[f"{prefix}k_rate"] = (strikeouts / pa.where(pa > 0)).fillna(0.0)
    df[f"{prefix}k_bb_ratio"] = (strikeouts / walks.where(walks > 0)).fillna(0.0)
    df[f"{prefix}iso"] = (df[slg_col].astype(float) - df[avg_col].astype(float)).fillna(0.0)
    df[f"{prefix}xbh_rate"] = (xbh / hits.where(hits > 0)).fillna(0.0)
    df[f"{prefix}hr_rate"] = (home_runs / pa.where(pa > 0)).fillna(0.0)
    df[f"{prefix}bb_minus_k_rate"] = df[f"{prefix}bb_rate"] - df[f"{prefix}k_rate"]

    babip_den = at_bats - strikeouts - home_runs + sac_flies
    df[f"{prefix}babip"] = ((hits - home_runs) / babip_den.where(babip_den > 0)).fillna(0.0)
    df[f"{prefix}contact_rate"] = (1.0 - df[f"{prefix}k_rate"]).clip(lower=0.0, upper=1.0)

    rc_den = at_bats + walks
    df[f"{prefix}runs_created"] = (((hits + walks) * total_bases) / rc_den.where(rc_den > 0)).fillna(0.0)
    return df


def _event_equals(events, value: str):
    return events.eq(value).fillna(False)


def _event_in(events, values):
    return events.isin(values).fillna(False)


def _fetch_statcast_window(start_dt: str, end_dt: str, suppress_noise: bool):
    from pybaseball.statcast import statcast
    statcast_module = importlib.import_module("pybaseball.statcast")

    if not suppress_noise:
        return statcast(start_dt=start_dt, end_dt=end_dt, verbose=False)

    original_tqdm = statcast_module.tqdm

    def quiet_tqdm(*args, **kwargs):
        kwargs = dict(kwargs)
        kwargs["disable"] = True
        return original_tqdm(*args, **kwargs)

    statcast_module.tqdm = quiet_tqdm
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning, message=r".*errors='ignore' is deprecated.*")
            warnings.filterwarnings("ignore", category=FutureWarning, message=r".*all-NA entries.*")
            return statcast(start_dt=start_dt, end_dt=end_dt, verbose=False)
    finally:
        statcast_module.tqdm = original_tqdm


def _format_window_label(window: Tuple[int, int, str, str]) -> str:
    year, month, _start_dt, _end_dt = window
    return f"{year}-{month:02d}"


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h{minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _preview_windows(windows: List[Tuple[int, int, str, str]], limit: int = 5) -> str:
    if not windows:
        return "none"

    labels = [_format_window_label(window) for window in windows[:limit]]
    preview = ", ".join(labels)
    if len(windows) > limit:
        preview += f", ... (+{len(windows) - limit} more)"
    return preview


def _summarize_window_years(windows: List[Tuple[int, int, str, str]]) -> str:
    if not windows:
        return "none"

    counts = {}
    for year, _month, _start_dt, _end_dt in windows:
        counts[year] = counts.get(year, 0) + 1
    return ", ".join(f"{year}({count})" for year, count in sorted(counts.items()))


def _window_queue_entries(windows: List[Tuple[int, int, str, str]]) -> List[Tuple[str, str]]:
    if not windows:
        return [("years", "none"), ("planned", "0"), ("first", "none"), ("last", "none")]

    labels = [_format_window_label(window) for window in windows]
    preview = _preview_windows(windows, limit=5)

    return [
        ("years", _summarize_window_years(windows)),
        ("planned", str(len(windows))),
        ("first", labels[0]),
        ("last", labels[-1]),
        ("preview", preview),
    ]


def _derive_batting_team(frame):
    import pandas as pd

    if "batting_team" in frame.columns:
        return frame["batting_team"].astype("string")

    batting_team = pd.Series(pd.NA, index=frame.index, dtype="string")
    home_team = frame["home_team"].astype("string") if "home_team" in frame.columns else batting_team.copy()
    away_team = frame["away_team"].astype("string") if "away_team" in frame.columns else batting_team.copy()
    inning_half = frame["inning_topbot"].astype("string") if "inning_topbot" in frame.columns else batting_team.copy()

    batting_team = home_team.copy()
    batting_team.loc[inning_half == "Top"] = away_team.loc[inning_half == "Top"]
    return batting_team


def _build_code_dimension(series, code_column: str, value_column: str, dtype: str):
    import pandas as pd

    values = series.astype("string")
    unique_values = sorted({value for value in values.dropna().tolist() if value is not None})
    if not unique_values:
        return pd.DataFrame(columns=[code_column, value_column]), pd.Series(dtype=dtype)

    dimension_df = pd.DataFrame({value_column: unique_values})
    dimension_df[code_column] = pd.Series(range(1, len(dimension_df) + 1), dtype=dtype)
    codes = values.map(dimension_df.set_index(value_column)[code_column]).astype(dtype)
    return dimension_df[[code_column, value_column]], codes


def build_player_dimension_table(detail_df):
    import pandas as pd

    if detail_df.empty:
        return pd.DataFrame(columns=["batter", "player_name", "stand"])

    return (
        detail_df[["batter", "player_name", "stand", "game_date", "season", "month", "game_pk", "at_bat_number", "pitch_number"]]
        .sort_values(["game_date", "season", "month", "game_pk", "at_bat_number", "pitch_number"], na_position="last")
        .drop_duplicates(subset=["batter"], keep="last")
        [["batter", "player_name", "stand"]]
        .reset_index(drop=True)
    )


def build_detail_storage_tables(detail_df):
    import pandas as pd

    empty_bundle = {
        "detail": pd.DataFrame(columns=DETAIL_CORE_COLUMNS),
        "detail_tracking": pd.DataFrame(columns=DETAIL_TRACKING_COLUMNS),
        "players": pd.DataFrame(columns=["batter", "player_name", "stand"]),
        "teams": pd.DataFrame(columns=["team_id", "team"]),
        "event_types": pd.DataFrame(columns=["event_code", "event"]),
        "pitch_types": pd.DataFrame(columns=["pitch_type_code", "pitch_type"]),
        "batted_ball_types": pd.DataFrame(columns=["bb_type_code", "bb_type"]),
    }
    if detail_df.empty:
        return empty_bundle

    player_dimension_df = build_player_dimension_table(detail_df)

    team_dimension_df, team_codes = _build_code_dimension(detail_df["batting_team"], "team_id", "team", "Int8")
    event_dimension_df, event_codes = _build_code_dimension(detail_df["events"], "event_code", "event", "Int8")
    pitch_type_dimension_df, pitch_type_codes = _build_code_dimension(detail_df["pitch_type"], "pitch_type_code", "pitch_type", "Int8")
    bb_type_dimension_df, bb_type_codes = _build_code_dimension(detail_df["bb_type"], "bb_type_code", "bb_type", "Int8")

    core_df = detail_df[
        [
            "game_date",
            "game_pk",
            "at_bat_number",
            "pitch_number",
            "season",
            "month",
            "inning",
            "outs_when_up",
            "balls",
            "strikes",
            "batter",
            "pitcher",
            "zone",
        ]
    ].copy()
    core_df["batting_team_id"] = team_codes
    core_df["event_code"] = event_codes
    core_df["pitch_type_code"] = pitch_type_codes
    core_df["bb_type_code"] = bb_type_codes
    core_df = core_df[DETAIL_CORE_COLUMNS]

    tracking_df = detail_df[DETAIL_TRACKING_COLUMNS].copy()
    tracking_df = tracking_df[tracking_df[DETAIL_TRACKING_VALUE_COLUMNS].notna().any(axis=1)].reset_index(drop=True)

    return {
        "detail": core_df,
        "detail_tracking": tracking_df,
        "players": player_dimension_df,
        "teams": team_dimension_df,
        "event_types": event_dimension_df,
        "pitch_types": pitch_type_dimension_df,
        "batted_ball_types": bb_type_dimension_df,
    }


def _table_from_pandas_with_date32(table_df):
    import pandas as pd
    import pyarrow as pa

    table = pa.Table.from_pandas(table_df, preserve_index=False)
    if "game_date" not in table.column_names:
        return table

    date_series = table_df["game_date"]
    date_values = date_series.dt.date if pd.api.types.is_datetime64_any_dtype(date_series) else date_series
    date_index = table.column_names.index("game_date")
    date_array = pa.array(date_values, type=pa.date32())
    return table.set_column(date_index, "game_date", date_array)


def _write_partitioned_dataset(dataset_df, dataset_dir, compression: str, partition_mode: str) -> int:
    import pyarrow.dataset as ds

    if dataset_df.empty:
        dataset_dir.mkdir(parents=True, exist_ok=True)
        return 0

    table = _table_from_pandas_with_date32(dataset_df)
    partitioning = ["season"] if partition_mode == "season" else ["season", "month"]
    write_options = {"compression": compression}
    try:
        file_options = ds.ParquetFileFormat().make_write_options(use_dictionary=True, **write_options)
    except TypeError:
        file_options = ds.ParquetFileFormat().make_write_options(**write_options)
    ds.write_dataset(
        table,
        base_dir=str(dataset_dir),
        format="parquet",
        partitioning=partitioning,
        existing_data_behavior="delete_matching",
        max_rows_per_group=250_000,
        max_rows_per_file=500_000,
        file_options=file_options,
    )
    return len(dataset_df)


def _write_dimension_table(df, path, compression: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    parquet_compression = None if compression == "none" else compression
    if df.empty:
        return 0
    df.to_parquet(path, index=False, compression=parquet_compression)
    return len(df)


def normalize_detail_dataframe(detail_df):
    import pandas as pd

    if detail_df.empty:
        return pd.DataFrame(columns=DETAIL_WORKING_COLUMNS)

    normalized = detail_df.copy()

    normalized["batting_team"] = _derive_batting_team(normalized)

    for col in DETAIL_WORKING_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = pd.NA

    if "game_date" in normalized.columns:
        normalized["game_date"] = pd.to_datetime(normalized["game_date"], errors="coerce")

    for col in DETAIL_INTEGER_DTYPES:
        if col in normalized.columns:
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce").astype(DETAIL_INTEGER_DTYPES[col])

    for col in DETAIL_FLOAT_COLUMNS:
        if col in normalized.columns:
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce").astype("Float32")

    for col in DETAIL_LOW_CARDINALITY_COLUMNS:
        if col in normalized.columns:
            normalized[col] = normalized[col].astype("string").astype("category")

    if "player_name" in normalized.columns:
        normalized["player_name"] = normalized["player_name"].astype("string")

    return normalized[DETAIL_WORKING_COLUMNS].copy()


def fetch_detail_dataframe(config, windows: Iterable[Tuple[int, int, str, str]]) -> pd.DataFrame:
    import pandas as pd
    from progress import LocalProgressReporter

    windows = list(windows)
    reporter = LocalProgressReporter(getattr(config, "pretty_local_output", False))
    frames: List[pd.DataFrame] = []
    total_windows = len(windows)
    total_rows = 0
    total_mem_bytes = 0
    fetch_started = time.time()

    reporter.phase("Statcast Detail Fetch", f"{total_windows} window(s)")
    if reporter.enabled:
        reporter.card("Window Queue", _window_queue_entries(windows), tone="35")

    for idx, (year, month, start_dt, end_dt) in enumerate(windows, start=1):
        window_started = time.time()
        if reporter.enabled:
            reporter.progress("windows", idx - 1, total_windows, extra=f"starting {start_dt}..{end_dt}")
        else:
            print(f"Fetching Statcast detail for {start_dt} to {end_dt}")
        frame = _fetch_statcast_window(start_dt, end_dt, suppress_noise=reporter.enabled)

        if frame is None or frame.empty:
            if reporter.enabled:
                elapsed = max(0.001, time.time() - fetch_started)
                avg = elapsed / idx
                eta = avg * (total_windows - idx)
                projected_total = avg * total_windows
                reporter.progress(
                    "windows",
                    idx,
                    total_windows,
                    extra=f"{start_dt}..{end_dt} rows=0 eta={eta:0.1f}s total_est={_format_duration(projected_total)}",
                )
                next_label = _format_window_label(windows[idx]) if idx < total_windows else "none"
                completed = windows[:idx]
                remaining = windows[idx:]
                reporter.info(
                    f"completed={year}-{month:02d} done_years={_summarize_window_years(completed)} "
                    f"remaining_years={_summarize_window_years(remaining)} remaining={total_windows - idx} "
                    f"next={next_label} next_up={_preview_windows(remaining, limit=5)} "
                    f"finish_in={_format_duration(eta)} total_est={_format_duration(projected_total)}"
                )
            else:
                elapsed = max(0.001, time.time() - fetch_started)
                avg = elapsed / idx
                eta = avg * (total_windows - idx)
                print(
                    f"METRIC statcast_window_complete index={idx} total={total_windows} "
                    f"start={start_dt} end={end_dt} rows=0 elapsed_s={elapsed:0.1f} eta_s={eta:0.1f}"
                )
            continue

        if config.sample_mode and len(frame) > config.sample_max_rows:
            frame = frame.sample(n=config.sample_max_rows, random_state=config.sample_random_state)

        frame["season"] = year
        frame["month"] = f"{month:02d}"
        frame_mem_bytes = int(frame.memory_usage(index=True, deep=True).sum())
        total_rows += len(frame)
        total_mem_bytes += frame_mem_bytes
        frames.append(frame)

        if reporter.enabled:
            elapsed = max(0.001, time.time() - fetch_started)
            avg = elapsed / idx
            eta = avg * (total_windows - idx)
            projected_total = avg * total_windows
            took = time.time() - window_started
            reporter.progress(
                "windows",
                idx,
                total_windows,
                extra=(
                    f"{start_dt}..{end_dt} rows={len(frame)} mem={frame_mem_bytes / (1024 ** 2):0.1f}MB "
                    f"took={took:0.1f}s eta={eta:0.1f}s total_est={_format_duration(projected_total)}"
                ),
            )
            next_label = _format_window_label(windows[idx]) if idx < total_windows else "none"
            completed = windows[:idx]
            remaining = windows[idx:]
            reporter.info(
                f"completed={year}-{month:02d} done_years={_summarize_window_years(completed)} "
                f"remaining_years={_summarize_window_years(remaining)} remaining={total_windows - idx} "
                f"next={next_label} next_up={_preview_windows(remaining, limit=5)} "
                f"finish_in={_format_duration(eta)} total_est={_format_duration(projected_total)}"
            )
        else:
            elapsed = max(0.001, time.time() - fetch_started)
            avg = elapsed / idx
            eta = avg * (total_windows - idx)
            took = time.time() - window_started
            print(
                f"METRIC statcast_window_complete index={idx} total={total_windows} "
                f"start={start_dt} end={end_dt} rows={len(frame)} frame_bytes={frame_mem_bytes} "
                f"window_s={took:0.1f} elapsed_s={elapsed:0.1f} eta_s={eta:0.1f}"
            )

    if reporter.enabled:
        reporter.success(f"Statcast fetch complete: {total_rows} rows in {time.time() - fetch_started:0.1f}s")
    else:
        print(
            f"METRIC statcast_fetch_complete windows={total_windows} rows={total_rows} "
            f"frame_bytes_total={total_mem_bytes} elapsed_s={time.time() - fetch_started:0.1f}"
        )

    if not frames:
        return pd.DataFrame()

    detail_df = pd.concat(frames, ignore_index=True)
    return normalize_detail_dataframe(detail_df)


def write_detail_datasets(
    detail_df: pd.DataFrame,
    base_output_dir,
    compression: str = "snappy",
    partition_mode: str = "season_month",
    storage_tables: dict | None = None,
) -> dict:
    detail_dir = base_output_dir / "detail"
    detail_tracking_dir = base_output_dir / "detail_tracking"
    dimensions_dir = base_output_dir / "dimensions"

    storage_tables = storage_tables if storage_tables is not None else build_detail_storage_tables(detail_df)
    detail_rows = _write_partitioned_dataset(storage_tables["detail"], detail_dir, compression, partition_mode)
    detail_tracking_rows = _write_partitioned_dataset(storage_tables["detail_tracking"], detail_tracking_dir, compression, partition_mode)
    player_dimension_rows = _write_dimension_table(storage_tables["players"], dimensions_dir / "players.parquet", compression)
    team_dimension_rows = _write_dimension_table(storage_tables["teams"], dimensions_dir / "teams.parquet", compression)
    event_dimension_rows = _write_dimension_table(storage_tables["event_types"], dimensions_dir / "event_types.parquet", compression)
    pitch_type_dimension_rows = _write_dimension_table(storage_tables["pitch_types"], dimensions_dir / "pitch_types.parquet", compression)
    bb_type_dimension_rows = _write_dimension_table(storage_tables["batted_ball_types"], dimensions_dir / "batted_ball_types.parquet", compression)

    return {
        "detail_rows": detail_rows,
        "detail_tracking_rows": detail_tracking_rows,
        "player_dimension_rows": player_dimension_rows,
        "team_dimension_rows": team_dimension_rows,
        "event_dimension_rows": event_dimension_rows,
        "pitch_type_dimension_rows": pitch_type_dimension_rows,
        "bb_type_dimension_rows": bb_type_dimension_rows,
    }


def build_player_season_aggregates(
    detail_df: pd.DataFrame,
    source_system: str = "statcast",
    player_dimension_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    import pandas as pd

    if detail_df.empty:
        return pd.DataFrame(
            columns=[
                "batter",
                "player_name",
                "season",
                "plate_appearances",
                "at_bats",
                "hits",
                "singles",
                "doubles",
                "triples",
                "home_runs",
                "walks",
                "strikeouts",
                "sac_flies",
                "avg",
                "obp",
                "slg",
                "ops",
                "bb_rate",
                "k_rate",
                "k_bb_ratio",
                "iso",
                "xbh_rate",
                "hr_rate",
                "bb_minus_k_rate",
                "babip",
                "contact_rate",
                "runs_created",
                "source_system",
            ]
        )

    agg_source = detail_df[["batter", "events", "game_pk", "at_bat_number", "season"]].copy()
    agg_source["events"] = agg_source["events"].astype("string")
    agg_source["pa_key"] = (
        agg_source["game_pk"].astype("string")
        + "-"
        + agg_source["at_bat_number"].astype("string")
        + "-"
        + agg_source["batter"].astype("string")
    )

    agg_source["is_hit"] = _event_in(agg_source["events"], HIT_EVENTS).astype(int)
    agg_source["is_single"] = _event_equals(agg_source["events"], "single").astype(int)
    agg_source["is_double"] = _event_equals(agg_source["events"], "double").astype(int)
    agg_source["is_triple"] = _event_equals(agg_source["events"], "triple").astype(int)
    agg_source["is_hr"] = _event_equals(agg_source["events"], "home_run").astype(int)
    agg_source["is_walk"] = _event_in(agg_source["events"], {"walk", "intent_walk"}).astype(int)
    agg_source["is_strikeout"] = _event_in(agg_source["events"], {"strikeout", "strikeout_double_play"}).astype(int)
    agg_source["is_sac_fly"] = _event_equals(agg_source["events"], "sac_fly").astype(int)
    agg_source["is_ab"] = (agg_source["events"].notna() & ~_event_in(agg_source["events"], AB_EXCLUDED_EVENTS)).astype(int)

    grouped = (
        agg_source.groupby(["batter", "season"], dropna=False)
        .agg(
            plate_appearances=("pa_key", "nunique"),
            at_bats=("is_ab", "sum"),
            hits=("is_hit", "sum"),
            singles=("is_single", "sum"),
            doubles=("is_double", "sum"),
            triples=("is_triple", "sum"),
            home_runs=("is_hr", "sum"),
            walks=("is_walk", "sum"),
            strikeouts=("is_strikeout", "sum"),
            sac_flies=("is_sac_fly", "sum"),
        )
        .reset_index()
    )

    if player_dimension_df is None:
        player_dimension_df = build_player_dimension_table(detail_df)
    names = player_dimension_df[["batter", "player_name"]].drop_duplicates(subset=["batter"], keep="last")
    grouped = grouped.merge(names, on="batter", how="left")
    grouped = add_rate_stats(
        grouped,
        hits_col="hits",
        at_bats_col="at_bats",
        walks_col="walks",
        singles_col="singles",
        doubles_col="doubles",
        triples_col="triples",
        home_runs_col="home_runs",
    )
    grouped = add_advanced_batting_stats(
        grouped,
        plate_appearances_col="plate_appearances",
        at_bats_col="at_bats",
        hits_col="hits",
        walks_col="walks",
        strikeouts_col="strikeouts",
        singles_col="singles",
        doubles_col="doubles",
        triples_col="triples",
        home_runs_col="home_runs",
        sac_flies_col="sac_flies",
        avg_col="avg",
        slg_col="slg",
    )
    grouped["source_system"] = source_system
    return grouped[
        [
            "batter",
            "player_name",
            "season",
            "plate_appearances",
            "at_bats",
            "hits",
            "singles",
            "doubles",
            "triples",
            "home_runs",
            "walks",
            "strikeouts",
            "sac_flies",
            "avg",
            "obp",
            "slg",
            "ops",
            "bb_rate",
            "k_rate",
            "k_bb_ratio",
            "iso",
            "xbh_rate",
            "hr_rate",
            "bb_minus_k_rate",
            "babip",
            "contact_rate",
            "runs_created",
            "source_system",
        ]
    ]


def build_player_career_aggregates(player_season_df: pd.DataFrame) -> pd.DataFrame:
    import pandas as pd

    if player_season_df.empty:
        return pd.DataFrame(
            columns=[
                "batter",
                "player_name",
                "seasons",
                "career_plate_appearances",
                "career_at_bats",
                "career_hits",
                "career_singles",
                "career_doubles",
                "career_triples",
                "career_home_runs",
                "career_walks",
                "career_strikeouts",
                "career_sac_flies",
                "career_avg",
                "career_obp",
                "career_slg",
                "career_ops",
                "career_bb_rate",
                "career_k_rate",
                "career_k_bb_ratio",
                "career_iso",
                "career_xbh_rate",
                "career_hr_rate",
                "career_bb_minus_k_rate",
                "career_babip",
                "career_contact_rate",
                "career_runs_created",
                "career_hits_rank",
                "source_system",
            ]
        )

    career = (
        player_season_df.groupby(["batter", "player_name"], dropna=False)
        .agg(
            seasons=("season", "nunique"),
            career_plate_appearances=("plate_appearances", "sum"),
            career_at_bats=("at_bats", "sum"),
            career_hits=("hits", "sum"),
            career_singles=("singles", "sum"),
            career_doubles=("doubles", "sum"),
            career_triples=("triples", "sum"),
            career_home_runs=("home_runs", "sum"),
            career_walks=("walks", "sum"),
            career_strikeouts=("strikeouts", "sum"),
            career_sac_flies=("sac_flies", "sum"),
        )
        .reset_index()
    )

    career = add_rate_stats(
        career,
        hits_col="career_hits",
        at_bats_col="career_at_bats",
        walks_col="career_walks",
        singles_col="career_singles",
        doubles_col="career_doubles",
        triples_col="career_triples",
        home_runs_col="career_home_runs",
    )
    career = career.rename(
        columns={
            "avg": "career_avg",
            "obp": "career_obp",
            "slg": "career_slg",
            "ops": "career_ops",
        }
    )
    career = add_advanced_batting_stats(
        career,
        plate_appearances_col="career_plate_appearances",
        at_bats_col="career_at_bats",
        hits_col="career_hits",
        walks_col="career_walks",
        strikeouts_col="career_strikeouts",
        singles_col="career_singles",
        doubles_col="career_doubles",
        triples_col="career_triples",
        home_runs_col="career_home_runs",
        sac_flies_col="career_sac_flies",
        avg_col="career_avg",
        slg_col="career_slg",
        prefix="career_",
    )

    career["career_hits_rank"] = career["career_hits"].rank(method="dense", ascending=False).astype(int)
    return career.sort_values(["career_hits", "career_home_runs"], ascending=[False, False])


def build_team_season_aggregates(detail_df: pd.DataFrame, source_system: str = "statcast") -> pd.DataFrame:
    import pandas as pd

    if detail_df.empty:
        return pd.DataFrame(
            columns=[
                "team",
                "season",
                "plate_appearances",
                "at_bats",
                "hits",
                "singles",
                "doubles",
                "triples",
                "home_runs",
                "walks",
                "strikeouts",
                "sac_flies",
                "avg",
                "obp",
                "slg",
                "ops",
                "bb_rate",
                "k_rate",
                "k_bb_ratio",
                "iso",
                "xbh_rate",
                "hr_rate",
                "bb_minus_k_rate",
                "babip",
                "contact_rate",
                "runs_created",
                "source_system",
            ]
        )

    agg_source = detail_df[["events", "game_pk", "at_bat_number", "season", "batting_team"]].copy()
    agg_source["events"] = agg_source["events"].astype("string")
    agg_source["team"] = agg_source["batting_team"].astype("string")

    agg_source["pa_key"] = (
        agg_source["game_pk"].astype("string")
        + "-"
        + agg_source["at_bat_number"].astype("string")
        + "-"
        + agg_source["team"].astype("string")
    )
    agg_source["is_hit"] = _event_in(agg_source["events"], HIT_EVENTS).astype(int)
    agg_source["is_single"] = _event_equals(agg_source["events"], "single").astype(int)
    agg_source["is_double"] = _event_equals(agg_source["events"], "double").astype(int)
    agg_source["is_triple"] = _event_equals(agg_source["events"], "triple").astype(int)
    agg_source["is_hr"] = _event_equals(agg_source["events"], "home_run").astype(int)
    agg_source["is_walk"] = _event_in(agg_source["events"], {"walk", "intent_walk"}).astype(int)
    agg_source["is_strikeout"] = _event_in(agg_source["events"], {"strikeout", "strikeout_double_play"}).astype(int)
    agg_source["is_sac_fly"] = _event_equals(agg_source["events"], "sac_fly").astype(int)
    agg_source["is_ab"] = (agg_source["events"].notna() & ~_event_in(agg_source["events"], AB_EXCLUDED_EVENTS)).astype(int)

    grouped = (
        agg_source.groupby(["team", "season"], dropna=False)
        .agg(
            plate_appearances=("pa_key", "nunique"),
            at_bats=("is_ab", "sum"),
            hits=("is_hit", "sum"),
            singles=("is_single", "sum"),
            doubles=("is_double", "sum"),
            triples=("is_triple", "sum"),
            home_runs=("is_hr", "sum"),
            walks=("is_walk", "sum"),
            strikeouts=("is_strikeout", "sum"),
            sac_flies=("is_sac_fly", "sum"),
        )
        .reset_index()
    )
    grouped = add_rate_stats(
        grouped,
        hits_col="hits",
        at_bats_col="at_bats",
        walks_col="walks",
        singles_col="singles",
        doubles_col="doubles",
        triples_col="triples",
        home_runs_col="home_runs",
    )
    grouped = add_advanced_batting_stats(
        grouped,
        plate_appearances_col="plate_appearances",
        at_bats_col="at_bats",
        hits_col="hits",
        walks_col="walks",
        strikeouts_col="strikeouts",
        singles_col="singles",
        doubles_col="doubles",
        triples_col="triples",
        home_runs_col="home_runs",
        sac_flies_col="sac_flies",
        avg_col="avg",
        slg_col="slg",
    )
    grouped["source_system"] = source_system

    return grouped[
        [
            "team",
            "season",
            "plate_appearances",
            "at_bats",
            "hits",
            "singles",
            "doubles",
            "triples",
            "home_runs",
            "walks",
            "strikeouts",
            "sac_flies",
            "avg",
            "obp",
            "slg",
            "ops",
            "bb_rate",
            "k_rate",
            "k_bb_ratio",
            "iso",
            "xbh_rate",
            "hr_rate",
            "bb_minus_k_rate",
            "babip",
            "contact_rate",
            "runs_created",
            "source_system",
        ]
    ]


def build_team_career_aggregates(team_season_df: pd.DataFrame) -> pd.DataFrame:
    import pandas as pd

    if team_season_df.empty:
        return pd.DataFrame(
            columns=[
                "team",
                "seasons",
                "career_plate_appearances",
                "career_at_bats",
                "career_hits",
                "career_singles",
                "career_doubles",
                "career_triples",
                "career_home_runs",
                "career_walks",
                "career_strikeouts",
                "career_sac_flies",
                "career_avg",
                "career_obp",
                "career_slg",
                "career_ops",
                "career_bb_rate",
                "career_k_rate",
                "career_k_bb_ratio",
                "career_iso",
                "career_xbh_rate",
                "career_hr_rate",
                "career_bb_minus_k_rate",
                "career_babip",
                "career_contact_rate",
                "career_runs_created",
                "career_hits_rank",
                "source_system",
            ]
        )

    career = (
        team_season_df.groupby(["team"], dropna=False)
        .agg(
            seasons=("season", "nunique"),
            career_plate_appearances=("plate_appearances", "sum"),
            career_at_bats=("at_bats", "sum"),
            career_hits=("hits", "sum"),
            career_singles=("singles", "sum"),
            career_doubles=("doubles", "sum"),
            career_triples=("triples", "sum"),
            career_home_runs=("home_runs", "sum"),
            career_walks=("walks", "sum"),
            career_strikeouts=("strikeouts", "sum"),
            career_sac_flies=("sac_flies", "sum"),
        )
        .reset_index()
    )

    career = add_rate_stats(
        career,
        hits_col="career_hits",
        at_bats_col="career_at_bats",
        walks_col="career_walks",
        singles_col="career_singles",
        doubles_col="career_doubles",
        triples_col="career_triples",
        home_runs_col="career_home_runs",
    )
    career = career.rename(
        columns={
            "avg": "career_avg",
            "obp": "career_obp",
            "slg": "career_slg",
            "ops": "career_ops",
        }
    )
    career = add_advanced_batting_stats(
        career,
        plate_appearances_col="career_plate_appearances",
        at_bats_col="career_at_bats",
        hits_col="career_hits",
        walks_col="career_walks",
        strikeouts_col="career_strikeouts",
        singles_col="career_singles",
        doubles_col="career_doubles",
        triples_col="career_triples",
        home_runs_col="career_home_runs",
        sac_flies_col="career_sac_flies",
        avg_col="career_avg",
        slg_col="career_slg",
        prefix="career_",
    )

    career["career_hits_rank"] = career["career_hits"].rank(method="dense", ascending=False).astype(int)
    return career.sort_values(["career_hits", "career_home_runs"], ascending=[False, False])


def write_aggregate_tables(
    player_season_df: pd.DataFrame | None,
    player_career_df: pd.DataFrame | None,
    team_season_df: pd.DataFrame | None,
    team_career_df: pd.DataFrame | None,
    manager_season_df: pd.DataFrame | None,
    manager_career_df: pd.DataFrame | None,
    aggregates_dir,
    compression: str = "snappy",
) -> None:
    aggregates_dir.mkdir(parents=True, exist_ok=True)
    parquet_compression = None if compression == "none" else compression
    if player_season_df is not None:
        player_season_df.to_parquet(aggregates_dir / "player_season_metrics.parquet", index=False, compression=parquet_compression)
    if player_career_df is not None:
        player_career_df.to_parquet(aggregates_dir / "player_career_metrics.parquet", index=False, compression=parquet_compression)
    if team_season_df is not None:
        team_season_df.to_parquet(aggregates_dir / "team_season_metrics.parquet", index=False, compression=parquet_compression)
    if team_career_df is not None:
        team_career_df.to_parquet(aggregates_dir / "team_career_metrics.parquet", index=False, compression=parquet_compression)
    if manager_season_df is not None:
        manager_season_df.to_parquet(aggregates_dir / "manager_season_metrics.parquet", index=False, compression=parquet_compression)
    if manager_career_df is not None:
        manager_career_df.to_parquet(aggregates_dir / "manager_career_metrics.parquet", index=False, compression=parquet_compression)
