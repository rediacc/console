"""The bump-none decision must EMIT ITS SIGNAL, and only on the skip path.

Ported from `.ci/scripts/quality/check-release-bump-skip.sh`, retired in W7 P5; see `rediacc_ci.quality.__init__` for the phase-5 decision that retired the twin.

WHY THIS EXISTS. Two gates already cover neighbouring ground and neither touches this: `rediacc_ci.security.ci_workflow_invariants` asserts the WIRING in ci.yml (that the decision is declared once, threaded, and not re-decided in finalize-release-sentinel), and `test_gate_skip_release_channel_pointer.py` proves the UPLOAD script's guard branches correctly. Nothing drove
`dispatch-release.sh`'s own
decision branch, so "Finalize Release emitted the skip signal for the right reason" was unobservable by construction. Release gates could say a release succeeded or was absent; they could not say WHY.

That distinction is not academic here. A bump-none merge and a broken decision both produce "no release". They are indistinguishable from the outside, and the only thing that tells them apart is the signal this script emits:

    release SKIPPED: #576 carries 'bump-none'
    ::notice title=Release skipped::...earns no release...
    decision: skip

Observed live on 2026-08-26 (run 32961178698, job 98165911876) after merging PR #576. This gate keeps that observable.

THE DIRECTION THAT MATTERS MOST is not "does it skip" -- it is that the signal must NOT appear when the commit is releasing. A skip notice on a releasing path would tell a reader the opposite of what happened, and `dispatch-release.sh`'s whole doctrine is that a silently withheld release is worse than an extra one.

HERMETIC: `gh` is shimmed, so this never touches the network and can run in any lane. WHAT IT CANNOT SEE: whether the workflow actually CALLS the script (that is `rediacc_ci.security.ci_workflow_invariants`'s subject), and whether a real run's log retains the line (only a live bump-none merge shows that).

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THIS GATE MERGES STDOUT AND STDERR, AND THAT IS DELIBERATE RATHER THAN LAZY.
`rediacc_ci.proc.run` refuses to merge -- its docstring says "never merges streams", for the 2026-09-06 stream-swap reason recorded in `.ci/scripts/lib/emit-advisory.sh:22-52` -- so this module reaches for `subprocess` directly instead of quietly weakening the shared helper. The reason is that the SUBJECT here is a blob: the twin runs `bash "$SUT" --decide-only 2>&1` and every
assertion below is a `grep` over the combined text, because `dispatch-release.sh` splits the same decision across both streams (the notice on stdout, the reasoning on stderr) and an assertion on one stream alone would pass
while the signal went to the other. Reproducing the merge is reproducing the
contract; using `proc.run` and concatenating afterwards would produce a DIFFERENT interleaving, which the failure path prints as its first six lines and the shadow comparator would then read as a genuine finding difference.

THE GH SHIM IS BUILT AS A FILE, NOT AS A PYTHON MOCK. The subject is a bash script that resolves `gh` through PATH; a mock inside this process would test nothing about it. The shim's text is carried over byte for byte, including the heredoc quoting, because `rows` reaches it as heredoc BODY and a change in quoting would start expanding `$` in a label.

THE TWIN SOURCES `.ci/scripts/lib/common.sh` AND THE PORT DOES NOT, which is the one archaeology token this file would otherwise drop. Its two `# shellcheck
source=` / `# BLOCKER:` lines record that `log_error`, `log_info` and
`get_repo_root` are used throughout, and that the BLOCKER exists because `check-python-gate-deps` and shellcheck would otherwise read the source line as unused. In the port `log_*` comes from `rediacc_ci.log` and the root from `rediacc_ci.paths.repo_root()`, so there is no source line and no suppression to justify -- but the FACT that these three helpers are the gate's only
dependency on the shared bash library is what makes the twin cheap to retire, and that is worth keeping.

THE EMPTY-ROWS CASE IS NOT AN EMPTY SHIM. `printf '%s\\n' "$rows"` with an empty `rows` writes ONE BLANK LINE, so case 5 ("no merged PR at all") drives the script
with a single empty line of API output rather than with nothing. That is a real
difference -- a script that reads line-by-line sees one iteration -- and it is reproduced exactly rather than tidied into an empty body.
"""

