"""Runtime fixture for the generated frozen UISemTest suite."""

from pathlib import Path

import pytest

from ui_semantics.pytest_export import FrozenSuitePytestRuntime


SOURCE_RUN_ROOT = Path('<TMP>')


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
