"""The `.devcontainer` bootstrap scripts must REPORT failures, not swallow them.

Ported from `.ci/scripts/quality/check-devcontainer-scripts.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live.

The twin's header, carried whole because the incident and the control-first rule
are the gate:

    Why this exists. `.devcontainer/init-submodules.sh` used to run
        git submodule update --init --recursive "$sub" 2>/dev/null
    and print "✗ $sub (no access, skipping)" for every non-zero exit, then
    `exit 0` regardless. A session lost real time to that: the token was valid
    and the failure was a stale credential helper, but the script reported the
    same sentence it prints for a permission denial, a DNS outage and a
    force-pushed submodule pointer, and the actual git error was discarded. The
    fix was by hand, and nothing stopped it coming back -- no existing gate reads
    shell stderr semantics.

    Three assertions, each with its own CONTROL. A control-first gate proves it
    can fail before it is allowed to pass: every assertion below is re-run
    against a deliberately broken copy of the script, and if the broken copy
    passes, this gate fails itself rather than reporting green.

      A. No primary operation discards its stderr.
      B. init-submodules.sh surfaces the real git error and exits non-zero.
      C. start-vscode.sh --background/--stop signal the process GROUP.

    Assertion C guards a bug this gate's own session shipped and then caught by
    running it: `bin/openvscode-server` is a wrapper whose node CHILD holds the
    port, so signalling the launched pid printed "stopped" while the listener
    survived, and the next start died with "port already in use".

    Hermetic: no network, no docker, no submodule access. Runs in ~2 seconds.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

ASSERTION A IS DELIBERATELY NARROW AND THE TWIN SAYS WHY, twice, and both
sentences are kept at the patterns they describe:

    Not a blanket ban on 2>/dev/null: probing for a pid, a command or a config
    value legitimately discards noise, and a gate that forbids those gets
    suppressed itself within a week. What must never be silenced is the command
    whose failure the script then reports on.

    Deliberately narrow: the command whose failure the script REPORTS ON. A probe
    (`command -v x 2>/dev/null`, `kill -0`, `ps`) is not a primary operation, and
    a gate that forbids those gets suppressed within a week.

THE MUTATIONS ARE RUN BY THE REAL `sed`, not re-implemented. Two of the three
carry BRE back-references (`s@^\\(  *\\)...@\\1...@`), and a Python rewrite of
those would be a second implementation of the thing whose job is to be identical.
Shelling out keeps the plant byte-for-byte what the twin plants, which is the
only way `CONTROL IS VACUOUS` keeps meaning what it says.

EACH CONTROL CHECKS THAT ITS PLANT LANDED, and that is the half most gates skip.
The twin greps the mutated copy for a marker before trusting the result: "The
planted marker is checked for explicitly, so a refactor that moves the target
line makes this control VACUOUS (and fails the gate) rather than silently
mutating nothing and calling it a pass."

`control_must_fail` RUNS THE ASSERTION IN A SUBSHELL in the twin, so the `fail()`
calls inside a control run do NOT increment the real counter and their output is
captured and thrown away. That is not incidental: without it, every control would
add its own deliberate failure to the gate's verdict. The port reproduces it with
a discarding reporter rather than a subshell.

THE GATE EMITS NO SEVERITY MARKER AT ALL. `fail()` prints `FAIL <text>` with ONE
space, which is not the `FAIL  ` (two spaces) the repository's comparator knows,
and `pass()` prints `ok   `. So the differential for this pair is recorded with a
`--finding-re`, stored on every ledger row so the rows can be re-run.

THE EM DASH IN THE THREE `CONTROL IS VACUOUS` LINES is named by code point rather
than typed, because this repository's authoring rule forbids the character and
the differential compares finding TEXT. Same treatment as
`scripts/lib/shadow-gate.ts` naming ESC with `String.fromCharCode(27)`.

UGREP WAS CHECKED HERE, NOT ASSUMED. `PRIMARY_OPS` alternates a `^`-anchored
branch with a branch carrying a negated class (`curl [^|]*`), which is the shape
`docs/agent-reference/TRAPS.md` records as returning silent false zeros from
`grep -E`. Measured on this host, ugrep 7.8.4: `-E` and `-P` return the SAME five
lines over a corpus containing one instance of each branch. The port's Python
regex is compared against the real `grep -E` over every `.devcontainer/*.sh` in
`tests/test_quality_devcontainer_scripts.py`, so a future ugrep that does
diverge shows up as a test failure rather than as two gates quietly disagreeing.
"""

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The em dash the twin's three CONTROL IS VACUOUS lines carry. Named by code
# point; see the port notes.
DASH = "—"

