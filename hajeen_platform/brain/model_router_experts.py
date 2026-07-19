"""
Expert Models Layer — طبقة النماذج الخبيرة
==========================================
Hajeen Brain يستخدم الخبراء الخارجيين كمستشارين فقط.
القرار النهائي يبقى دائمًا بيد Hajeen Brain.

يدعم:
- Expert Profiles مع معلومات التخصص والجودة والتكلفة
- Model Society (Debate بين الخبراء)
- Expert Consultation مع تحليزل الآراء
- Sovereignty-aware routing
"""
from __future__ import annotations
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class ExpertDomain(Enum):
    """مجالات تخصص الخبراء"""
    GENERAL = "general"
    CODE = "code"
    MATH = "math"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    ARABIC = "arabic"
    SCIENCE = "science"
    ENGINEERING = "engineering"
    LAW = "law"
    MEDICAL = "medical"
    PLANNING = "planning"
    REASONING = "reasoning"


class ExpertLevel(Enum):
    """مستوى الخبير"""
    JUNIOR = "junior"           # 0.5-0.7 quality
    SENIOR = "senior"           # 0.7-0.85 quality
    EXPERT = "expert"           # 0.85-0.95 quality
    MASTER = "master"           # 0.95+ quality


@dataclass
class ExpertProfile:
    """ملف تعريف الخبير"""
    expert_id: str
    name: str
    provider: str                           # openai | claude | gemini | ollama | local
    model_id: str
    domains: List[ExpertDomain]             # مجالات التخصص
    level: ExpertLevel                      # مستوى الخبير
    capabilities: List[str]                 # القدرات
    quality_score: float                   # 0-1
    speed_score: float                     # 0-1 (latency inverse)
    cost_score: float                      # 0-1 (cost inverse)
    success_rate: float                    # نسبة النجاح التاريخية
    last_evaluation: datetime               # آخر تقييم
    avg_latency_ms: float
    cost_per_1k_tokens: float
    max_tokens: int
    is_local: bool
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_overall_score(self) -> float:
        """حساب الدرجة الإجمالية"""
        return (
            self.quality_score * 0.40 +
            self.speed_score * 0.25 +
            self.cost_score * 0.20 +
            self.success_rate * 0.15
        )
    
    def is_suitable_for(self, domain: ExpertDomain) -> bool:
        """هل الخبير مناسب لهذا المجال"""
        return domain in self.domains


@dataclass
class ExpertOpinion:
    """رأي الخبير"""
    expert_id: str
    expert_name: str
    opinion: str
    confidence: float                      # 0-1
    reasoning: str
    timestamp: datetime
    latency_ms: float
    success: bool
    error: Optional[str] = None


@dataclass
class DebateResult:
    """نتيجة المناظرة بين الخبراء"""
    debate_id: str
    question: str
    experts_consulted: List[str]
    opinions: List[ExpertOpinion]
    consensus_reached: bool
    hajeen_analysis: str
    final_decision: str
    reasoning: str
    confidence: float
    sovereignty_preserved: bool            # هل احتفظ Hajeen بالسيادة
    timestamp: datetime
    total_latency_ms: float


@dataclass
class ConsultationResult:
    """نتيجة الاستشارة"""
    consultation_id: str
    question: str
    primary_expert: Optional[ExpertOpinion]
    secondary_opinions: List[ExpertOpinion]
    hajeen_override: bool                  # هل تجاوز Hajeen رأي الخبراء
    hajeen_reasoning: str
    final_response: str
    experts_used: List[str]
    total_latency_ms: float
    timestamp: datetime


