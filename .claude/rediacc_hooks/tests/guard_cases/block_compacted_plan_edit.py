"""The test tables of `block_compacted_plan_edit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os
import tempfile

from rediacc_hooks import hookio

# --------------------------------------------------------------------------- The fixture world ---------------------------------------------------------------------------
#
# Every branch of this guard is behind `[ -f "$FILE" ]` and reads the record out of the file on disk, so the differential cannot reach any of them without a real record at a path the payload names literally. Same deterministic-temp-dir arrangement as block_roundlog_write.py, and for the same reason: the repo's own agent/PLAN-*.md files would make the answer depend on which plans
# happen to be compacted today.
WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-records")


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
    "Full-Text: c129f44d1 agent/PLAN-a-compacted-record.md\n"
    "Full-Text-Blob: %s\n"
    "Record-Sig: %s\n"
    "\n"
    "## Boxes\n"
    "\n"
    "- [x] %s\n"
    "    (record) done=c129f44d1 landed in the same change\n"
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
ENVS = [("records", {"REDIACC_RECORD_WORLD": "{FIXTURE:record-world}"}, {})]


EDGE_CASES = [
    # Judged where the write LANDS (#bc7d998c): each refusal was allowed before, and the message names both paths.
    (
        "a Write through a .. detour onto the record",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "%s/agent/x/../PLAN-a-compacted-record.md" % WORLD,
                "content": "# rewritten\n",
            },
        },
    ),
    (
        "a Write through a symlink onto the record",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "%s/linked/PLAN-a-compacted-record.md" % WORLD,
                "content": "# rewritten\n",
            },
        },
    ),
    (
        "a Write replaces the spine outright",
        {"tool_name": "Write", "tool_input": {"file_path": RECORD, "content": "# rewritten\n"}},
    ),
    (
        "an edit quoting a whole header line",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": RECORD,
                "old_string": "Status: compacted",
                "new_string": "Status: active",
            },
        },
    ),
    # The 2026-09-06 reproduction: a MINIMAL unique old_string with no line prefix at all, which every line-anchored pattern above misses.
    (
        "the bare 40-hex blob as old_string",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "old_string": BLOB}},
    ),
    (
        "the bare 8-hex signature as old_string",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "old_string": SIG}},
    ),
    (
        "a done= attestation",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "new_string": "done=abandoned"}},
    ),
    (
        "a checkbox line",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "new_string": "- [ ] a new box"}},
    ),
    (
        "a (record) attestation line",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": RECORD, "new_string": "    (record) done=open"},
        },
    ),
    # BOTH DIRECTIONS of the box-body containment test.
    (
        "a box body quoted whole",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "old_string": BOX_BODY}},
    ),
    (
        "the shortest distinguishing part of a box body",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "old_string": BOX_BODY[:20]}},
    ),
    # ... and its floor: a needle under 12 characters is ordinary prose.
    (
        "a needle under the twelve-character floor",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "old_string": "Rotate the"}},
    ),
    # The common case, which must stay frictionless.
    (
        "sharpening the prose is allowed",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": RECORD,
                "old_string": "Prose that Record-Sig deliberately does not cover",
                "new_string": "Prose the signature deliberately leaves alone",
            },
        },
    ),
    # Both halves of the record test are required.
    (
        "a plan that is not a record",
        {"tool_name": "Write", "tool_input": {"file_path": PLAIN, "content": "# rewritten\n"}},
    ),
    (
        "a record path that does not exist",
        {"tool_name": "Write", "tool_input": {"file_path": "agent/PLAN-absent.md", "content": "x"}},
    ),
    ("a document that is not a plan", {"tool_name": "Write", "tool_input": {"file_path": "a.md"}}),
]
