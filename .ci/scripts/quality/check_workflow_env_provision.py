#!/usr/bin/env python3
"""check:ci-workflow-env-provision -- a job may not use a variable nothing gives it.

WHY THIS EXISTS, measured 2026-09-03 (run for 652233865, job 100717989555). The
`quality-security` job ran

    python3 -m pip install --user --disable-pip-version-check "PyYAML==${PYYAML_VERSION}"

and that variable is provisioned by a "Load gate toolchain pins" step which
`quality-static` has and `quality-security` did not. The shell expanded it to
EMPTY, pip was handed the literal `PyYAML==`, and CI reported

    ERROR: Could not find a version that satisfies the requirement PyYAML==

-- a message about pip, in a step named "Secret reachability", in a job whose
actual defect was three steps earlier and entirely invisible in that text.

THE SHAPE, and it is why an unset variable is worse than a missing file: bash
expands an undefined name to the empty string without a word of complaint, so
the failure always surfaces somewhere downstream wearing somebody else's name.
A step copied between jobs without the step that feeds it is the usual cause.

WHAT IS AND IS NOT A FINDING. Only names this repo PROVISIONS SOMEWHERE are
judged: a name that appears in some `env:` block, is written to $GITHUB_ENV, or
is emitted by toolchain.sh. Runner built-ins ($RUNNER_TEMP, $GITHUB_SHA, $HOME)
are never provisioned by this tree, so they cannot be flagged, and no allowlist
is needed to protect them. That is what keeps this at zero false positives
across 124 jobs rather than becoming the kind of noise a gate gets suppressed for.

ONE HOP INTO SCRIPTS, and it is load-bearing rather than a nicety. Nine jobs use
$RENET_BINARY, which no workflow line defines: `.ci/scripts/infra/build-renet.sh`
writes it to $GITHUB_ENV. Without following the script named in the run block
this gate reports nine confident findings that are all wrong. (The first version
DID -- because `m.lstrip('./')` strips every leading dot AND slash, turning
`.ci/scripts/...` into `ci/scripts/...`, which resolves to nothing. The nine
findings looked like a real defect class. `removeprefix` is the fix, and a broken
path resolver that reports MORE is the lucky direction; the same bug in a gate
that reports less is silent.)

Exit 1 on any finding, 2 on a failed control.
"""

from __future__ import annotations

import contextlib
import pathlib
import re
import subprocess
import sys
import tempfile

# Top-level, matching check_python_gate_deps.py and check_workflow_submodule_deps.py:
# the CI step that runs this installs the pinned PyYAML immediately before it, and a
# gate that quietly degrades when its parser is missing is the vacuity this tree has
# rules about. A bare ImportError traceback names the missing module, which is the
# right failure.
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
MIN_JOBS = 60

BUILTIN = re.compile(
    r"^(GITHUB|RUNNER|ACTIONS)_|"
    r"^(HOME|PATH|PWD|CI|USER|SHELL|TMPDIR|HOSTNAME|LANG|TERM|EDITOR|OSTYPE"
    r"|IFS|RANDOM|PPID|UID|EUID|SECONDS|LINENO|FUNCNAME|OLDPWD|SHLVL)$|^BASH"
)
USE = re.compile(r"\$\{?([A-Z][A-Z0-9_]{2,})\}?")
ASSIGN = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]{2,})=", re.MULTILINE)
GHENV = re.compile(r'([A-Z][A-Z0-9_]{2,})\s*=.*>>\s*"?\$\{?GITHUB_ENV', re.MULTILINE)
SCRIPT = re.compile(r"(?<![\w/.-])((?:\./)?(?:\.ci|scripts)/[\w./-]+\.(?:sh|py|ts|cjs))")


