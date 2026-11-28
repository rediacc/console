"""The slow-test ratchet: a test over 10 s fails the check unless `.ci/policy/pytest-slow-allow.json` lists it with a reason.

WHY (PLAN-ciquick-cpu.md Fix C). The 594 tests over 5 s took 68% of pytest time, and nothing stopped the next slow test from joining them. The allowlist is the baseline of the tests already that slow, each with a reason; a test not listed that runs over the threshold is a finding.

THE TIME IS THE MEDIAN OF THE RUNS GIVEN, OR THE FASTEST RE-TIME. One junit run on a loaded machine reads a 4 s test as 12 s, so the caller may pass several `--junit` files (one per run) and each test is judged on its median across the runs that contain it. One file is judged as it stands. `check_pytest.slow_ratchet` passes the parallel run as `--junit` and two serial re-runs of the `confirm_candidates` it named as `--confirm`; a test a re-time holds is judged on its fastest re-time alone (`read_timing` states why the parallel run gets no vote there).

THE ALLOWLIST ONLY SHRINKS. A listed test that no longer runs over the threshold is reported as stale (`pytest-slow-stale`) and fails only under `--strict-stale`, because a run over a subset of the suite cannot tell "faster" from "not collected". Dropping the entry is how the baseline shrinks; adding one needs a reason that names why the test cannot be made fast.

A TEST IS JUDGED ON ITS OWN TIME: its call, plus the setup that is not shared-fixture setup. junit's `time` is setup + call + teardown, so a module fixture's setup lands on the first test of its module (`test_githook_generated_artifacts` charged its 13 s `world` fixture to a test whose call took 2-4 s). The `pytest_phase_timing` plugin writes each run's phases to `<junit stem>.phases.json` beside the junit, and a test found there is judged on `setup - shared_setup + call`: function-scoped and autouse fixture setup stays the test's, any wider-scoped fixture's setup does not. Teardown is judged the same way (`teardown - shared_teardown`): a function-scoped fixture's own teardown is the test's, and a module fixture's teardown, which lands on the module's last test, is not. The shared time is printed per junit classname (a test file, or a test class within it) as information, the share no test is judged on. A junit with no phase file beside it, or a case its phase file lacks, is judged on the junit time, and the ratchet says so: a missing measurement never passes a test silently.

EXIT CODES: 0 clean, 1 a finding, 2 no verdict (no junit readable, or none with a test case that ran: a junit whose only cases are skipped has no verdict either): a ratchet that read nothing proves nothing.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import re
import statistics
import sys
import typing

from rediacc_ci import log, paths
from rediacc_ci.core import xml_trusted
from rediacc_ci.policy_paths import policy_path

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from xml.etree import ElementTree

THRESHOLD_S = 10.0
ALLOW_NAME = "pytest-slow-allow.json"
JUNIT_RELPATH = ".ci/cache/quality-pytest/junit.xml"
# A file whose shared fixture setup totals more than this is named in the information lines; below it the line is noise.
SHARED_REPORT_FLOOR_S = 1.0
SHARED_REPORT_LIMIT = 10
_KEY_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._:/@#-]")
# The xdist `@group` suffix is the trailing `@<word>` after the last parameter bracket; an `@` inside a parametrize id (`test_x[a@1]`) is part of the name. `pytest_phase_timing.GROUP_SUFFIX_RE` is the same pattern.
GROUP_SUFFIX_RE = re.compile(r"@[^@\]]*$")


def strip_group(name: str) -> str:
    """`name` without its trailing xdist `@group` suffix, an `@` inside a `[...]` parameter id kept."""
    return GROUP_SUFFIX_RE.sub("", name)


def node_of(case: ElementTree.Element) -> str:
    """`<classname>::<name>` with the xdist `@group` suffix dropped, the node `check_pytest.junit_finding_keys` names."""
    return "%s::%s" % (case.get("classname") or "", strip_group(case.get("name") or ""))


def phases_path(junit: pathlib.Path) -> pathlib.Path:
    """The phase file `pytest_phase_timing` writes for the run whose junit is `junit`: `<stem>.phases.json` beside it."""
    return junit.with_suffix(".phases.json")


def read_phases(path: pathlib.Path) -> tuple[dict[str, object], str | None]:
    """`(junit node -> phases, why it could not be read)`; the reason is None when the file was read."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "no phase file at %s" % path
    except (OSError, ValueError) as exc:
        return {}, "the phase file %s cannot be read (%s)" % (path, exc)
    tests = doc.get("tests") if isinstance(doc, dict) else None
    if not isinstance(tests, dict):
        return {}, "the phase file %s holds no `tests` table" % path
    return dict(tests), None


