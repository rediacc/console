"""Deny WHOLE-FILE tool writes to a pr-babysit ROUND LOG. Targeted edits pass.

WHY THIS EXISTS. The round log is three parts in a fixed order: an immutable wave header, a STATUS block overwritten in place every round, and the round history appended below it forever. Refreshing STATUS is therefore a SPLICE, and the obvious splice is wrong in a way that looks right:

    text[:i] + new        # i = index of "## STATUS"

That replaces from the STATUS heading to END OF FILE, taking the entire history appendix with it. On 2026-08-19 a heartbeat tick whose whole purpose was keeping the log current did exactly this, and there was no backup of that file anywhere. The loss was silent: the write succeeded, the new STATUS looked perfect, and nothing said the appendix had gone.

`worklist.py --roundlog` cannot express that splice. It parses the document into (head, status, tail), replaces only the middle, and prints the byte count of what it kept on either side, so a truncation can never again pass for a routine update. It also stamps the time itself, which matters more than it sounds: STATUS's timestamp is the signal a watchdog reads to decide whether the
loop is wedged, and a hand-typed stamp can be copied forward from the previous round without anything noticing.

WHY ONLY WHOLE-FILE WRITES, AND NOT EVERY EDIT. This is the one place this guard deliberately differs from block-agent-state-shape.sh next door. STATE.md has MERGE semantics across concurrent sessions, so every direct write to it is unsafe and the CLI is its only writer. The round log has a single owner, and two of its three parts are meant to be written by hand: the history
appendix is appended to forever, and the wave header takes dated addenda. Denying those would leave legitimate work with no path at all, which is how a guard teaches people to route around it.

The failure being prevented is specifically SILENT TRUNCATION, and only a whole-file replacement can do that silently. A targeted Edit carries an exact old_string: it either matches what is there or it fails loudly, and it cannot quietly swallow a 5 KB appendix it never mentioned. So Write and NotebookEdit are denied, Edit and MultiEdit are allowed through.

SCOPED TO ROUND LOGS, NOT BRIEFINGS. `pr-babysit-<branch>-briefing.md` is a different artifact with a different contract (immutable once the babysitter is running; superseded by a NEW file, never rewritten). The verb does not handle briefings, so they are left to their own rule rather than blocked here with nothing offered in return.

FAILS OPEN by design, like its neighbour: anything this pattern does not recognise is allowed through rather than blocked on a guess.

PORT NOTE ON THE ANCHORS. `[[ "$FILE" =~ (^|/)reports/pr-babysit-[^/]+\\.md$ ]]`
is POSIX `regexec` over the whole variable, so `$` is the end of the STRING.
Python's `$` also matches before a trailing newline, so the port writes `\\Z`;
the same reasoning is set out at length in block_agent_state_shape.py.

PORT NOTE ON WHY THIS GUARD NEEDS A FIXTURE AT ALL. Its last test is `[ -e "$FILE" ]`, a filesystem read of a path the PAYLOAD names, resolved against the process's own directory. There is no environment variable to point at a world, and a hook payload is a static string, so the only way to reach the DENY branch is for a real file to exist at a path the edge case can name
literally. The builder below therefore writes to a DETERMINISTIC directory under the system temp dir rather than to the random one the harness offers, and `ENVS` names it through a variable this guard never reads -- the variable's only job is to make the harness build the world before the cases run.
"""

from rediacc_hooks.guards import _write_rules, tables

__getattr__ = tables(
    "block_roundlog_write",
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

# CREATING one is not truncating one, and without `exists_only` the two halves of the contract deadlock. Walking the documented path hit it head-on on 2026-08-27: `worklist.py --roundlog` refuses to create a log ("This verb REPLACES a STATUS block, it does not create a round log ... Write the wave header first"), and this guard then refused the write it had just been told to make.
# There was no third door.
DEFECT = (
    "return _write_rules.edit_run(ev, RULE, exists_only=True, raw=False)",
    "return _write_rules.edit_run(ev, RULE, exists_only=False, raw=False)",
)

# The path, the briefing exemption, the passed tools (Edit and MultiEdit: targeted edits cannot silently truncate; only whole-file writes can) and the refusal are one row of `_write_rules.ROWS`, shared with the shell half.
RULE = _write_rules.ROWS["roundlog"]
TARGETED_TOOLS = RULE.passes
ROUND_LOG = RULE.path.pattern
MESSAGE = RULE.message[0]


def run(ev):
    # The path is judged where the write LANDS: `hookio.landing` resolves symlinks, then `..`, as the kernel does (#bc7d998c, review 9c6817f3.1-.4, .8). CREATING one is not truncating one: a file that does not exist has no appendix to swallow, and the failure this guard prevents is specifically the SILENT LOSS of an existing history.
    return _write_rules.edit_run(ev, RULE, exists_only=True, raw=False)
