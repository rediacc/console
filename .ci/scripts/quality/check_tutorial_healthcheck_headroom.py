#!/usr/bin/env python3
"""check:ci-tutorial-healthcheck-headroom - no tutorial app may be sized for a fast host only.

WHY THIS EXISTS
---------------
Recording the 18-tutorial suite aborted at tutorial 9 with `container pgadmin is
unhealthy` the moment the recording host was downclocked. Nothing was wrong with
the tutorial: pgAdmin's healthcheck allowed `start_period: 120s` plus 10 retries
at 3s, a total startup budget of 150 seconds, and on a slower CPU pgAdmin's first
boot (Python imports plus schema migration) simply takes longer than that. The
whole run died, non-resumably, on a number somebody picked while watching a fast
machine.

That number is invisible to every other gate. The compose file is valid, the
tutorial script is correct, the app works. Only a slow host disagrees, and no CI
gate runs the suite on one.

WHAT THIS CHECKS
----------------
The startup budget of every healthcheck under `.ci/tutorials/apps/`:

    budget = start_period + interval * retries

must be at least MIN_BUDGET_SECONDS. That single number is what actually governs
whether a container is allowed to be slow, and it is the one both knobs feed, so
checking it catches a tightening of either.

WHY 180 SECONDS
---------------
Evidence, not taste: the configuration observed to FAIL had a budget of exactly
150s. A floor must exceed a value proven insufficient, so 180 leaves 20% headroom
above the known-bad point. Raise it if a slower host is ever adopted; never lower
it to make a red gate green.

Widening a window costs a fast machine NOTHING. Failures inside `start_period` do
not count against `retries`, and a container is marked healthy the instant a check
passes, so the extra budget is engaged only when the host is actually slow.

CONTROL-FIRST
-------------
`--selftest` plants both a too-tight and a generous healthcheck and requires the
detector to flag exactly the tight one. Finding no compose files at all is a hard
FAILURE, not a pass: a headroom check with nothing to check asserts nothing.
"""

from __future__ import annotations

import glob
import os
import sys
import tempfile

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, must be loud
    print("FAIL: PyYAML is required for this gate but is not installed", file=sys.stderr)
    sys.exit(1)

MIN_BUDGET_SECONDS = 180.0

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
APPS_GLOB = os.path.join(REPO, ".ci", "tutorials", "apps", "**", "docker-compose.y*ml")

# Compose defaults, from the Compose spec. Used when a key is omitted.
DEFAULT_INTERVAL = 30.0
DEFAULT_RETRIES = 3


def duration_seconds(value, default: float) -> float:
    """Parse a Compose duration ('30s', '1m30s', 90) into seconds."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    units = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
    total = 0.0
    number = ""
    unit = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            if unit:
                total += float(number) * units.get(unit, 1.0)
                number, unit = "", ""
            number += ch
        else:
            unit += ch
    if number:
        total += float(number) * units.get(unit or "s", 1.0)
    return total


def budgets_for(path: str):
    """Yield (service, budget_seconds, detail) for every healthcheck in one file."""
    with open(path, encoding="utf-8") as handle:
        doc = yaml.safe_load(handle) or {}
    for name, service in (doc.get("services") or {}).items():
        health = (service or {}).get("healthcheck")
        if not health or health.get("disable"):
            continue
        start = duration_seconds(health.get("start_period"), 0.0)
        interval = duration_seconds(health.get("interval"), DEFAULT_INTERVAL)
        retries = int(health.get("retries", DEFAULT_RETRIES))
        budget = start + interval * retries
        detail = f"start_period={start:g}s + interval={interval:g}s x retries={retries}"
        yield name, budget, detail


def scan(paths):
    """Return (findings, checked_count)."""
    findings = []
    checked = 0
    for path in paths:
        for name, budget, detail in budgets_for(path):
            checked += 1
            if budget < MIN_BUDGET_SECONDS:
                rel = os.path.relpath(path, REPO)
                findings.append(
                    f"{rel}::{name} allows only {budget:g}s to become healthy "
                    f"({detail}); floor is {MIN_BUDGET_SECONDS:g}s"
                )
    return findings, checked


def selftest() -> int:
    """Plant a too-tight and a generous healthcheck; flag exactly the tight one."""
    tight = """
services:
  slowboot:
    image: example
    healthcheck:
      test: ["CMD", "true"]
      interval: 3s
      retries: 10
      start_period: 120s
"""
    generous = """
services:
  patient:
    image: example
    healthcheck:
      test: ["CMD", "true"]
      interval: 3s
      retries: 30
      start_period: 300s
"""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        tight_path = os.path.join(tmp, "docker-compose.yml")
        generous_path = os.path.join(tmp, "docker-compose.yaml")
        with open(tight_path, "w", encoding="utf-8") as handle:
            handle.write(tight)
        with open(generous_path, "w", encoding="utf-8") as handle:
            handle.write(generous)

        findings, checked = scan([tight_path])
        if len(findings) == 1 and "slowboot" in findings[0]:
            print("  ok    a 150s budget (the configuration that actually failed) is FLAGGED")
        else:
            print(f"  FAIL  expected exactly 1 finding for the tight healthcheck, got {findings}")
            ok = False

        findings, checked = scan([generous_path])
        if not findings and checked == 1:
            print("  ok    a 390s budget is accepted, and was actually inspected")
        else:
            print(
                f"  FAIL  generous healthcheck should pass and be counted; {findings=} {checked=}"
            )
            ok = False

        findings, checked = scan([])
        if checked == 0:
            print("  ok    an empty file set yields zero inspections (drives the vacuity guard)")
        else:
            print(f"  FAIL  empty file set reported {checked} inspections")
            ok = False

    print(
        f"\nselftest: {'passed' if ok else 'FAILED'} -- the detector fires on the known-bad value"
    )
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        print("Tutorial Healthcheck Headroom -- selftest")
        print("=" * 60)
        return selftest()

    print("Tutorial Healthcheck Headroom")
    print("=" * 60)

    paths = sorted(glob.glob(APPS_GLOB, recursive=True))
    if not paths:
        print(
            f"FAIL: required subject missing -- no compose files under "
            f".ci/tutorials/apps/. A headroom check with nothing to check asserts "
            f"nothing and must not report success.",
            file=sys.stderr,
        )
        return 1

    findings, checked = scan(paths)
    if checked == 0:
        print(
            "FAIL: required subject missing -- found compose files but not one "
            "healthcheck among them. Either they regressed or this gate is looking "
            "in the wrong place; both are failures, not a pass.",
            file=sys.stderr,
        )
        return 1

    print(
        f"{checked} healthcheck(s) in {len(paths)} compose file(s); floor {MIN_BUDGET_SECONDS:g}s"
    )

    if findings:
        print(f"\n✗ {len(findings)} healthcheck(s) sized for a fast host only:", file=sys.stderr)
        for finding in findings:
            print(f"    - {finding}", file=sys.stderr)
        print(
            "\n  Widen start_period or retries. This costs a fast machine nothing: "
            "start_period failures do not count against retries, and the container "
            "goes healthy the moment a check passes.",
            file=sys.stderr,
        )
        return 1

    print("\n✓ every tutorial healthcheck leaves room for a slow host.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
