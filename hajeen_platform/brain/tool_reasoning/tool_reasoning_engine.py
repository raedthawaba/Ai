"""
Tool Reasoning Engine
====================

Phase 11: Tool Reasoning Implementation
- Tool Selection
- Tool Planning
- Tool Validation
- Tool Retry
- Function Calling
- MCP Support
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    SEARCH = "search"
    CALCULATOR = "calculator"
    CODE = "code"
    FILE = "file"
    DATABASE = "database"
    API = "api"
    WEB = "web"
    DATA = "data"
    ML = "ml"
    CUSTOM = "custom"


class ToolStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    TIMEOUT = "timeout"


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


@dataclass
class Tool:
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter]
    returns: Dict[str, Any]
    is_async: bool = False
    timeout_seconds: int = 30
    retry_count: int = 3


@dataclass
class ToolExecution:
    execution_id: str
    tool_name: str
    parameters: Dict[str, Any]
    status: ToolStatus
    result: Any = None
    error: str = None
    start_time: float = field(default_factory=time.time)
    end_time: float = None
    confidence: float = 1.0


class MCPToolAdapter:
    """Adapter for Model Context Protocol tools."""
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """Register default built-in tools."""
        self.register_tool(Tool(
            name="search",
            description="Search the web for information",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter("query", "string", "Search query", required=True),
                ToolParameter("max_results", "number", "Maximum results", required=False, default=10),
            ],
            returns={"type": "array"},
        ))
        
        self.register_tool(Tool(
            name="calculate",
            description="Perform mathematical calculations",
            category=ToolCategory.CALCULATOR,
            parameters=[
                ToolParameter("expression", "string", "Mathematical expression", required=True),
            ],
            returns={"type": "number"},
        ))
        
        self.register_tool(Tool(
            name="execute_code",
            description="Execute Python code",
            category=ToolCategory.CODE,
            parameters=[
                ToolParameter("code", "string", "Python code to execute", required=True),
            ],
            returns={"type": "object"},
            is_async=True,
            timeout_seconds=60,
        ))
        
        self.register_tool(Tool(
            name="read_file",
            description="Read content from a file",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter("path", "string", "File path", required=True),
            ],
            returns={"type": "string"},
        ))
        
        self.register_tool(Tool(
            name="write_file",
            description="Write content to a file",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter("path", "string", "File path", required=True),
                ToolParameter("content", "string", "Content to write", required=True),
            ],
            returns={"type": "boolean"},
        ))
        
        self.register_tool(Tool(
            name="api_call",
            description="Make an HTTP API call",
            category=ToolCategory.API,
            parameters=[
                ToolParameter("url", "string", "API endpoint URL", required=True),
                ToolParameter("method", "string", "HTTP method", required=False, default="GET"),
                ToolParameter("body", "object", "Request body", required=False),
            ],
            returns={"type": "object"},
            timeout_seconds=60,
        ))
    
    def register_tool(self, tool: Tool):
        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
    
    def get_tool(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)
    
    def list_tools(self) -> List[Tool]:
        return list(self.tools.values())


class ToolRegistry:
    """Registry for tool implementations."""
    
    def __init__(self):
        self._implementations: Dict[str, Callable] = {}
        self._mcp_adapter = MCPToolAdapter()
    
    def register(self, name: str, func: Callable):
        self._implementations[name] = func
        logger.info(f"Registered implementation for tool: {name}")
    
    def get_implementation(self, name: str) -> Optional[Callable]:
        return self._implementations.get(name)
    
    def has_implementation(self, name: str) -> bool:
        return name in self._implementations
    
    def get_mcp_adapter(self) -> MCPToolAdapter:
        return self._mcp_adapter


class ToolSelector:
    """Intelligent tool selection."""
    
    def __init__(self, tool_registry: ToolRegistry):
        self.registry = tool_registry
    
    def select_tools(self, task: str, context: Dict[str, Any] = None) -> List[Tool]:
        """Select appropriate tools for a task."""
        context = context or {}
        available_tools = self.registry.get_mcp_adapter().list_tools()
        task_lower = task.lower()
        
        keyword_map = {
            "search": [ToolCategory.SEARCH, ToolCategory.WEB],
            "calculate": [ToolCategory.CALCULATOR],
            "math": [ToolCategory.CALCULATOR],
            "code": [ToolCategory.CODE],
            "python": [ToolCategory.CODE],
            "file": [ToolCategory.FILE],
            "read": [ToolCategory.FILE],
            "write": [ToolCategory.FILE],
            "api": [ToolCategory.API],
            "http": [ToolCategory.API],
        }
        
        selected_categories = set()
        for keyword, categories in keyword_map.items():
            if keyword in task_lower:
                selected_categories.update(categories)
        
        if not selected_categories:
            return available_tools[:3]
        
        selected = [t for t in available_tools if t.category in selected_categories]
        return selected[:5]


class ToolReasoningEngine:
    """
    Main tool reasoning engine.
    """
    
    def __init__(self):
        self.registry = ToolRegistry()
        self.selector = ToolSelector(self.registry)
        self.execution_history: List[ToolExecution] = []
        self._function_handlers: Dict[str, Callable] = {}
        logger.info("ToolReasoningEngine initialized")
    
    async def reason_about_tools(self, task: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Main entry point for tool reasoning."""
        context = context or {}
        selected_tools = self.selector.select_tools(task, context)
        
        return {
            "task": task,
            "selected_tools": [t.name for t in selected_tools],
            "tool_details": [
                {"name": t.name, "description": t.description, "category": t.category.value}
                for t in selected_tools
            ],
            "confidence": 0.8,
        }
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolExecution:
        """Execute a tool with given parameters."""
        execution_id = hashlib.md5(f"{tool_name}{time.time()}".encode()).hexdigest()[:12]
        
        tool = self.registry.get_mcp_adapter().get_tool(tool_name)
        if not tool:
            return ToolExecution(
                execution_id=execution_id,
                tool_name=tool_name,
                parameters=parameters,
                status=ToolStatus.FAILED,
                error=f"Tool not found: {tool_name}",
            )
        
        impl = self.registry.get_implementation(tool_name)
        if not impl and tool_name not in self._function_handlers:
            return ToolExecution(
                execution_id=execution_id,
                tool_name=tool_name,
                parameters=parameters,
                status=ToolStatus.FAILED,
                error=f"No implementation for tool: {tool_name}",
            )
        
        impl = impl or self._function_handlers.get(tool_name)
        
        try:
            if tool.is_async or asyncio.iscoroutinefunction(impl):
                result = await asyncio.wait_for(impl(**parameters), timeout=tool.timeout_seconds)
            else:
                result = impl(**parameters)
            
            execution = ToolExecution(
                execution_id=execution_id,
                tool_name=tool_name,
                parameters=parameters,
                status=ToolStatus.SUCCESS,
                result=result,
                end_time=time.time(),
            )
        except asyncio.TimeoutError:
            execution = ToolExecution(
                execution_id=execution_id,
                tool_name=tool_name,
                parameters=parameters,
                status=ToolStatus.TIMEOUT,
                error="Tool execution timed out",
                end_time=time.time(),
            )
        except Exception as e:
            execution = ToolExecution(
                execution_id=execution_id,
                tool_name=tool_name,
                parameters=parameters,
                status=ToolStatus.FAILED,
                error=str(e),
                end_time=time.time(),
            )
        
        self.execution_history.append(execution)
        return execution
    
    def register_function(self, name: str, handler: Callable):
        """Register a function as a tool handler."""
        self._function_handlers[name] = handler
        logger.info(f"Registered function handler: {name}")
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of all available tools."""
        tools = self.registry.get_mcp_adapter().list_tools()
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category.value,
                "has_implementation": self.registry.has_implementation(t.name),
            }
            for t in tools
        ]


_tool_reasoning_engine: Optional[ToolReasoningEngine] = None


def get_tool_reasoning_engine() -> ToolReasoningEngine:
    """Get singleton instance."""
    global _tool_reasoning_engine
    if _tool_reasoning_engine is None:
        _tool_reasoning_engine = ToolReasoningEngine()
    return _tool_reasoning_engine
