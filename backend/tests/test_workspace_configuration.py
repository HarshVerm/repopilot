"""Regression checks for persistent workspaces across release deployments."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.services.reviews.service import ReviewService, ReviewStateError


def test_all_workspace_consumers_use_configured_root(tmp_path):
    script = '''
import importlib
from pathlib import Path
import os
from app.core.config import settings
modules = [
    "app.services.workspace.manager", "app.services.tasks.workflow",
    "app.services.hardening.readiness", "app.services.cleanup.workspace",
    "app.api.routes.indexing", "app.api.routes.reviews",
    "app.api.routes.retrieval", "app.api.routes.coding",
    "app.api.routes.debugging", "app.api.routes.execution",
    "app.api.routes.publishing", "app.api.routes.plans",
]
expected = Path(os.environ["WORKSPACE_ROOT"])
for name in modules:
    assert importlib.import_module(name).WORKSPACES_DIR == expected, name
assert settings.workspace_root == expected
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "WORKSPACE_ROOT": str(tmp_path / "persistent")},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_missing_review_workspace_is_a_recoverable_conflict(tmp_path):
    with pytest.raises(ReviewStateError, match="workspace is unavailable"):
        asyncio.run(ReviewService().verify_current_workspace(
            change_set=SimpleNamespace(base_commit_sha="unchanged"),
            repository_path=tmp_path / "missing-repository",
            db=None,
            expected_diff_hash="unchanged",
            allow_diff_hash_backfill=False,
        ))
