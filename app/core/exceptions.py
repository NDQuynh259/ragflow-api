"""Application-level errors that are independent of the HTTP framework."""


class AppError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.headers = dict(headers or {})
