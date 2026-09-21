"""The shrink-only baseline DECISION, in one place, for the Python gates.

WHAT IT IS. A shrink-only baseline freezes the debt a gate finds on the day it lands, refuses GROWTH, and is drained rather than reseeded. Two decisions make that work and both are here:

  * `baseline_additions` -- what the new set has that the old one does not.
    COMPOSITION, never a total. A reseed that drains thirty and adds one still
    LOOKS like progress in the totals, which is exactly how a brand new
    violation gets enshrined as permanent invisible debt.
  * `write_verdict` -- whether a `--write-baseline` is allowed at all. ORDER IS
    LOAD-BEARING: the missing-baseline case is decided FIRST, because every
    later rule reads the old set and with no file there is no old set. Deleting
    the baseline is otherwise the cheapest way to switch the whole rule off.

WHY IT IS HERE AND NOT COPIED AGAIN. `scripts/lib/shrink-only-baseline.ts` is the TypeScript original; `.ci/scripts/quality/check_language_policy.py` transliterated the decision half into Python and said so out loud, naming the resulting coverage gap in `gate-test:shrink-only-composition` rather than leaving it to be found. That was correct while the port it would have
collided with was in flight. A SECOND Python copy is not correct, and
`check:ci-shape-duplication` would report the pair, so the decision moves here and both gates call it.

WHAT IS DELIBERATELY NOT HERE: the WORDING of a refusal. `render_refusal` differs per gate because the noun differs (a bash file, a stray path) and so does the remedy (port it, delete it), and a shared message that said neither would be worse than two that each say one. The decision is shared; the sentence is not.
"""


def baseline_additions(old: list[str], new: list[str]) -> list[str]:
    """Ids in the new set that are not in the old one, i.e. the set GREW.

    Order follows `new`, so a caller printing the result shows the additions in the order its own enumeration produced them rather than in sorted order, which is what makes a diff against the file readable.
    """
    known = set(old)
    return [entry for entry in new if entry not in known]


def write_verdict(*, baseline_exists: bool, first_seed: bool, additions: list[str]) -> str | None:
    """The complete `--write-baseline` decision. None means the write is allowed.

    Returns one of `"missing-baseline"`, `"would-grow"`, or None. A STRING rather than an exception because both refusals are ordinary outcomes a gate reports and exits 1 on, not programming errors.
    """
    if not baseline_exists and not first_seed:
        return "missing-baseline"
    if not baseline_exists:
        return None
    return "would-grow" if additions else None


__all__ = ["baseline_additions", "write_verdict"]
