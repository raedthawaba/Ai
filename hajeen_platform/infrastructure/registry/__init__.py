"""
Service & Resource Registries
============================

Provides dynamic registries for:
- Models (LLM providers)
- Tools (agent tools)
- Prompts (prompt templates)
- Workflows (multi-step workflows)
- Datasets (training data)

All registries support:
- Dynamic registration
- Lookup by name/category
- Versioning
- Metadata
- Lazy loading
"""

from __future__ import annotations

import logging
from typing import (
    Any, Callable, Dict, Generic, List, Optional, 
    Type, TypeVar, Callable, Set, Tuple
)
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RegistryCategory(Enum):
    """Registry category."""
    MODEL = "model"
    TOOL = "tool"
    PROMPT = "prompt"
    WORKFLOW = "workflow"
    DATASET = "dataset"
    SERVICE = "service"
    CUSTOM = "custom"


@dataclass
class RegistryEntry:
    """Base registry entry."""
    name: str
    category: RegistryCategory
    version: str = "1.0.0"
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    registered_at: datetime = field(default_factory=datetime.utcnow)
    registered_by: str = "system"
    tags: Set[str] = field(default_factory=set)
    dependencies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "category": self.category.value,
            "version": self.version,
            "description": self.description,
            "metadata": self.metadata,
            "enabled": self.enabled,
            "registered_at": self.registered_at.isoformat(),
            "registered_by": self.registered_by,
            "tags": list(self.tags),
            "dependencies": self.dependencies,
        }


@dataclass
class ModelEntry(RegistryEntry):
    """Model registry entry."""
    provider: str = ""
    model_id: str = ""
    capabilities: Set[str] = field(default_factory=set)
    context_window: int = 0
    max_tokens: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    latency_ms_avg: float = 0.0
    accuracy_score: float = 0.0
    is_local: bool = False
    endpoint: Optional[str] = None
    auth_type: str = "api_key"


@dataclass
class ToolEntry(RegistryEntry):
    """Tool registry entry."""
    tool_type: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable] = None
    permissions_required: List[str] = field(default_factory=list)
    rate_limit: Optional[int] = None  # calls per minute


@dataclass
class PromptEntry(RegistryEntry):
    """Prompt registry entry."""
    template: str = ""
    variables: List[str] = field(default_factory=list)
    system_prompt: str = ""
    examples: List[Dict[str, str]] = field(default_factory=list)
    models_compatible: Set[str] = field(default_factory=set)
    temperature: float = 0.7
    max_tokens: int = 2048


@dataclass 
class WorkflowEntry(RegistryEntry):
    """Workflow registry entry."""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300
    retry_on_failure: bool = True
    max_retries: int = 3


@dataclass
class DatasetEntry(RegistryEntry):
    """Dataset registry entry."""
    dataset_type: str = ""
    source_url: Optional[str] = None
    record_count: int = 0
    schema: Dict[str, Any] = field(default_factory=dict)
    format: str = "jsonl"
    size_bytes: int = 0
    version_info: Dict[str, Any] = field(default_factory=dict)


