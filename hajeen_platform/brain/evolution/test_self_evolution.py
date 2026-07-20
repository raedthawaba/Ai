import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from hajeen_platform.brain.evolution.self_evolution import (
    SelfEvolution,
    get_self_evolution_engine,
)
from hajeen_platform.brain.reflection.self_reflection import ReflectionReport
from hajeen_platform.core.llm.base import LLMResponse


async def main():
    # Mock dependencies
    mock_policy_engine = AsyncMock()
    mock_self_reflection = AsyncMock()
    mock_decision_engine = AsyncMock()

    # Mock LLM response for proposal generation
    mock_decision_engine.decide.side_effect = [
        # First call for analyze_and_propose
        MagicMock(primary_model="mock_model", llm_response=LLMResponse(
            content=json.dumps({
                "type": "policy_addition",
                "description": "Add a policy to prefer local models for simple tasks.",
                "proposed_change": {
                    "name": "PreferLocalForSimpleTasks",
                    "rules": {"complexity": "LOW", "is_local_preferred": True},
                    "action": {"type": "set_preference", "preference": "local"}
                }
            }),
            model="mock_model",
            provider="mock_provider"
        )),
        # Second call for evaluate_and_implement (approved)
        MagicMock(primary_model="mock_model", llm_response=LLMResponse(
            content=json.dumps({
                "status": "approved",
                "reason": "The proposed policy enhances efficiency for simple tasks without significant risks.",
                "risks": []
            }),
            model="mock_model",
            provider="mock_provider"
        )),
        # Third call for evaluate_and_implement (rejected)
        MagicMock(primary_model="mock_model", llm_response=LLMResponse(
            content=json.dumps({
                "status": "rejected",
                "reason": "The proposed change introduces too much overhead for minimal gain.",
                "risks": ["performance degradation"]
            }),
            model="mock_model",
            provider="mock_provider"
        )),
    ]

    # Create an instance of SelfEvolution with mocked dependencies
    evolution_engine = SelfEvolution()
    evolution_engine._policy_engine = mock_policy_engine
    evolution_engine._self_reflection = mock_self_reflection
    evolution_engine._decision_engine = mock_decision_engine

    # Simulate a reflection report
    report = ReflectionReport(
        report_id="report_123",
        task_id="task_abc",
        goal_id="goal_xyz",
        was_plan_good=False,
        better_path_exists=True,
        correct_model_used=False,
        cost_can_be_reduced=True,
        quality_can_increase=True,
        plan_score=0.5,
        efficiency_score=0.6,
        quality_score=0.7,
        overall_score=0.6,
        lessons_learned=["Plan was inefficient", "Model choice was suboptimal"],
        recommendations=["Consider local models", "Refine planning algorithm"],
        actual_latency_ms=5000,
        actual_tokens_used=1000,
        estimated_tokens=500,
        model_used="openai/gpt-4o",
        better_model_suggestion="ollama/llama3",
        cost_saving_suggestion="Reduce max_tokens",
        metadata={}
    )

    print("--- Test Case 1: Analyze and Propose ---")
    proposal = await evolution_engine.analyze_and_propose(report)
    if proposal:
        print(f"Generated Proposal: {proposal}")
        assert proposal.type == "policy_addition"
        assert proposal.status == "pending"
    else:
        print("No proposal generated.")

    print("\n--- Test Case 2: Evaluate and Implement (Approved) ---")
    if proposal:
        implemented = await evolution_engine.evaluate_and_implement(proposal)
        print(f"Proposal Implemented: {implemented}")
        print(f"Final Proposal Status: {proposal.status}")
        assert implemented is True
        assert proposal.status == "implemented"
        mock_policy_engine.add_policy.assert_called_once()
    else:
        print("Cannot evaluate, no proposal generated.")

    print("\n--- Test Case 3: Analyze and Propose (another report) ---")
    report2 = ReflectionReport(
        report_id="report_456",
        task_id="task_def",
        goal_id="goal_uvw",
        was_plan_good=True,
        better_path_exists=False,
        correct_model_used=True,
        cost_can_be_reduced=False,
        quality_can_increase=False,
        plan_score=0.9,
        efficiency_score=0.9,
        quality_score=0.9,
        overall_score=0.9,
        lessons_learned=["Good performance"],
        recommendations=["Maintain current strategy"],
        actual_latency_ms=1000,
        actual_tokens_used=200,
        estimated_tokens=200,
        model_used="ollama/llama3",
        better_model_suggestion=None,
        cost_saving_suggestion=None,
        metadata={}
    )

    proposal2 = await evolution_engine.analyze_and_propose(report2)
    if proposal2:
        print(f"Generated Proposal 2: {proposal2}")
        # Simulate a rejected proposal
        proposal2.proposed_change = {"type": "model_change", "details": "unnecessary change"}
        proposal2.description = "Unnecessary model change"
        implemented2 = await evolution_engine.evaluate_and_implement(proposal2)
        print(f"Proposal 2 Implemented: {implemented2}")
        print(f"Final Proposal 2 Status: {proposal2.status}")
        assert implemented2 is False
        assert proposal2.status == "rejected"
    else:
        print("No second proposal generated.")

    print("\n--- Test Case 4: Get pending proposals ---")
    pending = evolution_engine.get_pending_proposals()
    print(f"Pending Proposals: {pending}")
    assert len(pending) == 0 # All proposals should be evaluated by now

    print("\n--- Test Case 5: Test get_self_evolution_engine singleton ---")
    engine1 = await get_self_evolution_engine()
    engine2 = await get_self_evolution_engine()
    assert engine1 is engine2
    print("Singleton test passed.")

if __name__ == "__main__":
    asyncio.run(main())
