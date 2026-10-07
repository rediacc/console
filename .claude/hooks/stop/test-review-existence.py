#!/usr/bin/env python3
"""Controls for the per-commit reviewer's existence oracle (`wl_review.apply_existence_oracle`, worklist #95564d76).

    python3 .claude/hooks/stop/test-review-existence.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/), so no table edit is needed to wire this file in.

WHAT IS UNDER TEST. The reviewer sees hunks, not files, and on 2026-10-07 it recorded four claims that a name was undefined or not imported on 30117014 (two [high], two [medium]) whose definitions sat outside the diff it was sent; each blocked a stop until hand-refuted. The oracle looks each named identifier up in the commit's own tree and closes a claim whose every identifier exists, as
`not-a-bug | refuted by the existence oracle ... | oracle <isoZ>`, in the record.

HOW. Every case runs through the REAL pipeline, `run_review` with a fake model that returns one finding, against a scratch git repository whose files are the real lines of the reviewed commits (trimmed to the definitions and uses the claims are about; the text of every claim is the recorded one, verbatim). So the same controls are red on a reviewer without the oracle (each refutable claim
stays `open`), which is how this file was proven: run against the pre-fix wl_review.py, 4 of the real-claim controls failed.

BOTH DIRECTIONS. A refutation needs a positive hit for every name, so the TRUE findings must stay open: the planted `foo` with no definition anywhere, a name bound only in another function's scope, a repo module that lacks the attribute, an undeclared attribute, a missing stdlib attribute, a module that defines `__getattr__`. And claims that are not about existence at all (a JS value of
`undefined`, a quoted string that "does not appear", a hidden implementation "not shown in diff", a prose file, and the two fad44674 misreadings, which name code that exists but read it wrongly) must stay open, because the oracle cannot judge them and must not pretend to.
"""

import importlib.util
import os
import pathlib
import subprocess
import sys

import wl_review as R

_CI = pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci"


