#!/usr/bin/env python3
"""A workflow step that RUNS node must have node set up EARLIER in its job.

WHY THIS EXISTS. Run 33125687081 on 0827-1: `Quality / Code` died with
`sh: 1: tsx: not found`, exit 127, on check:ci-gate-manifest. The watchdog then
cancelled seven sibling jobs, so one missing dependency presented as most of CI
going red while those seven reported no verdict at all.

The job did `actions/checkout` and nothing else, which was correct for years:
every step in it was a shell script needing no node. Two tsx gates were added to
it and nothing noticed that the job could not run them.

WHY NO EXISTING GATE CATCHES IT. Every developer tree already has node_modules,
so both gates pass locally and in the lane. The dependency only fails where the
tree is built from scratch, which is the one place nobody watches interactively.
check:ci-parity proves a gate is WIRED into a workflow; it says nothing about
whether the job it landed in can execute it. That is the gap: wired and runnable
are different claims, and only the first was checked.

This is the mirror image of the GOPATH/bin defect fixed two commits earlier --
there a script installed a tool it could not then find; here a job was handed a
tool it never installed. Both are invisible in the environment where they are
written and fatal in the one where they run.

WHAT IT CHECKS. For every job in every workflow, steps IN ORDER. A step needs
node when its `run` invokes node/npx/tsx directly, or names an `npm run <key>`
whose package.json script does. A step PROVIDES node via actions/setup-node or
the repo's ./.github/actions/setup-workspace. A needing step with no providing
step before it in the same job is the finding.

ORDER IS THE POINT, not mere presence: a setup step placed after the gate it
serves looks correct in a diff and fails identically at runtime.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"

# A step provides node if it uses one of these.
PROVIDERS = ("actions/setup-node", "actions/setup-workspace", "setup-workspace")

# Invocations that need the node_modules TREE, not merely the npm binary.
#
# `npm` itself is preinstalled on a GitHub runner, so `npm run <key>` succeeds
# with no dependency tree whenever the key resolves to a shell script -- which is
# how quality-static has run eight npm steps for months with no node setup. Only
# a resolved command reaching for a devDependency (tsx) or a node entrypoint
# actually needs the tree. An earlier cut of this gate matched bare `npm ` and
# reported nine findings, every one of them a job that works.
NEEDS_RE = re.compile(r"(^|[\s;&|(])(npx|tsx|node)\s")
NPM_RUN_RE = re.compile(r"npm\s+run\s+([A-Za-z0-9:_-]+)")


def npm_scripts() -> dict[str, str]:
    """Root package.json scripts, so `npm run <key>` can be resolved one hop."""
    try:
        return json.loads((ROOT / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    except (OSError, ValueError):
        # Unreadable or malformed package.json. Returning {} degrades to the
        # direct-invocation check rather than crashing; check-npmrc.sh and the
        # lockfile gates own the "package.json is broken" verdict.
        return {}


SCRIPTS = npm_scripts()


def step_needs_node(run: str, _depth: int = 0) -> bool:
    """Does this step need the node_modules TREE to succeed?

    Resolve `npm run <key>` through package.json by EXACT key and ask what that
    command actually invokes. Two earlier cuts got this wrong in opposite
    directions, and each was caught by a control or by checking a flagged job:

      * matching package.json keys as SUBSTRINGS of the step text, so a short
        key matched unrelated paths and a pure-shell job was flagged;
      * treating bare `npm ` as needing the tree, which flagged nine jobs that
        demonstrably work -- npm is preinstalled, and `npm run` on a key that
        resolves to a shell script needs no dependencies at all.

    What genuinely needs the tree is tsx (a devDependency), npx, or a node
    entrypoint. That is the whole rule.
    """
    if not run or _depth > 2:
        return False
    if NEEDS_RE.search(run):
        return True
    for key in NPM_RUN_RE.findall(run):
        cmd = SCRIPTS.get(key)
        if cmd and step_needs_node(cmd, _depth + 1):
            return True
    return False


def step_provides_node(step: dict) -> bool:
    uses = str(step.get("uses") or "")
    return any(p in uses for p in PROVIDERS)


def scan_workflow(doc: dict, name: str) -> list[str]:
    findings: list[str] = []
    for job_id, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        ready = False
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            if step_provides_node(step):
                ready = True
                continue
            run = str(step.get("run") or "")
            if step_needs_node(run) and not ready:
                label = step.get("name") or run.strip().splitlines()[0][:60]
                findings.append(
                    f"{name}: job '{job_id}' step '{label}' runs node with no "
                    f"setup-node/setup-workspace earlier in the job"
                )
    return findings


def main() -> int:
    bad: list[str] = []
    scanned = 0

    for wf in sorted(WORKFLOWS.glob("*.yml")):
        try:
            doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            # A workflow that will not parse IS a finding: this gate cannot judge
            # what it cannot read, and silently skipping it would be the vacuity
            # the anti-vacuity floor below exists to prevent.
            bad.append(f"{wf.name}: could not parse ({exc})")
            continue
        if not isinstance(doc, dict):
            continue
        scanned += 1
        bad.extend(scan_workflow(doc, wf.name))

    # ANTI-VACUITY FLOOR. A glob that quietly matched nothing, or a parser that
    # returned empty docs, would keep this green forever while reading nothing.
    if scanned < 10:
        print(f"✗ only {scanned} workflow(s) parsed -- the scan is not reaching the tree")
        return 1
    print(f"ok   scope: {scanned} workflow(s) parsed")

    # --- controls: it must FIRE on the real shape and stay silent on the fix ---
    def ctl(yml: str, want_fire: bool, label: str) -> bool:
        found = scan_workflow(yaml.safe_load(yml), "fixture")
        if want_fire and not found:
            print(f"✗ CONTROL FAILED: {label} -- gate could not fire, so its green means nothing")
            return False
        if not want_fire and found:
            print(f"✗ CONTROL FAILED: {label} -- gate fires on the CORRECT shape")
            return False
        print(f"ok   control: {label}")
        return True

    ok = True
    ok &= ctl(
        "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
        "      - name: Gate\n        run: npm run check:ci-gate-manifest\n",
        True,
        "a tsx gate with NO node setup is detected (the real 33125687081 defect)",
    )
    ok &= ctl(
        "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
        "      - uses: ./.github/actions/setup-workspace\n"
        "      - name: Gate\n        run: npm run check:ci-gate-manifest\n",
        False,
        "setup-workspace BEFORE the gate is not flagged",
    )
    ok &= ctl(
        "jobs:\n  a:\n    steps:\n      - name: Gate\n        run: npm run check:ci-gate-manifest\n"
        "      - uses: ./.github/actions/setup-workspace\n",
        True,
        "setup AFTER the gate still fires -- order is the point, not presence",
    )
    ok &= ctl(
        "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
        "      - name: Shell only\n        run: .ci/scripts/quality/check-npmrc.sh\n",
        False,
        "a job of pure shell steps is not flagged",
    )
    if not ok:
        return 1

    if bad:
        print(f"\n✗ {len(bad)} job(s) run node without setting it up first:\n")
        for b in bad:
            print(f"  {b}")
        print(
            "\n  FIX: add `- uses: ./.github/actions/setup-workspace` to that job,\n"
            "  BEFORE the step. Defaults are enough for a tsx gate: no account\n"
            "  submodule, no natives, no package build."
        )
        return 1

    print("✓ every job that runs node sets it up first.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
