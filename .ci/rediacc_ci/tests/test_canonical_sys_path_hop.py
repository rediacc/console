"""This repo has ONE canonical way onto sys.path, and this is the whole-tree control.

WHAT PRE-A1 ESTABLISHED, AND WHY IT NEEDS A GUARD RATHER THAN A MEASUREMENT.
Before that box, eight files under `.ci/scripts/quality` carried a hand-written `sys.path.insert` and `.ci/rediacc_ci/quality/hook_exec_baseline.py` carried a ninth. Ten inserts across nine files, in four different spellings, all of them saying "put a directory on the path". They are now:

    import _cipath                              the `.ci` hop, once, in a shim
    paths.on_sys_path(paths.hooks_stop_dir(R))  the `.claude/hooks/stop` hop
    paths.on_sys_path(<dir>)                    anything else

That box's acceptance was a BEFORE/AFTER measurement of the file set, which proves the sweep happened and proves nothing at all about tomorrow. The next gate written in this tree will be copied from a neighbour, and the neighbour it is copied from decides which spelling spreads. So the invariant is pinned here instead of being left as a paragraph in a plan.

WHY THE CORPUS IS NOW THE WHOLE TREE, AND WHAT THAT COST. Until 2026-09-09 this control governed exactly two directories, `.ci/scripts/quality` and `.ci/rediacc_ci/quality`. Those two hold 2 of the 39 hops that actually exist in this repository, and the second directory holds none at all. A control scoped to the ground its own workstream had already cleared is a control that can
only report success: widening it is W1P4, and the number it was widened against is measured below rather than quoted, because every count in that plan that was quoted rather than re-measured has been wrong.

    git ls-files -z --cached --others --exclude-standard -- '*.py'
        | xargs -0 <ast walk for sys.path.insert / append / extend>
    -> 655 .py in the corpus, 39 hops in 36 files   (2026-09-09, working tree)
    -> 567 of those 655 are tracked; the 88 untracked ones carry 3 of the 39
    -> 45 files at HEAD 73bd8f7ec by the same walk, so the tree has already
       shrunk and this control is what makes that shrink permanent

That plan box said "68 files and rising". No reading of this tree produces 68. On the same 655-file corpus: 36 files / 39 hops by the syntax walk, 41 files / 49 hops by a line-anchored grep that also counts docstring examples and fixture strings, and 45 files at HEAD by the syntax walk. The number was quoted rather than measured.

WHY A BASELINE AND NOT THIRTY-THREE MORE EXEMPTIONS. 33 of those 36 files are outside the box that widened this control, and an exemption means "this is correct forever". Freezing them as DEBT says the opposite: the total may not grow, a baselined hop that gets fixed must be DRAINED rather than left as a permanent hole, and both halves are asserted below. EXEMPT is reserved for the
three that are structurally required, each with a reason this file proves is still live.

WHAT THE `_cipath` TRICK CANNOT DO, MEASURED RATHER THAN ASSUMED, because the next box to read this file will otherwise try it. `import _cipath` resolves only because a PATH invocation puts the script's own directory on `sys.path[0]`. Five of the baselined hops sit INSIDE a package and still run as scripts: `check_pytest.py`, the three under `rediacc_ci/setup/`, and
`rediacc_hooks/dispatch.py` (`battery.py` made six until it was deleted with the bash gate-test battery, 2026-10-09). THREE of those five are also imported by their package name -- `setup/tools.py` and `setup/port_parity.py` by the suite, `dispatch.py` by two hook suites -- and a sibling shim is impossible for them: driven on a throwaway package, running
`pkg/sub/dualuse.py` as a script prints `__package__=None` and loads, while
`from pkg.sub import dualuse` dies at `import _pkgpath`. The remaining two, `check_pytest.py` and `setup/shadow_driver.py`, COULD take a shim and would gain nothing, because they sit in different directories and the shim is itself a file containing the hop: two hops would become two shims. So none of the five is sitting there because nobody swept it.

WHY THE BASELINE IS KEYED ON A HASH OF THE HOP'S SOURCE AND NOT ON ITS LINE.
A line number churns when a paragraph moves above it, and a baseline that churns gets regenerated wholesale, which silently re-absorbs findings nobody looked at. The hash survives a MOVE and deliberately does NOT survive a REWRITE: rewriting a hop is exactly the moment a human should look at it again. When that happens the run reports one gone and one new IN THE SAME FILE --
hand-edit that single line rather than regenerating the table, which would absorb any other writer's fresh findings along with yours.

WHY AN AST WALK AND NOT A GREP. This tree's Python is heavily commented ABOUT the hops it no longer has: `check_python_gate_deps.py` mentions `sys.path.insert(` seven times in comments while writing it zero times, and `_cipath.py`'s docstring quotes the line it is replacing. A grep-based version of this control reported five false positives on its first run and would have been
"fixed" by deleting the explanations, which are the most valuable text in those files. Measured on the widened corpus, grep also reports two files the syntax tree correctly ignores -- `packages/locales/site_locales.py`, whose hop is a usage example in the module docstring, and `.ci/rediacc_ci/quality/dead_python.py`, whose hop is a fixture string. The syntax tree cannot see either.

THE FLOOR IS THE KNOWN-POSITIVE SET, NOT A TYPED NUMBER. A sweep that empties the finding set by breaking the scanner looks exactly like a sweep that fixed everything, and the previous version of this file guarded that with `assert len(files) > 50` -- a hand-typed constant, which goes red at the moment the migration it guards succeeds and passes against nothing if the corpus moves.
What replaces it is derived entirely from the corpus: every path this file already knows carries a hop must still be FOUND carrying one, so a scanner that sees nothing reports all 39 vanished entries rather than a clean tree.
"""

