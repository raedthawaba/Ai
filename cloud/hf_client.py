"""
hf_client.py — HuggingFace Hub Client
الاتصال بـ HuggingFace Hub وإدارة المصادقة ورفع/تحميل الملفات
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class HFClient:
    """
    عميل HuggingFace Hub المركزي.
    يدير المصادقة، ورفع/تحميل الملفات، وإدارة Tokens.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        dataset_repo: Optional[str] = None,
        model_repo: Optional[str] = None,
    ):
        self.token = token or os.getenv("HF_TOKEN", "")
        self.dataset_repo = dataset_repo or os.getenv(
            "HF_DATASET_REPO", "Raedthawaba/hajeen-datasets"
        )
        self.model_repo = model_repo or os.getenv(
            "HF_MODEL_REPO", "Raedthawaba/hajeen-model"
        )
        self._api = None
        self._authenticated = False

    def _get_api(self):
        """الحصول على HuggingFace API مع lazy initialization."""
        if self._api is None:
            try:
                from huggingface_hub import HfApi
                self._api = HfApi(token=self.token)
                self._authenticated = True
                logger.info("✅ HuggingFace API initialized successfully")
            except ImportError:
                raise ImportError(
                    "huggingface_hub غير مثبت. شغّل: pip install huggingface_hub"
                )
        return self._api

    def authenticate(self) -> bool:
        """
        التحقق من صحة الـ Token وإتمام المصادقة.
        Returns: True إذا نجحت المصادقة.
        """
        try:
            from huggingface_hub import login, whoami
            if not self.token:
                logger.warning("⚠️  HF_TOKEN غير موجود في البيئة")
                return False
            login(token=self.token, add_to_git_credential=False)
            user_info = whoami(token=self.token)
            logger.info(f"✅ مصادق كـ: {user_info.get('name', 'unknown')}")
            self._authenticated = True
            return True
        except Exception as e:
            logger.error(f"❌ فشل المصادقة مع HuggingFace: {e}")
            return False

    def upload_file(
        self,
        local_path: str,
        repo_path: str,
        repo_id: Optional[str] = None,
        repo_type: str = "model",
        commit_message: str = "Upload from Hajeen Platform",
    ) -> str:
        """
        رفع ملف واحد إلى HuggingFace Repository.

        Args:
            local_path: مسار الملف المحلي
            repo_path:  المسار داخل الـ repository
            repo_id:    معرّف الـ repository (افتراضي: model_repo)
            repo_type:  نوع الـ repo ('model' أو 'dataset')
            commit_message: رسالة الـ commit

        Returns:
            رابط الملف المرفوع
        """
        api = self._get_api()
        target_repo = repo_id or (
            self.dataset_repo if repo_type == "dataset" else self.model_repo
        )

        logger.info(f"⬆️  رفع {local_path} → {target_repo}/{repo_path}")
        try:
            url = api.upload_file(
                path_or_fileobj=local_path,
                path_in_repo=repo_path,
                repo_id=target_repo,
                repo_type=repo_type,
                commit_message=commit_message,
            )
            logger.info(f"✅ تم الرفع بنجاح: {url}")
            return url
        except Exception as e:
            logger.error(f"❌ فشل رفع الملف {local_path}: {e}")
            raise

    def upload_folder(
        self,
        local_folder: str,
        repo_folder: str = "",
        repo_id: Optional[str] = None,
        repo_type: str = "model",
        ignore_patterns: Optional[List[str]] = None,
        commit_message: str = "Upload folder from Hajeen Platform",
    ) -> str:
        """
        رفع مجلد كامل إلى HuggingFace Repository.
        """
        api = self._get_api()
        target_repo = repo_id or (
            self.dataset_repo if repo_type == "dataset" else self.model_repo
        )
        ignore_patterns = ignore_patterns or ["*.pyc", "__pycache__", ".git"]

        logger.info(f"⬆️  رفع مجلد {local_folder} → {target_repo}/{repo_folder}")
        try:
            url = api.upload_folder(
                folder_path=local_folder,
                path_in_repo=repo_folder,
                repo_id=target_repo,
                repo_type=repo_type,
                ignore_patterns=ignore_patterns,
                commit_message=commit_message,
            )
            logger.info(f"✅ تم رفع المجلد: {url}")
            return url
        except Exception as e:
            logger.error(f"❌ فشل رفع المجلد {local_folder}: {e}")
            raise

    def download_file(
        self,
        repo_path: str,
        local_path: str,
        repo_id: Optional[str] = None,
        repo_type: str = "model",
    ) -> str:
        """
        تحميل ملف من HuggingFace Repository.
        """
        from huggingface_hub import hf_hub_download
        target_repo = repo_id or (
            self.dataset_repo if repo_type == "dataset" else self.model_repo
        )

        logger.info(f"⬇️  تحميل {target_repo}/{repo_path}")
        try:
            downloaded = hf_hub_download(
                repo_id=target_repo,
                filename=repo_path,
                repo_type=repo_type,
                token=self.token,
                local_dir=str(Path(local_path).parent),
            )
            logger.info(f"✅ تم التحميل: {downloaded}")
            return downloaded
        except Exception as e:
            logger.error(f"❌ فشل تحميل {repo_path}: {e}")
            raise

    def create_repo_if_not_exists(
        self, repo_id: str, repo_type: str = "model", private: bool = True
    ) -> None:
        """إنشاء الـ repository إذا لم يكن موجوداً."""
        api = self._get_api()
        try:
            api.create_repo(
                repo_id=repo_id,
                repo_type=repo_type,
                private=private,
                exist_ok=True,
            )
            logger.info(f"✅ Repository جاهز: {repo_id}")
        except Exception as e:
            logger.warning(f"⚠️  create_repo: {e}")

    def list_repo_files(
        self, repo_id: Optional[str] = None, repo_type: str = "model"
    ) -> List[str]:
        """عرض قائمة ملفات الـ repository."""
        api = self._get_api()
        target_repo = repo_id or self.model_repo
        try:
            files = api.list_repo_files(repo_id=target_repo, repo_type=repo_type)
            return list(files)
        except Exception as e:
            logger.error(f"❌ فشل عرض الملفات: {e}")
            return []

    def get_repo_info(self, repo_id: Optional[str] = None, repo_type: str = "model") -> Dict[str, Any]:
        """الحصول على معلومات الـ repository."""
        api = self._get_api()
        target_repo = repo_id or self.model_repo
        try:
            info = api.repo_info(repo_id=target_repo, repo_type=repo_type)
            return {
                "id": info.id,
                "private": info.private,
                "last_modified": str(info.last_modified),
            }
        except Exception as e:
            logger.error(f"❌ فشل جلب معلومات الـ repo: {e}")
            return {}