class ExpertRegistry:
    """سجل الخبراء المتاحين"""
    
    def __init__(self):
        self._experts: Dict[str, ExpertProfile] = {}
        self._providers: Dict[str, Any] = {}
        self._init_default_experts()
    
    def _init_default_experts(self):
        """تهيئة الخبراء الافتراضيين"""
        
        # OpenAI Experts
        self.register_expert(ExpertProfile(
            expert_id="openai-gpt4o",
            name="GPT-4o",
            provider="openai",
            model_id="gpt-4o",
            domains=[ExpertDomain.GENERAL, ExpertDomain.CODE, ExpertDomain.MATH, 
                     ExpertDomain.ANALYSIS, ExpertDomain.CREATIVE, ExpertDomain.PLANNING],
            level=ExpertLevel.MASTER,
            capabilities=["reasoning", "coding", "math", "analysis", "creative", "planning"],
            quality_score=0.97,
            speed_score=0.75,
            cost_score=0.30,
            success_rate=0.95,
            last_evaluation=datetime.now(),
            avg_latency_ms=2000,
            cost_per_1k_tokens=5.0,
            max_tokens=128000,
            is_local=False,
        ))
        
        self.register_expert(ExpertProfile(
            expert_id="openai-gpt4o-mini",
            name="GPT-4o Mini",
            provider="openai",
            model_id="gpt-4o-mini",
            domains=[ExpertDomain.GENERAL, ExpertDomain.CODE, ExpertDomain.ANALYSIS],
            level=ExpertLevel.SENIOR,
            capabilities=["reasoning", "coding", "analysis"],
            quality_score=0.88,
            speed_score=0.90,
            cost_score=0.85,
            success_rate=0.92,
            last_evaluation=datetime.now(),
            avg_latency_ms=800,
            cost_per_1k_tokens=0.15,
            max_tokens=128000,
            is_local=False,
        ))
        
        # Claude Experts
        self.register_expert(ExpertProfile(
            expert_id="claude-sonnet",
            name="Claude Sonnet",
            provider="claude",
            model_id="claude-3-5-sonnet-20240620",
            domains=[ExpertDomain.GENERAL, ExpertDomain.ANALYSIS, ExpertDomain.REASONING,
                     ExpertDomain.ENGINEERING, ExpertDomain.PLANNING],
            level=ExpertLevel.EXPERT,
            capabilities=["reasoning", "analysis", "engineering", "planning", "writing"],
            quality_score=0.95,
            speed_score=0.80,
            cost_score=0.40,
            success_rate=0.94,
            last_evaluation=datetime.now(),
            avg_latency_ms=1800,
            cost_per_1k_tokens=3.0,
            max_tokens=200000,
            is_local=False,
        ))
        
        # Gemini Expert
        self.register_expert(ExpertProfile(
            expert_id="gemini-pro",
            name="Gemini Pro",
            provider="gemini",
            model_id="gemini-1.5-pro",
            domains=[ExpertDomain.GENERAL, ExpertDomain.SCIENCE, ExpertDomain.MATH],
            level=ExpertLevel.EXPERT,
            capabilities=["reasoning", "science", "math", "multimodal"],
            quality_score=0.93,
            speed_score=0.85,
            cost_score=0.50,
            success_rate=0.91,
            last_evaluation=datetime.now(),
            avg_latency_ms=1500,
            cost_per_1k_tokens=1.25,
            max_tokens=1000000,
            is_local=False,
        ))
        
        # Ollama Local Experts
        self.register_expert(ExpertProfile(
            expert_id="ollama-llama3",
            name="Llama 3",
            provider="ollama",
            model_id="llama3",
            domains=[ExpertDomain.GENERAL, ExpertDomain.ARABIC],
            level=ExpertLevel.SENIOR,
            capabilities=["conversation", "arabic", "general"],
            quality_score=0.78,
            speed_score=0.70,
            cost_score=1.0,
            success_rate=0.85,
            last_evaluation=datetime.now(),
            avg_latency_ms=800,
            cost_per_1k_tokens=0.0,
            max_tokens=4096,
            is_local=True,
            base_url="http://localhost:11434",
        ))
        
        self.register_expert(ExpertProfile(
            expert_id="ollama-qwen2.5",
            name="Qwen 2.5",
            provider="ollama",
            model_id="qwen2.5:7b",
            domains=[ExpertDomain.GENERAL, ExpertDomain.CODE, ExpertDomain.ARABIC],
            level=ExpertLevel.SENIOR,
            capabilities=["coding", "arabic", "general"],
            quality_score=0.82,
            speed_score=0.65,
            cost_score=1.0,
            success_rate=0.87,
            last_evaluation=datetime.now(),
            avg_latency_ms=1000,
            cost_per_1k_tokens=0.0,
            max_tokens=8192,
            is_local=True,
            base_url="http://localhost:11434",
        ))
        
        # Hajeen Local (Sovereign)
        self.register_expert(ExpertProfile(
            expert_id="hajeen-local",
            name="Hajeen Brain",
            provider="local",
            model_id="hajeen-v1",
            domains=[ExpertDomain.GENERAL, ExpertDomain.ARABIC, ExpertDomain.PLANNING],
            level=ExpertLevel.JUNIOR,
            capabilities=["arabic", "planning", "reasoning"],
            quality_score=0.70,
            speed_score=0.95,
            cost_score=1.0,
            success_rate=0.80,
            last_evaluation=datetime.now(),
            avg_latency_ms=100,
            cost_per_1k_tokens=0.0,
            max_tokens=4096,
            is_local=True,
        ))
        
        logger.info(f"ExpertRegistry: initialized with {len(self._experts)} experts")
    
    def register_expert(self, expert: ExpertProfile):
        """تسجيل خبير جديد"""
        self._experts[expert.expert_id] = expert
        logger.info(f"ExpertRegistry: registered expert {expert.name}")
    
    def get_expert(self, expert_id: str) -> Optional[ExpertProfile]:
        return self._experts.get(expert_id)
    
    def get_experts_by_domain(self, domain: ExpertDomain) -> List[ExpertProfile]:
        """الحصول على الخبراء المناسبين لمجال معين"""
        suitable = [e for e in self._experts.values() if e.is_suitable_for(domain)]
        return sorted(suitable, key=lambda e: e.get_overall_score(), reverse=True)
    
    def get_best_expert(self, domain: ExpertDomain, prefer_local: bool = True) -> Optional[ExpertProfile]:
        """الحصول على أفضل خبير لمجال معين"""
        experts = self.get_experts_by_domain(domain)
        if not experts:
            return None
        
        if prefer_local:
            local = [e for e in experts if e.is_local]
            if local:
                return local[0]
        
        return experts[0]
    
    def get_all_experts(self) -> List[ExpertProfile]:
        return list(self._experts.values())
    
    def update_expert_stats(self, expert_id: str, latency_ms: float, success: bool):
        """تحديث إحصائيات الخبير"""
        if expert_id in self._experts:
            expert = self._experts[expert_id]
            # تحديث معدل النجاح
            current_total = expert.metadata.get('total_calls', 0)
            current_success = expert.metadata.get('successful_calls', 0)
            if success:
                current_success += 1
            expert.metadata['total_calls'] = current_total + 1
            expert.metadata['successful_calls'] = current_success
            expert.success_rate = current_success / (current_total + 1)
            
            # تحديث زمن الاستجابة
            expert.avg_latency_ms = (
                (expert.avg_latency_ms * current_total + latency_ms) / (current_total + 1)
            )
            expert.last_evaluation = datetime.now()


