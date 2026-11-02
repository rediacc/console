"""SIGTERM reaches the teardown of both proxy gates exactly once, and a second SIGTERM during teardown cannot cut it short (reviews 3182e020.1, .2, 3c5f450a.1, .6)."""

from __future__ import annotations

import os
import signal
import subprocess
from typing import TYPE_CHECKING, Any, cast

import pytest

if TYPE_CHECKING:
    import types

from rediacc_ci.quality import proxy_image_smoke as smoke
from rediacc_ci.quality import proxy_wrangler_dev_e2e as dev

GATES = [(smoke, "_smoke"), (dev, "run")]


@pytest.mark.parametrize(("gate", "entry"), GATES, ids=["image-smoke", "wrangler-dev"])
def test_sigterm_runs_the_whole_teardown_even_when_a_second_one_lands_in_it(
    monkeypatch: pytest.MonkeyPatch, gate: types.ModuleType, entry: str
) -> None:
    ran: list[str] = []

    def body(*_a: object, **_k: object) -> int:
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            raise AssertionError("the first SIGTERM must raise")
        finally:
            os.kill(os.getpid(), signal.SIGTERM)
            ran.append("first removal")
            ran.append("second removal")

    monkeypatch.setattr(gate, "controls_first", lambda *_a, **_k: 0)
    monkeypatch.setattr(gate, entry, body)
    monkeypatch.setattr(gate.paths, "repo_root", lambda: None, raising=False)
    previous = signal.getsignal(signal.SIGTERM)
    assert gate.main([]) == 143
    assert ran == ["first removal", "second removal"]
    assert signal.getsignal(signal.SIGTERM) == previous


def test_stop_reports_a_wrangler_that_survives_sigkill(monkeypatch: pytest.MonkeyPatch) -> None:
    class Proc:
        pid = 4242

        def poll(self) -> None:
            return None

        def wait(self, timeout: float) -> None:
            raise subprocess.TimeoutExpired("wrangler", timeout)

    sent: list[int] = []
    monkeypatch.setattr(dev.os, "killpg", lambda _pid, sig: sent.append(sig))
    assert dev._stop(cast("Any", Proc())) is False
    assert sent == [signal.SIGINT, signal.SIGKILL]


def test_a_surviving_wrangler_is_a_finding() -> None:
    found = dev.verdict({**dev.HEALTHY, "wrangler_survived": 4242})
    assert any("still running after SIGKILL" in f for f in found)
