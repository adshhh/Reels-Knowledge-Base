"""Shared fixtures for the serve test suite: a fake corpus and a TestClient against it."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reelkb.serve.app import create_app
from reelkb.testing.fake_db import build


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    return TestClient(create_app(data_dir))
