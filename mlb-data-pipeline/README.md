# Baseball Data Pipeline

This module builds detail and aggregate baseball datasets and publishes versioned Parquet snapshots to DigitalOcean Spaces.

Data coverage model:

- Statcast detail + aggregates: 2015 onward
- Lahman aggregates-only (no Statcast-style event detail): configurable historical seasons, default 1871-2014

The Python modules live directly under `src/` and the top-level `download_and_convert.py` file is only a thin CLI wrapper.

The first run is designed to be a full historical load. After that, the Kubernetes CronJob runs in incremental mode and refreshes the newest data plus a one-month trailer so late corrections get picked up.

Jupyter users can start from the shared notebook template copied into their workspace as `MLB_Data_Starter.ipynb`.

## Outputs

- Detail core dataset: partitioned by `season` and `month`
- Detail tracking dataset: partitioned by `season` and `month`
- Dimension dataset: `players.parquet`
- Dimension dataset: `teams.parquet`
- Dimension dataset: `event_types.parquet`
- Dimension dataset: `pitch_types.parquet`
- Dimension dataset: `batted_ball_types.parquet`
- Aggregate dataset: `player_season_metrics.parquet`
- Aggregate dataset: `player_career_metrics.parquet`
- Aggregate dataset: `team_season_metrics.parquet`
- Aggregate dataset: `team_career_metrics.parquet`
- Aggregate dataset: `manager_season_metrics.parquet`
- Aggregate dataset: `manager_career_metrics.parquet`
- Snapshot manifest: `manifest.json`
- Latest pointer: `latest.json`

The detail layer is now split into a compact core Statcast table plus a separate tracking sidecar. The core table keeps query-facing identifiers, game context, and encoded outcome fields. The tracking sidecar holds optional pitch-flight and contact measurements keyed by the same pitch identity fields.

Repeated entities and low-cardinality values are normalized rather than repeated row-by-row: player names live in `players.parquet`, team abbreviations live in `teams.parquet`, and enum-like fields such as events, pitch types, and batted-ball types are stored as integer codes with dimension tables.

The core detail table stores `game_date` as a date-only value, keeps `batting_team` in normalized ID form instead of storing both `home_team` and `away_team`, and writes tracking measurements as `float32` values to cut disk usage further.

Player and team aggregate outputs include counting stats plus query-friendly rate stats: `avg`, `obp`, `slg`, and `ops` (with career-prefixed variants in career tables).

Manager aggregate outputs are sourced from Lahman managerial records and include season/career wins, losses, winning percentage, games above .500, and ranking by career wins.

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
make -C mlb-data-pipeline run-bootstrap-job IMAGE_REPO=docker.io/<dockerhub-user>/mlb-data-pipeline
```

Apply weekly refresh cronjob:

```bash
make -C mlb-data-pipeline apply-cronjob IMAGE_REPO=docker.io/<dockerhub-user>/mlb-data-pipeline
```

## Make Targets

- `docker`: build the local Docker image
- `publish`: tag and push the Docker image to `IMAGE_REPO`
- `local-install`: create/update the local virtualenv and install Python dependencies
- `local-wizard`: interactive terminal wizard for choosing local/sample/bootstrap/upload run modes
- `bootstrap-estimate`: print the planned bootstrap window count and a rough runtime estimate for this machine
- `local-run`: run locally and write parquet only to `OUTPUT_DIR` with upload forced off
- `local-run-upload`: run locally, write parquet to `OUTPUT_DIR`, and upload to Spaces when `SPACES_*` is configured
- `local-bootstrap`: full historical local bootstrap with upload forced off
- `local-bootstrap-upload`: full historical local bootstrap plus upload to Spaces
- `local-bootstrap-zstd`: full historical local bootstrap with `PARQUET_COMPRESSION=zstd`
- `local-bootstrap-zstd-upload`: full historical local bootstrap with zstd compression and upload to Spaces
- `local-run-sample`: local sample/debug run with upload forced off
- `local-run-docker`: run the container locally with a bind-mounted output directory and upload forced off
- `local-run-sample-docker`: sampled Docker run with a bind-mounted output directory and upload forced off
- `local-run-detail-only`: write only detail dataset output (no aggregate parquet files)
- `local-run-aggregates-only`: write only aggregate parquet outputs (no detail dataset files)
- `local-run-player-season`: write only player season aggregate output
- `local-run-team-career`: write only team career aggregate output
- `local-run-manager-season`: write only manager season aggregate output
- `local-run-manager-career`: write only manager career aggregate output

Manager-only targets set `LAHMAN_ENABLED=true` automatically.
- `test`: run the Python test suite
- `run-bootstrap-job`: render and apply the one-off Kubernetes bootstrap job
- `run-job`: alias for the same rendered one-off bootstrap job
- `apply-cronjob`: render and apply the incremental Kubernetes CronJob
- `apply-spaces-secret-example`: apply the example Spaces secret manifest
- `clean`: remove rendered Kubernetes manifests

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

If you want the terminal to ask what kind of run you want instead of remembering target names, use:

```bash
make -C mlb-data-pipeline local-wizard
```

If you want a quick estimate before starting a full first bootstrap, use:

```bash
make -C mlb-data-pipeline bootstrap-estimate
```

`local-run`, `local-bootstrap`, and the sample local targets force `UPLOAD_ENABLED=false`, so they stay local even if `SPACES_*` variables are already exported in your shell.

Full local historical backfill for this pipeline (Lahman pre-2015 + Statcast 2015+):

```bash
# Baseball predates Statcast. Enable Lahman to fill pre-2015 aggregates.
make -C mlb-data-pipeline local-bootstrap \
	PYTHON=python3.12 \
	OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

