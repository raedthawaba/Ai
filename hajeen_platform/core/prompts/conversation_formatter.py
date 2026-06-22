from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    role: MessageRole
    content: str
    name: Optional[str] = None

    model_config = {"extra": "allow"}


from typing import Optional  # noqa: E402


class ConversationFormatter:
    """Format conversation histories into model-specific prompt strings."""

    @staticmethod
    def to_llama3(messages: List[Message], bos: str = "<s>") -> str:
        parts = [bos]
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                parts.append(
                    f"<|start_header_id|>system<|end_header_id|>\n{msg.content}<|eot_id|>"
                )
            elif msg.role == MessageRole.USER:
                parts.append(
                    f"<|start_header_id|>user<|end_header_id|>\n{msg.content}<|eot_id|>"
                )
            elif msg.role == MessageRole.ASSISTANT:
                parts.append(
                    f"<|start_header_id|>assistant<|end_header_id|>\n{msg.content}<|eot_id|>"
                )
        parts.append("<|start_header_id|>assistant<|end_header_id|>\n")
        return "".join(parts)

    @staticmethod
    def to_mistral(messages: List[Message]) -> str:
        parts: list[str] = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                parts.append(msg.content)
            elif msg.role == MessageRole.USER:
                parts.append(f"[INST] {msg.content} [/INST]")
            elif msg.role == MessageRole.ASSISTANT:
                parts.append(f"{msg.content}</s>")
        return " ".join(parts)

    @staticmethod
    def to_chatml(messages: List[Message]) -> str:
        parts: list[str] = []
        for msg in messages:
            parts.append(f"<|im_start|>{msg.role.value}\n{msg.content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    @staticmethod
    def to_alpaca(instruction: str, input_text: str = "") -> str:
        if input_text:
            return (
                f"### Instruction:\n{instruction}\n\n"
                f"### Input:\n{input_text}\n\n### Response:"
            )
        return f"### Instruction:\n{instruction}\n\n### Response:"

    @staticmethod
    def to_openai_messages(messages: List[Message]) -> List[dict]:
        return [{"role": m.role.value, "content": m.content} for m in messages]

    @staticmethod
    def trim_history(
        messages: List[Message],
        max_messages: int = 20,
        keep_system: bool = True,
    ) -> List[Message]:
        system = [m for m in messages if m.role == MessageRole.SYSTEM]
        non_system = [m for m in messages if m.role != MessageRole.SYSTEM]
        trimmed = non_system[-(max_messages):]
        return (system + trimmed) if keep_system else trimmed
