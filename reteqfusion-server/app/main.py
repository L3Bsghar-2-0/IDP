"""FastAPI entrypoint with lifespan-managed MQTT, DB pool, and background tasks."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.alerts.alerting import AlertingService
from app.api.router import api_router
from app.config import get_settings
from app.logging_setup import configure_logging
from app.mqtt.client import MqttClient
from app.mqtt.handlers import MessageDispatcher
from app.processing.pipeline import ProcessingPipeline
from app.storage.database import Database
from app.storage.dlq_repo import DlqRepository
from app.storage.device_repo import DeviceRepository
from app.storage.migrations import run_migrations
from app.storage.telemetry_repo import TelemetryRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup / shutdown of all background services."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("application_starting", extra={"version": "1.0.0"})

    # 1. Database
    database = Database(settings.database_url)
    await database.connect()
    await run_migrations(database)

    telemetry_repo = TelemetryRepository(database)
    dlq_repo = DlqRepository(database)
    device_repo = DeviceRepository(database)

    # 2. MQTT message queue (thread-safe bridge)
    queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)

    # 3. MQTT client (background thread)
    mqtt_client = MqttClient(settings, queue, asyncio.get_running_loop())
    mqtt_client.start()

    # 4. Processing pipeline
    pipeline = ProcessingPipeline(
        telemetry_repo=telemetry_repo,
        dlq_repo=dlq_repo,
        device_repo=device_repo,
        mqtt_client=mqtt_client,
        settings=settings,
    )

    dispatcher = MessageDispatcher(pipeline=pipeline, dlq_repo=dlq_repo)

    # 5. Consumer coroutine
    async def consume_loop() -> None:
        while True:
            try:
                topic, payload = await queue.get()
            except asyncio.CancelledError:
                break
            try:
                await dispatcher.dispatch(topic, payload)
            except Exception as exc:  # noqa: BLE001
                logger.exception("dispatch_failed", extra={"topic": topic, "err": str(exc)})

    consumer_task = asyncio.create_task(consume_loop(), name="mqtt-consumer")

    # 6. Alerting background task
    alerting = AlertingService(
        database=database,
        mqtt_client=mqtt_client,
        settings=settings,
    )
    alert_task = asyncio.create_task(alerting.run_forever(), name="alerting")

    # publish to app state for routers
    app.state.database = database
    app.state.telemetry_repo = telemetry_repo
    app.state.dlq_repo = dlq_repo
    app.state.device_repo = device_repo
    app.state.mqtt_client = mqtt_client
    app.state.queue = queue

    logger.info("application_ready")

    try:
        yield
    finally:
        logger.info("application_stopping")
        consumer_task.cancel()
        alert_task.cancel()
        for task in (consumer_task, alert_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        try:
            mqtt_client.stop()
        except Exception:  # noqa: BLE001
            logger.exception("mqtt_shutdown_failed")
        await database.close()
        logger.info("application_stopped")


app = FastAPI(
    title="ReTeqFusion IoT Server",
    description="Industrial energy monitoring telemetry ingestion + REST API.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)
