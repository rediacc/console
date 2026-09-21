"""ONE extractor, applied to both sides of the port.

WHAT THIS IS FOR. D3 moved a 2,774-line bash suite into pytest, and the acceptance was never "the diff looks right": it was that the MULTISET OF ASSERTION LABELS the ported suite emits equals the multiset the bash suite emitted, read by the same
function on both sides. A comparison of two hand-written inventories proves that two
inventories agree; a comparison of two RUNS proves that every case executed.

THE BASH SIDE IS A RECORDING NOW. `.claude/hooks/test-hooks.sh` was retired once the comparison came out even, so the right-hand argument is no longer a live run but the file that run produced: `.ci/rediacc_ci/tests/goldens/claude-hooks/label-multiset.golden`, 512 labels headed with the twin's blob sha. The extractor needs no change, because a recording of what a suite
printed and the suite printing it are the same bytes to this reader.

WHY THIS IS NOT ALSO A GATE, said plainly rather than left to be discovered. Thirty-six of those 512 labels carry a COUNT scraped out of a delegate's output ("stop/wl_git.py --selftest: 63 control(s) passed"), so a live comparison against the recording would go red on every control legitimately added to a delegated suite. A ledger somebody re-records to get past a red is not a
ledger, and the delegated counts already have a floor each in `test_hooks_delegates.py`. So the recording is EVIDENCE of the cutover, drivable by hand with the invocation below, and the standing enforcement is the floors.

WHY THE LINE, AND NOT THE SOURCE TEXT. Reading labels out of the two sources would need two different parsers -- the bash label is the fourth word-ish of a `check` call, the Python one is the third argument of `case(...)` -- and two parsers is two things that can be wrong in the same direction. Both suites PRINT the same line:

    ok   [0] raw-pr-body(blocked) (exit 0)

so one regex reads both, and a case that exists but never ran contributes nothing, which is exactly the failure a static comparison cannot see.

HOW THE PYTHON SIDE PRINTS IT. pytest captures stdout, so `record()` appends to a file named by $HOOK_LABEL_DIR instead. ONE FILE PER PROCESS, because the suite runs under `pytest -n <jobs> --dist loadgroup` and several workers append at once; a shared file would interleave partial lines and the extractor would read a corrupted label as a missing one.

    HOOK_LABEL_DIR=/tmp/labels <pytest ...>
    python3 -m rediacc_hooks.tests.hooklabels /tmp/labels \\
        .ci/rediacc_ci/tests/goldens/claude-hooks/label-multiset.golden

exits 0 when the two multisets are equal and 1 naming both differences.

THE EXPECTED DELTA AT THE RETIREMENT, measured 2026-09-21 and recorded here so a later reader is not left wondering whether a difference is a regression. 511 of the recording's 512 labels are reproduced verbatim. The 512th, `stop suites: 27 ported module(s) collected by check:ci-pytest, not re-run here`, is the harness asserting its OWN delegation and is restated by the port
as `rediacc_hooks/tests: reachable via check:ci-pytest`; the harness's self-reference died with it, the other links did not. Eleven labels appear only on the port's side, every one of them coverage added after the port (the REST and GraphQL bypass arms, the settled-question worktree cases, and the control that drives a collapsed settings entry through the expander).
"""

import collections
import os
import pathlib
import re
import sys

# `ok`/`FAIL`, the bracketed verdict, then the label. The suffix ` (exit N)` is printed by four of the nine assertion helpers and by none of the other five, so it is stripped rather than captured: a label must key the same whichever helper asserted it.
LINE_RE = re.compile(r"^(ok|FAIL)\s+\[([^\]]*)\]\s+(.*?)\s*$")
EXIT_SUFFIX_RE = re.compile(r"\s+\(exit\s+[^)]*\)$")

ENV_DIR = "HOOK_LABEL_DIR"


def labels(text: str) -> collections.Counter:
    """`Counter[(verdict, bracket, label)]` for everything `text` asserted."""
    found: collections.Counter = collections.Counter()
    for line in text.splitlines():
        match = LINE_RE.match(line)
        if not match:
            continue
        verdict, bracket, label = match.groups()
        found[(verdict, bracket, EXIT_SUFFIX_RE.sub("", label))] += 1
    return found


def read_dir(path: pathlib.Path) -> collections.Counter:
    """Every per-process label file under `path`, folded into one multiset."""
    found: collections.Counter = collections.Counter()
    for child in sorted(path.glob("labels-*.txt")):
        found += labels(child.read_text(encoding="utf-8", errors="replace"))
    return found


def record(bracket: object, label: str, *, ok: bool = True) -> None:
    """Emit one assertion line, in the bash suite's shape, if recording is on.

    A no-op when $HOOK_LABEL_DIR is unset, so an ordinary `pytest` run pays nothing.
    """
    directory = os.environ.get(ENV_DIR)
    if not directory:
        return
    target = pathlib.Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    line = "%s   [%s] %s\n" % ("ok" if ok else "FAIL", bracket, label)
    with open(target / ("labels-%d.txt" % os.getpid()), "a", encoding="utf-8") as handle:
        handle.write(line)


def _side(argument: str) -> collections.Counter:
    path = pathlib.Path(argument)
    if path.is_dir():
        return read_dir(path)
    return labels(path.read_text(encoding="utf-8", errors="replace"))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    left, right = _side(argv[0]), _side(argv[1])
    # ZERO IS A FAILURE ON EITHER SIDE. An empty extraction compares equal to another empty extraction, and that green would mean the extractor did not see a run.
    if not left or not right:
        print(
            "REFUSING: %s yielded %d label(s) and %s yielded %d. An empty side makes "
            "this comparison vacuous."
            % (argv[0], sum(left.values()), argv[1], sum(right.values())),
            file=sys.stderr,
        )
        return 1
    only_left = left - right
    only_right = right - left
    print("%s: %d label(s), %d distinct" % (argv[0], sum(left.values()), len(left)))
    print("%s: %d label(s), %d distinct" % (argv[1], sum(right.values()), len(right)))
    if not only_left and not only_right:
        print("EQUAL: the two multisets agree.")
        return 0
    for name, side in (("ONLY IN " + argv[0], only_left), ("ONLY IN " + argv[1], only_right)):
        for (verdict, bracket, label), count in sorted(side.items()):
            print("%s: %dx %s [%s] %s" % (name, count, verdict, bracket, label))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
