"""The test tables of `block_guarded_path_edit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`.

The guard merged the three path-judged edit halves (block_review_file_edit, block_live_proof_ledger_write, block_roundlog_write), so its EDGE_CASES hold the rows of all three; only the round log row needs a world on disk.
"""

import os

from rediacc_hooks import hookio
from rediacc_hooks.tests.fixtures.guards.loader import load_table

# A fixed location, named by both the builder and the edge cases below. See THE ROUND LOG FIXTURE in the guard's docstring for why it cannot be the harness's own per-session temporary directory.
WORLD = hookio.golden_world("rediacc-guard-roundlog")


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
ENVS: list = [("roundlog", {"REDIACC_ROUNDLOG_WORLD": "{FIXTURE:roundlog-world}"}, {})]


EDGE_CASES = load_table("block_guarded_path_edit", "EDGE_CASES")
