import os
import logging
from typing import Optional, List, Dict, Any
from huggingface_hub import hf_hub_download, snapshot_download, HfApi
from datasets import load_dataset, Dataset, concatenate_datasets

logger = logging.getLogger(__name__)

class HFHubManager:
    """
    مدير التكامل مع HuggingFace لإدارة البيانات والأوزان.
    """
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("HF_TOKEN")
        self.api = HfApi(token=self.token)

    def download_model(self, repo_id: str, local_dir: str, revision: str = "main") -> str:
        """
        تحميل أوزان النموذج من HuggingFace إلى مجلد محلي.
        """
        logger.info(f"Downloading model from {repo_id} to {local_dir}...")
        os.makedirs(local_dir, exist_ok=True)
        path = snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            revision=revision,
            token=self.token
        )
        logger.info(f"Model downloaded to {path}")
        return path

    def fetch_dataset(self, repo_id: str, split: str = "train") -> Dataset:
        """
        سحب مجموعة البيانات من HuggingFace.
        """
        logger.info(f"Loading dataset {repo_id} (split: {split})...")
        dataset = load_dataset(repo_id, split=split, token=self.token)
        return dataset

    def push_to_hub(self, local_path: str, repo_id: str, commit_message: str = "Update from Hajeen Platform"):
        """
        رفع ملفات أو مجلدات إلى HuggingFace Hub.
        """
        logger.info(f"Pushing {local_path} to {repo_id}...")
        if os.path.isdir(local_path):
            self.api.upload_folder(
                folder_path=local_path,
                repo_id=repo_id,
                commit_message=commit_message
            )
        else:
            self.api.upload_file(
                path_or_fileobj=local_path,
                path_in_repo=os.path.basename(local_path),
                repo_id=repo_id,
                commit_message=commit_message
            )
        logger.info("Push successful.")

    def add_data_to_dataset(self, repo_id: str, new_data: List[Dict[str, Any]], split: str = "train"):
        """
        إضافة بيانات جديدة إلى مجموعة البيانات الحالية ورفعها.
        """
        current_ds = self.fetch_dataset(repo_id, split=split)
        new_ds = Dataset.from_list(new_data)
        
        # دمج البيانات
        updated_ds = concatenate_datasets([current_ds, new_ds])
        
        logger.info(f"Updating dataset {repo_id} with {len(new_data)} new records.")
        updated_ds.push_to_hub(repo_id, token=self.token)
        logger.info("Dataset updated on Hub.")