import ast
import hashlib
import os
import pathlib
import re
import subprocess
import sys

import pytest

from rediacc_ci import gitx, paths
from rediacc_ci.tests.twin_names import usage_command

# NO XDIST GROUP SINCE 2026-10-05 (agent/plans/PLAN-prepush-full-cpu.md PF15). The scan lists the working tree (`git ls-files --cached --others`), and on 2026-10-01 a `-n 16` run failed here on test_gate_shrink_only_composition.py's `quality/zz_composition_string_probe_port_*.py`, listed and gone before it was read, so this reader joined the real-tree group. Every such plant now lives in a scratch copy, so nothing in the suite plants into the listed tree, and the session tripwire (`test_tree_tripwire.py`) fails a run in which a test changes one.

#: relpath -> why this hop is correct forever. Each reason is checked for liveness
#: below, and each is PRINTED on every run: a quiet exemption is how a control stops
#: meaning what its name says.
EXEMPT: dict[str, str] = {
    ".ci/rediacc_ci/paths.py": (
        "BLOCKER: this IS `on_sys_path`, the canonical resolver. The function whose "
        "whole purpose is to put a directory on sys.path has to contain the one "
        "insert that does it, and it is the insert every other call site was "
        "replaced BY."
    ),
    ".ci/scripts/quality/_cipath.py": (
        "BLOCKER: this IS the canonical `.ci` hop. It is the one file that cannot "
        "reach `rediacc_ci.paths`, because putting `.ci` on sys.path is the thing "
        "it exists to do; see its own docstring for why the side-effect import "
        "form is the only spelling ruff accepts before the imports that follow it."
    ),
    ".ci/scripts/docker/_cipath.py": (
        "BLOCKER: the SECOND canonical `.ci` hop, exempt for the identical reason as "
        "the quality copy above and not a duplicate of its debt. A path invocation "
        "puts THE SCRIPT'S OWN DIRECTORY on sys.path[0], so an entry point in "
        ".ci/scripts/docker/ can only ever resolve `import _cipath` to a file beside "
        "it; importing the quality copy instead would require `.ci` to be on the path "
        "already, which is precisely what has not happened yet. The circularity is "
        "the reason a second copy exists, and the file's own docstring measures it. "
        "The exemption dies the day `.ci/scripts/docker/` stops holding path-invoked "
        "entry points."
    ),
    ".ci/scripts/security/_cipath.py": (
        "BLOCKER: the canonical `.ci` hop for the path-invoked entry points in "
        ".ci/scripts/security/, exempt for the reason the docker copy above gives: "
        "`import _cipath` resolves only to a file beside the script, so each "
        "directory of path-invoked entry points needs its own copy. The exemption "
        "dies the day `.ci/scripts/security/` stops holding path-invoked entry points."
    ),
    ".ci/scripts/ci/profiler/_cipath.py": (
        "BLOCKER: the canonical `.ci` hop for the profiler's path-invoked sampler "
        "shims (b934e8777), exempt for the reason the docker copy above gives: a "
        "path invocation puts only the script's own directory on sys.path[0]. Three "
        "directories below `.ci` rather than two; the file's `raise` checks the depth. "
        "The exemption dies the day `.ci/scripts/ci/profiler/` stops holding "
        "path-invoked entry points."
    ),
    ".ci/scripts/quality/check_fetch_retry.py": (
        "BLOCKER: ruff's E402 EXEMPTS a `sys.path` mutation that precedes a "
        "module-level import and exempts nothing else. Measured against ruff "
        "0.16.1, the version check_python_lint.py pins: a bare insert then "
        "`import json` is clean, the resolver call then `import json` is E402, and "
        "so is any other statement. This file imports a SIBLING gate at module "
        "level and the hop has to come first, so the canonical form would cost a "
        "per-line waiver where the bare form costs nothing. The exemption dies the "
        "day that import moves inside a function."
    ),
    ".claude/rediacc_hooks/syspath.py": (
        "BLOCKER: this IS the canonical hop for code under `.claude`, the counterpart "
        "of `paths.on_sys_path` for files that cannot reach `rediacc_ci`: a guard or "
        "hook suite importing `rediacc_ci.paths` would first need `.ci` on sys.path, "
        "which is the hop being replaced. Guards import it as `rediacc_hooks.syspath`; "
        "scripts outside the package (Stop-hook suites, context hooks, standalone "
        "guard tests) load it BY PATH, which is why it is stdlib-only. The function "
        "whose whole purpose is the insert has to contain the one insert that does it."
    ),
    ".claude/rediacc_hooks/guards/block_prose_style_edit.py": (
        "BLOCKER: importing `rediacc_ci.quality.prose_style` needs `.ci` on sys.path, "
        "and neither `_cipath.py` nor `paths.on_sys_path` can supply it -- both live "
        "inside `.ci`, so reaching either one already needs the thing the hop exists "
        "to do. Moving the hop into `rediacc_hooks/dispatch.py`, the package's usual "
        "single entry point, was considered and rejected: dispatch.py runs every "
        "guard in one process, so a permanent `.ci` insert there would put "
        "`rediacc_ci` and `_cipath` on every LATER guard's import path for the "
        "whole chain, not just this one's. This guard's insert is SCOPED and "
        "removed in a `finally` (see its own docstring), which is the narrower, "
        "self-cleaning shape and the reason it stays local rather than moving up."
    ),
    ".claude/rediacc_hooks/guards/block_prose_style_commit.py": (
        "BLOCKER: the same circularity and the same rejected alternative as "
        "`block_prose_style_edit.py`'s entry above; see that reason in full. Both "
        "guards import the same engine the same scoped way, so the argument is "
        "identical rather than duplicated by accident."
    ),
}

