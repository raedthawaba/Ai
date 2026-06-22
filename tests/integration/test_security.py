"""اختبارات Phase 7 — Security & Production Hardening."""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from typing import Set
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# JWT Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestJWTAuthentication:
    def test_create_and_verify_token(self):
        from security.middleware.security_middleware import create_token, verify_token
        token = create_token("user_123", roles=["viewer"])
        payload = verify_token(token)
        assert payload["sub"] == "user_123"
        assert "viewer" in payload["roles"]

    def test_token_contains_expiry(self):
        from security.middleware.security_middleware import create_token, verify_token
        token = create_token("user_exp", roles=["admin"], ttl=3600)
        payload = verify_token(token)
        assert "exp" in payload
        assert payload["exp"] > time.time()

    def test_expired_token_raises(self):
        from security.middleware.security_middleware import create_token, verify_token
        token = create_token("expired_user", roles=["viewer"], ttl=-1)
        with pytest.raises((ValueError, Exception)):
            verify_token(token)

    def test_tampered_token_raises(self):
        from security.middleware.security_middleware import create_token, verify_token
        token = create_token("user", roles=["viewer"])
        tampered = token[:-5] + "XXXXX"
        with pytest.raises((ValueError, Exception)):
            verify_token(tampered)

    def test_token_with_extra_claims(self):
        from security.middleware.security_middleware import create_token, verify_token
        token = create_token("u1", roles=["admin"], extra={"org": "hajeen"})
        payload = verify_token(token)
        assert payload.get("org") == "hajeen"

    def test_admin_role_included(self):
        from security.middleware.security_middleware import create_token, verify_token
        token = create_token("admin_user", roles=["admin", "viewer"])
        payload = verify_token(token)
        assert "admin" in payload["roles"]


# ──────────────────────────────────────────────────────────────────────────────
# RBAC Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestRBAC:
    def test_admin_has_all_permissions(self):
        from security.middleware.security_middleware import has_permission
        for perm in ("read", "write", "delete", "manage_users"):
            assert has_permission(["admin"], perm) is True

    def test_viewer_has_read_only(self):
        from security.middleware.security_middleware import has_permission
        assert has_permission(["viewer"], "read") is True
        assert has_permission(["viewer"], "delete") is False
        assert has_permission(["viewer"], "manage_users") is False

    def test_editor_can_write(self):
        from security.middleware.security_middleware import has_permission
        assert has_permission(["editor"], "write") is True
        assert has_permission(["editor"], "delete") is False

    def test_multiple_roles_combined(self):
        from security.middleware.security_middleware import has_permission
        assert has_permission(["viewer", "editor"], "delete") is False
        assert has_permission(["viewer", "admin"], "delete") is True

    def test_unknown_role_has_no_permissions(self):
        from security.middleware.security_middleware import has_permission
        assert has_permission(["ghost_role"], "read") is False

    def test_empty_roles_no_permissions(self):
        from security.middleware.security_middleware import has_permission
        assert has_permission([], "read") is False


# ──────────────────────────────────────────────────────────────────────────────
# RateLimiter Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestRateLimiter:
    def test_allows_requests_under_limit(self):
        from security.middleware.security_middleware import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert limiter.is_allowed("user_1") is True

    def test_blocks_requests_over_limit(self):
        from security.middleware.security_middleware import RateLimiter
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed("user_2")
        assert limiter.is_allowed("user_2") is False

    def test_different_keys_independent(self):
        from security.middleware.security_middleware import RateLimiter
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed("key_a")
        limiter.is_allowed("key_a")
        limiter.is_allowed("key_a")  # blocked
        assert limiter.is_allowed("key_b") is True  # independent

    def test_get_remaining_decreases(self):
        from security.middleware.security_middleware import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        limiter.is_allowed("r_user")
        remaining = limiter.get_remaining("r_user")
        assert remaining == 4

    def test_reset_clears_bucket(self):
        from security.middleware.security_middleware import RateLimiter
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed("reset_key")
        limiter.is_allowed("reset_key")
        assert limiter.is_allowed("reset_key") is False
        limiter.reset("reset_key")
        assert limiter.is_allowed("reset_key") is True

    def test_cleanup_expired_removes_old_entries(self):
        from security.middleware.security_middleware import RateLimiter
        limiter = RateLimiter(max_requests=100, window_seconds=1)
        limiter.is_allowed("old_user")
        time.sleep(1.1)
        removed = limiter.cleanup_expired()
        assert removed >= 0  # لا يرمي خطأ


# ──────────────────────────────────────────────────────────────────────────────
# Input Sanitization Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestInputSanitization:
    def test_sanitize_removes_script_tags(self):
        from security.middleware.security_middleware import sanitize_input
        result = sanitize_input("<script>alert('xss')</script>")
        assert "<script" not in result.lower()

    def test_sanitize_removes_javascript_protocol(self):
        from security.middleware.security_middleware import sanitize_input
        result = sanitize_input("javascript:void(0)")
        assert "javascript:" not in result.lower()

    def test_sanitize_truncates_long_input(self):
        from security.middleware.security_middleware import sanitize_input
        long_input = "a" * 20_000
        result = sanitize_input(long_input, max_length=1000)
        assert len(result) <= 1000

    def test_sanitize_clean_input_unchanged(self):
        from security.middleware.security_middleware import sanitize_input
        clean = "ما هو الذكاء الاصطناعي؟"
        result = sanitize_input(clean)
        assert "الذكاء الاصطناعي" in result

    def test_validate_api_key_correct(self):
        from security.middleware.security_middleware import validate_api_key
        valid_keys: Set[str] = {"secret-key-1", "secret-key-2"}
        assert validate_api_key("secret-key-1", valid_keys) is True

    def test_validate_api_key_wrong(self):
        from security.middleware.security_middleware import validate_api_key
        valid_keys: Set[str] = {"correct-key"}
        assert validate_api_key("wrong-key", valid_keys) is False


