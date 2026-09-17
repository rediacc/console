"""Every CLI flag a script actually has is taught in its canonical doc.

Ported from `.ci/scripts/quality/check-cli-doc-coverage.sh`, which is not
deleted; see `rediacc_ci.quality.__init__` for why both copies live.

Why this exists. `check-ci-watch-recipe.sh`'s Check G did this for exactly one
pair (ci-trace.py / ci-watch's SKILL.md) and immediately found two real,
previously-invisible gaps (--until-final, --timeout) the moment it ran.
Generalized here (2026-08-27) to a second real pair found by the same sweep:
`scripts/ci-runner/run.ts`'s hand-rolled `switch (arg) { case '--flag': }` parser
against `docs/agent-reference/ci-gates.md`'s flag table, which was ALSO missing
three real flags (--heavy-limit, --manifest, --list) the moment this ran against
it.

Deliberately NOT folded into every self-improving skill: `testing`
(`.claude/skills/testing/SKILL.md`) is a pure router across six docs with no
single script whose CLI surface it owns, so there is nothing to flag-diff there.
And `rdc`'s CLI docs already have their own, different mechanism
(`scripts/gates/check-cli-docs.ts`, generation-based, checks the OPPOSITE direction --
no stale flag mentioned that doesn't exist) -- not reinvented here.

Extraction is genuinely per-script-family: Python argparse and this repo's own
hand-rolled TS switch/case parser look nothing alike on the page, so each PAIRS
row names which extractor reads it, rather than one regex pretending to cover
both.

Controls are built by CONSTRUCTION (a real doc copy with one real flag's mention
stripped), never by pattern-substituting real source, so rewording a target cannot
silently void them -- `check-control-vacuity.sh` exists to catch a control that
cannot fire.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THIS GATE HAS NO ENVIRONMENT SEAM, and that shapes how it is proven. Its twin
derives its root from `dirname "${BASH_SOURCE[0]}"/../../..`, so there is no
variable to point at a fixture. The differential therefore runs the twin from a
BYTE-IDENTICAL COPY placed at the same relative path inside a fixture tree, whose
`.ci/scripts/ci/ci-trace.py`, `scripts/ci-runner/run.ts` and two docs carry the
plant; the port is pointed at the same tree with `REDIACC_CI_ROOT`. The copy is
compared with `cmp` before every run, because a differential against a stale copy
of the twin proves the port matches something nobody ships. The port keeps
`REDIACC_CI_ROOT` rather than inventing a private variable: `rediacc_ci.paths`
exists precisely because eight gates had eight different names for this idea.

`grep -A1` IS A LINE-WINDOW, NOT A FILTER, and reproducing it needs saying out
loud. It emits the matching line AND the following one, so a flag whose
`add_argument(` call wraps onto the next line is still seen. A port that scanned
only matching lines would silently lose every wrapped call -- and the gate's own
comment explains why the window exists rather than a whole-file grep: "a bare
`grep -oE '\"--[a-z-]+\"'` over the whole script also matches internal subprocess
flags the script shells out to (git's `--abbrev-ref`, gh's `--repo`), which are
not the script's own CLI surface at all."

`sort -u` UNDER `LC_ALL=C`, which `scripts/lib/shadow-gate.ts` pins for both
sides. Python's `sorted()` on these ASCII strings is byte order, so the two agree;
the pin is what makes that true rather than a coincidence of the developer's
locale.

THE CONTROL'S `sed` IS A PLAIN GLOBAL SUBSTITUTION and is reproduced as
`str.replace`, including its blunt edge: replacing `--changed` also hits
`--changed-only` if such a flag existed. That over-reach makes the control
STRICTER, never weaker -- more flags go missing from the fixture, and the
assertion only asks whether the TARGET went missing -- so it is carried rather
than refined.
"""

import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# label | script | doc | extractor. One row per pair, and the extractor is named per row because argparse and a hand-rolled TS switch look nothing alike.
PAIRS = (
    (
        "ci-trace",
        ".ci/scripts/ci/ci-trace.py",
        ".claude/skills/ci-watch/SKILL.md",
        "python_argparse",
    ),
    ("ci-runner", "scripts/ci-runner/run.ts", "docs/agent-reference/ci-gates.md", "ts_switch_case"),
)

# The two extraction patterns, kept as written. `--[a-z][a-z-]*` deliberately refuses a leading digit or capital: argparse flags in this tree are lowercase, and widening the class is how a subprocess flag sneaks into the surface.
_ARGPARSE_FLAG = re.compile(r'"(--[a-z][a-z-]*)"')
_SWITCH_FLAG = re.compile(r"case '(--[a-zA-Z][a-zA-Z-]*)'")
_ADD_ARGUMENT = "add_argument("


def _colours() -> tuple[str, str, str]:
    """The twin's own colour rule: stdout is a tty AND NO_COLOR is unset.

    Not `rediacc_ci.log`, and the difference is deliberate. This gate never
    sourced `common.sh`; it writes `ok` lines to STDOUT and `✗` lines to stderr
    with its own two-colour palette, and a port that routed everything through
    the shared logger would move the `ok` lines to stderr. That is exactly the
    2026-09-06 stream swap recorded in `rediacc_ci.log`'s docstring, performed
    deliberately, which is worse than performing it by accident.
    """
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        return "\033[0;31m", "\033[0;32m", "\033[0m"
    return "", "", ""


