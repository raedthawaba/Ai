"""Shard Manager — consistent hashing-based data sharding across storage nodes."""
from __future__ import annotations

import hashlib
import logging
from bisect import bisect, insort
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class StorageNode:
    node_id: str
    host: str
    port: int
    weight: int = 1
    is_healthy: bool = True
    virtual_nodes: int = 150


class ConsistentHashRing:
    """Virtual node consistent hash ring for data distribution."""

    def __init__(self, virtual_nodes: int = 150) -> None:
        self.virtual_nodes = virtual_nodes
        self._ring: Dict[int, StorageNode] = {}
        self._sorted_keys: List[int] = []

    def add_node(self, node: StorageNode) -> None:
        vn = node.virtual_nodes * node.weight
        for i in range(vn):
            key = self._hash(f"{node.node_id}:{i}")
            self._ring[key] = node
            insort(self._sorted_keys, key)
        logger.info("Added node %s to ring (%d virtual nodes)", node.node_id, vn)

    def remove_node(self, node_id: str) -> None:
        to_remove = [k for k, n in self._ring.items() if n.node_id == node_id]
        for key in to_remove:
            del self._ring[key]
            self._sorted_keys.remove(key)
        logger.info("Removed node %s from ring", node_id)

    def get_node(self, key: str) -> Optional[StorageNode]:
        if not self._ring:
            return None
        hash_key = self._hash(key)
        idx = bisect(self._sorted_keys, hash_key) % len(self._sorted_keys)
        node = self._ring[self._sorted_keys[idx]]
        if not node.is_healthy:
            return self._get_next_healthy(idx)
        return node

    def get_nodes(self, key: str, n: int = 3) -> List[StorageNode]:
        if not self._ring:
            return []
        hash_key = self._hash(key)
        idx = bisect(self._sorted_keys, hash_key) % len(self._sorted_keys)
        seen: set = set()
        nodes: List[StorageNode] = []
        for i in range(len(self._sorted_keys)):
            pos = (idx + i) % len(self._sorted_keys)
            node = self._ring[self._sorted_keys[pos]]
            if node.node_id not in seen and node.is_healthy:
                seen.add(node.node_id)
                nodes.append(node)
            if len(nodes) == n:
                break
        return nodes

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def _get_next_healthy(self, start_idx: int) -> Optional[StorageNode]:
        for i in range(1, len(self._sorted_keys)):
            idx = (start_idx + i) % len(self._sorted_keys)
            node = self._ring[self._sorted_keys[idx]]
            if node.is_healthy:
                return node
        return None

    def get_distribution(self) -> Dict[str, int]:
        dist: Dict[str, int] = {}
        for node in self._ring.values():
            dist[node.node_id] = dist.get(node.node_id, 0) + 1
        return dist


class ShardManager:
    """Routes storage operations to the correct shard."""

    def __init__(self, nodes: List[StorageNode], replication_factor: int = 3) -> None:
        self.replication_factor = replication_factor
        self._ring = ConsistentHashRing()
        for node in nodes:
            self._ring.add_node(node)

    def get_shard(self, key: str) -> StorageNode:
        node = self._ring.get_node(key)
        if not node:
            raise RuntimeError("No healthy storage nodes available")
        return node

    def get_replica_shards(self, key: str) -> List[StorageNode]:
        return self._ring.get_nodes(key, n=self.replication_factor)

    def get_all_shards_for_key(self, key: str) -> Tuple[StorageNode, List[StorageNode]]:
        replicas = self.get_replica_shards(key)
        primary = replicas[0] if replicas else self.get_shard(key)
        secondaries = replicas[1:] if len(replicas) > 1 else []
        return primary, secondaries