#: relpath -> the hop fingerprints frozen there. DEBT, not permission. The total may
#: not grow and an entry that gets fixed must be deleted from this table, which is
#: what keeps the set shrinking. Do not add a new finding here; fix it.
#:
#: A fingerprint is the first 12 hex of sha1 over `ast.unparse` of the call, so two
#: byte-identical hops in two files share a fingerprint and that is fine: the key is
#: the (path, fingerprint) pair.
BASELINE: dict[str, tuple[str, ...]] = {
    ".ci/rediacc_ci/check_pytest.py": ("068d93dec96d",),
    ".ci/rediacc_ci/dev/shadow_driver.py": ("c1e552fa19e9",),  # FRESH
    ".ci/rediacc_ci/docker/shadow_driver.py": ("c1e552fa19e9",),  # FRESH
    ".ci/rediacc_ci/setup/port_parity.py": ("c1e552fa19e9",),
    ".ci/rediacc_ci/setup/shadow_driver.py": ("c1e552fa19e9",),
    ".ci/rediacc_ci/setup/tools.py": ("c1e552fa19e9",),
    # -- The three `FRESH` lines below ARRIVED AFTER PRE-A1. Not a fix this control was allowed to make: all three were UNCOMMITTED work belonging to a writer running concurrently with it, and editing another writer's live files is how a tree with no safety net loses work. Sorted in place rather than grouped, so the table stays regenerable and a reader diffing it sees a stable
    # order.
    ".ci/rediacc_ci/tests/test_wl_proc.py": ("a885259827b2",),  # FRESH
    ".ci/rediacc_ci/tests/test_worklist_state_stdin.py": ("a885259827b2",),  # FRESH
    ".ci/scripts/ci/ci-trace.py": ("022cec69eb9d",),
    ".claude/hooks/context/band-notice.py": ("0f4656206187",),
    ".claude/hooks/context/epoch-reset.py": ("0f4656206187",),
    ".claude/hooks/context/onboard.py": ("0f4656206187",),
    ".claude/hooks/context/precompact-floor.py": ("0f4656206187",),
    ".claude/hooks/context/test-context-bands.py": ("0f4656206187",),
    ".claude/hooks/post-bash/cancel_old_ci.py": ("c1e552fa19e9",),  # FRESH
    ".claude/hooks/post-bash/refresh_pr_body.py": ("c1e552fa19e9",),  # FRESH
    ".claude/hooks/stop/calibrate-judge-rules.py": ("cac5257d3f9d",),
    ".claude/hooks/stop/test-adhoc-watch.py": ("cac5257d3f9d",),
    ".claude/hooks/stop/test-always-tier.py": ("5163c1cfecb6",),
    ".claude/hooks/stop/test-completion-evidence.py": ("a30413cc683d",),
    ".claude/hooks/stop/test-judge-schema.py": ("cac5257d3f9d",),
    ".claude/hooks/stop/test-plan-status-parse.py": ("cac5257d3f9d",),
    ".claude/hooks/stop/test-planindex.py": ("cac5257d3f9d",),
    ".claude/hooks/stop/test-planrec.py": ("2af853e16b8e", "2af853e16b8e"),
    ".claude/hooks/stop/test-reggate-ledger.py": ("cac5257d3f9d",),
    ".claude/hooks/stop/test-teammate-idle.py": ("cac5257d3f9d",),
    ".claude/hooks/stop/wl_planindex.py": ("cac5257d3f9d",),
    ".claude/hooks/stop/wl_proc.py": ("dbee896ecaff",),  # FRESH
    ".claude/hooks/stop/wl_profile.py": ("0f4656206187",),
    ".claude/hooks/stop/worklist.py": ("16811be88177",),
    ".claude/hooks/why-on-edit.py": ("8b7733d72e0c", "97bcfa3db44a"),
    ".claude/rediacc_hooks/dispatch.py": ("068d93dec96d",),
}

#: The subset of BASELINE that is NOT historical debt: hops added AFTER PRE-A1
#: declared the canonical form, caught on the day this control's corpus widened to
#: include untracked files. They are printed separately on every run because a fresh
#: violation folded into 33 lines of old debt is a violation nobody will ever drain,
#: and because two of the three are a hand-rolled copy of `on_sys_path` itself --
#: `if root not in sys.path: sys.path.insert(0, root)` in a file that already imports
#: `paths`. DRAIN THESE FIRST.
FRESH: frozenset[str] = frozenset(
    {
        ".ci/rediacc_ci/dev/shadow_driver.py",
        ".ci/rediacc_ci/docker/shadow_driver.py",
        ".ci/rediacc_ci/tests/test_wl_proc.py",
        ".ci/rediacc_ci/tests/test_worklist_state_stdin.py",
        ".claude/hooks/post-bash/cancel_old_ci.py",
        ".claude/hooks/post-bash/refresh_pr_body.py",
        ".claude/hooks/stop/wl_proc.py",
    }
)

