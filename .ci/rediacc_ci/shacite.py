"""How a short sha is WRITTEN into a citation, and how a reader tells a cited sha from a date.

THE DEFECT THIS EXISTS FOR (#0241c97d, after #e9852315 and 63e725da1). Every reader of plan and tick citations (`check_plan_citations.citations`, `wl_planrec.launder`, `plan_lifecycle.unfenced_tokens`) skips an ALL-DIGIT hex token, because `[0-9a-f]{7,40}` also matches a CI run id, a date and an issue number. A sha's 9-character abbreviation is all decimal digits with probability (10/16)^9, about 1 in 69, so a real `commit:<sha9>` citation was invisible that often: never judged, never laundered, never remapped.

TWO HALVES, and both are needed:

  * READ. `commit_cited(text, start)` says whether the token at `start` is written in the `commit:<sha>` form a tick or a plan uses to name a commit. That prefix is a claim that the token IS a commit, so a reader judges it even when it is all digits. An unprefixed digit run stays skipped: it is still far more often a run id or a date than an object.
  * WRITE. `citable_token(full, short)` lengthens an all-digit abbreviation along the full sha until it carries a letter, so a token any writer puts into a citation is one every reader reads, including the readers that know nothing of the prefix. `lengthen_commit_refs(text, expand)` applies it to every all-digit `commit:<sha>` in a piece of tick evidence.

ONE COPY, stdlib only. `.ci` imports it as `rediacc_ci.shacite`; the Stop hook reaches it through `wl_gh.import_ci` (the scoped `rediacc_hooks.syspath.import_from_ci` loader), the precedent `wl_gh` set for `rediacc_ci.core.gh_retry`. Nothing here may import beyond the standard library, because the hook side loads it with `.ci` on sys.path only for the duration of the import.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

#: The citation form a tick and a plan use to name a commit: `commit:<sha>`.
COMMIT_PREFIX = "commit:"

#: Every `commit:<sha>` in a text. The same shape as `worklist.COMMIT_REF_RE`, which the tick verb validates with; `test_shacite.py` holds the two equal, so the writer here and the validator there cannot disagree about which tokens are refs.
COMMIT_REF_RE = re.compile(r"(?<![\w-])commit:([0-9a-fA-F]{7,40})(?![\w])")

# The prefix ending exactly where a token starts, preceded by nothing word-like, so `nocommit:` or `xcommit:` never licenses a digit run.
_PREFIX_TAIL_RE = re.compile(r"(?:\A|[^\w-])commit:\Z")


def commit_cited(text: str, start: int) -> bool:
    """Is the token beginning at `text[start]` written as `commit:<token>`?

    Read on a slice rather than with a lookbehind at `pos`, so the answer depends only on the characters before `start` and never on how a caller's regex was anchored.
    """
    if start < len(COMMIT_PREFIX):
        return False
    return bool(_PREFIX_TAIL_RE.search(text[max(0, start - len(COMMIT_PREFIX) - 1) : start]))


def skip_as_number(text: str, start: int, token: str) -> bool:
    """True when a reader should skip `token` as a date, run id or issue number rather than judge it as a git object: it is all digits AND it is not written as `commit:<token>`."""
    return token.isdigit() and not commit_cited(text, start)


def citable_token(full: str, short: str) -> str:
    """`short` lengthened along `full` until it carries a letter, so a token a writer puts into a citation is one every reader of it will read.

    A `short` that already carries a letter is returned unchanged. An all-digit `full` (which no reader can tell from a number) is returned whole.
    """
    if not short.isdigit():
        return short
    return next(
        (full[:n] for n in range(len(short) + 1, len(full) + 1) if not full[:n].isdigit()), full
    )


def lengthen_commit_refs(text: str, expand: Callable[[str], str]) -> str:
    """`text` with every all-digit `commit:<sha>` rewritten through `citable_token`.

    `expand(token)` returns the full sha the token names, or "" when it names none; a token that does not expand, or whose expansion does not start with it, is left exactly as written, so the validator that runs on the text still sees (and refuses) what the author typed. Every other byte of `text` is untouched.
    """

    def one(m: re.Match[str]) -> str:
        tok = m.group(1)
        if not tok.isdigit():
            return m.group(0)
        full = (expand(tok) or "").strip().lower()
        if not full.startswith(tok):
            return m.group(0)
        return COMMIT_PREFIX + citable_token(full, tok)

    return COMMIT_REF_RE.sub(one, text or "")


__all__ = [
    "COMMIT_PREFIX",
    "COMMIT_REF_RE",
    "citable_token",
    "commit_cited",
    "lengthen_commit_refs",
    "skip_as_number",
]
