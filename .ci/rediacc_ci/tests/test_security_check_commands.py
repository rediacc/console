"""Differential: `rediacc_ci.security.check_commands` against its twin
`.ci/scripts/security/check-commands.sh` (registered gate
`check:ci-shell-commands`, `ci-quality.yml:351`).

A FIXTURE TREE, NOT THE REAL REPOSITORY. Both subjects derive the console
root from their own file location (`.ci/scripts/security/` for the twin,
`.ci/rediacc_ci/security/` for the port, both three directories up), so each
case COPIES both subjects into a fresh tree at the right relative depth and
scans fixture `.sh` files placed under `.ci/` and `scripts/` there --
verified independently to also agree on the REAL tree (515 files, both sides
clean, exit 0) before this file was written.

TWO REAL BUGS IN THE TWIN, FIXED 2026-09-10 IN LOCKSTEP WITH THIS PORT.
Until this date, both were reproduced (not fixed) here to match the
then-still-buggy twin:

  1. `$(cmd)` used to be invisible. A double-quote escaping mistake in the
     twin's source turned the intended `\\$\\(` into a bare `$\\(` once
     bash's quote rules stripped the backslash before `$`; ugrep's `-E`
     (7.5.0, this house's documented `^`-alternation trap's twin for `$`)
     then treated that `$` as a real anchor even mid-alternation, making
     the whole branch permanently unmatchable.
     `test_command_substitution_form_is_now_caught` locks down the fix: a
     disallowed command hidden inside `$(...)` must now be CAUGHT by both
     the twin and the port, on a real invocation of both.
  2. `if <cmd>; then` used to be invisible. The wide per-file filter has a
     fifth branch (`^[[:space:]]*if\\s+`) that the narrow per-command check
     never had, so a line caught ONLY by that branch matched no per-command
     regex and nothing was ever reported. `test_if_guarded_form_is_now_caught`
     locks down the fix the same way.

Fixed in `.ci/scripts/security/check-commands.sh:70,84` and
`.ci/rediacc_ci/security/check_commands.py` in the same change, applying the
46-finding corpus fix documented in `agent/PLAN-shell-command-gate-regex-fix.md`.
`test_planted_defect_is_caught`'s two plants now regress the PORT alone
against the fixed twin, guarding against either bug creeping back in.

K=5 LEDGER: `.ci/shadow/w7p6-check-commands.observations.jsonl` (re-recorded
2026-09-10 against the fixed pair).
"""

from __future__ import annotations

import shutil
import subprocess
import typing

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "security" / "check-commands.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "security" / "check_commands.py"


def _fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "tree"
    (root / ".ci" / "scripts" / "security").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "security").mkdir(parents=True)
    (root / ".ci" / "x").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "security" / TWIN.name)
    shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "security" / PORT.name)
    return root