#: What the author is told to write instead, in every failure message. One string so
#: the advice cannot drift between the two assertions that give it.
ADVICE = (
    "Use the canonical form instead. `import _cipath` for the `.ci` hop, "
    "`paths.on_sys_path(paths.hooks_stop_dir(ROOT))` for the Stop hook's directory, "
    "`paths.on_sys_path(<dir>)` for anything else -- it is idempotent, where a bare "
    "insert run twice leaves two copies on the path."
)


def fingerprint(hop_source: str) -> str:
    """The stable id of a hop: 12 hex of sha1 over its unparsed source.

    Exported rather than inlined so the controls at the bottom exercise the same
    function the scan uses, instead of a second copy that could agree with nothing.
    """
    return hashlib.sha1(hop_source.encode("utf-8")).hexdigest()[:12]


def hops(source: str) -> list[tuple[int, str]]:
    """(line, unparsed source) for every `sys.path.insert/append/extend` CALL.

    A comment, a docstring and a string literal cannot match, because none of them is a Call node. That is the whole reason this is a syntax walk.
    """
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or fn.attr not in ("insert", "append", "extend"):
            continue
        target = fn.value
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "path"
            and isinstance(target.value, ast.Name)
            and target.value.id == "sys"
        ):
            out.append((node.lineno, ast.unparse(node)))
    return sorted(out)


def _corpus() -> list[str]:
    """Every `.py` path in this repo that git can see, tracked or not.

    GIT AND NOT A GLOB, for the reason `gitx.ls_files` exists: a glob walks node_modules, build output and other sessions' scratch files, and its answer moves for reasons that have nothing to do with the invariant. Submodules under `private/` are deliberately not recursed -- they have their own CI and this control cannot fix a hop it cannot edit.

    `untracked=True`, AND THAT IS THE WHOLE DIFFERENCE BETWEEN A CONTROL AND A
    DECORATION. Written without it first, and the planted violation this control is supposed to catch did not fire: a NEW file is untracked by definition, and `git ls-files` without `--others` cannot see one. The plant was in this very file, which was itself untracked at the time, so the scan read 567 paths and the 568th was the one carrying the plant. Turning the flag on moved the
    corpus
    from 567 to 655 and surfaced three real hops that had arrived after PRE-A1 in
    files no committed enumeration contains. `gitx.ls_files`'s own docstring records the identical defect in `check-python-lint.sh:88`, which "shipped green over an untracked file for an unknown period". `--exclude-standard` still keeps gitignored scratch out, so `.ci/cache` cannot red this.

    `existing=True` DROPS a path git lists but disk does not have, and on its own
    that would be exactly the "unknown folded into fine" this file argues against. It is safe only because the floor below covers it: in a partial checkout the dropped paths are the ones whose hops are frozen, so they come back as vanished entries rather than as silence.
    """
    return gitx.ls_files("*.py", root=paths.repo_root(), untracked=True, existing=True)


