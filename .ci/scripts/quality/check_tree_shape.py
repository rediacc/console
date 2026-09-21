#!/usr/bin/env python3
"""check:ci-tree-shape -- what may sit at the repository root and under agent/.

Logic is in `rediacc_ci.quality.tree_shape`, which pytest and this file's `--selftest` import directly; the permitted classes are data in `.ci/policy/tree-shape.json`. Both carry the reasoning and it is not repeated here.

WHY THIS GATE EXISTS RATHER THAN A TIDY-UP. Debris (`aa.jsonl`, `zz.jsonl`, `.events.jsonl`, `.lastevent-*.json`, `.requests`, `.local/`, `claude/`) sat untracked at the repository root, written by the old bash worklist suites, and a second reggate ledger appeared under `.claude/hooks/stop/agent/` because `wl_reggate.debt_dir()` fell back to a cwd-relative root. Deleting those
files fixes today. This fixes the class.

EIGHT FINDINGS, EACH WITH A PLANTED CONTROL: T1 a stray root file, T2 a new top-level directory, T3 a stray file under agent/, T4 a directory under agent/ that is neither reserved nor a session slug, T5 the policy and `wl_store.AGENT_RESERVED_DIRS` disagreeing, T6 a repository path built from a bare relative string, T7 the enumeration losing the tree, T8 a baseline entry that no
longer fires.

THE BASELINE IS SHRINK-ONLY AS A SET and the decision is shared with `check:ci-language-policy` through `rediacc_ci.quality.shrink_only`. A count would let through the one change that matters most: delete one stray and add another in the same commit, and the total is unchanged while the shape has gained a file nobody decided on.

WHAT A GREEN HERE DOES NOT MEAN. It says nothing about the CONTENT of any file, nothing about trees outside the root and `agent/`, and nothing about a gitignored file: `--exclude-standard` is deliberate, because an ignored build artefact is output rather than a stray.

---- gate ----
step: Tree shape
needs: none
selftest: true
lane: quality-static
why: the repository root and agent/ are where a stray file is invisible, because
     neither is reviewed the way packages/ and docs/ are. Two defects in one week
     were both a missing rule about where a file may be, rather than a bug in any
     one script.
---- end gate ----
"""

import json
import pathlib
import sys

import _cipath  # noqa: F401
from rediacc_ci import controls, gitx, paths
from rediacc_ci.controls import plant
from rediacc_ci.quality import shrink_only
from rediacc_ci.quality import tree_shape as TS

CONTROL_FLOOR = 22

#: How many findings are printed before the rest become a count.
SHOWN = 12


class CannotRunError(RuntimeError):
    """The instrument is missing, which is never a verdict about the tree."""


# --------------------------------------------------------------------------- The fixture the controls plant into.

CLEAN_LISTING = "\n".join(  # noqa: FLY002 -- a LISTING to scan, not a sentence to interpolate
    [
        "CLAUDE.md",
        "package.json",
        "pyproject.toml",
        "conftest.py",
        "run.sh",
        "rdc.sh",
        "README.md",
        "LICENSE",
        "Dockerfile",
        "biome.json",
        ".gitignore",
        ".npmrc",
        "agent/README.md",
        "agent/RULES.md",
        "agent/INDEX.md",
        "agent/DECISIONS.md",
        "agent/PLAN-sample.md",
        "agent/plans/PLAN-other.md",
        "agent/archive/0815-1/STATE.md",
        "agent/worklist/abcd1234.jsonl",
        "agent/reggate/main.jsonl",
        "agent/pr/main.md",
        "agent/legacy/STATE.md",
        "agent/programs/thing/README.md",
        "agent/abcd1234/STATE.md",
        "docs/agent-reference/TRAPS.md",
        "scripts/ci-runner/manifest.ts",
        ".ci/rediacc_ci/paths.py",
        ".claude/settings.json",
        "packages/cli/package.json",
    ]
)

CLEAN_SOURCE = (
    "import pathlib\n"
    "from rediacc_ci import paths\n"
    "def where():\n"
    '    return paths.from_root("agent")\n'
)

RESERVED = {"archive", "programs", "worklist", "reggate", "plans", "pr", "legacy"}
TOP_NAMES = {"agent", "docs", "scripts", ".ci", ".claude", "packages"}
CALLEES = {"open", "os.listdir", "os.scandir"}
FS_METHODS = {"glob", "is_dir", "read_text"}


def _paths(listing: str) -> list[str]:
    return [line for line in listing.splitlines() if line]


def _codes(found: list[TS.Finding]) -> set[str]:
    return {f.code for f in found}


def _policy(root: pathlib.Path) -> dict:
    return TS.load_policy(root)


