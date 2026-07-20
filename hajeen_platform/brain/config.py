"""
Brain Configuration — إعدادات محرك الاستدلال
============================================

إعدادات مركزية وموحدة لجميع مكوّنات Brain.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class ReasoningStrategyType(str, Enum):
    """استراتيجيات الاستدلال المتاحة."""
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHT = "tree_of_thought"
    DECOMPOSITION = "decomposition"
    ANALOGY = "analogy"
    FIRST_PRINCIPLES = "first_principles"
    MULTI_PERSPECTIVE = "multi_perspective"


class ReasoningStrategyConfig(BaseModel):
    """إعدادات استراتيجية الاستدلال."""
    default_strategy: ReasoningStrategyType = ReasoningStrategyType.CHAIN_OF_THOUGHT
    fallback_strategy: ReasoningStrategyType = ReasoningStrategyType.DECOMPOSITION
    max_steps: int = Field(default=10, ge=1, le=50)
    enable_alternatives: bool = True


class LLMConfig(BaseModel):
    """إعدادات الـ LLM."""
    primary_model: str = "gpt-4o"
    reasoning_model: str = "gpt-4o-mini"
    fallback_models: List[str] = ["gpt-4o-mini", "gpt-4o"]
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=100, le=32000)
    timeout_seconds: float = Field(default=30.0, ge=5.0, le=300.0)
    retry_attempts: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: float = Field(default=1.0, ge=0.1, le=10.0)


class RiskAssessmentConfig(BaseModel):
    """إعدادات تقييم المخاطر."""
    enabled: bool = True
    max_risks_per_analysis: int = Field(default=10, ge=1, le=50)
    include_mitigation_strategies: bool = True
    severity_threshold: str = "low"  # low, medium, high, critical


class SolutionConfig(BaseModel):
    """إعدادات اقتراح الحلول."""
    enabled: bool = True
    min_solutions: int = Field(default=2, ge=1, le=20)
    max_solutions: int = Field(default=5, ge=1, le=20)
    min_pros: int = Field(default=2, ge=1, le=10)
    max_pros: int = Field(default=5, ge=1, le=10)
    min_cons: int = Field(default=1, ge=1, le=10)
    max_cons: int = Field(default=4, ge=1, le=10)
    enable_feasibility_scoring: bool = True


class CacheConfig(BaseModel):
    """إعدادات التخزين المؤقت."""
    enabled: bool = True
    max_entries: int = Field(default=1000, ge=10)
    ttl_seconds: int = Field(default=3600, ge=60)
    cache_key_prefix: str = "reasoning"


class LoggingConfig(BaseModel):
    """إعدادات التسجيل."""
    level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    format: str = "json"  # json, text
    include_trace: bool = True
    include_timing: bool = True
    log_reasoning_steps: bool = True
    log_llm_calls: bool = True


class MetricsConfig(BaseModel):
    """إعدادات المقاييس."""
    enabled: bool = True
    track_latency: bool = True
    track_confidence: bool = True
    track_success_rate: bool = True
    track_strategy_usage: bool = True
    export_prometheus: bool = False
    metrics_prefix: str = "hajeen_brain"


class ErrorRecoveryConfig(BaseModel):
    """إعدادات استعادة الأخطاء."""
    enable_fallback: bool = True
    fallback_confidence: float = Field(default=0.3, ge=0.0, le=1.0)
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_on_llm_error: bool = True
    graceful_degradation: bool = True
    return_partial_results: bool = True


class ExecutionTraceConfig(BaseModel):
    """إعدادات سجل التنفيذ."""
    enabled: bool = True
    include_step_details: bool = True
    include_intermediate_results: bool = True
    max_trace_depth: int = Field(default=100, ge=10)
    persist_traces: bool = False
    trace_storage_path: Optional[Path] = None


class ReasoningEngineConfig(BaseModel):
    """الإعدادات الرئيسية لمحرك الاستدلال."""
    
    # الإعدادات الأساسية
    name: str = "ReasoningEngine"
    version: str = "1.0.0"
    environment: str = "production"
    
    # المكوّنات
    reasoning_strategy: ReasoningStrategyConfig = Field(default_factory=ReasoningStrategyConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    risk_assessment: RiskAssessmentConfig = Field(default_factory=RiskAssessmentConfig)
    solution: SolutionConfig = Field(default_factory=SolutionConfig)
    
    # التخزين والأداء
    cache: CacheConfig = Field(default_factory=CacheConfig)
    
    # المراقبة
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    
    # معالجة الأخطاء
    error_recovery: ErrorRecoveryConfig = Field(default_factory=ErrorRecoveryConfig)
    
    # سجل التنفيذ
    execution_trace: ExecutionTraceConfig = Field(default_factory=ExecutionTraceConfig)
    
    # حدود إضافية
    max_context_length: int = Field(default=10000, ge=100)
    enable_caching: bool = True
    enable_metrics: bool = True
    
    @classmethod
    def from_file(cls, path: Path) -> "ReasoningEngineConfig":
        """تحميل الإعدادات من ملف YAML أو JSON."""
        import json

        import yaml
        
        path = Path(path)
        if path.suffix in (".yaml", ".yml"):
            with open(path) as f:
                data = yaml.safe_load(f)
        elif path.suffix == ".json":
            with open(path) as f:
                data = json.load(f)
        else:
            raise ValueError(f"Unsupported config file format: {path.suffix}")
        
        return cls(**data)
    
    def to_file(self, path: Path) -> None:
        """حفظ الإعدادات إلى ملف."""
        import json

        import yaml
        
        path = Path(path)
        data = self.model_dump()
        
        if path.suffix in (".yaml", ".yml"):
            with open(path, "w") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        elif path.suffix == ".json":
            with open(path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported config file format: {path.suffix}")


# Rebuild models to resolve forward references
ReasoningStrategyConfig.model_rebuild()
ReasoningEngineConfig.model_rebuild()


# ── Default Config Singleton ───────────────────────────────────────────────────

_default_config: Optional[ReasoningEngineConfig] = None


def get_default_config() -> ReasoningEngineConfig:
    """الحصول على الإعدادات الافتراضية."""
    global _default_config
    if _default_config is None:
        _default_config = ReasoningEngineConfig()
    return _default_config


def configure_engine(config: ReasoningEngineConfig) -> None:
    """تعيين إعدادات مخصصة للمحرك."""
    global _default_config
    _default_config = config


def reset_config() -> None:
    """إعادة تعيين الإعدادات للافتراضية."""
    global _default_config
    _default_config = None
