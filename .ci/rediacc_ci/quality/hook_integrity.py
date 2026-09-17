"""The enforcement layer cannot quietly disarm itself.

Ported from `.ci/scripts/quality/check-hook-integrity.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

The twin's header, carried whole. Every paragraph of it records a hole this gate had and closed, and the holes are the design:

    WHY. Everything this repo relies on to stop an agent doing the wrong thing is
    a hook, and until 2026-08-25 nothing guarded the hooks themselves.
    block-protected-files.sh covers settings.json and pre-commit-check.sh only,
    and only against restore/checkout/rm. One session changed 5 hook files across
    6 commits with no friction at all. A session that finds a guard inconvenient
    can weaken it AND delete its controls in the same commit, and CI stays green.

    The operator chose gate-plus-warning over blocking the commit (a hard block
    would have fired six times that day on legitimate work), so the teeth are here.

    Two assertions:

      A. INVENTORY IS SHRINK-ONLY. Every block-*.sh in every audited chain
         appears in the baseline. A guard that leaves the tree fails until the
         baseline is deliberately drained, so removing a guard is a reviewable
         diff rather than a side effect.
      B. BOTH DIRECTIONS COVERED. Each guard needs a case asserting it BLOCKS and
         one asserting it ALLOWS. Block-only coverage cannot detect over-blocking,
         and an over-blocking guard is one that gets deleted -- which is how the
         rule dies. Guards that lack a direction TODAY are listed in the coverage
         baseline: it can shrink, never grow.

    ALL THREE CHAINS ARE AUDITED, and that is a 2026-08-27 repair of a hole this
    gate had from birth. GUARD_DIR was the single literal path .claude/hooks/
    pre-bash, so `pre-edit/` and `pre-ask/` were outside BOTH assertions --
    structurally invisible rather than merely uncovered. An audit found
    pre-edit/block-inline-python.sh sitting at 0 cases in either direction, a
    guard against code injection that this gate could never have flagged. Seven
    guards were in that position. Keys are chain-qualified (`pre-edit/block-x.sh`)
    so two chains can never collide on one basename.

    HELPER-DRIVEN CASES COUNT, which is the other half of that repair. The old
    reader grepped the literal string `check 2 pre-bash/<name>`, so the five
    `gh_case` cases for block-second-open-pr.sh and the four `_gc_run` cases for
    block-git-empty-commit.sh were invisible and both guards sat in the coverage
    baseline as gaps they had not been for months. A stale entry is not free: it
    is a slot where the NEXT regression hides. Helpers are resolved by reading the
    suite -- a function whose body names exactly one guard IS a case wrapper for
    that guard -- rather than from a hand-kept list that would rot the same way.

    Controls are built by CONSTRUCTION (fixtures written literally), so rewording
    a real guard cannot silently void them -- the failure
    check-control-vacuity.sh exists to catch.

    post-bash was MISSING until 2026-08-28. It is a real, registered chain --
    settings.json wires cancel-old-ci.sh and refresh-pr-body.sh into it -- and
    because it was absent from this list, both were outside the inventory and
    could be deleted with no gate noticing. Found by sweeping the class after the
    warn-* gap: that was a filename prefix escaping the net, this was a whole
    chain. B/C are unaffected: they glob block-*, and post-bash has none.

    THE LIST ITSELF NOW LIVES IN $SCOPE, not in this file, and the move is a
    widened seam rather than a tidy-up. The .claude hook port renames and adds
    chain directories; while this was a bash array inside the enforcement script,
    every such move was an edit to the enforcement script, made by whoever was
    moving files. Reading it from declared data means the port re-keys DATA and
    this gate's logic is never opened. $SCOPE carries the admission rule and the
    reason neither list can be derived.

    THERE IS NO HARDCODED HOOKS ROOT ANY MORE, and that is the second half of the
    same widening. `HOOKS="$ROOT/.claude/hooks"` and `SUITE="$HOOKS/test-hooks.sh"`
    made the whole gate a function of ONE directory: chains were names inside it,
    guard keys were fragments relative to it, and cases were read from exactly one
    file inside it. A guard that moves OUT of that directory does not fail this
    gate, it leaves it -- the corpus silently shrinks and every assertion below
    still passes over what remains. That is not hypothetical: 47 ported guards are
    tracked at .claude/rediacc_hooks/guards/ today and this gate cannot see one of
    them, because they are outside the root the seam was keyed on.

    So both seams are now REPO-RELATIVE FILE LISTS in $SCOPE:

      guard_dirs            the directories whose files are guards (section A/B's
                            subject). Keys are the repo-relative PATH, so the
                            inventory baseline is a list of files rather than a
                            list of fragments waiting for a root to be prepended.
      guards_outside_chains individual guard files that no directory sweep finds.
      case_sources          the files whose contents count as coverage cases
                            (section B/C's subject).

    A move re-keys one list in one place. Nothing below knows where .claude/hooks
    is, so nothing below narrows when it stops being where the guards live.

    REFUSING AN EMPTY LIST IS THE POINT. A missing or malformed scope file that
    yielded two empty arrays would make every loop below iterate zero times: A
    would find zero guards, B would check zero directions, and the gate would exit
    0 having audited nothing. That is precisely the vacuous green this file's own
    section C exists to abolish, so the load refuses instead of degrading.

    A DECLARED DIRECTORY THAT DOES NOT EXIST is the failure mode a file list adds,
    and it is exactly the one a move produces: rename the directory, forget the
    list, and the sweep below iterates nothing while every assertion still passes
    over the directories that are left. Silent narrowing by typo. Refuse instead.

    THE SUITE SPELLS A GUARD BY ITS DIRECTORY'S LAST SEGMENT plus its filename
    ("pre-bash/block-x.sh"), because that is how it joins $DIR. Two declared
    directories sharing a last segment would therefore be indistinguishable to the
    coverage reader, and one guard's cases would be credited to another's. Cheap
    to refuse, impossible to notice once it happens.

    TWO LISTS, because A and B ask different questions of a guard.

      all_guards  block-* AND warn-*  -- A: "can this file vanish unnoticed?"
                                         That applies to every guard there is.
      on_disk     block-* only        -- B/C: "does it have a block case AND an
                                         allow case?" A warn-* guard exits 0
                                         always and has NO block direction, so
                                         demanding one would make the gate wrong
                                         about four correct guards -- and a gate
                                         that is wrong is a gate that gets
                                         suppressed. Measured before splitting:
                                         extending the single list to warn-*
                                         failed all four with block=0,allow=0.

    Until this split, warn-hook-change.sh, warn-remote-drift.sh and
    warn-submodule-deletions.sh were outside the inventory entirely -- and A's own
    failure text, "each of these can be deleted with no gate noticing", was true of
    them with nothing saying so.

    GUARDS OUTSIDE ANY CHAIN DIRECTORY are declared in $SCOPE under
    `guards_outside_chains`, because a glob cannot find them. The admission rule is
    WHETHER ABSENCE IS SILENT, not what the file is named or where it sits:

      * a missing pre-bash/post-bash guard just stops blocking -- nothing says so,
        which is the entire reason this inventory exists
      * a missing trapguard/dispatch.py means traps stop firing, equally silent
      * a missing require-jq.sh means the precondition it enforces goes unchecked

    DELIBERATELY EXCLUDED, and this is the other half of the rule: stop/worklist.py,
    stop/wl_wait.py, stop/wl_report.py and the context/*.py hooks are MACHINERY,
    not guards, and their absence is LOUD -- a missing stop hook errors on every
    single stop rather than quietly permitting something. A gate that cannot tell
    those apart would be inventorying files that already announce their own death.

    EXTENSION-AGNOSTIC, and that is the second half of this seam widening. The
    patterns were `block-*.sh` and `*.sh`, so the moment a guard is ported to
    Python it leaves BOTH sets: A's baseline arm still names the vanished .sh
    loudly, but the new .py file enters no list at all, so A's unlisted arm never
    mentions it and B stops asking it for either direction. That is a silent hole
    opened by a correct port, which is the exact class this gate was built for.
    Matching on the NAME PREFIX instead means a ported guard stays audited under
    its new extension.

    THE SEPARATOR IS PART OF THE PREFIX, found by planting the file a port
    actually produces. A first pass matched `block-*`, and a fixture named
    `block_ported.py` -- hyphen to underscore, which is what a Python port does to
    a module name -- still missed section B entirely while landing in the
    all-guards list, so it would have been inventoried as un-deletable and never
    asked for a block or an allow case. `block[-_]*` covers both spellings.

    Proven a no-op on the tree it was widened against: 42 block-* and 50 total,
    identical sets before and after, because no chain holds a .py guard yet.

    Two exclusions, both of them non-guards that a bare `*` would otherwise
    inventory: `test-*` files are the per-guard case suites this gate READS
    (section B resolves them at line-level), so listing them as guards would demand
    coverage of the coverage; `*.pyc` and directories are build litter and package
    roots (`pre-bash/lib`, `__pycache__`) rather than files that can silently stop
    enforcing anything.

    C. THE ANTI-VACUITY FLOOR CANNOT BE REMOVED.

    test-hooks.sh runs sibling modules' `--selftest` and folds their PASS count
    into its own. Without a MINIMUM-COUNT floor, a selftest that prints nothing and
    exits 0 reads as a passing suite -- and that is not hypothetical twice over:
    `wl_git.py` and `wl_admit.py` carried 18 controls each that NOTHING ran for
    months, while `wl_reggate.py --selftest` exits 0 having no selftest at all,
    because running a library module as a script does nothing and succeeds.

    The floor is what separates those three states from a real pass, so the floor
    itself is enforcement, and this file's whole premise is that enforcement cannot
    quietly disarm itself. Deleting the floor is a one-line edit that turns every
    orphaned control back into a silent green.

    THE HARNESS IS DERIVED FROM $CASE_SOURCES, not named. While this read
    `HARNESS="$SUITE"`, section C was an assertion about one hardcoded file, and a
    suite that MOVED took its floor out of the gate's sight without failing
    anything -- the same silent narrowing the seam widening above is about. A
    declared case source qualifies as a folding harness by CONTAINING a fold of an
    external count, which is the only thing a floor is ever about, so a source with
    no folds is correctly silent rather than wrongly red.

    ZERO folding harnesses is not "nothing to check", it is section C auditing
    nothing, which is the vacuous green this whole section exists to abolish.

    EVERY selftest fold needs a floor, not just one, and counting is not enough to
    know that. A single `lt "$floor"` anywhere satisfied the check above while two
    folds (wl_roundlog, wl_planfid) added a sibling module's PASS count with no
    refusal at all -- the exact vacuous-green shape this section exists to prevent,
    in the very file it protects.

    Nor is a `floor` variable the only honest guard: five of the eight folds refuse
    a ZERO count instead (`-gt 0`, `-eq 0`), which is a floor of one and catches the
    same failure. So this looks at each fold SITE and asks whether some count
    refusal stands between the count and the addition. A gate demanding one exact
    spelling would have reported five correct folds as defects, and a gate that
    cries wolf is one the next session learns to route around.

    A fold of a VARIABLE count. `PASS + 1` is a single case incrementing itself and
    needs no floor; `PASS + n` folds in a whole sibling suite's self-reported total.

    A minimum can be a named `floor` or a literal number -- `-lt 12` is exactly as
    much of a floor as `-lt "$floor"`, and demanding the variable reported two
    correctly floored folds as defects the first time this ran. A zero-count
    refusal (`-gt 0`, `-eq 0`) is a floor of one and catches the same failure.

    THE WINDOW INCLUDES THE FOLD LINE ITSELF. It used to stop one line short, so a
    fold whose refusal sits on the SAME line -- `if [ "$n" -lt "$floor" ]; then
    FAIL=...; else PASS=$((PASS + n)); fi` -- was reported as unfloored. A correctly
    floored fold named as a defect is the cry-wolf failure the comment above is
    about, and it is the reason a floorcheck fixture written that way went red while
    asserting nothing. Found by planting it. No effect on the current harness, whose
    folds are all multi-line.

    A's second arm needs its own control, or "everything on disk is listed" is a
    sentence nothing tests. Six guards sat unlisted for weeks precisely because
    nothing asked. Built by construction: a fixture inventory with one name REMOVED,
    so the comparison has a known answer.

    A's FIRST arm ("guard(s) in the baseline but GONE from the tree", the
    missing-array check above) had no control at all until this stop: every
    assertion this gate makes elsewhere is proven by a planted fixture, but a
    baseline entry whose file was deleted from disk had never been shown to actually
    trip a failure. Same shape as the anti-vacuity rule this file itself states: a
    check that has never been proven to fail is the same class as a check that
    cannot fail. Built the same way as the second arm's control above -- fixture
    inventory + fixture hooks dir, never the real ones.

    THE FIRST fold is the SAME-LINE spelling, folded into this fixture rather than
    given its own control so the check gains coverage without gaining an output
    line. It was reported as unfloored until the window included the fold line
    itself; if that regresses, this control goes red.

    IT HAS TO COME FIRST. Placed after the multi-line fold it proved nothing: the
    12-line lookbehind reached that fold's `-lt "$floor"` and passed the same-line
    fold on someone else's floor. Caught by reverting the fix and watching the
    control stay green.

    CONTROL, by construction: strip the floor from a copy and require the check to
    notice. Built by DELETION of a line that is present, not by pattern
    substitution, so it cannot silently produce an identical copy -- the vacuous-
    plant hole check-control-vacuity.sh exists for.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE SPEC INDIRECTION IS KEPT, AND IT IS NOT CEREMONY. The twin writes a JSON `spec` (sources plus a key-to-directory map) and hands `covmap` its PATH, so the reader has no opinion about where guards live: the real run hands it the checkout and the fixture controls hand it a throwaway tree the same way. This port keeps the same two-argument shape as a data structure rather than a
file, because the property that matters is that the reader takes its roots from the caller.

`os.path.join(root, tail)` IGNORES `root` WHEN `tail` IS ABSOLUTE, which is what lets the fixture controls pass absolute paths through the same `mkspec`. Carried, because a port that rejected absolute entries would break exactly the controls that make this gate's green mean something.

DEDUPLICATION OF THE FINAL PATH SEGMENT IS REFUSED BEFORE ANYTHING RUNS. The twin does it with parameter expansion rather than `sed`, and says why: "check-control-vacuity.sh reads any `sed s///` in a gate that has controls as a control mutant built by substitution and demands a proof-of-plant this line has no plant for. Measured: adding the sed spelling turned that gate red on this
file, which was clean at HEAD." The port has no such hazard, and the refusal is carried anyway because the CONDITION is the point, not the spelling.

THE COVERAGE READER'S THREE SOURCES are direct `check`/`check_out` calls, helper functions whose body names exactly one guard, and a dedicated `test-<stem>.py|.sh` beside the guard. All three are reproduced with the twin's own regexes, including the extension-agnostic `\\.(?:sh|py)` widening: "after the hook port a case in the suite names `pre-bash/block_x.py`, and a reader
anchored to `.sh` would count zero cases for it. B would then report a fully covered guard as newly uncovered -- loud rather than silent, but wrong, and a gate that is wrong is a gate that gets suppressed. Measured a no-op on the suite it was widened against: 81 direct case matches before and after, identical set."

`check` AND `check_out` THEMSELVES NAME THEIR GUARD THROUGH A VARIABLE, so they cannot match the helper-wrapper rule and do not need excluding by name. Carried verbatim from the twin, because it is the sort of exclusion a port adds "for safety" and thereby changes the answer.

THE TWIN READS ITS SCOPE WITH `while read` AND A TRAILING `|| true`, and both halves of that are archaeology this port would otherwise lose. It said `mapfile` until 2026-09-06; the twin's own words for the change:

    `while read` RATHER THAN `mapfile`, and it is not a style choice. `mapfile`
    is bash 4+ and `check:ci-shell-commands` rejects it as unavailable in the
    minimal CI image; these three lines were the last three findings that gate
    had. Behaviour is identical for this input: scope_list emits one entry per
    line and an entry can never contain a newline, since it is a JSON string this
    file's own reader has already rejected unless every element is a non-empty
    string.

    The trailing `|| true` on each is REQUIRED and is not defensive noise. `read`
    returns non-zero at end of input, which under `set -e` would kill the script
    at the last line of the loop and take the emptiness refusal below with it.
    That refusal is the only thing standing between an unreadable scope file and
    a gate that exits 0 having audited nothing.

THE PORT NEEDED NO CHANGE FOR IT, and that is worth writing down rather than leaving as an absence. `scope_list` here raises `ScopeError` and the caller turns that into an empty list, which is the same value both `mapfile` and the `while read` loop produce from an empty process substitution. There is no `set -e` to survive, so there is nothing for `|| true` to correspond to -- but
the HAZARD it guards is real in this file too, and it is the reason the three `except ScopeError` arms below assign `[]` and fall through to the emptiness refusal instead of returning early. A port that let the exception escape would exit non-zero with a traceback rather than the gate's own four-line refusal, which reads as a broken runner rather than an unreadable data file.

THE DIFFERENTIAL COVERS ALL THREE WAYS THE SCOPE CAN COLLAPSE, because under the `while read` form they are the same event and the `|| true` fires on the FIRST `read` rather than the last: a declared key holding an empty list, a scope file
with no such key at all, and a scope file that is not JSON. The ledger carries a
tree for each.
"""