class Registry:
    """
    Base registry with common functionality.
    
    Usage:
        registry = Registry("my_registry")
        
        # Register items
        registry.register("item1", {"key": "value"})
        registry.register("item2", {"key": "value2"}, category=RegistryCategory.TOOL)
        
        # Lookup
        item = registry.get("item1")
        all_items = registry.list()
        tools = registry.list(category=RegistryCategory.TOOL)
    """
    
    def __init__(self, name: str):
        self.name = name
        self._entries: Dict[str, RegistryEntry] = {}
        self._lock = threading.RLock()
        self._listeners: List[Callable] = []
        self._initialized = False
    
    def register(
        self,
        name: str,
        entry: Optional[RegistryEntry] = None,
        category: RegistryCategory = RegistryCategory.CUSTOM,
        version: str = "1.0.0",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> RegistryEntry:
        """
        Register an item.
        
        Args:
            name: Unique name
            entry: Pre-built entry (if None, creates one)
            category: Category
            version: Version string
            description: Description
            metadata: Additional metadata
            **kwargs: Entry-specific fields
            
        Returns:
            Created registry entry
        """
        with self._lock:
            key = self._make_key(name, category)
            
            if key in self._entries:
                logger.warning(f"Overwriting existing entry: {key}")
            
            if entry is None:
                entry = RegistryEntry(
                    name=name,
                    category=category,
                    version=version,
                    description=description,
                    metadata=metadata or {},
                )
                # Apply additional kwargs
                for k, v in kwargs.items():
                    if hasattr(entry, k):
                        setattr(entry, k, v)
            
            entry.name = name
            entry.category = category
            self._entries[key] = entry
            
            # Notify listeners
            for listener in self._listeners:
                try:
                    listener("register", entry)
                except Exception as e:
                    logger.error(f"Registry listener error: {e}")
            
            logger.debug(f"Registered: {key}")
            return entry
    
    def unregister(self, name: str, category: Optional[RegistryCategory] = None) -> bool:
        """Unregister an item."""
        with self._lock:
            if category:
                key = self._make_key(name, category)
                if key in self._entries:
                    del self._entries[key]
                    return True
            else:
                # Try all categories
                for cat in RegistryCategory:
                    key = self._make_key(name, cat)
                    if key in self._entries:
                        del self._entries[key]
                        return True
            return False
    
    def get(self, name: str, category: Optional[RegistryCategory] = None) -> Optional[RegistryEntry]:
        """Get an entry by name."""
        with self._lock:
            if category:
                return self._entries.get(self._make_key(name, category))
            
            # Search all categories
            for cat in RegistryCategory:
                entry = self._entries.get(self._make_key(name, cat))
                if entry:
                    return entry
            return None
    
    def list(
        self,
        category: Optional[RegistryCategory] = None,
        tags: Optional[Set[str]] = None,
        enabled_only: bool = True,
        include_metadata: bool = False
    ) -> List[RegistryEntry]:
        """List entries, optionally filtered."""
        with self._lock:
            results = []
            
            for entry in self._entries.values():
                if enabled_only and not entry.enabled:
                    continue
                if category and entry.category != category:
                    continue
                if tags and not tags.intersection(entry.tags):
                    continue
                results.append(entry)
            
            return results
    
    def find(self, predicate: Callable[[RegistryEntry], bool]) -> List[RegistryEntry]:
        """Find entries matching a predicate."""
        with self._lock:
            return [e for e in self._entries.values() if predicate(e)]
    
    def count(self, category: Optional[RegistryCategory] = None) -> int:
        """Count entries."""
        with self._lock:
            if category:
                return sum(1 for e in self._entries.values() if e.category == category)
            return len(self._entries)
    
    def exists(self, name: str, category: Optional[RegistryCategory] = None) -> bool:
        """Check if entry exists."""
        return self.get(name, category) is not None
    
    def enable(self, name: str, category: Optional[RegistryCategory] = None) -> bool:
        """Enable an entry."""
        entry = self.get(name, category)
        if entry:
            entry.enabled = True
            return True
        return False
    
    def disable(self, name: str, category: Optional[RegistryCategory] = None) -> bool:
        """Disable an entry."""
        entry = self.get(name, category)
        if entry:
            entry.enabled = False
            return True
        return False
    
    def add_listener(self, listener: Callable):
        """Add a registry change listener."""
        self._listeners.append(listener)
    
    def clear(self):
        """Clear all entries."""
        with self._lock:
            self._entries.clear()
    
    def _make_key(self, name: str, category: RegistryCategory) -> str:
        """Create storage key."""
        return f"{category.value}:{name}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Export registry to dictionary."""
        return {
            "name": self.name,
            "count": len(self._entries),
            "entries": [e.to_dict() for e in self._entries.values()]
        }
    
    def __len__(self) -> int:
        return len(self._entries)
    
    def __contains__(self, name: str) -> bool:
        return self.exists(name)
    
    def __repr__(self) -> str:
        return f"<Registry {self.name} entries={len(self)}>"


class ModelRegistry(Registry):
    """Registry for AI models."""
    
    def __init__(self):
        super().__init__("models")
    
    def register_model(
        self,
        name: str,
        provider: str,
        model_id: str,
        capabilities: Set[str],
        context_window: int = 0,
        cost_input: float = 0,
        cost_output: float = 0,
        is_local: bool = False,
        **kwargs
    ) -> ModelEntry:
        """Register a model."""
        entry = ModelEntry(
            name=name,
            category=RegistryCategory.MODEL,
            provider=provider,
            model_id=model_id,
            capabilities=capabilities,
            context_window=context_window,
            cost_per_1k_input=cost_input,
            cost_per_1k_output=cost_output,
            is_local=is_local,
            **kwargs
        )
        return self.register(name, entry, category=RegistryCategory.MODEL)
    
    def get_model(self, name: str) -> Optional[ModelEntry]:
        """Get a model entry."""
        return self.get(name, RegistryCategory.MODEL)
    
    def list_models(
        self,
        provider: Optional[str] = None,
        capability: Optional[str] = None,
        local_only: bool = False
    ) -> List[ModelEntry]:
        """List models with filters."""
        models = self.list(category=RegistryCategory.MODEL)
        
        if provider:
            models = [m for m in models if m.provider == provider]
        
        if capability:
            models = [m for m in models if capability in m.capabilities]
        
        if local_only:
            models = [m for m in models if m.is_local]
        
        return models
    
    def find_best_model(
        self,
        capability: str,
        max_cost: Optional[float] = None,
        prefer_local: bool = True
    ) -> Optional[ModelEntry]:
        """Find best model for a capability."""
        candidates = self.list_models(capability=capability)
        
        if not candidates:
            return None
        
        # Filter by cost
        if max_cost:
            candidates = [
                m for m in candidates 
                if m.cost_per_1k_input + m.cost_per_1k_output <= max_cost
            ]
        
        if not candidates:
            return None
        
        # Prefer local
        if prefer_local:
            local = [m for m in candidates if m.is_local]
            if local:
                return local[0]
        
        # Return cheapest
        return min(candidates, key=lambda m: m.cost_per_1k_input + m.cost_per_1k_output)


class ToolRegistry(Registry):
    """Registry for agent tools."""
    
    def __init__(self):
        super().__init__("tools")
    
    def register_tool(
        self,
        name: str,
        tool_type: str,
        handler: Callable,
        input_schema: Optional[Dict] = None,
        output_schema: Optional[Dict] = None,
        permissions: Optional[List[str]] = None,
        **kwargs
    ) -> ToolEntry:
        """Register a tool."""
        entry = ToolEntry(
            name=name,
            category=RegistryCategory.TOOL,
            tool_type=tool_type,
            handler=handler,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            permissions_required=permissions or [],
            **kwargs
        )
        return self.register(name, entry, category=RegistryCategory.TOOL)
    
    def get_tool(self, name: str) -> Optional[ToolEntry]:
        """Get a tool entry."""
        return self.get(name, RegistryCategory.TOOL)
    
    def list_tools(self, tool_type: Optional[str] = None) -> List[ToolEntry]:
        """List tools with optional filter."""
        tools = self.list(category=RegistryCategory.TOOL)
        if tool_type:
            tools = [t for t in tools if t.tool_type == tool_type]
        return tools
    
    def execute_tool(self, name: str, **kwargs) -> Any:
        """Execute a tool by name."""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool not found: {name}")
        
        if not tool.enabled:
            raise ValueError(f"Tool disabled: {name}")
        
        if not tool.handler:
            raise ValueError(f"Tool has no handler: {name}")
        
        return tool.handler(**kwargs)


class PromptRegistry(Registry):
    """Registry for prompt templates."""
    
    def __init__(self):
        super().__init__("prompts")
    
    def register_prompt(
        self,
        name: str,
        template: str,
        variables: Optional[List[str]] = None,
        system_prompt: str = "",
        models: Optional[Set[str]] = None,
        **kwargs
    ) -> PromptEntry:
        """Register a prompt template."""
        entry = PromptEntry(
            name=name,
            category=RegistryCategory.PROMPT,
            template=template,
            variables=variables or [],
            system_prompt=system_prompt,
            models_compatible=models or set(),
            **kwargs
        )
        return self.register(name, entry, category=RegistryCategory.PROMPT)
    
    def get_prompt(self, name: str) -> Optional[PromptEntry]:
        """Get a prompt entry."""
        return self.get(name, RegistryCategory.PROMPT)
    
    def render_prompt(
        self,
        name: str,
        **variables
    ) -> Tuple[str, str]:
        """
        Render a prompt template with variables.
        
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        prompt = self.get_prompt(name)
        if not prompt:
            raise ValueError(f"Prompt not found: {name}")
        
        user_prompt = prompt.template
        for var in prompt.variables:
            if var in variables:
                user_prompt = user_prompt.replace(f"{{{var}}}", str(variables[var]))
        
        return prompt.system_prompt, user_prompt


class WorkflowRegistry(Registry):
    """Registry for multi-step workflows."""
    
    def __init__(self):
        super().__init__("workflows")
    
    def register_workflow(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        input_schema: Optional[Dict] = None,
        output_schema: Optional[Dict] = None,
        timeout: int = 300,
        **kwargs
    ) -> WorkflowEntry:
        """Register a workflow."""
        entry = WorkflowEntry(
            name=name,
            category=RegistryCategory.WORKFLOW,
            steps=steps,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            timeout_seconds=timeout,
            **kwargs
        )
        return self.register(name, entry, category=RegistryCategory.WORKFLOW)
    
    def get_workflow(self, name: str) -> Optional[WorkflowEntry]:
        """Get a workflow entry."""
        return self.get(name, RegistryCategory.WORKFLOW)


class DatasetRegistry(Registry):
    """Registry for training datasets."""
    
    def __init__(self):
        super().__init__("datasets")
    
    def register_dataset(
        self,
        name: str,
        dataset_type: str,
        source_url: Optional[str] = None,
        schema: Optional[Dict] = None,
        **kwargs
    ) -> DatasetEntry:
        """Register a dataset."""
        entry = DatasetEntry(
            name=name,
            category=RegistryCategory.DATASET,
            dataset_type=dataset_type,
            source_url=source_url,
            schema=schema or {},
            **kwargs
        )
        return self.register(name, entry, category=RegistryCategory.DATASET)
    
    def get_dataset(self, name: str) -> Optional[DatasetEntry]:
        """Get a dataset entry."""
        return self.get(name, RegistryCategory.DATASET)


# Alias for ServiceRegistry
ServiceRegistry = Registry

# Global registry instances
_model_registry: Optional[ModelRegistry] = None
_tool_registry: Optional[ToolRegistry] = None
_prompt_registry: Optional[PromptRegistry] = None
_workflow_registry: Optional[WorkflowRegistry] = None
_dataset_registry: Optional[DatasetRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get global model registry."""
    global _model_registry
    if _model_registry is None:
        _model_registry = ModelRegistry()
    return _model_registry


def get_tool_registry() -> ToolRegistry:
    """Get global tool registry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


def get_prompt_registry() -> PromptRegistry:
    """Get global prompt registry."""
    global _prompt_registry
    if _prompt_registry is None:
        _prompt_registry = PromptRegistry()
    return _prompt_registry


def get_workflow_registry() -> WorkflowRegistry:
    """Get global workflow registry."""
    global _workflow_registry
    if _workflow_registry is None:
        _workflow_registry = WorkflowRegistry()
    return _workflow_registry


def get_dataset_registry() -> DatasetRegistry:
    """Get global dataset registry."""
    global _dataset_registry
    if _dataset_registry is None:
        _dataset_registry = DatasetRegistry()
    return _dataset_registry