def _by_file(name):
    """A `.ci/rediacc_ci` module loaded BY FILE, not through a `sys.path` hop (test_canonical_sys_path_hop.py freezes those)."""
    spec = importlib.util.spec_from_file_location(name, _CI / ("%s.py" % name))
    if spec is None or spec.loader is None:
        raise SystemExit("%s: .ci/rediacc_ci/%s.py is missing" % (__file__, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


controls = _by_file("controls")
runtmp = _by_file("runtmp")

CONTROL_FLOOR = 140
T = controls.Controls("review-existence", floor=CONTROL_FLOOR)
check = T.check

BRANCH = "1007-1"
NOW = 1_791_000_000

# ---- the fixture tree: real lines from 30117014a and fad446748, trimmed ------------------------

NONDRAFT = ".claude/rediacc_hooks/guards/block_nondraft_pr_create.py"
STALE = ".claude/rediacc_hooks/guards/block_stale_pr_branch_date.py"
SHELLSCAN = ".claude/rediacc_hooks/shellscan.py"
RETRY = ".ci/rediacc_ci/quality/gh_retry_reads.py"
LAZY = ".claude/rediacc_hooks/lazy_mod.py"
PLANT = "src/plant.py"
RUN_TS = "scripts/ci-runner/run.ts"
DOC = ".claude/commands/pr-merge.md"

FILES = {
    NONDRAFT: '''"""Enforce the draft-PR flow on `gh pr create`."""

import re

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.wellknown import ACCOUNT_REPO, ELITE_REPO, GH_REPO, HOMEBREW_TAP_REPO, RENET_REPO

CHAIN = "pre-bash"
ORDER = 22

UNRESOLVED_MESSAGE = (
    "❌ BLOCKED: this 'gh pr create' names its repository through a variable or a command "
    "substitution this hook cannot evaluate, so whether it must be a draft cannot be decided. "
    "Name the repository literally: --repo %s with --draft, or --repo "
    "rediacc/<renet|account|elite> without it." % GH_REPO
)
''',
    STALE: '''"""A PR must not be opened from a branch carrying an OLD date."""

import pathlib

from rediacc_hooks import hookio, shellscan


def check(ev, cmd, scan):
    cwd = ev.field("cwd")
    if not (cwd != "" and pathlib.Path(cwd).is_dir()):
        cwd = ev.cwd
    heads = []
    runs = shellscan.gh_pr_runs(cmd, "create")
    if runs:
        for run_ in runs:
            parsed = shellscan.gh_args(run_.xargv)
            if parsed.on("help"):
                continue
            head = parsed.last("head") or ""
            heads.append("" if shellscan.unresolved(head) else head)
    return heads


def other(ev):
    stray_local = ev.cwd
    return stray_local
''',
    SHELLSCAN: '''"""The one shell walker the guards share."""

import re

_UNRESOLVED = "\\x00unresolved\\x00"


class _Run:
    """One simple command bash would execute, as the walk found it."""

    __slots__ = (
        "argv",
        "canonical",
        "cwd",
        "env",
        "git_dir",
        "git_sub",
        "name",
        "usage",
        "vars",
        "writes",
        "xargv",
    )

    def __init__(self, name, argv, canonical, cwd, env=None):
        self.name = name
        self.argv = argv
        self.xargv = None


def unresolved(value):
    """Whether an expanded value carries something the walk could not evaluate."""
    return value is not None and _UNRESOLVED in value


def _assignment(text):
    return None


def _shell_builtin(base, argv, shell):
    """The shell state after `export`, `declare -x`/`typeset -x` or `unset` with `argv`, as a new dict."""
    if base not in ("export", "declare", "typeset", "unset"):
        return shell
    letters = "".join(a[1:] for a in argv if a.startswith("-") and len(a) > 1 and a != "--")
    names = [a for a in argv if not (a.startswith("-") and len(a) > 1)]
    out = dict(shell)
    exported = "n" not in letters or base != "export"
    for arg in names:
        hit = _assignment(arg)
        if hit:
            name, value, append = hit
            old = out.get(name, (None, False))[0]
            out[name] = ((old or "") + value if append else value, exported)
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", arg):
            out[arg] = (out.get(arg, (None, False))[0], exported)
    return out
''',
    RETRY: '''"""Every `gh` read in CI goes through the retrying wrapper."""

import argparse
import ast
import dataclasses
import functools
import hashlib
import json
import pathlib


@functools.cache
def _shellscan():
    """`rediacc_hooks.shellscan`, the one gh argv parser."""
    return None
''',
    LAZY: '''"""A module whose attributes are computed, so no attribute is provably absent."""


def __getattr__(name):
    return name
''',
    PLANT: '''"""Planted: `foo` is used and defined nowhere, and `lazy_mod.anything` resolves through __getattr__."""

import functools
from typing import TYPE_CHECKING

from rediacc_hooks import lazy_mod, shellscan


def caller():
    return foo(1)


def helper():
    only_here = 1
    return only_here


def user():
    return only_here + shellscan.no_such_helper() + functools.cachee + lazy_mod.anything


def typo(run_):
    return run_.xargvv


if TYPE_CHECKING:
    from rediacc_hooks import only_for_types


def scoped():
    squares = [sq for sq in range(3)]
    return sq, squares


def declares():
    global never_assigned
    return never_assigned, only_for_types
''',
    RUN_TS: """import { spawnSync } from 'node:child_process';

function gitTry(args: string[]): string | null {
  const r = spawnSync('git', args, { encoding: 'utf8' });
  return r.status === 0 ? r.stdout : null;
}

export function incrementalInputOf(file: string): string | null {
  return gitTry(['show', `HEAD:${file}`]);
}

export function lookup(map: Map<string, string>, key: string): number {
  return map.get(key).length;
}

export function stale(): string {
  return missingHelper();
}
""",
    DOC: """# pr-merge

Which the hook, P-A1 and the merge gate count alike.
""",
}


def line_of(path, needle, nth=1):
    """1-based line of the `nth` line of FILES[path] containing `needle`."""
    seen = 0
    for n, text in enumerate(FILES[path].split("\n"), start=1):
        if needle in text:
            seen += 1
            if seen == nth:
                return n
    raise SystemExit("fixture %s has no line containing %r" % (path, needle))


# (label, file, line, severity, claim, want refuted?, evidence substrings a refutation must carry)
CASES = [
    # -- the four 2026-10-07 existence claims on 30117014, verbatim: each must be refuted, citing where the name lives
    (
        "30117014.1 GH_REPO imported",
        NONDRAFT,
        line_of(NONDRAFT, "without it."),
        "high",
        'UNRESOLVED_MESSAGE constant definition uses % GH_REPO where GH_REPO is undefined; line contains `"...without it." % GH_REPO` which will raise NameError when module imports.',
        True,
        ["GH_REPO bound at %s:%d" % (NONDRAFT, line_of(NONDRAFT, "import ACCOUNT_REPO"))],
    ),
    (
        "30117014.2 xargv declared in shellscan's __slots__",
        STALE,
        line_of(STALE, "run_.xargv"),
        "high",
        "Typo in attribute access: `run_.xargv` should be `run_.argv`; will raise AttributeError at runtime when the code reaches this line during a gh pr create.",
        True,
        ["run_.xargv declared at %s:%d" % (SHELLSCAN, line_of(SHELLSCAN, '"xargv",'))],
    ),
    (
        "30117014.3 functools imported",
        RETRY,
        line_of(RETRY, "def _shellscan"),
        "medium",
        "_shellscan() function uses @functools.cache decorator but the import of functools is not shown in the diff (diff starts at line 144); if not imported, NameError occurs.",
        True,
        ["functools imported at %s:%d" % (RETRY, line_of(RETRY, "import functools"))],
    ),
    (
        "30117014.4 shellscan.unresolved defined",
        STALE,
        line_of(STALE, "shellscan.unresolved"),
        "medium",
        "Calls shellscan.unresolved(head) but this function does not appear in the truncated shellscan.py diff; likely AttributeError at runtime if the function does not exist.",
        True,
        [
            "shellscan.unresolved defined at %s:%d"
            % (SHELLSCAN, line_of(SHELLSCAN, "def unresolved"))
        ],
    ),
    # -- the two fad44674 claims, verbatim: misreadings of code that exists, not existence claims. The oracle cannot judge them and must leave them open (a quote check was measured and rejected: on the 197 recorded findings it would have closed 3 that were later FIXED).
    (
        "fad44674.1 misquoted unpacking stays open",
        SHELLSCAN,
        line_of(SHELLSCAN, "old = out.get"),
        "high",
        "Line `old, exp = shell.get(name, (None, False))[0]` attempts to unpack the first element (a string value) into two variables, causing TypeError at runtime when `export VAR=value` or `declare -x VAR=value` statements are encountered. Should be `old, _ = shell.get(name, (None, False))`.",
        False,
        [],
    ),
    (
        "fad44674.2 writes-to-shell misreading stays open",
        SHELLSCAN,
        line_of(SHELLSCAN, "out[name] = "),
        "high",
        "Modification writes to `shell` parameter instead of the `out` dict being returned, so variable state changes from export/declare statements are lost. The returned `out` dict won't include environment updates, breaking the new GH_REPO tracking feature. Should write to `out[name]` not `shell[name]`.",
        False,
        [],
    ),
    # -- the 3cab21d7.1 shape on TypeScript, verbatim: gitTry is declared in the file
    (
        "3cab21d7.1 gitTry declared (TS)",
        RUN_TS,
        line_of(RUN_TS, "return gitTry"),
        "high",
        "incrementalInputOf calls gitTry(['show', ...]) at lines 2656, 2662, and 2666, but gitTry is never defined in this file or imported. This will crash with ReferenceError when a --quick run attempts incremental logic.",
        True,
        ["gitTry declared at %s:%d" % (RUN_TS, line_of(RUN_TS, "function gitTry"))],
    ),
    # -- TRUE findings: every one must stay open
    (
        "PLANT foo defined nowhere",
        PLANT,
        line_of(PLANT, "return foo(1)"),
        "high",
        "`foo` is called but never defined or imported; caller() raises NameError on its first call.",
        False,
        [],
    ),
    (
        "PLANT a name bound only in another function's scope",
        PLANT,
        line_of(PLANT, "return only_here +"),
        "high",
        "user() reads only_here, which is not defined in its scope (it is local to helper()), so it raises NameError.",
        False,
        [],
    ),
    (
        "PLANT a repo module that lacks the attribute",
        PLANT,
        line_of(PLANT, "return only_here +"),
        "high",
        "shellscan.no_such_helper is not defined in rediacc_hooks/shellscan.py, so user() raises AttributeError (no such function).",
        False,
        [],
    ),
    (
        "PLANT an attribute declared nowhere",
        PLANT,
        line_of(PLANT, "run_.xargvv"),
        "high",
        "Typo: `run_.xargvv` should be `run_.xargv`; AttributeError at runtime.",
        False,
        [],
    ),
    (
        "PLANT a stdlib attribute that does not exist",
        PLANT,
        line_of(PLANT, "return only_here +"),
        "medium",
        "`functools.cachee` does not exist in the stdlib, raising AttributeError (typo for functools.cache).",
        False,
        [],
    ),
    (
        "PLANT a module with __getattr__ proves nothing",
        PLANT,
        line_of(PLANT, "return only_here +"),
        "medium",
        "lazy_mod.anything is not defined in lazy_mod; AttributeError (no such attribute).",
        False,
        [],
    ),
    (
        "PLANT a JS name declared nowhere",
        RUN_TS,
        line_of(RUN_TS, "missingHelper()"),
        "high",
        "stale() calls missingHelper(), which is not defined or imported anywhere; ReferenceError at runtime.",
        False,
        [],
    ),
    # -- NOT existence claims: each must stay open
    (
        "JS `undefined` as a value is not an existence claim",
        RUN_TS,
        line_of(RUN_TS, "map.get(key).length"),
        "high",
        "lookup() returns map.get(key).length, but map.get returns undefined for an absent key, so `.length` throws a TypeError.",
        False,
        [],
    ),
    (
        "f473fdd6.1 a string that does not appear (no name-error) stays open",
        RETRY,
        line_of(RETRY, "def _shellscan"),
        "high",
        'The control mutation check searches for literal string "COULD NOT TELL %s" to verify the mutation planted correctly, but this string doesn\'t appear in the module being tested or in the MUTANT_ARM, so the check will always pass even if the mutation fails to plant, rendering the control ineffective.',
        False,
        [],
    ),
    (
        "e6cacb57.2 a hidden implementation 'not shown in diff' stays open",
        RETRY,
        line_of(RETRY, "def _shellscan"),
        "medium",
        "fetch_run_jobs docstring claims it 'Raises ghx.GhError', but the new _api_json default implementation calls .json() on the GhResult without verifying that ghx.GhResult.json() actually raises ghx.GhError on failure (implementation not shown in diff); this may raise a different exception type.",
        False,
        [],
    ),
    (
        "c0b7b16f.3 an undefined abbreviation in prose stays open (it was FIXED)",
        DOC,
        line_of(DOC, "P-A1"),
        "low",
        "References undefined abbreviation 'P-A1' in 'which the hook, P-A1 and the merge gate count alike'--no definition or explanation provided for this designation.",
        False,
        [],
    ),
]


# ---- the scratch repository ------------------------------------------------------------------

root = pathlib.Path(runtmp.run_dir("review-existence-suite-"))
os.environ["TMPDIR"] = str(root / "tmp")
(root / "tmp").mkdir()
GIT = [
    "git",
    "-C",
    str(root),
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "user.name=t",
    "-c",
    "user.email=t@example.invalid",
]


def git(*args):
    return subprocess.run([*GIT, *args], check=True, capture_output=True, text=True).stdout.strip()


git("init", "-q", "-b", BRANCH)
for rel, body in FILES.items():
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
git("add", "-A")
git("commit", "-q", "-m", "base")

CFG = dict(R.DEFAULTS, slot_wait_s=5, max_concurrent=1)


def reviewer_for(finding):
    calls = []

    def reviewer(_prompt, _cfg, _log):
        calls.append(1)
        return (
            {
                "verdict": "findings",
                "findings": [finding],
                "labels": {"bump": "patch", "kind": ["bug"], "why": "x"},
            },
            "",
            None,
        )

    return reviewer, calls


def review_case(n, path, line, severity, claim):
    """Commit a one-line touch of `path` (appended, so no line moves), review it with a model that returns this one finding, and return (record, model calls)."""
    marker = "// case %d\n" % n if path.endswith(".ts") else "# case %d\n" % n
    with (root / path).open("a", encoding="utf-8") as fh:
        fh.write(marker if not path.endswith(".md") else "\ncase %d\n" % n)
    git("add", "--", path)
    git("commit", "-q", "-m", "fix(x): case %d" % n)
    sha = git("rev-parse", "HEAD")
    reviewer, calls = reviewer_for(
        {"severity": severity, "file": path, "line": line, "claim": claim}
    )
    out = R.run_review(
        root, "console", sha, BRANCH, cfg=CFG, reviewer=reviewer, now=NOW, log=lambda *_a: None
    )
    review, err = R.read_review(out) if out is not None else (None, "nothing written")
    return review, err, len(calls)


refuted_ids, open_ids, id_of = [], [], {}
for n, (label, path, line, severity, claim, want_refuted, evidence) in enumerate(CASES, start=1):
    review, err, ncalls = review_case(n, path, line, severity, claim)
    # The control for the control: the model was really called and its one finding really landed, so an `open` below is the oracle's verdict, not a missing finding.
    check("%s: the fake model was called once" % label, ncalls, 1)
    check("%s: the record parses" % label, err, None)
    if review is None:
        continue
    check("%s: exactly one finding recorded" % label, len(review.findings), 1)
    if not review.findings:
        continue
    f = review.findings[0]
    id_of[label] = f.id
    check("%s: claim recorded verbatim" % label, f.claim, R.normalise_claim(claim))
    check(
        "%s: %s" % (label, "refuted by the oracle" if want_refuted else "left open"),
        f.resolution_kind(),
        "not-a-bug" if want_refuted else "open",
    )
    if want_refuted:
        refuted_ids.append(f.id)
        check("%s: signed by the oracle" % label, " | oracle 20" in f.resolution, True)
        for piece in evidence:
            check("%s: evidence cites %r" % (label, piece), piece in f.resolution, True)
    else:
        open_ids.append((f.id, f.severity))


# ---- what the readers see -------------------------------------------------------------------

st = R.branch_state(root, BRANCH, cfg=CFG, repos=[])
blocking = sorted(f.id for _p, f in st["blocking"])
check(
    "branch_state: the open [high] findings block and no refuted one does",
    blocking,
    sorted(i for i, sev in open_ids if sev == "high"),
)
check("branch_state: no record is malformed", st["malformed"], [])
check(
    "branch_state: no refuted finding is advisory either",
    sorted(set(refuted_ids) & {f.id for _p, f in st["advisory"]}),
    [],
)
surfaced = "\n".join(R.surface_new(root, BRANCH, "feedface-0000", cfg=CFG))
for fid in refuted_ids:
    check(
        "surface_new names refuted %s" % fid,
        "refuted by the existence oracle: [" in surfaced and fid in surfaced,
        True,
    )
check(
    "surface_new names the planted foo finding as an open [high] one",
    "  [high] %s %s:" % (id_of.get("PLANT foo defined nowhere"), PLANT) in surfaced,
    True,
)
check("five refutations, from the real claims", len(refuted_ids), 5)


# ---- the grammar ----------------------------------------------------------------------------

STAMP = "2026-10-07T10:00:00Z"
good = R.Finding("a" * 8 + ".1", "high", "f.py", 1, "in-diff", "x is undefined")
good.resolution = (
    "not-a-bug | refuted by the existence oracle at abc: x bound at f.py:1 | oracle %s" % STAMP
)
check("an oracle-signed not-a-bug parses as not-a-bug", good.resolution_kind(), "not-a-bug")
check("and reads as oracle-refuted", good.oracle_refuted(), True)
human = R.Finding("a" * 8 + ".1", "high", "f.py", 1, "in-diff", "x")
human.resolution = "not-a-bug | evidence at f.py:1 cited by a person | d778be9d %s" % STAMP
check("a person's not-a-bug is not oracle-refuted", human.oracle_refuted(), False)
bogus = R.Finding("a" * 8 + ".1", "high", "f.py", 1, "in-diff", "x")
bogus.resolution = "not-a-bug | refuted by the existence oracle at abc: x | orakle %s" % STAMP
check(
    "a misspelled signer is not a resolution (the grammar did not open wide)",
    bogus.resolution_kind(),
    "",
)
rec = R.Review(sha="a" * 40, verdict="findings", findings=[good], reviewed_at=STAMP)
check(
    "an oracle-signed record round-trips through render/parse",
    R.parse(R.render(rec)).findings[0].resolution,
    good.resolution,
)


# ---- the pieces, directly ---------------------------------------------------------------------

check(
    "claimed_identifiers: dotted, called and snake names; strings in spans blanked; exceptions and files dropped",
    R.claimed_identifiers(
        'Calls shellscan.unresolved(head) in `x = f("GH_REPO")` but this function does not appear in shellscan.py; AttributeError'
    ),
    ["shellscan.unresolved", "f", "x"],
)
check(
    "claimed_identifiers: the subject of 'is not defined' is taken past its noun",
    R.claimed_identifiers("The _git function is not defined; similar paths use _run()"),
    ["_run", "_git"],
)
check(
    "claimed_identifiers: a plain-word subject is taken",
    R.claimed_identifiers("caller() reads x, and x is undefined there"),
    ["caller", "x"],
)
check(
    "claimed_identifiers: a pronoun subject is kept, so it can only fail the lookup",
    R.claimed_identifiers("caller() reads a global and it is undefined"),
    ["caller", "it"],
)
check(
    "claimed_identifiers: a relative subject resolves to the word it refers to",
    R.claimed_identifiers("caller() reads x, which is undefined"),
    ["caller", "x"],
)
check(
    "claimed_identifiers: an elided subject is the clause's first word",
    R.claimed_identifiers(
        "contextlib module is used in `contextlib.suppress()` but is not imported"
    ),
    ["contextlib.suppress", "contextlib"],
)
check(
    "claimed_identifiers: a method named like a file extension is still a call",
    R.claimed_identifiers("ghx.GhResult.json() is not defined"),
    ["ghx.GhResult.json"],
)
check(
    "claimed_identifiers: a name quoted in prose is still checked",
    R.claimed_identifiers("the helper 'foo_bar' is not defined"),
    ["foo_bar"],
)
check("existence_claim: NameError alone", R.existence_claim("calling it raises NameError"), True)
check("existence_claim: 'not imported' alone", R.existence_claim("functools is not imported"), True)
check(
    "existence_claim: 'does not appear' without a name error is not one",
    R.existence_claim("this string does not appear in the module"),
    False,
)
check(
    "existence_claim: a bare AttributeError is a type claim, not one",
    R.existence_claim("rel is a Path, so .startswith() raises AttributeError"),
    False,
)
check(
    "existence_claim: 'undefined' is a name claim on Python",
    R.existence_claim("x is undefined here", "a.py"),
    True,
)
check(
    "existence_claim: 'undefined' is a value on TypeScript",
    R.existence_claim("map.get returns undefined here", "a.ts"),
    False,
)
tree = R._Tree(root, git("rev-parse", "HEAD"))
plant_line = line_of(PLANT, "return foo(1)")
check(
    "_py_verify: foo is found nowhere",
    R._py_verify(tree, PLANT, plant_line, "foo"),
    "",
)
check(
    "_py_verify control: caller IS found, so the empty answer above is about foo",
    R._py_verify(tree, PLANT, plant_line, "caller").startswith("caller bound at %s:" % PLANT),
    True,
)
check(
    "_py_verify: a builtin is found",
    R._py_verify(tree, PLANT, plant_line, "len"),
    "len is a builtin",
)
check(
    "module_file: an absolute import resolves by suffix",
    tree.module_file("rediacc_hooks.shellscan", PLANT),
    SHELLSCAN,
)
check("module_file: an unknown module is empty", tree.module_file("no.such.mod", PLANT), "")
check(
    "refute_existence: a plain-word subject that is unbound keeps the claim open though caller() exists",
    R.refute_existence(
        tree,
        R.Finding(
            "x.1",
            "high",
            PLANT,
            plant_line,
            "in-diff",
            "caller() reads x, which is undefined; NameError",
        ),
    ),
    "",
)
check(
    "refute_existence control: the same shape about a bound name is refuted",
    R.refute_existence(
        tree,
        R.Finding(
            "x.1",
            "high",
            PLANT,
            plant_line,
            "in-diff",
            "caller() reads helper, and helper is undefined; NameError",
        ),
    ).startswith("refuted by the existence oracle"),
    True,
)
check(
    "refute_existence: a pronoun subject keeps the claim open though caller() exists",
    R.refute_existence(
        tree,
        R.Finding(
            "x.1",
            "high",
            PLANT,
            plant_line,
            "in-diff",
            "caller() reads a global and it is undefined; NameError",
        ),
    ),
    "",
)
stale_line = line_of(STALE, "run_.xargv")
check(
    "refute_existence: a local of other() named at a line inside check() is NOT bound there (scope, not grep)",
    R.refute_existence(
        tree,
        R.Finding(
            "x.1", "high", STALE, stale_line, "in-diff", "stray_local is not defined; NameError"
        ),
    ),
    "",
)
check(
    "refute_existence: the same claim quoting the real line is judged in that line's scope and refuted",
    R.refute_existence(
        tree,
        R.Finding(
            "x.1",
            "high",
            STALE,
            stale_line,
            "in-diff",
            "`stray_local = ev.cwd` but stray_local is not defined; NameError",
        ),
    ).startswith("refuted by the existence oracle"),
    True,
)
scoped_line = line_of(PLANT, "return sq, squares")
declares_line = line_of(PLANT, "return never_assigned")
for label, line, claim in (
    (
        "a comprehension target is not bound outside it",
        scoped_line,
        "sq is not defined in scoped(); NameError",
    ),
    (
        "a `global` declaration binds nothing",
        declares_line,
        "never_assigned is not defined anywhere; NameError",
    ),
    (
        "an `if TYPE_CHECKING:` import is unbound at runtime",
        declares_line,
        "only_for_types is not imported at runtime; NameError",
    ),
):
    check(
        "refute_existence: %s" % label,
        R.refute_existence(tree, R.Finding("x.1", "high", PLANT, line, "in-diff", claim)),
        "",
    )
check(
    "refute_existence control: squares, bound in the same function, IS found",
    R.refute_existence(
        tree,
        R.Finding(
            "x.1", "high", PLANT, scoped_line, "in-diff", "squares is not defined; NameError"
        ),
    ).startswith("refuted by the existence oracle"),
    True,
)
check(
    "_stdlib_has: `this` (prints on import) has `s`, and is still never imported to say so",
    (R._stdlib_has("this", ["s"]), "this" in sys.modules),
    (False, False),
)
check(
    "_stdlib_has control: an inert stdlib attribute is found",
    R._stdlib_has("functools", ["cache"]),
    True,
)
check(
    "refute_existence: a non-code path is never judged",
    R.refute_existence(
        tree, R.Finding("x.1", "high", DOC, 3, "in-diff", "`x` is not defined; NameError")
    ),
    "",
)

T.exit()
