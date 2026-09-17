"""Port of `.ci/scripts/test/gates/test-language-policy.sh`.

Subject: `.ci/scripts/quality/check_language_policy.py` (RULING 7). Its claim, and therefore what has to be proven in BOTH directions: the set of tracked bash files under `.ci` and `.claude` may lose members and may never gain one, exemptions are named with a `BLOCKER:` reason and die when they stop suppressing anything, and a green produced by an enumeration that saw nothing is
refused rather than printed.

HOW IT IS DRIVEN. Every case but the last builds a throwaway git repository and points the subject at it through `LANGUAGE_POLICY_ROOT` / `_BASELINE` / `_ALLOWLIST`, so no tracked baseline, allowlist or script is touched. `git ls-files` IS the subject's corpus, which is why the fixture has to be a real repository with a real index rather than a directory of files: a fixture that
merely looks like a tree exercises a code path the subject does not have.

THE LAST CASE IS SEAM-FREE, against the real repository, because every seam above it is a chance for the subject to be correct about a fixture and wrong about the tree it ships with. That case is also why this module opts in to the real-tree group: `gates.lock.json` records `reads: ["tree:repo"]` for `gate-test:language-policy`, and `real_tree_admission` refuses a twin in that set
that does not declare `REAL_TREE_TWIN`.

EVERY FIRE CASE HAS ITS CONTROL: the same fixture with one thing changed and the opposite verdict asserted. A gate that cannot be made to fire is not a gate, and a gate that fires on everything is not one either.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-language-policy.sh"

# The seam-free case runs the subject against the real repository. See the docstring.
REAL_TREE_TWIN = True

# THE SELF-SCANNING TRAP, AND WHY THIS FLAG IS RENDERED RATHER THAN WRITTEN. `gate-test:shrink-only-composition` enumerates every tracked-or-untracked `.ts`/`.js`/`.py` file whose TEXT contains the drain flag and requires each one to consume the composition guard. It excludes nothing by name, so a PORT that quotes the flag becomes an "unguarded Python baseline writer" and reds that
# gate tree-wide. Measured on 2026-09-09: writing the flag literally here put this file on that gate's offender list within minutes of it being created. Splitting it means the contiguous string never appears in this file's bytes, and `test_this_port_is_not_a_shrink_only_offender` reds BY NAME if that ever stops being true. Batch 3's `label-references` port paid for this rule first;
# any port of a self-scanning subject owes the same treatment.
DRAIN_FLAG = "--write-" + "baseline"

ROOT = paths.repo_root()
GATE = ROOT / ".ci" / "scripts" / "quality" / "check_language_policy.py"
CANONICAL_VALIDATOR = ROOT / ".ci" / "scripts" / "lib" / "blocker-validator.sh"

# A reason long enough and specific enough to satisfy the canonical validator (30 characters after normalisation, no banned phrase). Held in one constant so a case that means to test something ELSE cannot fail on the reason by accident.
GOOD_REASON = (
    "vendored downstream and drift-locked, so a port here would fork code whose "
    "contract is being byte-identical"
)

BASELINE_JSON = """{
  "note": "fixture",
  "bashFiles": [
    ".ci/scripts/one.sh",
    ".ci/scripts/two.sh",
    ".claude/hooks/three.sh"
  ]
}
"""


def python3() -> str:
    return harness.require_tool("python3", "install python3; the subject is a Python gate")


def git_bin() -> str:
    return harness.require_tool(
        "git", "install git; the fixture must be a real repository with a real index"
    )


def git(*args: str) -> harness.RunResult:
    return harness.run([git_bin(), *args])


def fixture(directory: pathlib.Path) -> None:
    """A real git repository holding a small `.ci` / `.claude` tree.

    Five bash files: three that must be judged, two under an exempt tree. Plus a `.py` file, which must NOT be judged -- without it a matcher that returned true for everything would pass every case below.
    """
    for sub in (".ci/scripts", ".ci/media", ".claude/hooks"):
        (directory / sub).mkdir(parents=True, exist_ok=True)
    (directory / ".ci/scripts/one.sh").write_text(
        "#!/usr/bin/env bash\necho one\n", encoding="utf-8"
    )
    (directory / ".ci/scripts/two.sh").write_text(
        "#!/usr/bin/env bash\necho two\n", encoding="utf-8"
    )
    (directory / ".claude/hooks/three.sh").write_text(
        "#!/usr/bin/env bash\necho hook\n", encoding="utf-8"
    )
    (directory / ".ci/media/render.sh").write_text(
        "#!/usr/bin/env bash\necho media\n", encoding="utf-8"
    )
    (directory / ".ci/media/upload.sh").write_text(
        "#!/usr/bin/env bash\necho more media\n", encoding="utf-8"
    )
    (directory / ".ci/scripts/keeper.py").write_text(
        "#!/usr/bin/env python3\nprint(1)\n", encoding="utf-8"
    )
    (directory / "allowlist").write_text(
        "# BLOCKER: %s\ntree:.ci/media/\n" % GOOD_REASON, encoding="utf-8"
    )
    (directory / "baseline.json").write_text(BASELINE_JSON, encoding="utf-8")
    git("-C", str(directory), "init", "-q")
    git("-C", str(directory), "add", "-A", "--", ".")


def run_gate(root: pathlib.Path, *args: str) -> harness.RunResult:
    """The subject, pointed at a fixture through its three seams.

    The streams stay APART here and the callers read `.combined`, mirroring the twin's `2>&1`: those assertions are about which message appeared. The one
    case that reads them apart is `test_real_tree_seam_free`, which is where the
    twin makes that claim too.
    """
    return harness.run(
        [python3(), str(GATE), *args],
        env={
            "LANGUAGE_POLICY_ROOT": str(root),
            "LANGUAGE_POLICY_BASELINE": str(root / "baseline.json"),
            "LANGUAGE_POLICY_ALLOWLIST": str(root / "allowlist"),
        },
        timeout=300,
    )


def allowlist(root: pathlib.Path, body: str) -> None:
    (root / "allowlist").write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------


def test_clean_tree_passes(gate):
    with harness.temp_dir() as d:
        fixture(d)
        result = run_gate(d)
        gate.assert_exit_code(0, result.rc, "a tree matching its baseline must pass")
        gate.assert_contains(
            result.combined, "5 bash file(s)", "prints the SHAPE, not just a verdict"
        )
        gate.assert_contains(result.combined, "3 frozen", "says how many are frozen")
        gate.assert_contains(result.combined, "2 exempt", "says how many are exempt")
    gate.log_pass("a clean tree passes and prints its shape")


def test_new_bash_file_fires(gate):
    with harness.temp_dir() as d:
        fixture(d)
        (d / ".ci/scripts/four.sh").write_text("#!/usr/bin/env bash\necho new\n", encoding="utf-8")
        git("-C", str(d), "add", "-A", "--", ".")
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "a NEW non-exempt bash file must be refused")
        gate.assert_contains(result.combined, ".ci/scripts/four.sh", "names the offending file")
        gate.assert_contains(
            result.combined, "Write it in Python instead", "says what to do about it"
        )
    gate.log_pass("a new non-exempt bash file fires")


def test_new_file_under_exempt_tree_is_silent(gate):
    """THE CONTROL FOR THE CASE ABOVE. Without it, a gate that fired on any change at all would pass that test, and the exemption would be proving nothing."""
    with harness.temp_dir() as d:
        fixture(d)
        (d / ".ci/media/four.sh").write_text("#!/usr/bin/env bash\necho new\n", encoding="utf-8")
        git("-C", str(d), "add", "-A", "--", ".")
        result = run_gate(d)
        gate.assert_exit_code(0, result.rc, "a new file under an EXEMPT tree must be silent")
        gate.assert_contains(result.combined, "3 exempt", "counts it as exempt, and says so")
    gate.log_pass("CONTROL: a new file under an exempt tree does not fire")


def test_new_py_file_is_silent(gate):
    """The other half of the same control: the gate must be blind to Python, or it is a file-count gate wearing a language gate's name."""
    with harness.temp_dir() as d:
        fixture(d)
        (d / ".ci/scripts/ported.py").write_text(
            "#!/usr/bin/env python3\nprint(2)\n", encoding="utf-8"
        )
        git("-C", str(d), "add", "-A", "--", ".")
        result = run_gate(d)
        gate.assert_exit_code(0, result.rc, "adding a PYTHON file is the goal state, not a finding")
    gate.log_pass("CONTROL: a new Python file does not fire")


