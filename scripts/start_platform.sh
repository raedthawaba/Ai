#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Hajeen AI Platform — Full Platform Startup Script (Section 6.15)
# ═══════════════════════════════════════════════════════════════
#
# Starts: API + Worker + Scheduler
# Redis: Uses fakeredis fallback when Redis server is unavailable
#
# Usage:
#   ./scripts/start_platform.sh              # start all
#   ./scripts/start_platform.sh worker       # worker only
#   ./scripts/start_platform.sh api          # api only
#   ./scripts/start_platform.sh scheduler    # scheduler only
#   ./scripts/start_platform.sh demo         # full demo run

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR]${NC}   $*"; exit 1; }

COMPONENT="${1:-all}"

# ── Directories ──────────────────────────────────────────────────────────────
mkdir -p logs data

# ── Redis check ──────────────────────────────────────────────────────────────
check_redis() {
    if command -v redis-cli &>/dev/null && redis-cli ping 2>/dev/null | grep -q PONG; then
        success "Redis is running at localhost:6379"
        export REDIS_URL="redis://localhost:6379/0"
    else
        warn "Redis not available — using in-memory mode (fakeredis)"
        export CELERY_USE_MEMORY=1
    fi
}

# ── API ──────────────────────────────────────────────────────────────────────
start_api() {
    info "Starting API server..."
    uvicorn api.main:app \
        --host 0.0.0.0 \
        --port "${API_PORT:-8000}" \
        --reload \
        --log-level info \
        &
    API_PID=$!
    success "API running (PID $API_PID) → http://localhost:${API_PORT:-8000}/docs"
}

# ── Worker ───────────────────────────────────────────────────────────────────
start_worker() {
    info "Starting Celery worker..."
    python -m celery \
        -A workers.celery_app \
        worker \
        --queues "default,ingestion,processing,pipeline" \
        --concurrency "${WORKER_CONCURRENCY:-4}" \
        --loglevel info \
        --events \
        --logfile "logs/celery_worker.log" \
        &
    WORKER_PID=$!
    success "Celery worker running (PID $WORKER_PID)"
}

# ── Scheduler ────────────────────────────────────────────────────────────────
start_scheduler() {
    info "Starting APScheduler..."
    python -c "
import time, signal, sys, logging
logging.basicConfig(level=logging.INFO)
from data_engine.ingestion.schedulers.cron_scheduler import get_scheduler

scheduler = get_scheduler()
scheduler.start()
print('[OK]    Scheduler started')

def _stop(sig, frame):
    scheduler.shutdown()
    print('[OK]    Scheduler stopped')
    sys.exit(0)

signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

while True:
    time.sleep(5)
" &
    SCHED_PID=$!
    success "Scheduler running (PID $SCHED_PID)"
}

# ── Demo run ─────────────────────────────────────────────────────────────────
run_demo() {
    info "Running full platform demo..."
    python -c "
import asyncio, logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def demo():
    print()
    print('=== Hajeen AI Platform — Demo Run ===')
    print()

    # 1. Setup a channel
    from shared.schemas.channel import ChannelConfig, SourceConfig, ScheduleConfig
    from shared.utils.id_generator import generate_channel_id
    from data_engine.channels.predefined.demo_channel import DemoChannel
    from data_engine.channels.registry import ChannelRegistry

    channel_id = generate_channel_id()
    config = ChannelConfig(
        id=channel_id,
        name='Demo Platform Channel',
        description='Demo channel for platform test',
        source=SourceConfig(type='demo', url='https://example.com/demo'),
        schedule=ScheduleConfig(cron='*/5 * * * *'),
    )
    channel = DemoChannel(config=config)
    ChannelRegistry.register(channel)
    print(f'[1] Channel created: {channel_id}')

    # 2. Fetch articles
    fetch_result = await channel.fetch()
    articles = fetch_result.articles
    print(f'[2] Fetched {len(articles)} articles')

    # 3. Run pipeline
    processed = await channel.run_pipeline(articles)
    print(f'[3] Processed {len(processed)} articles')

    # 4. Simulate task monitoring
    from monitoring.task_monitor import TaskMonitor, TaskStatus
    monitor = TaskMonitor()
    rec = monitor.on_task_start('demo-task-001', 'demo.task', queue='default')
    monitor.on_task_success('demo-task-001', result_summary=f'Processed {len(processed)} articles')
    summary = monitor.summary()
    print(f'[4] Monitor summary: {summary}')

    # 5. Priority queue demo
    from workers.priority_queue import PriorityTaskQueue, Priority
    q = PriorityTaskQueue()
    q.push('high_task',  payload={'urgency': 'high'},   priority=Priority.HIGH)
    q.push('normal_task', payload={'urgency': 'low'},   priority=Priority.NORMAL)
    q.push('critical',   payload={'urgency': 'critical'}, priority=Priority.CRITICAL)
    tasks = [q.pop() for _ in range(3)]
    print(f'[5] Priority order: {[t.name for t in tasks if t]}')

    # 6. Scheduler demo
    from data_engine.ingestion.schedulers.cron_scheduler import CronScheduler
    sched = CronScheduler()
    sched.start()
    sched.add_interval_job(lambda: None, seconds=60, job_id='demo-job', name='Demo Job')
    jobs = sched.list_jobs()
    print(f'[6] Scheduler jobs: {len(jobs)}')
    sched.shutdown()

    # 7. Retry manager demo
    from workers.retry_manager import RetryManager
    rm = RetryManager()
    state = rm.register('demo-001', 'demo.task')
    rm.record_failure('demo-001', 'Connection timeout')
    delay = rm.compute_delay(1)
    print(f'[7] Retry delay for attempt 1: {delay:.1f}s')

    print()
    print('=== Demo completed successfully! ===')
    print()

asyncio.run(demo())
"
}

# ── Cleanup ──────────────────────────────────────────────────────────────────
cleanup() {
    info "Shutting down..."
    kill "${API_PID:-}" "${WORKER_PID:-}" "${SCHED_PID:-}" 2>/dev/null || true
    success "Shutdown complete"
}

# ── Main ─────────────────────────────────────────────────────────────────────
echo -e "${BOLD}══════════════════════════════════════${NC}"
echo -e "${BOLD}  Hajeen AI Platform v0.6.0${NC}"
echo -e "${BOLD}══════════════════════════════════════${NC}"

check_redis

case "$COMPONENT" in
    api)       start_api ;;
    worker)    start_worker ;;
    scheduler) start_scheduler ;;
    demo)      run_demo ;;
    all)
        trap cleanup EXIT INT TERM
        start_api
        sleep 1
        start_worker
        sleep 1
        start_scheduler
        success "All services started!"
        info "API docs: http://localhost:${API_PORT:-8000}/docs"
        info "Press Ctrl+C to stop"
        wait
        ;;
    *) error "Unknown component: $COMPONENT. Use: all | api | worker | scheduler | demo" ;;
esac