def scan(root: pathlib.Path, files: list[str]) -> dict[str, list[tuple[int, str]]]:
    """relpath -> its hops, for the files that HAVE one. Unreadable input raises.

    Raises rather than skipping, because a file that cannot be parsed is UNCHECKED and an unchecked file folded into "fine" is the exact vacuity this control is
    for.

    THE SYNTAX ERROR IS CAUGHT AND RE-RAISED WITH A SENTENCE, not left to surface as a bare traceback from `ast.parse`. This corpus includes UNTRACKED files, so it reads whatever another session has half-written at that moment: on 2026-09-09 `.ci/rediacc_ci/battery.py:83` was momentarily unparsable and the unhelpful version of this message would have read as flake in a file this
    control never touched.
    """
    found: dict[str, list[tuple[int, str]]] = {}
    for rel in files:
        path = root / rel
        if not path.is_file():
            msg = (
                f"{rel} is listed by git but is not on disk, so this control cannot "
                "read it. A partial checkout means the scan is not seeing the tree "
                "and its green would mean nothing."
            )
            raise AssertionError(msg)
        try:
            got = hops(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            msg = (
                f"{rel}:{exc.lineno} does not parse ({exc.msg}), so this control could "
                "not read it and cannot claim the tree is clean. Fix that file. If it "
                "is another session's half-written work, wait for it rather than "
                "narrowing this scan."
            )
            raise AssertionError(msg) from exc
        if got:
            found[rel] = got
    return found


def vanished(found: dict[str, list[tuple[int, str]]]) -> list[str]:
    """The FLOOR. Known-positive entries the scan failed to find, by name.

    Derived from the corpus, never typed: EXEMPT and BASELINE are together the set of hops this repo is known to contain, so a scanner that has stopped seeing the tree reports all of them here rather than reporting a clean tree.
    """
    gone: list[str] = [
        f"{rel} is EXEMPT but the scan found no hop in it"
        for rel in sorted(EXEMPT)
        if not found.get(rel)
    ]
    for rel, frozen in sorted(BASELINE.items()):
        have = sorted(fingerprint(text) for _, text in found.get(rel, []))
        for fp in sorted(frozen):
            if fp in have:
                have.remove(fp)
            else:
                gone.append(f"{rel} no longer carries the baselined hop {fp}")
    return gone


def _shape(files: list[str], found: dict[str, list[tuple[int, str]]]) -> str:
    total = sum(len(v) for v in found.values())
    return (
        f"{len(files)} .py scanned (tracked + untracked), {total} hop(s) in "
        f"{len(found)} file(s), "
        f"{len(EXEMPT)} exempt, {sum(len(v) for v in BASELINE.values())} baselined"
    )


def test_the_corpus_is_real_and_fully_read() -> None:
    """Zero inputs is a FAILURE, and so is an input this control could not read."""
    files = _corpus()
    assert files, (
        "git ls-files returned no Python files. This control is scanning nothing and "
        "its green would mean nothing; check that it is running inside the work tree."
    )
    found = scan(paths.repo_root(), files)
    print("SHAPE  " + _shape(files, found))
    for rel in sorted(FRESH):
        # PRINTED, ALWAYS, and separately from the historical debt it would otherwise disappear into.
        print(f"FRESH DEBT, DRAIN FIRST  {rel}  (arrived after PRE-A1)")


def test_the_floor_holds_every_known_hop_is_still_found() -> None:
    """The anti-collapse floor, derived from the corpus rather than typed."""
    files = _corpus()
    gone = vanished(scan(paths.repo_root(), files))
    assert gone == [], (
        "\n".join(gone)
        + "\n\nEither these hops were genuinely fixed -- in which case DRAIN them, by "
        "deleting each line from BASELINE (or from EXEMPT, whose reason has then "
        "expired) -- or the scan has stopped seeing the tree, in which case its green "
        f"would have meant nothing. {_shape(files, scan(paths.repo_root(), files))}"
    )


def grown(found: dict[str, list[tuple[int, str]]]) -> list[str]:
    """Hops that are in the tree and in neither table: the GROWTH direction, by name."""
    findings: list[str] = []
    for rel, got in sorted(found.items()):
        if rel in EXEMPT:
            continue
        budget = list(BASELINE.get(rel, ()))
        for line, text in got:
            fp = fingerprint(text)
            if fp in budget:
                budget.remove(fp)
                continue
            findings.append(f"{rel}:{line}  {text}   [{fp}]")
    return findings


def test_no_hand_written_hop_outside_the_exemptions_and_the_baseline() -> None:
    """The invariant: the set may not GROW. New findings are named with their line."""
    files = _corpus()
    found = scan(paths.repo_root(), files)
    findings = grown(found)
    assert findings == [], (
        "\n".join(findings)
        + "\n\n"
        + ADVICE
        + " Do not add it to the baseline. If the line is one of this file's own "
        "frozen hops and only its TEXT changed, the fingerprint has re-keyed: "
        "hand-edit that single entry rather than regenerating the table, which would "
        f"absorb any other writer's fresh findings. {_shape(files, found)}"
    )


def test_the_exemptions_are_all_live() -> None:
    """An exemption whose reason has expired is a FAILURE, so the set can only shrink."""
    found = scan(paths.repo_root(), _corpus())
    stale: list[str] = []
    for rel, reason in sorted(EXEMPT.items()):
        # PRINTED, ALWAYS. The debt is visible in the run and not only in the source.
        print(f"EXEMPT BY NAME  {rel}\n      {reason}")
        if not found.get(rel):
            stale.append(
                f"{rel} no longer writes a hand-written hop, so its exemption is dead. "
                "Delete the entry rather than leaving a permanent hole in the scan."
            )
    assert stale == [], "\n".join(stale)


def test_the_baseline_names_only_files_that_exist() -> None:
    """A baselined path that is gone is UNCHECKED debt, not drained debt."""
    tracked = set(_corpus())
    orphans = sorted(rel for rel in BASELINE if rel not in tracked)
    assert orphans == [], (
        "\n".join(orphans)
        + "\n\nThese are frozen in BASELINE but are not tracked Python files any more. "
        "If the file was deleted, delete its line here too; if it MOVED, move the line, "
        "because a baseline that silently forgets an entry is how debt re-enters."
    )


def test_every_fresh_entry_is_really_baselined() -> None:
    """FRESH is a VIEW on BASELINE. A name in one and not the other is a silent hole."""
    orphans = sorted(FRESH - set(BASELINE))
    assert orphans == [], (
        "\n".join(orphans)
        + "\n\nThese are printed every run as fresh debt but are not in BASELINE, so "
        "nothing is actually holding them. Either the path is misspelt or the entry "
        "was drained from BASELINE and should have been dropped from FRESH too."
    )


def test_the_detector_fires_and_does_not_over_fire() -> None:
    """Both directions, because a detector with only a positive control flags everything."""
    plant = "import sys\n\nsys.path.insert(0, '/x')\nprint(sys)\n"
    assert [line for line, _ in hops(plant)] == [3], "a real hop was not detected"
    assert hops("import sys\nsys.path.append('/x')\n"), "append is a hop too"
    assert hops("import sys\nsys.path.extend(['/x'])\n"), "extend is a hop too"

    canonical = (
        "import _cipath\n"
        "from rediacc_ci import paths\n\n"
        "paths.on_sys_path(paths.hooks_stop_dir())\n"
    )
    assert hops(canonical) == [], "the canonical form was reported as a hand-written hop"

    prose = (
        '"""A docstring that says sys.path.insert(0, str(CI_DIR)) and explains it."""\n'
        "# and a comment that also says sys.path.insert(0, HOOK_DIR)\n"
        "PROBE = \"import sys; sys.path.insert(0, '.')\"\n"
    )
    assert hops(prose) == [], (
        "a comment, a docstring or a string literal was read as code -- this is the "
        "false-positive class that would be 'fixed' by deleting the explanations"
    )

    other = "class T:\n    path = []\nT.path.insert(0, 'x')\nimport os\nos.path.insert\n"
    assert hops(other) == [], "an insert on something that is not sys.path was reported"


def test_the_floor_fires_when_the_corpus_collapses() -> None:
    """The control on the control: a scanner that sees NOTHING must go red, by name."""
    gone = vanished({})
    assert len(gone) == len(EXEMPT) + sum(len(v) for v in BASELINE.values()), (
        "an empty scan did not report every known hop as vanished, so the floor "
        f"would not have caught a collapsed corpus: {gone}"
    )
    assert any(".claude/hooks/stop/worklist.py" in g for g in gone), (
        "the floor's report does not name the entries it lost, which is what makes it "
        "readable as a collapse rather than as a clean tree"
    )
    # And the mirror: the real corpus must NOT report a collapse, or the two directions of this control would both be satisfied by a permanently red floor.
    assert vanished(scan(paths.repo_root(), _corpus())) == []


def test_the_growth_check_fires_on_a_plant_and_not_on_the_baseline() -> None:
    """Both directions of the ratchet, exercised without editing the tree."""
    baselined = ".ci/rediacc_ci/check_pytest.py"
    real = "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))"
    assert fingerprint(real) in BASELINE[baselined], (
        "the fingerprint function no longer agrees with the frozen table, so every "
        "baselined entry would read as both vanished and brand new"
    )
    # A baselined hop, unchanged: silence.
    assert grown({baselined: [(92, real)]}) == []
    # A SECOND hop in the same file, beyond the frozen budget: reported.
    plant = "sys.path.insert(0, '/planted/by/the/control')"
    assert fingerprint(plant) not in BASELINE[baselined], "the plant collides with real debt"
    two = grown({baselined: [(92, real), (93, plant)]})
    assert len(two) == 1, two
    assert "93" in two[0], two
    assert "/planted/by/the/control" in two[0], two
    # A hop in a file neither table knows: reported.
    fresh = grown({".ci/rediacc_ci/nothing_knows_this.py": [(1, plant)]})
    assert len(fresh) == 1, fresh
    assert "nothing_knows_this" in fresh[0], fresh
    # An EXEMPT file is excused, which is the direction that must NOT fire.
    assert grown({".ci/scripts/quality/_cipath.py": [(72, plant)]}) == []


# --------------------------------------------------------------------------- The printed `python3 -m` line (worklist #175470e9).
#
# `PYTHONPATH=.ci` IS THE HOP FOR A COMMAND A READER TYPES. A module's usage line, `--help` prog, or "run X first" hint is copied from the repository root, where `rediacc_ci` is not importable: `python3 -m rediacc_ci.deploy.clone_d1` there dies with `No module named 'rediacc_ci'` (review finding 08928e86.2, measured). Every printed command therefore spells the hop, `PYTHONPATH=.ci python3 -m ...`.
#
# THE CORPUS is every non-docstring string constant under `.ci/rediacc_ci` (tests excluded: a test builds its own command lines), plus the docstring of every module whose code reads `__doc__`, because that docstring is printed as help (`release_state_validator`, `silent_failure_patterns`, `linode_cluster_validation`, ...). A docstring nothing prints is prose about the module and is not judged.

PRINTED_ROOT = ".ci/rediacc_ci"
# EVERY INTERPRETER SPELLING, not only `python3` (review findings f6733156.1 and f6733156.3): `python`, `python3`, `python3.N`, each optionally behind a path (`/usr/bin/python3`, `.venv/bin/python`), and the package itself (`-m rediacc_ci`) as well as a dotted module. Each fails the same way from the repository root.
INTERPRETER = r"(?:[\w.~/-]*/)?python(?:3(?:\.\d+)?)?"
# `\b` CLOSES THE MODULE NAME (review finding 9edcb111.3): without it `rediacc_cix` and `rediacc_ci_old` read as the package followed by junk.
BARE_M = re.compile(
    r"(?<![\w./~-])(?<!PYTHONPATH=\.ci )%s -m (rediacc_ci(?:\.\w+)*)\b" % INTERPRETER
)
RUNNABLE_M = re.compile(
    r"((?:[A-Z_]+=\S+ )*)PYTHONPATH=\.ci (%s) -m (rediacc_ci(?:\.\w+)*)\b" % INTERPRETER
)

#: (module path, a fragment of the string constant) -> (how many bare commands the strings carrying that fragment hold, why they are not commands printed for a reader to run). The key is (module, fragment); the VALUE carries the declared count beside the reason (review finding f6733156.2, the structure stated as built per 9edcb111.2): a fragment alone exempted every string in the module that carried it, so a new bare line added inside one of those strings passed in silence. Each key's count is summed over every string carrying its fragment, and a count that moves either way is red.
NOT_A_PRINTED_COMMAND: dict[tuple[str, str], tuple[int, str]] = {
    (".ci/rediacc_ci/ci/gate_ledger.py", "backfill --export <dir>"): (
        1,
        "the manifest's `generated_by` record of what wrote the export, data a reader parses, not a line printed to run",
    ),
    (".ci/rediacc_ci/proxies/ensure_nfpm.py", 'PATH="$(python3 -m rediacc_ci.build.ensure_nfpm)'): (
        1,
        "quotes the callers' own shell line, which runs where the workflow already exports PYTHONPATH",
    ),
    (
        ".ci/rediacc_ci/quality/toolchain_pins.py",
        "via `python3 -m rediacc_ci.core.toolchain pairs`",
    ): (
        1,
        "names the workflow line the gate searches for, which must match the workflow text as written",
    ),
    (".ci/rediacc_ci/quality/toolchain_pins.py", 'report >> "$GITHUB_ENV"'): (
        1,
        "a selftest fixture fed to the gate's own regex",
    ),
    (".ci/rediacc_ci/quality/rdc_native.py", "exec python3 -m rediacc_ci.native"): (
        2,
        "the generated `rdc` shim's body, a selftest fixture compared byte for byte",
    ),
    (".ci/rediacc_ci/quality/dead_python.py", "rediacc_ci.quality.orphan_mod"): (
        0,
        "a selftest fixture naming a module that exists only in the gate's scratch tree (already hop-spelled; kept out of the runnable cases)",
    ),
    (".ci/rediacc_ci/quality/dead_python.py", "rediacc_ci.testrun.orphan_run"): (
        0,
        "a selftest fixture naming a module that exists only in the gate's scratch tree (already hop-spelled; kept out of the runnable cases)",
    ),
}


def _exemptions(rel: str, text: str, exemptions: dict) -> list[tuple[str, str]]:
    """EVERY exemption key whose fragment this string carries (review finding 9edcb111.1): a string holding two fragments counts toward both keys, so neither reads as stale and both declared counts are checked against it."""
    return [key for key in exemptions if key[0] == rel and key[1] in text]


def _docstring_nodes(tree: ast.AST) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
        ):
            out.add(id(body[0].value))
    return out


