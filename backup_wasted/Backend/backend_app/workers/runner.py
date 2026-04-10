from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from backend_app.api.deps import get_adapter_client
from backend_app.core.config import get_settings
from backend_app.db.session import SessionLocal
from backend_app.workers.reapers import AccessCodeReaper, RuntimeSessionReaper
from backend_app.workers.runtime_refresh import RuntimeRefreshWorker

logger = logging.getLogger(__name__)


async def run_builtin_workers(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    refresh_worker = RuntimeRefreshWorker(
        session_factory=SessionLocal,
        adapter_factory=get_adapter_client,
        stale_after_minutes=settings.runtime_refresh_stale_after_minutes,
    )
    runtime_reaper = RuntimeSessionReaper(
        session_factory=SessionLocal,
        adapter_factory=get_adapter_client,
    )
    access_code_reaper = AccessCodeReaper(session_factory=SessionLocal)

    intervals = {
        "runtime_refresh": settings.runtime_refresh_interval_seconds,
        "runtime_reaper": settings.runtime_reaper_interval_seconds,
        "access_code_reaper": settings.access_code_reaper_interval_seconds,
    }
    last_run = {name: 0.0 for name in intervals}
    loop = asyncio.get_running_loop()

    while not stop_event.is_set():
        now = loop.time()
        try:
            if now - last_run["runtime_refresh"] >= intervals["runtime_refresh"]:
                result = await asyncio.to_thread(
                    refresh_worker.run_once,
                    limit=settings.maintenance_batch_limit,
                )
                logger.info("runtime_refresh worker finished: %s", result.model_dump())
                last_run["runtime_refresh"] = now

            if now - last_run["runtime_reaper"] >= intervals["runtime_reaper"]:
                result = await asyncio.to_thread(
                    runtime_reaper.run_once,
                    limit=settings.maintenance_batch_limit,
                )
                logger.info("runtime_reaper worker finished: %s", result.model_dump())
                last_run["runtime_reaper"] = now

            if now - last_run["access_code_reaper"] >= intervals["access_code_reaper"]:
                result = await asyncio.to_thread(
                    access_code_reaper.run_once,
                    limit=max(settings.maintenance_batch_limit, 100),
                )
                logger.info("access_code_reaper worker finished: %s", result.model_dump())
                last_run["access_code_reaper"] = now
        except Exception:  # pragma: no cover - defensive background logging
            logger.exception("Builtin maintenance worker run failed.")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=1.0)
        except TimeoutError:
            continue


async def shutdown_worker_task(task: asyncio.Task[None], stop_event: asyncio.Event) -> None:
    stop_event.set()
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