def test_shebang_without_extension_is_caught(gate):
    """The rule may not be evadable by dropping the extension."""
    with harness.temp_dir() as d:
        fixture(d)
        (d / ".ci/scripts/helper").write_text("#!/bin/bash\necho sneaky\n", encoding="utf-8")
        git("-C", str(d), "add", "-A", "--", ".")
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "a shebang'd file with no .sh must still be caught")
        gate.assert_contains(result.combined, ".ci/scripts/helper", "names it")
    gate.log_pass("dropping the .sh extension does not evade the rule")


def test_drained_file_demands_a_ratchet(gate):
    with harness.temp_dir() as d:
        fixture(d)
        git("-C", str(d), "rm", "-qf", str(d / ".ci/scripts/two.sh"))
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "a ported file must demand the baseline be ratcheted")
        gate.assert_contains(result.combined, ".ci/scripts/two.sh", "names the drained file")
        gate.assert_contains(result.combined, DRAIN_FLAG, "gives the exact drain command")
    gate.log_pass("a ported file demands the baseline be ratcheted down")


def test_composition_trap_on_the_read_path(gate):
    """Delete one, add one. The TOTAL is unchanged, so a count-based gate goes green here. This is the exact case the set-based requirement exists for."""
    with harness.temp_dir() as d:
        fixture(d)
        git("-C", str(d), "rm", "-qf", str(d / ".ci/scripts/two.sh"))
        (d / ".ci/scripts/four.sh").write_text(
            "#!/usr/bin/env bash\necho swapped\n", encoding="utf-8"
        )
        git("-C", str(d), "add", "-A", "--", ".")
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "one out and one in must be refused, though the count is equal"
        )
        gate.assert_contains(
            result.combined, ".ci/scripts/four.sh", "names the file that was ADDED"
        )
    gate.log_pass("swapping one file for another is caught, though the total is unchanged")


