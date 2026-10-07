"""The bump-none decision must EMIT ITS SIGNAL, and only on the skip path.

Ported from `.ci/scripts/quality/check-release-bump-skip.sh`, retired in W7 P5; see `rediacc_ci.quality.__init__` for the phase-5 decision that retired the twin.

THE SUBJECT IS THE DECIDER CI RUNS: `python3 -m rediacc_ci.ci.dispatch_release --decide-only`, the child `rediacc_ci.ci.initialize.release_decision` starts in step 6b. The module name is read from `initialize.DISPATCH_RELEASE_MODULE` rather than restated here, so the day initialize runs a different decider this gate drives that one, and an absent module is a refusal rather than a pass. Until 2026-10-07 this gate drove `.ci/scripts/ci/dispatch-release.sh`, which became a frozen twin when initialize cut over to the retried port (056fe87b6); a gate on the twin judged code CI no longer executes. The twin's equivalence to the port is `test_ci_dispatch_release.py`'s subject, not this gate's.

WHY THIS EXISTS. Two gates already cover neighbouring ground and neither touches this: `rediacc_ci.security.ci_workflow_invariants` asserts the WIRING in ci.yml (that the decision is declared once, threaded, and not re-decided in finalize-release-sentinel), and `test_gate_skip_release_channel_pointer.py` proves the UPLOAD script's guard branches correctly. Nothing drove the decider's own decision branch, so "Finalize Release emitted the skip signal for the right reason" was unobservable by construction. Release gates could say a release succeeded or was absent; they could not say WHY.

That distinction is not academic here. A bump-none merge and a broken decision both produce "no release". They are indistinguishable from the outside, and the only thing that tells them apart is the signal the decider emits:

    release SKIPPED: #576 carries 'bump-none'
    ::notice title=Release skipped::...earns no release...
    decision: skip

Observed live on 2026-08-26 (run 32961178698, job 98165911876) after merging PR #576. This gate keeps that observable.

THE DIRECTION THAT MATTERS MOST is not "does it skip" -- it is that the signal must NOT appear when the commit is releasing. A skip notice on a releasing path would tell a reader the opposite of what happened, and the decider's whole doctrine is that a silently withheld release is worse than an extra one.

HERMETIC: `gh` is shimmed on PATH (the port runs `gh` through `rediacc_ci.core.ghx`, which resolves it through PATH as the bash twin did), so this never touches the network and can run in any lane. Every shimmed failure is NON-transient on purpose: a 5xx or connection fault makes the port retry with a 5 s and 15 s backoff and then refuse (PLAN-gh-retry G3), and that refusal is `test_ci_dispatch_release.py`'s and `test_ci_initialize.py`'s subject, driven there with an injected sleep. WHAT IT CANNOT SEE: whether the workflow actually CALLS initialize (that is `rediacc_ci.security.ci_workflow_invariants`'s subject), and whether a real run's log retains the line (only a live bump-none merge shows that).

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THIS GATE MERGES STDOUT AND STDERR, AND THAT IS DELIBERATE RATHER THAN LAZY.
`rediacc_ci.proc.run` refuses to merge -- its docstring says "never merges streams", for the 2026-09-06 stream-swap reason recorded in `.ci/scripts/lib/emit-advisory.sh:22-52` -- so this module reaches for `subprocess` directly instead of quietly weakening the shared helper. The reason is that the SUBJECT here is a blob: initialize reads the decider's output with `stderr=subprocess.STDOUT`, and every assertion below is a substring test over the combined text, because the decider splits the same decision across both streams (the notice and the verdict on stdout, the reasoning on stderr through `rediacc_ci.log`) and an assertion on one stream alone would pass while the signal went to the other. Reproducing the merge is reproducing the contract initialize reads.

THE GH SHIM IS BUILT AS A FILE, NOT AS A PYTHON MOCK. The subject is a child process that resolves `gh` through PATH; a mock inside this process would test nothing about it. The shim carries `rows` as heredoc BODY under a quoted delimiter, so a `$` in a label is never expanded.

THE EMPTY-ROWS CASE IS NOT AN EMPTY SHIM. `printf '%s\\n' "$rows"` with an empty `rows` writes ONE BLANK LINE, so case 5 ("no merged PR at all") drives the decider with a single empty line of API output rather than with nothing. That is a real difference -- a decider that reads line-by-line sees one iteration -- and it is reproduced exactly rather than tidied into an empty body.
"""

