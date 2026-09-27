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
- Aggregate dataset: `manager_season_metrics.parquet`
- Aggregate dataset: `manager_career_metrics.parquet`
- Snapshot manifest: `manifest.json`
- Latest pointer: `latest.json`

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
- `local-run-sample`: local sample/debug run with upload forced off
- `local-run-docker`: run the container locally with a bind-mounted output directory and upload forced off
- `local-run-sample-docker`: sampled Docker run with a bind-mounted output directory and upload forced off
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

Expected bootstrap runtime on a current developer Mac:

- The full `local-bootstrap` path does **not** fetch monthly data back to 1871.
- Statcast detail begins in 2015, so as of 2026-09-19 the bootstrap fetch plan is about `141` monthly Statcast windows.
- Lahman covers pre-2015 historical aggregates and is typically much cheaper than the Statcast fetch.
- Based on observed local timing where active in-season months take roughly `10-20s` each and offseason months are much lighter, a cold first bootstrap on this machine should be expected to take roughly `30-60 minutes`.
- Treat `60-90 minutes` as a safer upper-bound if Baseball Savant is slow, your network is noisy, or the machine is busy with other work.

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
