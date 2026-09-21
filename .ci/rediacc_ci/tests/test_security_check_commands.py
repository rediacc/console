"""`rediacc_ci.security.check_commands`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/security/check-commands.sh` and the port over one fixture tree each and compared exit code, stdout and stderr. The K=5 ledger `.ci/shadow/w7p6-check-commands.observations.jsonl` recorded that comparison over five distinct trees, re-recorded on 2026-09-10 against the fixed pair.

THE TWIN HAS NOW BEEN DELETED, and every case compares against `goldens/check-commands/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree. Each provenance header carries the twin's blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

The registered gate `check:ci-shell-commands` had already been the port since W7P6, so nothing in CI changes with the deletion.

A FIXTURE TREE, NOT THE REAL REPOSITORY. The subject derives the console root from its own file location, three directories up, so each case COPIES the port into a fresh tree at the right relative depth and scans fixture `.sh` files placed under `.ci/` and `scripts/` there.

Both sides were verified independently to agree on the REAL tree as well (515 files, both clean, exit 0) before the differential was written.

TWO REAL BUGS IN THE TWIN WERE FIXED 2026-09-10 IN LOCKSTEP WITH THE PORT, and the recordings are of the FIXED twin.

  1. `$(cmd)` used to be invisible. A double-quote escaping mistake turned the intended `\\$\\(` into a bare `$\\(` once bash's quote rules stripped the backslash before `$`; ugrep's `-E` then treated that `$` as a real anchor even mid-alternation, making the whole branch permanently unmatchable. `command-substitution-is-caught` is the recording that locks the fix down.
  2. `if <cmd>; then` used to be invisible. The wide per-file filter has a fifth branch (`^[[:space:]]*if\\s+`) that the narrow per-command check never had, so a line caught ONLY by that branch matched no per-command regex and nothing was ever reported. `an-if-guarded-form` is the recording for that one.

Both were fixed in the twin and the port in the same change, applying the 46-finding corpus fix documented in `agent/PLAN-shell-command-gate-regex-fix.md`. `test_planted_defect_is_caught` still reintroduces each bug into the port alone and requires the recording to catch it.

WHAT IS NORMALISED: nothing. Every path a message names is relative to the fixture tree the subject was run from, so the recorded bytes carry no absolute path at all, and that was checked by eye over the whole corpus rather than assumed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "security" / "check_commands.py"
SLUG = "check-commands"

SUBST_FIXTURE = '#!/bin/bash\nx=$(shuf -n1 file.txt)\necho "$x"\n'
IFGUARD_FIXTURE = "#!/bin/bash\nif seq 1 10; then\n    echo hi\nfi\n"

# name -> the fixture files the tree carries, and whether the run is a CI one
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "a-clean-tree": {"files": {".ci/x/clean.sh": "#!/bin/bash\necho hello\ndate\n"}},
    "a-direct-disallowed-command": {
        "files": {".ci/x/bad.sh": "#!/bin/bash\nseq 1 10\necho hi | tac\n"}
    },
    "a-variable-assignment": {
        "files": {".ci/x/assign.sh": "#!/bin/bash\ntimeout=30\nlocal seq=5\nexport tac=x\n"}
    },
    "a-comment-line": {"files": {".ci/x/comment.sh": "#!/bin/bash\n# seq 1 10 is a comment\n"}},
    "a-yaml-style-key": {
        "files": {".ci/x/yaml.sh": "#!/bin/bash\ncat <<'EOF'\nmytimeout: 3s\nEOF\n"}
    },
    "array-order-decides-the-first-hit": {"files": {".ci/x/order.sh": "#!/bin/bash\nbc | tac\n"}},
    "command-substitution-is-caught": {"files": {".ci/x/subst.sh": SUBST_FIXTURE}},
    "an-if-guarded-form": {"files": {".ci/x/ifguard.sh": IFGUARD_FIXTURE}},
    "run-sh-is-always-scanned": {"files": {"run.sh": "#!/bin/bash\nseq 1 5\n"}},
    "run-sh-absent": {"files": {".ci/x/clean.sh": "echo fine\n"}},
    "the-scripts-directory-is-scanned": {
        "files": {"scripts/dev/thing.sh": "#!/bin/bash\nmapfile -t x < f\n"}
    },
    "several-files-under-ci-with-no-colour": {
        "files": {
            ".ci/x/a.sh": "#!/bin/bash\nseq 1 3\n",
            ".ci/x/b.sh": "#!/bin/bash\ndc -e '1 2 + p'\n",
        },
        "ci": True,
    },
}

CASES = tuple(CASE_KW)


def fixture(where: pathlib.Path, name: str, *, subject: pathlib.Path) -> pathlib.Path:
    """A tree shaped like the repository, holding a COPY of the subject at its own depth."""
    root = where / "tree"
    (root / ".ci" / "rediacc_ci" / "security").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "security").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "x").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    holder = ".ci/scripts/security" if subject.suffix == ".sh" else ".ci/rediacc_ci/security"
    shutil.copy2(subject, root / holder / subject.name)
    for rel, content in CASE_KW[name]["files"].items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def run(subject: pathlib.Path, where: pathlib.Path, name: str) -> tuple[int, str, str]:
    """One subject, once, over this case's own tree."""
    root = fixture(where, name, subject=subject)
    holder = ".ci/scripts/security" if subject.suffix == ".sh" else ".ci/rediacc_ci/security"
    runner = "bash" if subject.suffix == ".sh" else "python3"
    env = None
    if CASE_KW[name].get("ci"):
        # A CURATED environment, not an overlay: the colour decision is the subject of this case and an inherited NO_COLOR would decide it instead.
        env = {"CI": "true", "PATH": os.environ.get("PATH", "")}
    proc = subprocess.run(
        [runner, str(root / holder / subject.name)],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def recorded(name: str) -> tuple[int, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str]:
    want = recorded(name)
    got = run(PORT, tmp_path / "port", name)
    labels = ("exit code", "stdout", "stderr")
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%r\n--- port ---\n%r" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_a_clean_tree_is_compatible() -> None:
    code, stdout, _ = recorded("a-clean-tree")
    assert code == 0
    assert "All commands are CI-compatible" in stdout


def test_direct_disallowed_commands_are_reported() -> None:
    code, _, stderr = recorded("a-direct-disallowed-command")
    assert code == 1
    assert "'seq' not available" in stderr
    assert "'tac' not available" in stderr
    assert "Found 2 CI-incompatible command(s)" in stderr


def test_the_three_shapes_that_are_not_findings() -> None:
    """An assignment, a comment and a YAML-looking key inside a heredoc all name a disallowed command and none of them runs one."""
    for name in ("a-variable-assignment", "a-comment-line", "a-yaml-style-key"):
        assert recorded(name)[0] == 0, name


def test_first_disallowed_command_in_array_order_wins() -> None:
    """`bc | tac` on one line: `bc` is checked before `tac` in `DISALLOWED`'s own array order and the twin `break`s on its first hit, so only `bc` is reported even though `tac` also appears and would independently match."""
    code, _, stderr = recorded("array-order-decides-the-first-hit")
    assert code == 1
    assert "'bc' not available" in stderr
    assert "'tac' not available" not in stderr
    assert "Found 1 CI-incompatible command(s)" in stderr


def test_command_substitution_and_if_guarded_forms_are_caught() -> None:
    """FIXED 2026-09-10, and these two recordings are what hold the fix in place. If either goes red the regex regressed on the port side, since the twin's side is frozen."""
    code, _, stderr = recorded("command-substitution-is-caught")
    assert code == 1
    assert "'shuf' not available" in stderr
    code, _, stderr = recorded("an-if-guarded-form")
    assert code == 1
    assert "'seq' not available" in stderr


def test_run_sh_and_the_scripts_directory_are_in_the_corpus() -> None:
    """`run.sh` is scanned by name and its absence is not an error; `scripts/` joined the corpus after a bash-4-only `mapfile` sat unreported in `scripts/ops/reset-bench.sh` for as long as anyone could remember."""
    code, _, stderr = recorded("run-sh-is-always-scanned")
    assert code == 1
    assert "run.sh:2" in stderr
    assert recorded("run-sh-absent")[0] == 0
    code, _, stderr = recorded("the-scripts-directory-is-scanned")
    assert code == 1
    assert "'mapfile' not available" in stderr


def test_ci_true_disables_colour_on_both_streams() -> None:
    code, stdout, stderr = recorded("several-files-under-ci-with-no-colour")
    assert code == 1
    assert "\033[" not in stdout, "CI=true must disable colour on stdout"
    assert "\033[" not in stderr, "CI=true must disable colour on stderr"


def test_no_recording_names_an_absolute_path() -> None:
    """ANTI-VACUITY on the normalisation claim in the module docstring. A recording that carried the recording host's tempdir would be unreadable anywhere else, and the claim that nothing is masked would be false rather than economical."""
    for name in CASES:
        for stream in recorded(name)[1:]:
            assert "/tmp/" not in stream, "%s carries an absolute path" % name
            assert str(ROOT) not in stream, "%s carries the checkout root" % name


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-REGRESSION, two independent plants. Each reintroduces one of the two bugs fixed on 2026-09-10 into the port alone and requires the recording to catch it.

    The recordings are of the FIXED twin, so each mutant must diverge from them; the bug creeping back into the port is exactly what that divergence would be. The mutants are throwaway copies at the depth `_console_root()` needs, and the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")

    # Plant A: regress Bug 1 (the `$(` escape) in the port only.
    plant_a = original.replace(
        r'_WIDE_RE = re.compile(r"(^[ \t]*|[|&;]\s*|\$\(|^[ \t]*if\s+)(" + _CMD_ALTERNATION + ")")',
        r'_WIDE_RE = re.compile(r"(^[ \t]*|[|&;]\s*|$\(|^[ \t]*if\s+)(" + _CMD_ALTERNATION + ")")',
    )
    assert plant_a != original, "the line Plant A targets is no longer present verbatim"

    # Plant B: regress Bug 2 (the missing `if` branch) in the narrow regex only, leaving the wide one alone.
    plant_b = original.replace(
        r'return re.compile(r"(^[ \t]*|[|&;]\s*|\$\(|^[ \t]*if\s+)" + re.escape(cmd) + r"\b")',
        r'return re.compile(r"(^[ \t]*|[|&;]\s*|\$\()" + re.escape(cmd) + r"\b")',
    )
    assert plant_b != original, "the line Plant B targets is no longer present verbatim"

    for label, mutated, name in (
        ("A", plant_a, "command-substitution-is-caught"),
        ("B", plant_b, "an-if-guarded-form"),
    ):
        where = tmp_path / ("mutant-" + label)
        holder = where / "src" / ".ci" / "rediacc_ci" / "security"
        holder.mkdir(parents=True)
        mutant = holder / "check_commands.py"
        mutant.write_text(mutated, encoding="utf-8")
        code, _, _ = run(mutant, where, name)
        assert recorded(name)[0] == 1, "the recorded corpus moved"
        assert code == 0, "Plant %s did not regress the port" % label

    compare(tmp_path / "good", "command-substitution-is-caught")
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
