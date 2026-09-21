"""Document CQRS Commands and Handlers."""

from chat_api.modules.documents.application.commands.delete_document_command import (
    DeleteDocumentAuthorizer,
    DeleteDocumentCommand,
    DeleteDocumentHandler,
)
from chat_api.modules.documents.application.commands.index_document_command import (
    IndexDocumentCommand,
    IndexDocumentHandler,
)
from chat_api.modules.documents.application.commands.upload_document_command import (
    UploadDocumentAuthorizer,
    UploadDocumentCommand,
    UploadDocumentHandler,
)

__all__ = [
    "UploadDocumentCommand",
    "UploadDocumentAuthorizer",
    "UploadDocumentHandler",
    "DeleteDocumentCommand",
    "DeleteDocumentAuthorizer",
    "DeleteDocumentHandler",
    "IndexDocumentCommand",
    "IndexDocumentHandler",
]