def selftest() -> int:
    """Every finding, planted and mirrored. The mirror is half the control."""
    tally = controls.Controls("tree shape", floor=CONTROL_FLOOR)
    # THE GATE'S OWN POLICY, NOT THE SUBJECT TREE'S, and `paths.repo_root()` rather than `TS.repo_root()` is what makes that true under `TREE_SHAPE_ROOT`. The controls prove the INSTRUMENT works; reading the fixture's policy would make them a second verdict about the fixture, so a test that deliberately breaks a policy would fail the controls and exit 2 instead of reporting its
    # finding.
    try:
        policy = _policy(paths.repo_root())
    except (OSError, ValueError) as exc:
        tally.fail("the policy file parses", exc)
        return 0 if tally.report() else 1

    clean = _paths(CLEAN_LISTING)

    # T1. A file at the root that no class names.
    tally.check("T1 clean", _codes(TS.finding_t1(TS.split_entries(clean)[0], policy)), set())
    strayed = plant(CLEAN_LISTING, "biome.json\n", "biome.json\naa.jsonl\n")
    tally.check(
        "T1 planted", _codes(TS.finding_t1(TS.split_entries(_paths(strayed))[0], policy)), {"T1"}
    )

    # T2. A new top-level directory.
    tally.check("T2 clean", _codes(TS.finding_t2(TS.split_entries(clean)[1], policy)), set())
    newdir = plant(
        CLEAN_LISTING, "docs/agent-reference/TRAPS.md", "claude/agent-reference/TRAPS.md"
    )
    tally.check(
        "T2 planted", _codes(TS.finding_t2(TS.split_entries(_paths(newdir))[1], policy)), {"T2"}
    )

    # T3. A loose file directly under agent/.
    tally.check("T3 clean", _codes(TS.finding_t3(TS.split_entries(clean)[2], policy)), set())
    loose = plant(CLEAN_LISTING, "agent/RULES.md", "agent/zz.jsonl")
    tally.check(
        "T3 planted", _codes(TS.finding_t3(TS.split_entries(_paths(loose))[2], policy)), {"T3"}
    )
    tally.check(
        "T3 admits a plan, a report and a census by pattern",
        _codes(
            TS.finding_t3(
                {"PLAN-x.md", "REPORT-y.md", "census-plan-record.jsonl", "README.md"}, policy
            )
        ),
        set(),
    )

    # T4. A directory under agent/ that is neither reserved nor a session slug.
    tally.check(
        "T4 clean", _codes(TS.finding_t4(TS.split_entries(clean)[3], policy, RESERVED)), set()
    )
    phantom = plant(CLEAN_LISTING, "agent/legacy/STATE.md", "agent/not-a-session-name/STATE.md")
    tally.check(
        "T4 planted",
        _codes(TS.finding_t4(TS.split_entries(_paths(phantom))[3], policy, RESERVED)),
        {"T4"},
    )
    tally.check(
        "T4 spares an 8-character session slug",
        _codes(TS.finding_t4({"abcd1234", "d778be9d"}, policy, RESERVED)),
        set(),
    )

    # T5. The derivation, in both directions.
    tally.check("T5 clean", _codes(TS.finding_t5(policy, RESERVED)), set())
    tally.check(
        "T5 fires when the hook knows a directory the policy does not",
        _codes(TS.finding_t5(policy, RESERVED | {"ledgers"})),
        {"T5"},
    )
    tally.check(
        "T5 fires when the policy knows one the hook does not",
        _codes(TS.finding_t5(policy, RESERVED - {"pr"})),
        {"T5"},
    )
    tally.check(
        "T5 names the missing half rather than only counting",
        [f.path for f in TS.finding_t5(policy, RESERVED - {"pr"})],
        ["pr"],
    )

    # T6. The bare relative repository path.
    tally.check(
        "T6 clean", TS.bare_relative_sites(CLEAN_SOURCE, "x.py", TOP_NAMES, CALLEES, FS_METHODS), []
    )
    relative = plant(CLEAN_SOURCE, 'paths.from_root("agent")', 'pathlib.Path("agent").glob("*")')
    tally.check(
        "T6 planted",
        [
            literal
            for _line, literal in TS.bare_relative_sites(
                relative, "x.py", TOP_NAMES, CALLEES, FS_METHODS
            )
        ],
        ["agent"],
    )
    tally.check(
        "T6 spares a dot, which names the caller's own directory on purpose",
        TS.bare_relative_sites(
            'import pathlib\npathlib.Path(".").is_dir()\n', "x.py", TOP_NAMES, CALLEES, FS_METHODS
        ),
        [],
    )
    tally.check(
        "T6 spares a name that is not a top-level directory here",
        TS.bare_relative_sites(
            'import pathlib\npathlib.Path("node_modules").is_dir()\n',
            "x.py",
            TOP_NAMES,
            CALLEES,
            FS_METHODS,
        ),
        [],
    )
    tally.check(
        "T6 reads a nested literal too",
        [
            literal
            for _line, literal in TS.bare_relative_sites(
                'import pathlib\npathlib.Path("agent/INDEX.md").read_text()\n',
                "x.py",
                TOP_NAMES,
                CALLEES,
                FS_METHODS,
            )
        ],
        ["agent/INDEX.md"],
    )
    tally.check(
        "T6 survives a file that does not parse",
        TS.bare_relative_sites("def (:\n", "x.py", TOP_NAMES, CALLEES, FS_METHODS),
        [],
    )

    # T7. The vacuity floor, and it must win over every other finding.
    tally.check(
        "T7 clean",
        _codes(TS.finding_t7(TS.split_entries(clean)[0], 14, len(TS.split_entries(clean)[1]))),
        set(),
    )
    tally.check(
        "T7 planted on a pathspec that yields one top-level directory",
        _codes(TS.finding_t7(TS.split_entries(clean)[0], 14, 1)),
        {"T7"},
    )
    tally.check(
        "T7 planted on a lost agent tree",
        _codes(TS.finding_t7({"CLAUDE.md"}, 1, 6)),
        {"T7"},
    )
    tally.check(
        "T7 short-circuits the rest",
        _codes(
            TS.findings(
                ["CLAUDE.md", "aa.jsonl"],
                policy=policy,
                reserved=RESERVED,
                bare_sites=[],
                baseline=None,
            )
        ),
        {"T7"},
    )

    # T8, and the baseline applied as a set.
    stray_paths = _paths(plant(CLEAN_LISTING, "biome.json\n", "biome.json\naa.jsonl\n"))
    tally.check(
        "a baselined stray is silent",
        _codes(
            TS.findings(
                stray_paths, policy=policy, reserved=RESERVED, bare_sites=[], baseline=["aa.jsonl"]
            )
        ),
        set(),
    )
    tally.check(
        "T8 planted: a baseline entry that no longer fires",
        _codes(
            TS.findings(
                clean, policy=policy, reserved=RESERVED, bare_sites=[], baseline=["aa.jsonl"]
            )
        ),
        {"T8"},
    )
    tally.check(
        "the seed set ignores the baseline",
        TS.live_entries(stray_paths, policy=policy, reserved=RESERVED, bare_sites=[]),
        ["aa.jsonl"],
    )

    # The shrink-only decision, shared rather than copied.
    tally.check(
        "COMPOSITION TRAP: a reseed that drains many and adds one still GROWS",
        shrink_only.baseline_additions(["a", "b", "c"], ["a", "new"]),
        ["new"],
    )
    tally.check(
        "a genuine shrink adds nothing",
        shrink_only.baseline_additions(["a", "b"], ["a"]),
        [],
    )
    tally.check(
        "a write that would grow is refused",
        shrink_only.write_verdict(baseline_exists=True, first_seed=False, additions=["new"]),
        "would-grow",
    )
    tally.check(
        "a missing baseline is refused unless declared a first seed",
        shrink_only.write_verdict(baseline_exists=False, first_seed=False, additions=[]),
        "missing-baseline",
    )
    tally.check(
        "a first seed is allowed",
        shrink_only.write_verdict(baseline_exists=False, first_seed=True, additions=[]),
        None,
    )

    return 0 if tally.report() else 1


