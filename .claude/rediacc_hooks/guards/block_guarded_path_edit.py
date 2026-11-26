"""Refuse an Edit, Write, MultiEdit or NotebookEdit that lands on a path one of the path-judged rows of `_write_rules.ROWS` protects: a per-commit review record, the live-proof ledger, or (by a whole-file write) a pr-babysit round log.

ONE GUARD PER CHAIN (PLAN-tooling-code-reduction CR5, D5). Three pre-edit guards (`block_review_file_edit`, `block_live_proof_ledger_write`, `block_roundlog_write`) were each one `_write_rules.edit_run(ev, RULE)` call over one row. They are one guard now, reading the three rows in turn; their pre-bash halves (`block_review_file_shell_write`, `block_live_proof_ledger_shell_write`, `block_roundlog_truncate`) are unchanged, and each still reads the same row. The three landing tests are disjoint, so at most one row can refuse a given write, and the refusal is the row's own text.

THE OLD STEMS' HISTORY. The CR7 fire ledger keys a refusal by the refusing guard's stem, so a row written before the merge names one of the three old stems. `guards.RENAMED` maps each to this stem, and the committed snapshot `.ci/config/hook-ledger.json` carries their counts folded into this guard's entry.

THE REVIEW RECORD ROW (agent/plans/PLAN-per-commit-review.md section 6; operator ruling 2026-10-02). A review file is the record a haiku reviewer wrote about one commit, and an open finding at or above `block_at` refuses the branch's push. A hand edit is the one way to make that refusal disappear without fixing anything: downgrade `[high]` to `[low]`, rewrite the claim, or type a Resolution line. The file's `Body-Sig`
catches an edited severity or claim, but anyone can recompute a signature that has no secret, so this row is the real protection. The only writers are the reviewer itself (`.claude/hooks/stop/wl_review.py`) and `worklist.py --review-mark`, which validates the fix sha, the evidence or the deferral item before it touches the single Resolution line. Both write through Python, which no tool guard sees.

THE LIVE-PROOF LEDGER ROW (agent/plans/PLAN-tested-on-bench.md box V10; review findings 2a2941c4.1 and 2a2941c4.5). CI judges `agent/ledgers/live-proof.jsonl` with no secrets and no network, and the gate's LP5 checks only that a row's `id` hashes to its content, so a hand-written row with a recomputed id and `status: VERIFIED` passes it. The one writer is the recorder, `python3 -m rediacc_ci.ops.live_proof record --write`, which
appends a row only after the run it describes and keeps the run's log whose digest the row carries. The recorder writes through Python, which no tool guard sees; every tool write is a hand write and is refused.

THE ROUND LOG ROW. A round log is three parts in a fixed order: an immutable wave header, a STATUS block overwritten in place every round, and the round history appended below it forever. Refreshing STATUS is therefore a SPLICE, and the obvious splice is wrong in a way that looks right:

    text[:i] + new        # i = index of "## STATUS"

That replaces from the STATUS heading to END OF FILE, taking the entire history appendix with it. On 2026-08-19 a heartbeat tick did exactly this, silently, to a file with no backup. `worklist.py --roundlog` cannot express that splice: it replaces only the middle and prints the bytes it kept on either side, and it stamps the time itself, because STATUS's timestamp is what a watchdog reads to decide whether the loop is wedged.

Only WHOLE-FILE writes are refused there. The round log has a single owner, and two of its three parts are meant to be written by hand: the history appendix is appended to forever, and the wave header takes dated addenda. A targeted Edit carries an exact old_string, so it either matches or fails loudly and cannot swallow an appendix it never named; Write and NotebookEdit are denied, Edit and MultiEdit pass (the row's `passes`). A briefing (`pr-babysit-<branch>-briefing.md`) has its own contract and is the row's `exempt`. CREATING a log is not truncating one: a file that does not exist has no appendix to swallow, and `worklist.py --roundlog` refuses to create a log, so without `exists_only` the two halves of the contract deadlocked (walked head-on on 2026-08-27).

Every row is judged where the write LANDS: `hookio.landing` resolves symlinks, then `..`, as the kernel does (#bc7d998c, review 9c6817f3.1-.4, .8).

THE PLANTS. Each row keeps the plant its own guard carried. The DEFECT is the round log's (without `exists_only` a log is refused at its creation, which the suite and the golden must catch); MUTANTS swap the review and ledger rows for `_write_rules.NOTHING`, the row no path matches. `test-block_guarded_path_edit.py` runs every row's cases and requires each plant to turn at least one case of its own row.

THE ROUND LOG FIXTURE. Its existence test reads a path the PAYLOAD names, so the DENY branch needs a real file at a path the edge case spells literally. The builder in tests/guard_cases writes a DETERMINISTIC directory under the system temp dir, and `ENVS` names it through a variable this guard never reads, whose only job is to make the harness build the world before the cases run.
"""

from rediacc_hooks import hookio
from rediacc_hooks.guards import _write_rules, tables

__getattr__ = tables(
    "block_guarded_path_edit",
    "EDGE_CASES",
    "ENVS",
    "FIXTURES",
    "EXISTING_BRIEFING",
    "EXISTING_LOG",
    "MISSING_LOG",
    "WORLD",
    "_round_log_world",
)

CHAIN = "pre-edit"
ORDER = 9

DEFECT = (
    "return _write_rules.edit_run(ev, ROUNDLOG, exists_only=True, raw=False)",
    "return _write_rules.edit_run(ev, ROUNDLOG, exists_only=False, raw=False)",
)
# With its row swapped for NOTHING, every review file (every ledger write) is editable by hand.
MUTANTS = {
    "review_file": (
        'REVIEW_FILE = _write_rules.ROWS["review_file"]',
        "REVIEW_FILE = _write_rules.NOTHING",
    ),
    "live_proof_ledger": (
        'LIVE_PROOF_LEDGER = _write_rules.ROWS["live_proof_ledger"]',
        "LIVE_PROOF_LEDGER = _write_rules.NOTHING",
    ),
}

# The paths, the refusals, the passed tools and the sanctioned writers are rows of `_write_rules.ROWS`, shared with the shell halves.
REVIEW_FILE = _write_rules.ROWS["review_file"]
LIVE_PROOF_LEDGER = _write_rules.ROWS["live_proof_ledger"]
ROUNDLOG = _write_rules.ROWS["roundlog"]
if ROUNDLOG.path is None:
    raise RuntimeError("the roundlog row of _write_rules.ROWS names no path")
LEDGER_REL = "agent/ledgers/live-proof.jsonl"


def run(ev):
    for rule in (REVIEW_FILE, LIVE_PROOF_LEDGER):
        if _write_rules.edit_run(ev, rule) != hookio.ALLOW:
            return hookio.DENY
    return _write_rules.edit_run(ev, ROUNDLOG, exists_only=True, raw=False)