import json
import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The three declared inputs. Repo-relative, and named once.
SCOPE_REL = "scripts/data/hook-audit-scope.json"
INV_REL = "scripts/data/hook-inventory-baseline.json"
COV_REL = "scripts/data/hook-coverage-baseline.json"

# A guard file's name prefix, both spellings. `block[-_]*` in the twin: a Python port of a guard turns the hyphen into an underscore, and a reader anchored on the hyphen would drop it from section B while still inventorying it.
GUARD_PREFIXES = ("block-", "block_")
GUARD_SUFFIXES = (".sh", ".py")

# A fold of a VARIABLE count into the harness's own PASS total.
FOLD_RE = re.compile(r"PASS=\$\(\(PASS \+ ([A-Za-z_][A-Za-z0-9_]*)\)\)")

# Some count refusal standing between the count and the addition. A named `floor`, a literal minimum, or a zero-count refusal: all three are floors.
GUARD_RE = re.compile(r"-lt[ \t]+(\"?\$?\{?floor|[0-9])|-gt[ \t]+0|-eq[ \t]+0|-le[ \t]+0")

# How far back a fold's refusal may sit. Twelve lines, INCLUDING the fold line itself; see the header for the same-line spelling that the exclusive window reported as a defect.
FOLD_WINDOW = 12

