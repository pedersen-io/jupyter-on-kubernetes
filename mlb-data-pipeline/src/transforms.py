from __future__ import annotations

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


def fetch_detail_dataframe(config, windows: Iterable[Tuple[int, int, str, str]]) -> pd.DataFrame:
    import pandas as pd
    from pybaseball import statcast

    frames: List[pd.DataFrame] = []

    for year, month, start_dt, end_dt in windows:
        print(f"Fetching Statcast detail for {start_dt} to {end_dt}")
        frame = statcast(start_dt=start_dt, end_dt=end_dt, verbose=False)

        if frame is None or frame.empty:
            continue

        if config.sample_mode and len(frame) > config.sample_max_rows:
            frame = frame.sample(n=config.sample_max_rows, random_state=config.sample_random_state)

        frame["season"] = year
        frame["month"] = f"{month:02d}"
        frames.append(frame)

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
                "avg",
                "obp",
                "slg",
                "ops",
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

    agg_source["is_hit"] = agg_source["events"].isin(HIT_EVENTS).astype(int)
    agg_source["is_single"] = (agg_source["events"] == "single").astype(int)
    agg_source["is_double"] = (agg_source["events"] == "double").astype(int)
    agg_source["is_triple"] = (agg_source["events"] == "triple").astype(int)
    agg_source["is_hr"] = (agg_source["events"] == "home_run").astype(int)
    agg_source["is_walk"] = agg_source["events"].isin({"walk", "intent_walk"}).astype(int)
    agg_source["is_strikeout"] = agg_source["events"].isin({"strikeout", "strikeout_double_play"}).astype(int)
    agg_source["is_ab"] = (~agg_source["events"].isin(AB_EXCLUDED_EVENTS)).astype(int)

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
            "avg",
            "obp",
            "slg",
            "ops",
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
                "career_avg",
                "career_obp",
                "career_slg",
                "career_ops",
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
                "avg",
                "obp",
                "slg",
                "ops",
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
    agg_source["is_hit"] = agg_source["events"].isin(HIT_EVENTS).astype(int)
    agg_source["is_single"] = (agg_source["events"] == "single").astype(int)
    agg_source["is_double"] = (agg_source["events"] == "double").astype(int)
    agg_source["is_triple"] = (agg_source["events"] == "triple").astype(int)
    agg_source["is_hr"] = (agg_source["events"] == "home_run").astype(int)
    agg_source["is_walk"] = agg_source["events"].isin({"walk", "intent_walk"}).astype(int)
    agg_source["is_strikeout"] = agg_source["events"].isin({"strikeout", "strikeout_double_play"}).astype(int)
    agg_source["is_ab"] = (~agg_source["events"].isin(AB_EXCLUDED_EVENTS)).astype(int)

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
            "avg",
            "obp",
            "slg",
            "ops",
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
                "career_avg",
                "career_obp",
                "career_slg",
                "career_ops",
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

    career["career_hits_rank"] = career["career_hits"].rank(method="dense", ascending=False).astype(int)
    return career.sort_values(["career_hits", "career_home_runs"], ascending=[False, False])


def write_aggregate_tables(
    player_season_df: pd.DataFrame,
    player_career_df: pd.DataFrame,
    team_season_df: pd.DataFrame,
    team_career_df: pd.DataFrame,
    aggregates_dir,
) -> None:
    aggregates_dir.mkdir(parents=True, exist_ok=True)
    player_season_df.to_parquet(aggregates_dir / "player_season_metrics.parquet", index=False)
    player_career_df.to_parquet(aggregates_dir / "player_career_metrics.parquet", index=False)
    team_season_df.to_parquet(aggregates_dir / "team_season_metrics.parquet", index=False)
    team_career_df.to_parquet(aggregates_dir / "team_career_metrics.parquet", index=False)
