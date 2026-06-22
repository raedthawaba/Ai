"""Replication Manager — synchronous and asynchronous data replication."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReplicationMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"
    SEMI_SYNC = "semi_sync"


@dataclass
class ReplicationResult:
    key: str
    primary_ok: bool
    replica_acks: int
    total_replicas: int
    latency_ms: float
    errors: List[str]

    @property
    def quorum_met(self) -> bool:
        quorum = (self.total_replicas // 2) + 1
        return self.replica_acks >= quorum


class ReplicationManager:
    """Handles synchronous, asynchronous, and semi-synchronous replication."""

    def __init__(
        self,
        shard_manager: Any,
        write_func: Callable,
        mode: ReplicationMode = ReplicationMode.SEMI_SYNC,
        quorum: int = 2,
    ) -> None:
        self.shard_manager = shard_manager
        self.write_func = write_func
        self.mode = mode
        self.quorum = quorum

    async def replicate(
        self,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReplicationResult:
        start = time.perf_counter()
        primary, secondaries = self.shard_manager.get_all_shards_for_key(key)
        all_replicas = [primary] + secondaries
        errors: List[str] = []
        acks = 0

        primary_ok = await self._write_to_node(primary, key, value, metadata)
        if primary_ok:
            acks += 1
        else:
            errors.append(f"Primary {primary.node_id} write failed")

        if self.mode == ReplicationMode.SYNC:
            for replica in secondaries:
                ok = await self._write_to_node(replica, key, value, metadata)
                if ok:
                    acks += 1
                else:
                    errors.append(f"Replica {replica.node_id} write failed")

        elif self.mode == ReplicationMode.SEMI_SYNC:
            tasks = [
                self._write_to_node(r, key, value, metadata)
                for r in secondaries
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for replica, result in zip(secondaries, results):
                if result is True:
                    acks += 1
                else:
                    errors.append(f"Replica {replica.node_id}: {result}")

        elif self.mode == ReplicationMode.ASYNC:
            asyncio.create_task(self._async_replicate(secondaries, key, value, metadata))
            acks = 1

        result = ReplicationResult(
            key=key,
            primary_ok=primary_ok,
            replica_acks=acks,
            total_replicas=len(all_replicas),
            latency_ms=(time.perf_counter() - start) * 1000,
            errors=errors,
        )

        if not result.quorum_met and self.mode != ReplicationMode.ASYNC:
            logger.error("Quorum not met for key %s: %d/%d", key, acks, len(all_replicas))

        return result

    async def _write_to_node(
        self, node: Any, key: str, value: Any, metadata: Optional[Dict]
    ) -> bool:
        try:
            await asyncio.to_thread(self.write_func, node, key, value, metadata)
            return True
        except Exception as exc:
            logger.warning("Write to node %s failed: %s", node.node_id, exc)
            return False

    async def _async_replicate(
        self, replicas: List[Any], key: str, value: Any, metadata: Optional[Dict]
    ) -> None:
        for replica in replicas:
            try:
                await asyncio.to_thread(self.write_func, replica, key, value, metadata)
            except Exception as exc:
                logger.error("Async replication to %s failed: %s", replica.node_id, exc)