def extract_python_argparse(script: pathlib.Path) -> list[str]:
    """Flags declared by argparse, sorted and de-duplicated.

    Scoped to the line AFTER each `add_argument(` call, not every quoted `--flag`
    in the file: see the port notes for the subprocess-flag reason. Verified
    against ci-trace.py directly before trusting it.
    """
    lines = script.read_text(encoding="utf-8", errors="replace").split("\n")
    window: set[int] = set()
    for index, line in enumerate(lines):
        if _ADD_ARGUMENT in line:
            window.add(index)
            if index + 1 < len(lines):
                window.add(index + 1)
    found: set[str] = set()
    for index in sorted(window):
        found.update(_ARGPARSE_FLAG.findall(lines[index]))
    return sorted(found)


def extract_ts_switch_case(script: pathlib.Path) -> list[str]:
    """Flags handled by this repo's OWN hand-rolled `switch (arg) { case '--flag': }`
    CLI parsers. There is no Commander or yargs in this codebase's own tooling
    scripts, which is why a parser-specific pattern is the right instrument.
    """
    text = script.read_text(encoding="utf-8", errors="replace")
    return sorted(set(_SWITCH_FLAG.findall(text)))


EXTRACTORS = {
    "python_argparse": extract_python_argparse,
    "ts_switch_case": extract_ts_switch_case,
}


class _Report:
    """The twin's `fails` counter plus its two printers, in one object.

    An object rather than a module global because two runs in one process -- which
    is what the selftest does -- must not share a counter. The bash original could
    not have that bug; a port with a module-level `FAILS` would introduce it.
    """

    def __init__(self) -> None:
        self.fails = 0
        self.red, self.green, self.nc = _colours()

    def fail(self, *parts: str) -> None:
        print("%s✗%s %s" % (self.red, self.nc, " ".join(parts)), file=sys.stderr)
        self.fails += 1

    def ok(self, message: str) -> None:
        print("%sok%s   %s" % (self.green, self.nc, message))


def check_pair(
    report: _Report,
    root: pathlib.Path,
    label: str,
    script_rel: str,
    doc_rel: str,
    extractor: str,
    tmp: pathlib.Path,
) -> None:
    """One pair: the real check, then one control built by construction."""
    script = root / script_rel
    doc = root / doc_rel

    if not script.is_file():
        report.fail("%s: %s is missing" % (label, script_rel))
        return
    if not doc.is_file():
        report.fail("%s: %s is missing" % (label, doc_rel))
        return

    flags = EXTRACTORS[extractor](script)

    # ANTI-VACUITY. Zero flags means the EXTRACTION broke, not that the script has no CLI. Reporting "every one of 0 flags is taught" would be a green over nothing, which is the shape this repo keeps finding.
    if not flags:
        report.fail(
            "%s: found ZERO flags in %s -- the extraction broke, not the script"
            % (label, script_rel)
        )
        return

    doc_text = doc.read_text(encoding="utf-8", errors="replace")
    missing = [flag for flag in flags if flag not in doc_text]
    if not missing:
        report.ok(
            "%s: every one of %d CLI flag(s) in %s is taught in %s"
            % (label, len(flags), script_rel, doc_rel)
        )
    else:
        report.fail(
            "%s: %s does not mention: %s -- a flag that exists but is"
            % (label, doc_rel, " ".join(missing)),
            "never taught is invisible to any session reading only the doc",
        )

    # CONTROL, built by construction: a REAL copy of the doc with one real flag's only mention replaced, not a synthetic fixture -- the extraction above must fire on it, or this check proves nothing.
    fixture = tmp / ("%s-doc-missing-flag" % label)
    fixture.write_text(doc_text, encoding="utf-8")
    target = ""
    for flag in flags:
        if flag in doc_text:
            target = flag
            break
    if not target:
        report.fail(
            "%s control: no flag found in the doc to remove -- the fixture cannot test anything"
            % label
        )
        return
    mutated = doc_text.replace(target, "REDACTED")
    fixture.write_text(mutated, encoding="utf-8")
    control_missing = [flag for flag in flags if flag not in mutated]
    if target in control_missing:
        report.ok("%s control: removing %s's only mention is detected" % (label, target))
    else:
        report.fail(
            "%s control: removing %s's only mention was NOT detected -- the check cannot fail"
            % (label, target)
        )


