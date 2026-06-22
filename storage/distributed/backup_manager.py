"""Backup Manager — automated incremental and full backups with S3/GCS support."""
from __future__ import annotations

import gzip
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BackupMetadata:
    backup_id: str
    backup_type: str
    source: str
    destination: str
    size_bytes: int
    created_at: float = field(default_factory=time.time)
    duration_seconds: float = 0.0
    status: str = "pending"
    error: Optional[str] = None
    checksum: str = ""


class BackupManager:
    """Orchestrates automated database and object storage backups."""

    def __init__(
        self,
        storage_backend: str = "s3",
        bucket: str = "",
        prefix: str = "backups/hajeen",
        retention_days: int = 30,
    ) -> None:
        self.storage_backend = storage_backend
        self.bucket = bucket
        self.prefix = prefix
        self.retention_days = retention_days

    def backup_postgres(
        self,
        db_url: str,
        backup_id: Optional[str] = None,
    ) -> BackupMetadata:
        backup_id = backup_id or f"pg_{int(time.time())}"
        local_path = f"/tmp/backup_{backup_id}.sql.gz"
        start = time.time()

        meta = BackupMetadata(
            backup_id=backup_id,
            backup_type="postgres_full",
            source=db_url.split("@")[-1],
            destination=f"{self.prefix}/postgres/{backup_id}.sql.gz",
            size_bytes=0,
        )

        try:
            cmd = [
                "pg_dump",
                "--no-password",
                "--format=custom",
                "--compress=9",
                "--file", local_path,
                db_url,
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=3600)

            meta.size_bytes = os.path.getsize(local_path)
            meta.checksum = self._compute_checksum(local_path)
            self._upload(local_path, meta.destination)
            meta.status = "completed"
            logger.info(
                "Postgres backup %s completed: %.1fMB in %.1fs",
                backup_id, meta.size_bytes / 1024**2, time.time() - start,
            )

        except subprocess.CalledProcessError as exc:
            meta.status = "failed"
            meta.error = exc.stderr.decode() if exc.stderr else str(exc)
            logger.error("Postgres backup failed: %s", meta.error)
            raise

        finally:
            meta.duration_seconds = time.time() - start
            Path(local_path).unlink(missing_ok=True)

        return meta

    def backup_vector_db(self, vector_db_path: str, backup_id: Optional[str] = None) -> BackupMetadata:
        backup_id = backup_id or f"vdb_{int(time.time())}"
        local_path = f"/tmp/backup_{backup_id}.tar.gz"
        start = time.time()

        meta = BackupMetadata(
            backup_id=backup_id,
            backup_type="vector_db_full",
            source=vector_db_path,
            destination=f"{self.prefix}/vectordb/{backup_id}.tar.gz",
            size_bytes=0,
        )

        try:
            cmd = ["tar", "-czf", local_path, "-C", os.path.dirname(vector_db_path),
                   os.path.basename(vector_db_path)]
            subprocess.run(cmd, check=True, capture_output=True, timeout=1800)

            meta.size_bytes = os.path.getsize(local_path)
            meta.checksum = self._compute_checksum(local_path)
            self._upload(local_path, meta.destination)
            meta.status = "completed"

        except Exception as exc:
            meta.status = "failed"
            meta.error = str(exc)
            logger.error("Vector DB backup failed: %s", exc)
            raise

        finally:
            meta.duration_seconds = time.time() - start
            Path(local_path).unlink(missing_ok=True)

        return meta

    def list_backups(self, backup_type: Optional[str] = None) -> List[Dict[str, Any]]:
        import boto3
        s3 = boto3.client("s3")
        prefix = f"{self.prefix}/{backup_type}/" if backup_type else self.prefix
        paginator = s3.get_paginator("list_objects_v2")
        backups: List[Dict[str, Any]] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                backups.append({
                    "key": obj["Key"],
                    "size_bytes": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                })
        return backups

    def _upload(self, local_path: str, remote_key: str) -> None:
        import boto3
        s3 = boto3.client("s3")
        s3.upload_file(local_path, self.bucket, remote_key,
                       ExtraArgs={"ServerSideEncryption": "AES256"})
        logger.info("Uploaded %s to s3://%s/%s", local_path, self.bucket, remote_key)

    def _compute_checksum(self, path: str) -> str:
        import hashlib
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