def own_seconds(phases: object) -> tuple[float, float] | None:
    """`(the test's own seconds, its shared-fixture setup seconds)` from one phase entry, or None when the entry is not an object or carries no usable numbers (none of setup, call and teardown).

    Own is `setup - shared_setup + call + teardown - shared_teardown`; the second number is the shared setup plus the shared teardown. An unmeasured share (null or absent) counts as zero, so the whole phase stays charged to the test.
    """
    if not isinstance(phases, dict) or all(
        phases.get(k) is None for k in ("setup", "call", "teardown")
    ):
        return None
    # CPU WHEN RECORDED (PLAN-ciquick-gate-contract K4). The plugin records each phase's CPU (the test process plus its waited children) beside the wall time; a test is judged on CPU when its call carries one, so a loaded machine stops reddening a different set of 10-16 s tests on every run (2026-11-28, ci:quick 37-45). An entry without CPU fields (an older phase file) is judged on wall time as before.
    return _own_with_suffix(phases, "_cpu" if phases.get("call_cpu") is not None else "")


def is_cpu_judged(phases: object) -> bool:
    """True when `own_seconds` of this phase entry judges CPU time (its call carries a CPU field)."""
    return isinstance(phases, dict) and phases.get("call_cpu") is not None


def wall_seconds(phases: object) -> float | None:
    """The test's own WALL seconds from one phase entry (the secondary column beside a CPU-judged time), or None when unusable."""
    split = _own_with_suffix(phases, "") if isinstance(phases, dict) else None
    return None if split is None else split[0]


def _num(value: object) -> float:
    """`value` as seconds, 0.0 when absent; a non-number raises TypeError or ValueError like `float`."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float, str)):
        return float(value) or 0.0
    raise TypeError(value)


def _own_with_suffix(phases: dict[str, object], suffix: str) -> tuple[float, float] | None:
    try:
        setup = _num(phases.get("setup" + suffix))
        call = _num(phases.get("call" + suffix))
        teardown = _num(phases.get("teardown" + suffix))
        shared = _num(phases.get("shared_setup" + suffix))
        shared_td = _num(phases.get("shared_teardown" + suffix))
    except (TypeError, ValueError):
        return None
    shared = min(max(shared, 0.0), setup)
    shared_td = min(max(shared_td, 0.0), teardown)
    return setup - shared + call + teardown - shared_td, shared + shared_td


@dataclasses.dataclass
class Timing:
    """What the runs say: each test's judged own seconds, the median shared-fixture setup charged to it, and the notes on any run judged on junit time."""

    durations: dict[str, float]
    shared: dict[str, float]
    notes: list[str]
    # Secondary column: each test's wall seconds beside the judged time, and whether the judged time is CPU. Never part of the verdict.
    wall: dict[str, float] = dataclasses.field(default_factory=dict)
    cpu_judged: set[str] = dataclasses.field(default_factory=set)


# One sample per run: (judged seconds, wall seconds, judged on CPU).
Sample = tuple[float, float, bool]


