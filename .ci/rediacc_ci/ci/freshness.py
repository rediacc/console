#!/usr/bin/env python3
"""One freshness contract for the committed artifacts a live producer rewrites from real CI data (agent/plans/PLAN-ci-consolidation.md Part B).

    PYTHONPATH=.ci python3 -m rediacc_ci.ci.freshness --check --cadence pr|nightly [--report-to FILE]
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.freshness --list
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.freshness --refresh <artifact>

THE REGISTRY is `.ci/config/freshness.json` (its `$comment` carries the schema). Each entry names one `artifact`, the `producers` that rewrite it, the `check` that compares it with fresh measurements, whether that check needs the `network`, and the `cadence`s it runs at. Before this module the two artifacts (lane-durations.json and gate-costs.json) were checked by two commands chained in package.json and two steps in housekeeping.yml, and gate_costs appended to a report budget_report's step had opened: two writers of one file, and a third artifact would have meant a third copy of each.

`--check` runs every entry whose `cadence` names the asked cadence, each from the repo root with PYTHONPATH=<root>/.ci, and exits 1 when any check exits non-zero (the summary line prints the sum of their exit codes). It is the ONLY writer of `--report-to`, which gets one section per artifact, passing or not, so a reader of a red report sees which artifact failed and what the green ones said.

REFUSALS (exit 2, and the refusal is written to `--report-to` when one was asked for, so housekeeping's issue post says why): a registry that is missing, unparseable, empty, carries an unknown key, a duplicate artifact, or a cadence outside ("pr", "nightly"); and a cadence no entry runs at, since a check that selects nothing verifies nothing. A registered artifact that does not exist is a FAILED check (exit 1), named with the `--refresh` command that produces it, never a skip. A check that cannot be spawned, or that is still running or not yet started when the run's shared `CHECK_BUDGET_S` deadline passes, is a failure too: unknown is unchecked, and unchecked is not fresh.

`--refresh <artifact>` runs that entry's producers in order with their output on this terminal, stops at the first one that fails, and refuses an artifact the registry does not name.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rediacc_ci import paths

REGISTRY_REL_PATH = ".ci/config/freshness.json"
CADENCES = ("pr", "nightly")
TOP_KEYS = frozenset({"$comment", "artifacts"})
ENTRY_KEYS = frozenset({"artifact", "producers", "check", "network", "cadence"})
# ONE deadline for every check of a run, not one per check: housekeeping's budget-check job has 10 minutes, and its report step only runs if this returns before the job is killed. Measured 2026-10-07 from a dev box: budget_report --check 280 s, gate_costs --check 17 s.
CHECK_BUDGET_S = 480
REFUSED = 2


class RegistryError(ValueError):
    """The registry cannot be trusted to say what is checked; nothing is run."""


@dataclass(frozen=True)
class Entry:
    artifact: str
    producers: tuple[tuple[str, ...], ...]
    check: tuple[str, ...]
    network: bool
    cadence: tuple[str, ...]


def _argv(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(a, str) and a for a in value):
        raise RegistryError("%s must be a non-empty list of non-empty strings (an argv)" % where)
    return tuple(value)


def parse_registry(data: Any, source: str) -> list[Entry]:
    """Validate the registry document and return its entries; every refusal names `source` and the entry."""
    if not isinstance(data, dict):
        raise RegistryError("%s is not a JSON object" % source)
    unknown_top = sorted(set(data) - TOP_KEYS)
    if unknown_top:
        raise RegistryError(
            "%s has unknown top-level key(s): %s" % (source, ", ".join(unknown_top))
        )
    raw = data.get("artifacts")
    if not isinstance(raw, list) or not raw:
        raise RegistryError(
            "%s registers ZERO artifacts. An empty registry checks nothing, so its green would mean nothing."
            % source
        )
    entries: list[Entry] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        where = "%s artifacts[%d]" % (source, i)
        if not isinstance(item, dict):
            raise RegistryError("%s is not an object" % where)
        unknown = sorted(set(item) - ENTRY_KEYS)
        if unknown:
            raise RegistryError("%s has unknown key(s): %s" % (where, ", ".join(unknown)))
        missing = sorted(ENTRY_KEYS - set(item))
        if missing:
            raise RegistryError("%s is missing key(s): %s" % (where, ", ".join(missing)))
        artifact = item["artifact"]
        if not isinstance(artifact, str) or not artifact or Path(artifact).is_absolute():
            raise RegistryError("%s artifact must be a non-empty repo-relative path" % where)
        if artifact in seen:
            raise RegistryError("%s registers %s a second time" % (where, artifact))
        seen.add(artifact)
        producers = item["producers"]
        if not isinstance(producers, list) or not producers:
            raise RegistryError(
                "%s (%s) has no producers; nothing could refresh it" % (where, artifact)
            )
        network = item["network"]
        if not isinstance(network, bool):
            raise RegistryError("%s (%s) network must be true or false" % (where, artifact))
        cadence = item["cadence"]
        if (
            not isinstance(cadence, list)
            or not cadence
            or any(c not in CADENCES for c in cadence)
            or len(set(cadence)) != len(cadence)
        ):
            raise RegistryError(
                "%s (%s) cadence must be a non-empty subset of %s, got %r"
                % (where, artifact, list(CADENCES), cadence)
            )
        entries.append(
            Entry(
                artifact=artifact,
                producers=tuple(
                    _argv(p, "%s (%s) producers[%d]" % (where, artifact, j))
                    for j, p in enumerate(producers)
                ),
                check=_argv(item["check"], "%s (%s) check" % (where, artifact)),
                network=network,
                cadence=tuple(cadence),
            )
        )
    return entries


def load_registry(root: Path) -> list[Entry]:
    path = root / REGISTRY_REL_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryError("%s does not exist" % path) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError("%s does not parse: %s" % (path, exc)) from exc
    return parse_registry(data, REGISTRY_REL_PATH)


def _env(root: Path) -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(paths.ci_dir(root))}


def run_check(argv: tuple[str, ...], root: Path, timeout: float) -> tuple[int, str]:
    """Run one check, stdout and stderr merged in order. A spawn failure or a timeout is a failing rc with the reason as its output, never an exception and never a pass."""
    try:
        proc = subprocess.run(
            list(argv),
            cwd=root,
            env=_env(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (
            124,
            "UNCHECKED: the check ran past the %.0fs left of the run's budget and was stopped.\n"
            % timeout,
        )
    except OSError as exc:
        return 127, "UNCHECKED: the check could not be started: %s\n" % exc
    return proc.returncode, proc.stdout or ""


def _section(entry: Entry, rc: int, output: str) -> str:
    verdict = "PASS" if rc == 0 else "FAIL"
    body = output if output.endswith("\n") or not output else output + "\n"
    return "=== %s: %s (rc %d) ===\n$ %s\n%s" % (
        entry.artifact,
        verdict,
        rc,
        shlex.join(entry.check),
        body or "(no output)\n",
    )


def _write_report(report_to: Path | None, text: str) -> None:
    if report_to is None:
        return
    # tree-write: safe only with an explicit --report-to (housekeeping's /tmp/budget-check.txt), which check:ci-budget-freshness never passes
    report_to.write_text(text, encoding="utf-8")


def check(
    entries: list[Entry],
    cadence: str,
    root: Path,
    *,
    report_to: Path | None = None,
    budget_s: float = CHECK_BUDGET_S,
) -> int:
    selected = [e for e in entries if cadence in e.cadence]
    skipped = [e for e in entries if cadence not in e.cadence]
    if not selected:
        msg = (
            "freshness --check: REFUSED. No registered artifact runs at cadence %r (%d registered); "
            "a check that selects nothing verifies nothing.\n" % (cadence, len(entries))
        )
        sys.stderr.write(msg)
        _write_report(report_to, msg)
        return REFUSED
    sections: list[str] = []
    failed: list[tuple[str, int]] = []
    rc_sum = 0
    deadline = time.monotonic() + budget_s
    for entry in selected:
        left = deadline - time.monotonic()
        if left <= 0:
            rc, output = (
                124,
                "UNCHECKED: the run's %.0fs budget was spent before this check started.\n"
                % budget_s,
            )
        elif not (root / entry.artifact).is_file():
            rc = 1
            output = (
                "%s does not exist. A registered artifact that is missing is unchecked, not fresh; "
                "produce it with `PYTHONPATH=.ci python3 -m rediacc_ci.ci.freshness --refresh %s`.\n"
                % (entry.artifact, entry.artifact)
            )
        else:
            rc, output = run_check(entry.check, root, left)
        section = _section(entry, rc, output)
        sys.stdout.write(section)
        sys.stdout.flush()
        sections.append(section)
        rc_sum += rc
        if rc != 0:
            failed.append((entry.artifact, rc))
    sections.extend(
        "=== %s: skipped (cadence %s only) ===\n" % (entry.artifact, ", ".join(entry.cadence))
        for entry in skipped
    )
    if failed:
        verdict = (
            "freshness --check --cadence %s: %d of %d artifact(s) FAILED (exit codes sum %d): %s\n"
            % (
                cadence,
                len(failed),
                len(selected),
                rc_sum,
                ", ".join("%s (rc %d)" % f for f in failed),
            )
        )
        sys.stderr.write(verdict)
    else:
        verdict = (
            "freshness --check --cadence %s: %d artifact(s) fresh, %d skipped at this cadence.\n"
            % (
                cadence,
                len(selected),
                len(skipped),
            )
        )
        sys.stdout.write(verdict)
    _write_report(report_to, "".join(sections) + verdict)
    return 1 if failed else 0


def list_entries(entries: list[Entry]) -> int:
    for e in entries:
        print(
            "%s\n  cadence: %s\n  network: %s\n  check:   %s"
            % (e.artifact, ", ".join(e.cadence), "yes" if e.network else "no", shlex.join(e.check))
        )
        for p in e.producers:
            print("  produce: %s" % shlex.join(p))
    print("%d artifact(s) registered in %s" % (len(entries), REGISTRY_REL_PATH))
    return 0


def refresh(entries: list[Entry], artifact: str, root: Path) -> int:
    match = [e for e in entries if e.artifact == artifact]
    if not match:
        sys.stderr.write(
            "freshness --refresh: %r is not registered in %s; registered: %s\n"
            % (artifact, REGISTRY_REL_PATH, ", ".join(e.artifact for e in entries))
        )
        return REFUSED
    entry = match[0]
    for i, argv in enumerate(entry.producers, start=1):
        print(
            "freshness --refresh %s: producer %d of %d: %s"
            % (artifact, i, len(entry.producers), shlex.join(argv))
        )
        sys.stdout.flush()
        try:
            rc = subprocess.run(list(argv), cwd=root, env=_env(root), check=False).returncode
        except OSError as exc:
            sys.stderr.write("freshness --refresh: producer could not be started: %s\n" % exc)
            return 1
        if rc != 0:
            sys.stderr.write(
                "freshness --refresh %s: producer %d (%s) exited %d; later producers were not run.\n"
                % (artifact, i, shlex.join(argv), rc)
            )
            return 1
    if not (root / artifact).is_file():
        sys.stderr.write(
            "freshness --refresh %s: every producer exited 0 and the artifact still does not exist.\n"
            % artifact
        )
        return 1
    print("freshness --refresh %s: %d producer(s) ran." % (artifact, len(entry.producers)))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="freshness",
        description="Check, list or refresh the committed artifacts registered in .ci/config/freshness.json.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true", help="run every check at --cadence; exit 1 on any failure"
    )
    mode.add_argument("--list", action="store_true", help="print the registry")
    mode.add_argument(
        "--refresh", metavar="ARTIFACT", default=None, help="run ARTIFACT's producers in order"
    )
    parser.add_argument(
        "--cadence", choices=CADENCES, default=None, help="with --check: which entries run"
    )
    parser.add_argument(
        "--report-to",
        type=Path,
        default=None,
        help="with --check: write the per-artifact report here",
    )
    args = parser.parse_args(argv)
    if args.check and args.cadence is None:
        parser.error("--check needs --cadence (pr or nightly)")
    if not args.check and (args.cadence is not None or args.report_to is not None):
        parser.error("--cadence and --report-to go with --check only")
    root = paths.repo_root()
    try:
        entries = load_registry(root)
    except RegistryError as exc:
        msg = "freshness: REFUSED. %s\n" % exc
        sys.stderr.write(msg)
        if args.check:
            _write_report(args.report_to, msg)
        return REFUSED
    if args.list:
        return list_entries(entries)
    if args.refresh is not None:
        return refresh(entries, args.refresh, root)
    return check(entries, args.cadence, root, report_to=args.report_to)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
