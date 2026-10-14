"""`rediacc_ci.quality.inline_suppressions`: the controls the in-module selftest cannot reach from a pure function.

The selftest proves the scanner and the set arithmetic. What it cannot prove is that the gate REFUSES when its tree is not the tree: a scan over a near-empty root, a submodule missing on a CI runner, a baseline write that would grow. Each of those is a way for the gate to print a tick over nothing, so each one is driven here against a real temporary git repository.

Marker fixtures are assembled from halves, so this file never holds a literal marker and the gate it tests has nothing to find here.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.core import common
from rediacc_ci.quality import inline_suppressions as gate

if TYPE_CHECKING:
    import pathlib

NQ = "# noq" + "a"


def _repo(root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root


def test_selftest_passes() -> None:
    assert gate.selftest(quiet=True) == 0


def test_scan_repo_reads_code_and_skips_prose(tmp_path: pathlib.Path) -> None:
    root = _repo(
        tmp_path,
        {
            "a.py": "x = 1  %s: B010\n" % NQ,
            "bin/tool": "#!/usr/bin/env python3\ny = 2  %s: F401\n" % NQ,
            "docs/a.md": "Never write `%s: B010`.\n" % NQ,
            "b.py": '"""Mentions %s: B010 in a docstring."""\n' % NQ,
        },
    )
    scan = gate.Scan()
    gate.scan_repo(root, "console", "", scan)
    assert gate.flatten(scan.counts) == {"a.py": {"noqa B010": 1}, "bin/tool": {"noqa F401": 1}}
    # CONTROL: the docstring file and the Markdown were READ or skipped, never counted.
    assert scan.files_by_language["py"] == 3


def test_a_near_empty_root_is_vacuous_not_clean(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The floor, on a root whose submodules are absent the way a fresh local clone's are.

    `CI` IS REMOVED, because `main` reads the process environment and under `CI=true` a missing submodule refuses BEFORE the floor is reached: the same exit 1 for the neighbouring test's reason. The suite inherits `CI=true` on every GitHub runner, so this passed only where it was not set (run 38389205702). The second half drives that CI arm through the same `main`, so both refusals are told apart by their text.
    """
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    monkeypatch.delenv("CI", raising=False)
    rc = gate.main([], root=root)
    assert rc == 1
    assert "VACUOUS" in capsys.readouterr().err
    monkeypatch.setenv("CI", "true")
    rc = gate.main([], root=root)
    err = capsys.readouterr().err
    assert rc == 1
    assert "is required in CI but missing" in err
    assert "VACUOUS" not in err


def test_a_missing_submodule_refuses_in_ci(tmp_path: pathlib.Path) -> None:
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    with pytest.raises(common.RefusalError):
        gate.scan_tree(root, env={"CI": "true"})


def test_a_missing_submodule_is_not_checked_locally(tmp_path: pathlib.Path) -> None:
    root = _repo(tmp_path, {"a.py": "x = 1  %s: E402\n" % NQ})
    scan = gate.scan_tree(root, env={})
    assert scan.not_checked == ["private/renet", "private/account"]
    # CONTROL: console itself was still read.
    assert gate.flatten(scan.counts) == {"a.py": {"noqa E402": 1}}


def test_count_reads_its_pathspec(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--count <path>` once ignored its argument and ran the whole gate (item 3993c728): every per-tree acceptance line of the drain plan read the same tree-wide verdict. Each spec now gets its own count, and a spec under which nothing was read refuses instead of reporting 0."""
    root = _repo(
        tmp_path,
        {
            "a/x.py": "x = 1  %s: F401\ny = 2  %s: E402\n" % (NQ, NQ),
            "a/clean.py": "z = 3\n",
            "b/y.py": "w = 4\n",
            "ab/z.py": "v = 5  %s: B010\n" % NQ,
        },
    )
    monkeypatch.delenv("CI", raising=False)
    assert gate.main(["--count", "a", "./b/"], root=root) == 0
    out = capsys.readouterr().out
    assert "a: 2 marker(s) in 1 of 2 code file(s) read (by kind: noqa 2)" in out
    assert "b: 0 marker(s) in 0 of 1 code file(s) read (by kind: none)" in out
    # CONTROL: a prefix is a path component, so `a` above did not swallow `ab/z.py`, and `ab` sees it.
    assert gate.main(["--count", "ab"], root=root) == 0
    assert (
        "ab: 1 marker(s) in 1 of 1 code file(s) read (by kind: noqa 1)" in capsys.readouterr().out
    )
    assert gate.main(["--count", "a/x.py"], root=root) == 0
    assert "a/x.py: 2 marker(s) in 1 of 1" in capsys.readouterr().out
    assert gate.main(["--count", "nowhere"], root=root) == 1
    assert "VACUOUS: no code file was read under nowhere" in capsys.readouterr().err
    assert gate.main(["--count"], root=root) == 2


def test_the_gate_holds_zero_and_refuses_a_baseline_file(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Box F of PLAN-inline-suppressions: zero markers, and NO baseline. Each verdict is driven through the real `main` on one root, in both directions, so a gate that went green on anything (or red on everything) fails here.

    The console floor is lowered for the temporary root and `CI` is removed so the absent submodules are NOT CHECKED rather than a refusal; `test_a_near_empty_root_is_vacuous_not_clean` holds the real floor.
    """
    root = _repo(tmp_path, {"a.py": "x = 1\n", "b.ts": "export const y = 2;\n"})
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(gate, "MIN_CONSOLE_FILES", 1)

    assert gate.main([], root=root) == 0
    out = capsys.readouterr().out
    assert "0 markers, no baseline" in out
    assert "2 code file(s) read" in out

    # RED: a baseline file at the retired path fails even when it is empty and untracked.
    baseline = root / gate.RETIRED_BASELINE_REL
    baseline.parent.mkdir(parents=True)
    baseline.write_text('{"counts": {}}\n', encoding="utf-8")
    assert gate.main([], root=root) == 1
    captured = capsys.readouterr()
    assert "admits no baseline" in captured.err
    assert "no baseline" not in captured.out
    baseline.unlink()
    assert gate.main([], root=root) == 0
    capsys.readouterr()

    # RED: a planted marker is named by file and line.
    (root / "a.py").write_text("x = 1\nimport json  %s: F401\n" % NQ, encoding="utf-8")
    assert gate.main([], root=root) == 1
    err = capsys.readouterr().err
    assert "a.py:2: %s: F401" % NQ in err
    assert "1 inline suppression marker(s) in 1 file(s)" in err


def test_a_retired_or_unknown_flag_is_refused_not_ignored(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--write-baseline` once wrote the file; silently running the gate instead would read as a successful write, and writing would re-create what box F deleted."""
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(gate, "MIN_CONSOLE_FILES", 1)
    assert gate.main(["--write-baseline"], root=root) == 2
    assert "--write-baseline is retired" in capsys.readouterr().err
    assert not (root / gate.RETIRED_BASELINE_REL).exists()
    assert gate.main(["--write-baseline", "--first-seed"], root=root) == 2
    assert gate.main(["--bogus"], root=root) == 2
    assert "unknown argument(s): --bogus" in capsys.readouterr().err
    assert gate.main(["--count", "a.py", "--bogus"], root=root) == 2
    assert gate.main(["--selftest", "--count"], root=root) == 2
    # CONTROL: the supported spellings still run.
    assert gate.main(["--selftest"], root=root) == 0
    assert gate.main(["--count", "a.py"], root=root) == 0