# What makes a declared case source a FOLDING HARNESS: it folds an external count.
HARNESS_RE = re.compile(r"PASS=\$\(\(PASS \+ [A-Za-z_]")

# The floor line section C requires of every folding harness.
FLOOR_LINE = 'lt "$floor"'


class ScopeError(ValueError):
    """The scope file is unreadable, or a declared key is empty or malformed.

    A named type because the caller must refuse rather than degrade: an empty scope makes every loop iterate zero times and the gate exit 0 having audited nothing.
    """


def scope_list(path: pathlib.Path, key: str) -> list[str]:
    """One entry per line, or a refusal. Never a partial list.

    The twin's embedded reader exits 1 on ANY of: an unreadable file, a value that is not a list, an empty list, or a list holding a non-string or an empty string. All four are the same event -- the seam scanned to nothing -- and all four must refuse.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ScopeError(str(exc)) from exc
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ScopeError("%s is not a non-empty list" % key)
    if not all(isinstance(x, str) and x for x in value):
        raise ScopeError("%s holds a non-string or an empty entry" % key)
    return list(value)


def mkspec(root: str, sources: list[str], dirs: list[str]) -> dict:
    """The seam, serialised. `{"sources": [...], "dirs": {key: abs}}`.

    Every path the reader below touches arrives through this, so the reader has no opinion about where guards live: callers hand it a root plus two lists, and the fixture controls hand it a throwaway tree the same way the real run hands it the checkout. An absolute entry passes through unchanged (`os.path.join` ignores the root when the tail is absolute).
    """
    return {
        "sources": [os.path.join(root, s) for s in sources],
        # KEY -> absolute directory. The key is whatever the caller declared, so the real run keys by repo-relative path and the fixtures key by chain name.
        "dirs": {d: os.path.join(root, d) for d in dirs},
    }


def covmap(spec: dict) -> list[tuple[str, int, int]]:
    """Per guard, `(key/name, block-cases, allow-cases)`.

    Counts cases asserting exit 2 and cases asserting exit 0, from three sources: direct `check`/`check_out` calls, calls to a helper function that wraps exactly one guard, and a dedicated `test-<stem>.py|.sh` beside the guard (which exists to assert both directions, so it counts as both).

    CASES COME FROM A LIST OF SOURCES, not from one suite file. While it was one file, moving a guard's cases into a second suite made that guard read as newly uncovered -- and the cheapest way to make that red go away is to baseline the guard, which retires the assertion permanently. Reading every declared source means a case that MOVED still counts, and only a case that was
    DELETED goes red.
    """
    sources, dirs = spec["sources"], spec["dirs"]
    src = ""
    for path in sources:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                src += handle.read() + "\n"
        except OSError:
            pass

    # The suite names a guard by its directory's LAST SEGMENT plus its filename, because that is how it joins $DIR. The key is the caller's declared path, and the two are related here rather than by any assumption about a root. A duplicate segment is refused before this runs.
    segs = sorted({os.path.basename(k.rstrip("/")) for k in dirs})
    chain_re = "|".join(re.escape(c) for c in segs)
    # EXTENSION-AGNOSTIC for the same reason the disk globs are; see the header.
    guard_re = r"(?:%s)/[A-Za-z0-9_.-]+\.(?:sh|py)" % chain_re

    counts: dict[str, tuple[int, int]] = {}

    def bump(guard: str, rc: str) -> None:
        block, allow = counts.get(guard, (0, 0))
        counts[guard] = (block + (rc == "2"), allow + (rc == "0"))

    # 1. Direct case calls.
    for rc, guard in re.findall(r"\b(?:check|check_out)\s+([0-9]+)\s+(%s)" % guard_re, src):
        bump(guard, rc)

    # 2. Helper wrappers. A shell function whose body names exactly ONE guard
    #    under $DIR is a case wrapper for it; its call sites take the expected rc
    # first, the same shape `check` uses. `check` and `check_out` themselves name their guard through a VARIABLE, so they cannot match here and do not need excluding by name.
    for match in re.finditer(
        r"^([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{(.*?)^\}", src, re.MULTILINE | re.DOTALL
    ):
        fn, body = match.group(1), match.group(2)
        named = set(re.findall(r"\$DIR/(%s)" % guard_re, body))
        if len(named) != 1:
            continue
        guard = named.pop()
        for rc in re.findall(r"^[ \t]*%s\s+([0-9]+)\b" % re.escape(fn), src, re.MULTILINE):
            bump(guard, rc)

    out: list[tuple[str, int, int]] = []
    # 3. A dedicated test file covers both directions by definition.
    for key, directory in sorted(dirs.items()):
        if not os.path.isdir(directory):
            continue
        seg = os.path.basename(key.rstrip("/"))
        for name in sorted(os.listdir(directory)):
            # Same prefix and extension rule as the on-disk glob below, including the underscore spelling a Python port produces. splitext rather than name[:-3], which only happens to be right while every extension is three characters long.
            if not (name.startswith(GUARD_PREFIXES) and name.endswith(GUARD_SUFFIXES)):
                continue
            block, allow = counts.get("%s/%s" % (seg, name), (0, 0))
            stem = os.path.splitext(name)[0]
            if any(
                os.path.exists(os.path.join(directory, "test-%s%s" % (stem, ext)))
                for ext in (".py", ".sh")
            ):
                block, allow = block + 1, allow + 1
            out.append(("%s/%s" % (key, name), block, allow))
    return out


def lookup(mapping: dict[str, tuple[int, int]], guard: str) -> tuple[int, int]:
    """`awk '$1 == g'` with the twin's `END { if (!found) print 0, 0 }`."""
    return mapping.get(guard, (0, 0))


