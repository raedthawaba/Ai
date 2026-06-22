"""
cloud_sync.py — Cloud Synchronization Manager
مزامنة المشروع مع HuggingFace: رفع النتائج، الـ logs، التقارير تلقائياً
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv

from .hf_client import HFClient
from .model_manager import ModelManager

load_dotenv()
logger = logging.getLogger(__name__)


class CloudSync:
    """
    مدير المزامنة السحابية.
    يرفع logs، تقارير التدريب، والنتائج تلقائياً أثناء وبعد التدريب.
    """

    def __init__(
        self,
        hf_client: Optional[HFClient] = None,
        sync_interval: int = 300,
        auto_sync: bool = True,
    ):
        self.client = hf_client or HFClient()
        self.model_manager = ModelManager(hf_client=self.client)
        self.sync_interval = sync_interval
        self.auto_sync = auto_sync
        self._sync_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._sync_queue: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        self.log_dir = Path(os.getenv("TRAINING_LOG_DIR", "./training_logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"CloudSync جاهز — interval: {sync_interval}s, auto: {auto_sync}"
        )

    def start_auto_sync(self) -> None:
        """بدء المزامنة التلقائية في خيط منفصل."""
        if self._sync_thread and self._sync_thread.is_alive():
            logger.warning("المزامنة التلقائية تعمل بالفعل")
            return

        self._stop_event.clear()
        self._sync_thread = threading.Thread(
            target=self._sync_loop, daemon=True, name="HFCloudSync"
        )
        self._sync_thread.start()
        logger.info(f"✅ بدأت المزامنة التلقائية كل {self.sync_interval}s")

    def stop_auto_sync(self) -> None:
        """إيقاف المزامنة التلقائية."""
        self._stop_event.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=10)
        logger.info("⏹  توقفت المزامنة التلقائية")

    def _sync_loop(self) -> None:
        """حلقة المزامنة الداخلية."""
        while not self._stop_event.is_set():
            try:
                self._process_queue()
            except Exception as e:
                logger.error(f"❌ خطأ في المزامنة: {e}")
            self._stop_event.wait(self.sync_interval)

    def _process_queue(self) -> None:
        """معالجة قائمة انتظار الرفع."""
        with self._lock:
            queue = self._sync_queue.copy()
            self._sync_queue.clear()

        for item in queue:
            try:
                if item["type"] == "file":
                    self.client.upload_file(
                        local_path=item["local_path"],
                        repo_path=item["repo_path"],
                        repo_type=item.get("repo_type", "model"),
                        commit_message=item.get("commit_message", "[Hajeen] Auto-sync"),
                    )
                elif item["type"] == "log":
                    self._upload_log_content(item["content"], item["log_name"])
            except Exception as e:
                logger.error(f"❌ فشل رفع {item}: {e}")

    def queue_file(
        self,
        local_path: str,
        repo_path: str,
        repo_type: str = "model",
        commit_message: Optional[str] = None,
    ) -> None:
        """إضافة ملف لقائمة الرفع."""
        with self._lock:
            self._sync_queue.append({
                "type": "file",
                "local_path": local_path,
                "repo_path": repo_path,
                "repo_type": repo_type,
                "commit_message": commit_message or f"[Hajeen] Sync {Path(local_path).name}",
            })

    def upload_training_log(
        self,
        log_data: Dict[str, Any],
        step: int,
        immediate: bool = False,
    ) -> Optional[str]:
        """
        رفع log التدريب.

        Args:
            log_data: بيانات الـ log (loss, lr, perplexity...)
            step: رقم الـ step الحالي
            immediate: رفع فوري أم إضافة للقائمة
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_name = f"training_log_step{step}_{ts}.json"
        content = json.dumps({
            "step": step,
            "timestamp": datetime.now().isoformat(),
            **log_data,
        }, indent=2, ensure_ascii=False)

        local_path = self.log_dir / log_name
        local_path.write_text(content, encoding="utf-8")

        if immediate:
            try:
                return self.client.upload_file(
                    local_path=str(local_path),
                    repo_path=f"logs/training/{log_name}",
                    repo_type="model",
                    commit_message=f"[Hajeen] Training log step={step}",
                )
            except Exception as e:
                logger.error(f"❌ فشل رفع log step={step}: {e}")
                return None
        else:
            self.queue_file(
                local_path=str(local_path),
                repo_path=f"logs/training/{log_name}",
                commit_message=f"[Hajeen] Training log step={step}",
            )
            return None

    def _upload_log_content(self, content: str, log_name: str) -> None:
        """رفع محتوى log مباشرةً."""
        tmp = Path(f"/tmp/{log_name}")
        tmp.write_text(content, encoding="utf-8")
        try:
            self.client.upload_file(
                local_path=str(tmp),
                repo_path=f"logs/{log_name}",
                repo_type="model",
                commit_message=f"[Hajeen] Log: {log_name}",
            )
        finally:
            tmp.unlink(missing_ok=True)

    def upload_evaluation_results(
        self,
        results: Dict[str, Any],
        step: int,
        benchmark_name: str = "hajeen_eval",
    ) -> Optional[str]:
        """رفع نتائج التقييم."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{benchmark_name}_step{step}_{ts}.json"
        tmp = Path(f"/tmp/{fname}")
        payload = {
            "step": step,
            "benchmark": benchmark_name,
            "timestamp": datetime.now().isoformat(),
            "results": results,
        }
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            url = self.client.upload_file(
                local_path=str(tmp),
                repo_path=f"logs/evaluation/{fname}",
                repo_type="model",
                commit_message=f"[Hajeen] Eval results — step={step}",
            )
            logger.info(f"✅ تم رفع نتائج التقييم: {url}")
            return url
        except Exception as e:
            logger.error(f"❌ فشل رفع نتائج التقييم: {e}")
            return None
        finally:
            tmp.unlink(missing_ok=True)

    def upload_training_report(
        self,
        report: Dict[str, Any],
        report_name: str = "training_report",
    ) -> Optional[str]:
        """رفع تقرير التدريب النهائي."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{report_name}_{ts}.json"
        tmp = Path(f"/tmp/{fname}")
        report["generated_at"] = datetime.now().isoformat()
        report["platform"] = "Hajeen Platform"
        tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            url = self.client.upload_file(
                local_path=str(tmp),
                repo_path=f"reports/{fname}",
                repo_type="model",
                commit_message=f"[Hajeen] Training report — {ts}",
            )
            logger.info(f"✅ تم رفع تقرير التدريب: {url}")
            return url
        except Exception as e:
            logger.error(f"❌ فشل رفع التقرير: {e}")
            return None
        finally:
            tmp.unlink(missing_ok=True)

    def sync_checkpoint_with_report(
        self,
        checkpoint_path: str,
        step: int,
        metrics: Dict[str, float],
        epoch: Optional[int] = None,
    ) -> Dict[str, Optional[str]]:
        """
        رفع checkpoint + metrics + report في عملية واحدة.
        """
        results: Dict[str, Optional[str]] = {}

        logger.info(f"🔄 مزامنة كاملة للـ checkpoint step={step}")

        results["checkpoint"] = self.model_manager.upload_checkpoint(
            checkpoint_path=checkpoint_path,
            step=step,
            epoch=epoch,
            metrics=metrics,
        )

        results["log"] = self.upload_training_log(
            log_data=metrics,
            step=step,
            immediate=True,
        )

        return results
