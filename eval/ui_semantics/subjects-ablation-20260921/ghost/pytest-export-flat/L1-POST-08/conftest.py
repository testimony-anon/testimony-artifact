"""Runtime fixture for the generated frozen UISemTest suite."""

import os
from pathlib import Path

import pytest

from ui_semantics.pytest_export import FrozenSuitePytestRuntime


ARTIFACT_ROOT = Path(os.environ.get('UISEMTEST_ARTIFACT_ROOT') or Path(__file__).resolve().parents[6])
SOURCE_RUN_ROOT = ARTIFACT_ROOT / 'eval/ui_semantics/subjects-ablation-20260921/ghost/flat-01/cases/L1-POST-08/union'


@pytest.fixture(scope="session")
def uisemtest_runtime(tmp_path_factory):
    runtime = FrozenSuitePytestRuntime(
        SOURCE_RUN_ROOT,
        tmp_path_factory.mktemp("uisemtest-pytest-runtime", numbered=True),
    ).open()
    try:
        yield runtime
    finally:
        runtime.close()
