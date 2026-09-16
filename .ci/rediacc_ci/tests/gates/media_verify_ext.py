"""The four `.ci/media/verify.sh` helpers `media_verify.py` does not carry yet.

`media_chain_probe`, `media_chain_mutate`, `media_chain_run` and
`media_assert_absent_from_origins`.

WHY A SECOND MODULE RATHER THAN FOUR MORE FUNCTIONS IN `media_verify.py`.
`media_verify.py` says in its own docstring that a later batch porting a chain
test "adds those three here rather than building a second sandbox", and that is
the right home. This batch is not allowed to edit tracked files under its brief,
and `media_verify.py` is tracked and clean, so the three land beside it instead
of inside it, and `media_chain_sandbox` is IMPORTED from there rather than
copied. There is still exactly one sandbox builder, which is the property the
note was protecting; only the file boundary differs. Fold this module into
`media_verify.py` whenever that file is next opened for writing.

WHAT THE CHAIN PROVES, restated from the bash header because it is the reason
these three exist at all. A stub defined next to the call site would prove only
that `media-entry.sh`'s case tree routes. A marker planted INSIDE THE MODULE
FUNCTION'S OWN BODY proves the interpreter got as far as reading THAT FILE for
THAT NAME, having crossed `./run.sh`'s `exec`. Nothing downstream of the marker
runs, which is what keeps a probe of `www tutorials record` from wanting a VM.

WHERE THIS REIMPLEMENTS awk AND sed, AND WHY THE ANSWERS AGREE.

  `media_chain_probe` is an awk program whose only predicate is
  `$0 == NAME "() {"` -- a WHOLE-LINE equality against a literal, with no regex
  anywhere -- and which prints one inserted line after the FIRST match (`!done`).
  `probe()` below is the same predicate spelled `line == "%s() {" % name` over
  `splitlines()`, inserting after the first match and refusing when there is
  none. The awk `END { if (!done) ... exit 1 }` arm is the refusal; a Python
  return of False would be a silent skip, so it raises instead.

  `media_chain_mutate` is `sed <expr>`, and the two call sites this batch needs
  pass `s|^        www) exec .*|...|` and `s/^provision_start() {/..._RENAMED() {/`
  -- both anchored substitutions over whole lines. Rather than shell out to sed
  and inherit its dialect, `mutate()` takes a compiled pattern and a replacement
  and applies `re.sub` per line, then REFUSES when nothing changed. That refusal
  is stricter than sed, which exits 0 having matched nothing, and it is the
  difference between a control that fires and a control that reports green
  because its anchor moved. `chmod +x` is preserved because the mutated file is
  usually `run.sh` and the next step executes it.

  `media_chain_run` is `"$BASH" "$repo/$script" "$@" 2>&1`, merged, with the
  status returned. `run()` returns the `RunResult` so a caller can read
  `.combined` (what `LAST_CHAIN` held) and `.rc` separately. The MEDIA_COVERAGE_FILE
  arm of the bash version is NOT ported: it exists so the bash suite's own
  coverage probe can trace a chain run, and the Python side has no such probe.
  Its absence is visible rather than assumed -- `run()` refuses if the variable
  is set, instead of quietly tracing nothing.
"""

import os
import pathlib
import re
import shutil

from rediacc_ci.tests.gates import harness
from rediacc_ci.tests.gates.media_verify import (
    _BASH,
    MEDIA_DIR,
    media_chain_sandbox,
    media_origins,
)

__all__ = [
    "absent_from_origins",
    "assert_absent_from_origins",
    "media_chain_sandbox",
    "mutate",
    "probe",
    "run",
]


class ChainError(Exception):
    """What the bash helpers signal by writing to stderr and returning 1."""


def probe(repo: pathlib.Path, module: str, name: str) -> None:
    """Restore `module` from the real folder, then make `name()`'s first act a marker.

    RESTORING FIRST is not tidiness: the twin's route table plants sixteen probes
    into ONE sandbox, one after another, and without the restore each probe would
    stack on the last one's marker and every row after the first would report the
    wrong function's name.
    """
    source = MEDIA_DIR / module
    if not source.is_file():
        raise ChainError("media_chain_probe: no such module: %s" % source)
    lines = source.read_text(encoding="utf-8").splitlines()
    opening = "%s() {" % name
    out: list[str] = []
    done = False
    for line in lines:
        out.append(line)
        if not done and line == opening:
            out.append('    echo "MEDIA_CHAIN_REACHED:%s:$*"; return 0' % name)
            done = True
    if not done:
        raise ChainError("media_chain_probe: %s() not found in %s" % (name, module))
    target = repo / ".ci" / "media" / module
    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    shutil.copystat(source, target)


