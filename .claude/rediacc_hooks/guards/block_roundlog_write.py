"""Deny WHOLE-FILE tool writes to a pr-babysit ROUND LOG. Targeted edits pass.

WHY THIS EXISTS. The round log is three parts in a fixed order: an immutable
wave header, a STATUS block overwritten in place every round, and the round
history appended below it forever. Refreshing STATUS is therefore a SPLICE,
and the obvious splice is wrong in a way that looks right:

    text[:i] + new        # i = index of "## STATUS"

That replaces from the STATUS heading to END OF FILE, taking the entire
history appendix with it. On 2026-08-19 a heartbeat tick whose whole purpose
was keeping the log current did exactly this, and there was no backup of that
file anywhere. The loss was silent: the write succeeded, the new STATUS looked
perfect, and nothing said the appendix had gone.

`worklist.py --roundlog` cannot express that splice. It parses the document
into (head, status, tail), replaces only the middle, and prints the byte count
of what it kept on either side, so a truncation can never again pass for a
routine update. It also stamps the time itself, which matters more than it
sounds: STATUS's timestamp is the signal a watchdog reads to decide whether
the loop is wedged, and a hand-typed stamp can be copied forward from the
previous round without anything noticing.

WHY ONLY WHOLE-FILE WRITES, AND NOT EVERY EDIT. This is the one place this
guard deliberately differs from block-agent-state-shape.sh next door. STATE.md
has MERGE semantics across concurrent sessions, so every direct write to it is
unsafe and the CLI is its only writer. The round log has a single owner, and
two of its three parts are meant to be written by hand: the history appendix
is appended to forever, and the wave header takes dated addenda. Denying those
would leave legitimate work with no path at all, which is how a guard teaches
people to route around it.

The failure being prevented is specifically SILENT TRUNCATION, and only a
whole-file replacement can do that silently. A targeted Edit carries an exact
old_string: it either matches what is there or it fails loudly, and it cannot
quietly swallow a 5 KB appendix it never mentioned. So Write and NotebookEdit
are denied, Edit and MultiEdit are allowed through.

SCOPED TO ROUND LOGS, NOT BRIEFINGS. `pr-babysit-<branch>-briefing.md` is a
different artifact with a different contract (immutable once the babysitter is
running; superseded by a NEW file, never rewritten). The verb does not handle
briefings, so they are left to their own rule rather than blocked here with
nothing offered in return.

FAILS OPEN by design, like its neighbour: anything this pattern does not
recognise is allowed through rather than blocked on a guess.

PORT NOTE ON THE ANCHORS. `[[ "$FILE" =~ (^|/)reports/pr-babysit-[^/]+\\.md$ ]]`
is POSIX `regexec` over the whole variable, so `$` is the end of the STRING.
Python's `$` also matches before a trailing newline, so the port writes `\\Z`;
the same reasoning is set out at length in block_agent_state_shape.py.

PORT NOTE ON WHY THIS GUARD NEEDS A FIXTURE AT ALL. Its last test is
`[ -e "$FILE" ]`, a filesystem read of a path the PAYLOAD names, resolved
against the process's own directory. There is no environment variable to point
at a world, and a hook payload is a static string, so the only way to reach the
DENY branch is for a real file to exist at a path the edge case can name
literally. The builder below therefore writes to a DETERMINISTIC directory
under the system temp dir rather than to the random one the harness offers, and
`ENVS` names it through a variable this guard never reads -- the variable's
only job is to make the harness build the world before the cases run.
"""

import os
import re
import tempfile

from rediacc_hooks import hookio

CHAIN = "pre-edit"
TWIN = "pre-edit/block-roundlog-write.sh"
ORDER = 9

# CREATING one is not truncating one, and without this line the two halves of
# the contract deadlock. Walking the documented path hit it head-on on
# 2026-08-27: `worklist.py --roundlog` refuses to create a log ("This verb
# REPLACES a STATUS block, it does not create a round log ... Write the wave
# header first"), and this guard then refused the write it had just been told
# to make. There was no third door.
DEFECT = (
    "if not os.path.exists(file_path):\n        return hookio.ALLOW",
    "if False:\n        return hookio.ALLOW",
)

# Targeted edits cannot silently truncate; only whole-file writes can.
TARGETED_TOOLS = ("Edit", "MultiEdit")

ROUND_LOG = r"(\A|/)reports/pr-babysit-[^/]+\.md\Z"

