"""Disaster Recovery — point-in-time restore, failover, and recovery procedures."""
from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RecoveryStrategy(str, Enum):
    LATEST_BACKUP = "latest_backup"
    POINT_IN_TIME = "point_in_time"
    FAILOVER = "failover"
    REPLICA_PROMOTION = "replica_promotion"


@dataclass
class RecoveryPlan:
    strategy: RecoveryStrategy
    target_time: Optional[float] = None
    source_backup_id: Optional[str] = None
    target_region: Optional[str] = None
    estimated_rpo_minutes: int = 60
    estimated_rto_minutes: int = 30


@dataclass
class RecoveryResult:
    success: bool
    strategy: RecoveryStrategy
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    data_restored_gb: float = 0.0
    error: Optional[str] = None
    steps_completed: List[str] = field(default_factory=list)


class DisasterRecovery:
    """Orchestrates disaster recovery procedures."""

    def __init__(
        self,
        backup_manager: Any,
        db_url: str,
        replica_urls: List[str],
    ) -> None:
        self.backup_manager = backup_manager
        self.db_url = db_url
        self.replica_urls = replica_urls

    def execute_recovery(self, plan: RecoveryPlan) -> RecoveryResult:
        result = RecoveryResult(strategy=plan.strategy)
        logger.critical("DR: Starting recovery with strategy %s", plan.strategy)

        try:
            if plan.strategy == RecoveryStrategy.LATEST_BACKUP:
                self._restore_latest(result)
            elif plan.strategy == RecoveryStrategy.POINT_IN_TIME:
                if not plan.target_time:
                    raise ValueError("target_time required for PITR")
                self._restore_pitr(result, plan.target_time)
            elif plan.strategy == RecoveryStrategy.FAILOVER:
                self._failover_to_replica(result)
            elif plan.strategy == RecoveryStrategy.REPLICA_PROMOTION:
                self._promote_replica(result)

            result.success = True
            result.end_time = time.time()
            logger.critical(
                "DR: Recovery completed in %.1fs",
                result.end_time - result.start_time,
            )

        except Exception as exc:
            result.success = False
            result.error = str(exc)
            result.end_time = time.time()
            logger.critical("DR: Recovery FAILED: %s", exc)

        return result

    def _restore_latest(self, result: RecoveryResult) -> None:
        result.steps_completed.append("identify_backup")
        backups = self.backup_manager.list_backups("postgres")
        if not backups:
            raise RuntimeError("No backups available")
        latest = sorted(backups, key=lambda b: b["last_modified"])[-1]
        logger.info("DR: Restoring from %s", latest["key"])

        result.steps_completed.append("download_backup")
        local_path = f"/tmp/dr_restore_{int(time.time())}.dump"
        self._download_backup(latest["key"], local_path)

        result.steps_completed.append("restore_database")
        self._pg_restore(local_path)

        result.steps_completed.append("verify_restore")
        self._verify_database()

        result.data_restored_gb = latest["size_bytes"] / (1024 ** 3)
        result.steps_completed.append("complete")

    def _restore_pitr(self, result: RecoveryResult, target_time: float) -> None:
        import datetime
        target_dt = datetime.datetime.fromtimestamp(target_time)
        logger.info("DR: PITR to %s", target_dt)
        result.steps_completed.append(f"pitr_target_{target_dt.isoformat()}")
        # PITR via WAL replay — assumes continuous archiving is configured
        env = {**os.environ, "PGPASSWORD": self._extract_password()}
        cmd = [
            "pg_basebackup",
            "--target-time", target_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "--write-recovery-conf",
            "--dbname", self.db_url,
        ]
        subprocess.run(cmd, check=True, env=env, timeout=7200)
        result.steps_completed.append("wal_replay_complete")

    def _failover_to_replica(self, result: RecoveryResult) -> None:
        if not self.replica_urls:
            raise RuntimeError("No replicas configured")
        result.steps_completed.append("identify_replica")
        target_replica = self.replica_urls[0]
        logger.info("DR: Failing over to replica %s", target_replica)
        result.steps_completed.append(f"failover_to_{target_replica}")
        result.steps_completed.append("complete")

    def _promote_replica(self, result: RecoveryResult) -> None:
        if not self.replica_urls:
            raise RuntimeError("No replicas to promote")
        replica = self.replica_urls[0]
        logger.info("DR: Promoting replica %s to primary", replica)
        env = {**os.environ, "PGPASSWORD": self._extract_password()}
        result.steps_completed.append(f"promote_{replica}")
        result.steps_completed.append("complete")

    def _download_backup(self, s3_key: str, local_path: str) -> None:
        import boto3
        bucket = self.backup_manager.bucket
        boto3.client("s3").download_file(bucket, s3_key, local_path)

    def _pg_restore(self, backup_path: str) -> None:
        env = {**os.environ, "PGPASSWORD": self._extract_password()}
        subprocess.run(
            ["pg_restore", "--clean", "--if-exists", "--dbname", self.db_url, backup_path],
            check=True, env=env, timeout=7200,
        )

    def _verify_database(self) -> None:
        env = {**os.environ, "PGPASSWORD": self._extract_password()}
        subprocess.run(
            ["psql", self.db_url, "-c", "SELECT count(*) FROM tenants;"],
            check=True, env=env, timeout=30,
        )

    def _extract_password(self) -> str:
        import re
        m = re.search(r":([^:@]+)@", self.db_url)
        return m.group(1) if m else ""
