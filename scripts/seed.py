"""Seed script for development & testing.

Seeds initial admin and demo user accounts along with default workspaces and memberships.

Usage:
    uv run python scripts/seed.py
    poe seed
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# Fix Windows console encoding if needed
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Load .env
from dotenv import load_dotenv

load_dotenv()

# Register repositories in UnitOfWork
import chat_api.composition.dependencies  # noqa: F401
from chat_api.modules.auth.application.commands import RegisterCommand, RegisterHandler
from chat_api.modules.workspaces.domain.entity import WorkspaceMember, WorkspaceRole
from core.database import SqlAlchemyUnitOfWork
from sqlalchemy import text


@dataclass(frozen=True)
class SeedUserData:
    email: str
    password: str
    full_name: str
    is_admin: bool = False


SEED_USERS: list[SeedUserData] = [
    SeedUserData(
        email="admin@ragflow.io",
        password="password123",
        full_name="System Administrator",
        is_admin=True,
    ),
    SeedUserData(
        email="user@ragflow.io",
        password="password123",
        full_name="Demo User",
        is_admin=False,
    ),
]


def seed_data(reset: bool = False) -> None:
    uow = SqlAlchemyUnitOfWork()

    print("=" * 64)
    print(">> Starting Database Seeding for Authentication & Workspaces")
    print("=" * 64)

    created_users = []
    admin_workspace = None

    with uow:
        if reset:
            print("[*] Resetting existing seed accounts...")
            for user_data in SEED_USERS:
                existing_user = uow.users.get_by_email(user_data.email)
                if existing_user and uow.session:
                    user_workspaces = uow.workspaces.list_by_user_id(existing_user.id)
                    for ws in user_workspaces:
                        uow.session.execute(
                            text("DELETE FROM workspace_members WHERE workspace_id = :ws_id"),
                            {"ws_id": ws.id},
                        )
                        uow.session.execute(
                            text("DELETE FROM workspaces WHERE id = :ws_id"),
                            {"ws_id": ws.id},
                        )
                    uow.session.execute(
                        text("DELETE FROM user_sessions WHERE user_id = :uid"),
                        {"uid": existing_user.id},
                    )
                    uow.session.execute(
                        text("DELETE FROM users WHERE id = :uid"),
                        {"uid": existing_user.id},
                    )
                    print(f"    - Removed existing user: {user_data.email}")
            if uow.session:
                uow.session.flush()

        # Check and seed users
        for user_data in SEED_USERS:
            existing_user = uow.users.get_by_email(user_data.email)
            if existing_user:
                print(f"[SKIP] User '{user_data.email}' already exists (ID: {existing_user.id}).")
                workspaces = uow.workspaces.list_by_user_id(existing_user.id)
                created_users.append((existing_user, user_data.password, workspaces))
                if user_data.is_admin and workspaces:
                    admin_workspace = workspaces[0]
                continue

            print(f"[+] Creating user: {user_data.email} ({user_data.full_name})...")
            handler = RegisterHandler(uow)
            user = handler.handle(
                RegisterCommand(
                    email=user_data.email,
                    password=user_data.password,
                    full_name=user_data.full_name,
                )
            )
            if uow.session:
                uow.session.flush()

            workspaces = uow.workspaces.list_by_user_id(user.id)
            created_users.append((user, user_data.password, workspaces))
            if user_data.is_admin and workspaces:
                admin_workspace = workspaces[0]
            print(f"    - Created user {user.email} (ID: {user.id})")
            if workspaces:
                print(f"    - Default workspace: '{workspaces[0].name}' (ID: {workspaces[0].id})")

        # Optionally attach Demo User to Admin's Workspace as MEMBER for testing switch-workspace
        if admin_workspace:
            for user, _, _ in created_users:
                if user.email != "admin@ragflow.io":
                    if not admin_workspace.is_member(user.id):
                        print(f"[*] Adding '{user.email}' as MEMBER to '{admin_workspace.name}'...")
                        admin_workspace.members.append(
                            WorkspaceMember(
                                workspace_id=admin_workspace.id,
                                user_id=user.id,
                                role=WorkspaceRole.MEMBER,
                            )
                        )
                        uow.workspaces.save(admin_workspace)
                        print(f"    - Added member to workspace {admin_workspace.id}")

    print("\n" + "=" * 64)
    print("[SUCCESS] Seeding Completed Successfully!")
    print("=" * 64)
    print("\nAvailable credentials for login:")
    for user, pwd, ws_list in created_users:
        ws_info = ", ".join([f"'{w.name}' ({w.id})" for w in ws_list]) if ws_list else "None"
        print(f"  * Email:     {user.email}")
        print(f"    Password:  {pwd}")
        print(f"    Name:      {user.full_name}")
        print(f"    Workspace: {ws_info}")
        print("-" * 64)

    print("\nQuick Test (cURL):")
    print(
        '  curl -X POST http://localhost:8000/api/v1/auth/login \\\n'
        '    -H "Content-Type: application/json" \\\n'
        '    -d \'{"email": "admin@ragflow.io", "password": "password123"}\'\n'
    )
    print("=" * 64)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed database for authentication and workspaces.")
    parser.add_argument("--reset", action="store_true", help="Reset existing seed data if supported.")
    args = parser.parse_args()

    seed_data(reset=args.reset)


if __name__ == "__main__":
    main()