MESSAGE = (
    "❌ BLOCKED: a whole-file write to a pr-babysit round log. Its STATUS block is spliced "
    "in place, and the obvious splice (text[:i] + new) deletes the entire round history "
    "below it -- which is what happened on 2026-08-19, silently, to a file with no backup. "
    "To refresh STATUS use the verb, which replaces ONLY that block and reports the bytes "
    "it kept above and below:  .claude/hooks/stop/worklist.py --roundlog <branch> <<'EOF' "
    "... EOF   The tool writes the '## STATUS (round N, <utc>)' heading itself: the round "
    "auto-increments, and the stamp is machine-written because a watchdog reads it to "
    "decide whether this loop is wedged. To append to the history or amend the wave "
    "header, use Edit -- targeted edits are deliberately allowed, because they cannot "
    "swallow an appendix they never named."
)

# A fixed location, named by both the builder and the edge cases below. See the
# port note in the module docstring for why it cannot be the harness's own
# per-session temporary directory.
WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-roundlog")
EXISTING_LOG = "%s/reports/pr-babysit-0831-1.md" % WORLD
MISSING_LOG = "%s/reports/pr-babysit-never-written.md" % WORLD
EXISTING_BRIEFING = "%s/reports/pr-babysit-0831-1-briefing.md" % WORLD


def _round_log_world(_unused):
    """A directory holding one real round log and one real briefing.

    Idempotent: it is a fixed path, so a second run of the suite finds the
    files already there and must not fail on that. The `_unused` argument is
    the per-session directory the harness offers, deliberately ignored.
    """
    reports = os.path.join(WORLD, "reports")
    os.makedirs(reports, exist_ok=True)
    for path in (EXISTING_LOG, EXISTING_BRIEFING):
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("# wave header\n\n## STATUS (round 1, 2026-08-19T00:00:00Z)\n\nx\n")
    return WORLD


FIXTURES = {"roundlog-world": _round_log_world}

# The variable is never read by this guard. It exists so the harness resolves
# the token, which is what builds the world above before any case runs.
ENVS = [("roundlog", {"REDIACC_ROUNDLOG_WORLD": "{FIXTURE:roundlog-world}"}, {})]

EDGE_CASES = [
    (
        "a Write over an existing round log",
        {"tool_name": "Write", "tool_input": {"file_path": EXISTING_LOG, "content": "x"}},
    ),
    (
        "a NotebookEdit over an existing round log",
        {
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": EXISTING_LOG, "new_source": "x"},
        },
    ),
    # Targeted edits are deliberately allowed: they cannot swallow an appendix
    # they never named.
    (
        "an Edit on the same file",
        {"tool_name": "Edit", "tool_input": {"file_path": EXISTING_LOG, "new_string": "x"}},
    ),
    (
        "a MultiEdit on the same file",
        {"tool_name": "MultiEdit", "tool_input": {"file_path": EXISTING_LOG, "edits": []}},
    ),
    # The 2026-08-27 deadlock: creating one is not truncating one.
    (
        "creating a round log that does not exist yet",
        {"tool_name": "Write", "tool_input": {"file_path": MISSING_LOG, "content": "x"}},
    ),
    # A briefing is a different artifact with a different contract.
    (
        "a briefing is not a round log",
        {"tool_name": "Write", "tool_input": {"file_path": EXISTING_BRIEFING, "content": "x"}},
    ),
    (
        "a round log outside a reports/ directory",
        {"tool_name": "Write", "tool_input": {"file_path": "pr-babysit-0831-1.md", "content": "x"}},
    ),
    (
        "an ordinary file in reports/",
        {"tool_name": "Write", "tool_input": {"file_path": "reports/notes.md", "content": "x"}},
    ),
    ("no path and no tool name", {"tool_input": {"new_string": "x"}}),
]


def run(ev):
    file_path = ev.first(("tool_input", "file_path"), ("tool_input", "notebook_path"))
    tool = ev.field("tool_name")

    # Targeted edits cannot silently truncate; only whole-file writes can.
    if hookio.case_glob(tool, *TARGETED_TOOLS):
        return hookio.ALLOW
    if hookio.case_glob(file_path, "*-briefing.md"):
        return hookio.ALLOW
    if re.search(ROUND_LOG, file_path) is None:
        return hookio.ALLOW

    # CREATING one is not truncating one. A file that does not exist has no appendix
    # to swallow, and the failure this guard prevents is specifically the SILENT LOSS
    # of an existing history.
    if not os.path.exists(file_path):
        return hookio.ALLOW

    ev.warn(MESSAGE)
    return hookio.DENY