# --------------------------------------------------------------------------- The tree-reading half.


def _reserved(root: pathlib.Path) -> set[str]:
    """`wl_store.AGENT_RESERVED_DIRS`, DERIVED rather than copied.

    A missing `.claude/` is CANNOT RUN rather than a verdict: without the hook's own set there is nothing to compare the policy against, and a gate that silently skipped its derivation would report a clean shape while the one thing it exists to check had not happened.
    """
    # `paths.hooks_stop_dir` rather than a join, for the reason check_plan_boxes.py states: it is the ONE place the `.claude/hooks/stop` literal lives, so the move planned for that program is a one-line change there. It is also the spelling `check:ci-python-gate-deps` recognises as a sys.path hop, which is what tells it `wl_store` is first-party rather than a package this job
    # forgot to install.
    hooks = paths.hooks_stop_dir(root)
    paths.on_sys_path(hooks)
    try:
        import wl_store  # noqa: PLC0415 -- the derivation is the point; see the docstring
    except ImportError as exc:
        raise CannotRunError(
            "cannot import wl_store from %s (%s), so AGENT_RESERVED_DIRS cannot be derived "
            "and T5 would silently not run" % (hooks, exc)
        ) from exc
    return set(wl_store.AGENT_RESERVED_DIRS)


def _gather(root: pathlib.Path):
    """ONE enumeration, the whole repository, tracked plus untracked-not-ignored.

    Narrowing the pathspec to `:(glob)*` and `agent` was the first shape and it was VACUOUS in one direction: git lists blobs, so a pathspec that admits only root files and the agent tree yields exactly one top-level directory name, leaving T2 with nothing it can fire on. The whole listing costs one subprocess and is what the bare-relative scan needs anyway.
    """
    everything, why = TS.enumerate_tree(root)
    if why:
        raise CannotRunError(why)
    policy = TS.load_policy(root)
    return everything, TS.scan_bare_relative(root, policy, everything), policy