def main(argv: list[str] | None = None) -> int:
    if argv and argv[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    report = _Report()

    # The registry itself can collapse. An empty PAIRS list would run no checks and print "0 pair(s) clean", which reads as coverage.
    if not PAIRS:
        report.fail("PAIRS is empty -- the registry broke, not the docs")

    with tempfile.TemporaryDirectory() as tmp:
        scratch = pathlib.Path(tmp)
        for label, script_rel, doc_rel, extractor in PAIRS:
            check_pair(report, root, label, script_rel, doc_rel, extractor, scratch)

    print()
    if report.fails == 0:
        print("%s✓%s cli-doc-coverage: %d pair(s) clean." % (report.green, report.nc, len(PAIRS)))
        print("  Blind spot: this checks that a flag's NAME is mentioned somewhere in the")
        print("  doc, not that the mention is accurate, current, or in the right place.")
        return 0
    print("%s✗%s cli-doc-coverage: %d failure(s)." % (report.red, report.nc, report.fails))
    return 1


def selftest() -> int:
    """Plant an untaught flag, and its mirror, inside a throwaway repo root.

    `REDIACC_CI_ROOT` is what makes this possible without touching a tracked file,
    and it is the same seam the differential uses. See `rediacc_ci.paths`: one
    variable for the whole program, rather than the eight per-gate `*_ROOT` names
    it replaced.
    """
    ctl = Controls("cli-doc-coverage", floor=10, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        def expect_finding(
            py_flags: list[str], ts_flags: list[str], doc_a: str, doc_b: str
        ) -> None:
            (root / ".ci/scripts/ci").mkdir(parents=True, exist_ok=True)
            (root / ".claude/skills/ci-watch").mkdir(parents=True, exist_ok=True)
            (root / "scripts/ci-runner").mkdir(parents=True, exist_ok=True)
            (root / "docs/agent-reference").mkdir(parents=True, exist_ok=True)
            (root / ".ci/scripts/ci/ci-trace.py").write_text(
                "".join('p.add_argument(\n    "%s", help="x")\n' % f for f in py_flags),
                encoding="utf-8",
            )
            (root / "scripts/ci-runner/run.ts").write_text(
                "".join("      case '%s': break;\n" % f for f in ts_flags), encoding="utf-8"
            )
            (root / ".claude/skills/ci-watch/SKILL.md").write_text(doc_a, encoding="utf-8")
            (root / "docs/agent-reference/ci-gates.md").write_text(doc_b, encoding="utf-8")

        def run() -> int:
            saved = dict(os.environ)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                os.environ.clear()
                os.environ.update(saved)

        py = ["--json", "--until-final", "--timeout"]
        ts = ["--list", "--manifest", "--heavy-limit"]
        taught_py = "\n".join(py)
        taught_ts = "\n".join(ts)

        expect_finding(py, ts, taught_py, taught_ts)
        ctl.check("CONTROL: every flag taught is clean", run(), 0)

        # THE WRAPPED CALL. `add_argument(` on one line and the flag on the next
        # is why the twin uses `grep -A1`; a port that scanned only the matching
        # line would report 0 flags here and fail its own vacuity check.
        ctl.check(
            "WINDOW: a flag on the line AFTER add_argument( is still found",
            len(extract_python_argparse(root / ".ci/scripts/ci/ci-trace.py")),
            3,
        )

        # THE PLANT: one flag exists but is not taught, in each pair separately so a gate that only ever reads the first row is caught.
        expect_finding(py, ts, "\n".join(py[:2]), taught_ts)
        ctl.check("PLANT: an untaught argparse flag is caught", run(), 1)
        expect_finding(py, ts, taught_py, "\n".join(ts[:2]))
        ctl.check("PLANT: an untaught switch-case flag is caught", run(), 1)

        # THE MIRROR the reviewer waves through: teaching it again must go quiet.
        expect_finding(py, ts, taught_py, taught_ts)
        ctl.check("MIRROR: teaching the flag makes it clean again", run(), 0)

        # ANTI-VACUITY: a script with no flags at all. `0 of 0 taught` would be a green over nothing.
        expect_finding([], ts, taught_py, taught_ts)
        ctl.check("VACUITY: zero extracted flags is a refusal, not a clean pair", run(), 1)

        # A missing script and a missing doc are each refusals rather than skips.
        expect_finding(py, ts, taught_py, taught_ts)
        (root / ".ci/scripts/ci/ci-trace.py").unlink()
        ctl.check("VACUITY: a missing script is a refusal", run(), 1)
        expect_finding(py, ts, taught_py, taught_ts)
        (root / ".claude/skills/ci-watch/SKILL.md").unlink()
        ctl.check("VACUITY: a missing doc is a refusal", run(), 1)

        # THE CONTROL'S OWN CONTROL. A doc that teaches a flag only as part of a LONGER one still counts as a mention, because the twin's test is a substring test. Pinned so a port that "improved" it to a word-boundary match is caught: that would be a different gate.
        expect_finding(["--json"], ts, "--json-output only", taught_ts)
        ctl.check("SUBSTRING: --json is taught by a mention of --json-output", run(), 0)

        # And the shape that makes the constructed control meaningful: a doc that mentions NONE of the flags cannot supply a target, so the control reports that it could not test anything rather than passing.
        expect_finding(py, ts, "nothing relevant here", taught_ts)
        ctl.check("CONTROL VACUITY: a doc with no flag at all is a refusal", run(), 1)

    return 0 if ctl.report() else 1
