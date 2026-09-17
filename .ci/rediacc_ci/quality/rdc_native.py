"""`rdc.sh` stays a wrapper, and the SEA build it delegates answers the same on all three OSes.

WHAT THIS GATE IS FOR. On 2026-09-09 the `--native` SEA build left `rdc.sh` for `rediacc_ci.native`: 93 lines out of a 314-line file, including two hand-written `case "$(uname ...)"` blocks that `rediacc_ci.core.platform` already owned and cites by line. Two things can undo that and neither is visible in a diff review of one file.

  1. THE WRAPPER RE-ABSORBS LOGIC, one reasonable special case at a time, which is the
     same failure `.ci/scripts/test/gates/test-run-sh.sh` section 7 exists to stop for
     `run.sh`. A line ceiling is the only check that catches the twentieth small addition
     rather than the first big one.
  2. THE PORT DRIFTS ON AN ARM NOBODY RUNS. This is the interesting half. In bash the
     mac and win arms of that build were NEVER EXECUTED by anything in this repository:
     CI is Linux, every developer here is Linux or WSL, and the only way to learn that
     `rdc-mac-arm64` had become `rdc-macos-arm64` was for someone with a Mac to try it.
     `rediacc_ci.native.plan()` takes `system` and `machine` as ARGUMENTS, so this gate
     asks all three arms on a Linux box and holds the answers against a literal table.

THE TABLE IS WRITTEN OUT, NOT DERIVED, and that is the whole value of it. Deriving the expected paths by calling the same helpers the subject calls would agree with any defect in those helpers, which is the tautology this gate would otherwise be. `ARMS` below spells `rdc-mac-arm64`, `rdc-win-x64.exe` and `rdc.old.exe` as literals, read off the bash that was deleted, so a re-keyed
mapping is a MISMATCH rather than a matching pair of wrongs.

ANTI-VACUITY. Every probe is a real subprocess and its exit code is checked; a probe that
could not run is a finding, never a skip. The arm count is asserted against the table's own length, so a loop that stopped iterating fails instead of reporting a clean sweep. The subject file being absent is a failure, and so is a `rdc.sh` of zero bytes.

THE CONTROL RUNS AGAINST A MUTATED COPY OF THE PACKAGE, not against a mutated copy of the gate. `plan()` resolves its root from `native.py`'s own location and this gate points the subprocess at the copy with `PYTHONPATH`, so the control exercises the same delegation the real run does, over a package whose darwin mapping has been re-keyed. The plant is asserted to have landed before
its result is believed: a substitution that matched nothing would otherwise produce an identical copy, a control that "fires" on unmutated source, and a green that means nothing. Both directions are covered, because a differential that always reports a mismatch is as useless as one that never does.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import controls, log, paths

# The subject, relative to the repo root.
RDC_SH = "rdc.sh"

# THE CEILING, and the four lines of headroom are deliberate. `run.sh` sits at 120 of 120 and its own box records that as a constraint rather than a comfort: the next verb ported there cannot add a line without a ceiling change in the same commit. A wrapper this size should be able to gain a sentence of explanation without an author having to touch the gate, and 4 lines is nowhere
# near the 93 that left. The success line prints the spare.
CEILING = 185

# A floor as well as a ceiling. A `rdc.sh` that has become a two-line stub is not a win,
# it is a file somebody truncated; every assertion below would pass on it.
FLOOR = 40

# The three platform arms, times the spellings `uname` really emits, times both arches. Read off the bash that was deleted (`rdc.sh:89-118` at HEAD~), NOT derived from the subject's own tables. See the module docstring.
#
# Each row: (uname -s, uname -m, sea platform, sea arch, exe suffix).
ARMS: tuple[tuple[str, str, str, str, str], ...] = (
    ("Linux", "x86_64", "linux", "x64", ""),
    ("Linux", "amd64", "linux", "x64", ""),
    ("Linux", "aarch64", "linux", "arm64", ""),
    ("Linux", "arm64", "linux", "arm64", ""),
    ("Darwin", "x86_64", "mac", "x64", ""),
    ("Darwin", "arm64", "mac", "arm64", ""),
    ("MINGW64_NT-10.0-22631", "x86_64", "win", "x64", ".exe"),
    ("MSYS_NT-10.0-19045", "amd64", "win", "x64", ".exe"),
    ("CYGWIN_NT-10.0", "aarch64", "win", "arm64", ".exe"),
)

# The two refusals the bash had, kept word for word. A platform or an architecture with no pinned build must STOP, not fall through to a default: the whole install step overwrites the user's `rdc` with whatever was produced.
REFUSALS: tuple[tuple[str, str, str], ...] = (
    ("Plan9", "x86_64", "Unsupported platform Plan9 for --native"),
    ("Linux", "riscv64", "Unsupported arch riscv64 for --native"),
)

# A fixed HOME for every probe, so `dest` and `backup` are comparable against a literal and no assertion depends on whose machine the gate runs on.
PROBE_HOME = "/nonexistent-probe-home"


def expected_plan(root: str, home: str, arm: tuple[str, str, str, str, str]) -> dict[str, str]:
    """What `--print-plan` must say for one arm, as literals.

    `backup` is spelled `rdc.old<exe>` rather than derived from `dest`, because that is what `getOldBinaryPath()` in `packages/cli/src/utils/platform.ts` looks for and a derivation would agree with a subject that derived it wrongly the same way.
    """
    _system, _machine, sea_os, sea_arch, exe = arm
    return {
        "sea_platform": sea_os,
        "sea_arch": sea_arch,
        "exe": exe,
        "built": "%s/dist/cli/rdc-%s-%s%s" % (root, sea_os, sea_arch, exe),
        "dest": "%s/.local/share/rediacc/bin/rdc%s" % (home, exe),
        "backup": "%s/.local/share/rediacc/bin/rdc.old%s" % (home, exe),
    }


def probe(ci_dir: str, system: str, machine: str) -> tuple[int, str, str]:
    """Ask one arm, in a real subprocess, against the package under `ci_dir`.

    `ci_dir` is the directory that goes on PYTHONPATH, so pointing it at a COPY is what makes the planted-defect control exercise the real delegation rather than a stub. cwd is `/`: nothing here may depend on the caller's directory, and running from the repo root would hide it if something did.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = ci_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["HOME"] = PROBE_HOME
    env.pop("REDIACC_CI_ROOT", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "rediacc_ci.native",
            "--print-plan",
            "--system",
            system,
            "--machine",
            machine,
        ],
        cwd="/",
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return completed.returncode, completed.stdout, completed.stderr


