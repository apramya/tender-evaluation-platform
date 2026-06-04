"""
File storage abstraction for local disk and optional S3 persistence.
"""
import os
import uuid
from typing import BinaryIO, Dict, Optional

from app.utils.config import settings


class StorageService:
    """Save uploaded files locally, and mirror to S3 when configured."""

    @staticmethod
    def _s3_client():
        import boto3

        return boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )

    @staticmethod
    def _build_s3_key(kind: str, file_id: str, filename: str) -> str:
        safe_name = os.path.basename(filename).replace("\\", "_").replace("/", "_")
        return f"{settings.S3_PREFIX}/{kind}/{file_id}_{safe_name}"

    @staticmethod
    async def save_upload(
        *,
        file_obj,
        original_filename: str,
        kind: str,
        file_ext: str,
    ) -> Dict[str, Optional[str]]:
        file_id = str(uuid.uuid4())
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        local_path = os.path.join(settings.UPLOAD_DIR, f"{kind}_{file_id}.{file_ext}")

        content = await file_obj.read()
        with open(local_path, "wb") as f:
            f.write(content)

        metadata: Dict[str, Optional[str]] = {
            "id": file_id,
            "local_path": local_path,
            "storage_backend": "local",
            "s3_bucket": None,
            "s3_key": None,
        }

        if settings.STORAGE_BACKEND.lower() == "s3" and settings.S3_UPLOAD_ON_REQUEST:
            if not settings.S3_BUCKET_NAME:
                raise ValueError("S3_BUCKET_NAME must be set when STORAGE_BACKEND=s3")

            s3_key = StorageService._build_s3_key(kind, file_id, original_filename)
            StorageService._s3_client().put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=s3_key,
                Body=content,
            )
            metadata.update({
                "storage_backend": "s3",
                "s3_bucket": settings.S3_BUCKET_NAME,
                "s3_key": s3_key,
            })
        elif settings.STORAGE_BACKEND.lower() == "s3":
            metadata.update({
                "storage_backend": "local",
                "s3_bucket": None,
                "s3_key": None,
                "s3_pending": "true",
            })

        return metadata

    @staticmethod
    def ensure_local_file(local_path: str, raw_data: Optional[dict]) -> str:
        if local_path and os.path.exists(local_path):
            return local_path

        raw_data = raw_data or {}
        if raw_data.get("storage_backend") != "s3":
            return local_path

        bucket = raw_data.get("s3_bucket")
        key = raw_data.get("s3_key")
        if not bucket or not key:
            return local_path

        os.makedirs(settings.TEMP_DIR, exist_ok=True)
        filename = os.path.basename(key)
        download_path = os.path.join(settings.TEMP_DIR, filename)
        StorageService._s3_client().download_file(bucket, key, download_path)
        return download_path

    @staticmethod
    def delete_file(local_path: Optional[str], raw_data: Optional[dict]) -> None:
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except OSError:
                pass

        raw_data = raw_data or {}
        bucket = raw_data.get("s3_bucket")
        key = raw_data.get("s3_key")
        if bucket and key:
            try:
                StorageService._s3_client().delete_object(Bucket=bucket, Key=key)
            except Exception:
                pass
