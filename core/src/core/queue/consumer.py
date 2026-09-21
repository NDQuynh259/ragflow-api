"""Asynchronous RabbitMQ Consumer and Job Dispatcher engine."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Any

import aio_pika
from pamqp.common import FieldValue

from core.config import settings
from core.queue.constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BASE_DELAY_MS,
    Exchanges,
    Queues,
    RoutingKeys,
)
from core.queue.schema import JobEnvelope

logger = logging.getLogger("core.queue.consumer")


class JobDispatcher:
    """Registry and dispatcher routing JobEnvelope actions to typed processor callables.

    Supports:
    - Both async coroutine functions and sync functions (offloaded via asyncio.to_thread).
    - Flexible signature injection (kwargs, envelope, or individual payload keys).
    - Error hooks and middleware logging with correlation_id.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(self, action: str, handler: Callable[..., Any]) -> None:
        """Register an action processor handler."""
        self._handlers[action] = handler
        logger.debug("Registered handler for queue action '%s': %s", action, handler.__name__)

    async def dispatch(self, envelope: JobEnvelope) -> Any:
        """Route envelope to registered handler by action."""
        handler = self._handlers.get(envelope.action)
        if handler is None:
            raise ValueError(
                f"No handler registered for action '{envelope.action}' (job: {envelope.job_id})"
            )

        sig = inspect.signature(handler)
        kwargs: dict[str, Any] = dict(envelope.payload)
        kwargs["job_id"] = envelope.job_id
        if "envelope" in sig.parameters:
            kwargs["envelope"] = envelope
        if "correlation_id" in sig.parameters and envelope.correlation_id:
            kwargs["correlation_id"] = envelope.correlation_id

        # Pass all kwargs if handler accepts **kwargs, otherwise filter by signature
        has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        call_kwargs = (
            kwargs if has_varkw else {k: v for k, v in kwargs.items() if k in sig.parameters}
        )

        if asyncio.iscoroutinefunction(handler):
            return await handler(**call_kwargs)
        return await asyncio.to_thread(handler, **call_kwargs)


