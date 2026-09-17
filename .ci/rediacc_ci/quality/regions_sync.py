"""The two copies of the region list must be identical.

Ported from `.ci/scripts/quality/check-regions-sync.sh`, which is not deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

WHY. `packages/shared/src/regions/index.ts` imports `./data.json` and its comment says it is "a copy of the root regions.json kept in sync by the build process". There is no such build process. The two files are identical today only because somebody copied one onto the other by hand, and nothing would have said so if they had drifted.

The drift is silent in the worst direction: `data.json` is the BAKED-IN fallback the CLI uses when it cannot fetch the live list, and it cannot fetch the live list
-- `region-discovery.ts` points at `${SITE_URL}/regions.json`, which returns 404
(measured 2026-08-26). So the fallback is not a fallback, it is the ONLY path, and a stale copy of it would be what every user actually gets while the root file looked authoritative.

This gate does not invent the sync process the comment describes. It makes the comment's PROMISE enforceable, which is the cheaper and more honest half: the files may be maintained by hand, but they can no longer diverge unnoticed.

WHAT IT CANNOT SEE: whether either file's CONTENT is correct, and whether the live endpoint serves anything at all. The 404 is a separate, larger finding.

-----------------------------------------------------------------------------
PORT NOTES. What changed, what did not, and the one thing that is now weaker.
-----------------------------------------------------------------------------

THE COMPARISON IS OVER PARSED JSON, NOT BYTES, and that is carried across verbatim because it is a decision rather than an implementation: formatting differences are not drift, and failing on them would train people to reformat rather than to reconcile. The bash twin achieved it by shelling out to
`python3 -c "json.dumps(json.load(...), sort_keys=True)"` twice. The port calls
`json.load` directly, which removes two subprocesses and, more usefully, removes the class of failure where the interpreter that parses the file is not the interpreter the gate is running under.

`require_cmd python3` IS GONE, AND ITS DISAPPEARANCE IS NOT A LOSS. The twin checks for python3 TWICE -- once through `require_cmd` at the top and once again through `command -v` just before `norm()` is defined -- because a comparison that cannot run is not a pass. In a Python program the interpreter is a precondition of reaching line one, so the check has nothing left to guard.
The SECOND copy of it in the twin is worth naming: it is dead code even in bash, since `require_cmd` already exited. It is not reproduced.

THE TWIN SOURCES `.ci/scripts/lib/common.sh` AND THE PORT DOES NOT, which is the one archaeology token this file would otherwise drop. Its two `# shellcheck
source=` / `# BLOCKER:` lines record that `log_error`, `log_info` and
`get_repo_root` are used throughout, and that the BLOCKER exists because `check-python-gate-deps` and shellcheck would otherwise read the source line as unused. In the port `log_*` comes from `rediacc_ci.log` and the root from `rediacc_ci.paths.repo_root()`, so there is no source line and no suppression to justify -- but the FACT that these three helpers are the gate's only
dependency on the shared bash library is what makes the twin cheap to retire, and that is worth keeping.

THE EXIT-STATUS BEHAVIOUR ON A NON-DICT, NON-LIST ROOT IS PRESERVED EXACTLY, and it is the ugly corner of the original. The twin computes

    len(d.get('regions', d)) if isinstance(d,(dict,list)) else 0

and a top-level JSON *list* satisfies the isinstance test, then dies on `.get` with an AttributeError. Under `set -e` the assignment carries that failure out and the script exits non-zero having printed a traceback and no verdict. The port reproduces the same expression rather than "fixing" it, because the fix is a behaviour change and this file's job is to keep the verdict. The
traceback TEXT differs between the two -- it names different files -- but a crash is not a verdict on either side, and `scripts/lib/shadow-gate.ts` classifies neither as a finding.

THE DIFF PRINTED ON DIVERGENCE. The twin ends with `diff <(printf '%s\n' "$a") <(printf '%s\n' "$b") | head -20`. Both operands are ONE line -- `json.dumps` with no indent -- so the output is always the four-line normal-format hunk `1c1`, `< a`, `---`, `> b`, and `head -20` never truncates anything. The port emits those four lines literally rather than reaching for difflib, which
produces a different format for the same fact. The `head -20` is carried as a cap anyway, so a future multi-line normalization cannot turn a divergence report into a screenful.
"""

