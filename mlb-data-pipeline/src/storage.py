import json
import re
from pathlib import Path
from typing import Optional, Set, Tuple

from config import Config

DETAIL_PARTITION_RE = re.compile(r"season=(\d{4})/month=(\d{2})(?:/|$)")


def local_dataset_root(config: Config) -> Path:
    return config.output_dir / config.dataset_prefix


def local_latest_pointer_path(config: Config) -> Path:
    return local_dataset_root(config) / "latest.json"


def read_json_file(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


def resolve_local_manifest_path(config: Config, manifest_path: str) -> Path:
    return config.output_dir / manifest_path


def create_s3_client(config: Config):
    if not config.upload_enabled:
        return None

    if not all([
        config.spaces_bucket,
        config.spaces_region,
        config.spaces_endpoint,
        config.spaces_access_key_id,
        config.spaces_secret_access_key,
    ]):
        return None

    import boto3

    return boto3.client(
        "s3",
        region_name=config.spaces_region,
        endpoint_url=config.spaces_endpoint,
        aws_access_key_id=config.spaces_access_key_id,
        aws_secret_access_key=config.spaces_secret_access_key,
    )


def parse_partition_key(path_fragment: str) -> Optional[Tuple[int, int]]:
    match = DETAIL_PARTITION_RE.search(path_fragment)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def list_local_captured_months(detail_dir: Path) -> Set[Tuple[int, int]]:
    captured: Set[Tuple[int, int]] = set()
    if not detail_dir.exists():
        return captured

    for partition_dir in detail_dir.glob("season=*/month=*"):
        parsed = parse_partition_key(partition_dir.as_posix())
        if parsed is not None:
            captured.add(parsed)

    return captured


def list_bucket_captured_months(client, bucket: str, detail_prefix: str) -> Set[Tuple[int, int]]:
    captured: Set[Tuple[int, int]] = set()
    paginator = client.get_paginator("list_objects_v2")
    prefix = detail_prefix.rstrip("/") + "/"

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            parsed = parse_partition_key(item["Key"])
            if parsed is not None:
                captured.add(parsed)

    return captured


def read_latest_manifest(client, bucket: str, dataset_prefix: str) -> Optional[dict]:
    try:
        response = client.get_object(Bucket=bucket, Key=f"{dataset_prefix}/latest.json")
    except Exception as exc:
        error = getattr(exc, "response", {}).get("Error", {}) if hasattr(exc, "response") else {}
        if error.get("Code") in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise

    payload = response["Body"].read().decode("utf-8")
    return json.loads(payload)


def read_local_latest_pointer(config: Config) -> Optional[dict]:
    return read_json_file(local_latest_pointer_path(config))


def read_latest_pointer(config: Config, client) -> Optional[dict]:
    if client is not None and config.spaces_bucket:
        return read_latest_manifest(client, config.spaces_bucket, config.dataset_prefix)
    return read_local_latest_pointer(config)


def latest_processed_end_date(client, config: Config) -> Optional[str]:
    latest = read_latest_pointer(config, client)
    if latest is None:
        return None

    manifest_path = latest.get("manifest_path")
    if not manifest_path:
        return None

    if client is not None and config.spaces_bucket:
        try:
            manifest_obj = client.get_object(Bucket=config.spaces_bucket, Key=manifest_path)
        except Exception:
            return None
        manifest = json.loads(manifest_obj["Body"].read().decode("utf-8"))
    else:
        manifest = read_json_file(resolve_local_manifest_path(config, manifest_path))
        if manifest is None:
            return None

    source = manifest.get("source", {})
    window_end_date = source.get("window_end_date")
    if window_end_date:
        return window_end_date

    generated_at = manifest.get("generated_at_utc", "")
    if generated_at:
        return generated_at[:10]

    return None


def upload_directory(client, bucket: str, local_dir: Path, prefix: str) -> None:
    for local_path in local_dir.rglob("*"):
        if not local_path.is_file():
            continue

        relative_path = local_path.relative_to(local_dir).as_posix()
        object_key = f"{prefix}/{relative_path}"
        print(f"Uploading {local_path} -> s3://{bucket}/{object_key}")
        client.upload_file(str(local_path), bucket, object_key)


def upload_manifest(client, bucket: str, content: dict, key: str) -> None:
    payload = json.dumps(content, indent=2).encode("utf-8")
    client.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="application/json")
