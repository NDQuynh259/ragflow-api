"""Core Message Queue module.

Provides standardized job envelopes, ports, producers, and consumer dispatchers
for reliable asynchronous background processing across the RAG platform.
"""

from __future__ import annotations

from core.queue.background import BackgroundQueueAdapter
from core.queue.constants import Actions, Exchanges, Queues, RoutingKeys
from core.queue.consumer import AsyncRabbitMQConsumer, JobDispatcher
from core.queue.in_memory import InMemoryQueueAdapter
from core.queue.port import IngestionQueuePort, JobQueuePort
from core.queue.rabbitmq import RabbitMQQueueAdapter
from core.queue.schema import DocumentJobPayload, JobEnvelope

__all__ = [
    "Actions",
    "AsyncRabbitMQConsumer",
    "BackgroundQueueAdapter",
    "DocumentJobPayload",
    "Exchanges",
    "IngestionQueuePort",
    "InMemoryQueueAdapter",
    "JobDispatcher",
    "JobEnvelope",
    "JobQueuePort",
    "Queues",
    "RabbitMQQueueAdapter",
    "RoutingKeys",
]
