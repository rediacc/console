#!/usr/bin/env python3
"""A workflow step that needs a resource must have it set up EARLIER in its job.

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

A SECOND, DIFFERENT INSTANCE OF THE SAME CLASS surfaced 2026-08-30: run
33[...] (Quality/Packages -> "Tutorial player release gate") died with
"agent-browser is not installed or not accessible in PATH". The gate had been
tested only on a devbox that already carries agent-browser globally, and this
was its first run in CI ever -- ci-quality.yml never installed one. The node
check above would have stayed silent: agent-browser is not node, npx, or tsx,
and the missing resource was a separate CLI tool, not a missing dependency
tree. Rather than write a second, parallel script for "does the agent-browser
CLI have a setup step before its gate", this file generalises: it now tracks a
LIST of resources, each with its own "does this step need it" / "does this
step provide it" pair, and asks the identical order question for each one.

WHAT IT CHECKS. For every job in every workflow, steps IN ORDER, per tracked
RESOURCE. A step needs a resource when its `run` invokes it directly, or names
an `npm run <key>` whose package.json script does. A step PROVIDES a resource
via the setup mechanism that resource declares. A needing step with no
providing step before it in the same job is the finding.

ORDER IS THE POINT, not mere presence: a setup step placed after the gate it
serves looks correct in a diff and fails identically at runtime.

WHAT THIS DOES NOT CLAIM. This is not "every gate's dependencies are
verified" -- it tracks the resources named in RESOURCES below, chosen because
each one has already caused a real CI red once. Adding a new externally-
acquired tool to a gate should mean adding a resource entry here, the same way
adding a pinned binary means adding a row to check-toolchain-pins.sh's
registry. A fully general "infer any tool any script might need" scanner is
not this gate's job; toolchain.sh and check-toolchain-pins.sh already own the
pinned-binary half of that problem (ruff/go/shfmt/shellcheck/actionlint), and
this owns the "job never set the resource up at all" half for anything else.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"


def _load_package_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Unreadable or malformed package.json. check-npmrc.sh and the
        # lockfile gates own the "package.json is broken" verdict; this gate
        # just resolves one less hop and falls back to the direct-invocation
        # check, which still fires on a literal match in the `run:` text.
        return {}


def _workspace_scripts() -> dict[str, dict[str, str]]:
    """`{workspace name: {script key: command}}`, root included under "".

    `npm run <key>` alone resolves against the root scripts. `npm run <key>
    -w <name>` (or `--workspace=<name>` / `--workspace <name>`) resolves
    against that workspace's OWN package.json -- required for
    `check:test:tutorial-player`: its root script is `npm run
    test:tutorial-player -w @rediacc/www`, and `test:tutorial-player` is
    declared only in packages/www/package.json, not root's. Resolving one
    hop and stopping there (the ORIGINAL cut of this function) silently
    treated that whole chain as "resolves to nothing", which is exactly the
    control failure this comment documents: the planted 2026-08-30 defect
    control could not fire until this existed.
    """
    root_pkg = _load_package_json(ROOT / "package.json")
    table: dict[str, dict[str, str]] = {"": root_pkg.get("scripts", {})}
    for pattern in ("packages/*/package.json", "workers/*/package.json"):
        for pkg_path in ROOT.glob(pattern):
            pkg = _load_package_json(pkg_path)
            name = pkg.get("name")
            if name:
                table[name] = pkg.get("scripts", {})
    return table


SCRIPTS_BY_WORKSPACE = _workspace_scripts()

_NPM_RUN_RE = re.compile(
    r"npm\s+run\s+([A-Za-z0-9:_-]+)(?:\s+(?:-w|--workspace)(?:=|\s+)([^\s]+))?"
)
# A resolved command that hands off to an interpreter and a file. One hop past
# `npm run`: the command TEXT stops mentioning any resource once it reaches
# this shape, but the FILE's own source is where the real invocation lives
# (execFileSync('agent-browser', ...) inside a .js gate, for instance).
_INTERPRETER_FILE_RE = re.compile(r"\b(?:node|bash|sh|python3?)\s+(\S+\.(?:m?js|cjs|sh|py))\b")


def _needs_via_run_pattern(
    run_pattern: re.Pattern[str], file_pattern: re.Pattern[str] | None = None
) -> Callable[[str, int], bool]:
    """Build a `needs(run)` predicate that resolves `npm run <key> [-w <ws>]`
    through the right workspace's package.json, then one more hop into the
    resolved script FILE's own source if the command hands off to one.

    TWO PATTERNS ON PURPOSE. `run_pattern` matches shell COMMAND text and must
    stay anchored to command position (`echo agent-browser` in a run: block is
    prose, not an invocation -- the exact mention-vs-target shape
    check-toolchain-pins.sh's A6 rule already paid for). `file_pattern` matches
    arbitrary FILE SOURCE once resolution reaches one (a JS string literal
    argument to execFileSync is not at "command position" in any shell sense),
    so it is deliberately the looser of the two -- a stray comment mentioning
    the tool costs one over-suggested install step, which is a fix a reader
    dismisses at a glance; a missed real invocation is the defect class this
    whole file exists to catch. Defaults to `run_pattern` when a resource's
    shell and file shapes are close enough not to need the split (node's
    npx/tsx/node keywords do not appear as bare comment prose the way a tool
    name like "agent-browser" does).

    Shared by every resource below so this resolution path -- workflow step
    text -> package.json script -> script file content -- is identical for
    node, agent-browser, or anything added later, rather than reinvented per
    resource.
    """
    file_re = file_pattern or run_pattern

    def needs(run: str, _depth: int = 0, workspace: str = "") -> bool:
        if not run or _depth > 3:
            return False
        if run_pattern.search(run):
            return True
        m = _INTERPRETER_FILE_RE.search(run)
        if m:
            file_path = ROOT / m.group(1)
            try:
                content = file_path.read_text(encoding="utf-8")
            except OSError:
                content = ""
            if content and file_re.search(content):
                return True
        for key, ws in _NPM_RUN_RE.findall(run):
            target_ws = ws or workspace
            cmd = SCRIPTS_BY_WORKSPACE.get(target_ws, {}).get(key)
            if cmd and needs(cmd, _depth + 1, target_ws):
                return True
        return False

    return needs


@dataclass(frozen=True)
class Resource:
    name: str
    needs: Callable[[str], bool]
    provides: Callable[[dict], bool]
    fix: str


# --- node_modules tree -------------------------------------------------------
# Invocations that need the node_modules TREE, not merely the npm binary.
#
# `npm` itself is preinstalled on a GitHub runner, so `npm run <key>` succeeds
# with no dependency tree whenever the key resolves to a shell script -- which
# is how quality-static has run eight npm steps for months with no node
# setup. Only a resolved command reaching for a devDependency (tsx) or a node
# entrypoint actually needs the tree. An earlier cut of this gate matched bare
# `npm ` and reported nine findings, every one of them a job that works.
_NODE_NEEDS_RE = re.compile(r"(^|[\s;&|(])(npx|tsx|node)\s")
_NODE_PROVIDERS = ("actions/setup-node", "actions/setup-workspace", "setup-workspace")


def _step_provides_node(step: dict) -> bool:
    uses = str(step.get("uses") or "")
    return any(p in uses for p in _NODE_PROVIDERS)


# --- agent-browser CLI --------------------------------------------------------
# A real, separately-acquired CLI (npm-global-installed, not a devDependency),
# unrelated to the node_modules tree above -- a job can have node fully set up
# and still lack this. Found live 2026-08-30 on check:test:tutorial-player's
# first-ever CI run: "agent-browser is not installed or not accessible in
# PATH". Provided by the exact install line .claude/agents/browser-probe.md
# documents ("Install it from $HOME, never from inside the console repo").
#
# COMMAND-POSITION ANCHORED for shell text: `[;&|(]` are genuine command
# separators, plain whitespace is NOT one of them, or `echo agent-browser` in
# a run: block's prose would fire as an invocation -- the exact mention-vs-
# target class check-toolchain-pins.sh's A6 rule already learned to exempt.
_BROWSER_NEEDS_RE = re.compile(r"(^|[\n;&|(])\s*agent-browser(\s|$)")
# UNANCHORED for file content: the real call site is a JS string literal
# (execFileSync('agent-browser', ...)), which is not at "command position" in
# any shell sense. See _needs_via_run_pattern's docstring for the asymmetry.
_BROWSER_NEEDS_FILE_RE = re.compile(r"\bagent-browser\b")
_BROWSER_PROVIDE_RE = re.compile(r"npm\s+install\s+(-g|--global)\s+agent-browser")


def _step_provides_agent_browser(step: dict) -> bool:
    return bool(_BROWSER_PROVIDE_RE.search(str(step.get("run") or "")))


RESOURCES = (
    Resource(
        name="node",
        needs=_needs_via_run_pattern(_NODE_NEEDS_RE),
        provides=_step_provides_node,
        fix=(
            "add `- uses: ./.github/actions/setup-workspace` to that job,\n"
            "  BEFORE the step. Defaults are enough for a tsx gate: no account\n"
            "  submodule, no natives, no package build."
        ),
    ),
    Resource(
        name="agent-browser",
        needs=_needs_via_run_pattern(_BROWSER_NEEDS_RE, _BROWSER_NEEDS_FILE_RE),
        provides=_step_provides_agent_browser,
        fix=(
            'add a step running `cd "$HOME" && npm install -g agent-browser@latest '
            "--ignore-scripts=false` to that job, BEFORE the step (not from inside\n"
            "  the checkout -- this repo's ignore-scripts=true .npmrc silently skips\n"
            "  the postinstall that selects the platform binary)."
        ),
    ),
)


def scan_workflow(doc: dict, name: str) -> list[str]:
    findings: list[str] = []
    for job_id, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        ready = {r.name: False for r in RESOURCES}
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            run = str(step.get("run") or "")
            for r in RESOURCES:
                if r.provides(step):
                    ready[r.name] = True
                    continue
                if r.needs(run) and not ready[r.name]:
                    label = step.get("name") or run.strip().splitlines()[0][:60]
                    findings.append(
                        f"{name}: job '{job_id}' step '{label}' needs {r.name} with no "
                        f"setup for it earlier in the job"
                    )
    return findings


def _fix_for(resource_name: str) -> str:
    for r in RESOURCES:
        if r.name == resource_name:
            return r.fix
    return "add the missing setup step before the gate."


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
    print(f"ok   scope: {scanned} workflow(s) parsed, {len(RESOURCES)} resource(s) tracked")

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
    ok &= ctl(
        "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
        "      - name: Browser gate\n        run: npm run check:test:tutorial-player\n",
        True,
        "the REAL production step (check:test:tutorial-player, resolved 3 hops -- "
        "npm run -> workspace package.json -> script file source -- into finding "
        "execFileSync('agent-browser', ...)) is detected with no install step "
        "(the real 2026-08-30 defect, reproduced through the actual chain, not a "
        "synthetic stand-in)",
    )
    ok &= ctl(
        "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
        "      - name: Bare gate\n        run: agent-browser open http://x\n",
        True,
        "a bare agent-browser invocation with no install step is detected",
    )
    ok &= ctl(
        'jobs:\n  a:\n    steps:\n      - run: cd "$HOME" && npm install -g agent-browser@latest --ignore-scripts=false\n'
        "      - name: Browser gate\n        run: agent-browser open http://x\n",
        False,
        "agent-browser install BEFORE the gate is not flagged",
    )
    ok &= ctl(
        "jobs:\n  a:\n    steps:\n      - name: Browser gate\n        run: agent-browser open http://x\n"
        '      - run: cd "$HOME" && npm install -g agent-browser@latest --ignore-scripts=false\n',
        True,
        "agent-browser install AFTER the gate still fires -- order is the point here too",
    )
    ok &= ctl(
        "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
        "      - name: Gate\n        run: npm run check:ci-gate-manifest\n"
        "      - name: Unrelated\n        run: echo agent-browser mentioned only in prose\n",
        True,
        "CONTROL: a prose mention of agent-browser in an unrelated echo does not "
        "suppress the real node finding above it",
    )
    if not ok:
        return 1

    if bad:
        print(f"\n✗ {len(bad)} finding(s) -- a job uses a resource it never set up:\n")
        for b in bad:
            print(f"  {b}")
        print()
        for r in RESOURCES:
            if any(f" needs {r.name} " in b for b in bad):
                print(f"  FIX ({r.name}): {_fix_for(r.name)}")
        return 1

    print("✓ every job sets up what it needs, before it needs it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