def printed_texts(root: pathlib.Path) -> list[tuple[str, int, str]]:
    """(module path, line, text) for every string this corpus counts as printed (see above)."""
    out = []
    for path in sorted((root / PRINTED_ROOT).rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in rel:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = _docstring_nodes(tree)
        prints_doc = any(isinstance(n, ast.Name) and n.id == "__doc__" for n in ast.walk(tree))
        module_doc = (
            tree.body[0].value if tree.body and isinstance(tree.body[0], ast.Expr) else None
        )
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in docs and not (prints_doc and node is module_doc):
                continue
            out.append((rel, node.lineno, node.value))
    return out


def bare_commands(texts: list[tuple[str, int, str]], exemptions: dict | None = None) -> list[str]:
    """`path:line: <interpreter> -m <module>` for every printed text spelling the command without the hop, plus one line for every exemption whose bare count is not the declared one (a stale exemption included: it counts zero strings)."""
    exemptions = NOT_A_PRINTED_COMMAND if exemptions is None else exemptions
    bad = []
    counted = dict.fromkeys(exemptions, 0)
    seen = dict.fromkeys(exemptions, False)
    for rel, line, text in texts:
        keys = _exemptions(rel, text, exemptions)
        found = ["%s:%d: %s" % (rel, line, m.group(0)) for m in BARE_M.finditer(text)]
        if not keys:
            bad += found
        for key in keys:
            seen[key] = True
            counted[key] += len(found)
    for key, (want, _why) in exemptions.items():
        if not seen[key]:
            bad.append("%s: exemption %r matches no string any more" % key)
        elif counted[key] != want:
            bad.append(
                "%s: exemption %r covers %d bare command(s), declared %d"
                % (key[0], key[1], counted[key], want)
            )
    return bad


def runnable_commands(texts: list[tuple[str, int, str]]) -> list[tuple[str, str]]:
    """(module path, the printed command up to its module) for every hop-spelled command, one per (path, module)."""
    seen: dict[tuple[str, str], str] = {}
    for rel, _line, text in texts:
        if _exemptions(rel, text, NOT_A_PRINTED_COMMAND):
            continue
        for m in RUNNABLE_M.finditer(text):
            seen.setdefault((rel, m.group(3)), m.group(0))
    return sorted((rel, command) for (rel, _module), command in seen.items())


_ROOT = paths.repo_root()
_TEXTS = printed_texts(_ROOT)
_RUNNABLE = runnable_commands(_TEXTS)
_FIND = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 3)"


