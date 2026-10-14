"""wl_floor: the Stop hook's FLOOR, the checks that block at every effort level (agent/plans/PLAN-stop-hook-effort.md).

`effort` in agent/plans/QUEUE.md `## Settings` turns the battery up and down (`quiet` < `low` < `smart` < `high` < `ultra`), and `.claude/config/effort.json` gives every other check a threshold. The FLOOR is what no level may turn off: the hook cannot see, a watch is broken, CI is unreadable, or red outside a turbo batch that is still building locally (wl_checks.TURBO_BUILD_PARKS parks ci-red then, operator ruling 2026-10-13), a writer is dead or over the cap, a report is unread, a background wait has no wake-up timer. `quiet` is this set and nothing else, and it replaces the `stop_hook: off` switch that used to skip these too.

SEALED, beside `wl_standdown.CORE`. `.ci/policy/worklist-env-registry.json` lists this file under `sealed_modules`: it reads no environment variable and imports nothing, so no knob can shrink the set. effort.json marks each of these keys `"floor"`, and the effort-table rule of `npm run check:ci-plan-record` refuses a table that gives one of them a level instead, so a demotion is a diff to this file, where the argument for it belongs.
"""

# Blocks at every level, whatever effort.json says.
FLOOR = frozenset(
    {
        "hook-blind",
        "event-unparseable",
        "cl-shape",
        "adhoc-watch",
        "adhoc-watch-broken",
        "trapguard-errors",
        "ci-red",
        "ci-unreadable",
        "roster-dead",
        "roster-cap",
        "unread-reports",
        "wake-timer",
    }
)

# Blocks at every level only while compaction is due (the late context band with STATE.md not current): the recovery document must be written before the context is summarised. Outside that band effort.json's threshold decides.
FLOOR_WHEN_COMPACTING = frozenset({"agent-state", "agent-absent"})


def base(key):
    """The check class of a key: `agent-pushback:<name>` -> `agent-pushback`."""
    return str(key).split(":", 1)[0]


def floored(key, compaction_due=False):
    """True when `key` blocks at every level."""
    head = base(key)
    return head in FLOOR or (bool(compaction_due) and head in FLOOR_WHEN_COMPACTING)