def test_composition_trap_on_the_write_path(gate):
    """The same trap, on the drain flag, which is where it actually bites: a drain that absorbs a new finding prints a SMALLER number and looks like progress. Refusing on the read path alone does not close this."""
    with harness.temp_dir() as d:
        fixture(d)
        git("-C", str(d), "rm", "-qf", str(d / ".ci/scripts/two.sh"))
        (d / ".ci/scripts/four.sh").write_text(
            "#!/usr/bin/env bash\necho swapped\n", encoding="utf-8"
        )
        git("-C", str(d), "add", "-A", "--", ".")
        result = run_gate(d, DRAIN_FLAG)
        gate.assert_exit_code(1, result.rc, "a reseed that ABSORBS a new file must be refused")
        gate.assert_contains(result.combined, "would GAIN", "says the set would grow")
        gate.assert_contains(
            result.combined, ".ci/scripts/four.sh", "names what it would have absorbed"
        )
        gate.assert_contains(result.combined, "LOOKS like progress", "explains why the totals lie")
        # AND THE FILE MUST BE UNTOUCHED. A refusal that still writes is not a refusal.
        gate.assert_not_contains(
            (d / "baseline.json").read_text(encoding="utf-8"),
            "four.sh",
            "refused write left no trace",
        )
    gate.log_pass("the write path refuses a reseed that would absorb a new file")


