#!/usr/bin/env python3
"""check:ci-docker-npm-pins -- no Dockerfile may install an npm package at an unpinned version.

WHY THIS EXISTS, and it is a regression test for a build that broke with no commit
behind it. On 2026-09-04 private/account's image stopped building:

    npm error Cannot read properties of null (reading 'edgesOut')

an arborist crash inside #loadPeerSet while walking vitest 4's peer graph. It failed
in CI (job 100832669673) and reproduced identically on a laptop. Nothing in this repo
had changed; a package published that morning had. The stage resolved its whole
dependency tree live from the registry on every build, so a stranger's publish was
enough.

THE RULE. Every `npm install` / `npm i` / `npm add` inside a tracked Dockerfile must
name a version for each package, or install from a lockfile. Concretely:

  * a global install (`-g`) must spell `pkg@<version>`, and `@latest`, `@next`,
    `@beta` and a bare name are all UNPINNED -- a tag is a moving target, which is
    the whole defect;
  * a project install with no package list resolves from package.json, so it is
    judged on whether a lockfile is in the build context: `npm ci` is pinned by
    construction, plain `npm install` is not.

A `${VAR}` version is PINNED: an ARG is a value in the file, reviewable and diffable,
and it is the shape the devcontainer already uses.

The escape hatch is .ci/config/docker-npm-pin-exclusions.json, keyed `<path>:<line
substring>`, whose reason must start with BLOCKER:. An entry that matches nothing is
REFUSED as dead scaffold.

Exit 1 on an unpinned install or a dead exclusion, 2 on a failed control.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("DOCKER_NPM_PINS_ROOT") or Path(__file__).resolve().parents[3])
EXCLUSIONS = ROOT / ".ci" / "config" / "docker-npm-pin-exclusions.json"
MIN_REASON_CHARS = 40
# Measured 2026-09-04 with the enumeration this gate actually uses (git ls-files
# --recurse-submodules): 11 tracked Dockerfiles carrying 9 npm-install lines between
# them. A `find` over the tree says 14, which is the number a first draft of this
# comment carried -- it counts untracked and node_modules copies that CI never sees.
# The floor guards the ENUMERATION, not the population.
MIN_DOCKERFILES = int(os.environ.get("DOCKER_NPM_PINS_MIN", "6"))
# Workflows are the bigger half of the corpus and the half this gate originally
# missed, so they get their own floor rather than hiding inside a combined one.
MIN_WORKFLOWS = int(os.environ.get("DOCKER_NPM_PINS_MIN_WORKFLOWS", "20"))

# Long flags that are BOOLEAN, so the token after them really is a package.
# Listed rather than guessed: treating every long flag as value-taking would
# swallow the package in `npm install --ignore-scripts foo@latest`.
_VALUELESS_LONG_FLAGS = frozenset(
    {
        "--ignore-scripts",
        "--no-save",
        "--save",
        "--save-dev",
        "--save-exact",
        "--global",
        "--force",
        "--no-audit",
        "--no-fund",
        "--package-lock-only",
        "--dry-run",
        "--legacy-peer-deps",
        "--include-workspace-root",
        "--workspaces",
    }
)

MOVING_TAGS = ("latest", "next", "beta", "canary", "rc", "dev")
# `run:` joins the lead-ins for the workflow arm. Without it the gate matched
# `run: cd "$HOME" && npm install -g x@latest` (via the `&&`) but NOT the plainer
# `run: npm install -g x@latest` -- caught by this file's own control, which is
# the whole reason the workflow cases plant both shapes.
NPM_RE = re.compile(r"(?:^|&&|;|\|\||\bRUN\s+|\brun:\s*)\s*npm\s+(install|i|add)\b([^&;|\n]*)")


def _tracked() -> list[str]:
    r = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--recurse-submodules"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [] if r.returncode != 0 else [p for p in r.stdout.split() if "node_modules/" not in p]


def dockerfiles() -> list[str]:
    return [p for p in _tracked() if Path(p).name.startswith("Dockerfile")]


def workflows() -> list[str]:
    """WORKFLOWS TOO, since 2026-09-04, and the omission cost a red the same night.

    This gate shipped scanning Dockerfiles only, caught three unpinned installs there,
    and reported a clean tree while `.github/workflows/ci-quality.yml` ran
    `npm install -g agent-browser@latest` on every run of the tutorial-player gate. A
    version that moves on its own is a CI result that changes with no commit behind
    it -- the exact class this gate exists for -- and scoping it by FILE TYPE rather
    than by the thing it forbids left the largest population of `npm install -g` lines
    in the repo unscanned.
    """
    return [
        p
        for p in _tracked()
        if (p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")))
        or (p.startswith(".github/actions/") and p.endswith("action.yml"))
    ]


def scanned() -> list[str]:
    return dockerfiles() + workflows()


def unpinned_specs(args: str) -> list[str]:
    """Package specs in an npm-install argument string that name no fixed version."""
    out = []
    prev_flag_wants_value = False
    for tok in args.split():
        # A FLAG'S ARGUMENT IS NOT A PACKAGE. `npm install --prefix private/account`
        # read `private/account` as an unpinned package name and reported
        # cleanup-preview.yml as a finding -- caught the moment the gate started
        # scanning workflows, where `--prefix` and `-w` are common and Dockerfiles
        # had none. A long flag with no `=` takes the next token; that one rule
        # covers --prefix, --workspace, --registry, --omit and the rest.
        if prev_flag_wants_value:
            prev_flag_wants_value = False
            continue
        if tok.startswith("--") and "=" not in tok:
            prev_flag_wants_value = tok not in _VALUELESS_LONG_FLAGS
            continue
        if tok.startswith("-") or ("=" in tok and tok.startswith("--")):
            continue
        if tok in ("&&", "\\", "|"):
            continue
        # a path or a flag value, not a package
        if tok.startswith(("/", "./", "$")) or tok.endswith((".tgz", ".tar.gz")):
            continue
        name, sep, ver = tok.rpartition("@")
        if tok.startswith("@") and tok.count("@") == 1:
            name, sep, ver = tok, "", ""  # a bare scoped name, e.g. @openai/codex
        if not sep or not name:
            out.append(tok)
            continue
        if "${" in ver or ver.startswith("$"):
            continue  # an ARG is a value in the file: reviewable and diffable
        if ver.lower() in MOVING_TAGS:
            out.append(tok)
    return out


LOCK_COPY_RE = re.compile(r"^\s*COPY\b.*\b(package-lock\.json|package\*\.json)\b")
FROM_RE = re.compile(r"^\s*FROM\b", re.IGNORECASE)


def findings_for(text: str, kind: str = "dockerfile") -> tuple[list[tuple[str, str]], int]:
    """([(line, why)], number of npm-install lines seen) for one Dockerfile.

    A bare `npm install` with no package list is judged on whether a LOCKFILE reached
    THIS STAGE. Per-stage, not per-file, and that is not pedantry -- it is the exact
    false negative this gate nearly shipped with. private/account/Dockerfile's FIRST
    stage was fixed on 2026-09-04 to copy `package*.json` and run `npm ci`; a
    whole-file scan then read that one COPY as forgiveness for the two LATER stages,
    which still copy `package.json` alone and still re-resolve their trees live. The
    gate written to catch tonight's break would have reported tonight's break clean.

    The count is returned so the caller can refuse a verdict when NOTHING was
    inspected: "no Dockerfile installs anything" is what a broken scan looks like.
    """
    out: list[tuple[str, str]] = []
    seen = 0
    has_lock = False
    for raw in text.split("\n"):
        line = raw.strip()
        if FROM_RE.match(line):
            has_lock = False  # a new stage inherits no COPY from the previous one
            continue
        if line.startswith("#"):
            continue
        if LOCK_COPY_RE.match(line):
            has_lock = True
        m = NPM_RE.search(line)
        if not m:
            continue
        seen += 1
        args = m.group(2)
        # `npm ci` never reaches here (the verb list excludes it); a plain install
        # with no package list resolves from package.json, which is only reproducible
        # if a lockfile came with it.
        specs = unpinned_specs(args)
        if kind == "workflow":
            # A BARE `npm install` MEANS SOMETHING ELSE IN A WORKFLOW, and treating
            # the two alike produced four false findings the moment this gate was
            # widened. A Dockerfile stage sees only what it COPYs, so `npm install`
            # with no lockfile beside it really does resolve live. A workflow step
            # runs against a full checkout with package-lock.json already on disk.
            # What still applies here is the half that broke CI: a package spec that
            # names no fixed version.
            if specs:
                out.append((line, "unpinned package(s): " + ", ".join(specs)))
            continue
        if not specs and "-g" not in args.split():
            if has_lock:
                continue  # package.json plus its lockfile: reproducible enough
            out.append(
                (
                    line,
                    (
                        "resolves package.json live, because no lockfile is COPYed into "
                        "this STAGE; COPY package*.json into it and use `npm ci`"
                    ),
                )
            )
        elif specs:
            out.append((line, "unpinned package(s): " + ", ".join(specs)))
    return out, seen


def selftest() -> int:
    bad = 0

    def check(label, ok, detail=""):
        nonlocal bad
        print("  %s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else "  <- %s" % detail))
        if not ok:
            bad += 1

    cases = [
        (
            "RUN npm install -g @openai/codex @google/gemini-cli",
            1,
            "a bare scoped name is unpinned",
        ),
        ("RUN npm install -g agent-browser@latest", 1, "@latest is a moving target, not a pin"),
        ("RUN npm install -g agent-browser@0.36.0", 0, "an exact version passes"),
        ("RUN npm install -g agent-browser@${AGENT_BROWSER_VERSION}", 0, "an ARG is a pin"),
        ("RUN npm ci --ignore-scripts", 0, "npm ci is pinned by construction"),
        ("RUN npm install --ignore-scripts", 1, "a bare project install with no lockfile is not"),
        ("#RUN npm install -g whatever", 0, "a commented line is not an install"),
        (
            "RUN apk add --no-cache python3 && npm install -g typescript@6.0.3",
            0,
            "a pinned install after && passes",
        ),
        (
            "RUN apk add --no-cache python3 && npm install -g typescript",
            1,
            "an UNPINNED install after && is still found",
        ),
    ]
    for line, want, label in cases:
        got = len(findings_for(line)[0])
        check(label, got == want, "got %d finding(s), want %d" % (got, want))

    check(
        "a long flag's ARGUMENT is not read as a package",
        len(findings_for("      - run: npm install --prefix private/account", "workflow")[0]) == 0,
        findings_for("      - run: npm install --prefix private/account", "workflow")[0],
    )
    check(
        "CONTROL: a boolean long flag does not swallow the package after it",
        len(findings_for("      - run: npm install -g --ignore-scripts x@latest", "workflow")[0])
        == 1,
        findings_for("      - run: npm install -g --ignore-scripts x@latest", "workflow")[0],
    )

    # THE WORKFLOW ARM, both directions. It was added after the gate shipped
    # Dockerfile-only and reported a clean tree while ci-quality.yml installed
    # `agent-browser@latest` on every run -- so the case that matters most is the one
    # this gate could not see, and the case beside it is the false finding that
    # widening produced on the first try.
    wf_bad = "      - run: npm install -g agent-browser@latest"
    check(
        "workflow: an unpinned GLOBAL install is a finding",
        len(findings_for(wf_bad, "workflow")[0]) == 1,
        findings_for(wf_bad, "workflow")[0],
    )
    wf_ok = '      - run: npm install -g "agent-browser@$AGENT_BROWSER_VERSION"'
    check(
        "workflow CONTROL: a version from an env var is a pin",
        len(findings_for(wf_ok, "workflow")[0]) == 0,
        findings_for(wf_ok, "workflow")[0],
    )
    wf_bare = "      - run: cd private/account && npm install"
    check(
        "workflow: a BARE install is NOT a finding (a checkout carries the lockfile)",
        len(findings_for(wf_bare, "workflow")[0]) == 0,
        findings_for(wf_bare, "workflow")[0],
    )
    check(
        "and the same bare line in a DOCKERFILE still is",
        len(findings_for(wf_bare, "dockerfile")[0]) == 1,
        findings_for(wf_bare, "dockerfile")[0],
    )

    # THE LOCKFILE ARM, both answers, because it is the one that decides whether
    # tonight's actual break is reported or forgiven.
    with_lock = "COPY package*.json ./\nRUN npm install --ignore-scripts"
    check(
        "CONTROL: a bare install IS forgiven when a lockfile is COPYed in",
        len(findings_for(with_lock)[0]) == 0,
        findings_for(with_lock)[0],
    )
    no_lock = "COPY private/account/package.json ./\nRUN npm install --omit=dev"
    check(
        "a bare install with only package.json copied is still a finding",
        len(findings_for(no_lock)[0]) == 1,
        findings_for(no_lock)[0],
    )
    check(
        "the lockfile arm does not forgive an UNPINNED GLOBAL install",
        len(findings_for("COPY package*.json ./\nRUN npm install -g x@latest")[0]) == 1,
    )
    return bad


def main() -> int:
    print("docker npm pins: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2

    try:
        excl = json.loads(EXCLUSIONS.read_text(encoding="utf-8")).get("exclusions") or {}
    except (OSError, ValueError):
        excl = {}

    # THE TREE MUST BE ALL THERE BEFORE ANY VERDICT IS HONEST, and this gate learned
    # it the same way check_syncpack_sources.py did -- from CI, on its first run.
    #
    # quality-static checks out NO submodules. private/account/Dockerfile then simply
    # vanishes from the enumeration, its two exclusions match nothing, and the
    # dead-scaffold arm fires: two confident findings telling the reader to delete
    # entries that are entirely correct (job 100870135489). A missing file is
    # "cannot verify", never "your entry is dead".
    #
    # Checked against the paths the CONFIG names, not against what the scan found:
    # asking the enumeration whether the enumeration is complete answers itself.
    absent = sorted({k.split(":", 1)[0] for k in excl} - set(scanned()))
    if absent:
        print(
            "✗ CANNOT VERIFY: these Dockerfiles are named by "
            + EXCLUSIONS.name
            + " but are not present in this checkout:\n"
            + "".join(f"    {d}\n" for d in absent)
            + "  They are in submodules. Each one drops silently out of the enumeration,\n"
            "  which turns a correct exclusion into a 'dead entry' finding.\n"
            "  Fix: run this gate in a job whose checkout sets `submodules: true`.",
            file=sys.stderr,
        )
        return 1

    n_wf = len(workflows())
    if n_wf < MIN_WORKFLOWS:
        print(
            "VACUOUS INPUT: git listed %d workflow/action file(s), floor is %d. The "
            "enumeration lost the half of the corpus this gate was widened to cover."
            % (n_wf, MIN_WORKFLOWS),
            file=sys.stderr,
        )
        return 1

    found = scanned()
    if len(found) < MIN_DOCKERFILES:
        print(
            "VACUOUS INPUT: git listed %d Dockerfile(s), floor is %d. The enumeration lost "
            "the corpus; refusing a verdict." % (len(found), MIN_DOCKERFILES),
            file=sys.stderr,
        )
        return 1

    problems: list[str] = []
    used: set[str] = set()
    n_install = 0
    for rel in sorted(found):
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits, seen = findings_for(text, "workflow" if rel.startswith(".github/") else "dockerfile")
        n_install += seen
        for line, why in hits:
            # EXACT line, not a substring, and the difference is not style. The two
            # excluded lines in private/account/Dockerfile are `npm install` and
            # `npm install --omit=dev && \`; under substring matching the shorter key
            # matches BOTH, the longer one then matches nothing, and the gate reports
            # a live exclusion as dead scaffold. Exact is the only unambiguous key.
            key = next((k for k in excl if k == "%s:%s" % (rel, line)), None)
            if key:
                used.add(key)
                continue
            problems.append("%s: %s\n      %s" % (rel, why, line))

    for key, reason in sorted(excl.items()):
        if not str(reason).startswith("BLOCKER:") or len(str(reason)) < MIN_REASON_CHARS:
            problems.append(
                "%s is excluded with a reason that is not substantive. It must start with "
                "'BLOCKER:' and say what makes that line different." % key
            )
        elif key not in used:
            problems.append(
                "%s excludes a line that no longer exists or is no longer a finding. Delete "
                "it -- an exclusion that suppresses nothing is how a list outlives its "
                "reasons." % key
            )

    # ANTI-VACUITY. A scan that inspected nothing reports a clean tree, and the first
    # draft of this gate did exactly that: it counted FILES WITH FINDINGS and printed
    # "0 with an npm install" beside a tick.
    if n_install == 0:
        print(
            "VACUOUS: %d Dockerfile(s) scanned and NOT ONE runs an npm install. That is a "
            "broken scan, not a clean tree." % len(found),
            file=sys.stderr,
        )
        return 1

    if problems:
        print("✗ docker npm pins (%d problem(s)):" % len(problems), file=sys.stderr)
        for p in problems:
            print("    %s" % p, file=sys.stderr)
        return 1

    print(
        "✓ npm pins: %d file(s) scanned -- %d Dockerfile(s) (floor %d) and %d workflow/action "
        "file(s) (floor %d) -- %d npm install line(s) inspected, every package version fixed "
        "or excluded with a stated reason"
        % (len(found), len(dockerfiles()), MIN_DOCKERFILES, n_wf, MIN_WORKFLOWS, n_install)
    )
    print(
        "  Blind spot: this proves a VERSION is named. Whether that version still exists, "
        "and whether its own transitive tree is locked, is the lockfile's job -- which is "
        "why a bare `npm install` is a finding here even with no package list."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