def floorcheck(text: str) -> list[int]:
    """Line numbers of folds with NO minimum standing between count and addition.

    The window INCLUDES the fold line itself. See the header: it used to stop one line short, so a same-line refusal read as unfloored, and a correctly floored fold named as a defect is the cry-wolf failure that gets a gate routed around.
    """
    lines = text.splitlines()
    out: list[int] = []
    for index, line in enumerate(lines):
        if not FOLD_RE.search(line):
            continue
        window = lines[max(0, index - FOLD_WINDOW) : index + 1]
        if not any(GUARD_RE.search(w) for w in window):
            out.append(index + 1)
    return out


def read_json_list(path: pathlib.Path) -> list[str]:
    """A baseline file, as a list of strings. Raises on anything else."""
    with open(path, encoding="utf-8") as handle:
        return list(json.load(handle))


def inv_unlisted(listed: list[str], on_disk: list[str]) -> list[str]:
    """Guards on disk but absent from the inventory, in disk order.

    A guard in that state can be DELETED without A noticing, which is the whole point of A. Six guards were in it on 2026-08-27 because nobody re-ran the baseline after adding them.
    """
    known = set(listed)
    return [g for g in on_disk if g not in known]


def inv_missing(listed: list[str], root: pathlib.Path) -> list[str]:
    """Baselined guards whose file is gone from disk, in baseline order."""
    return [want for want in listed if want and not (root / want).is_file()]


