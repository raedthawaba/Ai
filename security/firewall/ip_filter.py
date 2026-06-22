"""IP Filter — IP allowlist/blocklist with CIDR support and dynamic updates."""
from __future__ import annotations

import ipaddress
import logging
import time
from typing import Any, List, Optional, Set, Tuple, Union

import redis

logger = logging.getLogger(__name__)

IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]

PRIVATE_RANGES: List[IPNetwork] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]


class IPFilter:
    """Enforces IP-based access control with Redis-backed dynamic lists."""

    BLOCKLIST_KEY = "security:ip:blocklist"
    ALLOWLIST_KEY = "security:ip:allowlist"

    def __init__(
        self,
        redis_client: redis.Redis,
        mode: str = "blocklist",
        allow_private: bool = True,
    ) -> None:
        self.redis = redis_client
        self.mode = mode
        self.allow_private = allow_private
        self._static_blocklist: List[IPNetwork] = []
        self._static_allowlist: List[IPNetwork] = []

    def is_allowed(self, ip_str: str) -> Tuple[bool, str]:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, "invalid_ip"

        if self.allow_private and any(ip in net for net in PRIVATE_RANGES):
            return True, "private_network"

        if self._is_blocked(ip):
            return False, "blocklisted"

        if self.mode == "allowlist" and not self._is_allowed(ip):
            return False, "not_allowlisted"

        return True, "allowed"

    def block_ip(self, ip: str, reason: str = "", ttl: Optional[int] = None) -> None:
        key = f"{self.BLOCKLIST_KEY}:{ip}"
        value = f"{reason}:{time.time()}"
        if ttl:
            self.redis.setex(key, ttl, value)
        else:
            self.redis.set(key, value)
        logger.warning("Blocked IP %s: %s", ip, reason)

    def unblock_ip(self, ip: str) -> None:
        self.redis.delete(f"{self.BLOCKLIST_KEY}:{ip}")
        logger.info("Unblocked IP %s", ip)

    def add_to_allowlist(self, cidr: str) -> None:
        self.redis.sadd(self.ALLOWLIST_KEY, cidr)
        try:
            self._static_allowlist.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError as exc:
            logger.warning("Invalid CIDR %s: %s", cidr, exc)

    def _is_blocked(self, ip: IPAddress) -> bool:
        if self.redis.exists(f"{self.BLOCKLIST_KEY}:{ip}"):
            return True
        return any(ip in net for net in self._static_blocklist)

    def _is_allowed(self, ip: IPAddress) -> bool:
        for cidr in self.redis.smembers(self.ALLOWLIST_KEY):
            try:
                net = ipaddress.ip_network(cidr.decode(), strict=False)
                if ip in net:
                    return True
            except ValueError:
                pass
        return any(ip in net for net in self._static_allowlist)