def mutate(repo: pathlib.Path, relative: str, pattern: str, replacement: str) -> None:
    """One anchored line substitution in a sandbox file, REFUSING a no-op.

    `sed` exits 0 when its expression matched nothing, which is exactly how a
    control comes to pass for the wrong reason after its anchor moves. This
    raises instead, so an anchor that has drifted is a red naming the anchor.
    """
    target = repo / relative
    if not target.is_file():
        raise ChainError("media_chain_mutate: no such file: %s" % target)
    compiled = re.compile(pattern)
    original = target.read_text(encoding="utf-8")
    lines = original.splitlines()
    changed = 0
    for index, line in enumerate(lines):
        new = compiled.sub(replacement, line)
        if new != line:
            lines[index] = new
            changed += 1
    if changed == 0:
        raise ChainError(
            "media_chain_mutate: %r matched no line in %s, so the control it sets up "
            "would pass for the wrong reason" % (pattern, relative)
        )
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    target.chmod(target.stat().st_mode | 0o111)


def run(repo: pathlib.Path, script: str, *argv: str) -> harness.RunResult:
    """The sandbox's own `./run.sh` or `./media.sh`, streams MERGED as in bash.

    Called from inside `harness.fake_bin`, so PATH holds only what the test
    admitted -- for the whole chain that is `uname` and `dirname` and nothing
    else. Measured, not assumed: run.sh resolves ROOT_DIR with dirname on its
    first line, and .ci/scripts/lib/common.sh runs detect_os at source time.
    """
    if os.environ.get("MEDIA_COVERAGE_FILE"):
        raise ChainError(
            "MEDIA_COVERAGE_FILE is set, but the Python chain runner has no xtrace arm: "
            "it would run the chain and record NOTHING, which reads as covered. The bash "
            "twin's coverage seam is what that variable is for."
        )
    return harness.run([_BASH, str(repo / script), *argv])


def assert_absent_from_origins(gate, pattern: str, root: pathlib.Path, message: str) -> None:
    """`media_assert_absent_from_origins`. The non-function half of the cutover invariant.

    TUTORIAL_COLS, `_BRIDGE_SSH_CONFIG` and the tutorials usage string are not
    functions, so `media_assert_sole_owner` cannot see them; this asserts the same
    thing for a PATTERN, over the same origin set, with the same refusal to treat a
    missing origin as a clean one.

    NO `-F` FLAG HERE, AND THAT IS THE POINT OF THE SIGNATURE. The bash version
    takes an optional `-F` and forwards it to grep, because one caller hunts a fixed
    string containing `[record|extract|...]`, which as a basic regular expression is
    a bracket expression matching ONE CHARACTER -- so the unflagged form would look
    for something else entirely and answer "not present" whatever the file held. In
    Python the two cases are `re.search` and `in`, and rather than reproduce a flag
    whose omission is silent, the caller passes an already-escaped pattern (or
    `re.escape(...)`) and this always treats it as a regex. The fixed-string caller
    therefore cannot get it wrong by forgetting a flag; it gets it wrong loudly, by
    the pattern not compiling or by matching nothing where it should match.

    `media_origins` returns the complaints about missing origins rather than
    raising, so this is where "a file nobody read" becomes a FAILURE.
    """
    gate.assertions += 1
    problem = absent_from_origins(pattern, root)
    if problem:
        gate.log_fail("%s (%s)" % (message, problem))


def absent_from_origins(pattern: str, root: pathlib.Path) -> str | None:
    """None when the pattern is absent from every origin, else the ONE reason it is not.

    SPLIT OUT OF THE ASSERTION SO A CONTROL CAN OBSERVE IT. The bash twin has the
    same problem and solves it the same way, by running the assertion in a SUBSHELL
    (`_absence_verdict`) so that `log_fail`'s `exit` takes down the subshell rather
    than the gate. A Python `log_fail` RAISES, so catching it would work too and
    would be worse: an exception caught by a control is indistinguishable from an
    exception raised by a bug in the control. Returning the reason makes both
    directions ordinary values.
    """
    origins, missing = media_origins(root)
    if missing:
        return (
            "the origin set is incomplete, so absence could not be established -- %s" % (missing[0])
        )
    compiled = re.compile(pattern)
    for origin in origins:
        for number, line in enumerate(origin.read_text(encoding="utf-8").splitlines(), start=1):
            if compiled.search(line):
                return "%s:%d: %s" % (origin.name, number, line.strip())
    return None