For the smallest practical local footprint while keeping the full historical run intact, prefer zstd:

```bash
make -C mlb-data-pipeline local-bootstrap-zstd \
	PYTHON=python3.12 \
	OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

`PARQUET_COMPRESSION` is configurable and defaults to `snappy`. Valid options are `none`, `snappy`, `gzip`, `brotli`, `lz4`, and `zstd`. Compression still matters, but the biggest storage wins now come from the split core/tracking schema, narrower integer and `float32` types, and dictionary-friendly normalization of repeated dimensions.

Expected bootstrap runtime on a current developer Mac:

- The full `local-bootstrap` path does **not** fetch monthly data back to 1871.
- Statcast detail begins in 2015, so as of 2026-09-19 the bootstrap fetch plan is about `141` monthly Statcast windows.
- Lahman covers pre-2015 historical aggregates and is typically much cheaper than the Statcast fetch.
- Based on observed local timing where active in-season months take roughly `10-20s` each and offseason months are much lighter, a cold first bootstrap on this machine should be expected to take roughly `30-60 minutes`.
- Treat `60-90 minutes` as a safer upper-bound if Baseball Savant is slow, your network is noisy, or the machine is busy with other work.

Estimated output size and file count for a full historical run:

- Full historical bootstrap = Statcast detail for 2015-present + Lahman aggregate history for 1871-2014.
- The detail core and tracking datasets are partitioned by `season` and `month`, and the writer splits files at `max_rows_per_group=250_000` and `max_rows_per_file=500_000`.
- The canonical Statcast storage layer no longer repeats player names, raw team strings, or verbose enum strings in every row, and it drops several exploratory derived metrics from the written detail snapshots.
- In practice, the detail dataset usually lands in the rough range of `600-1,500` Parquet files for the full historical run, depending on month-by-month Statcast volume and how many rows each partition contains.
- The aggregate outputs add a small fixed cost: about `6` parquet files for the main aggregate tables, plus the snapshot manifest and pointer files.
- The Lahman historical layer is tiny compared to Statcast detail; it adds a modest historical aggregate footprint but does not materially change the size profile of the full run.
- With the default compression (`snappy`), a full historical local snapshot is typically on the order of `115-210 GB` on disk. With `PARQUET_COMPRESSION=zstd`, expect roughly `55-130 GB` depending on dataset variance and how much of the snapshot is detail data.
- The latest schema pass (player-name decoupling through `players.parquet` reuse and additional `Int8` narrowing for pitch/event encodings) generally trims another small slice from core detail storage, usually around `1-3%` versus the prior compact schema baseline.
- A typical monthly add/update run usually writes `2-20` parquet files for the detail partition that month, plus the aggregate parquet files, and lands in roughly `3-12 GB` of new detail data for one month with `zstd`, or `5-18 GB` without it.
- Due to the month-partitioned structure, the incremental job tends to be dominated by the latest Statcast month(s), not by Lahman history.

This is why the recommended local developer workflow is to run a full historical bootstrap with `zstd` once and then use incremental monthly refreshes for ongoing updates.

The pretty local output will show the planned years, current window, completed window, remaining years, and next windows so you can see whether the run is progressing at the rate you expect.
During the fetch loop, pretty local output also shows a rolling `total_est` and `finish_in` projection based on the average time of completed windows so far.

Bootstrap locally and publish the initial snapshot to the same Spaces bucket and prefix that the CronJob will later read:

```bash
cd mlb-data-pipeline
export SPACES_BUCKET=your-bucket
export SPACES_REGION=your-region
export SPACES_ENDPOINT=https://your-region.digitaloceanspaces.com
export SPACES_ACCESS_KEY_ID=your-access-key
export SPACES_SECRET_ACCESS_KEY=your-secret-key
make local-bootstrap-upload PYTHON=python3.12 OUTPUT_DIR=$(pwd)/output
```

That bootstrap run must upload `latest.json` and the snapshot manifest to Spaces. The scheduled incremental job depends on those files to avoid falling back to a first-pass build.

At startup, the pipeline now runs a storage preflight: it fails on partial `SPACES_*` configuration, verifies bucket access when Spaces is enabled, and reports whether the target already has `latest.json`.

Uploads are now explicit. Use `local-run-upload` or `local-bootstrap-upload` when you intend to publish to Spaces. Use `local-run` or `local-bootstrap` when you intend to stay local only.

The Docker-based local targets are also local-only by default. If you ever want a Docker-based local upload target, add one intentionally rather than relying on inherited shell state.

Local runs use pretty progress output by default (phase markers, color, progress bars, ETA).
Disable it for plain logs:

```bash
make -C mlb-data-pipeline local-run PRETTY_LOCAL_OUTPUT=false
```

Kubernetes job logging stays plain text unless you explicitly set `PRETTY_LOCAL_OUTPUT=true` there.
Plain logs and Kubernetes runs emit structured metric lines (prefixed with `METRIC`) and a final one-line `SUMMARY` for easier log scraping. Pretty local output favors colored phase headers, progress bars, and summary cards instead.
Pretty local output also shows:

- planned years and window counts before fetch starts
- a preview of the next windows in queue
- after each completed window, the finished month, remaining window count, remaining years, and the next few windows

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

Protect an incremental run from accidentally turning into a first-pass historical build:

```bash
make -C mlb-data-pipeline local-run \
	PYTHON=python3.12 \
	START_SEASON=2015 \
	END_SEASON=$(date +%Y) \
	INCREMENTAL_MODE=true \
	REQUIRE_EXISTING_SNAPSHOT=true \
	TRAILER_MONTHS=1 \
	OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