def toolchain_names(root: pathlib.Path = ROOT) -> set[str]:
    """Names `toolchain.sh --env` writes into $GITHUB_ENV."""
    try:
        r = subprocess.run(
            [str(root / ".ci/scripts/lib/toolchain.sh"), "--env"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {ln.split("=", 1)[0] for ln in r.stdout.split("\n") if "=" in ln}


def scan(root: pathlib.Path, tools: set[str]):
    """-> (per_job {(wf, job): (defined, used)}, provisioned_anywhere)."""
    per_job, anywhere = {}, set()
    for wf in sorted((root / ".github" / "workflows").glob("*.yml")):
        try:
            doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict):
            continue
        wenv = set((doc.get("env") or {}).keys())
        for jname, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            defs = set(wenv) | set((job.get("env") or {}).keys())
            uses: set[str] = set()
            for st in job.get("steps") or []:
                if not isinstance(st, dict):
                    continue
                defs |= set((st.get("env") or {}).keys())
                run = st.get("run")
                if not isinstance(run, str):
                    continue
                defs |= set(ASSIGN.findall(run)) | set(GHENV.findall(run))
                if "toolchain.sh --env" in run:
                    defs |= tools
                for rel in SCRIPT.findall(run):
                    sp = root / rel.removeprefix("./")
                    if sp.is_file():
                        with contextlib.suppress(OSError):
                            defs |= set(GHENV.findall(sp.read_text(encoding="utf-8")))
                uses |= {m for m in USE.findall(run) if not BUILTIN.match(m)}
            per_job[(wf.name, jname)] = (defs, uses)
            anywhere |= defs
    return per_job, anywhere


def findings(per_job, anywhere) -> list[str]:
    out = []
    for (wf, j), (defs, uses) in sorted(per_job.items()):
        out.extend(
            f"{wf}: job `{j}` uses ${u} in a run: block, but nothing in that job "
            f"provides it. Other jobs do, so the value is real and this one gets "
            f"the empty string -- silently, with the failure surfacing downstream."
            for u in sorted(uses - defs)
            if u in anywhere
        )
    return out


def selftest() -> int:
    bad = 0

    def check(name, ok, detail=""):
        nonlocal bad
        print(
            f"  {'PASS' if ok else 'FAIL'}  {name}"
            + (f"\n        {detail}" if detail and not ok else "")
        )
        if not ok:
            bad += 1

    with tempfile.TemporaryDirectory() as td:
        fx = pathlib.Path(td)
        (fx / ".github" / "workflows").mkdir(parents=True)
        (fx / ".github" / "workflows" / "w.yml").write_text(
            yaml.safe_dump(
                {
                    "jobs": {
                        "provider": {
                            "steps": [
                                {"run": 'echo "PIN_VERSION=1 " >> "$GITHUB_ENV"'},
                                {"run": "pip install pkg==${PIN_VERSION}"},
                            ]
                        },
                        "consumer": {"steps": [{"run": "pip install pkg==${PIN_VERSION}"}]},
                        "builtin": {"steps": [{"run": 'ls "$RUNNER_TEMP" "$GITHUB_SHA"'}]},
                    }
                }
            )
        )
        per_job, anywhere = scan(fx, set())
        f = findings(per_job, anywhere)
        check(
            "PLANT: a job using a name only another job provides is caught",
            any("consumer" in x for x in f),
            str(f),
        )
        check(
            "CONTROL: the job that provides it is not flagged", not any("provider" in x for x in f)
        )
        check("CONTROL: runner built-ins are never flagged", not any("builtin" in x for x in f))

    # CONTROL on the real tree: the script hop must resolve, or $RENET_BINARY
    # (written to $GITHUB_ENV by build-renet.sh) becomes nine false findings.
    hop = ROOT / ".ci/scripts/infra/build-renet.sh"
    check(
        "CONTROL: the one-hop script resolver finds a real $GITHUB_ENV writer",
        hop.is_file() and bool(GHENV.findall(hop.read_text(encoding="utf-8"))),
        str(hop),
    )
    return bad


def main() -> int:
    print("workflow env provision: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2

    per_job, anywhere = scan(ROOT, toolchain_names())
    if len(per_job) < MIN_JOBS:
        print(
            f"VACUOUS INPUT: {len(per_job)} job(s) parsed, floor {MIN_JOBS}. "
            f"The enumeration lost the corpus; refusing a verdict.",
            file=sys.stderr,
        )
        return 1

    probs = findings(per_job, anywhere)
    if probs:
        print(f"✗ workflow env provision ({len(probs)} finding(s)):", file=sys.stderr)
        for p in probs:
            print(f"    {p}", file=sys.stderr)
        print(
            "  Fix: give the job the step that provisions the name -- usually the same "
            "step the job that already works uses.",
            file=sys.stderr,
        )
        return 1

    print(
        f"✓ workflow env provision: {len(per_job)} job(s), "
        f"{len(anywhere)} provisioned name(s); every use has a provider in its own job"
    )
    print("  Blind spot: a name provisioned by a COMPOSITE ACTION's own steps is not")
    print("  resolved, so this under-reports rather than inventing findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
