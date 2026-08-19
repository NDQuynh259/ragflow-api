"""Shared pytest options for parser inspection tests."""

from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--layout-file",
        action="store",
        default=None,
        help="Path to a document to parse with LayoutParser (inspection test).",
    )


@pytest.fixture
def layout_file(request: pytest.FixtureRequest) -> Path | None:
    """Return the requested input file, or None for the opt-in test."""
    value = request.config.getoption("--layout-file")
    return Path(value).expanduser() if value else None
