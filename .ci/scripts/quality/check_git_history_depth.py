#!/usr/bin/env python3
"""A job that READS history must have CHECKED OUT history.

THE DEFECT THIS EXISTS FOR IS A SILENT WRONG ANSWER, not a crash. `actions/checkout`
defaults to `fetch-depth: 1`, and git does not fail on a shallow clone -- it answers
confidently from the truncated history it has. `git log --since=` returns fewer commits,
`git rev-list --count` returns a smaller number, `git describe` picks the wrong tag, and
`--diff-filter=A` reports the graft commit as having ADDED every file beneath it. Nothing
goes red. The number is simply wrong, and every conclusion drawn from it is wrong with it.

MEASURED IN THIS REPO, 2026-09-01, which is why the gate exists. A local checkout was
grafted at 2026-08-28. `git show --diff-filter=A --name-only 609314a41 | wc -l` reported
**4,531 added files**; with real history that commit adds **4**. Every per-month arrival
rate computed from it was wrong by three orders of magnitude, and the analysis built on
those rates looked entirely reasonable for hours. The fix was one `git fetch --unshallow`
by hand, with nothing to stop the same thing happening in CI where nobody is watching a
shell.

WHY NO EXISTING GATE CATCHES IT. Every gate here runs in a tree somebody already checked
out correctly, so the dependency is invisible: the command succeeds, prints a number, and
the number is wrong only in the job whose checkout was shallow. The dependency lives across
two parts of one file that nothing reads together -- the job's `actions/checkout` step and
a `run:` line further down.

THE INVARIANT HOLDS TODAY and that is the point of gating it now rather than after a
breakage: 11 of 144 checkout steps declare `fetch-depth: 0`, each in a job that needs it,
and the other 133 are correctly shallow. Nothing enforces the pairing.

WHY PYTHON RATHER THAN A check-*.ts. Reading job/step STRUCTURE needs a real YAML parse,
and the five sibling gates that do that -- check_workflow_submodule_deps.py,
check_ci_gate_prerequisites.py and friends -- are all Python on PyYAML. The TypeScript
version of this gate worked, but `yaml` is not a declared npm dependency here (it appears
only as an override), so shipping it would have meant adding a dependency to duplicate a
capability the repo already has. knip caught that, which is the gate doing its job.

SWEPT THE CLASS, 2026-09-01, and the sweep is why this gate stops at the step's own text.
18 files under `.ci/scripts/` and `scripts/` run depth-dependent git. Following the step ->
script hop (via check_workflow_submodule_deps.py's resolver, which already does exactly
that walk) produced **89 findings across 25+ jobs** on a CI that has been green for months.
They are false by construction, because the scripts mitigate shallowness THEMSELVES in ways
no text-level gate can see:

  - `check-branch.sh:63` fetches the base ref explicitly -- `+refs/heads/X:refs/remotes/
    origin/X` -- before its `rev-list`, and its comment at :69 names "a shallow clone with
    no merge base" as a case it already handles.
  - `resolve-version.sh:44` says it uses `git tag -l` rather than `git describe` BECAUSE
    describe requires tags. It was written shallow-safe deliberately.

So the hop was reverted, and a rule that hard-coded `resolve-version.sh` as a history op
went with it: that rule punished a script for the mitigation it already had. A gate that
reports 89 findings nobody can act on is a wall, and this repo has the scar already.

The class is therefore NOT-GATEABLE at the script level with a concrete divergence -- the
same third exit the shape rule has. What IS soundly gateable is a step that reads history
in its own text, which is what remains below.

WHAT COUNTS AS READING HISTORY is deliberately narrow -- see HISTORY_OPS. `git log -1`,
`git rev-parse HEAD` and `git status` are all CORRECT on a depth-1 clone and are not
flagged. False positives here would push authors toward `fetch-depth: 0` everywhere, which
is the opposite of what this repo wants: the media-history rewrite exists precisely so
clones stay cheap.
"""

import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required for this gate (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)

# A floor: a broken glob reports a confident green having read nothing.
MIN_WORKFLOWS = 20