import os
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, plant

SCRIPT_ENV = "RELEASE_DECIDE_SCRIPT"
DEFAULT_SCRIPT = ".ci/scripts/ci/dispatch-release.sh"

# The environment the subject is driven under. GITHUB_SHA is the real sha of the 2026-08-26 merge the gate is written from, kept so that a reader who greps for it lands on the incident rather than on a placeholder.
DRIVE_ENV = {
    "GITHUB_REPOSITORY": "rediacc/console",
    "GITHUB_SHA": "1c006e538fe3d33eeb280b809140b0d477a280db",
}

# The literal the whole gate is about. Kept as one constant because it appears as both the needle of case 1 and the anti-needle of cases 2 through 5, and two spellings of it would let one direction silently stop asserting.
SKIP_SIGNAL = "release SKIPPED"

# How many lines of the subject's output a failure report shows. `head -6` in the twin: enough to see the decision, short enough that five failures do not bury the summary.
FAILURE_EXCERPT_LINES = 6


def _write_shim(bin_dir: pathlib.Path, rows: str) -> None:
    """The `gh` the subject will find on PATH.

    `rows` is what the API would return, one PR per line as "<number> <labels,csv>"; the literal FAIL makes the shim exit non-zero.
    """
    shim = bin_dir / "gh"
    if rows == "FAIL":
        shim.write_text('#!/bin/bash\necho "api exploded" >&2\nexit 1\n', encoding="utf-8")
    else:
        shim.write_text("#!/bin/bash\ncat <<'ROWS'\n%s\nROWS\n" % rows, encoding="utf-8")
    shim.chmod(0o755)


