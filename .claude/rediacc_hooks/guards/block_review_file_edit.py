"""Refuse an Edit, Write, MultiEdit or NotebookEdit of a per-commit review record under `agent/reviews/`.

WHY (agent/plans/PLAN-per-commit-review.md section 6; operator ruling 2026-10-02). A review file is the record a haiku reviewer wrote about one commit, and an open finding at or above `block_at` refuses the branch's push. A hand edit is the one way to make that refusal disappear without fixing anything: downgrade `[high]` to `[low]`, rewrite the claim, or type a Resolution line. The file's `Body-Sig`
catches an edited severity or claim, but anyone can recompute a signature that has no secret, so this guard is the real protection. The only writers are the reviewer itself (`.claude/hooks/stop/wl_review.py`) and `worklist.py --review-mark`, which validates the fix sha, the evidence or the deferral item before it touches the single Resolution line. Both write through Python, which no tool guard sees.

THE SHELL HALF is `block_review_file_shell_write` (pre-bash): redirections, `tee`, `sed -i`, `cp`/`mv` onto the directory and interpreter one-liners that open a review file for writing. A guard declares one chain, so the plan's single guard is two modules.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_review_file_edit.py` beside it and against its own DEFECT, never against a golden.
"""

import re

from rediacc_hooks import hookio
from rediacc_hooks.guards import _cases

__getattr__ = _cases.lazy("block_review_file_edit", "EDGE_CASES")

CHAIN = "pre-edit"
OWN_SUITE = True
ORDER = 14

# The path test is the whole guard: with it gone every review file is editable by hand.
DEFECT = ("if REVIEW_PATH.search(path) is None:", "if True:")

REVIEW_PATH = re.compile(r"(\A|/)agent/reviews/")

MESSAGE = (
    "BLOCKED: %s of a per-commit review record (%s).\n"
    "\n"
    "Review files are written by the reviewer and closed only through the verb, which checks\n"
    "the fix before it records it. A hand edit is how a high finding disappears without a fix.\n"
    "\n"
    "  close a finding:  .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> fixed <sha>\n"
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> not-a-bug <evidence path:line>\n"
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> waived #<item> ASKED:<YYYY-MM-DDTHH:MM>Z\n"
    "  re-review:        python3 .claude/hooks/stop/wl_review.py --run <sha> --branch <branch>\n"
)


def run(ev):
    given = ev.first(("tool_input", "file_path"), ("tool_input", "notebook_path"))
    if not given or given == "null":
        return hookio.ALLOW
    # Judged where the write LANDS (review 3f53e99e.1 sweep): `agent/x/../reviews/...` and a directory symlink into the review directory were allowed as typed, and `agent/reviews/../notes/a.md` was refused. `hookio.landing` is the one reading every pre-edit guard shares (9c6817f3.8).
    path = hookio.landing(given, ev.field("cwd") or None)[0]
    if REVIEW_PATH.search(path) is None:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % (ev.field("tool_name") or "a write", given))
    return hookio.DENY