import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import log
from rediacc_ci.ci import initialize
from rediacc_ci.controls import Controls, plant
from rediacc_ci.well_known import GH_REPO

# The selftest's seam: a path to an EXECUTABLE stand-in decider, run as `<path> --decide-only` instead of the live module. Unset, the gate drives the module initialize runs.
SCRIPT_ENV = "RELEASE_DECIDE_SCRIPT"

# The environment the subject is driven under. GITHUB_SHA is the real sha of the 2026-08-26 merge the gate is written from, kept so that a reader who greps for it lands on the incident rather than on a placeholder.
DRIVE_ENV = {
    "GITHUB_REPOSITORY": GH_REPO,
    "GITHUB_SHA": "1c006e538fe3d33eeb280b809140b0d477a280db",
}

# The literal the whole gate is about. Kept as one constant because it appears as both the needle of case 1 and the anti-needle of cases 2 through 5, and two spellings of it would let one direction silently stop asserting.
SKIP_SIGNAL = "release SKIPPED"

# How many lines of the subject's output a failure report shows: enough to see the decision, short enough that five failures do not bury the summary.
FAILURE_EXCERPT_LINES = 6


def _write_shim(bin_dir: pathlib.Path, rows: str) -> None:
    """The `gh` the subject will find on PATH.

    `rows` is what the API would return, one PR per line as "<number> <labels,csv>"; the literal FAIL makes the shim exit non-zero with a NON-transient message, the fail-open path.
    """
    shim = bin_dir / "gh"
    if rows == "FAIL":
        shim.write_text('#!/bin/bash\necho "api exploded" >&2\nexit 1\n', encoding="utf-8")
    else:
        shim.write_text("#!/bin/bash\ncat <<'ROWS'\n%s\nROWS\n" % rows, encoding="utf-8")
    shim.chmod(0o755)


def live_subject() -> tuple[list[str], str] | None:
    """The argv initialize uses for its decider, and the file it resolves to; None when the module is gone.

    `find_spec` rather than a hard-coded path: the module name is initialize's, so a renamed or moved decider is found where initialize would find it, or refused here.
    """
    name = initialize.DISPATCH_RELEASE_MODULE
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError:
        spec = None
    if spec is None or not spec.origin:
        return None
    return [sys.executable, "-m", name], spec.origin