def _read_run(
    junit: pathlib.Path,
    samples: dict[str, list[Sample]],
    shared_samples: dict[str, list[float]],
    notes: list[str],
    skip_failed: bool = False,
) -> None:
    """Add one run's per-test seconds to `samples` (own time from its phase file where it holds the test, junit time otherwise) and its shared-fixture seconds to `shared_samples`. An unreadable junit adds nothing, and a skipped test no sample. With `skip_failed` a test that failed or errored adds none either: a re-time that died early at 0.1 s says nothing about the test's own cost."""
    try:
        root = xml_trusted.parse(junit)
    except (OSError, SyntaxError):  # ElementTree.ParseError is a SyntaxError
        return
    phases, unreadable = read_phases(phases_path(junit))
    if unreadable:
        notes.append(
            "%s; the tests of %s are judged on their junit time, which includes shared fixture setup"
            % (unreadable, junit)
        )
    unphased = 0
    malformed = 0
    for case in root.iter("testcase"):
        if case.find("skipped") is not None:
            continue
        if skip_failed and (case.find("failure") is not None or case.find("error") is not None):
            continue
        node = node_of(case)
        measured = own_seconds(phases[node]) if node in phases else None
        if node in phases and measured is None:
            malformed += 1
        if measured is not None:
            wall = wall_seconds(phases[node])
            samples.setdefault(node, []).append(
                (measured[0], measured[0] if wall is None else wall, is_cpu_judged(phases[node]))
            )
            shared_samples.setdefault(node, []).append(measured[1])
            continue
        try:
            seconds = float(case.get("time") or 0.0)
        except ValueError:
            continue
        if not unreadable and node not in phases:
            unphased += 1
        samples.setdefault(node, []).append((seconds, seconds, False))
    if malformed:
        notes.append(
            "%d test(s) in %s have a malformed entry in %s and are judged on their junit time"
            % (malformed, junit, phases_path(junit))
        )
    if unphased:
        notes.append(
            "%d test(s) in %s have no entry in %s and are judged on their junit time"
            % (unphased, junit, phases_path(junit))
        )


def read_timing(junits: Iterable[pathlib.Path], confirms: Iterable[pathlib.Path] = ()) -> Timing:
    """Each test's judged seconds: the fastest of its re-times where a `confirms` run holds it, the median across `junits` otherwise.

    WHY THE RE-TIMES ARE JUDGED APART (2026-11-18). The parallel run is not an independent vote on a re-timed test: the test was re-timed because that run read it over the threshold, so the median of the parallel run and two re-times was the slower re-time whenever the parallel run was the slowest of the three, and one re-time slowed by the gates `ci:quick` runs beside this one failed the test. `test_githook_generated_artifacts::test_enrolled_artifact_against_the_real_hook[enrolled_allowed-skill-reference]` read 33.5 s in the parallel run and 12.3 s as that median, while its own call took 5.4 s re-run alone. Contention only ever adds time, so the fastest re-time is the closest reading of the test's own cost, and a test whose own cost is over the threshold is over it in every re-time.
    """
    samples: dict[str, list[Sample]] = {}
    shared_samples: dict[str, list[float]] = {}
    notes: list[str] = []
    for junit in junits:
        _read_run(junit, samples, shared_samples, notes)
    retimed: dict[str, list[Sample]] = {}
    for junit in confirms:
        _read_run(junit, retimed, shared_samples, notes, skip_failed=True)
    durations = {node: statistics.median(t[0] for t in times) for node, times in samples.items()}
    wall = {node: statistics.median(t[1] for t in times) for node, times in samples.items()}
    cpu_judged = {node for node, times in samples.items() if all(t[2] for t in times)}
    for node, times in retimed.items():
        fastest = min(times, key=lambda t: t[0])
        durations[node], wall[node] = fastest[0], fastest[1]
        cpu_judged.discard(node)
        if fastest[2]:
            cpu_judged.add(node)
    return Timing(
        durations=durations,
        wall=wall,
        cpu_judged=cpu_judged,
        shared={node: statistics.median(times) for node, times in shared_samples.items()},
        notes=notes,
    )


def read_durations(junits: Iterable[pathlib.Path]) -> dict[str, float]:
    """Each test's median own seconds across `junits` (`read_timing` states the measurement)."""
    return read_timing(junits).durations