# The subject directory and the two named scripts inside it.
DC_REL = ".devcontainer"
INIT_NAME = "init-submodules.sh"
VSCODE_NAME = "start-vscode.sh"

# A. stderr suppression on a PRIMARY operation.
#
# Not a blanket ban on 2>/dev/null: probing for a pid, a command or a config
# value legitimately discards noise, and a gate that forbids those gets
# suppressed itself within a week. What must never be silenced is the command
# whose failure the script then reports on.
PRIMARY_OPS = re.compile(
    r"git (clone|fetch|pull|submodule update|submodule add)"
    r"|curl [^|]*(-o |-O |--output)"
    r"|^[ \t]*tar "
    r"|npm (ci|install)"
)
SUPPRESSORS = re.compile(
    r"2>/dev/null|2> */dev/null|2>&-|>[ \t]*/dev/null[ \t]+2>&1|&>[ \t]*/dev/null"
)

# `grep -vE '^[0-9]+:[[:space:]]*#'` over `grep -n` output: a COMMENT that names
# a primary operation is documentation, not an operation.
NUMBERED_COMMENT = re.compile(r"^[0-9]+:[ \t]*#")

# C. Process-group lifecycle in start-vscode.sh.
SETSID = re.compile(r"^[ \t]*setsid ")
KILL_GROUP = re.compile(r'kill -(TERM|9) -- "?-\$')

# B. git's own words, not a paraphrase of them.
GIT_ERROR = re.compile(
    r"does not (appear to be|exist)|repository .* not found|fatal:", re.IGNORECASE
)

# The three mutations, each with the marker that proves it landed. Kept as data
# so the sed expression and the thing it plants cannot drift apart.
A_MUTATION = (
    r"s@^\(  *\){ GIT_TERMINAL_PROMPT=0 git .*$@\1git submodule update --init "
    r'--recursive "$sub" 2>/dev/null ### PLANTED@'
)
A_MARKER = "# PLANTED"

B_SWALLOW = (
    's#^  err="$(attempt false "$sub")"#  err="(no access, skipping)"; '
    'attempt false "$sub" >/dev/null 2>\\&1#'
)
B_ALWAYS_ZERO = "s#^  exit 1$#  exit 0#"
B_MUTATIONS = (B_SWALLOW, B_ALWAYS_ZERO)
B_MARKER = "no access, skipping"

C_MUTATIONS = (
    r"s#^\([[:space:]]*\)setsid nohup #\1nohup #",
    's#kill -TERM -- "-$pgid"#kill -TERM "$pid"#',
    's#kill -9 -- "-$pgid"#kill -9 "$pid"#',
)


def scan_suppression(text: str) -> list[str]:
    """`grep -nE PRIMARY_OPS | grep -vE '^[0-9]+:[[:space:]]*#' | grep -E SUPPRESSORS`.

    Returns the offending `<n>:<line>` strings. The comment filter runs BETWEEN
    the two matchers, on the NUMBERED lines, which is why its pattern carries the
    `^[0-9]+:` prefix.
    """
    numbered = [
        "%d:%s" % (number, line)
        for number, line in enumerate(text.split("\n"), start=1)
        if PRIMARY_OPS.search(line)
    ]
    kept = [line for line in numbered if not NUMBERED_COMMENT.search(line)]
    return [line for line in kept if SUPPRESSORS.search(line)]


