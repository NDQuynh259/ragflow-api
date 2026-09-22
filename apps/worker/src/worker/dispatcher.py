"""Worker job dispatcher registry and action routing."""

from core.queue import Actions, JobDispatcher
from worker.processors.index_document import process_index_document


def build_dispatcher() -> JobDispatcher:
    """Register all background job action handlers (CQRS processor mapping)."""
    dispatcher = JobDispatcher()
    dispatcher.register(Actions.INDEX, process_index_document)
    dispatcher.register(Actions.REINDEX, process_index_document)
    return dispatcher