import json
import os
import pathlib
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The two paths, and the environment seams that redirect them. The seams exist
# for this gate's own controls: a gate whose subject cannot be moved can only be
# proven against the real tree, where it is green, and a control that cannot plant a defect proves nothing. Names are carried over unchanged from the twin so a harness driving either implementation sets the same two variables.
ROOT_FILE_ENV = "REGIONS_ROOT_FILE"
BAKED_FILE_ENV = "REGIONS_BAKED_FILE"
DEFAULT_ROOT_FILE = "regions.json"
DEFAULT_BAKED_FILE = "packages/shared/src/regions/data.json"

# The floor. One region is the smallest list that is not vacuous; the twin's
# comment for it -- "an empty list would make this comparison vacuous" -- is the load-bearing half, because two empty files compare EQUAL and a gate with no floor would report success over two broken ones.
MIN_REGIONS = 1

# The cap on the divergence hunk, carried from `head -20` in the twin.
DIFF_CAP = 20


def normalize(path: pathlib.Path) -> str:
    """The file's JSON, canonically re-serialized. Raises on invalid JSON.

    `sort_keys=True` is what makes this a comparison of CONTENT: it sorts every
    mapping recursively, so two files that disagree only about key order compare equal, which is the whole point of not comparing bytes.

    Deliberately no `indent`: the result is one line, and the divergence report below depends on that.
    """
    with path.open(encoding="utf-8") as handle:
        return json.dumps(json.load(handle), sort_keys=True)


