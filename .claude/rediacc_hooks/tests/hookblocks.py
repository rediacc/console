"""The one-block assertion runner the fixture cases use.

WHY A SEPARATE OBJECT FROM `hookcases.STATIC`. Most of the suite is data: an event,
an expected exit code, a label. The cases here are not, and no amount of table
design makes them so -- they need a temporary git repo in a known state, a `gh`
stub on PATH, an exported CLAUDE_PROJECT_DIR pointing at a stale clone, or a
genuinely LIVE process for a guard whose whole claim is that it reads the process
table. Those live beside the code that builds them.

A BLOCK KEEPS GOING AFTER A FAILING CASE, exactly as the shell suite did. One
pytest function covers a whole fixture block, so raising on the first mismatch
would hide every later case in that block AND skip the teardown that kills the
fixture's background process. Failures are collected and reported together.

`spec` IS THE COVERAGE READER'S TEXT, not a label. See the note in hookcases.py:
`hook_integrity.covmap` scans declared `case_sources` for the literal shape
`check 2 guards/block_x.py`, so a case's identity is written in that shape here too.
"""

import os

from rediacc_hooks.tests import hookcases, hooklabels


class Block:
    """One fixture block's assertions, with the shell suite's reporting shape."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.failures: list[str] = []
        self.count = 0

    def note(self, bracket: object, label: str, *, ok: bool, detail: str = "") -> None:
        """Record one verdict. The single place a label is emitted."""
        self.count += 1
        hooklabels.record(bracket, label, ok=ok)
        if not ok:
            self.failures.append(
                "[%s] %s%s" % (bracket, label, (" -- " + detail) if detail else "")
            )

    def check(
        self,
        spec: str,
        payload: str,
        label: str,
        *,
        env: dict | None = None,
        cwd: str | None = None,
    ) -> None:
        kase = hookcases.case(spec, payload, label)
        code, _ = hookcases.run_guard(kase.key, payload, want_stderr=False, env=env, cwd=cwd)
        self.note(kase.expected, label, ok=code == kase.expected, detail="got exit %d" % code)

    def check_out(
        self,
        spec: str,
        payload: str,
        label: str,
        needle: str,
        *,
        env: dict | None = None,
        cwd: str | None = None,
    ) -> None:
        kase = hookcases.case(spec, payload, label, needle)
        code, err = hookcases.run_guard(kase.key, payload, want_stderr=True, env=env, cwd=cwd)
        ok = code == kase.expected and needle in err
        self.note(
            kase.expected,
            label,
            ok=ok,
            detail="got exit %d, needle %s" % (code, "present" if needle in err else "MISSING"),
        )

    def done(self) -> None:
        """Fail the pytest function if anything in the block did, naming every case.

        ZERO CASES IS A FAILURE. A block whose fixture silently produced nothing to
        assert would otherwise report a clean green over an empty loop, which is the
        exact shape the suite's own controls exist to refuse.
        """
        # `raise AssertionError`, not `assert`. This is not a test module, and a bare
        # `assert` in one is stripped under -O; the repo holds every non-test file to
        # that rule for exactly that reason.
        if self.count == 0:
            raise AssertionError("%s asserted NOTHING; its fixture produced no cases" % self.name)
        if self.failures:
            raise AssertionError(
                "%s: %d of %d case(s) failed:\n  %s"
                % (self.name, len(self.failures), self.count, "\n  ".join(self.failures))
            )


def env_with(**overrides: str) -> dict:
    """The current environment plus `overrides`, for a case that needs one exported.

    A COPY, never a mutation of os.environ. Under `pytest -n` several blocks run in
    one worker process, and a leaked CLAUDE_PROJECT_DIR would silently re-point every
    later case in that worker at a throwaway clone.
    """
    merged = dict(os.environ)
    merged.update(overrides)
    return merged