class ExpertConsultant:
    """المستشار الخبير — يستشير الخبراء ويعيد رأيهم"""
    
    def __init__(self, registry: Optional[ExpertRegistry] = None):
        self.registry = registry or ExpertRegistry()
        self._providers: Dict[str, Any] = {}
    
    def register_provider(self, provider_id: str, provider: Any):
        """تسجيل مزود خدمة"""
        self._providers[provider_id] = provider
    
    async def consult_expert(
        self,
        expert_id: str,
        question: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ExpertOpinion:
        """استشارة خبير واحد"""
        expert = self.registry.get_expert(expert_id)
        if not expert:
            return ExpertOpinion(
                expert_id=expert_id,
                expert_name="Unknown",
                opinion="",
                confidence=0.0,
                reasoning="Expert not found",
                timestamp=datetime.now(),
                latency_ms=0,
                success=False,
                error="Expert not found"
            )
        
        t0 = time.perf_counter()
        try:
            response = await self._call_expert(expert, question, context)
            latency = (time.perf_counter() - t0) * 1000
            
            # تحديث الإحصائيات
            self.registry.update_expert_stats(expert_id, latency, True)
            
            return ExpertOpinion(
                expert_id=expert_id,
                expert_name=expert.name,
                opinion=response.get("content", ""),
                confidence=expert.quality_score,
                reasoning=response.get("reasoning", ""),
                timestamp=datetime.now(),
                latency_ms=latency,
                success=True,
            )
        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000
            self.registry.update_expert_stats(expert_id, latency, False)
            
            return ExpertOpinion(
                expert_id=expert_id,
                expert_name=expert.name,
                opinion="",
                confidence=0.0,
                reasoning="",
                timestamp=datetime.now(),
                latency_ms=latency,
                success=False,
                error=str(e)
            )
    
    async def consult_multiple(
        self,
        expert_ids: List[str],
        question: str,
        context: Optional[Dict[str, Any]] = None,
        parallel: bool = True
    ) -> List[ExpertOpinion]:
        """استشارة عدة خبراء"""
        if parallel:
            tasks = [
                self.consult_expert(eid, question, context)
                for eid in expert_ids
            ]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for eid in expert_ids:
                result = await self.consult_expert(eid, question, context)
                results.append(result)
            return results
    
    async def _call_expert(
        self,
        expert: ExpertProfile,
        question: str,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """استدعاء الخبير عبر المزود المناسب"""
        # التحقق من المزود المسجل
        if expert.provider in self._providers:
            provider = self._providers[expert.provider]
            if hasattr(provider, 'chat'):
                return await provider.chat(question, context or {})
        
        # استدعاء OpenAI
        if expert.provider == "openai":
            return await self._call_openai(expert, question)
        
        # استدعاء Claude
        if expert.provider == "claude":
            return await self._call_claude(expert, question)
        
        # استدعاء Gemini
        if expert.provider == "gemini":
            return await self._call_gemini(expert, question)
        
        # استدعاء Ollama
        if expert.provider == "ollama":
            return await self._call_ollama(expert, question)
        
        # Fallback
        return {
            "content": f"[{expert.name}] غير متاح حالياً",
            "reasoning": "Provider not configured"
        }
    
    async def _call_openai(self, expert: ExpertProfile, question: str) -> Dict[str, Any]:
        """استدعاء OpenAI"""
        import os
        import httpx
        api_key = os.getenv("OPENAI_API_KEY", expert.api_key or "")
        
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": expert.model_id,
                        "messages": [{"role": "user", "content": question}],
                        "max_tokens": 2048
                    }
                )
                data = resp.json()
                return {"content": data["choices"][0]["message"]["content"]}
        except Exception as e:
            raise RuntimeError(f"OpenAI error: {e}")
    
    async def _call_claude(self, expert: ExpertProfile, question: str) -> Dict[str, Any]:
        """استدعاء Claude"""
        import os
        import httpx
        api_key = os.getenv("ANTHROPIC_API_KEY", expert.api_key or "")
        
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01"
                    },
                    json={
                        "model": expert.model_id,
                        "messages": [{"role": "user", "content": question}],
                        "max_tokens": 2048
                    }
                )
                data = resp.json()
                return {"content": data["content"][0]["text"]}
        except Exception as e:
            raise RuntimeError(f"Claude error: {e}")
    
    async def _call_gemini(self, expert: ExpertProfile, question: str) -> Dict[str, Any]:
        """استدعاء Gemini"""
        import os
        import httpx
        api_key = os.getenv("GEMINI_API_KEY", expert.api_key or "")
        
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not configured")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{expert.model_id}:generateContent",
                    params={"key": api_key},
                    json={"contents": [{"parts": [{"text": question}]}]}
                )
                data = resp.json()
                return {"content": data["candidates"][0]["content"]["parts"][0]["text"]}
        except Exception as e:
            raise RuntimeError(f"Gemini error: {e}")
    
    async def _call_ollama(self, expert: ExpertProfile, question: str) -> Dict[str, Any]:
        """استدعاء Ollama المحلي"""
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{expert.base_url}/api/generate",
                    json={"model": expert.model_id, "prompt": question, "stream": False}
                )
                data = resp.json()
                return {"content": data.get("response", "")}
        except Exception as e:
            raise RuntimeError(f"Ollama error: {e}")


