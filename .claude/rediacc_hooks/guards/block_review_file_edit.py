"""Refuse an Edit, Write, MultiEdit or NotebookEdit of a per-commit review record under `agent/reviews/`.

WHY (agent/plans/PLAN-per-commit-review.md section 6; operator ruling 2026-10-02). A review file is the record a haiku reviewer wrote about one commit, and an open finding at or above `block_at` refuses the branch's push. A hand edit is the one way to make that refusal disappear without fixing anything: downgrade `[high]` to `[low]`, rewrite the claim, or type a Resolution line. The file's `Body-Sig`
catches an edited severity or claim, but anyone can recompute a signature that has no secret, so this guard is the real protection. The only writers are the reviewer itself (`.claude/hooks/stop/wl_review.py`) and `worklist.py --review-mark`, which validates the fix sha, the evidence or the deferral item before it touches the single Resolution line. Both write through Python, which no tool guard sees.

THE SHELL HALF is `block_review_file_shell_write` (pre-bash): redirections, `tee`, `sed -i`, `cp`/`mv` onto the directory and interpreter one-liners that open a review file for writing. A guard declares one chain, so the plan's single guard is two modules.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_review_file_edit.py` beside it and against its own DEFECT, never against a golden.
"""

from rediacc_hooks.guards import _write_rules, tables

__getattr__ = tables("block_review_file_edit", "EDGE_CASES")

CHAIN = "pre-edit"
OWN_SUITE = True
ORDER = 14

# The row is the whole guard: with the row no path matches, every review file is editable by hand.
DEFECT = ('RULE = _write_rules.ROWS["review_file"]', "RULE = _write_rules.NOTHING")

# The path, the refusal and the sanctioned writers are one row of `_write_rules.ROWS`, shared with the shell half.
RULE = _write_rules.ROWS["review_file"]
REVIEW_PATH = RULE.path
MESSAGE = RULE.message[0]


def run(ev):
    return _write_rules.edit_run(ev, RULE)
