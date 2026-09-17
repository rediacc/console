"""The Stop hook's duplication cache must watch exactly what the counter reads.

`.claude/hooks/stop/wl_shapedup.py` hashes mtime+size over `CORPUS_GLOBS` to decide
whether `scripts/gates/check-shape-duplication.ts` needs re-running, and the counter reads
`FAMILIES`. The two are separate literals in different languages, and nothing made them
agree.

WHY DRIFT HERE IS SILENT AND ONE-SIDED. If the signature is NARROWER than the counter's
corpus, editing a file the counter reads does not move the hash, the hook serves a
CACHED verdict, and the rule is quietly answering about the tree as it was. That is
worse than a stale answer being late: `wl_shapedup.py`'s own header claims "any edit
moves it, so this can make the rule LATE by nothing and can never silently switch it
off", and a narrower signature makes that claim false. Wider is merely wasteful -- the
counter re-runs when it need not.

MEASURED 2026-09-08. A sweep for extension-shaped `.sh` matchers flagged the signature
as missing the Python half; it was not, because the counter's `FAMILIES` is bash-only
too. The finding was conditional on a widening that was measured (62 new shapes at 3+
copies, one of them sixteen copies of the shared entry-point scaffold) and then
REVERTED, because landing that red on a shared tree is a wave rather than a line. So
the two lists are correct today and will be wrong the moment one of them moves alone --
which is exactly what this pins.
"""

import re

from rediacc_ci import paths

# `scripts/gates/`, NOT `scripts/`. Written flat this file could not open the counter at all and BOTH tests below died in `_families` with FileNotFoundError -- a drift control that cannot read its own subject, which is a gate that never ran rather than a gate that passed. The docstring above already spelled the right path.
COUNTER = paths.from_root("scripts", "gates", "check-shape-duplication.ts")
HOOK = paths.from_root(".claude", "hooks", "stop", "wl_shapedup.py")


def _families() -> set[str]:
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
    """The anti-vacuity half. If either regex stopped matching -- a rename, a reformat,
    a move to a different quoting style -- both sides would come back as empty sets and
    the equality above would hold for the worst possible reason."""
    assert len(_families()) >= 4
    assert len(_corpus_globs()) >= 4
