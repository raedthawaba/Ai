"""واجهة سطر الأوامر — Data Engine CLI.

الأوامر المتاحة:
  create-channel  — إنشاء قناة جديدة وحفظها في SQLite
  list-channels   — عرض جميع القنوات
  trigger CHANNEL_ID — تشغيل pipeline حقيقي كامل
  delete-channel  — حذف قناة
  start-api       — تشغيل FastAPI
  start-worker    — تشغيل Celery worker
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

# ── إعداد sys.path ─────────────────────────────────────────────────────────
_here = Path(__file__).resolve().parent.parent  # hajeen_platform/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

# ── إعداد Logging ──────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/cli.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("data_engine.cli")

app = typer.Typer(
    help="Hajeen AI Platform — Data Engine CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


# ──────────────────────────────────────────────────────────────────────────
# create-channel
# ──────────────────────────────────────────────────────────────────────────

@app.command("create-channel")
def create_channel(
    name: str = typer.Option(..., "--name", "-n", help="اسم القناة"),
    channel_type: str = typer.Option(
        "rss", "--type", "-t",
        help="نوع القناة: rss | demo | api | placeholder",
    ),
    url: str = typer.Option(
        "https://techcrunch.com/feed/",
        "--url", "-u",
        help="URL المصدر",
    ),
    schedule: str = typer.Option(
        "0 */6 * * *", "--schedule", "-s",
        help="تعبير cron للجدولة",
    ),
    description: Optional[str] = typer.Option(
        None, "--description", help="وصف اختياري"
    ),
) -> None:
    """إنشاء قناة جديدة وحفظها في SQLite."""

    async def _create() -> None:
        from data_engine.channels.builder import ChannelBuilder
        from data_engine.channels.registry import ChannelRegistry
        from shared.schemas.channel import (
            ChannelConfig, ChannelStatus, ScheduleConfig, SourceConfig
        )
        from shared.utils.id_generator import generate_channel_id
        from shared.utils.datetime_utils import utc_now

        channel_id = generate_channel_id()
        now = utc_now()

        try:
            source = SourceConfig(url=url, type=channel_type)  # type: ignore[arg-type]
        except Exception as exc:
            console.print(f"[red]خطأ في تكوين المصدر: {exc}[/red]")
            raise typer.Exit(1)

        config = ChannelConfig(
            id=channel_id,
            name=name,
            description=description or "",
            source=source,
            schedule=ScheduleConfig(cron=schedule),
            status=ChannelStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

        channel = await ChannelBuilder.create_from_config(config)

        # إلغاء تسجيل إذا كانت موجودة (لتجنب التكرار عند إعادة التشغيل)
        if ChannelRegistry.get(channel_id):
            ChannelRegistry.unregister(channel_id)

        ChannelRegistry.register(channel)

        console.print(
            f"\n[green]✓ تم إنشاء القناة بنجاح![/green]\n"
            f"  المعرّف  : [cyan]{channel_id}[/cyan]\n"
            f"  الاسم    : [bold]{name}[/bold]\n"
            f"  النوع    : [magenta]{channel_type}[/magenta]\n"
            f"  URL      : {url}\n"
            f"  الجدولة  : {schedule}\n"
        )
        console.print(
            f"[dim]لتشغيل القناة:[/dim] "
            f"[yellow]python -m data_engine.cli trigger {channel_id}[/yellow]"
        )

    asyncio.run(_create())


# ──────────────────────────────────────────────────────────────────────────
# list-channels
# ──────────────────────────────────────────────────────────────────────────

@app.command("list-channels")
def list_channels() -> None:
    """عرض جميع القنوات المحفوظة في SQLite."""
    from data_engine.channels.registry import ChannelRegistry

    configs = ChannelRegistry.list_from_db()
    if not configs:
        console.print("[yellow]لا توجد قنوات محفوظة. أنشئ قناة أولاً.[/yellow]")
        return

    table = Table(title="القنوات المسجّلة")
    table.add_column("المعرّف", style="cyan", no_wrap=True)
    table.add_column("الاسم", style="bold green")
    table.add_column("النوع", style="magenta")
    table.add_column("URL")
    table.add_column("الحالة", style="yellow")
    table.add_column("الجدولة", style="blue")

    for cfg in configs:
        schedule = cfg.schedule.cron if cfg.schedule else "—"
        table.add_row(
            cfg.id,
            cfg.name,
            cfg.source.type,
            str(cfg.source.url)[:50],
            cfg.status.value,
            schedule,
        )

    console.print(table)


# ──────────────────────────────────────────────────────────────────────────
# trigger CHANNEL_ID — pipeline كامل حقيقي
# ──────────────────────────────────────────────────────────────────────────

@app.command("trigger")
def trigger_channel(
    channel_id: str = typer.Argument(..., help="معرّف القناة"),
    save: bool = typer.Option(True, "--save/--no-save", help="تخزين النتائج"),
) -> None:
    """تشغيل pipeline كامل لقناة: Fetch → Clean → Filter → Enrich → Store."""

    async def _trigger() -> None:
        import time
        from data_engine.channels.registry import ChannelRegistry
        from data_engine.channels.builder import ChannelBuilder
        from data_engine.pipelines.pipeline_orchestrator import PipelineOrchestrator
        from data_engine.storage.storage_manager import StorageManager
        from shared.schemas.channel import ChannelStatus

        # استعادة القناة من SQLite إذا لم تكن في الذاكرة
        channel = ChannelRegistry.get(channel_id)
        if not channel:
            console.print(f"[yellow]جارٍ استعادة القناة {channel_id} من SQLite...[/yellow]")
            await ChannelRegistry.restore_from_db()
            channel = ChannelRegistry.get(channel_id)

        if not channel:
            console.print(f"[red]القناة '{channel_id}' غير موجودة.[/red]")
            console.print("[dim]استخدم list-channels لعرض القنوات المتاحة.[/dim]")
            raise typer.Exit(1)

        console.print(
            f"\n[bold cyan]═══ تشغيل Pipeline ═══[/bold cyan]\n"
            f"  القناة  : [bold]{channel.config.name}[/bold]\n"
            f"  المعرّف : {channel_id}\n"
            f"  النوع   : {channel.config.source.type}\n"
            f"  URL     : {channel.config.source.url}\n"
        )

        # === المرحلة 1: Fetch ===
        console.print("[yellow]▶ 1/5 Fetch — جلب البيانات...[/yellow]")
        t0 = time.time()
        fetch_result = await channel.fetch()
        articles = fetch_result.articles
        fetch_ms = (time.time() - t0) * 1000
        console.print(
            f"   [green]✓[/green] تم جلب [bold]{len(articles)}[/bold] مقال "
            f"[dim]({fetch_ms:.0f}ms)[/dim]"
        )

        if not articles:
            console.print("[yellow]لا توجد مقالات للمعالجة.[/yellow]")
            return

        # إعداد Storage Manager
        storage = None
        if save:
            try:
                storage = StorageManager()
                await storage.connect()
                console.print(
                    f"   [dim]التخزين: {storage.base_data_dir}[/dim]"
                )
            except Exception as exc:
                console.print(f"[yellow]تحذير: لم يتم الاتصال بالتخزين — {exc}[/yellow]")

        # === المراحل 2-5: Pipeline ===
        console.print("[yellow]▶ 2-5/5 Pipeline — المعالجة الكاملة...[/yellow]")
        orchestrator = PipelineOrchestrator(
            name=f"cli_trigger:{channel.config.name}",
            source_id=channel.config.id,
            storage_manager=storage,
            allowed_languages=["ar", "en"],
        )

        t1 = time.time()
        context = await orchestrator.run(articles=articles)
        pipeline_ms = (time.time() - t1) * 1000

        stored_count = context.get("stored_count") or 0

        console.print(
            f"\n[bold green]══════════════════════════════════[/bold green]\n"
            f"[bold green]   ✓ Pipeline مكتمل بنجاح![/bold green]\n"
            f"[bold green]══════════════════════════════════[/bold green]\n"
        )

        # جدول الإحصائيات
        stats = Table(show_header=True, header_style="bold")
        stats.add_column("المرحلة", style="cyan")
        stats.add_column("العدد", justify="right", style="green")
        stats.add_column("الوقت", justify="right", style="dim")

        for trace in context.stage_traces:
            stats.add_row(
                trace.stage_name,
                f"{trace.output_count}/{trace.input_count}",
                f"{trace.duration_ms:.0f}ms",
            )

        console.print(stats)

        console.print(
            f"\n  المدخلات  : [bold]{len(articles)}[/bold] مقال\n"
            f"  المخرجات  : [bold]{context.article_count}[/bold] مقال\n"
            f"  المحفوظة  : [bold]{stored_count}[/bold] مقال\n"
            f"  الوقت     : [bold]{pipeline_ms:.0f}ms[/bold]\n"
            f"  الأخطاء   : {len(context.errors)}\n"
        )

        if context.errors:
            console.print("[yellow]تحذيرات:[/yellow]")
            for err in context.errors[:5]:
                console.print(f"  • {err.stage}: {err.message}")

        if storage:
            console.print(
                f"\n[dim]البيانات محفوظة في:[/dim]\n"
                f"  storage_data/raw/     — البيانات الخام\n"
                f"  storage_data/bronze/  — بعد التنظيف\n"
                f"  storage_data/silver/  — بعد الإثراء\n"
            )

        ChannelRegistry.update_status(channel_id, ChannelStatus.ACTIVE)

    asyncio.run(_trigger())


# ──────────────────────────────────────────────────────────────────────────
# delete-channel
# ──────────────────────────────────────────────────────────────────────────

@app.command("delete-channel")
def delete_channel(
    channel_id: str = typer.Argument(..., help="معرّف القناة المراد حذفها"),
) -> None:
    """حذف قناة من SQLite والذاكرة."""
    from data_engine.channels.registry import ChannelRegistry

    try:
        ChannelRegistry.unregister(channel_id)
        console.print(f"[green]✓ تم حذف القناة {channel_id}[/green]")
    except Exception as exc:
        console.print(f"[red]خطأ: {exc}[/red]")
        raise typer.Exit(1)


# ──────────────────────────────────────────────────────────────────────────
# start-api
# ──────────────────────────────────────────────────────────────────────────

@app.command("start-api")
def start_api(
    host: str = typer.Option("0.0.0.0", "--host", help="Host"),
    port: int = typer.Option(8000, "--port", "-p", help="Port"),
    reload: bool = typer.Option(False, "--reload", help="Hot reload"),
) -> None:
    """تشغيل FastAPI server."""
    import uvicorn

    console.print(
        f"[green]تشغيل API على http://{host}:{port}[/green]\n"
        f"  Docs: http://{host}:{port}/docs\n"
    )
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# ──────────────────────────────────────────────────────────────────────────
# start-worker
# ──────────────────────────────────────────────────────────────────────────

@app.command("start-worker")
def start_worker(
    concurrency: int = typer.Option(2, "--concurrency", "-c"),
    loglevel: str = typer.Option("info", "--loglevel"),
) -> None:
    """تشغيل Celery worker (in-memory بدون Redis)."""
    import subprocess

    os.environ.setdefault("CELERY_USE_MEMORY", "1")
    cmd = [
        sys.executable, "-m", "celery",
        "-A", "workers.celery_app",
        "worker",
        "--concurrency", str(concurrency),
        "--loglevel", loglevel,
        "--pool", "threads",
    ]
    console.print(f"[yellow]تشغيل Celery worker...[/yellow]")
    console.print(f"[dim]CELERY_USE_MEMORY=1 (بدون Redis)[/dim]")
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        console.print("[yellow]تم إيقاف Worker.[/yellow]")


# ──────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────

def main() -> None:
    app()


if __name__ == "__main__":
    main()
