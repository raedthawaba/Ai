from __future__ import annotations

import time
from typing import Dict, List, Optional


class ConversationBuilder:
    """Build multi-turn conversation datasets."""

    @staticmethod
    def from_qa_pairs(qa_pairs: List[Dict]) -> List[Dict]:
        """Convert Q/A pairs to conversation format."""
        conversations: List[Dict] = []
        for pair in qa_pairs:
            q = pair.get("question", pair.get("instruction", ""))
            a = pair.get("answer", pair.get("response", ""))
            if not q or not a:
                continue
            conversations.append(
                {
                    "messages": [
                        {"role": "user", "content": q},
                        {"role": "assistant", "content": a},
                    ],
                    "created_at": time.time(),
                }
            )
        return conversations

    @staticmethod
    def build_multi_turn(
        turns: List[Dict],
        system_prompt: Optional[str] = None,
    ) -> Dict:
        messages: List[Dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for turn in turns:
            role = turn.get("role", "user")
            content = turn.get("content", turn.get("text", ""))
            if content.strip():
                messages.append({"role": role, "content": content.strip()})
        return {
            "messages": messages,
            "turn_count": len([m for m in messages if m["role"] != "system"]),
            "created_at": time.time(),
        }

    @staticmethod
    def split_into_windows(
        messages: List[Dict],
        window_size: int = 6,
        stride: int = 2,
    ) -> List[List[Dict]]:
        windows: List[List[Dict]] = []
        for i in range(0, max(1, len(messages) - window_size + 1), stride):
            window = messages[i: i + window_size]
            if len(window) >= 2:
                windows.append(window)
        return windows

    @staticmethod
    def to_sharegpt_format(conversations: List[Dict]) -> List[Dict]:
        output: List[Dict] = []
        for convo in conversations:
            messages = convo.get("messages", [])
            formatted: List[Dict] = []
            for msg in messages:
                role = msg.get("role", "user")
                from_map = {"user": "human", "assistant": "gpt", "system": "system"}
                formatted.append(
                    {"from": from_map.get(role, "human"), "value": msg.get("content", "")}
                )
            if formatted:
                output.append({"conversations": formatted})
        return output