def shared_by_file(
    shared: dict[str, float], floor: float = SHARED_REPORT_FLOOR_S
) -> list[tuple[str, float]]:
    """`(junit classname, shared-fixture seconds)` per classname (a test file, or a test class within it) over `floor`, costliest first: the setup no test is judged on."""
    totals: dict[str, float] = {}
    for node, seconds in shared.items():
        classname = node.partition("::")[0]
        totals[classname] = totals.get(classname, 0.0) + seconds
    return sorted(
        ((c, s) for c, s in totals.items() if s > floor), key=lambda item: (-item[1], item[0])
    )


def read_allow(path: pathlib.Path) -> tuple[dict[str, str], list[str]]:
    """`(test -> reason, problems)`. An entry with no reason is a problem, so the list cannot become a silent skip file."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, ["cannot be read: %s" % exc]
    allowed: dict[str, str] = {}
    problems: list[str] = []
    if not isinstance(doc, dict):
        return {}, ["holds no top-level object"]
    entries = doc.get("entries") or []
    if not isinstance(entries, list):
        return {}, ["`entries` is not a list"]
    for i, entry in enumerate(entries):
        test = entry.get("test") if isinstance(entry, dict) else None
        raw_reason = entry.get("reason") if isinstance(entry, dict) else None
        reason = raw_reason.strip() if isinstance(raw_reason, str) else ""
        if not isinstance(test, str) or not test:
            problems.append("entry %d names no test" % i)
        elif not reason:
            problems.append("%s carries no reason" % test)
        elif test in allowed:
            problems.append("%s is listed twice" % test)
        else:
            allowed[test] = reason
    return allowed, problems


def over_threshold(
    durations: dict[str, float], allowed: dict[str, str], threshold: float = THRESHOLD_S
) -> tuple[list[tuple[str, float]], list[str]]:
    """`(unlisted tests over the threshold, slowest first; listed tests no longer over it, sorted)`."""
    slow = sorted(
        ((n, s) for n, s in durations.items() if s > threshold and n not in allowed),
        key=lambda item: (-item[1], item[0]),
    )
    stale = sorted(n for n in allowed if n in durations and durations[n] <= threshold)
    return slow, stale


def nodeid_of(node: str, root: pathlib.Path) -> str | None:
    """The pytest node id of a junit `<classname>::<name>` under `root`, or None when no file under `root` holds the classname's dotted path.

    An empty dotted part is a hidden directory at any depth (`.ci.rediacc_ci.tests.test_x` is `.ci/rediacc_ci/tests/test_x.py`, `tests..data.test_x` is `tests/.data/test_x.py`), and the dotted parts past the file are test classes.
    """
    classname, _, name = node.partition("::")
    parts: list[str] = []
    hidden = False
    for part in classname.split("."):
        if part == "":
            hidden = True
            continue
        parts.append("." + part if hidden else part)
        hidden = False
    for k in range(len(parts), 0, -1):
        rel = "/".join(parts[:k]) + ".py"
        if (root / rel).is_file():
            return "::".join([rel, *parts[k:], name])
    return None


def confirm_candidates(
    junit: pathlib.Path,
    root: pathlib.Path,
    allow_path: pathlib.Path | None = None,
    threshold: float = THRESHOLD_S,
) -> list[str]:
    """The pytest node ids of the unlisted tests over `threshold` in `junit`, for the caller to re-time in serial runs.

    WHY (2026-11-17). The full run is parallel, so its times carry the suite's own contention and a shared fixture's setup lands on whichever test reaches a worker first: 38 of the 40 tests that full run judged over 10 s ran between 0.0 and 9.1 s when re-run alone (`test_d1_shard_move` cases read 28 s against 0.2 s). Re-timing only the candidates in serial runs and judging each on its fastest re-time (`read_timing`) keeps the threshold about the test rather than the machine. A candidate whose file cannot be found is not re-timed and is judged on the full run alone.
    """
    allowed, _problems = read_allow(allow_path or policy_path(ALLOW_NAME, root))
    slow, _stale = over_threshold(read_durations([junit]), allowed, threshold)
    return [nodeid for node, _s in slow if (nodeid := nodeid_of(node, root)) is not None]


def describe_time(node: str, timing: Timing) -> str:
    """`11.0 s CPU (wall 14.0 s)` for a CPU-judged test, `11.0 s wall` for one judged on wall time (an older phase file or junit time)."""
    seconds = timing.durations[node]
    if node in timing.cpu_judged:
        return "%.1f s CPU (wall %.1f s)" % (seconds, timing.wall.get(node, seconds))
    return "%.1f s wall" % seconds


def finding_key(rule: str, node: str) -> str:
    key = "%s:%s" % (rule, _KEY_UNSAFE_RE.sub("#", node))
    if len(key) > 200:
        key = key[:180] + "#" + log.finding_key("n", node).split(":", 1)[1]
    return key


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument(
        "--junit",
        action="append",
        type=pathlib.Path,
        help="a junit file; repeat for each run (the median is judged). Default: the quality-pytest junit.",
    )
    parser.add_argument(
        "--confirm",
        action="append",
        type=pathlib.Path,
        default=[],
        help="a junit of a serial re-time; repeat for each. A test a re-time holds is judged on its fastest re-time, not on the --junit runs.",
    )
    parser.add_argument(
        "--allow",
        type=pathlib.Path,
        default=None,
        help="the allowlist (default: %s in the policy directory)" % ALLOW_NAME,
    )
    parser.add_argument("--threshold", type=float, default=THRESHOLD_S)
    parser.add_argument("--strict-stale", action="store_true")
    args = parser.parse_args(argv)
    root = paths.repo_root()
    junits = args.junit or [root / JUNIT_RELPATH]
    allow_path = args.allow or policy_path(ALLOW_NAME, root)

    timing = read_timing(junits, args.confirm)
    durations = timing.durations
    for note in timing.notes:
        print("pytest-slow-ratchet: note: %s" % note)
    if not durations:
        print(
            "pytest-slow-ratchet: no test case in %s, so there is no verdict to render"
            % ", ".join(str(j) for j in [*junits, *args.confirm]),
            file=sys.stderr,
        )
        return 2
    allowed, problems = read_allow(allow_path)
    for problem in problems:
        print("pytest-slow-ratchet: %s: %s" % (allow_path, problem), file=sys.stderr)
    slow, stale = over_threshold(durations, allowed, args.threshold)
    for node, _seconds in slow:
        print(
            "pytest-slow-ratchet: %s took %s (> %g s); make it fast, or list it in %s with a reason"
            % (node, describe_time(node, timing), args.threshold, ALLOW_NAME),
            file=sys.stderr,
        )
        log.emit_finding(finding_key("pytest-slow", node))
    for node in stale:
        print(
            "pytest-slow-ratchet: %s is listed in %s but now runs under %g s; drop the entry"
            % (node, ALLOW_NAME, args.threshold),
            file=sys.stderr,
        )
        if args.strict_stale:
            log.emit_finding(finding_key("pytest-slow-stale", node))
    for classname, seconds in shared_by_file(timing.shared)[:SHARED_REPORT_LIMIT]:
        print(
            "pytest-slow-ratchet: info: %s spent %.1f s in shared (module, class or session) fixture setup and teardown, which is not charged to any test"
            % (classname, seconds)
        )
    failed = bool(slow or problems or (stale and args.strict_stale))
    judged_cpu = sum(1 for n in durations if n in timing.cpu_judged)
    print(
        "pytest-slow-ratchet: %d test(s) judged over %d run(s) (%d on CPU time, %d on wall time); %d unlisted over %g s, %d stale entries"
        % (
            len(durations),
            len(junits) + len(args.confirm),
            judged_cpu,
            len(durations) - judged_cpu,
            len(slow),
            args.threshold,
            len(stale),
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
