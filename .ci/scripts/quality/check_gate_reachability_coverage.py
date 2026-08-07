#!/usr/bin/env python3
"""Assert the Stop hook's gate-reachability probe agrees with how gates are actually registered.

WHY THIS EXISTS. On 2026-08-07 `wl_reggate.gate_reachable()` returned False for
EVERY gate in this repo -- `check:ci-shell-commands`, `check:ci-dead-bash`,
`check:ci-python-lint`, all 191 manifest registrations. It walked `npm run X`
edges between package.json script bodies starting at `ci`, but `ci` is
`tsx scripts/ci-runner/run.ts`, whose body contains no `npm run` references at
all: the runner schedules from scripts/ci-runner/manifest.ts. The walk terminated
immediately.

The cost was not a missed defect but a MANUFACTURED one. The probe told two
consecutive sessions that correctly-wired gates were "defined but never run" and
demanded they be re-wired. A probe that cannot pass is the same class as a check
that cannot fail, and it is more expensive, because it spends real work denying
something true.

WHAT THIS GUARDS. The probe now understands two registration mechanisms: npm-run
chaining, and the ci-runner manifest. Nothing forced those two to stay in sync
with reality, so a future refactor of gate registration (a third mechanism, a
renamed manifest, a changed entry shape) would silently return the probe to
blindness. This compares the probe's verdict against the registrations that exist.

ASSERTIONS
  1. FLOOR       the probe discovers a non-trivial number of manifest gates. An
                 empty set would make assertion 2 vacuously true -- the failure
                 shape this file exists to prevent, reproduced inside itself.
  2. AGREEMENT   every manifest gate that also has a check:* npm key is reported
                 reachable.
  3. CONTROL     a fabricated key is reported UNREACHABLE, so "reachable" has not
                 been widened into "always true".

CONTROL-FIRST. Simulates the pre-fix probe (manifest awareness removed) and
requires assertion 2 to FAIL against it. If the planted defect passes, this gate
declares itself broken and exits non-zero.
"""

from __future__ import annotations

import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HOOK_DIR = os.path.join(REPO_ROOT, ".claude", "hooks", "stop")

# The probe knows about 191 manifest gates today. A floor well under that catches
# "the manifest stopped parsing" without failing on ordinary gate churn.
MIN_MANIFEST_GATES = 40

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"


def die(msg: str) -> None:
    print(f"{RED}✗{NC} {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_probe():
    if not os.path.isdir(HOOK_DIR):
        die(
            f"check-gate-reachability-coverage: {HOOK_DIR} not found; cannot judge a probe that is not there"
        )
    sys.path.insert(0, HOOK_DIR)
    try:
        # Deferred deliberately: HOOK_DIR must be on sys.path first, and a
        # top-level import would make this gate uncollectable outside the repo.
        import wl_reggate  # noqa: PLC0415
    except ImportError as exc:
        die(
            f"check-gate-reachability-coverage: cannot import wl_reggate ({exc}). Refusing to pass while measuring nothing."
        )
    for fn in ("gate_reachable", "_manifest_gate_ids"):
        if not hasattr(wl_reggate, fn):
            die(
                f"check-gate-reachability-coverage: wl_reggate.{fn}() is missing (renamed? removed?). The probe's contract changed; update this gate deliberately rather than letting it pass."
            )
    return wl_reggate


def evaluate(probe, scripts, manifest_ids) -> list[str]:
    """Findings, one string per problem. Empty means the probe agrees with reality."""
    out: list[str] = []

    if len(manifest_ids) < MIN_MANIFEST_GATES:
        out.append(
            f"FLOOR: the probe found only {len(manifest_ids)} manifest gate(s), under the "
            f"{MIN_MANIFEST_GATES} floor. Manifest parsing is broken, and every agreement "
            "check below would pass while checking nothing."
        )
        return out  # everything after this would be vacuous

    checkable = sorted(g for g in manifest_ids if g.startswith("check:") and g in scripts)
    if not checkable:
        out.append("FLOOR: no manifest gate has a matching check:* npm key; nothing to agree about")
        return out

    unreachable = [g for g in checkable if not probe.gate_reachable(scripts, g, REPO_ROOT)]
    if unreachable:
        shown = ", ".join(unreachable[:5])
        more = f" (and {len(unreachable) - 5} more)" if len(unreachable) > 5 else ""
        out.append(
            f"AGREEMENT: {len(unreachable)}/{len(checkable)} registered gates are reported "
            f"UNREACHABLE: {shown}{more}. The probe cannot see how gates are registered, so "
            "it will report correctly-wired gates as 'defined but never run'."
        )
    return out


def main() -> int:
    probe = load_probe()
    try:
        with open(os.path.join(REPO_ROOT, "package.json"), encoding="utf-8") as fh:
            scripts = json.load(fh).get("scripts", {})
    except (OSError, ValueError) as exc:
        die(f"check-gate-reachability-coverage: cannot read package.json scripts ({exc})")

    manifest_ids = probe._manifest_gate_ids(REPO_ROOT)

    # --- control: the pre-fix probe, with manifest awareness removed ---------
    real_lookup = probe._manifest_gate_ids
    probe._manifest_gate_ids = lambda _root: set()
    try:
        control = evaluate(probe, scripts, manifest_ids)
    finally:
        probe._manifest_gate_ids = real_lookup
    if not control:
        die(
            "check-gate-reachability-coverage: CONTROL DID NOT FIRE. With manifest awareness "
            "removed the probe still agreed with every registration, so this gate cannot detect "
            "the blindness it exists for."
        )

    # --- the real run --------------------------------------------------------
    findings = evaluate(probe, scripts, manifest_ids)

    # A fabricated key must stay unreachable, or "reachable" has become "always true".
    if probe.gate_reachable(scripts, "check:ci-this-key-does-not-exist", REPO_ROOT):
        findings.append(
            "CONTROL: a fabricated key was reported REACHABLE. The probe now answers true for "
            "anything, which passes this gate while proving nothing about real wiring."
        )

    if findings:
        print(
            f"{RED}✗{NC} the gate-reachability probe disagrees with how gates are registered:",
            file=sys.stderr,
        )
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        print(file=sys.stderr)
        print(
            "  Fix .claude/hooks/stop/wl_reggate.py::gate_reachable so it understands every",
            file=sys.stderr,
        )
        print(
            "  registration mechanism in use. A probe that cannot pass manufactures work:",
            file=sys.stderr,
        )
        print("  it tells sessions their wired gates are unwired.", file=sys.stderr)
        return 1

    print(
        f"{GREEN}✓{NC} gate-reachability probe agrees with all {len(manifest_ids)} manifest registrations"
    )
    print(
        f"  control fired without manifest awareness ({len(control)} finding(s)), so this green means the check can fail"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
