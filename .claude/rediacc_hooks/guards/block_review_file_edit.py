"""Refuse an Edit, Write, MultiEdit or NotebookEdit of a per-commit review record under `agent/reviews/`.

WHY (agent/plans/PLAN-per-commit-review.md section 6; operator ruling 2026-10-02). A review file is the record a haiku reviewer wrote about one commit, and an open finding at or above `block_at` refuses the branch's push. A hand edit is the one way to make that refusal disappear without fixing anything: downgrade `[high]` to `[low]`, rewrite the claim, or type a Resolution line. The file's `Body-Sig`
catches an edited severity or claim, but anyone can recompute a signature that has no secret, so this guard is the real protection. The only writers are the reviewer itself (`.claude/hooks/stop/wl_review.py`) and `worklist.py --review-mark`, which validates the fix sha, the evidence or the deferral item before it touches the single Resolution line. Both write through Python, which no tool guard sees.

THE SHELL HALF is `block_review_file_shell_write` (pre-bash): redirections, `tee`, `sed -i`, `cp`/`mv` onto the directory and interpreter one-liners that open a review file for writing. A guard declares one chain, so the plan's single guard is two modules.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_review_file_edit.py` beside it and against its own DEFECT, never against a golden.
"""

import re

from rediacc_hooks import hookio

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
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> deferred #<item>\n"
    "  re-review:        python3 .claude/hooks/stop/wl_review.py --run <sha> --branch <branch>\n"
)

EDGE_CASES = [
    (
        "a Write over a review file",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/agent/reviews/0930-1/%s.md" % ("a" * 40),
                "content": "x",
            },
        },
    ),
    (
        "an Edit of a review file",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "agent/reviews/0930-1/x.md",
                "old_string": "[high]",
                "new_string": "[low]",
            },
        },
    ),
    (
        "a MultiEdit of a review file",
        {
            "tool_name": "MultiEdit",
            "tool_input": {"file_path": "agent/reviews/b/x.md", "edits": []},
        },
    ),
    (
        "a NotebookEdit naming a review path",
        {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "agent/reviews/b/x.md"}},
    ),
    (
        "a plan that mentions the directory",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "agent/plans/PLAN-x.md", "content": "agent/reviews/"},
        },
    ),
    (
        "a sibling directory with a similar name",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "agent/reviews-old/x.md", "content": "x"},
        },
    ),
    (
        "a file called reviews elsewhere",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "docs/agent/reviewsx.md", "new_string": "x"},
        },
    ),
    ("no path", {"tool_name": "Write", "tool_input": {"content": "x"}}),
]


def run(ev):
    path = ev.first(("tool_input", "file_path"), ("tool_input", "notebook_path"))
    if not path or path == "null":
        return hookio.ALLOW
    if REVIEW_PATH.search(path) is None:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % (ev.field("tool_name") or "a write", path))
    return hookio.DENY