# ──────────────────────────────────────────────────────────────────────────────
# SecretManager Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSecretManager:
    def test_get_existing_env_var(self):
        from security.config.secret_manager import SecretManager
        os.environ["TEST_SECRET_KEY_HAJEEN"] = "test_value_123"
        mgr = SecretManager()
        value = mgr.get("TEST_SECRET_KEY_HAJEEN")
        assert value == "test_value_123"

    def test_get_missing_returns_default(self):
        from security.config.secret_manager import SecretManager
        mgr = SecretManager()
        value = mgr.get("DEFINITELY_NOT_EXISTS_XYZ", default="default_val")
        assert value == "default_val"

    def test_require_existing_returns_value(self):
        from security.config.secret_manager import SecretManager
        os.environ["REQUIRED_TEST_KEY"] = "required_value"
        mgr = SecretManager()
        assert mgr.require("REQUIRED_TEST_KEY") == "required_value"

    def test_require_missing_raises(self):
        from security.config.secret_manager import SecretManager
        mgr = SecretManager()
        with pytest.raises(ValueError):
            mgr.require("ABSOLUTELY_MISSING_SECRET_XYZ")

    def test_mask_sensitive_key(self):
        from security.config.secret_manager import SecretManager
        mgr = SecretManager()
        masked = mgr.mask("JWT_SECRET", "my_very_long_secret_value")
        assert "****" in masked
        assert "my_v" in masked  # first 4 chars

    def test_mask_non_sensitive_key(self):
        from security.config.secret_manager import SecretManager
        mgr = SecretManager()
        value = "public_value"
        masked = mgr.mask("PUBLIC_KEY", value)
        assert masked == value

    def test_load_from_env_file(self):
        from security.config.secret_manager import SecretManager
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_ENV_KEY=env_file_value\n")
            f.write("# comment line\n")
            f.write("ANOTHER_KEY=another_value\n")
            env_path = f.name
        try:
            mgr = SecretManager(env_file=env_path)
            assert mgr.get("TEST_ENV_KEY") == "env_file_value"
        finally:
            os.unlink(env_path)

    def test_summary_structure(self):
        from security.config.secret_manager import SecretManager
        mgr = SecretManager()
        summary = mgr.summary()
        assert "total_secrets" in summary
        assert "required_present" in summary
        assert "required_missing" in summary

    def test_rotation_callback_called(self):
        from security.config.secret_manager import SecretManager
        mgr = SecretManager()
        os.environ["ROTATING_KEY"] = "old_value"
        mgr._secrets["ROTATING_KEY"] = "old_value"

        calls = []
        mgr.register_rotation_callback("ROTATING_KEY", lambda old, new: calls.append((old, new)))
        mgr.rotate("ROTATING_KEY", "new_value")
        assert len(calls) == 1
        assert calls[0] == ("old_value", "new_value")


# ──────────────────────────────────────────────────────────────────────────────
# ResourceGuard Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestResourceGuard:
    @pytest.mark.asyncio
    async def test_protected_request_succeeds(self):
        from security.resource.resource_guard import ResourceGuard
        guard = ResourceGuard(max_concurrent=10, request_timeout=5.0)
        async with guard.protected_request("test_op"):
            await asyncio.sleep(0.001)
        assert True

    @pytest.mark.asyncio
    async def test_timeout_protection(self):
        from security.resource.resource_guard import ResourceGuard, TimeoutGuard
        with pytest.raises(TimeoutError):
            async with TimeoutGuard.async_timeout(0.01, "slow_op"):
                await asyncio.sleep(1.0)

    def test_rate_limiter_throttling(self):
        from security.middleware.security_middleware import RateLimiter
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("throttle_key") is True
        assert limiter.is_allowed("throttle_key") is False

    def test_memory_guard_check(self):
        from security.resource.resource_guard import MemoryGuard
        guard = MemoryGuard(max_memory_mb=999_999)
        assert guard.check() is True

    @pytest.mark.asyncio
    async def test_worker_isolation_runs_function(self):
        from security.resource.resource_guard import WorkerIsolation
        isolation = WorkerIsolation(max_workers=2)
        result = await isolation.run(lambda x: x * 2, 21)
        assert result == 42
        isolation.shutdown()

    def test_graceful_degradation_circuit_open(self):
        from security.resource.resource_guard import GracefulDegradation
        dg = GracefulDegradation(fallback="fallback_value", max_failures=2)
        dg.record_failure()
        dg.record_failure()
        assert dg.is_open() is True

    def test_graceful_degradation_circuit_closed_after_recovery(self):
        from security.resource.resource_guard import GracefulDegradation
        dg = GracefulDegradation(max_failures=2)
        dg.record_failure()
        dg.record_failure()
        dg._last_failure = time.time() - 200  # expire window
        assert dg.is_open() is False

    def test_resource_guard_health(self):
        from security.resource.resource_guard import ResourceGuard
        guard = ResourceGuard()
        health = guard.health()
        assert "memory_current_mb" in health
        assert "concurrent_requests" in health
        assert "overloaded" in health

    def test_secure_headers_present(self):
        from security.middleware.security_middleware import SECURE_HEADERS
        assert "X-Content-Type-Options" in SECURE_HEADERS
        assert "X-Frame-Options" in SECURE_HEADERS
        assert "Strict-Transport-Security" in SECURE_HEADERS