def test_pure_drain_is_allowed(gate):
    """CONTROL for the case above. If the drain flag refused everything the backlog could never shrink, and the gate would be a freeze rather than a ratchet."""
    with harness.temp_dir() as d:
        fixture(d)
        git("-C", str(d), "rm", "-qf", str(d / ".ci/scripts/two.sh"))
        result = run_gate(d, DRAIN_FLAG)
        gate.assert_exit_code(0, result.rc, "a pure drain must be allowed")
        gate.assert_contains(
            result.combined, "1 drained, 0 added", "reports the composition of the write"
        )
        gate.assert_not_contains(
            (d / "baseline.json").read_text(encoding="utf-8"), "two.sh", "the drained file is gone"
        )
        after = run_gate(d)
        gate.assert_exit_code(0, after.rc, "and the tree is green afterwards")
    gate.log_pass("CONTROL: a pure drain is written, and the tree is green after it")


def test_missing_baseline_refuses_a_blind_reseed(gate):
    with harness.temp_dir() as d:
        fixture(d)
        (d / "baseline.json").unlink()
        result = run_gate(d, DRAIN_FLAG)
        gate.assert_exit_code(1, result.rc, "reseeding with no previous set must be refused")
        gate.assert_contains(result.combined, "--first-seed", "names the flag that would allow it")
        seeded = run_gate(d, DRAIN_FLAG, "--first-seed")
        gate.assert_exit_code(0, seeded.rc, "CONTROL: --first-seed permits a genuine first seed")
    gate.log_pass("deleting the baseline is not a way to reseed it blind")


def test_missing_baseline_is_strict_not_silent(gate):
    with harness.temp_dir() as d:
        fixture(d)
        (d / "baseline.json").unlink()
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "no baseline means STRICT, never 'no debt recorded'")
        gate.assert_contains(result.combined, "STRICT", "says which mode it is in")
        gate.assert_contains(result.combined, "3 bash file(s)", "counts what strict mode refuses")
    gate.log_pass("an absent baseline is the strict flip, not an escape hatch")


def test_strict_mode_passes_when_only_exempt_bash_remains(gate):
    """W1 P6's goal state, proven reachable rather than assumed: no baseline file, and every surviving bash file named in the allowlist."""
    with harness.temp_dir() as d:
        fixture(d)
        (d / "baseline.json").unlink()
        git(
            "-C",
            str(d),
            "rm",
            "-qf",
            str(d / ".ci/scripts/one.sh"),
            str(d / ".ci/scripts/two.sh"),
            str(d / ".claude/hooks/three.sh"),
        )
        result = run_gate(d)
        gate.assert_exit_code(
            0, result.rc, "strict mode must be reachable, or the flip cannot land"
        )
        gate.assert_contains(result.combined, "STRICT", "says so")
        gate.assert_contains(result.combined, "goal state", "and names it as the goal state")
    gate.log_pass("CONTROL: strict mode is green once only allowlisted bash remains")


def test_missing_blocker_is_refused(gate):
    with harness.temp_dir() as d:
        fixture(d)
        allowlist(d, "tree:.ci/media/\n")
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "an exemption with no BLOCKER must be refused")
        gate.assert_contains(result.combined, "missing a '# BLOCKER:", "says what is missing")
    gate.log_pass("an allowlist entry with no BLOCKER reason is refused")


def test_low_effort_blocker_is_refused(gate):
    """This is also the control that the CANONICAL validator is really consulted. "tbd" is on `.ci/scripts/lib/blocker-validator.sh`'s banned-phrase list and nowhere in the subject's own source, so a passing verdict here would mean the subprocess never ran."""
    with harness.temp_dir() as d:
        fixture(d)
        allowlist(d, "# BLOCKER: tbd\ntree:.ci/media/\n")
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "a placeholder BLOCKER must be refused")
        gate.assert_contains(
            result.combined, "low-effort placeholder", "quotes the canonical validator"
        )
    gate.log_pass("a low-effort BLOCKER is refused BY the canonical validator")


