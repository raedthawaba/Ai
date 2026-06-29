from __future__ import annotations
import asyncio
import logging
from typing import Dict, Any, List, Callable

logger = logging.getLogger(__name__)

class DynamicExecutor:
    def __init__(self):
        self.workflows: Dict[str, Any] = {}
        self.state_machines: Dict[str, Any] = {}

    def register_workflow(self, workflow_id: str, workflow_definition: Dict) -> None:
        # workflow_definition could be a graph, a series of steps, etc.
        self.workflows[workflow_id] = workflow_definition
        logger.info(f"Workflow '{workflow_id}' registered.")

    def register_state_machine(self, sm_id: str, state_machine_definition: Dict) -> None:
        # state_machine_definition could define states, transitions, actions
        self.state_machines[sm_id] = state_machine_definition
        logger.info(f"State machine '{sm_id}' registered.")

    async def execute_workflow(self, workflow_id: str, initial_context: Dict) -> Any:
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        logger.info(f"Executing workflow '{workflow_id}' with context: {initial_context}")
        # Placeholder for actual dynamic workflow execution logic
        # This would involve traversing a graph, executing tasks, handling dependencies
        await asyncio.sleep(0.1) # Simulate work
        return {"status": "workflow_completed", "result": f"Workflow {workflow_id} processed.", "final_context": initial_context}

    async def execute_state_machine(self, sm_id: str, initial_state: str, payload: Dict) -> Any:
        state_machine = self.state_machines.get(sm_id)
        if not state_machine:
            raise ValueError(f"State machine '{sm_id}' not found.")

        logger.info(f"Executing state machine '{sm_id}' from state '{initial_state}' with payload: {payload}")
        current_state = initial_state
        history = [current_state]

        # Simulate state transitions
        for _ in range(10): # Limit transitions to prevent infinite loops in simulation
            if current_state not in state_machine.get("states", {}):
                break
            
            state_def = state_machine["states"][current_state]
            transition_event = state_def.get("on_event")
            
            if transition_event and transition_event in payload.get("events", []):
                next_state = state_def.get("transition_to")
                if next_state:
                    current_state = next_state
                    history.append(current_state)
                    logger.debug(f"Transitioned to state: {current_state}")
                else:
                    break # No further transition defined
            else:
                break # No event or no matching event
            await asyncio.sleep(0.05) # Simulate state processing

        return {"status": "sm_completed", "final_state": current_state, "history": history, "final_payload": payload}
