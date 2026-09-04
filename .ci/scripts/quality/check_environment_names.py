#!/usr/bin/env python3
"""check:ci-environment-names -- no workflow may mint an environment CI cannot clean up.

WHY THIS EXISTS. A job-level `environment:` block makes GitHub create the environment
OBJECT, and deleting one needs `Administration:write` -- a permission
check-no-app-admin-perm.sh forbids the CI App from holding, on purpose. So an
environment whose NAME varies per pull request produces one permanent object per PR
that housekeeping cannot remove: measured 2026-09-03, 25 `pr-*` environments with zero
deployments between them, all cluttering /deployments long after their PRs merged.

That was fixed by DELETING the `environment:` block from the preview job, by hand, and
nothing stops it coming back. ci.yml:1247 carries a comment explaining its absence,
which is a comment doing a gate's job -- and this repo has been here before: a comment
that invites the deletion of the line it guards is a documented trap.

THE RULE. An environment name may be a literal, or interpolate from a BOUNDED source
(a workflow input, a matrix value, a var). It may never interpolate from anything
that varies per pull request or per branch -- `github.event.number`, `github.event.pull_request.*`,
`github.ref`, `github.head_ref`, `github.sha`, or a `pr-` prefix -- because that is
exactly what mints an object per PR.

WHAT THIS DELIBERATELY DOES NOT DO. It says nothing about the /deployments RECORDS that
already exist for retired environments (production, marketing-*, github-pages). Those
are GitHub history, no commit can clear them, and deleting production deployment
history is outward-facing and the operator's call -- a gate on them would be red
forever on a condition this repo cannot satisfy.

Exit 1 on an unbounded environment name, 2 on a failed control.

---- gate ----
step: Environment names
needs: none
why: 25 orphaned pr-* environments accumulated because a job-level environment: creates
     an object CI has no permission to delete
---- end gate ----
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("ENV_NAMES_ROOT") or Path(__file__).resolve().parents[3])
WORKFLOWS = ROOT / ".github" / "workflows"
# Measured 2026-09-04: 33 workflow files. The floor guards the enumeration, and this
# gate obeys the vacuity rule it shares with check:ci-enumeration-vacuity.
MIN_WORKFLOWS = int(os.environ.get("ENV_NAMES_MIN", "20"))

# The expressions that vary per PR or per branch. `inputs.*`, `matrix.*` and `vars.*`
# are deliberately absent: those are bounded by a choice list, a matrix or repo config,
# and the three live environment names in this repo are built from exactly those.
UNBOUNDED = re.compile(
    r"github\.event\.number"
    r"|github\.event\.pull_request"
    r"|github\.ref(_name)?\b"
    r"|github\.head_ref"
    r"|github\.sha"
    r"|github\.run_(id|number)",
    re.IGNORECASE,
)
PR_LITERAL = re.compile(r"^\s*pr[-_]", re.IGNORECASE)


JOB_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
ENV_INLINE_RE = re.compile(r"^    environment:\s*(\S.*?)\s*$")
ENV_BLOCK_RE = re.compile(r"^    environment:\s*$")
ENV_NAME_RE = re.compile(r"^      name:\s*(\S.*?)\s*$")


def declared_environments(text: str) -> list[tuple[str, str]]:
    """[(job, environment name)] for one workflow, by hand rather than by PyYAML.

    A HAND PARSER ON PURPOSE, and a gate caught why: importing `yaml` here died on
    check:ci-python-gate-deps, because quality-code installs no PyYAML and the gate
    would have raised ModuleNotFoundError on a clean runner while passing locally.
    The shape is fixed -- two indent levels, two spellings -- so hand-parsing removes
    a dependency from a job rather than adding one, and leaves this runnable in the
    slim lane if it is ever moved there.
    """
    out: list[tuple[str, str]] = []
    job = ""
    in_env = False
    for raw in text.split("\n"):
        m = JOB_RE.match(raw)
        if m:
            job, in_env = m.group(1), False
            continue
        if not job:
            continue
        if in_env:
            n = ENV_NAME_RE.match(raw)
            if n:
                out.append((job, n.group(1).strip("\"'")))
                in_env = False
                continue
            if raw.strip() and not raw.startswith("      "):
                in_env = False
        if ENV_BLOCK_RE.match(raw):
            in_env = True
            continue
        inline = ENV_INLINE_RE.match(raw)
        if inline and not inline.group(1).startswith("#"):
            out.append((job, inline.group(1).strip("\"'")))
    return out


def env_name(spec) -> str | None:
    """The declared environment name of one job, or None."""
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        n = spec.get("name")
        return n if isinstance(n, str) else None
    return None


def problems_for(name: str) -> list[str]:
    """Why this environment name is unbounded, if it is."""
    out = []
    if UNBOUNDED.search(name):
        out.append("interpolates a per-PR or per-branch value")
    if PR_LITERAL.match(name):
        out.append("is named for a pull request")
    return out


def selftest() -> int:
    bad = 0

    def check(label, ok, detail=""):
        nonlocal bad
        print("  %s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else "  <- %s" % detail))
        if not ok:
            bad += 1

    cases = [
        ("edge", 0, "a literal name passes"),
        ("${{ inputs.target }}", 0, "an input is bounded"),
        ("${{ inputs.target }}-${{ matrix.id }}", 0, "input plus matrix is bounded"),
        ("${{ vars.SOMETHING }}", 0, "a repo var is bounded"),
        ("pr-${{ github.event.number }}", 2, "THE DEFECT: a per-PR name is refused twice over"),
        ("preview-${{ github.head_ref }}", 1, "a per-branch name is refused"),
        ("${{ github.ref_name }}", 1, "a ref name is refused"),
        ("pr-42", 1, "a literal pr- name is refused even with no expression"),
    ]
    for name, want, label in cases:
        got = len(problems_for(name))
        check(label, got == want, "got %d problem(s), want %d" % (got, want))

    check(
        "env_name reads both the string and the mapping form",
        env_name("edge") == "edge" and env_name({"name": "edge", "url": "x"}) == "edge",
    )
    check("env_name ignores a job with no environment", env_name(None) is None)

    # THE HAND PARSER, both YAML forms and a negative. It replaced PyYAML, so
    # nothing else proves it reads a workflow correctly.
    block = "jobs:\n  a:\n    environment:\n      name: edge\n      url: https://x\n  b:\n    steps: []\n"
    check(
        "parser reads the mapping form",
        declared_environments(block) == [("a", "edge")],
        declared_environments(block),
    )
    inline = "jobs:\n  a:\n    environment: stable\n"
    check(
        "parser reads the inline form",
        declared_environments(inline) == [("a", "stable")],
        declared_environments(inline),
    )
    none = "jobs:\n  a:\n    steps:\n      - run: echo environment: not-a-declaration\n"
    check(
        "parser ignores prose that merely says environment",
        declared_environments(none) == [],
        declared_environments(none),
    )
    return bad


def main() -> int:
    print("environment names: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2

    files = sorted(WORKFLOWS.glob("*.yml"))
    if len(files) < MIN_WORKFLOWS:
        print(
            "VACUOUS: %d workflow file(s), floor %d. The enumeration lost the corpus; "
            "refusing a verdict." % (len(files), MIN_WORKFLOWS),
            file=sys.stderr,
        )
        return 1

    findings: list[str] = []
    seen = 0
    for f in files:
        for job, name in declared_environments(f.read_text(encoding="utf-8")):
            seen += 1
            findings.extend(
                "%s: job %r declares environment %r, which %s" % (f.name, job, name, why)
                for why in problems_for(name)
            )

    if findings:
        print("✗ %d unbounded environment name(s):" % len(findings), file=sys.stderr)
        for p in findings:
            print("    %s" % p, file=sys.stderr)
        for line in [
            "",
            "  A job-level `environment:` makes GitHub create the environment OBJECT, and",
            "  deleting one needs Administration:write -- which check-no-app-admin-perm.sh",
            "  forbids the CI App from holding. A name that varies per PR therefore mints a",
            "  permanent object per PR that housekeeping cannot remove: 25 of them had",
            "  accumulated by 2026-09-03, every one with zero deployments.",
            "  Use a bounded source (an input, a matrix value, a var), or drop the block.",
        ]:
            print(line, file=sys.stderr)
        return 1

    print(
        "✓ environment names: %d workflow file(s) scanned (floor %d), %d job(s) declare an "
        "environment, none of them named per-PR or per-branch" % (len(files), MIN_WORKFLOWS, seen)
    )
    print(
        "  Blind spot: this governs what the tree CREATES. Records already in /deployments "
        "for retired environments are GitHub history no commit can clear, and removing them "
        "is the operator's call."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