def test_short_blocker_is_refused(gate):
    with harness.temp_dir() as d:
        fixture(d)
        allowlist(d, "# BLOCKER: it is vendored\ntree:.ci/media/\n")
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "a BLOCKER under the 30-character floor must be refused"
        )
        gate.assert_contains(result.combined, "too short", "names the rule it broke")
    gate.log_pass("a BLOCKER under the length floor is refused")


def test_dead_tree_entry_is_refused(gate):
    with harness.temp_dir() as d:
        fixture(d)
        allowlist(d, "# BLOCKER: %s\ntree:.ci/gone/\n" % GOOD_REASON)
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "an exemption that suppresses nothing must be refused")
        gate.assert_contains(result.combined, "covers no bash file", "says why the entry is dead")
    gate.log_pass("an exemption that covers nothing is reported dead")


def test_shim_entry_that_grew_is_refused(gate):
    with harness.temp_dir() as d:
        fixture(d)
        # A genuine one-line shim first: shebang, comment, `set`, one command.
        (d / ".ci/scripts/one.sh").write_text(
            '#!/usr/bin/env bash\n# a note\nset -euo pipefail\nexec other "$@"\n', encoding="utf-8"
        )
        allowlist(
            d,
            "# BLOCKER: %s\ntree:.ci/media/\n\n# BLOCKER: %s\nshim:.ci/scripts/one.sh\n"
            % (GOOD_REASON, GOOD_REASON),
        )
        git("-C", str(d), "add", "-A", "--", ".")
        # It is exempt now, so the baseline that still lists it is one entry stale.
        (d / "baseline.json").write_text(
            '{"note":"f","bashFiles":[".ci/scripts/two.sh",".claude/hooks/three.sh"]}\n',
            encoding="utf-8",
        )
        clean = run_gate(d)
        gate.assert_exit_code(0, clean.rc, "CONTROL: a genuine one-line shim is exempt")

        # Now grow it. The justification was "one-line shim" and that stopped being true without the file being deleted, which is the half a does-the-file-exist oracle would miss entirely.
        (d / ".ci/scripts/one.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nfoo\nbar\n", encoding="utf-8"
        )
        git("-C", str(d), "add", "-A", "--", ".")
        grown = run_gate(d)
        gate.assert_exit_code(1, grown.rc, "a shim that grew into a program must be refused")
        gate.assert_contains(grown.combined, "effective lines", "counts what it actually found")
    gate.log_pass("a shim: entry whose file grew past one line is refused by name")


