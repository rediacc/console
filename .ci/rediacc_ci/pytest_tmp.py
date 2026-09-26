"""The killed-run sweep for pytest's own basetemps. Loaded by the repo-root conftest (`pytest_plugins`), so both pytest roots, `.ci/rediacc_ci/tests` and `.claude/rediacc_hooks/tests`, get it.

A plugin module rather than conftest code for one reason: `.ci/rediacc_ci/tests/test_pytest_tmp.py` must drive it inside a CHILD pytest it can SIGKILL, and a child run from a scratch directory loads this with `-p rediacc_ci.pytest_tmp` (or, for the planted defect, without it) where a repo-root conftest would not load at all.

WHAT IT DELIBERATELY DOES NOT DO. An earlier cut also pointed TMPDIR and `tempfile.tempdir` for the whole test process at a pid-stamped run dir. Measured on 2026-09-24, that breaks two contracts that cannot both hold under one process-wide temp base: test_core_devbox.py compares an in-process temp path with a subprocess's, and block_edit_of_running_script's fixture world needs ONE fixed path across runs (it serialises runs on a lock there and reaps by that path). Children are covered where they are started instead: `rediacc_ci.tests.differential.BASE_ENV` and `rediacc_ci.tests.gates.harness.run`.
"""

from __future__ import annotations

import os
import tempfile

from _pytest.tmpdir import get_user

from rediacc_ci import runtmp


def pytest_configure() -> None:
    """Reclaim every basetemp a KILLED run left, before this run creates its own.

    pytest keeps a numbered basetemp until its `.lock` is three days old, and a SIGKILLed or timed-out run is exactly one whose lock survives (see `runtmp.sweep_dead_basetemps`). On 2026-09-24 ten such trees held most of /tmp's 1,048,576 inodes.

    The root is the DEFAULT one `_pytest/tmpdir.py` uses, `tempfile.gettempdir()` then `pytest-of-<user>`, read through `tempfile` and pytest's own helper so the env registry has nothing new to learn. A run that redirects its basetemps with `PYTEST_DEBUG_TEMPROOT` or `--basetemp` is outside this sweep, and nothing in this repo does either.
    """
    runtmp.sweep_dead_basetemps(
        os.path.join(tempfile.gettempdir(), "pytest-of-%s" % (get_user() or "unknown"))
    )
