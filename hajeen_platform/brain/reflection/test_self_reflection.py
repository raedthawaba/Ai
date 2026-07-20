
import asyncio

from hajeen_platform.brain.reflection.self_reflection import get_self_reflection


async def main():
    reflector = await get_self_reflection()

    print("\n--- Test Case 1: Good Performance ---")
    report1 = await reflector.reflect(
        task_id="task_001",
        goal_id="goal_A",
        model_used="openai/gpt-3.5-turbo",
        actual_latency_ms=1500,
        actual_tokens=100,
        estimated_tokens=120,
        response_quality=0.9,
        plan_steps=5,
        actual_steps=5,
        context={
            "user_query": "Summarize this document.",
            "document_length": "short"
        }
    )
    print(f"Report 1: {report1.to_dict()}")

    print("\n--- Test Case 2: Poor Quality ---")
    report2 = await reflector.reflect(
        task_id="task_002",
        goal_id="goal_B",
        model_used="ollama/llama3",
        actual_latency_ms=2500,
        actual_tokens=300,
        estimated_tokens=250,
        response_quality=0.5,
        plan_steps=3,
        actual_steps=4,
        context={
            "user_query": "Generate a complex code snippet.",
            "complexity": "high"
        }
    )
    print(f"Report 2: {report2.to_dict()}")

    print("\n--- Test Case 3: High Latency & Cost ---")
    report3 = await reflector.reflect(
        task_id="task_003",
        goal_id="goal_C",
        model_used="openai/gpt-4o",
        actual_latency_ms=8000,
        actual_tokens=500,
        estimated_tokens=300,
        response_quality=0.8,
        plan_steps=7,
        actual_steps=7,
        context={
            "user_query": "Research and write a detailed report.",
            "detail_level": "high"
        }
    )
    print(f"Report 3: {report3.to_dict()}")

    print("\n--- Aggregated Lessons and Average Scores ---")
    print(f"Aggregated Lessons: {reflector.get_aggregated_lessons()}")
    print(f"Average Scores: {reflector.get_average_scores()}")

if __name__ == "__main__":
    asyncio.run(main())