class AsyncRabbitMQConsumer:
    """Robust Async RabbitMQ Consumer built on aio-pika.

    Features:
    - aio_pika.connect_robust for resilient auto-reconnect on network drops.
    - 3-tier topology declaration: Main Queue, Delayed Retry Queue (TTL DLX), and Dead Letter Queue.
    - QoS prefetch_count = 1 for fair competing consumer distribution across workers.
    - Manual Acknowledgement with retry backoff:
      * Failure with retries remaining -> publishes to Delayed Retry Queue with TTL backoff, then ACKs old message.
      * When TTL expires -> RabbitMQ automatically re-delivers message to Main Queue via DLX.
      * Exceeded max retries -> rejects to Dead Letter Queue (requeue=False).
    - Graceful cancellation on SIGINT/SIGTERM.
    """

    def __init__(
        self,
        dispatcher: JobDispatcher,
        amqp_url: str | None = None,
        exchange: str | None = None,
        queue_name: str | None = None,
        routing_key: str | None = None,
        retry_exchange: str | None = None,
        retry_queue: str | None = None,
        retry_routing_key: str | None = None,
        dlx_exchange: str | None = None,
        dlq_queue: str | None = None,
        dlq_routing_key: str | None = None,
        prefetch_count: int = 1,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay_ms: int = DEFAULT_RETRY_BASE_DELAY_MS,
    ) -> None:
        self.dispatcher = dispatcher
        self.amqp_url = amqp_url or getattr(
            settings, "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
        )
        self.exchange = exchange or getattr(settings, "RABBITMQ_EXCHANGE", Exchanges.PRIMARY)
        self.queue_name = queue_name or getattr(
            settings, "RABBITMQ_INGESTION_QUEUE", Queues.DOCUMENT_INGESTION
        )
        self.routing_key = routing_key or getattr(
            settings, "RABBITMQ_ROUTING_KEY", RoutingKeys.DOCUMENT_INGESTION
        )

        self.retry_exchange = retry_exchange or getattr(
            settings, "RABBITMQ_RETRY_EXCHANGE", Exchanges.RETRY
        )
        self.retry_queue = retry_queue or getattr(
            settings, "RABBITMQ_RETRY_QUEUE", Queues.DOCUMENT_INGESTION_RETRY
        )
        self.retry_routing_key = retry_routing_key or getattr(
            settings, "RABBITMQ_RETRY_ROUTING_KEY", RoutingKeys.DOCUMENT_INGESTION_RETRY
        )

        self.dlx_exchange = dlx_exchange or getattr(
            settings, "RABBITMQ_DLX_EXCHANGE", Exchanges.DLX
        )
        self.dlq_queue = dlq_queue or getattr(
            settings, "RABBITMQ_DLQ_QUEUE", Queues.DOCUMENT_INGESTION_DLQ
        )
        self.dlq_routing_key = dlq_routing_key or getattr(
            settings, "RABBITMQ_DLQ_ROUTING_KEY", RoutingKeys.DOCUMENT_INGESTION_DLQ
        )

        self.prefetch_count = prefetch_count
        self.max_retries = max_retries
        self.retry_base_delay_ms = retry_base_delay_ms
        self._is_running = False

    async def setup_topology(
        self, channel: aio_pika.abc.AbstractChannel
    ) -> tuple[aio_pika.abc.AbstractQueue, aio_pika.abc.AbstractExchange]:
        """Declare 3-tier AMQP topology: DLQ, Delayed Retry (TTL), and Main Queue."""
        # 1. Dead Letter Exchange & Queue
        dlx = await channel.declare_exchange(
            self.dlx_exchange, type=aio_pika.ExchangeType.DIRECT, durable=True
        )
        dlq = await channel.declare_queue(self.dlq_queue, durable=True)
        await dlq.bind(dlx, routing_key=self.dlq_routing_key)

        # 2. Delayed Retry Exchange & Queue (points DLX back to main exchange)
        retry_ex = await channel.declare_exchange(
            self.retry_exchange, type=aio_pika.ExchangeType.DIRECT, durable=True
        )
        retry_args: dict[str, FieldValue] = {
            "x-dead-letter-exchange": self.exchange,
            "x-dead-letter-routing-key": self.routing_key,
        }
        retry_q = await channel.declare_queue(self.retry_queue, durable=True, arguments=retry_args)
        await retry_q.bind(retry_ex, routing_key=self.retry_routing_key)

        # 3. Main Exchange & Queue (points DLX to Dead Letter Queue on reject)
        main_ex = await channel.declare_exchange(
            self.exchange, type=aio_pika.ExchangeType.DIRECT, durable=True
        )
        main_args: dict[str, FieldValue] = {
            "x-dead-letter-exchange": self.dlx_exchange,
            "x-dead-letter-routing-key": self.dlq_routing_key,
        }
        main_q = await channel.declare_queue(self.queue_name, durable=True, arguments=main_args)
        await main_q.bind(main_ex, routing_key=self.routing_key)

        return main_q, retry_ex

    async def run(self) -> None:
        """Start consumer loop with fair dispatch and robust retry handling."""
        logger.info("Connecting to RabbitMQ at %s...", self.amqp_url)
        connection = await aio_pika.connect_robust(self.amqp_url)

        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=self.prefetch_count)

            main_queue, retry_ex = await self.setup_topology(channel)
            self._is_running = True

            logger.info(
                "Consumer ready. Listening on queue '%s' (exchange: '%s', prefetch: %d)...",
                self.queue_name,
                self.exchange,
                self.prefetch_count,
            )

            async with main_queue.iterator() as queue_iter:
                async for message in queue_iter:
                    await self._process_one_message(message, retry_ex)

    async def _process_one_message(
        self,
        message: aio_pika.abc.AbstractIncomingMessage,
        retry_ex: aio_pika.abc.AbstractExchange,
    ) -> None:
        envelope: JobEnvelope | None = None
        try:
            envelope = JobEnvelope.from_bytes(message.body)
        except Exception as parse_err:
            logger.error(
                "Failed to parse message into JobEnvelope: %s. Rejecting to DLQ.", parse_err
            )
            await message.reject(requeue=False)
            return

        logger.info(
            "Processing job %s [action: %s, attempt: %d, correlation: %s]",
            envelope.job_id,
            envelope.action,
            envelope.retry_count + 1,
            envelope.correlation_id,
        )

        try:
            await self.dispatcher.dispatch(envelope)
            await message.ack()
            logger.info("Job %s completed successfully (ACKed).", envelope.job_id)

        except Exception as exc:
            logger.exception(
                "Error processing job %s (attempt %d/%d): %s",
                envelope.job_id,
                envelope.retry_count + 1,
                self.max_retries,
                exc,
            )

            if envelope.retry_count < self.max_retries:
                envelope.retry_count += 1
                delay_ms = int(self.retry_base_delay_ms * (2 ** (envelope.retry_count - 1)))

                # Publish to Delayed Retry Queue with expiration (TTL)
                retry_message = aio_pika.Message(
                    body=envelope.to_bytes(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    expiration=delay_ms / 1000.0,
                    message_id=envelope.job_id,
                    correlation_id=envelope.correlation_id,
                    content_type="application/json",
                )
                await retry_ex.publish(retry_message, routing_key=self.retry_routing_key)
                await message.ack()
                logger.info(
                    "Job %s routed to retry queue (attempt %d/%d, TTL: %d ms).",
                    envelope.job_id,
                    envelope.retry_count,
                    self.max_retries,
                    delay_ms,
                )
            else:
                # Max retries reached -> Route to DLQ
                await message.reject(requeue=False)
                logger.error(
                    "Job %s exceeded max retries (%d). Rejected to DLQ '%s'.",
                    envelope.job_id,
                    self.max_retries,
                    self.dlq_queue,
                )


__all__ = ["AsyncRabbitMQConsumer", "JobDispatcher"]