def arm_findings(ci_dir: str) -> list[str]:
    """One line per arm whose answer is not the table's. [] when all nine agree.

    A probe that FAILED is a finding naming its stderr, never a skipped arm: an interpreter that cannot import the package would otherwise leave this list empty and the gate would call that a clean sweep.
    """
    root = str(pathlib.Path(ci_dir).parent)
    out: list[str] = []
    for arm in ARMS:
        system, machine = arm[0], arm[1]
        rc, stdout, stderr = probe(ci_dir, system, machine)
        if rc != 0:
            out.append(
                "%s / %s: --print-plan exited %d: %s" % (system, machine, rc, stderr.strip())
            )
            continue
        try:
            got = json.loads(stdout)
        except json.JSONDecodeError as exc:
            out.append("%s / %s: --print-plan did not emit JSON (%s)" % (system, machine, exc))
            continue
        want = expected_plan(root, PROBE_HOME, arm)
        out.extend(
            "%s / %s: %s is %r, the deleted bash produced %r"
            % (system, machine, key, got.get(key), want[key])
            for key in sorted(want)
            if got.get(key) != want[key]
        )
    return out


def refusal_findings(ci_dir: str) -> list[str]:
    """One line per refusal that did not happen, or happened with the wrong words."""
    out: list[str] = []
    for system, machine, message in REFUSALS:
        rc, _stdout, stderr = probe(ci_dir, system, machine)
        if rc == 0:
            out.append("%s / %s was ACCEPTED; it has no pinned build" % (system, machine))
        elif message not in stderr:
            out.append(
                "%s / %s refused without saying %r: %s" % (system, machine, message, stderr.strip())
            )
    return out