# --------------------------------------------------------------------------- The fixtures every control is built from, written LITERALLY. ---------------------------------------------------------------------------

FIXTURE_SUITE = """check 2 pre-bash/block-fixture-both.sh "x" "blocks"
check 0 pre-bash/block-fixture-both.sh "y" "allows"
check 2 pre-bash/block-fixture-blockonly.sh "x" "blocks"
check_out 2 pre-edit/block-fixture-editchain.sh "x" "blocks" "needle"
check_out 0 pre-edit/block-fixture-editchain.sh "y" "allows" "needle"
fx_case() {
    local exp="$1"
    bash "$DIR/pre-bash/block-fixture-helper.sh" || true
}
fx_case 2 "wrapped block"
fx_case 0 "wrapped allow"
"""

FIXTURE_INV_FULL = ["pre-bash/block-a.sh", "pre-bash/block-b.sh"]
FIXTURE_INV_SHORT = ["pre-bash/block-a.sh"]

# THE FIRST fold is the SAME-LINE spelling, folded into this fixture rather than given its own control so the check gains coverage without gaining an output line. IT HAS TO COME FIRST: placed after the multi-line fold it proved nothing, because the 12-line lookbehind reached that fold's `-lt "$floor"` and passed the same-line fold on someone else's floor.
FIXTURE_FLOORED = """m=$(count)
if [[ "$m" -lt "$floor" ]]; then FAIL=$((FAIL + 1)); else PASS=$((PASS + m)); fi
n=$(count)
if [[ "$n" -lt "$floor" ]]; then
    FAIL=$((FAIL + 1))
else
    PASS=$((PASS + n))
fi
"""

FIXTURE_FLOORED_LITERAL = """n=$(count)
if [[ "$n" -lt 12 ]]; then
    FAIL=$((FAIL + 1))
else
    PASS=$((PASS + n))
fi
"""

FIXTURE_FLOORED_ZERO = """n=$(count)
if [[ $n -gt 0 ]]; then
    PASS=$((PASS + n))
fi
"""

FIXTURE_UNFLOORED = """n=$(count)
PASS=$((PASS + n))
"""


def build_fixture_hooks(tmp: pathlib.Path) -> pathlib.Path:
    """The twin's `$TMP/hooks` tree plus its suite. Written by construction."""
    (tmp / "hooks" / "pre-bash").mkdir(parents=True, exist_ok=True)
    (tmp / "hooks" / "pre-edit").mkdir(parents=True, exist_ok=True)
    for name in (
        "pre-bash/block-fixture-both.sh",
        "pre-bash/block-fixture-blockonly.sh",
        "pre-bash/block-fixture-helper.sh",
        "pre-edit/block-fixture-editchain.sh",
    ):
        (tmp / "hooks" / name).write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (tmp / "suite.sh").write_text(FIXTURE_SUITE, encoding="utf-8")
    return tmp