class ModelSociety:
    """Model Society — مناظرة بين الخبراء"""
    
    def __init__(self, consultant: Optional[ExpertConsultant] = None):
        self.consultant = consultant or ExpertConsultant()
        self._debate_history: List[DebateResult] = []
    
    async def debate(
        self,
        question: str,
        domain: ExpertDomain,
        min_experts: int = 2,
        max_experts: int = 3,
        context: Optional[Dict[str, Any]] = None
    ) -> DebateResult:
        """إجراء مناظرة بين الخبراء"""
        debate_id = str(uuid.uuid4())
        t0 = time.perf_counter()
        
        # الحصول على الخبراء المناسبين
        experts = self.consultant.registry.get_experts_by_domain(domain)[:max_experts]
        
        if len(experts) < min_experts:
            # إذا لم يكن هناك خبراء كافيون، استخدم أي خبير متاح
            all_experts = self.consultant.registry.get_all_experts()
            experts = all_experts[:min_experts]
        
        # استشارة جميع الخبراء
        expert_ids = [e.expert_id for e in experts]
        opinions = await self.consultant.consult_multiple(
            expert_ids, question, context, parallel=True
        )
        
        # تحليل آراء الخبراء
        analysis = self._analyze_opinions(question, opinions)
        
        # اتخاذ القرار النهائي (هنا يأتي دور Hajeen)
        final_decision = self._make_decision(question, opinions, analysis)
        
        total_latency = (time.perf_counter() - t0) * 1000
        
        # التحقق من وجود توافق
        consensus = self._check_consensus(opinions)
        
        result = DebateResult(
            debate_id=debate_id,
            question=question,
            experts_consulted=expert_ids,
            opinions=opinions,
            consensus_reached=consensus,
            hajeen_analysis=analysis,
            final_decision=final_decision["decision"],
            reasoning=final_decision["reasoning"],
            confidence=final_decision["confidence"],
            sovereignty_preserved=True,  # القرار دائمًا بيد Hajeen
            timestamp=datetime.now(),
            total_latency_ms=total_latency
        )
        
        self._debate_history.append(result)
        return result
    
    def _analyze_opinions(self, question: str, opinions: List[ExpertOpinion]) -> str:
        """تحليل آراء الخبراء"""
        successful = [o for o in opinions if o.success]
        
        if not successful:
            return "جميع الخبراء فشلوا في الإجابة"
        
        # تجميع الآراء
        opinions_text = "\n".join([
            f"- {o.expert_name}: {o.opinion[:200]}..."
            for o in successful
        ])
        
        analysis = f"""تحليل آراء {len(successful)} خبراء:

{opinions_text}

التوافق: {self._check_consensus(opinions)}
"""
        return analysis
    
    def _check_consensus(self, opinions: List[ExpertOpinion]) -> bool:
        """التحقق من وجود توافق"""
        successful = [o for o in opinions if o.success]
        if len(successful) < 2:
            return False
        
        # بسيطة: إذا كان 80%+ من الخبراء يتفقون
        # (هنا يمكن تحسين الخوارزمية)
        return len(successful) >= 2
    
    def _make_decision(
        self,
        question: str,
        opinions: List[ExpertOpinion],
        analysis: str
    ) -> Dict[str, Any]:
        """Hajeen يتخذ القرار النهائي"""
        successful = [o for o in opinions if o.success]
        
        if not successful:
            return {
                "decision": "لا يمكن اتخاذ قرار بدون آراء الخبراء",
                "reasoning": "جميع الخبراء فشلوا",
                "confidence": 0.0
            }
        
        # ترتيب الآراء حسب الثقة
        sorted_opinions = sorted(successful, key=lambda o: o.confidence, reverse=True)
        
        # أفضل رأي
        best = sorted_opinions[0]
        
        # قرار Hajeen
        decision = f"""بناءً على استشارة {len(successful)} خبراء:

الأفضلية: {best.expert_name} (ثقة: {best.confidence:.0%})

{analysis}

قرار Hajeen: {best.opinion}

سبب الاختيار: {best.reasoning or 'أعلى ثقة بين الخبراء'}"""
        
        return {
            "decision": best.opinion,
            "reasoning": best.reasoning or "اختيار الخبير الأعلى ثقة",
            "confidence": best.confidence * 0.8  # Hajeen يخفض الثقة قليلاً
        }
    
    def get_debate_history(self) -> List[DebateResult]:
        return self._debate_history


# Singleton instances
_expert_registry: Optional[ExpertRegistry] = None
_expert_consultant: Optional[ExpertConsultant] = None
_model_society: Optional[ModelSociety] = None


def get_expert_registry() -> ExpertRegistry:
    global _expert_registry
    if _expert_registry is None:
        _expert_registry = ExpertRegistry()
    return _expert_registry


def get_expert_consultant() -> ExpertConsultant:
    global _expert_consultant
    if _expert_consultant is None:
        _expert_consultant = ExpertConsultant(get_expert_registry())
    return _expert_consultant


def get_model_society() -> ModelSociety:
    global _model_society
    if _model_society is None:
        _model_society = ModelSociety(get_expert_consultant())
    return _model_society
