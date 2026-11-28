"""The test tables of `block_compacted_plan_edit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os

from rediacc_hooks import hookio
from rediacc_hooks.tests.fixtures.guards.loader import load_table

# --------------------------------------------------------------------------- The fixture world ---------------------------------------------------------------------------
#
# Every branch of this guard is behind `[ -f "$FILE" ]` and reads the record out of the file on disk, so the differential cannot reach any of them without a real record at a path the payload names literally. Same deterministic-temp-dir arrangement as block_roundlog_write.py, and for the same reason: the repo's own agent/PLAN-*.md files would make the answer depend on which plans
# happen to be compacted today.
WORLD = hookio.golden_world("rediacc-guard-records")


RECORD = "%s/agent/PLAN-a-compacted-record.md" % WORLD


PLAIN = "%s/agent/PLAN-not-a-record.md" % WORLD


BLOB = "c129f44d1b7e4a0f8d3c25e6b91af07d2c5e0168"


SIG = "9a3f0b1d"


BOX_BODY = "Rotate the namespace and update all four consumers"


RECORD_TEXT = (
    "# A compacted plan record\n"
    "\n"
    "Status: compacted\n"
    "Owner: d1589e0b\n"
    "Full-Text: c0de0f44d agent/PLAN-a-compacted-record.md\n"
    "Full-Text-Blob: %s\n"
    "Record-Sig: %s\n"
    "\n"
    "## Boxes\n"
    "\n"
    "- [x] %s\n"
    "    (record) done=c0de0f44d landed in the same change\n"
    "- [ ] Delete the compatibility shim once nothing reads it\n"
    "\n"
    "## Why\n"
    "\n"
    "Prose that Record-Sig deliberately does not cover, so it stays editable in\n"
    "place and this guard must not fire on a change to it.\n"
) % (BLOB, SIG, BOX_BODY)


PLAIN_TEXT = "# An ordinary plan\n\nStatus: active\n\n## Tasks\n\n- [ ] Do the thing properly\n"


def _record_world(_unused):
    """One compacted record and one ordinary plan, at fixed paths."""
    os.makedirs(os.path.join(WORLD, "agent"), exist_ok=True)
    for path, text in ((RECORD, RECORD_TEXT), (PLAIN, PLAIN_TEXT)):
        hookio.write_world_file(path, text)
    # A directory symlink into the guarded tree (#bc7d998c): a write through it lands in the tree.
    link = os.path.join(WORLD, "linked")
    hookio.ensure_world_symlink(os.path.join(WORLD, "agent"), link)
    return WORLD


FIXTURES = {"record-world": _record_world}


# The variable is never read by this guard; resolving the token is what builds the world before any case runs.
ENVS: list = [("records", {"REDIACC_RECORD_WORLD": "{FIXTURE:record-world}"}, {})]


EDGE_CASES = load_table("block_compacted_plan_edit", "EDGE_CASES")
