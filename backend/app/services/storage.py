"""Object storage: local disk (dev) or any S3-compatible bucket (AWS S3, R2, Supabase Storage …)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from backend.app.core.config import get_settings


def _s3_client():
    import boto3
    s = get_settings()
    return boto3.client(
        "s3", region_name=s.s3_region, endpoint_url=s.s3_endpoint_url or None,
        aws_access_key_id=s.s3_access_key_id or None, aws_secret_access_key=s.s3_secret_access_key or None,
    )


def public_url(key: str) -> str:
    s = get_settings()
    if s.storage_backend == "s3":
        base = s.s3_public_base_url.rstrip("/") if s.s3_public_base_url else \
            f"https://{s.s3_bucket}.s3.{s.s3_region}.amazonaws.com"
        return f"{base}/{key}"
    return f"{s.api_url.rstrip('/')}/media/{key}"


async def put_bytes(key: str, data: bytes, content_type: str, *, cache_seconds: int = 31536000) -> str:
    s = get_settings()
    if s.storage_backend == "s3":
        def _put() -> None:
            _s3_client().put_object(Bucket=s.s3_bucket, Key=key, Body=data, ContentType=content_type,
                                    CacheControl=f"public, max-age={cache_seconds}, immutable")
        await asyncio.to_thread(_put)
    else:
        path = Path(s.storage_local_dir) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
    return public_url(key)


async def download_to(key: str, dest: Path) -> Path:
    s = get_settings()
    if s.storage_backend == "s3":
        await asyncio.to_thread(_s3_client().download_file, s.s3_bucket, key, str(dest))
    else:
        dest.write_bytes((Path(s.storage_local_dir) / key).read_bytes())
    return dest


async def delete(key: str) -> None:
    s = get_settings()
    if s.storage_backend == "s3":
        await asyncio.to_thread(_s3_client().delete_object, Bucket=s.s3_bucket, Key=key)
    else:
        (Path(s.storage_local_dir) / key).unlink(missing_ok=True)
