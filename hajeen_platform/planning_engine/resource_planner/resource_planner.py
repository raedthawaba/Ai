"""
Resource Planner - Planning Engine v1.0
=======================================

Manages resource estimation, allocation, and planning.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from ..core.base import BaseComponent
from ..core.models import (
    Task, TaskGraph, Resource, ResourceAllocation, ResourceType
)


class ResourcePlanner(BaseComponent):
    """
    Plans and manages resource allocation.
    
    Responsibilities:
    - Estimate resource requirements
    - Allocate resources to tasks
    - Track resource usage
    - Handle resource shortages
    """
    
    def __init__(self):
        super().__init__()
        self._resources: Dict[str, Resource] = {}
        self._allocations: List[ResourceAllocation] = []
        self._resource_templates: Dict[str, Dict[str, Any]] = {}
    
    async def _async_initialize(self) -> None:
        """Initialize the resource planner."""
        self._initialize_default_resources()
        self.logger.info("ResourcePlanner initialized")
    
    def _initialize_default_resources(self) -> None:
        """Initialize default resource templates."""
        self._resource_templates = {
            "compute": {
                "type": ResourceType.COMPUTE,
                "unit": "cores",
                "default_quantity": 1.0
            },
            "memory": {
                "type": ResourceType.MEMORY,
                "unit": "GB",
                "default_quantity": 1.0
            },
            "network": {
                "type": ResourceType.NETWORK,
                "unit": "Mbps",
                "default_quantity": 100.0
            },
            "storage": {
                "type": ResourceType.STORAGE,
                "unit": "GB",
                "default_quantity": 10.0
            },
            "credits": {
                "type": ResourceType.CREDITS,
                "unit": "credits",
                "default_quantity": 1000.0
            }
        }
    
    # =========================================================================
    # RESOURCE MANAGEMENT
    # =========================================================================
    
    def add_resource(
        self,
        name: str,
        resource_type: ResourceType,
        quantity: float,
        unit: str = "units"
    ) -> Resource:
        """Add a resource to the pool."""
        resource = Resource(
            resource_id=str(uuid.uuid4()),
            type=resource_type,
            name=name,
            quantity=quantity,
            unit=unit,
            available=quantity,
            reserved=0.0
        )
        
        self._resources[resource.resource_id] = resource
        self.logger.debug(f"Added resource: {name} ({resource_type.value})")
        
        return resource
    
    def get_resource(self, resource_id: str) -> Optional[Resource]:
        """Get a resource by ID."""
        return self._resources.get(resource_id)
    
    def get_resources_by_type(self, resource_type: ResourceType) -> List[Resource]:
        """Get all resources of a specific type."""
        return [r for r in self._resources.values() if r.type == resource_type]
    
    # =========================================================================
    # ESTIMATION
    # =========================================================================
    
    def estimate_requirements(
        self,
        task: Task
    ) -> List[Resource]:
        """Estimate resource requirements for a task."""
        requirements = []
        
        # Default estimates based on task type
        base_resources = {
            "action": [(ResourceType.COMPUTE, 0.5), (ResourceType.MEMORY, 0.1)],
            "query": [(ResourceType.COMPUTE, 1.0), (ResourceType.NETWORK, 50.0)],
            "analysis": [(ResourceType.COMPUTE, 2.0), (ResourceType.MEMORY, 0.5)],
            "verification": [(ResourceType.COMPUTE, 0.5), (ResourceType.MEMORY, 0.2)],
            "synthesis": [(ResourceType.COMPUTE, 1.5), (ResourceType.MEMORY, 0.3)],
            "decision": [(ResourceType.COMPUTE, 0.5), (ResourceType.MEMORY, 0.1)]
        }
        
        type_key = task.task_type.value if hasattr(task.task_type, 'value') else str(task.task_type)
        resources = base_resources.get(type_key, base_resources["action"])
        
        for res_type, quantity in resources:
            # Find matching resource
            matching = next(
                (r for r in self._resources.values() if r.type == res_type),
                None
            )
            
            if matching:
                resource = Resource(
                    resource_id=matching.resource_id,
                    type=matching.type,
                    name=matching.name,
                    quantity=quantity,
                    unit=matching.unit,
                    available=matching.available,
                    reserved=0.0
                )
                requirements.append(resource)
            else:
                # Create temporary resource
                resource = Resource(
                    resource_id=str(uuid.uuid4()),
                    type=res_type,
                    name=res_type.value,
                    quantity=quantity,
                    unit="units",
                    available=quantity,
                    reserved=0.0
                )
                requirements.append(resource)
        
        return requirements
    
    def estimate_total_requirements(
        self,
        task_graph: TaskGraph
    ) -> Dict[ResourceType, float]:
        """Estimate total resources needed for all tasks."""
        totals: Dict[ResourceType, float] = {}
        
        for task in task_graph.tasks.values():
            requirements = self.estimate_requirements(task)
            
            for resource in requirements:
                current = totals.get(resource.type, 0.0)
                totals[resource.type] = current + resource.quantity
        
        return totals
    
    # =========================================================================
    # ALLOCATION
    # =========================================================================
    
    def allocate_resources(
        self,
        task: Task,
        resources: Optional[List[Resource]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[ResourceAllocation]:
        """
        Allocate resources to a task.
        
        Returns:
            List of resource allocations
        """
        if resources is None:
            resources = self.estimate_requirements(task)
        
        allocations = []
        
        for resource in resources:
            # Check availability
            if resource.quantity > resource.remaining:
                self.logger.warning(
                    f"Insufficient resource {resource.name}: "
                    f"need {resource.quantity}, have {resource.remaining}"
                )
                # Partial allocation
                allocated_qty = resource.remaining
            else:
                allocated_qty = resource.quantity
            
            if allocated_qty <= 0:
                continue
            
            # Create allocation
            allocation = ResourceAllocation(
                task_id=task.task_id,
                resource_id=resource.resource_id,
                allocated_quantity=allocated_qty,
                start_time=start_time,
                end_time=end_time
            )
            
            # Update resource reserved amount
            resource.reserved += allocated_qty
            
            allocations.append(allocation)
            self._allocations.append(allocation)
        
        task.allocated_resources = allocations
        
        self.logger.debug(
            f"Allocated {len(allocations)} resources to task {task.task_id}"
        )
        
        return allocations
    
    def release_resources(self, task_id: str) -> None:
        """Release resources allocated to a task."""
        allocations = [a for a in self._allocations if a.task_id == task_id]
        
        for allocation in allocations:
            resource = self._resources.get(allocation.resource_id)
            if resource:
                resource.reserved -= allocation.allocated_quantity
                resource.reserved = max(0, resource.reserved)
        
        # Remove from active allocations
        self._allocations = [a for a in self._allocations if a.task_id != task_id]
        
        self.logger.debug(f"Released resources for task {task_id}")
    
    def release_all_resources(self) -> None:
        """Release all allocated resources."""
        for allocation in self._allocations:
            resource = self._resources.get(allocation.resource_id)
            if resource:
                resource.reserved = 0.0
        
        self._allocations.clear()
        self.logger.info("Released all resources")
    
    # =========================================================================
    # REPLANNING
    # =========================================================================
    
    def handle_resource_shortage(
        self,
        task: Task,
        shortage_type: ResourceType
    ) -> Dict[str, Any]:
        """
        Handle resource shortage for a task.
        
        Returns:
            Replanning strategy
        """
        shortage_amount = 0.0
        
        for resource in task.allocated_resources:
            if resource.type == shortage_type:
                shortage_amount = resource.quantity - resource.remaining
                break
        
        strategies = []
        
        # Strategy 1: Reduce resource consumption
        strategies.append({
            "strategy": "reduce_consumption",
            "description": f"Reduce {shortage_type.value} consumption by 50%",
            "impact": "May increase task duration"
        })
        
        # Strategy 2: Defer task
        strategies.append({
            "strategy": "defer_task",
            "description": "Wait for resources to become available",
            "impact": "May delay overall completion"
        })
        
        # Strategy 3: Use alternative resources
        strategies.append({
            "strategy": "alternative_resources",
            "description": "Find alternative resource sources",
            "impact": "May increase cost"
        })
        
        return {
            "shortage_type": shortage_type.value,
            "shortage_amount": shortage_amount,
            "strategies": strategies,
            "recommended": strategies[0] if strategies else None
        }
    
    # =========================================================================
    # QUERIES
    # =========================================================================
    
    def get_available_resources(self) -> Dict[str, Resource]:
        """Get all available resources."""
        return {
            rid: r for rid, r in self._resources.items()
            if r.remaining > 0
        }
    
    def get_allocated_resources(self, task_id: str) -> List[ResourceAllocation]:
        """Get all allocations for a task."""
        return [a for a in self._allocations if a.task_id == task_id]
    
    def get_resource_utilization(self) -> Dict[str, float]:
        """Get utilization percentage for each resource."""
        utilization = {}
        
        for rid, resource in self._resources.items():
            if resource.quantity > 0:
                utilization[resource.name] = (
                    resource.reserved / resource.quantity * 100
                )
        
        return utilization
    
    def find_available_slot(
        self,
        resource_id: str,
        duration: float,
        earliest_start: datetime
    ) -> Optional[datetime]:
        """
        Find the earliest available time slot for a resource.
        
        Args:
            resource_id: Resource to check
            duration: Required duration in seconds
            earliest_start: Earliest possible start time
            
        Returns:
            Start time of available slot, or None if none available
        """
        resource = self._resources.get(resource_id)
        if not resource:
            return None
        
        # Get all allocations for this resource
        allocations = [
            a for a in self._allocations
            if a.resource_id == resource_id and a.start_time
        ]
        
        # Sort by start time
        allocations.sort(key=lambda a: a.start_time or datetime.min)
        
        # Find gap
        current_time = earliest_start
        
        for allocation in allocations:
            if not allocation.start_time or not allocation.end_time:
                continue
            
            slot_duration = (allocation.start_time - current_time).total_seconds()
            
            if slot_duration >= duration:
                return current_time
            
            current_time = allocation.end_time
        
        return current_time
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get resource planner statistics."""
        return {
            "total_resources": len(self._resources),
            "total_allocations": len(self._allocations),
            "active_allocations": len([
                a for a in self._allocations
                if a.end_time is None
            ]),
            "utilization": self.get_resource_utilization(),
            "resources_by_type": {
                rt.value: len(self.get_resources_by_type(rt))
                for rt in ResourceType
            }
        }


# ============================================================================
# SINGLETON
# ============================================================================

_resource_planner_instance: Optional[ResourcePlanner] = None


def get_resource_planner() -> ResourcePlanner:
    """Get singleton instance."""
    global _resource_planner_instance
    if _resource_planner_instance is None:
        _resource_planner_instance = ResourcePlanner()
    return _resource_planner_instance