# Git invocations whose ANSWER changes with how much history is present. Each is a form a
# depth-1 clone answers WRONGLY rather than refusing.
HISTORY_OPS = [
    (re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?rev-list\b"), "git rev-list counts commits it can see"),
    (re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?describe\b"), "git describe needs the tag in history"),
    (re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?merge-base\b"), "merge-base needs the common ancestor"),
    (re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?shortlog\b"), "shortlog summarises history"),
    (re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?blame\b"), "blame walks back through history"),
    (
        re.compile(
            r"\bgit\s+(?:-C\s+\S+\s+)?log\b[^\n|;&]*(?:--since|--until|--reverse|--diff-filter|\.\.)"
        ),
        "a git log range or filter is answered from available history",
    ),
    (
        re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?diff\b[^\n|;&]*\.\.\."),
        "a three-dot diff needs the merge base",
    ),
]


def offences_in(job):
    """The history ops this job runs against a SHALLOW tree. [] if none.

    ORDER IS THE WHOLE POINT, and the first cut of this got it wrong. It asked "is every
    checkout in this job deep?", which is a false positive on the commonest real pattern:
    `cd-v2.yml`'s `init` job checks out SHALLOW (to mint an app token), checks out again
    with `fetch-depth: 0` into the same path, and only then runs `git rev-list` and
    `resolve-version.sh`. By then the tree is deep. That rule reported both as offences on
    the gate's very first run against the real tree -- which twelve green controls had not
    found, because the controls encoded the same wrong rule.

    So the depth a step sees is the depth of the LAST checkout into its path before it. A
    checkout carrying `path:` makes a SEPARATE tree and is ignored: it does not change the
    default worktree the `run:` steps execute in.

    A job with no checkout at all has no history to be wrong about and is never an offence.
    """
    steps = job.get("steps") if isinstance(job, dict) else None
    if not isinstance(steps, list):
        return []
    out = []
    deep_now = None  # None = nothing checked out into the default path yet
    for step in steps:
        if not isinstance(step, dict):
            continue
        if "actions/checkout" in str(step.get("uses", "")):
            with_ = step.get("with") or {}
            if "path" in with_:
                continue  # a different tree
            deep_now = str(with_.get("fetch-depth", "")) == "0"
            continue
        run = step.get("run")
        if not isinstance(run, str) or deep_now is not False:
            continue
        for line in run.split("\n"):
            trimmed = line.strip()
            if trimmed.startswith("#"):  # a comment is not an invocation
                continue
            for pattern, why in HISTORY_OPS:
                if pattern.search(trimmed) and not any(w == why for _o, w in out):
                    out.append((trimmed[:90], why))
    return out


def judge(workflows):
    """[(file, job, op, why)] over [(file, parsed_doc)]."""
    found = []
    for path, doc in workflows:
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        if not isinstance(jobs, dict):
            continue
        for name, job in jobs.items():
            for op, why in offences_in(job):
                found.append((path, name, op, why))
    return found


def selftest():
    """Controls, both directions. A gate that cannot fail is worse than none."""
    ok = True

    def check(label, cond):
        nonlocal ok
        if cond:
            print("  PASS  %s" % label)
        else:
            ok = False
            print("  FAIL  %s" % label, file=sys.stderr)

    def job(*steps):
        return [("f.yml", {"jobs": {"j": {"steps": list(steps)}}})]

    co = {"uses": "actions/checkout@v7"}
    deep = {"uses": "actions/checkout@v7", "with": {"fetch-depth": 0}}

    check(
        "a history op under a SHALLOW checkout is an offence",
        len(judge(job(co, {"run": "git rev-list --count HEAD"}))) == 1,
    )
    check(
        "CONTROL: the same op under fetch-depth: 0 is fine",
        len(judge(job(deep, {"run": "git rev-list --count HEAD"}))) == 0,
    )
    check(
        "CONTROL: a shallow checkout that reads no history is fine",
        len(judge(job(co, {"run": "npm run build && git status --short"}))) == 0,
    )
    # `git log -1` is CORRECT at depth 1. Flagging it would push authors to fetch-depth: 0
    # everywhere, which is the opposite of the goal.
    check(
        "CONTROL: git log -1 is correct at depth 1 and is not flagged",
        len(judge(job(co, {"run": "git log -1 --format=%H"}))) == 0,
    )
    check(
        "a git log RANGE is flagged where a plain git log is not",
        len(judge(job(co, {"run": "git log --since=30.days --format=%H"}))) == 1
        and len(judge(job(co, {"run": "git log --format=%H origin/main..HEAD"}))) == 1,
    )
    check(
        "a three-dot diff is flagged, a worktree diff is not",
        len(judge(job(co, {"run": "git diff origin/main...HEAD --name-only"}))) == 1
        and len(judge(job(co, {"run": "git diff --name-only"}))) == 0,
    )
    check(
        "CONTROL: a commented-out op is not an invocation",
        len(judge(job(co, {"run": "# git rev-list --count HEAD\nnpm test"}))) == 0,
    )
    check(
        "CONTROL: a job with NO checkout has no history to be wrong about",
        len(judge(job({"run": "git describe --tags"}))) == 0,
    )
    check(
        "a deep checkout in ANOTHER job does not cover this one",
        len(
            judge(
                [
                    (
                        "f.yml",
                        {
                            "jobs": {
                                "a": {"steps": [deep, {"run": "echo hi"}]},
                                "b": {"steps": [co, {"run": "git describe --tags"}]},
                            }
                        },
                    )
                ]
            )
        )
        == 1,
    )
    # THE REAL PATTERN, from cd-v2.yml's `init` job -- see offences_in's docstring.
    check(
        "CONTROL: shallow-then-deep into the same path is deep by the time ops run",
        len(judge(job(co, deep, {"run": "git rev-list --count HEAD"}))) == 0,
    )
    check(
        "but deep-then-SHALLOW leaves the op on a truncated tree",
        len(judge(job(deep, co, {"run": "git rev-list --count HEAD"}))) == 1,
    )
    check(
        "CONTROL: a checkout with path: makes a different tree and does not reset depth",
        len(
            judge(
                job(
                    deep,
                    {"uses": "actions/checkout@v7", "with": {"path": "other"}},
                    {"run": "git describe --tags"},
                )
            )
        )
        == 0,
    )
    check(
        "an op BEFORE any deep re-checkout is still an offence",
        len(judge(job(co, {"run": "git describe --tags"}, deep))) == 1,
    )
    # THE RULE THAT USED TO BE HERE WAS WRONG, and the sweep is what proved it.
    # `resolve-version.sh:44` says in as many words that it uses `git tag -l` rather than
    # `git describe` BECAUSE describe requires tags -- it was written shallow-safe on
    # purpose. Flagging it punished a script for the mitigation it already has.
    check(
        "CONTROL: a script written shallow-safe is not flagged for being called",
        len(judge(job(co, {"run": ".ci/scripts/version/resolve-version.sh --current"}))) == 0,
    )
    check("CONTROL: an empty workflow set yields no offences", len(judge([])) == 0)
    return ok


def workflows(root):
    out = subprocess.run(
        ["git", "ls-files", ".github/workflows/*.yml"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    found = []
    for rel in out.split("\n"):
        if not rel:
            continue
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            found.append((rel, yaml.safe_load(fh)))
    return found


def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return 0 if selftest() else 1
    if not selftest():
        print("REFUSING to report on the tree: this gate's own controls failed.", file=sys.stderr)
        return 1

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    wfs = workflows(root)
    if len(wfs) < MIN_WORKFLOWS:
        print(
            "found %d workflow(s), floor %d. The scan is broken, not the tree."
            % (len(wfs), MIN_WORKFLOWS),
            file=sys.stderr,
        )
        return 1

    found = judge(wfs)
    if found:
        print("\n%d job(s) read history from a shallow checkout:\n" % len(found), file=sys.stderr)
        for path, job_name, op, why in found:
            print("  %s  job '%s'" % (path, job_name), file=sys.stderr)
            print("    %s" % op, file=sys.stderr)
            print("    %s" % why, file=sys.stderr)
        print(
            "\n  A shallow clone does not FAIL these commands, it answers them wrongly and\n"
            "  stays green. Add `fetch-depth: 0` (with `filter: blob:none`, as the 11 deep\n"
            "  checkouts already do) to that job's checkout, or stop reading history in it.",
            file=sys.stderr,
        )
        return 1

    jobs = sum(len(d.get("jobs") or {}) for _p, d in wfs if isinstance(d, dict))
    print(
        "git history depth: %d workflow(s), %d job(s); no job reads history it did not fetch"
        % (len(wfs), jobs)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
