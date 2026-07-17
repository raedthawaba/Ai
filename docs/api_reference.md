# Hajeen AI — API Reference
## مرجع واجهات برمجة التطبيقات

---

## Base URL
```
http://localhost:8000/api/v1
```

---

## Authentication
جميع الطلبات تحتاج إلى Bearer Token:
```http
Authorization: Bearer <jwt_token>
```

---

## Brain Endpoints (العقل المركزي)

### POST /brain/chat
معالجة رسالة عبر العقل المركزي الكامل.

**Request:**
```json
{
  "message": "ما هي أفضل طريقة لتحسين أداء قاعدة بيانات PostgreSQL؟",
  "session_id": "sess_abc123",
  "user_id": "user_456",
  "stream": false,
  "max_tokens": 2048,
  "temperature": 0.7,
  "force_model": null,
  "request_type": "chat"
}
```

**Response:**
```json
{
  "request_id": "req_xyz789",
  "session_id": "sess_abc123",
  "content": "لتحسين أداء PostgreSQL، يمكنك...",
  "trace": {
    "trace_id": "trace_001",
    "layers": {
      "policy": { "blocked": false, "decision": "allowed" },
      "intent": {
        "category": "analysis_evaluation",
        "primary_intent": "تحسين أداء قاعدة البيانات",
        "confidence": 0.94
      },
      "context": {
        "detected_domain": "database",
        "estimated_complexity": "complex",
        "relevant_memories_count": 2
      },
      "reasoning": {
        "strategy": "chain_of_thought",
        "steps_count": 4,
        "confidence": 0.89
      }
    },
    "metrics": {
      "total_latency_ms": 1240.5,
      "tokens_used": 342,
      "quality_score": 0.91
    }
  },
  "model_used": "qwen2.5-7b",
  "sovereignty": {
    "used_local_model": true,
    "used_rag": false
  }
}
```

---

### POST /brain/chat/stream
معالجة رسالة مع streaming للاستجابة.

**Request:** نفس `/brain/chat` مع `"stream": true`

**Response:** `text/event-stream`
```
data: {"token": "لتحسين", "done": false}
data: {"token": " أداء", "done": false}
data: {"done": true, "total_tokens": 342}
```

---

### GET /brain/trace/{request_id}
الحصول على تفاصيل execution trace لطلب محدد.

**Response:**
```json
{
  "trace_id": "trace_001",
  "request_id": "req_xyz789",
  "layers": { "..." },
  "metrics": { "..." },
  "created_at": 1720000000.0
}
```

---

### GET /brain/stats
إحصائيات العقل المركزي.

**Response:**
```json
{
  "total_requests": 1542,
  "successful": 1530,
  "failed": 8,
  "blocked_by_policy": 4,
  "avg_latency_ms": 1180.3,
  "total_tokens": 2845120,
  "version": "3.0.0"
}
```

---

## Learning Pipeline Endpoints

### POST /learning/run
تشغيل pipeline التعلم المستمر.

**Request:**
```json
{
  "data": [
    {
      "instruction": "ما هو الـ Transformer في الذكاء الاصطناعي؟",
      "output": "Transformer هو معمارية شبكة عصبية...",
      "domain": "ai_concepts",
      "source_model": "gpt-4o",
      "quality_score": 0.92
    }
  ],
  "require_approval": false
}
```

**Response:**
```json
{
  "run_id": "run_20240717_abc123",
  "status": "completed",
  "samples_collected": 150,
  "samples_after_cleaning": 148,
  "samples_after_dedup": 132,
  "samples_approved": 120,
  "evaluation_results": {
    "perplexity": 8.3,
    "accuracy": 0.87,
    "bleu": 0.52,
    "passes_threshold": true
  },
  "deployment_info": {
    "model_version": "hajeen-v20240717-abc12345",
    "deployed_at": 1720000000.0,
    "rollback_available": true
  }
}
```

---

### POST /learning/approve
الموافقة على العينات المنتظرة للمراجعة البشرية.

**Response:**
```json
{
  "approved_count": 95,
  "pending_count": 0
}
```

---

### GET /learning/stats
إحصائيات pipeline التعلم.

**Response:**
```json
{
  "total_runs": 12,
  "completed": 10,
  "deployed_models": 8,
  "pending_approval": 0,
  "approved_samples": 1240
}
```

---

### GET /learning/registry
سجل النماذج المنشورة.

**Response:**
```json
{
  "current_active": "hajeen-v20240717-abc12345",
  "models": [
    {
      "model_version": "hajeen-v20240717-abc12345",
      "status": "active",
      "evaluation": {
        "perplexity": 8.3,
        "accuracy": 0.87
      },
      "deployed_at_human": "2024-07-17 14:30:00"
    }
  ]
}
```

---

## Memory Endpoints

### GET /memory/session/{session_id}
الحصول على ذاكرة الجلسة.

### GET /memory/long-term/{session_id}
استرجاع الذاكرة طويلة الأمد.

### POST /memory/semantic/search
البحث الدلالي في الذاكرة.

**Request:**
```json
{
  "query": "أداء قاعدة البيانات",
  "top_k": 5,
  "session_id": "sess_abc123"
}
```

---

## Knowledge Graph Endpoints

### POST /knowledge/node
إضافة عقدة للرسم البياني.

### GET /knowledge/context/{entity}
الحصول على السياق المعرفي لكيان.

### POST /knowledge/query
الاستعلام عن العلاقات.

---

## Monitoring Endpoints

### GET /health
فحص صحة النظام.

**Response:**
```json
{
  "status": "healthy",
  "version": "3.0.0",
  "components": {
    "brain": "ok",
    "memory": "ok",
    "model_router": "ok",
    "workers": "ok",
    "database": "ok"
  },
  "uptime_seconds": 86400
}
```

### GET /metrics
مقاييس Prometheus.

### GET /sovereignty/report
تقرير استقلالية النظام.

---

## Error Codes

| Code | المعنى |
|------|--------|
| 400 | طلب غير صحيح (Bad Request) |
| 401 | غير مصرح (Unauthorized) |
| 403 | محظور بواسطة Policy Engine |
| 422 | خطأ في التحقق من البيانات |
| 429 | تجاوز حد الطلبات (Rate Limit) |
| 500 | خطأ داخلي في الخادم |
| 503 | الخدمة غير متاحة مؤقتاً |