def _report(found: list[TS.Finding]) -> int:
    print("✗ tree shape: %d finding(s)" % len(found), file=sys.stderr)
    for finding in found[:SHOWN]:
        print("  %s %s" % (finding.code, finding.message), file=sys.stderr)
    if len(found) > SHOWN:
        print("  ...and %d more" % (len(found) - SHOWN), file=sys.stderr)
    return 1


def run(root: pathlib.Path) -> int:
    tree, bare, policy = _gather(root)
    root_files, root_dirs, agent_files, agent_dirs = TS.split_entries(tree)
    # VACUITY BEFORE THE DERIVATION, and the order is load-bearing rather than tidy. A tree thin enough to fail the floor has no `.claude/hooks/stop` either, so deriving first turns every vacuity case into exit 77 -- a BLOCKED that hides the refusal the floor exists to make.
    vacuous = TS.finding_t7(root_files, len(agent_files) + len(agent_dirs), len(root_dirs))
    if vacuous:
        return _report(vacuous)
    baseline_path = root / TS.BASELINE_REL
    baseline = TS.read_baseline(baseline_path)
    found = TS.findings(
        tree, policy=policy, reserved=_reserved(root), bare_sites=bare, baseline=baseline
    )
    if found:
        return _report(found)
    print(
        "✓ tree shape: %d root file(s) and %d root director(ies), %d file(s) and %d "
        "director(ies) under agent/, %d module(s) scanned for bare relative paths, "
        "%d baselined"
        % (
            len(root_files),
            len(root_dirs),
            len(agent_files),
            len(agent_dirs),
            len(policy["bare_relative_scan"]["dirs"]),
            len(baseline or []),
        )
    )
    print(
        "  Blind spot: names and locations only, in two trees. Nothing here reads a "
        "file's CONTENT, and a gitignored path is output rather than a stray."
    )
    return 0


def write_baseline(root: pathlib.Path, *, first_seed: bool) -> int:
    tree, bare, policy = _gather(root)
    current = sorted(
        set(TS.live_entries(tree, policy=policy, reserved=_reserved(root), bare_sites=bare))
    )
    path = root / TS.BASELINE_REL
    previous = TS.read_baseline(path)
    exists = previous is not None
    verdict = shrink_only.write_verdict(
        baseline_exists=exists,
        first_seed=first_seed,
        additions=shrink_only.baseline_additions(previous or [], current) if exists else [],
    )
    if verdict:
        print(
            TS.render_refusal(
                verdict,
                shrink_only.baseline_additions(previous or [], current) if exists else [],
                len(previous or []),
                len(current),
            ),
            file=sys.stderr,
        )
        return 1
    doc = {
        "note": (
            "SHRINK-ONLY, AND GENERATED -- do not hand-edit. Every entry is a path at the "
            "repository root or under agent/ that no class in .ci/policy/tree-shape.json "
            "permits, frozen on the day check:ci-tree-shape landed. This list may only "
            "lose members. A NEW path here is refused by "
            ".ci/scripts/quality/check_tree_shape.py even when the total shrinks, because "
            "composition is the claim and a total is not. The goal state is that this "
            "file holds an empty list and then does not exist. Drain it with "
            "`.ci/scripts/quality/check_tree_shape.py --write-baseline` in the same "
            "commit that removes a stray, and never to make a red go away."
        ),
        "strays": current,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print("✓ wrote %s: %d entr(ies)" % (TS.BASELINE_REL, len(current)))
    return 0


def main(argv: list[str]) -> int:
    try:
        if "--selftest" in argv:
            return selftest()

        print("tree shape: controls first, then the verdict")
        if selftest() != 0:
            print(
                "✗ instrument control failed; every verdict below would be meaningless",
                file=sys.stderr,
            )
            return 2

        root = TS.repo_root()
        if not gitx.is_work_tree(root):
            raise CannotRunError("%s is not a git work tree, so nothing can be enumerated" % root)
        if "--write-baseline" in argv:
            return write_baseline(root, first_seed="--first-seed" in argv)
        return run(root)
    except CannotRunError as exc:
        print("⚠ CANNOT RUN (exit 77, which is not a verdict): %s" % exc, file=sys.stderr)
        return 77


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
