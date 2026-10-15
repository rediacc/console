"""wl_effort: the Stop hook's one effort dial (agent/plans/PLAN-stop-hook-effort.md).

THE ASK (operator 2026-10-14): one `effort` instead of a hook switch, a focus verb, turbo and four more booleans, with "a modifiable list, to move some of the checks/tasks between the options instead of that complex switchings". agent/plans/QUEUE.md `## Settings` names the level; `.claude/config/effort.json` is the modifiable list.

THE LEVELS, each a superset of the one before: `quiet` (the FLOOR only), `low` (plus the mission: open items, the PR's plan, its finish line, reviews, the turbo and loop orders), `smart` (plus owed work and record integrity; `no-remaining` and `out-of-sync` start advise-only, and the table's `tuned` section names any the tuner has moved since; the judge runs without riders), `high` (every check, the full judge), `ultra` (high plus the throughput bundle).

ONE VERDICT PER KEY AND LEVEL, `verdict(key, level)`: `block`, `advise` (the check rides the advisory queue instead of holding the stop) or `off`. A FLOOR key (`wl_floor`) blocks at every level and is never read from the table. An unreadable table, or a key the table does not list, BLOCKS: the dial can only quiet the hook on purpose, the same rule `stop_hook: off` followed, and the effort-table rule of `npm run check:ci-plan-record` keeps the table complete so the second case does not ship.

THE ADVISORY QUEUE IS GATED HERE TOO. `wl_checks.outq_add` asks `advises(key)` against the level `activate` set for this stop; with no level active (a verb, a SessionStart) every advisory passes.

Reads no environment variable.
"""

from __future__ import annotations

import ast
import json
import pathlib

import wl_floor

LEVELS = ("quiet", "low", "smart", "high", "ultra")
# The level a missing or unparseable `effort:` line resolves to: every check, today's judge, no throughput change. A broken line must never be what quiets the hook.
FAILSAFE = "high"
FLOOR_MARK = "floor"
BLOCK, ADVISE, OFF = "block", "advise", "off"
TABLE_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "effort.json"
TABLE_REL = ".claude/config/effort.json"

# The switch values a bundle may set, with their type: the fence keys a level resolves (wl_planqueue.Settings).
BUNDLE_TYPES = {
    "turbo": bool,
    "turbo_push": str,
    "batch_size": int,
    "plan_concurrency": int,
    "writer_cap": int,
    "commit_remind_min": int,
    "backup_push_h": int,
    "cadence": bool,
    "agent_hint": bool,
    "agent_pushback": bool,
    "judge": str,
}
JUDGE_MODES = ("off", "core", "full")

_CACHE: dict[str, tuple[dict | None, str]] = {}


def rank(level: str) -> int:
    """The position of `level` in LEVELS; ValueError for an unknown one."""
    return LEVELS.index(level)


def load(path=None) -> tuple[dict | None, str]:
    """(table, problem). The parsed effort.json, or None and why it could not be read. Cached per path for the life of the process (one stop)."""
    path = pathlib.Path(path or TABLE_PATH)
    key = str(path)
    if key not in _CACHE:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            doc, why = None, str(exc)
        else:
            why = (
                ""
                if isinstance(doc, dict) and isinstance(doc.get("checks"), dict)
                else "no `checks` object"
            )
        if why:
            _CACHE[key] = (None, "%s is unreadable (%s): every check blocks" % (TABLE_REL, why))
        else:
            _CACHE[key] = (doc, "")
    return _CACHE[key]


def bundle(level: str, table=None) -> dict:
    """The switch values `level` sets, {} when the table or the level's bundle cannot be read."""
    table = load()[0] if table is None else table
    got = ((table or {}).get("bundles") or {}).get(level)
    return dict(got) if isinstance(got, dict) else {}


def _entry(key: str, table):
    return ((table or {}).get("checks") or {}).get(wl_floor.base(key))


def verdict(key: str, level: str, table=None, compaction_due: bool = False) -> str:
    """`block`, `advise` or `off` for violation `key` at `level`."""
    if wl_floor.floored(key, compaction_due):
        return BLOCK
    table = load()[0] if table is None else table
    entry = _entry(key, table)
    if not isinstance(entry, dict) or level not in LEVELS:
        return BLOCK
    try:
        at = rank(level)
        if at >= rank(str(entry.get("block", "quiet"))):
            return BLOCK
        if at >= rank(str(entry.get("advise", entry.get("block", "quiet")))):
            return ADVISE
    except ValueError:
        return BLOCK
    return OFF


def advises(key: str, level: str | None, table=None) -> bool:
    """True when advisory `key` is queued at `level`. None (no stop in progress) admits everything."""
    if level is None or wl_floor.floored(key):
        return True
    table = load()[0] if table is None else table
    entry = _entry(key, table)
    if not isinstance(entry, dict) or level not in LEVELS:
        return True
    try:
        return rank(level) >= rank(str(entry.get("advise", entry.get("block", "quiet"))))
    except ValueError:
        return True


# ---- the level of the stop in progress ----------------------------------------
_ACTIVE: list[str | None] = [None]


def activate(level: str | None) -> None:
    """Set the level `outq_add` gates against for the rest of this stop (None clears it)."""
    _ACTIVE[0] = level


def active() -> str | None:
    return _ACTIVE[0]


# ---- the keys the hook can produce, for the effort-table gate -------------------
STOP_DIR = pathlib.Path(__file__).resolve().parent


def _literal_head(node, assigned):
    """The check class a key argument names: a string constant, the literal left side of `"x:%s" % y`, or a name assigned one of those; None for anything else."""
    if isinstance(node, ast.Name):
        node = assigned.get(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
        return wl_floor.base(node.value)
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.left, ast.Constant)
        and isinstance(node.left.value, str)
    ):
        return wl_floor.base(node.left.value)
    return None


