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

    expected_cols = [
        "batter",
        "player_name",
        "events",
        "game_pk",
        "at_bat_number",
        "season",
        "month",
        "inning_topbot",
        "home_team",
        "away_team",
    ]
    for col in expected_cols:
        if col not in detail_df.columns:
            detail_df[col] = pd.NA

    return detail_df


def write_detail_dataset(detail_df: pd.DataFrame, detail_dir) -> int:
    import pyarrow as pa
    import pyarrow.dataset as ds

    if detail_df.empty:
        detail_dir.mkdir(parents=True, exist_ok=True)
        return 0

    table = pa.Table.from_pandas(detail_df, preserve_index=False)
    ds.write_dataset(
        table,
        base_dir=str(detail_dir),
        format="parquet",
        partitioning=["season", "month"],
        existing_data_behavior="delete_matching",
        max_rows_per_group=250_000,
        max_rows_per_file=500_000,
    )

    return len(detail_df)


def build_player_season_aggregates(detail_df: pd.DataFrame, source_system: str = "statcast") -> pd.DataFrame:
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

    agg_source = detail_df[["batter", "player_name", "events", "game_pk", "at_bat_number", "season"]].copy()
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

    names = (
        agg_source.dropna(subset=["player_name"])
        .groupby("batter", dropna=False)["player_name"]
        .last()
        .reset_index()
    )

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

    agg_source = detail_df[
        ["events", "game_pk", "at_bat_number", "season", "inning_topbot", "home_team", "away_team"]
    ].copy()
    agg_source["events"] = agg_source["events"].astype("string")

    # Derive batting team from inning half; fallback to home team when inning data is missing.
    agg_source["team"] = agg_source["home_team"].astype("string")
    agg_source.loc[agg_source["inning_topbot"] == "Top", "team"] = agg_source["away_team"].astype("string")

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
) -> None:
    aggregates_dir.mkdir(parents=True, exist_ok=True)
    if player_season_df is not None:
        player_season_df.to_parquet(aggregates_dir / "player_season_metrics.parquet", index=False)
    if player_career_df is not None:
        player_career_df.to_parquet(aggregates_dir / "player_career_metrics.parquet", index=False)
    if team_season_df is not None:
        team_season_df.to_parquet(aggregates_dir / "team_season_metrics.parquet", index=False)
    if team_career_df is not None:
        team_career_df.to_parquet(aggregates_dir / "team_career_metrics.parquet", index=False)
    if manager_season_df is not None:
        manager_season_df.to_parquet(aggregates_dir / "manager_season_metrics.parquet", index=False)
    if manager_career_df is not None:
        manager_career_df.to_parquet(aggregates_dir / "manager_career_metrics.parquet", index=False)