def _write(root: pathlib.Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run(subject: pathlib.Path, root: pathlib.Path) -> subprocess.CompletedProcess[str]:
    subject_dir = (
        root / ".ci" / "scripts" / "security"
        if subject.suffix == ".sh"
        else root / ".ci" / "rediacc_ci" / "security"
    )
    runner = ["bash"] if subject.suffix == ".sh" else ["python3"]
    return subprocess.run(
        [*runner, str(subject_dir / subject.name)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def run_both(root: pathlib.Path):
    return _run(TWIN, root), _run(PORT, root)


def _assert_agree(old, new, label: str) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )


def test_clean_tree_is_compatible(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    _write(root, ".ci/x/clean.sh", "#!/bin/bash\necho hello\ndate\n")
    old, new = run_both(root)
    assert old.returncode == 0
    _assert_agree(old, new, "clean-tree")
    assert "All commands are CI-compatible" in old.stdout


def test_direct_disallowed_command_is_reported(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    _write(root, ".ci/x/bad.sh", "#!/bin/bash\nseq 1 10\necho hi | tac\n")
    old, new = run_both(root)
    assert old.returncode == 1
    _assert_agree(old, new, "direct-disallowed")
    assert "'seq' not available" in old.stderr
    assert "'tac' not available" in old.stderr
    assert "Found 2 CI-incompatible command(s)" in old.stderr


def test_variable_assignment_is_not_a_finding(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    _write(root, ".ci/x/assign.sh", "#!/bin/bash\ntimeout=30\nlocal seq=5\nexport tac=x\n")
    old, new = run_both(root)
    assert old.returncode == 0
    _assert_agree(old, new, "assignment-skip")


def test_comment_line_is_not_a_finding(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    _write(root, ".ci/x/comment.sh", "#!/bin/bash\n# seq 1 10 is a comment\n")
    old, new = run_both(root)
    assert old.returncode == 0
    _assert_agree(old, new, "comment-skip")


def test_yaml_style_key_is_not_a_finding(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    _write(root, ".ci/x/yaml.sh", "#!/bin/bash\ncat <<'EOF'\nmytimeout: 3s\nEOF\n")
    old, new = run_both(root)
    assert old.returncode == 0
    _assert_agree(old, new, "yaml-key-skip")


def test_first_disallowed_command_in_array_order_wins(tmp_path: pathlib.Path) -> None:
    """`bc | tac` on one line: `bc` is checked before `tac` in `DISALLOWED`'s
    own array order and the twin `break`s on its first hit, so only `bc` is
    reported even though `tac` also appears and would independently match."""
    root = _fixture(tmp_path)
    _write(root, ".ci/x/order.sh", "#!/bin/bash\nbc | tac\n")
    old, new = run_both(root)
    assert old.returncode == 1
    _assert_agree(old, new, "array-order")
    assert "'bc' not available" in old.stderr
    assert "'tac' not available" not in old.stderr
    assert "Found 1 CI-incompatible command(s)" in old.stderr


def test_command_substitution_form_is_now_caught(tmp_path: pathlib.Path) -> None:
    """FIXED 2026-09-10: `$(shuf ...)` is now caught by both the twin and the
    port, which now agree with each other instead of agreeing on a shared
    blindness. If this goes red, the fix has regressed."""
    root = _fixture(tmp_path)
    _write(root, ".ci/x/subst.sh", '#!/bin/bash\nx=$(shuf -n1 file.txt)\necho "$x"\n')
    old, new = run_both(root)
    assert old.returncode == 1, "the twin should now catch $(...); the fix regressed"
    assert "'shuf' not available" in old.stderr
    _assert_agree(old, new, "command-substitution-now-caught")


def test_if_guarded_form_is_now_caught(tmp_path: pathlib.Path) -> None:
    """FIXED 2026-09-10: the narrow per-command check now carries the `if\\s+`
    branch the wide filter always had, so `if seq 1 10; then` is now caught
    by both sides."""
    root = _fixture(tmp_path)
    _write(root, ".ci/x/ifguard.sh", "#!/bin/bash\nif seq 1 10; then\n    echo hi\nfi\n")
    old, new = run_both(root)
    assert old.returncode == 1, "the twin should now catch if-guarded forms; the fix regressed"
    assert "'seq' not available" in old.stderr
    _assert_agree(old, new, "if-guarded-now-caught")


def test_run_sh_and_rdc_sh_are_always_scanned(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    _write(root, "run.sh", "#!/bin/bash\nseq 1 5\n")
    old, new = run_both(root)
    assert old.returncode == 1
    _assert_agree(old, new, "run-sh-scanned")
    assert "run.sh:2" in old.stderr


def test_run_sh_absent_is_not_an_error(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    _write(root, ".ci/x/clean.sh", "echo fine\n")
    old, new = run_both(root)
    assert old.returncode == 0
    _assert_agree(old, new, "run-sh-absent")


def test_scripts_directory_is_also_scanned(tmp_path: pathlib.Path) -> None:
    """The twin's own comment: `scripts/` joined the corpus after a bash-4-only
    `mapfile` sat unreported in `scripts/dev/reset-bench.sh` for as long as
    anyone could remember; keep it in the port's corpus too."""
    root = _fixture(tmp_path)
    _write(root, "scripts/dev/thing.sh", "#!/bin/bash\nmapfile -t x < f\n")
    old, new = run_both(root)
    assert old.returncode == 1
    _assert_agree(old, new, "scripts-dir-scanned")
    assert "'mapfile' not available" in old.stderr


def test_multiple_files_aggregate_and_ci_env_disables_color(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    _write(root, ".ci/x/a.sh", "#!/bin/bash\nseq 1 3\n")
    _write(root, ".ci/x/b.sh", "#!/bin/bash\ndc -e '1 2 + p'\n")
    old = subprocess.run(
        ["bash", str(root / ".ci" / "scripts" / "security" / "check-commands.sh")],
        cwd=root,
        capture_output=True,
        text=True,
        env={"CI": "true", "PATH": __import__("os").environ.get("PATH", "")},
        check=False,
        timeout=30,
    )
    new = subprocess.run(
        ["python3", str(root / ".ci" / "rediacc_ci" / "security" / "check_commands.py")],
        cwd=root,
        capture_output=True,
        text=True,
        env={"CI": "true", "PATH": __import__("os").environ.get("PATH", "")},
        check=False,
        timeout=30,
    )
    assert old.returncode == 1
    _assert_agree(old, new, "ci-env-no-color")
    assert "\033[" not in old.stdout, "CI=true must disable color on the twin's stdout"
    assert "\033[" not in old.stderr, "CI=true must disable color on the twin's stderr"


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-REGRESSION, two independent plants. Each reintroduces one of the
    two now-fixed bugs into the PORT ALONE, leaving the (now-fixed) twin
    untouched, and asserts the mutated port diverges from the twin -- i.e.
    the differential would catch either bug creeping back into just one
    side. Driven red, then the source is restored byte-identical and
    re-verified green."""
    original = PORT.read_text(encoding="utf-8")

    # Plant A: regress Bug 1 (the $( escape) in the port only.
    plant_a = original.replace(
        r'_WIDE_RE = re.compile(r"(^[ \t]*|[|&;]\s*|\$\(|^[ \t]*if\s+)(" + _CMD_ALTERNATION + ")")',
        r'_WIDE_RE = re.compile(r"(^[ \t]*|[|&;]\s*|$\(|^[ \t]*if\s+)(" + _CMD_ALTERNATION + ")")',
    )
    assert plant_a != original, "the line Plant A targets is no longer present verbatim"

    # Plant B: regress Bug 2 (the missing `if` branch) in _narrow_re only, leaving _WIDE_RE (and Plant A's line, in the ORIGINAL source) alone.
    plant_b = original.replace(
        r'return re.compile(r"(^[ \t]*|[|&;]\s*|\$\(|^[ \t]*if\s+)" + re.escape(cmd) + r"\b")',
        r'return re.compile(r"(^[ \t]*|[|&;]\s*|\$\()" + re.escape(cmd) + r"\b")',
    )
    assert plant_b != original, "the line Plant B targets is no longer present verbatim"

    # `_console_root()` resolves three parents up from wherever the subject file lives, so the twin is placed at the SAME relative depth as PORT inside a fresh throwaway tree, exactly how PORT itself is exercised everywhere else in this file.
    twin_root = tmp_path / "twin-tree"
    (twin_root / ".ci" / "scripts" / "security").mkdir(parents=True)
    (twin_root / ".ci" / "x").mkdir(parents=True)
    shutil.copy2(TWIN, twin_root / ".ci" / "scripts" / "security" / TWIN.name)

    def _run_twin(root: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(root / ".ci" / "scripts" / "security" / "check-commands.sh")],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    def _run_mutant(
        mutated: str, fixture_rel: str, fixture_body: str
    ) -> subprocess.CompletedProcess[str]:
        mutant_root = tmp_path / ("mutant-tree-" + fixture_rel.replace("/", "-"))
        (mutant_root / ".ci" / "rediacc_ci" / "security").mkdir(parents=True)
        (mutant_root / ".ci" / "x").mkdir(parents=True)
        (mutant_root / ".ci" / "rediacc_ci" / "security" / "check_commands.py").write_text(
            mutated, encoding="utf-8"
        )
        _write(mutant_root, fixture_rel, fixture_body)
        return subprocess.run(
            ["python3", str(mutant_root / ".ci" / "rediacc_ci" / "security" / "check_commands.py")],
            cwd=mutant_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    # Plant A, driven against the $(...) fixture.
    _write(twin_root, ".ci/x/subst.sh", "#!/bin/bash\nx=$(shuf -n1 file.txt)\n")
    twin_a = _run_twin(twin_root)
    assert twin_a.returncode == 1, "the fixed twin should catch $(...); check the fix landed"
    mutant_a = _run_mutant(plant_a, ".ci/x/subst.sh", "#!/bin/bash\nx=$(shuf -n1 file.txt)\n")
    assert mutant_a.returncode == 0, "Plant A did not regress the port back to missing $(...)"
    assert mutant_a.returncode != twin_a.returncode, (
        "Plant A was not caught by exit-code comparison"
    )

    # Plant B, driven against the if-guarded fixture.
    _write(twin_root, ".ci/x/ifguard.sh", "#!/bin/bash\nif seq 1 10; then\n    echo hi\nfi\n")
    twin_b = _run_twin(twin_root)
    assert twin_b.returncode == 1, (
        "the fixed twin should catch if-guarded forms; check the fix landed"
    )
    mutant_b = _run_mutant(
        plant_b, ".ci/x/ifguard.sh", "#!/bin/bash\nif seq 1 10; then\n    echo hi\nfi\n"
    )
    assert mutant_b.returncode == 0, (
        "Plant B did not regress the port back to missing if-guarded forms"
    )
    assert mutant_b.returncode != twin_b.returncode, (
        "Plant B was not caught by exit-code comparison"
    )

    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