def _call_name(node):
    fn = node.func
    return fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""


def produced_keys(stop_dir=None) -> tuple[set[str], set[str]]:
    """(blocking, advisory) check classes, read by AST: every literal key of a `vadd(...)` call and of an `outq_add(...)` call in the Stop hook's modules, plus wl_checklist's per-slug `_ckey("<class>", slug)` keys (blocking unless appended to its advisory list `a`)."""
    stop_dir = pathlib.Path(stop_dir or STOP_DIR)
    blocking: set[str] = set()
    advisory: set[str] = set()
    for path in sorted(stop_dir.glob("wl_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assigned = {}
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                assigned[node.targets[0].id] = node.value
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name == "vadd" and node.args:
                head = _literal_head(node.args[0], assigned)
                if head:
                    blocking.add(head)
            elif name == "outq_add":
                arg = (
                    node.args[3]
                    if len(node.args) > 3
                    else next((k.value for k in node.keywords if k.arg == "key"), None)
                )
                head = _literal_head(arg, assigned) if arg is not None else None
                if head:
                    advisory.add(head)
            elif name == "_ckey" and node.args:
                head = _literal_head(node.args[0], assigned)
                if not head:
                    continue
                up = parents.get(node)
                while up is not None and not (
                    isinstance(up, ast.Call) and _call_name(up) == "append"
                ):
                    up = parents.get(up)
                recv = (
                    up.func.value if up is not None and isinstance(up.func, ast.Attribute) else None
                )
                if isinstance(recv, ast.Name) and recv.id == "a":
                    advisory.add(head)
                else:
                    blocking.add(head)
    return blocking, advisory


def table_problems(table, blocking: set[str], advisory: set[str]) -> list[str]:
    """Every way `table` disagrees with the hook: each produced key once, no unknown key, the FLOOR marked `floor` and nothing else, `block` never below `advise`, every level's bundle well formed."""
    out: list[str] = []
    if not isinstance(table, dict):
        return ["%s is not a JSON object" % TABLE_REL]
    if tuple(table.get("levels") or ()) != LEVELS:
        out.append("levels: expected %s, got %r" % (list(LEVELS), table.get("levels")))
    bundles = table.get("bundles")
    if not isinstance(bundles, dict):
        out.append("bundles: missing")
        bundles = {}
    for level in LEVELS:
        got = bundles.get(level)
        if not isinstance(got, dict):
            out.append("bundles.%s: missing" % level)
            continue
        for key, value in got.items():
            want = BUNDLE_TYPES.get(key)
            if want is None:
                out.append("bundles.%s.%s: unknown switch" % (level, key))
            elif type(value) is not want:
                out.append("bundles.%s.%s: expected %s" % (level, key, want.__name__))
            elif key == "judge" and value not in JUDGE_MODES:
                out.append("bundles.%s.judge: expected %s" % (level, "|".join(JUDGE_MODES)))
        missing = sorted(set(BUNDLE_TYPES) - set(got))
        if missing:
            out.append("bundles.%s: missing %s" % (level, ", ".join(missing)))
    out.extend("bundles.%s: unknown level" % level for level in sorted(set(bundles) - set(LEVELS)))
    checks = table.get("checks")
    if not isinstance(checks, dict):
        return [*out, "checks: missing"]
    produced = blocking | advisory
    out.extend(
        "checks: %s is produced by the hook and missing from the table" % key
        for key in sorted(produced - set(checks))
    )
    out.extend(
        "checks: %s is not a key the hook produces" % key for key in sorted(set(checks) - produced)
    )
    for key, entry in sorted(checks.items()):
        if key in wl_floor.FLOOR:
            if entry != FLOOR_MARK:
                out.append(
                    "checks: %s is a FLOOR key (wl_floor.FLOOR) and must be %r, got %r"
                    % (key, FLOOR_MARK, entry)
                )
            continue
        if entry == FLOOR_MARK:
            out.append("checks: %s is marked floor but is not in wl_floor.FLOOR" % key)
            continue
        if not isinstance(entry, dict) or set(entry) - {"block", "advise"} or "advise" not in entry:
            out.append(
                'checks: %s: expected {"block": <level>, "advise": <level>} or "floor", got %r'
                % (key, entry)
            )
            continue
        if entry.get("advise") not in LEVELS or ("block" in entry and entry["block"] not in LEVELS):
            out.append("checks: %s: a level outside %s" % (key, "|".join(LEVELS)))
            continue
        if key in blocking and "block" not in entry:
            out.append("checks: %s blocks (a vadd) and needs a `block` level" % key)
        if key not in blocking and "block" in entry:
            out.append("checks: %s is advisory only (an outq_add) and takes no `block` level" % key)
        if "block" in entry and rank(entry["block"]) < rank(entry["advise"]):
            out.append(
                "checks: %s blocks at %s, below its advise level %s"
                % (key, entry["block"], entry["advise"])
            )
    return out


def level_keys(table, level: str) -> dict[str, list[str]]:
    """Every key of `table` at `level`, for the `--queue-set` printout and the operator's review of the table: a blocking check (a `vadd`, or a FLOOR key) under `block`, `advise` or `off`, and an advisory-only key (an `outq_add`) under `shown` or `hidden`."""
    out: dict[str, list[str]] = {BLOCK: [], ADVISE: [], OFF: [], "shown": [], "hidden": []}
    for key, entry in sorted(((table or {}).get("checks") or {}).items()):
        if isinstance(entry, dict) and "block" not in entry:
            out["shown" if advises(key, level, table) else "hidden"].append(key)
        else:
            out[verdict(key, level, table)].append(key)
    return out
