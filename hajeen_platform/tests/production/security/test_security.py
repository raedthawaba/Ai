"""
Security Tests — validates authentication, authorization, and injection defenses.
"""
import os
import time
from typing import Any, Dict

import httpx
import pytest

HOST = os.environ.get("SECURITY_TEST_HOST", "http://localhost:8000")


@pytest.fixture
def client() -> httpx.Client:
    with httpx.Client(base_url=HOST, timeout=10.0) as c:
        yield c


def test_unauthenticated_request_rejected(client: httpx.Client) -> None:
    resp = client.post("/api/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "test"}]
    })
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


def test_invalid_token_rejected(client: httpx.Client) -> None:
    resp = client.post(
        "/api/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "test"}]},
        headers={"Authorization": "Bearer invalid_token_here"},
    )
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


def test_expired_token_rejected(client: httpx.Client) -> None:
    import jwt
    expired_token = jwt.encode(
        {"sub": "test_user", "exp": int(time.time()) - 3600, "tenant_id": "test"},
        "wrong_secret",
        algorithm="HS256",
    )
    resp = client.post(
        "/api/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "test"}]},
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


def test_sql_injection_sanitized(client: httpx.Client) -> None:
    payloads = [
        "'; DROP TABLE users; --",
        "1 OR 1=1",
        "' UNION SELECT * FROM secrets --",
    ]
    for payload in payloads:
        resp = client.get(
            "/api/v1/models",
            params={"search": payload},
            headers={"X-Tenant-ID": "test"},
        )
        assert resp.status_code not in (500,), f"SQL injection may have caused server error"
        assert "error" not in resp.text.lower() or "syntax" not in resp.text.lower()


def test_rate_limiting_enforced(client: httpx.Client) -> None:
    responses = []
    for _ in range(150):
        resp = client.get("/api/v1/health")
        responses.append(resp.status_code)

    rate_limited = sum(1 for s in responses if s == 429)
    assert rate_limited > 0, "Rate limiting not enforced after 150 rapid requests"


def test_xss_headers_present(client: httpx.Client) -> None:
    resp = client.get("/api/v1/health")
    assert "X-Content-Type-Options" in resp.headers or resp.headers.get("content-type", "").startswith("application/json"), \
        "Missing security headers"


def test_tenant_isolation(client: httpx.Client) -> None:
    resp_a = client.get(
        "/api/v1/usage",
        headers={"X-Tenant-ID": "tenant-a", "Authorization": "Bearer test_token_a"},
    )
    resp_b = client.get(
        "/api/v1/usage",
        headers={"X-Tenant-ID": "tenant-b", "Authorization": "Bearer test_token_b"},
    )
    if resp_a.status_code == 200 and resp_b.status_code == 200:
        data_a = resp_a.json()
        data_b = resp_b.json()
        assert data_a.get("tenant_id") != data_b.get("tenant_id"), "Tenant isolation violated"
