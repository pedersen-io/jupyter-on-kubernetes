from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from transforms import add_rate_stats


def _require_columns(df: pd.DataFrame, required: list[str], table_name: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"{table_name} is missing required columns: {', '.join(missing)}")


def _load_mapping(path: Optional[Path]) -> Tuple[Optional[pd.DataFrame], dict]:
    quality = {
        "mapping_file_rows": 0,
        "mapping_file_player_ids": 0,
        "ambiguous_player_ids": 0,
    }

    if path is None:
        return None, quality

    mapping = pd.read_csv(path)
    quality["mapping_file_rows"] = int(len(mapping))
    if "playerID" not in mapping.columns:
        raise ValueError("LAHMAN_PLAYER_MAPPING_PATH must include a 'playerID' column")

    candidate_cols = ["batter", "mlbam_id", "mlbamid", "key_mlbam"]
    mapped_col = next((col for col in candidate_cols if col in mapping.columns), None)
    if mapped_col is None:
        raise ValueError(
            "LAHMAN_PLAYER_MAPPING_PATH must include one of: batter, mlbam_id, mlbamid, key_mlbam"
        )

    normalized = mapping[["playerID", mapped_col]].copy()
    normalized["playerID"] = normalized["playerID"].astype("string")
    normalized = normalized.rename(columns={mapped_col: "mapped_batter"})
    normalized["mapped_batter"] = normalized["mapped_batter"].apply(_normalize_mapped_batter)

    quality["mapping_file_player_ids"] = int(normalized["playerID"].dropna().nunique())
    non_empty = normalized.dropna(subset=["playerID", "mapped_batter"])
    ambiguous = non_empty.groupby("playerID")["mapped_batter"].nunique()
    quality["ambiguous_player_ids"] = int((ambiguous > 1).sum())

    normalized = normalized.drop_duplicates(subset=["playerID"], keep="first")
    return normalized, quality


def _normalize_mapped_batter(value):
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if text == "":
        return pd.NA
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _prepare_lahman_batting(start_season: int, end_season: int) -> pd.DataFrame:
    from pybaseball import lahman

    batting = lahman.batting()
    _require_columns(batting, ["playerID", "yearID", "teamID", "AB", "H", "2B", "3B", "HR", "BB", "SO"], "Lahman batting")

    filtered = batting[(batting["yearID"] >= start_season) & (batting["yearID"] <= end_season)].copy()
    if filtered.empty:
        return filtered

    for col in ["AB", "H", "2B", "3B", "HR", "BB", "SO", "HBP", "SF", "SH"]:
        if col not in filtered.columns:
            filtered[col] = 0
        filtered[col] = filtered[col].fillna(0)

    filtered["singles"] = (filtered["H"] - filtered["2B"] - filtered["3B"] - filtered["HR"]).clip(lower=0)
    filtered["season"] = filtered["yearID"].astype(int)
    filtered["plate_appearances"] = (
        filtered["AB"] + filtered["BB"] + filtered["HBP"] + filtered["SF"] + filtered["SH"]
    ).astype(int)

    return filtered


def _load_player_names() -> pd.DataFrame:
    from pybaseball import lahman

    people = lahman.people()
    _require_columns(people, ["playerID", "nameFirst", "nameLast"], "Lahman people")

    names = people[["playerID", "nameFirst", "nameLast"]].copy()
    names["nameFirst"] = names["nameFirst"].fillna("").astype("string")
    names["nameLast"] = names["nameLast"].fillna("").astype("string")
    names["player_name"] = (names["nameFirst"].str.strip() + " " + names["nameLast"].str.strip()).str.strip()
    names["player_name"] = names["player_name"].where(names["player_name"] != "", names["playerID"])
    return names[["playerID", "player_name"]]


def build_lahman_player_season_aggregates(
    start_season: int,
    end_season: int,
    mapping_path: Optional[Path],
) -> pd.DataFrame:
    aggregates, _ = build_lahman_player_season_aggregates_with_quality(
        start_season=start_season,
        end_season=end_season,
        mapping_path=mapping_path,
    )
    return aggregates


def build_lahman_player_season_aggregates_with_quality(
    start_season: int,
    end_season: int,
    mapping_path: Optional[Path],
) -> Tuple[pd.DataFrame, dict]:
    batting = _prepare_lahman_batting(start_season, end_season)
    if batting.empty:
        return (
            pd.DataFrame(
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
            ),
            {
                "mapping_file_rows": 0,
                "mapping_file_player_ids": 0,
                "ambiguous_player_ids": 0,
                "player_ids_in_output": 0,
                "mapped_player_ids_in_output": 0,
                "unmapped_player_ids_in_output": 0,
            },
        )

    names = _load_player_names()
    mapping, mapping_quality = _load_mapping(mapping_path)

    grouped = (
        batting.groupby(["playerID", "season"], dropna=False)
        .agg(
            plate_appearances=("plate_appearances", "sum"),
            at_bats=("AB", "sum"),
            hits=("H", "sum"),
            singles=("singles", "sum"),
            doubles=("2B", "sum"),
            triples=("3B", "sum"),
            home_runs=("HR", "sum"),
            walks=("BB", "sum"),
            strikeouts=("SO", "sum"),
        )
        .reset_index()
    )

    grouped = grouped.merge(names, on="playerID", how="left")
    grouped["player_name"] = grouped["player_name"].fillna(grouped["playerID"]).astype("string")

    mapped_count = 0
    if mapping is not None:
        grouped = grouped.merge(mapping, on="playerID", how="left")
        mapped_count = int(grouped.loc[grouped["mapped_batter"].notna(), "playerID"].dropna().nunique())
        grouped["batter"] = grouped["mapped_batter"].fillna("lahman:" + grouped["playerID"].astype("string"))
        grouped = grouped.drop(columns=["mapped_batter"])
    else:
        grouped["batter"] = "lahman:" + grouped["playerID"].astype("string")

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
    grouped["source_system"] = "lahman"

    player_id_count = int(grouped["playerID"].dropna().nunique())
    mapping_quality["player_ids_in_output"] = player_id_count
    mapping_quality["mapped_player_ids_in_output"] = mapped_count
    mapping_quality["unmapped_player_ids_in_output"] = max(player_id_count - mapped_count, 0)

    output = grouped[
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
    return output, mapping_quality


def build_lahman_team_season_aggregates(start_season: int, end_season: int) -> pd.DataFrame:
    batting = _prepare_lahman_batting(start_season, end_season)
    if batting.empty:
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

    grouped = (
        batting.groupby(["teamID", "season"], dropna=False)
        .agg(
            plate_appearances=("plate_appearances", "sum"),
            at_bats=("AB", "sum"),
            hits=("H", "sum"),
            singles=("singles", "sum"),
            doubles=("2B", "sum"),
            triples=("3B", "sum"),
            home_runs=("HR", "sum"),
            walks=("BB", "sum"),
            strikeouts=("SO", "sum"),
        )
        .reset_index()
        .rename(columns={"teamID": "team"})
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
    grouped["source_system"] = "lahman"

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
