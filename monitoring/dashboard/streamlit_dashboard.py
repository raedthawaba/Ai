"""Streamlit Dashboard — Phase 6 — لوحة مراقبة المنصة."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Streamlit lazy import لمنع الفشل عند عدم توفره
try:
    import streamlit as st
    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False


def _require_streamlit() -> None:
    if not _ST_AVAILABLE:
        raise ImportError("streamlit غير مثبّت — pip install streamlit")


def _load_metrics_from_log(log_path: str) -> List[Dict]:
    """تحميل الـ metrics من ملف JSONL."""
    records = []
    p = Path(log_path)
    if not p.exists():
        return records
    with p.open(encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    return records[-1000:]  # آخر 1000 سجل


def _get_health() -> Dict:
    """يستدعي الـ health checker."""
    try:
        import asyncio
        from monitoring.health.health_checker import HealthChecker
        checker = HealthChecker(timeout=3.0)
        loop = asyncio.new_event_loop()
        health = loop.run_until_complete(checker.check_all())
        loop.close()
        return health.to_dict()
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)}


def _get_metrics_text() -> str:
    try:
        from monitoring.metrics.prometheus_metrics import get_metrics_text
        return get_metrics_text()
    except Exception:
        return "# metrics not available"


def run_dashboard() -> None:
    """نقطة دخول الـ dashboard."""
    _require_streamlit()

    st.set_page_config(
        page_title="Hajeen AI Platform — Dashboard",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("🤖 Hajeen AI Platform — لوحة المراقبة")
    st.caption(f"آخر تحديث: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Sidebar
    st.sidebar.header("التنقل")
    page = st.sidebar.selectbox(
        "اختر الصفحة",
        ["صحة النظام", "مقاييس الاستيعاب", "مقاييس الـ RAG", "مقاييس Inference", "Prometheus Raw"],
    )

    if page == "صحة النظام":
        _page_health()
    elif page == "مقاييس الاستيعاب":
        _page_ingestion()
    elif page == "مقاييس الـ RAG":
        _page_rag()
    elif page == "مقاييس Inference":
        _page_inference()
    elif page == "Prometheus Raw":
        _page_prometheus()


def _page_health() -> None:
    st.header("🏥 صحة النظام")
    health = _get_health()
    status = health.get("status", "unknown")
    color = {"ok": "🟢", "degraded": "🟡", "down": "🔴"}.get(status, "⚪")

    st.metric("الحالة العامة", f"{color} {status.upper()}")

    components = health.get("components", {})
    if components:
        cols = st.columns(min(len(components), 4))
        for i, (name, info) in enumerate(components.items()):
            with cols[i % len(cols)]:
                s = info.get("status", "unknown")
                icon = {"ok": "✅", "degraded": "⚠️", "down": "❌"}.get(s, "❓")
                st.metric(name, f"{icon} {s}", delta=f"{info.get('latency_ms', 0):.1f}ms")
    else:
        st.info("لا توجد بيانات صحة متاحة")

    if st.button("تحديث"):
        st.rerun()


def _page_ingestion() -> None:
    st.header("📥 مقاييس الاستيعاب")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("المقالات المستوعبة", "—")
    with col2:
        st.metric("معدل الاستيعاب/دقيقة", "—")
    with col3:
        st.metric("الأخطاء", "—")
    st.info("اربط بـ Prometheus لعرض بيانات حقيقية")


def _page_rag() -> None:
    st.header("🔍 مقاييس البحث والـ RAG")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("طلبات البحث", "—")
    with col2:
        st.metric("متوسط الزمن (ms)", "—")
    with col3:
        st.metric("متوسط النتائج", "—")
    st.info("اربط بـ Prometheus لعرض بيانات حقيقية")


def _page_inference() -> None:
    st.header("🧠 مقاييس Inference")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("طلبات Inference", "—")
    with col2:
        st.metric("متوسط الزمن (s)", "—")
    with col3:
        st.metric("Tokens/ثانية", "—")
    st.info("اربط بـ Prometheus لعرض بيانات حقيقية")


def _page_prometheus() -> None:
    st.header("📊 Prometheus Metrics")
    text = _get_metrics_text()
    st.code(text[:5000], language="text")


if __name__ == "__main__":
    run_dashboard()
