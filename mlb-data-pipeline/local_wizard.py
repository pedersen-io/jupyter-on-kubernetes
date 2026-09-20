from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def prompt(message: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default not in {None, ""} else ""
    value = input(f"{message}{suffix}: ").strip()
    if value:
        return value
    return default or ""


def prompt_bool(message: str, default: bool) -> bool:
    default_label = "Y/n" if default else "y/N"
    while True:
        value = input(f"{message} [{default_label}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Please answer y or n.")


def prompt_int(message: str, default: int) -> int:
    while True:
        value = prompt(message, str(default))
        try:
            return int(value)
        except ValueError:
            print("Please enter a whole number.")


def choose_target() -> str:
    options = [
        ("1", "local-run", "Incremental or one-range local run, local files only"),
        ("2", "local-run-upload", "Incremental or one-range local run plus Spaces upload"),
        ("3", "local-bootstrap", "Full historical bootstrap, local files only"),
        ("4", "local-bootstrap-upload", "Full historical bootstrap plus Spaces upload"),
        ("5", "local-run-sample", "Small sample run for quick validation"),
        ("6", "local-run-docker", "Run the local-only container with a bind mount"),
        ("7", "local-run-sample-docker", "Run the sampled container with a bind mount"),
    ]

    print("Select a pipeline action:")
    for number, target, description in options:
        print(f"  {number}. {target:<24} {description}")

    valid = {number: target for number, target, _description in options}
    while True:
        selected = input("Choice [1]: ").strip() or "1"
        if selected in valid:
            return valid[selected]
        print("Please choose one of the listed numbers.")


def build_overrides(target: str) -> dict[str, str]:
    overrides: dict[str, str] = {}
    overrides["OUTPUT_DIR"] = prompt("Output directory", str(ROOT / "output"))
    overrides["PRETTY_LOCAL_OUTPUT"] = "true" if prompt_bool("Use pretty local output", True) else "false"

    if not target.endswith("-docker"):
        overrides["PYTHON"] = prompt("Python executable", os.getenv("PYTHON", "python3.12"))

    if target in {"local-bootstrap", "local-bootstrap-upload"}:
        print("Bootstrap mode uses START_SEASON=1871, END_SEASON=current year, INCREMENTAL_MODE=false, and LAHMAN_ENABLED=true.")
        return overrides

    if target in {"local-run", "local-run-upload", "local-run-docker"}:
        overrides["START_SEASON"] = prompt("Start season", os.getenv("START_SEASON", "2024"))
        overrides["END_SEASON"] = prompt("End season", os.getenv("END_SEASON", overrides["START_SEASON"]))
        overrides["INCREMENTAL_MODE"] = "true" if prompt_bool("Use incremental mode", True) else "false"
        overrides["REQUIRE_EXISTING_SNAPSHOT"] = "true" if prompt_bool("Require an existing latest snapshot", False) else "false"
        overrides["TRAILER_MONTHS"] = str(prompt_int("Trailer months", int(os.getenv("TRAILER_MONTHS", "1"))))
        overrides["LAHMAN_ENABLED"] = "true" if prompt_bool("Include Lahman historical aggregates", False) else "false"
        return overrides

    if target in {"local-run-sample", "local-run-sample-docker"}:
        overrides["START_SEASON"] = prompt("Start season", os.getenv("START_SEASON", "2024"))
        overrides["END_SEASON"] = prompt("End season", os.getenv("END_SEASON", overrides["START_SEASON"]))
        exact_dates = prompt_bool("Use an exact sample date range", True)
        if exact_dates:
            overrides["SAMPLE_MODE"] = "true"
            overrides["SAMPLE_START_DATE"] = prompt("Sample start date (YYYY-MM-DD)", "2024-03-01")
            overrides["SAMPLE_END_DATE"] = prompt("Sample end date (YYYY-MM-DD)", "2024-03-07")
        overrides["SAMPLE_MAX_ROWS"] = str(prompt_int("Sample max rows", int(os.getenv("SAMPLE_MAX_ROWS", "5000"))))
        overrides["SAMPLE_MAX_WINDOWS"] = str(prompt_int("Sample max windows", int(os.getenv("SAMPLE_MAX_WINDOWS", "1"))))
        return overrides

    return overrides


def main() -> int:
    print("MLB Data Pipeline Local Wizard")
    target = choose_target()
    overrides = build_overrides(target)

    if target.endswith("upload"):
        print("Upload mode selected. Ensure SPACES_BUCKET, SPACES_REGION, SPACES_ENDPOINT, SPACES_ACCESS_KEY_ID, and SPACES_SECRET_ACCESS_KEY are already exported.")

    command = ["make", target] + [f"{key}={value}" for key, value in overrides.items() if value != ""]
    print("Launching:")
    print("  " + " ".join(command))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())