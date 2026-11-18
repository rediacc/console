"""The slow-test ratchet: a test over 10 s fails the check unless `.ci/policy/pytest-slow-allow.json` lists it with a reason.

WHY (PLAN-ciquick-cpu.md Fix C). The 594 tests over 5 s took 68% of pytest time, and nothing stopped the next slow test from joining them. The allowlist is the baseline of the tests already that slow, each with a reason; a test not listed that runs over the threshold is a finding.

THE TIME IS THE MEDIAN OF THE RUNS GIVEN, OR THE FASTEST RE-TIME. One junit run on a loaded machine reads a 4 s test as 12 s, so the caller may pass several `--junit` files (one per run) and each test is judged on its median across the runs that contain it. One file is judged as it stands. `check_pytest.slow_ratchet` passes the parallel run as `--junit` and two serial re-runs of the `confirm_candidates` it named as `--confirm`; a test a re-time holds is judged on its fastest re-time alone (`read_timing` states why the parallel run gets no vote there).

THE ALLOWLIST ONLY SHRINKS. A listed test that no longer runs over the threshold is reported as stale (`pytest-slow-stale`) and fails only under `--strict-stale`, because a run over a subset of the suite cannot tell "faster" from "not collected". Dropping the entry is how the baseline shrinks; adding one needs a reason that names why the test cannot be made fast.

A TEST IS JUDGED ON ITS OWN TIME: its call, plus the setup that is not shared-fixture setup. junit's `time` is setup + call + teardown, so a module fixture's setup lands on the first test of its module (`test_githook_generated_artifacts` charged its 13 s `world` fixture to a test whose call took 2-4 s). The `pytest_phase_timing` plugin writes each run's phases to `<junit stem>.phases.json` beside the junit, and a test found there is judged on `setup - shared_setup + call`: function-scoped and autouse fixture setup stays the test's, any wider-scoped fixture's setup does not. Teardown is judged the same way (`teardown - shared_teardown`): a function-scoped fixture's own teardown is the test's, and a module fixture's teardown, which lands on the module's last test, is not. The shared time is printed per junit classname (a test file, or a test class within it) as information, the share no test is judged on. A junit with no phase file beside it, or a case its phase file lacks, is judged on the junit time, and the ratchet says so: a missing measurement never passes a test silently.

EXIT CODES: 0 clean, 1 a finding, 2 no verdict (no junit readable, or none with a test case in it): a ratchet that read nothing proves nothing.
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


def node_of(case: ElementTree.Element) -> str:
    """`<classname>::<name>` with the xdist `@group` suffix dropped, the node `check_pytest.junit_finding_keys` names."""
    name = (case.get("name") or "").split("@", 1)[0]
    return "%s::%s" % (case.get("classname") or "", name)


def phases_path(junit: pathlib.Path) -> pathlib.Path:
    """The phase file `pytest_phase_timing` writes for the run whose junit is `junit`: `<stem>.phases.json` beside it."""
    return junit.with_suffix(".phases.json")


def read_phases(path: pathlib.Path) -> tuple[dict[str, dict], str | None]:
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
    return {k: v for k, v in tests.items() if isinstance(v, dict)}, None


def own_seconds(phases: dict) -> tuple[float, float] | None:
    """`(the test's own seconds, its shared-fixture setup seconds)` from one phase entry, or None when the entry carries no usable numbers.

    Own is `setup - shared_setup + call + teardown - shared_teardown`; the second number is the shared setup plus the shared teardown. An unmeasured share (null or absent) counts as zero, so the whole phase stays charged to the test.
    """
    try:
        setup = float(phases.get("setup") or 0.0)
        call = float(phases.get("call") or 0.0)
        teardown = float(phases.get("teardown") or 0.0)
        shared = float(phases.get("shared_setup") or 0.0)
        shared_td = float(phases.get("shared_teardown") or 0.0)
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


def _read_run(
    junit: pathlib.Path,
    samples: dict[str, list[float]],
    shared_samples: dict[str, list[float]],
    notes: list[str],
) -> None:
    """Add one run's per-test seconds to `samples` (own time from its phase file where it holds the test, junit time otherwise) and its shared-fixture seconds to `shared_samples`. An unreadable junit adds nothing, and a skipped test no sample."""
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
        node = node_of(case)
        measured = own_seconds(phases[node]) if node in phases else None
        if node in phases and measured is None:
            malformed += 1
        if measured is not None:
            samples.setdefault(node, []).append(measured[0])
            shared_samples.setdefault(node, []).append(measured[1])
            continue
        try:
            seconds = float(case.get("time") or 0.0)
        except ValueError:
            continue
        if not unreadable and node not in phases:
            unphased += 1
        samples.setdefault(node, []).append(seconds)
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
    samples: dict[str, list[float]] = {}
    shared_samples: dict[str, list[float]] = {}
    notes: list[str] = []
    for junit in junits:
        _read_run(junit, samples, shared_samples, notes)
    retimed: dict[str, list[float]] = {}
    for junit in confirms:
        _read_run(junit, retimed, shared_samples, notes)
    durations = {node: statistics.median(times) for node, times in samples.items()}
    durations.update({node: min(times) for node, times in retimed.items()})
    return Timing(
        durations=durations,
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
    for i, entry in enumerate(doc.get("entries") or []):
        test = entry.get("test") if isinstance(entry, dict) else None
        reason = (entry.get("reason") or "").strip() if isinstance(entry, dict) else ""
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

    A leading dot is a hidden directory (`.ci.rediacc_ci.tests.test_x` is `.ci/rediacc_ci/tests/test_x.py`), and the dotted parts past the file are test classes.
    """
    classname, _, name = node.partition("::")
    parts = classname.split(".")
    if len(parts) > 1 and parts[0] == "":
        parts = ["." + parts[1], *parts[2:]]
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
    for node, seconds in slow:
        print(
            "pytest-slow-ratchet: %s took %.1f s (> %g s); make it fast, or list it in %s with a reason"
            % (node, seconds, args.threshold, ALLOW_NAME),
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
    print(
        "pytest-slow-ratchet: %d test(s) judged over %d run(s); %d unlisted over %g s, %d stale entries"
        % (len(durations), len(junits) + len(args.confirm), len(slow), args.threshold, len(stale))
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
