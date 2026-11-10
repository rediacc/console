"""check:ci-hint-corpus judges a HINTS entry's `Enforced-By:` with the shared TRAPS resolver (PLAN-experience-feedback P7, box C7b).

The gate script is run for real over a fixture HINTS.md (its `HINTS_FILE` pointed at a temp file), so the verdict and the printed reason are the ones CI sees. The fixture is the live corpus plus one planted entry; the control entry (a live pointer) must pass, or the red cases prove nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib

SCRIPT = paths.from_root(".ci", "scripts", "quality", "check_hint_corpus.py")
LIVE_HINTS = paths.from_root("docs", "agent-reference", "HINTS.md")


def _gate():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("check_hint_corpus_under_test", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(gate, tmp_path: pathlib.Path, enforced: str | None, capsys) -> tuple[int, str]:
    text = LIVE_HINTS.read_text(encoding="utf-8")
    if enforced is not None:
        text += (
            "\n## Planted entry for the Enforced-By check\nHint-Id: planted-enforced-by\n"
            "Source: file:CLAUDE.md:1\nStatus: active\nEnforced-By: %s\n" % enforced
        )
    path = tmp_path / "HINTS.md"
    path.write_text(text, encoding="utf-8")
    gate.HINTS_FILE = str(path)
    rc = gate.main()
    return rc, capsys.readouterr().err


def test_control_the_live_corpus_is_green(tmp_path, capsys):
    rc, err = _run(_gate(), tmp_path, None, capsys)
    assert rc == 0, err


@pytest.mark.parametrize(
    "pointer",
    ["gate:check:ci-hint-corpus", "JUDGMENT-ONLY", "JUDGMENT-ONLY, gate:check:ci-hint-corpus"],
)
def test_a_live_pointer_and_a_judgment_only_declaration_pass(tmp_path, capsys, pointer):
    rc, err = _run(_gate(), tmp_path, pointer, capsys)
    assert rc == 0, err


@pytest.mark.parametrize(
    "pointer",
    [
        "guard:block_planted_missing_guard",
        "gate:check:ci-planted-missing-gate",
        "hook:planted-missing-rule",
        "file:docs/agent-reference/NO-SUCH-FILE.md",
        "test:something",
    ],
)
def test_a_pointer_the_shared_resolver_rejects_reds_the_gate_with_the_reason(
    tmp_path, capsys, pointer
):
    rc, err = _run(_gate(), tmp_path, pointer, capsys)
    assert rc != 0, "the gate stayed green over %s" % pointer
    assert "planted-enforced-by: Enforced-By %s is not a live enforcer" % pointer in err, err
