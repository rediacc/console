"""The test tables of `block_plan_without_tasks`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os
import tempfile

from rediacc_hooks import hookio

# --------------------------------------------------------------------------- The fixture world ---------------------------------------------------------------------------
#
# Two plan files must EXIST on disk for the `[ -f "$FILE" ]` branch and the grandfather clause to be reachable, and the payload names its path literally, so the path has to be known when this module is imported. Same arrangement as block_roundlog_write.py: a deterministic directory under the system temp dir, built through an ENVS token this guard never reads. Using the repo's own
# agent/PLAN-*.md files instead would make the differential's answer depend on whichever plans happen to be checked out today.
WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-plans")


LEGACY_PLAN = "%s/agent/PLAN-legacy-prose.md" % WORLD


TASKED_PLAN = "%s/agent/PLAN-with-tasks.md" % WORLD


NEW_PLAN = "%s/agent/PLAN-not-written-yet.md" % WORLD


_PROSE_BODY = (
    "This document records the decision to move the secret namespace, the four\n"
    "consumers that read it today, and the order the operator locked in. It is\n"
    "written as prose on purpose, the way most of this tree's older plans are,\n"
    "so that an amendment to it exercises the grandfather clause rather than the\n"
    "refusal. Every sentence here exists to carry the file past the 400-character\n"
    "floor that wl_planfid uses to decide whether a plan is worth judging at all.\n"
)


# No checkbox anywhere, and no heading whose first three words name work, so `plan_tasks` finds nothing: the WHY_EMPTY arm.
PROSE_PLAN = "# A plan with no list at all\n\n" + _PROSE_BODY + _PROSE_BODY


# No checkbox either, but the heading DOES name work, so the plain bullets under it parse as tasks: the WHY_INFLATED arm, which is the shape that produced the incident in the header.
INFLATED_PLAN = (
    "# A plan whose bullets are not tasks\n\n"
    + _PROSE_BODY
    + "\n## Part 0 - DECIDED by the operator\n\n"
    "- Rotate the namespace before anything else touches it\n"
    "- Keep the old prefix readable for one release\n"
    "- Do not add a migration command for a consumer nobody has\n"
    "- Land the rename and the consumers in one change\n"
)


TASKED_PLAN_TEXT = (
    "# A plan that conforms\n\n" + _PROSE_BODY + "\n## Tasks\n\n"
    "- [ ] Rotate the namespace and update all four consumers\n"
    "- [x] Record the operator's locked decisions as prose\n"
)


def _plan_world(_unused):
    """The two plan files the on-disk branches need. Idempotent by design."""
    os.makedirs(os.path.join(WORLD, "agent"), exist_ok=True)
    for path, text in ((LEGACY_PLAN, PROSE_PLAN), (TASKED_PLAN, TASKED_PLAN_TEXT)):
        hookio.write_world_file(path, text)
    # A directory symlink into the guarded tree (#bc7d998c): a write through it lands in the tree.
    link = os.path.join(WORLD, "linked")
    hookio.ensure_world_symlink(os.path.join(WORLD, "agent"), link)
    return WORLD


FIXTURES = {"plan-world": _plan_world}


ENVS: list = [("plans", {"REDIACC_PLAN_WORLD": "{FIXTURE:plan-world}"}, {})]


EDGE_CASES = [
    # Judged where the write LANDS (#bc7d998c): each refusal was allowed before, and the message names both paths.
    (
        "a new prose plan through a .. detour",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "%s/agent/x/../PLAN-not-written-yet.md" % WORLD,
                "content": PROSE_PLAN,
            },
        },
    ),
    (
        "a new prose plan through a symlink",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "%s/linked/PLAN-not-written-yet.md" % WORLD,
                "content": PROSE_PLAN,
            },
        },
    ),
    (
        "a .. detour out of the plan folder",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "%s/agent/../PLAN-not-written-yet.md" % WORLD,
                "content": PROSE_PLAN,
            },
        },
    ),
    # A WRITE is authoring, so the whole document must conform.
    (
        "a Write of a prose plan with no list at all",
        {"tool_name": "Write", "tool_input": {"file_path": NEW_PLAN, "content": PROSE_PLAN}},
    ),
    (
        "a Write of the shape that produced the incident",
        {"tool_name": "Write", "tool_input": {"file_path": NEW_PLAN, "content": INFLATED_PLAN}},
    ),
    (
        "a Write of a conforming plan",
        {"tool_name": "Write", "tool_input": {"file_path": NEW_PLAN, "content": TASKED_PLAN_TEXT}},
    ),
    # A plan under 400 chars is a stub and is exempt.
    (
        "a stub is under the floor",
        {"tool_name": "Write", "tool_input": {"file_path": NEW_PLAN, "content": "# stub\n"}},
    ),
    # The grandfather clause: an amendment to a plan that never had a task list.
    (
        "an Edit to a legacy prose plan",
        {"tool_name": "Edit", "tool_input": {"file_path": LEGACY_PLAN, "new_string": "one line"}},
    ),
    # ... and an amendment to one that HAS a list, judged against the union.
    (
        "an Edit to a plan that already conforms",
        {"tool_name": "Edit", "tool_input": {"file_path": TASKED_PLAN, "new_string": "one line"}},
    ),
    # A Write over an existing legacy plan is a wholesale rewrite, so the grandfather clause deliberately does NOT apply to it.
    (
        "a Write over the legacy plan is a rewrite",
        {"tool_name": "Write", "tool_input": {"file_path": LEGACY_PLAN, "content": PROSE_PLAN}},
    ),
    # An Edit to a plan that does not exist yet is judged on its fragments.
    (
        "an Edit to a plan that does not exist yet",
        {"tool_name": "Edit", "tool_input": {"file_path": NEW_PLAN, "new_string": PROSE_PLAN}},
    ),
    (
        "the .claude/plans arm of the scope",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "x/.claude/plans/a.md", "content": PROSE_PLAN},
        },
    ),
    (
        "a document that is not a plan",
        {"tool_name": "Write", "tool_input": {"file_path": "docs/notes.md", "content": PROSE_PLAN}},
    ),
    ("no file_path at all", {"tool_name": "Write", "tool_input": {"content": PROSE_PLAN}}),
]