This is the recommended setting for low-memory scheduled jobs after you have already published an initial snapshot.

For DOKS, keep the CronJob on the incremental path only. The checked-in CronJob now sets `REQUIRE_EXISTING_SNAPSHOT=true` and uses a 1 GiB memory request/limit. If the bootstrap snapshot is missing, the job will fail fast instead of attempting a historical rebuild.

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
- `PARQUET_COMPRESSION` default `snappy` (`none`, `snappy`, `gzip`, `brotli`, `lz4`, `zstd`)
- `OUTPUT_DIR` default `/tmp/output`
- `DATASET_PREFIX` default `baseball`
- `UPLOAD_ENABLED` default `false` (`true` is required before any Spaces upload will happen, even if `SPACES_*` variables are set)
- `INCREMENTAL_MODE` default `true`
- `REQUIRE_EXISTING_SNAPSHOT` default `false` (`true` makes incremental runs fail fast instead of falling back to a first-pass historical build)
- `TRAILER_MONTHS` default `1`
- `STATCAST_START_SEASON` default `2015`
- `LAHMAN_ENABLED` default `false`
- `LAHMAN_START_SEASON` default `1871`
- `LAHMAN_END_SEASON` default `2014`
- `LAHMAN_PLAYER_MAPPING_PATH` optional path to CSV with `playerID` and one of `batter|mlbam_id|mlbamid|key_mlbam`
- `LAHMAN_INCLUDE_OVERLAP` default `false` (when false, Lahman contributes pre-Statcast seasons only)
- `SOURCE_OVERLAP_POLICY` default `statcast_preferred` (`statcast_preferred` or `lahman_preferred`)
- `PRETTY_LOCAL_OUTPUT` default `false` (Make `local-run` targets set it to `true`; k8s manifests remain unchanged)
- `INCLUDE_DETAIL_DATASET` default `true` (when `false`, the detail parquet dataset is not written)
- `INCLUDE_AGGREGATE_DATASETS` default `true` (when `false`, no aggregate parquet files are written)
- `INCLUDE_PLAYER_AGGREGATES` default `true`
- `INCLUDE_TEAM_AGGREGATES` default `true`
- `INCLUDE_MANAGER_AGGREGATES` default `true`
- `INCLUDE_SEASON_AGGREGATES` default `true`
- `INCLUDE_CAREER_AGGREGATES` default `true`
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

Uploads require both `UPLOAD_ENABLED=true` and a complete `SPACES_*` configuration. Otherwise, the script writes local Parquet outputs under `OUTPUT_DIR` only.