def build_scratch_super(where: pathlib.Path) -> None:
    """A superproject whose submodule URL is an unreachable local path.

    So assertion B needs neither the network nor credentials: the failure is a
    repository that is not there, which is the same class of failure as a stale
    credential helper and produces git's own diagnostic either way.
    """
    where.mkdir(parents=True, exist_ok=True)
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-C", str(where), *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    run("init", "-q", ".")
    run("config", "user.email", "gate@example.invalid")
    run("config", "user.name", "gate")
    (where / ".gitmodules").write_text(
        '[submodule "vendor/absent"]\n\tpath = vendor/absent\n'
        "\turl = file://%s/definitely-not-a-repo.git\n" % where,
        encoding="utf-8",
    )
    run(
        "update-index",
        "--add",
        "--cacheinfo",
        "160000,0000000000000000000000000000000000000001,vendor/absent",
    )
    run("add", ".gitmodules")
    run("commit", "-qm", "scratch")


def run_init_against_scratch(script: pathlib.Path, tmp: pathlib.Path) -> tuple[int, str]:
    """Run `script vendor/absent` in a fresh scratch superproject.

    Returns (exit status, combined output with trailing newlines stripped),
    matching `out="$(... 2>&1)"; rc=$?`. Three tokens are REMOVED from the
    environment (`GITHUB_TOKEN`, `GH_TOKEN`, `PAT`) so a developer's own
    credentials cannot make the unreachable URL reachable.
    """
    where = tmp / ("super.%d" % os.getpid())
    counter = 0
    while where.exists():
        counter += 1
        where = tmp / ("super.%d.%d" % (os.getpid(), counter))
    build_scratch_super(where)
    env = dict(os.environ)
    env["NO_COLOR"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    for name in ("GITHUB_TOKEN", "GH_TOKEN", "PAT"):
        env.pop(name, None)
    proc = subprocess.run(
        ["bash", str(script), "vendor/absent"],
        cwd=str(where),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, re.sub(r"\n+$", "", proc.stdout.decode("utf-8", "replace"))


def assert_a(scripts: list[pathlib.Path], report) -> int:
    """No primary operation discards its stderr. 0 clean, 1 on any offender."""
    rc = 0
    for script in scripts:
        offenders = scan_suppression(script.read_text(encoding="utf-8", errors="replace"))
        if offenders:
            report("A: %s discards stderr of a primary operation:" % script.name)
            # `printf '       %s\n' "$offenders"` with a QUOTED multi-line value
            # runs ONE format cycle, so only the first line carries the indent.
            report.detail("       %s" % "\n".join(offenders))
            rc = 1
    return rc


def assert_b(script: pathlib.Path, tmp: pathlib.Path, report) -> int:
    """A real failure must produce real error text AND a non-zero exit."""
    rc, out = run_init_against_scratch(script, tmp)
    if rc == 0:
        report(
            "B: %s exited 0 on an unreachable submodule; a failed init must be visible "
            "to the caller" % script.name
        )
        return 1
    # The load-bearing part: git's own words, not a paraphrase of them.
    if not GIT_ERROR.search(out):
        report("B: %s never printed git's actual error. Output was:" % script.name)
        for line in out.split("\n"):
            report.detail("       %s" % line)
        return 1
    return 0


def assert_c(script: pathlib.Path, report) -> int:
    """The background server must be started and stopped as a process GROUP."""
    rc = 0
    text = script.read_text(encoding="utf-8", errors="replace")
    if not any(SETSID.search(line) for line in text.split("\n")):
        report(
            "C: %s starts the background server without setsid; --stop cannot then reach "
            "the node child that owns the port" % script.name
        )
        rc = 1
    if not KILL_GROUP.search(text):
        report(
            "C: %s never signals a process group on stop; killing the wrapper pid leaves "
            "the listener alive" % script.name
        )
        rc = 1
    return rc


class Reporter:
    """`fail()` plus its detail lines, or a sink that counts and prints nothing.

    The silent form is what `control_must_fail` needs: the twin runs each control
    inside a command substitution, so the deliberate failures a mutated copy
    produces are captured and discarded and never reach the real counter.
    """

    def __init__(self, *, silent: bool) -> None:
        self.silent = silent
        self.count = 0

    def __call__(self, message: str) -> None:
        self.count += 1
        if not self.silent:
            print("FAIL %s" % message, file=sys.stderr)

    def detail(self, message: str) -> None:
        if not self.silent:
            print(message, file=sys.stderr)


def mutate(src: pathlib.Path, dst: pathlib.Path, expressions: tuple[str, ...]) -> None:
    """`cp` then one `sed -i` per expression, run by the REAL sed.

    See the port notes: two of these carry BRE back-references, and
    re-implementing them would put a second implementation between the plant and
    the thing it is supposed to plant.
    """
    shutil.copyfile(src, dst)
    for expression in expressions:
        subprocess.run(["sed", "-i", expression, str(dst)], check=True)


def main(argv: list[str] | None = None) -> int:
    """Run the three assertions and their three controls. 0 clean, 1 otherwise."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    dc = root / DC_REL
    init = dc / INIT_NAME
    vscode = dc / VSCODE_NAME

    report = Reporter(silent=False)

    print("check-devcontainer-scripts: stderr visibility and lifecycle invariants")

    if not init.is_file():
        report("missing %s" % init)
    if not vscode.is_file():
        report("missing %s" % vscode)
    if report.count != 0:
        return 1

    scripts = sorted(dc.glob("*.sh"))
    for script in scripts:
        proc = subprocess.run(["bash", "-n", str(script)], check=False)
        if proc.returncode != 0:
            report("syntax error in %s" % script.name)
    if report.count == 0:
        print("ok   every .devcontainer/*.sh parses")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)

        if assert_a(scripts, report) == 0:
            print("ok   no primary operation discards its stderr")
        if assert_b(init, tmpdir, report) == 0:
            print("ok   init-submodules.sh surfaces git's real error and exits non-zero")
        if assert_c(vscode, report) == 0:
            print("ok   start-vscode.sh uses a process group for start/stop")

        # --- controls ------------------------------------------------------
        control_fails = 0

        # A-control: reintroduce the exact suppression the old script had.
        # The planted marker is checked for explicitly, so a refactor that moves
        # the target line makes this control VACUOUS (and fails the gate) rather
        # than silently mutating nothing and calling it a pass.
        a_broken = tmpdir / "a-broken.sh"
        mutate(init, a_broken, (A_MUTATION,))
        if A_MARKER not in a_broken.read_text(encoding="utf-8", errors="replace"):
            print(
                "CONTROL IS VACUOUS: A %s the mutation did not apply, so nothing was planted."
                % DASH,
                file=sys.stderr,
            )
            print(
                "  The line it targets in init-submodules.sh has changed; update this control.",
                file=sys.stderr,
            )
            control_fails = 1
        elif not scan_suppression(a_broken.read_text(encoding="utf-8", errors="replace")):
            print("CONTROL DID NOT FIRE: A (stderr suppression)", file=sys.stderr)
            print(
                "  A copy of init-submodules.sh with 2>/dev/null on the submodule update "
                "was NOT flagged.",
                file=sys.stderr,
            )
            control_fails = 1

        # B-control: the old behavior -- swallow the git error and always exit 0.
        b_broken = tmpdir / "b-broken.sh"
        mutate(init, b_broken, B_MUTATIONS)
        if B_MARKER not in b_broken.read_text(encoding="utf-8", errors="replace"):
            print(
                "CONTROL IS VACUOUS: B %s the mutation did not apply, so nothing was planted."
                % DASH,
                file=sys.stderr,
            )
            control_fails = 1
        elif not control_must_fail(
            "B (real git error must surface)", lambda r: assert_b(b_broken, tmpdir, r)
        ):
            control_fails = 1

        # C-control: a copy of start-vscode.sh with the process-group handling
        # removed.
        c_broken = tmpdir / "c-broken.sh"
        mutate(vscode, c_broken, C_MUTATIONS)
        c_text = c_broken.read_text(encoding="utf-8", errors="replace")
        if any(SETSID.search(line) for line in c_text.split("\n")) or KILL_GROUP.search(c_text):
            print(
                "CONTROL IS VACUOUS: C %s the mutation did not apply, so nothing was planted."
                % DASH,
                file=sys.stderr,
            )
            control_fails = 1
        elif not control_must_fail("C (process-group lifecycle)", lambda r: assert_c(c_broken, r)):
            control_fails = 1

        if control_fails != 0:
            return 1
        print("ok   controls fired: each assertion rejects a copy carrying the original defect")

    if report.count != 0:
        print(file=sys.stderr)
        print(
            "%d assertion(s) failed. Rerun: npm run check:ci-devcontainer-scripts" % report.count,
            file=sys.stderr,
        )
        return 1
    print("All devcontainer script invariants hold.")
    return 0


def control_must_fail(label: str, run) -> bool:
    """The planted defect must be REJECTED. True when the control fired.

    The assertion's own output is discarded, matching the twin's command
    substitution: a control that printed its deliberate failure would read in the
    log exactly like a real one.
    """
    sink = Reporter(silent=True)
    if run(sink) == 0:
        print("CONTROL DID NOT FIRE: %s" % label, file=sys.stderr)
        print(
            "  The planted defect passed. This gate cannot detect the regression it claims "
            "to guard,",
            file=sys.stderr,
        )
        print(
            "  so it is failing itself rather than reporting a green it did not earn.",
            file=sys.stderr,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

# Lines that MUST be flagged by assertion A, and lines that must NOT. The second
# list is the one that keeps this gate alive: a probe discarding noise is
# legitimate, and a gate that forbids those gets suppressed within a week.
SUPPRESSED = (
    'git submodule update --init --recursive "$sub" 2>/dev/null',
    "git clone https://x/y 2>/dev/null",
    "  git fetch origin &>/dev/null",
    "curl -o out https://x >/dev/null 2>&1",
    "  tar xf a.tgz 2>/dev/null",
    "npm ci 2>&-",
)

NOT_SUPPRESSED = (
    "command -v jq 2>/dev/null",
    'kill -0 "$pid" 2>/dev/null',
    "ps -p 1 2>/dev/null",
    "git config --get x 2>/dev/null",
    'git submodule update --init --recursive "$sub"',
    "  # git clone https://x/y 2>/dev/null",
    "curl -o out https://x | tee log",
)


def selftest() -> int:
    """Both directions for A and C, and both directions for every mutation.

    The mutations are the part a port is most likely to get subtly wrong, so each
    one is applied to a fixture written by construction and the marker it plants
    is asserted present; then the same mutation is applied to a fixture it CANNOT
    match and the absence of the marker is asserted, which is exactly the
    `CONTROL IS VACUOUS` arm the twin fails itself on.
    """
    ctl = Controls("devcontainer-scripts", floor=24, verbose=True)

    for line in SUPPRESSED:
        ctl.truthy(
            "PLANT: a suppressed primary operation is flagged: %r" % line[:38],
            scan_suppression(line + "\n"),
        )
    for line in NOT_SUPPRESSED:
        ctl.check(
            "MIRROR: a probe or a comment is NOT flagged: %r" % line[:38],
            scan_suppression(line + "\n"),
            [],
        )

    ctl.check(
        "the offender carries its LINE NUMBER, from one",
        scan_suppression("a\nb\ngit clone x 2>/dev/null\n"),
        ["3:git clone x 2>/dev/null"],
    )

    # -- assertion C, both directions ---------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        good_c = root / "good-vscode.sh"
        good_c.write_text(
            '#!/bin/bash\n  setsid nohup "$BIN" --host x &\nkill -TERM -- "-$pgid"\n',
            encoding="utf-8",
        )
        bad_c = root / "bad-vscode.sh"
        bad_c.write_text(
            '#!/bin/bash\n  nohup "$BIN" --host x &\nkill -TERM "$pid"\n', encoding="utf-8"
        )
        sink = Reporter(silent=True)
        ctl.check("MIRROR: a process-group lifecycle passes C", assert_c(good_c, sink), 0)
        ctl.check("PLANT: a pid-only lifecycle fails C", assert_c(bad_c, sink), 1)
        ctl.check("PLANT: and it names BOTH halves", sink.count, 2)

        no_setsid = root / "no-setsid.sh"
        no_setsid.write_text('#!/bin/bash\nnohup x &\nkill -9 -- "-$pgid"\n', encoding="utf-8")
        sink = Reporter(silent=True)
        ctl.check("PLANT: setsid alone missing fails C", assert_c(no_setsid, sink), 1)
        ctl.check("and names exactly one half", sink.count, 1)

        # -- the three mutations, both directions ---------------------------
        real_init = paths.from_root(DC_REL, INIT_NAME)
        real_vscode = paths.from_root(DC_REL, VSCODE_NAME)

        a_out = root / "a.sh"
        mutate(real_init, a_out, (A_MUTATION,))
        ctl.truthy(
            "CONTROL: the A mutation lands its marker on the real file",
            A_MARKER in a_out.read_text(encoding="utf-8"),
        )
        ctl.truthy(
            "CONTROL: and the mutated copy is then flagged by A",
            scan_suppression(a_out.read_text(encoding="utf-8")),
        )
        decoy = root / "decoy.sh"
        decoy.write_text("#!/bin/bash\necho nothing to mutate here\n", encoding="utf-8")
        a_decoy = root / "a-decoy.sh"
        mutate(decoy, a_decoy, (A_MUTATION,))
        ctl.falsy(
            "MIRROR: the A mutation on a file it cannot match plants NOTHING, "
            "which is the CONTROL IS VACUOUS arm",
            A_MARKER in a_decoy.read_text(encoding="utf-8"),
        )

        b_out = root / "b.sh"
        mutate(real_init, b_out, B_MUTATIONS)
        ctl.truthy(
            "CONTROL: the B mutation lands its marker on the real file",
            B_MARKER in b_out.read_text(encoding="utf-8"),
        )
        b_decoy = root / "b-decoy.sh"
        mutate(decoy, b_decoy, B_MUTATIONS)
        ctl.falsy(
            "MIRROR: the B mutation on a decoy plants nothing",
            B_MARKER in b_decoy.read_text(encoding="utf-8"),
        )

        c_out = root / "c.sh"
        mutate(real_vscode, c_out, C_MUTATIONS)
        c_text = c_out.read_text(encoding="utf-8")
        ctl.falsy(
            "CONTROL: the C mutation removes every setsid from the real file",
            any(SETSID.search(line) for line in c_text.split("\n")),
        )
        ctl.falsy(
            "CONTROL: and every process-group kill",
            KILL_GROUP.search(c_text),
        )
        sink = Reporter(silent=True)
        ctl.check("CONTROL: the mutated copy then fails C", assert_c(c_out, sink), 1)

        # -- control_must_fail, both directions -----------------------------
        ctl.check(
            "control_must_fail returns True when the assertion rejects the plant",
            control_must_fail("fixture", lambda _r: 1),
            True,
        )
        ctl.check(
            "control_must_fail returns False when the plant PASSES",
            control_must_fail("fixture", lambda _r: 0),
            False,
        )

        # -- assertion B against the real script ----------------------------
        sink = Reporter(silent=True)
        ctl.check(
            "MIRROR: the real init-submodules.sh surfaces git's error and exits non-zero",
            assert_b(real_init, root, sink),
            0,
        )
        rc, out = run_init_against_scratch(real_init, root)
        ctl.truthy("CONTROL: the scratch superproject really does fail", rc != 0)
        ctl.truthy("CONTROL: and git's own words are in the output", GIT_ERROR.search(out))

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