def drive(work: pathlib.Path, script: pathlib.Path, rows: str) -> tuple[int, str]:
    """Run the REAL script with a shimmed gh. Returns (exit code, merged output)."""
    bin_dir = work / "bin"
    if bin_dir.exists():
        for child in bin_dir.iterdir():
            child.unlink()
    bin_dir.mkdir(parents=True, exist_ok=True)
    _write_shim(bin_dir, rows)

    env = dict(os.environ)
    env["PATH"] = "%s:%s" % (bin_dir, env.get("PATH", ""))
    env.update(DRIVE_ENV)
    env["GITHUB_OUTPUT"] = str(work / "out.txt")

    # See the port notes: the merge is the contract, not a shortcut.
    completed = subprocess.run(
        ["bash", str(script), "--decide-only"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    # `.rstrip("\n")` MIRRORS `$(...)`, and it is a fix rather than a tidy-up.
    # The twin captures with `res="$(drive "$rows")"`, and command substitution
    # strips every trailing newline. Without this the port's `out` keeps the SUT's final newline, `out.split("\n")` yields a trailing empty element, and the failure excerpt prints one extra six-space line per driven case that the twin never prints. Measured 2026-09-07 under W7 P4 by pointing RELEASE_DECIDE_SCRIPT at a copy that could not source its own lib: both sides exited 1 with
    # the same findings, and stderr differed by exactly five blank continuation lines. It only shows on the excerpt path, which fires when dispatch-release.sh is already broken -- the one moment the two implementations must still be readable as the same gate.
    return completed.returncode, completed.stdout.rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    if argv and argv[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    script_name = os.environ.get(SCRIPT_ENV, DEFAULT_SCRIPT)
    script = root / script_name
    if not script.is_file():
        log.error(
            "release-bump-skip: %s does not exist. Nothing to drive is not a clean tree -- "
            "if the decision moved, retarget this gate deliberately." % script_name
        )
        return 1

    failed = False

    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)

        def expect(label: str, rows: str, want: str, needle: str, anti: str) -> None:
            nonlocal failed
            code, out = drive(work, script, rows)
            if ("decision: %s" % want) not in out:
                log.error("release-bump-skip: %s -- expected 'decision: %s', got:" % (label, want))
                for line in out.split("\n")[:FAILURE_EXCERPT_LINES]:
                    print("      %s" % line, file=sys.stderr)
                failed = True
                return
            if needle and needle not in out:
                log.error("release-bump-skip: %s -- the signal is missing: %s" % (label, needle))
                failed = True
                return
            if anti and anti in out:
                log.error(
                    "release-bump-skip: %s -- emitted a signal it must NOT: %s" % (label, anti)
                )
                failed = True
                return
            log.info("  ok  %s (rc=%d)" % (label, code))

        log.info("release-bump-skip: driving the real decision through every branch")

        # 1. The case the label exists for: the signal must be emitted, and it must NAME the PR and the label, because "no release" without a reason is the ambiguity this gate exists to remove.
        expect(
            "bump-none only -> skips, and says why",
            "576 ci,bump-none",
            "skip",
            "release SKIPPED: #576 carries 'bump-none'",
            "",
        )

        # 2. THE DIRECTION THAT MATTERS MOST. A releasing commit must not carry a
        #    skip notice; a reader would conclude the opposite of what happened.
        expect(
            "no skip label -> releases, and emits NO skip signal",
            "576 ci,documentation",
            "release",
            "",
            SKIP_SIGNAL,
        )

        # 3. Mixed: one PR asks to skip, another does not. Releasing is correct, and the skip signal must still be withheld.
        expect(
            "mixed labels -> releases, still no skip signal",
            "576 ci,bump-none\n577 ci",
            "release",
            "",
            SKIP_SIGNAL,
        )

        # 4. Fail OPEN. An unreadable API must release rather than silently withhold -- the script's stated doctrine -- and must not claim a skip.
        expect(
            "API failure -> releases (fails open), no skip signal",
            "FAIL",
            "release",
            "",
            SKIP_SIGNAL,
        )

        # 5. No merged PR at all (direct push): releases, no skip signal.
        expect("no merged PR -> releases, no skip signal", "", "release", "", SKIP_SIGNAL)

        # ANTI-VACUITY. If the shim could not drive the script at all, every `expect` above would have failed loudly -- but a future refactor could make the script exit 0 printing nothing, and the "decision: release" test would then fail rather than pass, so the suite stays honest. The control here is the opposite risk: prove the harness can still produce a SKIP, so case 2's "no
        # skip signal" is not passing because the signal is unreachable for everyone.
        _code, control = drive(work, script, "999 bump-none")
        if SKIP_SIGNAL not in control:
            log.error(
                "release-bump-skip: CONTROL FAILED -- the harness cannot produce a skip "
                "signal at all, so every 'must not emit' assertion above is vacuous."
            )
            failed = True

    if failed:
        log.error("release-bump-skip FAILED")
        return 1

    log.info(
        "release-bump-skip: the skip signal is emitted on the skip path and withheld on all "
        "four releasing paths"
    )
    log.info("  Blind spot: does not prove the workflow CALLS this script (that is")
    log.info("  rediacc_ci.security.ci_workflow_invariants), nor that a live run's log")
    log.info("  retains the")
    log.info("  line -- only a real bump-none merge shows that.")
    return 0


# A stand-in for `dispatch-release.sh` that decides the same way it does, used by the selftest as the thing every plant mutates. Written out rather than copied
# from the real script, because a fixture built by copying is a fixture that
# stops testing the day the original is reworded -- and because mutating a REAL release script on disk to prove a gate fires is exactly the kind of control `check-control-vacuity.sh` refuses.
_FAKE_SUBJECT = r"""#!/bin/bash
set -euo pipefail
rows="$(gh api whatever 2>/dev/null || true)"
if grep -q 'bump-none' <<<"$rows" && ! grep -qv 'bump-none' <<<"$(grep -c . <<<"$rows")"; then :; fi
skip=false
number=""
while IFS=' ' read -r num labels; do
    [ -n "${num:-}" ] || continue
    case ",${labels:-}," in
        *,bump-none,*) skip=true; number="$num" ;;
        *) skip=false; number=""; break ;;
    esac
done <<<"$rows"
if [ "$skip" = true ]; then
    echo "release SKIPPED: #${number} carries 'bump-none'"
    echo "::notice title=Release skipped::this commit earns no release"
    echo "decision: skip"
else
    echo "decision: release"
fi
"""


def selftest() -> int:
    """Prove the gate fires on a broken decision and stays quiet on a working one.

    THE PLANT IS IN THE SUBJECT, NOT IN THE GATE, which is the only place it can be: this gate's whole claim is about what `dispatch-release.sh` prints, so a control that mutated the gate would prove nothing about that claim. The `RELEASE_DECIDE_SCRIPT` seam exists for exactly this and is used for nothing
    else.

    The fake subject is asserted to be a WORKING one first. Without that, every plant below would "fire" against a subject that was broken to begin with, and the suite would be green while testing nothing -- the same vacuity the gate itself is written against.
    """
    ctl = Controls("release-bump-skip", floor=7, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        def run_against(text: str) -> int:
            subject = base / "subject.sh"
            subject.write_text(text, encoding="utf-8")
            subject.chmod(0o755)
            saved = dict(os.environ)
            os.environ[SCRIPT_ENV] = str(subject)
            try:
                return main([])
            finally:
                os.environ.clear()
                os.environ.update(saved)

        ctl.check("CONTROL: a correct decision script passes", run_against(_FAKE_SUBJECT), 0)

        # PLANT 1, the direction that matters most: the skip notice is emitted on every path, so a releasing commit tells its reader the opposite of what happened. Cases 2 to 5 must all fire.
        always = plant(
            _FAKE_SUBJECT,
            'else\n    echo "decision: release"',
            'else\n    echo "release SKIPPED: #0 carries \'bump-none\'"\n    echo "decision: release"',
        )
        ctl.check("PLANT: a skip signal on the releasing path is caught", run_against(always), 1)

        # PLANT 2: the skip path goes silent. The decision is still right, so a gate that only checked `decision:` would pass -- which is the whole reason the needle exists.
        silent = plant(
            _FAKE_SUBJECT, "    echo \"release SKIPPED: #${number} carries 'bump-none'\"\n", ""
        )
        ctl.check("PLANT: a silent skip path is caught", run_against(silent), 1)

        # PLANT 3: the signal is emitted but stops naming the PR, so "no release" loses the reason again.
        unnamed = plant(
            _FAKE_SUBJECT,
            "echo \"release SKIPPED: #${number} carries 'bump-none'\"",
            'echo "release SKIPPED"',
        )
        ctl.check("PLANT: a skip signal that names no PR is caught", run_against(unnamed), 1)

        # PLANT 4: fails CLOSED instead of open. An unreadable API must release.
        closed = plant(
            _FAKE_SUBJECT,
            'rows="$(gh api whatever 2>/dev/null || true)"',
            'rows="$(gh api whatever 2>/dev/null)" || { echo "decision: skip"; exit 0; }',
        )
        ctl.check("PLANT: failing closed on an API error is caught", run_against(closed), 1)

        # PLANT 5: the subject prints nothing at all. This is the shape the twin's own anti-vacuity note calls out -- "a future refactor could make the script exit 0 printing nothing" -- and it must be a refusal, not a pass.
        ctl.check(
            "VACUITY: a subject that prints nothing is refused",
            run_against("#!/bin/bash\nexit 0\n"),
            1,
        )

        # And the seam's own refusal: a subject that is not there at all.
        saved = dict(os.environ)
        os.environ[SCRIPT_ENV] = str(base / "absent.sh")
        try:
            ctl.check("VACUITY: an absent subject is refused", main([]), 1)
        finally:
            os.environ.clear()
            os.environ.update(saved)

    return 0 if ctl.report() else 1
