"""Authentication CQRS Commands and Handlers."""

from chat_api.modules.auth.application.commands.login_command import (
    DEFAULT_SESSION_DURATION_DAYS,
    LoginCommand,
    LoginHandler,
    LoginResult,
)
from chat_api.modules.auth.application.commands.logout_command import (
    LogoutCommand,
    LogoutHandler,
)
from chat_api.modules.auth.application.commands.register_command import (
    RegisterCommand,
    RegisterHandler,
)
from chat_api.modules.auth.application.commands.switch_workspace_command import (
    SwitchWorkspaceCommand,
    SwitchWorkspaceHandler,
)

__all__ = [
    "DEFAULT_SESSION_DURATION_DAYS",
    "LoginCommand",
    "LoginHandler",
    "LoginResult",
    "LogoutCommand",
    "LogoutHandler",
    "RegisterCommand",
    "RegisterHandler",
    "SwitchWorkspaceCommand",
    "SwitchWorkspaceHandler",
]