def region_count(path: pathlib.Path) -> int:
    """How many regions the root file declares.

    The expression is the twin's, character for character in meaning, including the AttributeError a top-level list produces. See the module docstring: the corner is preserved rather than repaired, because repairing it would change the verdict on an input the twin refuses.
    """
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return len(data.get("regions", data)) if isinstance(data, (dict, list)) else 0


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Returns the process exit code; never raises for a verdict."""
    if argv and argv[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    root_file = root / os.environ.get(ROOT_FILE_ENV, DEFAULT_ROOT_FILE)
    baked_file = root / os.environ.get(BAKED_FILE_ENV, DEFAULT_BAKED_FILE)

    # Reported relative to the repo, as the twin does by `cd`-ing to the root first and then naming the paths as given. An absolute path in a finding is noise that differs per machine and would make two runs of the same gate on two checkouts produce different finding text for the same defect.
    names = {
        root_file: os.environ.get(ROOT_FILE_ENV, DEFAULT_ROOT_FILE),
        baked_file: os.environ.get(BAKED_FILE_ENV, DEFAULT_BAKED_FILE),
    }

    for candidate in (root_file, baked_file):
        shown = names[candidate]
        if not candidate.is_file():
            log.error(
                "regions-sync: %s does not exist. Nothing to compare is not a clean "
                "tree -- if the region list moved, retarget this gate deliberately." % shown
            )
            return 1
        # ANTI-VACUITY. An empty or truncated file would compare "equal" to another empty one and this gate would report success over two broken files. `-s` in the twin is a size test, not a parse test, and it fires BEFORE the parse so that the message names emptiness rather than arriving as a JSONDecodeError about column one.
        if candidate.stat().st_size == 0:
            log.error("regions-sync: %s is EMPTY, which is never a valid region list." % shown)
            return 1

    try:
        left = normalize(root_file)
    except (json.JSONDecodeError, UnicodeDecodeError):
        log.error("regions-sync: %s is not valid JSON" % names[root_file])
        return 1
    try:
        right = normalize(baked_file)
    except (json.JSONDecodeError, UnicodeDecodeError):
        log.error("regions-sync: %s is not valid JSON" % names[baked_file])
        return 1

    count = region_count(root_file)
    if count < MIN_REGIONS:
        log.error(
            "regions-sync: %s parsed to %d region(s); an empty list would make this "
            "comparison vacuous." % (names[root_file], count)
        )
        return 1

    if left != right:
        log.error("regions-sync: %s and %s have DIVERGED." % (names[root_file], names[baked_file]))
        log.error(
            "  %s is the baked-in fallback the CLI ships with, and because" % names[baked_file]
        )
        log.error("  ${SITE_URL}/regions.json currently 404s, that fallback is the ONLY list")
        log.error("  users ever get. A stale copy is therefore not a cosmetic mismatch.")
        log.error("  Reconcile them: cp '%s' '%s'" % (names[root_file], names[baked_file]))
        for line in unified_hunk(left, right)[:DIFF_CAP]:
            print(line, file=sys.stderr)
        return 1

    log.info(
        "regions-sync: %s and %s agree (%d region(s))"
        % (names[root_file], names[baked_file], count)
    )
    log.info("  Blind spot: proves the two copies MATCH, not that either is correct,")
    log.info("  and says nothing about whether the live endpoint serves the list.")
    return 0


def unified_hunk(left: str, right: str) -> list[str]:
    """`diff` normal format for two ONE-LINE strings.

    Written out rather than delegated to difflib because difflib's formats (`unified_diff`, `ndiff`, `context_diff`) all render this fact differently
    from `diff`, and the twin's readers have seen `1c1` for as long as the gate
    has existed. Four lines, always, for the one shape this can produce.
    """
    return ["1c1", "< %s" % left, "---", "> %s" % right]


def selftest() -> int:
    """Plant a defect in BOTH directions and require the gate to notice.

    A control that only proves the gate FIRES is half a control: a gate that always fires is as useless as one that never does, and it is the direction a reviewer waves through because red looks like diligence. So every case below has its mirror.

    Built by CONSTRUCTION in a tempdir, never by mutating the real region files: `check-control-vacuity.sh` classifies a control built by in-place substitution as one that must additionally prove the plant landed, and the cheaper answer is to not build controls that way.
    """
    # floor=10 rather than 0: the floor is the only thing that catches a selftest
    # whose cases stopped executing, and a default of zero is a floor that cannot fail. See rediacc_ci.controls for the five drifted copies that taught it.
    ctl = Controls("regions-sync", floor=10, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        good = base / "root.json"
        copy = base / "baked.json"
        three = {"regions": [{"id": "eu"}, {"id": "us"}, {"id": "asia"}]}

        def run(root_text: str | None, baked_text: str | None) -> int:
            if root_text is None:
                good.unlink(missing_ok=True)
            else:
                good.write_text(root_text, encoding="utf-8")
            if baked_text is None:
                copy.unlink(missing_ok=True)
            else:
                copy.write_text(baked_text, encoding="utf-8")
            env = dict(os.environ)
            env[ROOT_FILE_ENV] = str(good)
            env[BAKED_FILE_ENV] = str(copy)
            old = dict(os.environ)
            os.environ.clear()
            os.environ.update(env)
            try:
                return main([])
            finally:
                os.environ.clear()
                os.environ.update(old)

        same = json.dumps(three)
        ctl.check("CONTROL: two identical lists agree", run(same, same), 0)
        # The same content, reformatted and re-ordered. This must STILL pass, or the gate is comparing bytes and the twin's stated design is lost.
        reordered = json.dumps({"regions": three["regions"]}, indent=4)
        ctl.check("CONTROL: formatting is not drift", run(same, reordered), 0)

        # THE PLANT. One region removed from the baked copy. Nothing else changes.
        drifted = json.dumps({"regions": three["regions"][:2]})
        ctl.check("PLANT: a dropped region is DIVERGED", run(same, drifted), 1)

        # The mirror: a region ADDED to the baked copy is the same defect from the other end, and a gate that only compares lengths one way would miss it.
        extra = json.dumps({"regions": [*three["regions"], {"id": "sa"}]})
        ctl.check("PLANT MIRROR: an added region is DIVERGED", run(same, extra), 1)

        ctl.check("PLANT: a missing root file is refused", run(None, same), 1)
        ctl.check("PLANT: a missing baked file is refused", run(same, None), 1)
        ctl.check("PLANT: an empty root file is refused", run("", same), 1)
        ctl.check("PLANT: an empty baked file is refused", run(same, ""), 1)
        ctl.check("PLANT: invalid JSON is refused", run("{not json", same), 1)
        # THE VACUITY PLANT, and the one that matters most here. Two EMPTY region lists compare equal. Without the floor this is the shape that reports success over two broken files, which is the failure the whole gate is written against.
        empty_list = json.dumps({"regions": []})
        ctl.check(
            "VACUITY: two empty-but-equal lists are refused by the floor",
            run(empty_list, empty_list),
            1,
        )
        # And its mirror, so the floor is not passing because it fires on everything: exactly MIN_REGIONS is enough.
        one = json.dumps({"regions": [{"id": "eu"}]})
        ctl.check("FLOOR MIRROR: exactly %d region(s) is enough" % MIN_REGIONS, run(one, one), 0)

    return 0 if ctl.report() else 1