def wrapper_findings(text: str, ceiling: int = CEILING, floor: int = FLOOR) -> list[str]:
    """Structural findings on `rdc.sh`'s own text. Pure, so the selftest drives it directly.

    Three separate claims, and they are not the same claim:
      * the file is within its ceiling and above its floor;
      * the uname mapping did not stay behind as a THIRD copy;
      * the `--native` arm really names the module rather than only mentioning it.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    out: list[str] = []
    if len(lines) > ceiling:
        out.append(
            "rdc.sh is %d lines; the ceiling is %d. The build logic belongs in "
            "rediacc_ci.native, not back in the wrapper." % (len(lines), ceiling)
        )
    if len(lines) < floor:
        out.append(
            "rdc.sh is only %d lines, below the floor of %d. Every check here would pass "
            "on a truncated file." % (len(lines), floor)
        )
    code = "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))
    if 'case "$(uname' in code:
        out.append(
            'rdc.sh has a `case "$(uname ...)"` block again. rediacc_ci.core.platform owns '
            "that mapping and already names this file among the copies it replaced."
        )
    if "build-cli-executables.sh" in code:
        out.append(
            "rdc.sh invokes build-cli-executables.sh directly again; the SEA build sequence "
            "lives in rediacc_ci.native."
        )
    if "rediacc_ci.native" not in code:
        out.append("rdc.sh no longer delegates to rediacc_ci.native, so --native reaches nothing.")
    return out


def _mutated_copy(ci_dir: str, dest: str) -> str:
    """A copy of the package with darwin's SEA name re-keyed. Returns the copy's `.ci` dir.

    THE PLANT IS ASSERTED BY THE CALLER, and the assertion is not ceremony. This is a pattern substitution: reword the line it targets and it silently produces an identical copy, the control passes against unmutated source, and the green proves nothing. That is the exact shape `check:ci-control-vacuity` refuses in bash, applied here by hand because that gate parses only
    `check-*.sh`.
    """
    copied_ci = os.path.join(dest, ".ci")
    os.makedirs(copied_ci, exist_ok=True)
    shutil.copytree(
        os.path.join(ci_dir, "rediacc_ci"),
        os.path.join(copied_ci, "rediacc_ci"),
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    return copied_ci


NEEDLE = 'OS_DARWIN: "mac"'
REPLACEMENT = 'OS_DARWIN: "macos"'


def selftest() -> bool:
    check = controls.Checker()
    root = paths.repo_root()
    ci_dir = str(root / ".ci")

    # -- the pure half, both directions -------------------------------------------------
    ok_text = "\n".join(["#!/bin/bash"] + ["# filler"] * 60 + ["exec python3 -m rediacc_ci.native"])
    check(
        "CONTROL: a wrapper inside its budget yields no findings", wrapper_findings(ok_text) == []
    )
    check(
        "a wrapper over the ceiling is reported",
        any("ceiling" in f for f in wrapper_findings(ok_text + "\n# x" * 200)),
    )
    check(
        "a TRUNCATED wrapper is reported, not silently accepted",
        any(
            "floor" in f for f in wrapper_findings("#!/bin/bash\nexec python3 -m rediacc_ci.native")
        ),
    )
    check(
        "a re-inlined uname case block is reported",
        any("uname" in f for f in wrapper_findings(ok_text + '\ncase "$(uname -s)" in\nesac')),
    )
    check(
        "CONTROL: the same text inside a COMMENT is not a finding",
        wrapper_findings(ok_text + '\n# case "$(uname -s)" in') == [],
    )
    check(
        "a wrapper that stopped delegating is reported",
        any("delegates" in f for f in wrapper_findings("#!/bin/bash\n" + "# filler\n" * 60)),
    )

    # -- the differential, against an UNMUTATED copy first ------------------------------ The negative direction, and it runs first on purpose: if the copy mechanism itself were broken, the mutated run below would "fire" for a reason that has nothing to do
    # with the mutation. Proving the copy is clean is what makes the next result evidence.
    with tempfile.TemporaryDirectory() as tmp:
        clean_ci = _mutated_copy(ci_dir, tmp)
        check(
            "CONTROL: an unmutated COPY of the package answers every arm correctly",
            arm_findings(clean_ci) == [],
        )

    with tempfile.TemporaryDirectory() as tmp:
        planted_ci = _mutated_copy(ci_dir, tmp)
        target = os.path.join(planted_ci, "rediacc_ci", "core", "platform.py")
        with open(target, encoding="utf-8") as fh:
            before = fh.read()
        after = before.replace(NEEDLE, REPLACEMENT)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(after)
        # PROOF OF PLANT, before anything is concluded from the control.
        landed = after != before and REPLACEMENT in after
        check("CONTROL PLANT LANDED: darwin's SEA name was re-keyed in the copy", landed)
        if landed:
            planted = arm_findings(planted_ci)
            check(
                "the macOS arms FAIL on the planted defect",
                sum(1 for f in planted if f.startswith("Darwin /")) >= 2,
            )
            check(
                "CONTROL: the linux and windows arms are UNAFFECTED by it",
                not any(f.startswith(("Linux /", "MINGW", "MSYS", "CYGWIN")) for f in planted),
            )

    # -- the refusals -------------------------------------------------------------------
    check(
        "CONTROL: the real package refuses an unpinned platform and arch by name",
        refusal_findings(ci_dir) == [],
    )
    return check.ok


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return 0 if selftest() else 1
    if not selftest():
        log.error("REFUSING to report on the tree: this gate's own controls failed.")
        return 2

    root = paths.repo_root()
    subject = root / RDC_SH
    if not subject.is_file():
        log.error(
            "%s is not on disk; this gate has nothing to judge and its green would "
            "mean nothing." % RDC_SH
        )
        return 1
    text = subject.read_text(encoding="utf-8")
    if not text.strip():
        log.error("%s is empty; every assertion here would pass on it." % RDC_SH)
        return 1

    findings = wrapper_findings(text)
    ci_dir = str(root / ".ci")
    arms = arm_findings(ci_dir)
    refusals = refusal_findings(ci_dir)
    if len(ARMS) < 6:
        log.error("the arm table holds %d rows; it must cover all three platform arms." % len(ARMS))
        return 1

    if findings or arms or refusals:
        for line in findings + arms + refusals:
            log.error(line)
        log.error(
            "`./rdc.sh --native` is served by .ci/rediacc_ci/native.py. Fix it there, "
            "and do not move the build back into the wrapper."
        )
        return 1

    line_count = len(text.rstrip("\n").split("\n"))
    print(
        "rdc.sh native delegation: %d lines of %d (%d spare), %d platform arm(s) agree with the "
        "pre-port table, %d refusal(s) still refuse"
        % (line_count, CEILING, CEILING - line_count, len(ARMS), len(REFUSALS))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