def test_every_printed_python_m_command_spells_the_hop() -> None:
    """The class pin: a new port that prints `python -m`, `python3 -m` or `python3.N -m rediacc_ci...` without `PYTHONPATH=.ci` is named here. Control first: the detector fires on every planted bare spelling and not on the hop spelling, and an exemption whose bare count moves, or that matches nothing, is red."""
    planted = [
        ("x.py", 1, "usage: python3 -m rediacc_ci.a.b <x>"),
        ("x.py", 2, "usage: PYTHONPATH=.ci python3 -m rediacc_ci.a.b"),
        ("x.py", 3, "usage: PYTHONPATH=.ci python -m rediacc_ci.a.b"),
    ]
    assert bare_commands(planted, {}) == ["x.py:1: python3 -m rediacc_ci.a.b"]
    # f6733156.1 and .3: every interpreter spelling, behind a path or not, and the bare package.
    for text, want in (
        ("run: python -m rediacc_ci.a.b", "python -m rediacc_ci.a.b"),
        ("run: python3.12 -m rediacc_ci.a.b", "python3.12 -m rediacc_ci.a.b"),
        ("run: /usr/bin/python3 -m rediacc_ci.a.b", "/usr/bin/python3 -m rediacc_ci.a.b"),
        ("run: .venv/bin/python -m rediacc_ci.a", ".venv/bin/python -m rediacc_ci.a"),
        ("run `python3 -m rediacc_ci` first", "python3 -m rediacc_ci"),
    ):
        assert bare_commands([("x.py", 1, text)], {}) == ["x.py:1: %s" % want], text
    for text in (
        "run: cpython3 -m rediacc_ci.a",
        "run: PYTHONPATH=.ci python3.12 -m rediacc_ci.a",
        "python3 -m pytest",
        "run: python3 -m rediacc_cix",
        "run: python3 -m rediacc_ci_old.a",
    ):
        assert bare_commands([("x.py", 1, text)], {}) == [], text
    # 9edcb111.3, the other side of the boundary: the package still matches when punctuation, not a word character, follows it.
    for text in ("run `python3 -m rediacc_ci`.", "run python3 -m rediacc_ci."):
        assert bare_commands([("x.py", 1, text)], {}) == ["x.py:1: python3 -m rediacc_ci"], text
    # f6733156.2: an exemption is counted, so a new bare line inside an exempt string is red, and so is a stale one.
    fixture = {("x.py", "FIXTURE"): (1, "a planted exemption")}
    assert bare_commands([("x.py", 1, "FIXTURE python3 -m rediacc_ci.a")], fixture) == []
    grown = bare_commands(
        [("x.py", 1, "FIXTURE python3 -m rediacc_ci.a\nusage: python -m rediacc_ci.b")], fixture
    )
    assert grown == ["x.py: exemption 'FIXTURE' covers 2 bare command(s), declared 1"], grown
    assert bare_commands([("x.py", 1, "nothing here")], fixture) == [
        "x.py: exemption 'FIXTURE' matches no string any more"
    ]
    # 9edcb111.1: one string carrying two fragments counts toward BOTH keys; neither is stale, and each declared count is checked.
    pair = {
        ("x.py", "ONE"): (1, "a planted exemption"),
        ("x.py", "TWO"): (1, "a planted exemption"),
    }
    both = [("x.py", 1, "ONE TWO python3 -m rediacc_ci.a")]
    assert bare_commands(both, pair) == []
    pair[("x.py", "TWO")] = (2, "a planted exemption")
    assert bare_commands(both, pair) == [
        "x.py: exemption 'TWO' covers 1 bare command(s), declared 2"
    ]
    assert len(_RUNNABLE) >= 40, (
        "CONTROL: only %d printed commands found; the corpus is not being read" % len(_RUNNABLE)
    )
    assert bare_commands(_TEXTS) == []


