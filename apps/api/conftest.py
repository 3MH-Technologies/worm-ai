"""Root pytest configuration.

`pytest_plugins` must be declared in the top-level conftest only.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def settings() -> Any:
    """Application settings with test defaults (env is set in unit conftest)."""
    from app.core.config import get_settings

    return get_settings()