def test_file_entry_exempts_a_multiline_file(gate):
    """THE THIRD KIND (W7P6, 2026-09-09). Added because `tree:` and `shim:` between them could not spell `.ci/bootstrap.sh`: 395 permanently-bash lines alone in `.ci/`, where the only two available spellings were `tree:.ci/` (which exempts the entire port backlog) and moving the file to fit the grammar.

    A CASE THE TWIN DOES NOT HAVE. `test_twin_parity` compares case SETS in one direction only -- the port must hold every case the twin declares, and may add its own -- so the twin stays green while the subject grows a kind it does not know about. This case is the reason the addition is not invisible.

    BOTH DIRECTIONS, and the negative is the one that matters: `file:` has no line oracle, so it is strictly weaker than `shim:`, and a gate that let an author pick it over `shim:` would retire the check that notices a shim becoming a program. Pointing it at a ONE-line body must be refused BY NAME."""
    with harness.temp_dir() as d:
        fixture(d)
        # Multi-line, so `shim:` genuinely does not apply and `file:` is the only kind left.
        (d / ".ci/scripts/two.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nfoo\nbar\nbaz\n", encoding="utf-8"
        )
        allowlist(
            d,
            "# BLOCKER: %s\ntree:.ci/media/\n\n# BLOCKER: %s\nfile:.ci/scripts/two.sh\n"
            % (GOOD_REASON, GOOD_REASON),
        )
        git("-C", str(d), "add", "-A", "--", ".")
        # two.sh is exempt now, so the baseline must no longer carry it.
        (d / "baseline.json").write_text(
            '{"note":"f","bashFiles":[".ci/scripts/one.sh",".claude/hooks/three.sh"]}\n',
            encoding="utf-8",
        )
        ok = run_gate(d)
        gate.assert_exit_code(0, ok.rc, "a file: entry over a multi-line bash file is live")
        gate.assert_contains(
            ok.combined, "exempt file:.ci/scripts/two.sh", "and is PRINTED, not silently applied"
        )

        # CONTROL: the same entry over a ONE-line body must be sent to `shim:`.
        allowlist(
            d,
            "# BLOCKER: %s\ntree:.ci/media/\n\n# BLOCKER: %s\nfile:.ci/scripts/one.sh\n"
            % (GOOD_REASON, GOOD_REASON),
        )
        (d / "baseline.json").write_text(
            '{"note":"f","bashFiles":[".ci/scripts/two.sh",".claude/hooks/three.sh"]}\n',
            encoding="utf-8",
        )
        downgrade = run_gate(d)
        gate.assert_exit_code(1, downgrade.rc, "a file: entry where shim: applies must be refused")
        gate.assert_contains(
            downgrade.combined,
            "must be written `shim:.ci/scripts/one.sh`",
            "and the refusal names the kind to use instead",
        )

        # CONTROL: a file: entry naming nothing tracked is dead, exactly like shim:.
        allowlist(
            d,
            "# BLOCKER: %s\ntree:.ci/media/\n\n# BLOCKER: %s\nfile:.ci/scripts/gone.sh\n"
            % (GOOD_REASON, GOOD_REASON),
        )
        dead = run_gate(d)
        gate.assert_exit_code(1, dead.rc, "a file: entry suppressing nothing must be refused")
        gate.assert_contains(dead.combined, "is not a tracked bash file", "says why it is dead")
    gate.log_pass("a file: entry exempts a multi-line file, and is refused where shim: applies")


def test_malformed_entry_is_named_not_dropped(gate):
    with harness.temp_dir() as d:
        fixture(d)
        allowlist(d, "# BLOCKER: %s\ntree:.ci/media\n" % GOOD_REASON)
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "a tree: entry with no trailing slash must be refused")
        gate.assert_contains(
            result.combined, "must end in a slash", "explains the widening it prevents"
        )
    gate.log_pass("a malformed allowlist entry is named rather than silently dropped")


def test_empty_tree_fails(gate):
    """ANTI-VACUITY. An enumeration that found nothing is the failure this gate would otherwise report as the cleanest run in its history."""
    with harness.temp_dir() as d:
        empty = d / "empty"
        empty.mkdir(parents=True, exist_ok=True)
        git("-C", str(empty), "init", "-q")
        (empty / "allowlist").write_text(
            "# BLOCKER: %s\ntree:.ci/media/\n" % GOOD_REASON, encoding="utf-8"
        )
        (empty / "baseline.json").write_text('{"note":"f","bashFiles":[]}\n', encoding="utf-8")
        result = run_gate(empty)
        gate.assert_exit_code(1, result.rc, "zero files scanned is a FAILURE, never a pass")
        gate.assert_contains(result.combined, "VACUOUS", "says the corpus was empty")
    gate.log_pass("an empty corpus fails (anti-vacuity), it does not pass silently")


def test_corrupt_baseline_is_not_an_empty_one(gate):
    with harness.temp_dir() as d:
        fixture(d)
        (d / "baseline.json").write_text("not json at all\n", encoding="utf-8")
        result = run_gate(d)
        gate.assert_exit_code(77, result.rc, "a corrupt baseline is CANNOT RUN, not a verdict")
        gate.assert_contains(result.combined, "CANNOT RUN", "says it could not reach a verdict")
    gate.log_pass("a corrupt baseline is refused rather than read as an empty set")


