
import os
import shutil
import json
from datetime import datetime

class CheckpointManager:
    def __init__(self, checkpoint_dir: str = "/home/ubuntu/hajeen_platform/hajeen_model/checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        if not os.path.exists(self.checkpoint_dir):
            os.makedirs(self.checkpoint_dir)

    def save_checkpoint(self, model_state, epoch: int, metrics: dict, is_best: bool = False):
        checkpoint_name = f"checkpoint-epoch-{epoch}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        path = os.path.join(self.checkpoint_dir, checkpoint_name)
        os.makedirs(path)
        
        # In a real scenario, we would save the model weights here
        # For now, we save the metadata as requested
        meta_path = os.path.join(path, "training_meta.json")
        meta = {
            "epoch": epoch,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=4)
        
        if is_best:
            best_path = os.path.join(self.checkpoint_dir, "best_model")
            if os.path.exists(best_path):
                shutil.rmtree(best_path)
            shutil.copytree(path, best_path)
        
        return path

    def list_checkpoints(self) -> list:
        return sorted(os.listdir(self.checkpoint_dir))

    def load_latest_metadata(self) -> dict:
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            return {}
        
        latest = checkpoints[-1]
        meta_path = os.path.join(self.checkpoint_dir, latest, "training_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                return json.load(f)
        return {}
