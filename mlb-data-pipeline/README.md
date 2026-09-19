# Baseball Data Pipeline

This module builds detail and aggregate baseball datasets and publishes versioned Parquet snapshots to DigitalOcean Spaces.

Data coverage model:

- Statcast detail + aggregates: 2015 onward
- Lahman aggregates-only (no Statcast-style event detail): configurable historical seasons, default 1871-2014

The Python modules live directly under `src/` and the top-level `download_and_convert.py` file is only a thin CLI wrapper.

The first run is designed to be a full historical load. After that, the Kubernetes CronJob runs in incremental mode and refreshes the newest data plus a one-month trailer so late corrections get picked up.

Jupyter users can start from the shared notebook template copied into their workspace as `MLB_Data_Starter.ipynb`.

## Outputs

- Detail dataset: partitioned by `season` and `month`
- Aggregate dataset: `player_season_metrics.parquet`
- Aggregate dataset: `player_career_metrics.parquet`
- Aggregate dataset: `team_season_metrics.parquet`
- Aggregate dataset: `team_career_metrics.parquet`
- Snapshot manifest: `manifest.json`
- Latest pointer: `latest.json`

Player and team aggregate outputs include counting stats plus query-friendly rate stats: `avg`, `obp`, `slg`, and `ops` (with career-prefixed variants in career tables).

## Quick Start

Build image:

```bash
make -C mlb-data-pipeline docker
```

Publish image:

```bash
make -C mlb-data-pipeline publish IMAGE_REPO=docker.io/<dockerhub-user>/mlb-data-pipeline
```

Run one-off refresh job:

```bash
kubectl apply -f mlb-data-pipeline/spaces-secret.example.yaml
make -C mlb-data-pipeline run-job IMAGE_REPO=docker.io/<dockerhub-user>/mlb-data-pipeline
```

Apply weekly refresh cronjob:

```bash
make -C mlb-data-pipeline apply-cronjob IMAGE_REPO=docker.io/<dockerhub-user>/mlb-data-pipeline
```

## Local Testing

Run directly on your machine and write outputs locally:

```bash
# Creates/updates ./mlb-data-pipeline/.venv and installs deps there.
make -C mlb-data-pipeline local-install

# Optional: activate the venv for ad-hoc Python commands.
source mlb-data-pipeline/.venv/bin/activate

# Generates parquet snapshot outputs under OUTPUT_DIR.
make -C mlb-data-pipeline local-run START_SEASON=2024 END_SEASON=2024 OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

Full local historical backfill for this pipeline (Lahman pre-2015 + Statcast 2015+):

```bash
# Baseball predates Statcast. Enable Lahman to fill pre-2015 aggregates.
make -C mlb-data-pipeline local-run \
	PYTHON=python3.12 \
	START_SEASON=1871 \
	END_SEASON=$(date +%Y) \
	LAHMAN_ENABLED=true \
	INCREMENTAL_MODE=false \
	OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

Continue filling any missing historical months in an existing local dataset:

```bash
make -C mlb-data-pipeline local-run \
	PYTHON=python3.12 \
	START_SEASON=2015 \
	END_SEASON=$(date +%Y) \
	LAHMAN_ENABLED=true \
	INCREMENTAL_MODE=true \
	TRAILER_MONTHS=1 \
	OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

Optional explicit player mapping for cross-source identity stitching:

```bash
make -C mlb-data-pipeline local-run \
	PYTHON=python3.12 \
	START_SEASON=1871 \
	END_SEASON=$(date +%Y) \
	LAHMAN_ENABLED=true \
	LAHMAN_PLAYER_MAPPING_PATH=$(pwd)/mlb-data-pipeline/player_mapping.csv \
	INCREMENTAL_MODE=false \
	OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

Note: if your default `python3` is 3.14+, install and use Python 3.12 for this pipeline so `pyarrow` can install from wheels:

```bash
brew install python@3.12
make -C mlb-data-pipeline local-install PYTHON=python3.12
make -C mlb-data-pipeline local-run START_SEASON=2024 END_SEASON=2024 OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

Fast sampling run for debugging (caps windows and rows):

```bash
make -C mlb-data-pipeline local-run-sample START_SEASON=2024 END_SEASON=2024 SAMPLE_MAX_WINDOWS=1 SAMPLE_MAX_ROWS=5000 OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

Date-range sample run (exact window):

```bash
make -C mlb-data-pipeline local-run SAMPLE_MODE=true SAMPLE_START_DATE=2024-04-01 SAMPLE_END_DATE=2024-04-07 SAMPLE_MAX_ROWS=5000 OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

Run inside Docker and write outputs locally through a bind mount:

```bash
make -C mlb-data-pipeline local-run-docker START_SEASON=2024 END_SEASON=2024 OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

Sample mode inside Docker:

```bash
make -C mlb-data-pipeline local-run-sample-docker START_SEASON=2024 END_SEASON=2024 SAMPLE_MAX_WINDOWS=1 SAMPLE_MAX_ROWS=5000 OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

When Spaces credentials are not provided, outputs are written locally only.

For local first-pass loads, leave `INCREMENTAL_MODE=false` or omit it.

For local incremental test runs that mimic the CronJob, set:

```bash
INCREMENTAL_MODE=true TRAILER_MONTHS=1
```

## Environment Variables

- `START_SEASON` default `2015`
- `END_SEASON` default current year
- `OUTPUT_DIR` default `/tmp/output`
- `DATASET_PREFIX` default `baseball`
- `INCREMENTAL_MODE` default `true`
- `TRAILER_MONTHS` default `1`
- `STATCAST_START_SEASON` default `2015`
- `LAHMAN_ENABLED` default `false`
- `LAHMAN_START_SEASON` default `1871`
- `LAHMAN_END_SEASON` default `2014`
- `LAHMAN_PLAYER_MAPPING_PATH` optional path to CSV with `playerID` and one of `batter|mlbam_id|mlbamid|key_mlbam`
- `LAHMAN_INCLUDE_OVERLAP` default `false` (when false, Lahman contributes pre-Statcast seasons only)
- `SOURCE_OVERLAP_POLICY` default `statcast_preferred` (`statcast_preferred` or `lahman_preferred`)
- `SAMPLE_MODE` default `false`
- `SAMPLE_START_DATE` optional `YYYY-MM-DD` (must be set with `SAMPLE_END_DATE`)
- `SAMPLE_END_DATE` optional `YYYY-MM-DD` (must be set with `SAMPLE_START_DATE`)
- `SAMPLE_MAX_ROWS` default `20000` rows per pulled window when sample mode is enabled
- `SAMPLE_MAX_WINDOWS` default `2` monthly windows when sample mode is enabled without explicit dates
- `SAMPLE_RANDOM_STATE` default `42` for reproducible sampling
- `SPACES_BUCKET` required for upload
- `SPACES_REGION` required for upload
- `SPACES_ENDPOINT` required for upload, e.g. `https://nyc3.digitaloceanspaces.com`
- `SPACES_ACCESS_KEY_ID` required for upload
- `SPACES_SECRET_ACCESS_KEY` required for upload

If Spaces variables are omitted, the script still writes local Parquet outputs under `OUTPUT_DIR`.