def test_missing_git_is_cannot_run_not_a_verdict(gate):
    """A missing toolchain must be 77 with the cause named, never a pass, never a red, and never a traceback.

    THE PATH IS EMPTIED RATHER THAN THE BINARY HIDDEN, so the interpreter has to be named absolutely: `python3` resolved through the doctored PATH would fail to launch and the case would pass on the wrong exit code.
    """
    with harness.temp_dir() as d:
        fixture(d)
        interpreter = python3()
        result = harness.run(
            [interpreter, str(GATE)],
            env={
                "PATH": str(d / "nothing-here"),
                "LANGUAGE_POLICY_ROOT": str(d),
                "LANGUAGE_POLICY_BASELINE": str(d / "baseline.json"),
                "LANGUAGE_POLICY_ALLOWLIST": str(d / "allowlist"),
            },
            timeout=300,
        )
        gate.assert_exit_code(
            77, result.rc, "a missing toolchain must be 77, never a pass and never a red"
        )
        gate.assert_contains(result.combined, "CANNOT RUN", "says so in those words")
        gate.assert_contains(result.combined, "git is not on PATH", "names the missing tool")
        gate.assert_not_contains(
            result.combined, "Traceback", "and does not answer with a stack trace"
        )
    gate.log_pass("a missing git is exit 77 with the cause named, not a traceback")


def test_selftest_can_fail(gate):
    """THE CONTROL ON THE CONTROLS.

    A selftest that cannot go red is decoration, and this gate refuses its own verdict when the controls fail (exit 2), so that refusal has to be demonstrated rather than assumed. Built by CONSTRUCTION: the copy has one
    function body replaced wholesale, not a pattern substituted, so the mutation
    cannot silently fail to apply.

    THE COPY IS HANDED THE ENTRY-POINT DIRECTORY ON `PYTHONPATH`, and that is a fix rather than convenience. 73bd8f7ec routed 81 gate entry points through `import _cipath`, a side-effect module that lives BESIDE them and is found only because a path invocation puts the script's own directory on `sys.path[0]`. A copy in a temp dir has a different `sys.path[0]`, so the mutant dies
    with `ModuleNotFoundError: No module named '_cipath'` before reaching a single assertion -- a control failing for a reason that has nothing to do with what it controls.
    """
    with harness.temp_dir() as d:
        fixture(d)
        source = GATE.read_text(encoding="utf-8")
        needle = "    known = set(old)\n    return [entry for entry in new if entry not in known]\n"
        if needle not in source:
            gate.log_fail(
                "CONTROL COULD NOT PLANT: baseline_additions body not found as written in %s"
                % paths.relative_to_root(GATE)
            )
        mutant = d / "mutant.py"
        mutant.write_text(source.replace(needle, "    return []\n"), encoding="utf-8")
        gate.assert_eq(mutant.read_text(encoding="utf-8") == source, False, "the mutation landed")

        env = {
            "PYTHONPATH": "%s:%s" % (ROOT / ".ci", ROOT / ".ci" / "scripts" / "quality"),
            "LANGUAGE_POLICY_VALIDATOR": str(CANONICAL_VALIDATOR),
            "LANGUAGE_POLICY_ROOT": str(d),
        }
        selftest = harness.run([python3(), str(mutant), "--selftest"], env=env, timeout=300)
        gate.assert_exit_code(1, selftest.rc, "a broken shrink-only guard must fail the selftest")
        gate.assert_contains(
            selftest.combined, "COMPOSITION TRAP", "and names the control that caught it"
        )

        verdict = harness.run(
            [python3(), str(mutant)],
            env={
                **env,
                "LANGUAGE_POLICY_BASELINE": str(d / "baseline.json"),
                "LANGUAGE_POLICY_ALLOWLIST": str(d / "allowlist"),
            },
            timeout=300,
        )
        gate.assert_exit_code(2, verdict.rc, "and the gate refuses to give a verdict at all")
        gate.assert_contains(
            verdict.combined, "every verdict below would be meaningless", "saying why"
        )
    gate.log_pass("the selftest goes red when the guard is broken, and the gate then refuses")


