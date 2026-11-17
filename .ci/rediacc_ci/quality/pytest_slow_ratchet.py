"""The slow-test ratchet: a test over 10 s fails the check unless `.ci/policy/pytest-slow-allow.json` lists it with a reason.

WHY (PLAN-ciquick-cpu.md Fix C). The 594 tests over 5 s took 68% of pytest time, and nothing stopped the next slow test from joining them. The allowlist is the baseline of the tests already that slow, each with a reason; a test not listed that runs over the threshold is a finding.

THE TIME IS THE MEDIAN OF THE RUNS GIVEN. One junit run on a loaded machine reads a 4 s test as 12 s, so the caller passes up to three `--junit` files (one per run) and each test is judged on its median across the runs that contain it. One file is judged as it stands.

THE ALLOWLIST ONLY SHRINKS. A listed test that no longer runs over the threshold is reported as stale (`pytest-slow-stale`) and fails only under `--strict-stale`, because a run over a subset of the suite cannot tell "faster" from "not collected". Dropping the entry is how the baseline shrinks; adding one needs a reason that names why the test cannot be made fast.

EXIT CODES: 0 clean, 1 a finding, 2 no verdict (no junit readable, or none with a test case in it): a ratchet that read nothing proves nothing.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys
import typing

from rediacc_ci import log, paths
from rediacc_ci.core import xml_trusted

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from xml.etree import ElementTree

THRESHOLD_S = 10.0
ALLOW_RELPATH = ".ci/policy/pytest-slow-allow.json"
JUNIT_RELPATH = ".ci/cache/quality-pytest/junit.xml"
_KEY_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._:/@#-]")


def node_of(case: ElementTree.Element) -> str:
    """`<classname>::<name>` with the xdist `@group` suffix dropped, the node `check_pytest.junit_finding_keys` names."""
    name = (case.get("name") or "").split("@", 1)[0]
    return "%s::%s" % (case.get("classname") or "", name)


def read_durations(junits: Iterable[pathlib.Path]) -> dict[str, float]:
    """Each test's median seconds across `junits`; an unreadable file counts as absent, and a skipped test as no run."""
    samples: dict[str, list[float]] = {}
    for junit in junits:
        try:
            root = xml_trusted.parse(junit)
        except (OSError, SyntaxError):  # ElementTree.ParseError is a SyntaxError
            continue
        for case in root.iter("testcase"):
            if case.find("skipped") is not None:
                continue
            try:
                seconds = float(case.get("time") or 0.0)
            except ValueError:
                continue
            samples.setdefault(node_of(case), []).append(seconds)
    return {node: statistics.median(times) for node, times in samples.items()}


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
        "--allow",
        type=pathlib.Path,
        default=None,
        help="the allowlist (default: %s)" % ALLOW_RELPATH,
    )
    parser.add_argument("--threshold", type=float, default=THRESHOLD_S)
    parser.add_argument("--strict-stale", action="store_true")
    args = parser.parse_args(argv)
    root = paths.repo_root()
    junits = args.junit or [root / JUNIT_RELPATH]
    allow_path = args.allow or root / ALLOW_RELPATH

    durations = read_durations(junits)
    if not durations:
        print(
            "pytest-slow-ratchet: no test case in %s, so there is no verdict to render"
            % ", ".join(str(j) for j in junits),
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
            % (node, seconds, args.threshold, ALLOW_RELPATH),
            file=sys.stderr,
        )
        log.emit_finding(finding_key("pytest-slow", node))
    for node in stale:
        print(
            "pytest-slow-ratchet: %s is listed in %s but now runs under %g s; drop the entry"
            % (node, ALLOW_RELPATH, args.threshold),
            file=sys.stderr,
        )
        if args.strict_stale:
            log.emit_finding(finding_key("pytest-slow-stale", node))
    failed = bool(slow or problems or (stale and args.strict_stale))
    print(
        "pytest-slow-ratchet: %d test(s) judged over %d run(s); %d unlisted over %g s, %d stale entries"
        % (len(durations), len(junits), len(slow), args.threshold, len(stale))
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