def drive(work: pathlib.Path, argv: list[str], rows: str) -> tuple[int, str]:
    """Run the subject with a shimmed gh. Returns (exit code, merged output)."""
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
    # initialize hands the child the same PYTHONPATH, so the decider imports this checkout's ports wherever the cwd is.
    env["PYTHONPATH"] = initialize.PACKAGE_PARENT

    # See the port notes: the merge is the contract, not a shortcut.
    completed = subprocess.run(
        [*argv, "--decide-only"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    # `.rstrip("\n")` keeps the failure excerpt free of a trailing empty element: without it `out.split("\n")` yields one extra six-space line per driven case. Measured 2026-09-07 under W7 P4 against the bash twin's `$(...)` capture; kept because the excerpt path fires only when the decider is already broken, the moment its output most needs to read cleanly.
    return completed.returncode, completed.stdout.rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    if argv and argv[0] == "--selftest":
        return selftest()

    stand_in = os.environ.get(SCRIPT_ENV, "")
    if stand_in:
        if not pathlib.Path(stand_in).is_file():
            log.error(
                "release-bump-skip: the stand-in decider %s does not exist. Nothing to drive "
                "is not a clean tree." % stand_in
            )
            return 1
        subject, shown = [stand_in], stand_in
    else:
        live = live_subject()
        if live is None:
            log.error(
                "release-bump-skip: the release decider initialize runs (python3 -m %s) cannot "
                "be found. Nothing to drive is not a clean tree -- if the decision moved, "
                "retarget initialize.DISPATCH_RELEASE_MODULE and this gate follows."
                % initialize.DISPATCH_RELEASE_MODULE
            )
            return 1
        subject, origin = live
        shown = "python3 -m %s (%s)" % (initialize.DISPATCH_RELEASE_MODULE, origin)

    failed = False

    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)

        def expect(label: str, rows: str, want: str, needle: str, anti: str) -> None:
            nonlocal failed
            code, out = drive(work, subject, rows)
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

        log.info("release-bump-skip: driving %s --decide-only through every branch" % shown)

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

        # 4. Fail OPEN on a NON-transient failure (a 4xx, an auth error). The port still answers there, and must release rather than silently withhold -- the decider's stated doctrine -- and must not claim a skip. A 5xx is a refusal instead; see the module docstring.
        expect(
            "API failure -> releases (fails open), no skip signal",
            "FAIL",
            "release",
            "",
            SKIP_SIGNAL,
        )

        # 5. No merged PR at all (direct push): releases, no skip signal.
        expect("no merged PR -> releases, no skip signal", "", "release", "", SKIP_SIGNAL)

        # ANTI-VACUITY. If the shim could not drive the decider at all, every `expect` above would have failed loudly -- but a future refactor could make the decider exit 0 printing nothing, and the "decision: release" test would then fail rather than pass, so the suite stays honest. The control here is the opposite risk: prove the harness can still produce a SKIP, so case 2's "no
        # skip signal" is not passing because the signal is unreachable for everyone.
        _code, control = drive(work, subject, "999 bump-none")
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
    log.info("  Blind spot: does not prove the workflow CALLS initialize (that is")
    log.info("  rediacc_ci.security.ci_workflow_invariants), nor that a live run's log")
    log.info("  retains the line -- only a real bump-none merge shows that.")
    return 0


# A stand-in for the release decider that decides the same way it does, used by the selftest as the thing every plant mutates. It is bash because the gate's contract is the decider's PROCESS interface (argv, a `gh` on PATH, merged output), which a stand-in in any language honours. Written out rather than copied
# from the real decider, because a fixture built by copying is a fixture that
# stops testing the day the original is reworded -- and because mutating the REAL release decider on disk to prove a gate fires is exactly the kind of control `check-control-vacuity.sh` refuses.
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

    THE PLANT IS IN THE SUBJECT, NOT IN THE GATE, which is the only place it can be: this gate's whole claim is about what the release decider prints, so a control that mutated the gate would prove nothing about that claim. The `RELEASE_DECIDE_SCRIPT` seam exists for exactly this and is used for nothing
    else.

    The fake subject is asserted to be a WORKING one first. Without that, every plant below would "fire" against a subject that was broken to begin with, and the suite would be green while testing nothing -- the same vacuity the gate itself is written against.
    """
    ctl = Controls("release-bump-skip", floor=8, verbose=True)

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

        ctl.check("CONTROL: a correct stand-in decider passes", run_against(_FAKE_SUBJECT), 0)

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

        # PLANT 5: the subject prints nothing at all. This is the shape the twin's own anti-vacuity note calls out -- "a future refactor could make the decider exit 0 printing nothing" -- and it must be a refusal, not a pass.
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

        # And the live path's refusal: initialize names a decider module that does not resolve. Without this the default branch could fall through to driving nothing.
        real_module = initialize.DISPATCH_RELEASE_MODULE
        saved = dict(os.environ)
        os.environ.pop(SCRIPT_ENV, None)
        initialize.DISPATCH_RELEASE_MODULE = "rediacc_ci.ci.no_such_release_decider"
        try:
            ctl.check("VACUITY: an unresolvable live decider module is refused", main([]), 1)
        finally:
            initialize.DISPATCH_RELEASE_MODULE = real_module
            os.environ.clear()
            os.environ.update(saved)

    return 0 if ctl.report() else 1