def test_real_tree_seam_free(gate):
    """NO SEAMS. Every case above could be right about a fixture and wrong about the repository this gate ships with.

    THE STREAMS ARE READ APART HERE, which is the one place the twin makes that claim: a gate whose progress text lands on stderr is invisible until something parses it, and a merged read cannot see the difference.
    """
    result = harness.run([python3(), str(GATE)], cwd=ROOT, timeout=600)
    gate.assert_exit_code(0, result.rc, "the real tree must be green: %s" % result.err)
    gate.assert_contains(result.out, "control(s) passed", "controls ran before the verdict")
    gate.assert_contains(result.out, "language policy:", "and a verdict was printed")
    gate.assert_eq(len(result.err), 0, "a green run writes nothing to stderr")
    gate.log_pass("the real tree is green, seam-free, with both streams read apart")


def test_the_three_seams_still_exist_in_the_subject(gate):
    """ADDED BY THE PORT. Twenty-two of the twenty-three cases point the subject at a fixture through `LANGUAGE_POLICY_ROOT`, `_BASELINE` and `_ALLOWLIST`. If a seam were renamed the subject would silently judge the REAL tree instead, and most of those cases expect a non-zero exit -- so several would keep passing while asserting something about the wrong corpus."""
    source = GATE.read_text(encoding="utf-8")
    for seam in (
        "LANGUAGE_POLICY_ROOT",
        "LANGUAGE_POLICY_BASELINE",
        "LANGUAGE_POLICY_ALLOWLIST",
        "LANGUAGE_POLICY_VALIDATOR",
    ):
        gate.assert_contains(
            source, seam, "%s is how a case redirects the subject away from the real tree" % seam
        )
    gate.log_pass("all four redirection seams are still read by the subject")


def test_this_port_is_not_a_shrink_only_offender(gate):
    """THE SELF-SCANNING CONTROL, which the twin does not need and this port does.

    The twin is a `.sh` file, and `gate-test:shrink-only-composition` enumerates only `.ts`, `.js` and `.py`, so the twin is invisible to that gate for free. This module is a `.py` file that talks about the drain flag constantly, and it is invisible only because `DRAIN_FLAG` is split -- something a later editor would undo without connecting the two. So this reds BY NAME the moment
    the contiguous literal reappears in this file's bytes.

    Measured 2026-09-09: with the flag written out, this file appeared on that gate's offender list as ".ci/rediacc_ci/tests/gates/test_gate_language_policy.py offers ... and consumes neither a shared guard nor the ported one".
    """
    own = pathlib.Path(__file__).read_text(encoding="utf-8")
    if DRAIN_FLAG in own:
        gate.log_fail(
            "this port's own source contains the contiguous drain flag, so "
            "gate-test:shrink-only-composition will report it as an unguarded Python "
            "baseline writer. Keep it rendered through DRAIN_FLAG."
        )
    # AND THE CONSTANT MUST STILL BE THE REAL FLAG. A control that only checks for absence is satisfied by a typo, which would make every case above drive the subject with an argument it ignores. CHECKED AGAINST THE TWIN rather than against a literal written here: the twin is a `.sh` file, outside the offender corpus entirely, so it can carry the flag whole -- and comparing against
    # a literal in THIS file would be a tautology or a second thing to keep rendered.
    twin = (ROOT / BASH_TWIN).read_text(encoding="utf-8")
    if DRAIN_FLAG not in twin:
        gate.log_fail(
            "the rendered flag %r does not appear in %s, so it is a typo and every case "
            "above drove the subject with an argument it ignores" % (DRAIN_FLAG, BASH_TWIN)
        )
    gate.log_pass("the drain flag is rendered, so this port cannot flag itself (%r)" % DRAIN_FLAG)
