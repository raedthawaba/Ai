"""Integration Test — API Workflow End-to-End (Phase 1 — Section 1.6).

يختبر:
1. إنشاء قناة عبر API
2. استرجاع القنوات
3. تحديث القناة
4. تشغيل trigger عبر API
5. استرجاع الحالة
6. استرجاع audit log
7. إيقاف / استئناف القناة
8. حذف القناة
9. Global exception handlers
10. Request validation
"""
from __future__ import annotations

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def api_client():
    """إنشاء AsyncClient للـ FastAPI app."""
    from api.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture(scope="module")
async def sample_channel_id(api_client):
    """إنشاء قناة demo للاختبار وإعادة معرّفها."""
    response = await api_client.post("/api/v1/channels", json={
        "name": "Test RSS Channel",
        "description": "قناة اختبار تكاملي",
        "source": {
            "url": "https://feeds.bbcaudio.co.uk/world-service/features/podcasts.rss",
            "type": "demo",
            "params": {},
        },
    })
    assert response.status_code == 201
    return response.json()["id"]


# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint(api_client):
    """GET /health يجب أن يُعيد status ok."""
    resp = await api_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "version" in data
    assert data["status"] in ("ok", "degraded"), f"status غير متوقع: {data['status']}"


@pytest.mark.asyncio
async def test_ping_endpoint(api_client):
    """GET /ping يجب أن يُعيد pong."""
    resp = await api_client.get("/ping")
    assert resp.status_code == 200
    assert resp.json()["message"] == "pong"


# ─────────────────────────────────────────────
# Channel CRUD
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_channel(api_client):
    """POST /channels يُنشئ قناة جديدة."""
    resp = await api_client.post("/api/v1/channels", json={
        "name": "API Test Channel",
        "description": "وصف القناة",
        "source": {
            "url": "https://example.com/rss",
            "type": "demo",
        },
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["name"] == "API Test Channel"
    assert data["status"] in ("active", "inactive", "draft")


@pytest.mark.asyncio
async def test_list_channels(api_client, sample_channel_id):
    """GET /channels يُعيد قائمة القنوات."""
    resp = await api_client.get("/api/v1/channels")
    assert resp.status_code == 200
    channels = resp.json()
    assert isinstance(channels, list)
    ids = [ch["id"] for ch in channels]
    assert sample_channel_id in ids


@pytest.mark.asyncio
async def test_get_channel_by_id(api_client, sample_channel_id):
    """GET /channels/{id} يُعيد قناة بمعرّفها."""
    resp = await api_client.get(f"/api/v1/channels/{sample_channel_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_channel_id


@pytest.mark.asyncio
async def test_get_channel_not_found(api_client):
    """GET /channels/{id} يُعيد 404 لمعرّف غير موجود."""
    resp = await api_client.get("/api/v1/channels/non_existent_id_xyz")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_channel(api_client, sample_channel_id):
    """PUT /channels/{id} يُحدّث بيانات القناة."""
    resp = await api_client.put(
        f"/api/v1/channels/{sample_channel_id}",
        json={"description": "وصف محدّث"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_channel_id


@pytest.mark.asyncio
async def test_channel_status_endpoint(api_client, sample_channel_id):
    """GET /channels/{id}/status يُعيد إحصائيات القناة."""
    resp = await api_client.get(f"/api/v1/channels/{sample_channel_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "total_runs" in data
    assert "total_fetched" in data


@pytest.mark.asyncio
async def test_channel_audit_log(api_client, sample_channel_id):
    """GET /channels/{id}/audit يُعيد سجل audit."""
    resp = await api_client.get(f"/api/v1/channels/{sample_channel_id}/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert isinstance(data["events"], list)


@pytest.mark.asyncio
async def test_pause_and_resume_channel(api_client):
    """PATCH /channels/{id}/pause و /resume يعملان بشكل صحيح."""
    # إنشاء قناة جديدة
    create_resp = await api_client.post("/api/v1/channels", json={
        "name": "Pause Test Channel",
        "source": {"url": "https://example.com/rss", "type": "demo"},
    })
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    # إيقاف مؤقت
    pause_resp = await api_client.patch(f"/api/v1/channels/{cid}/pause")
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    # إيقاف مرة ثانية يُعيد 400
    pause_resp2 = await api_client.patch(f"/api/v1/channels/{cid}/pause")
    assert pause_resp2.status_code == 400

    # استئناف
    resume_resp = await api_client.patch(f"/api/v1/channels/{cid}/resume")
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "active"

    # تنظيف
    await api_client.delete(f"/api/v1/channels/{cid}")


# ─────────────────────────────────────────────
# Trigger
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trigger_channel(api_client, sample_channel_id):
    """POST /channels/{id}/trigger يُشغّل الـ pipeline."""
    resp = await api_client.post(f"/api/v1/channels/{sample_channel_id}/trigger")
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert "status" in data
    assert data["status"] in ("success", "partial", "empty")
    assert "fetched" in data
    assert "duration_ms" in data


@pytest.mark.asyncio
async def test_trigger_inactive_channel_returns_400(api_client):
    """تشغيل قناة inactive يُعيد 400."""
    create_resp = await api_client.post("/api/v1/channels", json={
        "name": "Inactive Channel",
        "source": {"url": "https://example.com/rss", "type": "demo"},
    })
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    # تغيير الحالة إلى inactive
    update_resp = await api_client.put(f"/api/v1/channels/{cid}", json={"status": "inactive"})
    assert update_resp.status_code == 200

    # تشغيل trigger يجب أن يُعيد 400
    trigger_resp = await api_client.post(f"/api/v1/channels/{cid}/trigger")
    assert trigger_resp.status_code == 400

    # تنظيف
    await api_client.delete(f"/api/v1/channels/{cid}")


@pytest.mark.asyncio
async def test_trigger_paused_channel_returns_400(api_client):
    """تشغيل قناة متوقفة مؤقتاً يُعيد 400."""
    create_resp = await api_client.post("/api/v1/channels", json={
        "name": "Pause Trigger Test",
        "source": {"url": "https://example.com/rss", "type": "demo"},
    })
    cid = create_resp.json()["id"]

    await api_client.patch(f"/api/v1/channels/{cid}/pause")

    trigger_resp = await api_client.post(f"/api/v1/channels/{cid}/trigger")
    assert trigger_resp.status_code == 400

    await api_client.delete(f"/api/v1/channels/{cid}")


# ─────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_channel_invalid_request(api_client):
    """إنشاء قناة ببيانات غير صالحة يُعيد 422."""
    resp = await api_client.post("/api/v1/channels", json={
        "name": "",
        "source": {"url": "not_a_url", "type": "rss"},
    })
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_update_channel_invalid_status(api_client, sample_channel_id):
    """تحديث القناة بحالة غير صالحة يُعيد 422."""
    resp = await api_client.put(
        f"/api/v1/channels/{sample_channel_id}",
        json={"status": "totally_invalid_status"},
    )
    assert resp.status_code == 422


# ─────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_channel(api_client):
    """DELETE /channels/{id} يحذف القناة ويُعيد 204."""
    create_resp = await api_client.post("/api/v1/channels", json={
        "name": "Delete Me",
        "source": {"url": "https://example.com/rss", "type": "demo"},
    })
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    delete_resp = await api_client.delete(f"/api/v1/channels/{cid}")
    assert delete_resp.status_code == 204

    get_resp = await api_client.get(f"/api/v1/channels/{cid}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_channel(api_client):
    """حذف قناة غير موجودة يُعيد 404."""
    resp = await api_client.delete("/api/v1/channels/does_not_exist_xyz")
    assert resp.status_code == 404
