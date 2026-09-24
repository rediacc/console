"""The Stop hook's duplication cache must watch exactly what the counter reads.

`.claude/hooks/stop/wl_shapedup.py` hashes mtime+size over `CORPUS_GLOBS` to decide whether `scripts/gates/check-shape-duplication.ts` needs re-running, and the counter reads `FAMILIES`. The two are separate literals in different languages, and nothing made them agree.

WHY DRIFT HERE IS SILENT AND ONE-SIDED. If the signature is NARROWER than the counter's corpus, editing a file the counter reads does not move the hash, the hook serves a CACHED verdict, and the rule is quietly answering about the tree as it was. That is worse than a stale answer being late: `wl_shapedup.py`'s own header claims "any edit moves it, so this can make the rule LATE by
nothing and can never silently switch it off", and a narrower signature makes that claim false. Wider is merely wasteful -- the counter re-runs when it need not.

MEASURED 2026-09-08. A sweep for extension-shaped `.sh` matchers flagged the signature as missing the Python half; it was not, because the counter's `FAMILIES` is bash-only too. The finding was conditional on a widening that was measured (62 new shapes at 3+ copies, one of them sixteen copies of the shared entry-point scaffold) and then REVERTED, because landing that red on a
shared tree is a wave rather than a line. So the two lists are correct today and will be wrong the moment one of them moves alone -- which is exactly what this pins.
"""

import re

from rediacc_ci import paths

# `scripts/gates/`, NOT `scripts/`. Written flat this file could not open the counter at all and BOTH tests below died in `_families` with FileNotFoundError -- a drift control that cannot read its own subject, which is a gate that never ran rather than a gate that passed. The docstring above already spelled the right path.
COUNTER = paths.from_root("scripts", "gates", "check-shape-duplication.ts")
HOOK = paths.from_root(".claude", "hooks", "stop", "wl_shapedup.py")


def _families() -> set[str]:
    # THE GATE PROFILE'S CORPUS, after agent/plans/PLAN-stop-hook-refactor-enforcement.md Commit 2's profile split: `PROFILES.gate.families` references this SAME `FAMILIES` constant by name rather than inlining a second array literal, so a text scan for `const FAMILIES = [...]` still finds the whole gate profile's pathspecs. Commit 3's `advisory` profile has its own named constant, `ADVISORY_FAMILIES`, pinned against the hook's `CORPUS_GLOBS_WIDE` by the companion test below with the same pattern, so each tier's signature watches exactly the profile it runs and the counter never scans anything the Stop hook does not also watch for staleness, whatever profile is asking.
    #
    # THE LITERAL GREW A TYPE AND A FLOOR on 2026-09-08 -- `const FAMILIES: readonly
    # Family[] = [{ pathspec: '...', floor: N }, ...]` -- and this pattern, written
    # against the bare `const FAMILIES = [`, stopped matching. It did not go quiet: the
    # `assert m` below fired by name, which is the whole reason it is an assert and not an `if m:`. The annotation is optional in the pattern so either spelling matches.
    m = re.search(
        r"const FAMILIES(?:\s*:[^=]+)?\s*=\s*\[(.*?)\];",
        COUNTER.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert m, "FAMILIES literal not found in %s" % paths.relative_to_root(COUNTER)
    # BOTH QUOTE STYLES, learned the hard way on 2026-09-08: a `prettier --write` run
    # with no repo config (there is none) rewrites this file's literals to double quotes,
    # and a single-quote-only pattern then returns an EMPTY set -- which would have made the equality below hold for the worst possible reason had the non-empty test not caught it first. Reading either spelling costs nothing and removes the trap.
    return set(re.findall(r"[\'\"]([^\'\"]+)[\'\"]", m.group(1)))


def _corpus_globs() -> set[str]:
    m = re.search(r"CORPUS_GLOBS = \((.*?)\)", HOOK.read_text(encoding="utf-8"), re.DOTALL)
    assert m, "CORPUS_GLOBS literal not found in %s" % paths.relative_to_root(HOOK)
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def _advisory_families() -> set[str]:
    # THE WIDE TIER'S HALF (Commit 3). `const ADVISORY_FAMILIES` and not a looser `FAMILIES` pattern: the narrow regex above must keep matching only the gate's literal, and this one only the advisory one, or the two equalities could each pass against the other's list.
    m = re.search(
        r"const ADVISORY_FAMILIES(?:\s*:[^=]+)?\s*=\s*\[(.*?)\];",
        COUNTER.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert m, "ADVISORY_FAMILIES literal not found in %s" % paths.relative_to_root(COUNTER)
    return set(re.findall(r"[\'\"]([^\'\"]+)[\'\"]", m.group(1)))


def _corpus_globs_wide() -> set[str]:
    m = re.search(r"CORPUS_GLOBS_WIDE = \((.*?)\)", HOOK.read_text(encoding="utf-8"), re.DOTALL)
    assert m, "CORPUS_GLOBS_WIDE literal not found in %s" % paths.relative_to_root(HOOK)
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def test_the_cache_signature_watches_exactly_what_the_counter_reads():
    families, globs = _families(), _corpus_globs()
    missing = sorted(families - globs)
    extra = sorted(globs - families)
    assert not missing, (
        "the Stop hook's CORPUS_GLOBS does not watch %s, which the counter READS: an "
        "edit to one of those files leaves the signature unchanged and the hook serves a "
        "STALE duplication verdict" % missing
    )
    assert not extra, (
        "the Stop hook watches %s, which the counter does not read: harmless but it "
        "re-runs a 1.1s counter for nothing, and it means the two lists have drifted" % extra
    )


def test_both_literals_are_non_empty():
    """The anti-vacuity half. If either regex stopped matching -- a rename, a reformat, a move to a different quoting style -- both sides would come back as empty sets and the equality above would hold for the worst possible reason.

    THE FLOOR IS 3 SINCE W7 P6, which ported the last `.claude/hooks/pre-bash/block-*.sh` and deleted that family from both lists. It is a floor on the PARSE, not a target for the estate: three is what the two literals hold today, so a regex that stopped matching still comes back below it.
    """
    assert len(_families()) >= 3
    assert len(_corpus_globs()) >= 3


def test_the_wide_signature_watches_exactly_what_the_advisory_profile_reads():
    """Risk 7 of agent/plans/PLAN-stop-hook-refactor-enforcement.md, for the wide tier: the same exact equality in both directions, for the same reason as the gate profile's. A narrower wide signature serves a stale advisory verdict; a wider one means the two lists have drifted."""
    families, globs = _advisory_families(), _corpus_globs_wide()
    missing = sorted(families - globs)
    extra = sorted(globs - families)
    assert not missing, (
        "the Stop hook's CORPUS_GLOBS_WIDE does not watch %s, which the advisory profile "
        "READS: an edit to one of those files leaves the wide signature unchanged and the "
        "hook serves a STALE advisory verdict" % missing
    )
    assert not extra, (
        "the Stop hook's CORPUS_GLOBS_WIDE watches %s, which the advisory profile does not "
        "read: the two lists have drifted" % extra
    )


def test_the_two_tiers_are_parsed_apart():
    """The anti-vacuity half for the wide tier, and the proof that each regex found its OWN literal: both wide lists parse non-empty, and neither narrow list shares a pathspec with them. A narrow regex that had started matching the wide tuple, or the reverse, would make one equality compare a list with itself."""
    assert len(_advisory_families()) >= 4
    assert len(_corpus_globs_wide()) >= 4
    assert not (_corpus_globs() & _corpus_globs_wide())
    assert not (_families() & _advisory_families())
