"""The test tables of `block_roundlog_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os
import tempfile

from rediacc_hooks import hookio

# A fixed location, named by both the builder and the edge cases below. See the port note in the module docstring for why it cannot be the harness's own per-session temporary directory.
WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-roundlog")


EXISTING_LOG = "%s/reports/pr-babysit-0831-1.md" % WORLD


MISSING_LOG = "%s/reports/pr-babysit-never-written.md" % WORLD


EXISTING_BRIEFING = "%s/reports/pr-babysit-0831-1-briefing.md" % WORLD


def _round_log_world(_unused):
    """A directory holding one real round log and one real briefing.

    Idempotent: it is a fixed path, so a second run of the suite finds the files already there and must not fail on that. The `_unused` argument is the per-session directory the harness offers, deliberately ignored.
    """
    reports = os.path.join(WORLD, "reports")
    os.makedirs(reports, exist_ok=True)
    for path in (EXISTING_LOG, EXISTING_BRIEFING):
        hookio.write_world_file(
            path, "# wave header\n\n## STATUS (round 1, 2026-08-19T00:00:00Z)\n\nx\n"
        )
    # A directory symlink into the guarded tree (#bc7d998c): a write through it lands in the tree.
    link = os.path.join(WORLD, "linked")
    hookio.ensure_world_symlink(os.path.join(WORLD, "reports"), link)
    return WORLD


FIXTURES = {"roundlog-world": _round_log_world}


# The variable is never read by this guard. It exists so the harness resolves the token, which is what builds the world above before any case runs.
ENVS = [("roundlog", {"REDIACC_ROUNDLOG_WORLD": "{FIXTURE:roundlog-world}"}, {})]


EDGE_CASES = [
    # Judged where the write LANDS (#bc7d998c): each refusal was allowed before.
    (
        "a .. detour onto an existing round log",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "%s/reports/x/../pr-babysit-0831-1.md" % WORLD,
                "content": "x",
            },
        },
    ),
    (
        "a symlink onto an existing round log",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "%s/linked/pr-babysit-0831-1.md" % WORLD, "content": "x"},
        },
    ),
    (
        "a .. detour out of the reports directory",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "%s/reports/../pr-babysit-0831-1.md" % WORLD,
                "content": "x",
            },
        },
    ),
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
    # Targeted edits are deliberately allowed: they cannot swallow an appendix they never named.
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
