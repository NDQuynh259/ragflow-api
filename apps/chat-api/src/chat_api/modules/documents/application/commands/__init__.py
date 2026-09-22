"""Document CQRS Commands and Handlers."""

from chat_api.modules.documents.application.commands.delete_document_command import (
    DeleteDocumentCommand,
    DeleteDocumentHandler,
)
from chat_api.modules.documents.application.commands.index_document_command import (
    IndexDocumentCommand,
    IndexDocumentHandler,
)
from chat_api.modules.documents.application.commands.upload_document_command import (
    UploadDocumentCommand,
    UploadDocumentHandler,
)

__all__ = [
    "UploadDocumentCommand",
    "UploadDocumentHandler",
    "DeleteDocumentCommand",
    "DeleteDocumentHandler",
    "IndexDocumentCommand",
    "IndexDocumentHandler",
]