def main(argv: list[str] | None = None) -> int:
    """Run A, B, C and every control. 0 clean, 1 on any failure or refusal."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    scope = root / SCOPE_REL
    inv = root / INV_REL
    cov = root / COV_REL

    fails = 0

    def fail(message: str) -> None:
        nonlocal fails
        print("✗ %s" % message, file=sys.stderr)
        fails += 1

    def note(message: str) -> None:
        print(message, file=sys.stderr)

    def ok(message: str) -> None:
        print("ok   %s" % message)

    # ---- scope, read from data ------------------------------------------
    try:
        guard_dirs = scope_list(scope, "guard_dirs")
    except ScopeError:
        guard_dirs = []
    try:
        extra_guards = scope_list(scope, "guards_outside_chains")
    except ScopeError:
        extra_guards = []
    try:
        case_sources = scope_list(scope, "case_sources")
    except ScopeError:
        case_sources = []

    if not guard_dirs or not extra_guards or not case_sources:
        print("✗ hook integrity: scope file unreadable or empty: %s" % scope, file=sys.stderr)
        note(
            "     guard_dirs=%d guards_outside_chains=%d case_sources=%d"
            % (len(guard_dirs), len(extra_guards), len(case_sources))
        )
        note("     Refusing to run: with an empty scope every assertion below audits nothing")
        note("     and this gate would exit 0 having checked no guard at all.")
        return 1

    missing_dirs = [d for d in guard_dirs if not (root / d).is_dir()]
    missing_dirs += [s for s in case_sources if not (root / s).is_file()]
    if missing_dirs:
        print(
            "✗ hook integrity: declared in %s but ABSENT from the tree: %s"
            % (scope, " ".join(missing_dirs)),
            file=sys.stderr,
        )
        note("     Refusing to run: a declared path that is not there audits nothing, and the")
        note("     assertions below would still pass over whatever is left.")
        return 1

    segments = [os.path.basename(d.rstrip("/")) for d in guard_dirs]
    dupes = sorted({s for s in segments if segments.count(s) > 1})
    if dupes:
        print(
            "✗ hook integrity: two guard_dirs share a final path segment: %s"
            % ("".join(s + " " for s in dupes)),
            file=sys.stderr,
        )
        note("     The coverage reader matches cases on that segment, so their guards would be")
        note("     credited to each other. Rename one, or the seam lies about coverage.")
        return 1

    spec = mkspec(str(root), case_sources, guard_dirs)
    mapping = {key: (block, allow) for key, block, allow in covmap(spec)}

    on_disk: list[str] = []
    all_guards: list[str] = []
    for chain in guard_dirs:
        directory = root / chain
        for name in sorted(os.listdir(directory)):
            path = directory / name
            if not path.is_file():
                continue
            if name.startswith(GUARD_PREFIXES) and not name.endswith(".pyc"):
                on_disk.append("%s/%s" % (chain, name))
        for name in sorted(os.listdir(directory)):
            path = directory / name
            if not path.is_file():
                continue
            if name.startswith("test-") or name.endswith(".pyc"):
                continue
            all_guards.append("%s/%s" % (chain, name))
    all_guards.extend(guard for guard in extra_guards if (root / guard).exists())

    # ---- A. inventory is shrink-only -------------------------------------
    if not all_guards:
        fail("A. found ZERO guards on disk -- this gate is not seeing the tree.")
    elif not inv.is_file():
        fail("A. inventory baseline missing: %s" % inv)
    else:
        listed = read_json_list(inv)
        missing = inv_missing(listed, root)
        if not missing:
            ok(
                "A. all %d baselined guard(s) still present (%d on disk across %d chain(s))"
                % (len(listed), len(all_guards), len(guard_dirs))
            )
        else:
            fail("A. guard(s) in the baseline but GONE from the tree: %s" % " ".join(missing))
            note(
                "     Removing a guard is a deliberate act: drain the baseline in the same "
                "commit and say why."
            )
        unlisted = inv_unlisted(listed, all_guards)
        if unlisted:
            fail("A. guard(s) on disk but NOT in the inventory: %s" % " ".join(unlisted))
            note("     Until listed, each of these can be deleted with no gate noticing.")
            note("     Add them to %s." % inv)

    # ---- B. both directions ----------------------------------------------
    if not cov.is_file():
        fail("B. coverage baseline missing: %s" % cov)
    else:
        known = read_json_list(cov)
        known_set = set(known)
        newly = []
        for guard in on_disk:
            block, allow = lookup(mapping, guard)
            if block > 0 and allow > 0:
                continue
            if guard not in known_set:
                newly.append("%s(block=%d,allow=%d)" % (guard, block, allow))
        if not newly:
            ok("B. no guard lost a direction (%d known gap(s) still baselined)" % len(known))
        else:
            fail("B. guard(s) newly missing a direction: %s" % " ".join(newly))
            note("     A guard with only block-cases cannot detect OVER-blocking, and an")
            note("     over-blocking guard is one that gets deleted. Add the missing case.")
        # Shrink-only: a baselined guard that now has both directions must be drained.
        drained = []
        for guard in known:
            if not guard or not (root / guard).is_file():
                continue
            block, allow = lookup(mapping, guard)
            if block > 0 and allow > 0:
                drained.append(guard)
        if drained:
            fail(
                "B. these now have BOTH directions and must leave the coverage baseline: %s"
                % " ".join(drained)
            )
            note(
                "     The baseline is shrink-only; a fixed entry left in it hides the next "
                "regression."
            )

    # ---- controls, by construction ---------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = build_fixture_hooks(pathlib.Path(tmp))
        fixture_spec = mkspec(
            str(tmpdir / "hooks"), [str(tmpdir / "suite.sh")], ["pre-bash", "pre-edit"]
        )
        fixture = {key: (b, a) for key, b, a in covmap(fixture_spec)}

        block, allow = lookup(fixture, "pre-bash/block-fixture-both.sh")
        if block > 0 and allow > 0:
            ok("control: a guard with both directions is recognised as covered")
        else:
            fail(
                "CONTROL DID NOT FIRE: a both-direction fixture read as uncovered "
                "(block=%d allow=%d)" % (block, allow)
            )
        block, allow = lookup(fixture, "pre-bash/block-fixture-blockonly.sh")
        if block > 0 and allow == 0:
            ok("control: a block-only guard is detected as missing the allow direction")
        else:
            fail(
                "CONTROL DID NOT FIRE: a block-only fixture read as covered, so B proves "
                "nothing (block=%d allow=%d)" % (block, allow)
            )
        # The pre-edit chain, and the check_out spelling, both of which the old reader was blind to. Its blindness is the reason this control exists.
        block, allow = lookup(fixture, "pre-edit/block-fixture-editchain.sh")
        if block > 0 and allow > 0:
            ok("control: a pre-edit guard covered via check_out is seen")
        else:
            fail(
                "CONTROL DID NOT FIRE: pre-edit/check_out coverage read as absent "
                "(block=%d allow=%d), which is exactly the hole this gate was widened to close"
                % (block, allow)
            )
        # A helper-wrapped guard. Counting only the literal `check N <guard>` reported two well-covered guards as gaps for months.
        block, allow = lookup(fixture, "pre-bash/block-fixture-helper.sh")
        if block > 0 and allow > 0:
            ok("control: cases routed through a helper function are counted")
        else:
            fail(
                "CONTROL DID NOT FIRE: helper-driven cases read as absent (block=%d allow=%d)"
                % (block, allow)
            )
        # NEGATIVE control: a guard with no case anywhere must read 0/0, or the three controls above would pass over a reader that simply says yes to everything.
        (tmpdir / "hooks" / "pre-bash" / "block-fixture-uncovered.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
        )
        fixture = {key: (b, a) for key, b, a in covmap(fixture_spec)}
        block, allow = lookup(fixture, "pre-bash/block-fixture-uncovered.sh")
        if block == 0 and allow == 0:
            ok(
                "control: a guard with no cases reads 0/0 (the reader is not saying yes to everything)"
            )
        else:
            fail(
                "CONTROL DID NOT FIRE: an uncovered fixture reported coverage "
                "(block=%d allow=%d)" % (block, allow)
            )
        (tmpdir / "hooks" / "pre-bash" / "test-block-fixture-blockonly.py").write_text(
            "", encoding="utf-8"
        )
        fixture = {key: (b, a) for key, b, a in covmap(fixture_spec)}
        _block, allow = lookup(fixture, "pre-bash/block-fixture-blockonly.sh")
        if allow > 0:
            ok("control: a dedicated test file counts as covering both directions")
        else:
            fail("CONTROL DID NOT FIRE: a dedicated test file was not counted")

        # A's second arm needs its own control, or "everything on disk is listed" is a sentence nothing tests.
        if not inv_unlisted(FIXTURE_INV_FULL, FIXTURE_INV_FULL):
            ok("control: a complete inventory reports nothing unlisted")
        else:
            fail("CONTROL DID NOT FIRE: a complete inventory reported a missing entry")
        if inv_unlisted(FIXTURE_INV_SHORT, FIXTURE_INV_FULL) == ["pre-bash/block-b.sh"]:
            ok("control: a guard on disk but absent from the inventory is named")
        else:
            fail(
                "CONTROL DID NOT FIRE: an unlisted guard went unnamed, so A's second arm "
                "proves nothing"
            )

        # A's FIRST arm, built the same way: fixture inventory + fixture hooks dir, never the real ones. block-b.sh is deliberately absent.
        inv_hooks = tmpdir / "inv-hooks"
        (inv_hooks / "pre-bash").mkdir(parents=True, exist_ok=True)
        (inv_hooks / "pre-bash" / "block-a.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
        )
        if inv_missing(FIXTURE_INV_FULL, inv_hooks) == ["pre-bash/block-b.sh"]:
            ok("control: a baseline entry whose guard is gone from disk is named")
        else:
            fail("CONTROL DID NOT FIRE: A's first arm (guard gone from tree) proves nothing")
        if not inv_missing(FIXTURE_INV_SHORT, inv_hooks):
            ok("control: a baseline entry whose guard still exists is not flagged")
        else:
            fail("CONTROL DID NOT FIRE: an existing guard was wrongly reported as gone")

        # ---- C. the anti-vacuity FLOOR cannot be removed ------------------
        harnesses = []
        for source in case_sources:
            text = (root / source).read_text(encoding="utf-8", errors="replace")
            if HARNESS_RE.search(text):
                harnesses.append((source, text))
        if not harnesses:
            fail(
                "C. no declared case source folds an external PASS count, so the floor rule "
                "audits NOTHING. Either the folding suite left $SCOPE's case_sources or it "
                "stopped folding; both need saying out loud."
            )
        for source, text in harnesses:
            if FLOOR_LINE not in text:
                fail(
                    "%s lost its selftest minimum-count FLOOR. Without it a module whose "
                    "--selftest prints nothing and exits 0 counts as a passing suite, which "
                    "is how 36 orphaned controls hid for months." % os.path.basename(source)
                )
            else:
                ok("the selftest loop enforces a minimum control count")

        for source, text in harnesses:
            unfloored = floorcheck(text)
            if unfloored:
                fail(
                    "%s folds an external PASS count with NO minimum at line(s): %s"
                    % (os.path.basename(source), "".join("%d " % n for n in unfloored))
                )
                note(
                    "     A fold with no floor counts a selftest that printed nothing as a passing"
                )
                note("     suite. That is how 36 orphaned controls hid for months.")
            else:
                ok("every external PASS fold refuses a count too low to be real")

        if not floorcheck(FIXTURE_FLOORED):
            ok("control: a floored fold is not reported")
        else:
            fail("CONTROL DID NOT FIRE: a correctly floored fold was reported as unfloored")
        if not floorcheck(FIXTURE_FLOORED_LITERAL):
            ok("control: a literal minimum counts as a floor")
        else:
            fail("CONTROL DID NOT FIRE: a literal '-lt 12' floor was reported as unfloored")
        if not floorcheck(FIXTURE_FLOORED_ZERO):
            ok("control: a zero-count refusal counts as a floor")
        else:
            fail("CONTROL DID NOT FIRE: a '-gt 0' refusal was reported as unfloored")
        if floorcheck(FIXTURE_UNFLOORED):
            ok("control: an unfloored fold is detected")
        else:
            fail(
                "CONTROL DID NOT FIRE: an unfloored fold went unnoticed, so the check above "
                "proves nothing"
            )

        # CONTROL, by construction: strip the floor from a copy and require the check to notice. Built by DELETION of a line that is present, not by pattern substitution, so it cannot silently produce an identical copy.
        for _source, text in harnesses:
            stripped = "\n".join(line for line in text.split("\n") if FLOOR_LINE not in line)
            if FLOOR_LINE in stripped:
                fail("CONTROL IS VACUOUS: the floor line survived its own removal")
            else:
                ok("CONTROL: the floor line is detectable, so its absence would be caught")

    print()
    if fails == 0:
        print(
            "✓ hook integrity: %d guard(s) present across %d chain(s), none newly uncovered."
            % (len(on_disk), len(guard_dirs))
        )
        print("  Blind spot, stated so a green is not read as more than it is: this counts")
        print("  CASES, not their quality. A guard whose two cases are both trivial passes")
        print("  here; only reading them catches that.")
        return 0
    print("✗ hook integrity: %d failure(s)." % fails)
    return 1


# --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------


def selftest() -> int:
    """Both directions for the coverage reader, the floor reader and both arms of A.

    The negative controls carry the weight: a reader that says yes to everything passes every positive case, and the twin's own suite is built around exactly that worry.
    """
    ctl = Controls("hook-integrity", floor=28, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = build_fixture_hooks(pathlib.Path(tmp))
        spec = mkspec(str(tmpdir / "hooks"), [str(tmpdir / "suite.sh")], ["pre-bash", "pre-edit"])
        fixture = {key: (b, a) for key, b, a in covmap(spec)}

        ctl.check(
            "PLANT: a guard with both directions reads covered",
            lookup(fixture, "pre-bash/block-fixture-both.sh"),
            (1, 1),
        )
        ctl.check(
            "PLANT: a block-only guard reads block=1 allow=0",
            lookup(fixture, "pre-bash/block-fixture-blockonly.sh"),
            (1, 0),
        )
        ctl.check(
            "PLANT: a pre-edit guard covered via check_out is seen",
            lookup(fixture, "pre-edit/block-fixture-editchain.sh"),
            (1, 1),
        )
        ctl.check(
            "PLANT: helper-driven cases are counted",
            lookup(fixture, "pre-bash/block-fixture-helper.sh"),
            (1, 1),
        )
        ctl.check(
            "MIRROR: a guard with no cases reads 0/0",
            lookup(fixture, "pre-bash/block-fixture-nothing.sh"),
            (0, 0),
        )

        # A guard file that EXISTS with no cases must appear in the map at 0/0, which is different from being absent from it.
        (tmpdir / "hooks" / "pre-bash" / "block-fixture-uncovered.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
        )
        fixture = {key: (b, a) for key, b, a in covmap(spec)}
        ctl.check(
            "MIRROR: an uncovered guard is LISTED at 0/0, not omitted",
            lookup(fixture, "pre-bash/block-fixture-uncovered.sh"),
            (0, 0),
        )
        ctl.truthy(
            "and it really is in the map",
            "pre-bash/block-fixture-uncovered.sh" in fixture,
        )

        # A dedicated test file counts as both directions.
        (tmpdir / "hooks" / "pre-bash" / "test-block-fixture-blockonly.py").write_text(
            "", encoding="utf-8"
        )
        fixture = {key: (b, a) for key, b, a in covmap(spec)}
        ctl.check(
            "PLANT: a dedicated test file adds one to BOTH directions",
            lookup(fixture, "pre-bash/block-fixture-blockonly.sh"),
            (2, 1),
        )

        # THE UNDERSCORE SPELLING a Python port produces. `block[-_]*` covers it;
        # a reader anchored on the hyphen would inventory it and never ask it for a direction.
        (tmpdir / "hooks" / "pre-bash" / "block_ported.py").write_text("", encoding="utf-8")
        fixture = {key: (b, a) for key, b, a in covmap(spec)}
        ctl.truthy(
            "PLANT: a `block_x.py` guard is seen by the coverage reader",
            "pre-bash/block_ported.py" in fixture,
        )

        # -- mkspec: an ABSOLUTE tail ignores the root ----------------------
        ctl.check(
            "mkspec joins a relative tail under the root",
            mkspec("/r", ["s.sh"], ["d"])["dirs"]["d"],
            "/r/d",
        )
        ctl.check(
            "mkspec lets an ABSOLUTE tail through unchanged, which the fixtures need",
            mkspec("/r", ["s.sh"], ["/abs/d"])["dirs"]["/abs/d"],
            "/abs/d",
        )

        # -- inventory arms, both directions --------------------------------
        ctl.check(
            "MIRROR: a complete inventory reports nothing unlisted",
            inv_unlisted(FIXTURE_INV_FULL, FIXTURE_INV_FULL),
            [],
        )
        ctl.check(
            "PLANT: a guard on disk but absent from the inventory is named",
            inv_unlisted(FIXTURE_INV_SHORT, FIXTURE_INV_FULL),
            ["pre-bash/block-b.sh"],
        )
        inv_hooks = tmpdir / "inv-hooks"
        (inv_hooks / "pre-bash").mkdir(parents=True, exist_ok=True)
        (inv_hooks / "pre-bash" / "block-a.sh").write_text("x\n", encoding="utf-8")
        ctl.check(
            "PLANT: a baseline entry whose guard is gone from disk is named",
            inv_missing(FIXTURE_INV_FULL, inv_hooks),
            ["pre-bash/block-b.sh"],
        )
        ctl.check(
            "MIRROR: a baseline entry whose guard still exists is not flagged",
            inv_missing(FIXTURE_INV_SHORT, inv_hooks),
            [],
        )

        # -- the floor reader, four spellings -------------------------------
        ctl.check("MIRROR: a floored fold is not reported", floorcheck(FIXTURE_FLOORED), [])
        ctl.check(
            "MIRROR: a literal minimum counts as a floor",
            floorcheck(FIXTURE_FLOORED_LITERAL),
            [],
        )
        ctl.check(
            "MIRROR: a zero-count refusal counts as a floor",
            floorcheck(FIXTURE_FLOORED_ZERO),
            [],
        )
        ctl.check(
            "PLANT: an unfloored fold is detected, by line number",
            floorcheck(FIXTURE_UNFLOORED),
            [2],
        )
        ctl.check(
            "MIRROR: `PASS + 1` is a single case and needs no floor",
            floorcheck("PASS=$((PASS + 1))\n"),
            [],
        )
        ctl.check(
            "PLANT: a refusal THIRTEEN lines back is out of the window",
            floorcheck('[ "$n" -lt "$floor" ]\n' + "x\n" * 12 + "PASS=$((PASS + n))\n"),
            [14],
        )

        # -- the scope reader refuses every malformed shape ------------------
        scope_file = tmpdir / "scope.json"
        scope_file.write_text(
            json.dumps({"ok": ["a"], "empty": [], "notlist": "a", "blank": [""], "num": [1]}),
            encoding="utf-8",
        )
        ctl.check("a well-formed list is returned", scope_list(scope_file, "ok"), ["a"])
        for key in ("empty", "notlist", "blank", "num", "absent"):
            ctl.raises(
                "PLANT: the scope reader refuses %r rather than degrading" % key,
                ScopeError,
                scope_list,
                scope_file,
                key,
            )
        bad = tmpdir / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        ctl.raises(
            "PLANT: an unreadable scope file refuses",
            ScopeError,
            scope_list,
            bad,
            "guard_dirs",
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
