import pytest
import asyncio
from hajeen_platform.services.agents.multi_agent.shared_memory import SharedMemoryBus
from hajeen_platform.services.agents.multi_agent.messenger import AgentMessenger
from hajeen_platform.services.agents.multi_agent.collaborative_layer import CollaborativeIntelligence
from hajeen_platform.services.agents.base_agent import BaseAgent, AgentContext, AgentResult

class MockAgent(BaseAgent):
    async def _execute(self, context: AgentContext) -> AgentResult:
        return AgentResult(success=True, output=f"Result from {self.name}", context=context)

@pytest.mark.asyncio
async def test_shared_memory_bus():
    bus = SharedMemoryBus()
    await bus.post_message("agent1", "hello")
    messages = await bus.get_messages()
    assert len(messages) == 1
    assert messages[0].content == "hello"
    
    await bus.set_state("key1", "value1")
    val = await bus.get_state("key1")
    assert val == "value1"

@pytest.mark.asyncio
async def test_agent_messenger():
    messenger = AgentMessenger()
    received = []
    
    async def callback(msg):
        received.append(msg)
        
    await messenger.subscribe("agent2", callback)
    await messenger.send_direct("agent1", "agent2", "private message")
    
    assert len(received) == 1
    assert received[0]["content"] == "private message"
    assert received[0]["from"] == "agent1"

@pytest.mark.asyncio
async def test_collaborative_layer():
    agent1 = MockAgent(name="agent1")
    agent2 = MockAgent(name="agent2")
    
    layer = CollaborativeIntelligence(agents=[agent1, agent2])
    context = AgentContext(goal="test collaborative goal")
    
    result = await layer.collaborative_solve("test goal", context)
    
    assert result.success is True
    assert "Collaborative Output" in result.output
    assert "agent1" in result.output
    assert "agent2" in result.output
