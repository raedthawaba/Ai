from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Save, load, and list training checkpoints."""

    def __init__(self, checkpoint_dir: str = "storage_data/checkpoints") -> None:
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        model: Any,
        tokenizer: Any,
        step: int,
        metrics: Optional[Dict] = None,
        tag: Optional[str] = None,
    ) -> str:
        name = tag or f"checkpoint-step-{step}"
        dest = self.checkpoint_dir / name
        dest.mkdir(exist_ok=True)

        try:
            model.save_pretrained(str(dest))
            if tokenizer is not None:
                tokenizer.save_pretrained(str(dest))
        except AttributeError as exc:
            logger.warning("Cannot call save_pretrained: %s", exc)

        meta = {
            "step": step,
            "saved_at": time.time(),
            "metrics": metrics or {},
            "tag": tag,
        }
        (dest / "checkpoint_meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        logger.info("Checkpoint saved: %s", dest)
        return str(dest)

    def load_latest(self) -> Optional[Path]:
        checkpoints = self._list_checkpoints()
        if not checkpoints:
            return None
        return max(checkpoints, key=lambda p: self._step_from_name(p.name))

    def load(self, path: str) -> Path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Checkpoint not found: {path}")
        return p

    def list_checkpoints(self) -> List[Dict]:
        result = []
        for p in self.checkpoint_dir.iterdir():
            if p.is_dir():
                meta_file = p / "checkpoint_meta.json"
                meta = {}
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                result.append({"name": p.name, "path": str(p), **meta})
        result.sort(key=lambda x: x.get("saved_at", 0), reverse=True)
        return result

    def delete(self, name: str) -> bool:
        p = self.checkpoint_dir / name
        if p.exists():
            shutil.rmtree(p)
            logger.info("Checkpoint deleted: %s", name)
            return True
        return False

    def _list_checkpoints(self) -> List[Path]:
        return [p for p in self.checkpoint_dir.iterdir() if p.is_dir()]

    @staticmethod
    def _step_from_name(name: str) -> int:
        parts = name.split("-")
        for part in reversed(parts):
            if part.isdigit():
                return int(part)
        return 0
