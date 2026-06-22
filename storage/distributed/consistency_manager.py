"""Consistency Manager — ensures eventual consistency across distributed storage nodes."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class VersionedValue:
    key: str
    value: Any
    version: int
    node_id: str
    timestamp: float = field(default_factory=time.time)
    checksum: str = ""

    def __post_init__(self) -> None:
        if not self.checksum:
            payload = json.dumps(self.value, default=str, sort_keys=True)
            self.checksum = hashlib.sha256(payload.encode()).hexdigest()[:16]


class ConsistencyManager:
    """Manages read repair, anti-entropy, and version reconciliation."""

    def __init__(self, shard_manager: Any, read_quorum: int = 2) -> None:
        self.shard_manager = shard_manager
        self.read_quorum = read_quorum
        self._repair_count = 0

    async def read_with_repair(
        self,
        key: str,
        read_func: Any,
        write_func: Any,
    ) -> Optional[Any]:
        replicas = self.shard_manager.get_replica_shards(key)
        if not replicas:
            return None

        read_tasks = [
            asyncio.to_thread(read_func, node, key)
            for node in replicas
        ]
        results = await asyncio.gather(*read_tasks, return_exceptions=True)

        valid: List[VersionedValue] = []
        for result in results:
            if isinstance(result, VersionedValue):
                valid.append(result)

        if not valid:
            return None

        # Return highest version (last-write-wins)
        latest = max(valid, key=lambda v: (v.version, v.timestamp))

        # Repair stale replicas
        stale_nodes = [
            replicas[i] for i, result in enumerate(results)
            if isinstance(result, VersionedValue) and result.version < latest.version
        ]

        if stale_nodes:
            asyncio.create_task(
                self._repair_replicas(stale_nodes, key, latest, write_func)
            )

        return latest.value

    async def _repair_replicas(
        self,
        nodes: List[Any],
        key: str,
        latest: VersionedValue,
        write_func: Any,
    ) -> None:
        self._repair_count += len(nodes)
        for node in nodes:
            try:
                await asyncio.to_thread(write_func, node, key, latest)
                logger.debug(
                    "Read repair: key=%s node=%s version=%d",
                    key, node.node_id, latest.version,
                )
            except Exception as exc:
                logger.warning("Read repair failed for %s/%s: %s", node.node_id, key, exc)

    async def run_anti_entropy(
        self,
        read_func: Any,
        write_func: Any,
        keys: List[str],
    ) -> Dict[str, Any]:
        repaired = 0
        errors = 0

        for key in keys:
            try:
                await self.read_with_repair(key, read_func, write_func)
                repaired += 1
            except Exception as exc:
                errors += 1
                logger.warning("Anti-entropy failed for key %s: %s", key, exc)

        return {
            "keys_checked": len(keys),
            "repaired": repaired,
            "errors": errors,
            "total_repairs": self._repair_count,
        }