@pytest.mark.parametrize(
    ("rel", "command"), _RUNNABLE, ids=["%s:%s" % (r, c.rsplit(" ", 1)[-1]) for r, c in _RUNNABLE]
)
def test_every_printed_python_m_command_runs_from_the_repository_root(
    rel: str, command: str
) -> None:
    """Each printed command, split the way `twin_names.usage_command` splits a usage line, finds its module from the repository root under the environment it spells. The module is located, not run: running every printed command would start e2e suites and deploys. Control first: without its `PYTHONPATH=.ci` the same lookup fails."""
    assigned, argv = usage_command("usage: " + command)
    assert assigned.get("PYTHONPATH") == ".ci", command
    assert argv[1] == "-m", command
    module = argv[2]
    bare = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    probe = [sys.executable, "-c", _FIND, module]
    control = subprocess.run(probe, cwd=_ROOT, env=bare, capture_output=True, check=False)
    assert control.returncode != 0, (
        "CONTROL: %s resolved with no PYTHONPATH; this case proves nothing" % module
    )
    got = subprocess.run(
        probe, cwd=_ROOT, env={**bare, **assigned}, capture_output=True, text=True, check=False
    )
    assert got.returncode == 0, "%s prints `%s`, which cannot find %s from the root: %s" % (
        rel,
        command,
        module,
        got.stderr,
    )


_SPAWN_AFTER_CHDIR = (
    "import os, subprocess, sys\n"
    "import rediacc_ci\n"
    "os.chdir(sys.argv[1])\n"
    "sys.exit(subprocess.call([sys.executable, '-c', 'import rediacc_ci']))\n"
)


def test_a_relative_pythonpath_survives_a_chdir_before_a_sibling_is_spawned(tmp_path) -> None:
    """The CLI build's failure, in small: started as `PYTHONPATH=.ci python3 -m rediacc_ci.<x>`, a module changes directory and starts a sibling module, whose import of the package must still resolve."""
    root = paths.repo_root()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    done = subprocess.run(
        [sys.executable, "-c", _SPAWN_AFTER_CHDIR, str(tmp_path)],
        cwd=root,
        env={**env, "PYTHONPATH": ".ci"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-600:]
    # CONTROL: the same child without the package imported first keeps the relative entry and cannot find it.
    bare = subprocess.run(
        [
            sys.executable,
            "-c",
            _SPAWN_AFTER_CHDIR.replace("import rediacc_ci\n", "", 1),
            str(tmp_path),
        ],
        cwd=root,
        env={**env, "PYTHONPATH": ".ci"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert bare.returncode != 0


@pytest.mark.parametrize(
    ("given", "want"),
    [("", ""), (".ci" + os.pathsep, "{root}/.ci" + os.pathsep), ("/abs/x", "/abs/x")],
)
def test_an_empty_pythonpath_entry_is_never_pinned(given: str, want: str) -> None:
    """An empty entry stays empty, so no child gains the starting directory on its path; an absolute entry is untouched."""
    root = paths.repo_root()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys\nsys.path.insert(0, sys.argv[1])\nimport rediacc_ci\nprint(os.environ['PYTHONPATH'], end='')",
            str(root / ".ci"),
        ],
        cwd=root,
        env={**env, "PYTHONPATH": given},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-400:]
    assert done.stdout == want.format(root=root)
