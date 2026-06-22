from __future__ import annotations

import random
from typing import Dict, List, Optional


_INSTRUCTION_TEMPLATES = [
    "Explain the following: {topic}",
    "Summarize this text: {text}",
    "Answer this question: {question}",
    "Write a {length} explanation of {topic}",
    "Translate the following to {language}: {text}",
    "What are the key points about {topic}?",
    "Provide a detailed analysis of: {text}",
    "How would you describe {topic} to a beginner?",
    "Compare and contrast: {topic}",
    "Give three examples of {topic}",
]


class InstructionBuilder:
    """Generate instruction-response pairs from raw text."""

    def __init__(self, templates: Optional[List[str]] = None, seed: int = 42) -> None:
        self.templates = templates or _INSTRUCTION_TEMPLATES
        self.rng = random.Random(seed)

    def build_from_text(
        self, text: str, topic: Optional[str] = None
    ) -> Dict:
        template = self.rng.choice(self.templates)
        instruction = template.format(
            topic=topic or "the topic",
            text=text[:500] if len(text) > 500 else text,
            question=f"What is {topic or 'this about'}?",
            language="English",
            length="brief",
        )
        return {"instruction": instruction, "input": text[:1000], "response": ""}

    def build_qa_pairs(
        self,
        context: str,
        questions: List[str],
        answers: List[str],
    ) -> List[Dict]:
        pairs: List[Dict] = []
        for q, a in zip(questions, answers):
            if not q.strip() or not a.strip():
                continue
            pairs.append(
                {
                    "instruction": q.strip(),
                    "input": context[:1000] if context else "",
                    "response": a.strip(),
                }
            )
        return pairs

    def build_summary_pairs(
        self, documents: List[str], summaries: List[str]
    ) -> List[Dict]:
        return [
            {
                "instruction": f"Summarize the following text in 2-3 sentences.",
                "input": doc[:2000],
                "response": summary,
            }
            for doc, summary in zip(documents, summaries)
            if doc.strip() and summary.strip()
        ]

    def augment_with_variations(
        self, record: Dict, n: int = 3
    ) -> List[Dict]:
        base_instruction = record.get("instruction", "")
        variations = [record]
        rephrases = [
            f"Please {base_instruction.lower()}",
            f"Can you {base_instruction.lower()}",
            f"I need you to {base_instruction.lower()}",
        ]
        for rephrase in rephrases[:n - 1]:
            variations.append({**record, "instruction": rephrase})
        return variations
