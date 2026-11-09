"""wl_worktrees: the Stop hook follows lease trees (agent/plans/PLAN-worktree-lease.md Design 7).

`survey` joins three sources per store, the console's and each `<common>/modules/**` one: `git worktree list --porcelain`, the pins under `refs/worktrees/`, and the records in `<common>/rediacc-worktrees/<id>.json`. wl_checks turns the answer into `worktree-unlanded` (block, owner session only) and `worktree-orphan` (advisory, which also carries a peer's lease as one line).

THE RECORD, read here and written by the `lease` verb: `id`, `path`, `owner` (the session id or its prefix), `agent` (the id inside `agent-<id>`, or ""), `base` ({"." or `private/<name>`: sha}) and `created_at`.

LIVENESS COMES FROM THE ROSTER. A subagent's shell does not live between tool calls, so an empty cwd list proves nothing. A lease is held by a live roster row (by `agent`, or by the meta's recorded tree), by a worklist `[>]` item naming it, or by a process inside it. A blind roster says nothing, and a lease is never accused on a blind reading.

LANDED IS NOT `wl_scratch.git_doubt`, whose `--not --remotes` reads every commit landed on the unpushed live branch as undelivered. A commit counts as landed by `git cherry` against the live tip, or by its `(cherry picked from commit <sha>)` line on a local branch or the live tip.

A STOP WITH NOTHING MOVED RUNS NO STATUS. Full figures are this session's leases only, cached in the state doc under a signature of each repo's lease HEAD, live tip, pin and index stat. A held lease drops its entry, so the stop after its writer ends reads the tree again. The limit: an unstaged edit made after the last reading moves none of these. The GC predicate runs its own status, so that limit costs a report and never a deletion.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
from typing import Any

import wl_core as C
import wl_leasehelp
import wl_roster
import wl_scratch

RECORD_DIR = "rediacc-worktrees"
PIN_ROOT = "refs/worktrees/"
# The console's key in `tips`, `pins`, a lease's repos and a record's `base`; a submodule's is its store path under `modules/`.
CONSOLE = "."
GIT_TIMEOUT_S = 30
SHA_SHOWN = 12
PICKED_LINE = "(cherry picked from commit %s)"
# A lease commit whose change already landed through another commit (a duplicate fix by a second writer, whose pick was skipped): the lead records it with this trailer on a branch commit, `Lease-Landed-As: <lease sha> <landed sha>`. Equivalence of two different patches cannot be read mechanically, so it is an explicit record, never inferred.
LANDED_AS_LINE = "Lease-Landed-As: %s "
# A gitlink row whose commit moved with nothing else changed: submodule-first landing leaves it behind, and the submodule is judged on its own.
GITLINK_MOVED = "SC.."
ORPHAN_TREE = "a tree with no record"
ORPHAN_RECORD = "a record with no tree"
ORPHAN_PIN = "a pin with neither a record nor a tree"


def _git(cwd, *args):
    """stdout, or None when git failed or could not run. `--no-optional-locks` is load-bearing: a plain status rewrites the index the signature reads (wl_scratch.git_doubt records the same trap)."""
    try:
        done = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def stores(common):
    """[(repo key, git dir)]: the console's, then each submodule store under `<common>/modules`."""
    out = [(CONSOLE, common)]
    modules = common / "modules"
    for pattern in ("*/HEAD", "*/*/HEAD"):
        out.extend(
            (head.parent.relative_to(modules).as_posix(), head.parent)
            for head in sorted(modules.glob(pattern))
        )
    return out


def parse_list(text):
    """`git worktree list --porcelain` as one {attribute: value} per tree, the main checkout first."""
    rows: list[dict[str, str]] = []
    row: dict[str, str] = {}
    for line in text.splitlines():
        if not line:
            if row:
                rows.append(row)
            row = {}
            continue
        key, _, value = line.partition(" ")
        row[key] = value
    if row:
        rows.append(row)
    return rows


def dirty_count(text):
    """The changed paths in `status --porcelain=v2` output, a moved gitlink's `.M SC..` row excused. `MM SC..` is also a staged change, so it counts, as `gc` keeps it."""
    count = 0
    for line in text.splitlines():
        fields = line.split(" ", 3)
        if (
            fields[0] in ("1", "2")
            and len(fields) > 2
            and fields[1] == ".M"
            and fields[2] == GITLINK_MOVED
        ):
            continue
        if line:
            count += 1
    return count


def _lease_id(path, base):
    """The first path segment under `base`, or ""."""
    prefix = str(base) + os.sep
    return path[len(prefix) :].split(os.sep, 1)[0] if path.startswith(prefix) else ""


def _read_store(world, repo, store, base):
    refs = _git(store, "for-each-ref", "--format=%(objectname) %(refname)", PIN_ROOT)
    if refs is None:
        world["doubts"].append("%s: its pins could not be read" % repo)
    else:
        for line in refs.splitlines():
            sha, _, ref = line.partition(" ")
            world["pins"].setdefault(ref[len(PIN_ROOT) :], {})[repo] = sha
    # No admin directory means no linked tree, by git's own layout, so most stores spend no second call.
    if not (store / "worktrees").is_dir():
        return
    listed = _git(store, "worktree", "list", "--porcelain")
    if listed is None:
        world["doubts"].append("%s: its trees could not be listed" % repo)
        return
    rows = parse_list(listed)
    if rows:
        world["tips"][repo] = rows[0].get("HEAD", "")
    for row in rows[1:]:
        path = row.get("worktree", "")
        lease_id = _lease_id(path, base)
        if not lease_id or not os.path.isdir(path):
            continue
        if repo == CONSOLE and C.lease_main(pathlib.Path(path)) is None:
            continue
        world["leases"].setdefault(lease_id, {})[repo] = {"path": path, "head": row.get("HEAD", "")}


def read_records(common, base):
    """{id: record} for every record whose tree belongs under `base`. An unreadable one stays, marked `broken`, because a record that cannot be read is still a claim on a tree."""
    out = {}
    for path in sorted((common / RECORD_DIR).glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            record = None
        if not isinstance(record, dict):
            out[path.stem] = {"id": path.stem, "broken": True}
            continue
        if _lease_id(os.path.realpath(str(record.get("path") or "")), base):
            out[str(record.get("id") or path.stem)] = record
    return out


def _stray_dirs(base):
    """Direct child directories of `base`, symlinks excluded."""
    try:
        with os.scandir(base) as it:
            return sorted(e.name for e in it if e.is_dir(follow_symlinks=False))
    except OSError:
        return []


def read_world(root):
    """Every lease fact readable from git and the record store. A checkout git cannot read holds nothing to follow."""
    world: dict[str, Any] = {
        "leases": {},
        "tips": {},
        "pins": {},
        "records": {},
        "dirs": [],
        "doubts": [],
    }
    root = pathlib.Path(root)
    dirs = C._git_dirs(root) if (root / ".git").exists() else None
    if dirs is None or not (dirs[1] / "HEAD").is_file():
        return world
    common = dirs[1]
    base = pathlib.Path(os.path.realpath(root / ".claude" / "worktrees"))
    for repo, store in stores(common):
        _read_store(world, repo, store, base)
    world["records"] = read_records(common, base)
    world["dirs"] = _stray_dirs(base)
    return world


def live_work(roster, cwd, session_id):
    """{"ids", "trees", "cwd"}: this session's live agents and the session's own directory, or None when the roster cannot say."""
    if not roster or roster.get("blind"):
        return None
    ids = set(roster.get("rows") or ())
    metas = wl_roster.load_metas(wl_roster.session_subagents_dir(cwd, session_id))
    trees = {
        os.path.realpath(metas[aid]["worktree"])
        for aid in ids
        if (metas.get(aid) or {}).get("worktree")
    }
    # A lead hands a lease over by path in the brief, so the record's agent is empty and the meta names no tree: only the prompt says who holds it, the way `gc` reads it.
    prompts = [
        (aid, wl_leasehelp.first_prompt((metas.get(aid) or {}).get("jsonl"))) for aid in sorted(ids)
    ]
    return {
        "ids": ids,
        "trees": trees,
        "prompts": prompts,
        "cwd": os.path.realpath(cwd) if cwd else "",
    }


def _holder(lease_id, record, live, leases, cwds):
    """What keeps this lease in use, or ""."""
    raw = str(record.get("path") or "")
    # realpath("") is the hook's own cwd, so a record with no path would read as the session standing inside it.
    path = os.path.realpath(raw) if raw else ""
    agent = str(record.get("agent") or "")
    if (agent and agent in live["ids"]) or (path and path in live["trees"]):
        return "a live writer"
    if not path:
        return ""
    if wl_scratch.lease_holder(lease_id, path, live.get("prompts") or ()):
        return "a live writer"
    # A session working inside its own lease has no roster row, and its shell does not live between tool calls.
    here = live.get("cwd") or ""
    if here == path or here.startswith(path + os.sep):
        return "this session"
    item = wl_scratch.lease_holder(lease_id, path, leases)
    if item:
        return "live item #%s" % item
    if any(c == path or c.startswith(path + os.sep) for c in cwds):
        return "a process inside it"
    return ""


def signature(repos, tips, pins):
    """What the cached figures of one lease rest on. Reads files only, so an unmoved lease costs no git call."""
    parts = []
    for repo in sorted(repos):
        row = repos[repo]
        dirs = C._git_dirs(pathlib.Path(row["path"]))
        stamp = []
        if dirs is not None:
            try:
                st = os.stat(dirs[0] / "index")
                stamp = [st.st_mtime_ns, st.st_size]
            except OSError:
                stamp = []
        parts.append([repo, row["head"], tips.get(repo, ""), pins.get(repo, ""), stamp])
    return hashlib.sha1(json.dumps(parts).encode("utf-8")).hexdigest()[:16]


def unlanded_commits(tree, head, pin, tip, base):
    """The commits of `head` and `pin` the live tip does not hold, or None when git could not say. `base` only narrows the history searched for a `-x` line."""
    found: list[str] = []
    for ref in dict.fromkeys(r for r in (head, pin) if r):
        text = _git(tree, "cherry", tip, ref)
        if text is None:
            return None
        for line in text.splitlines():
            if line.startswith("+ ") and line[2:].strip() not in found:
                found.append(line[2:].strip())
    if not found:
        return []
    greps = ["--grep=" + PICKED_LINE % sha for sha in found]
    greps += ["--grep=" + LANDED_AS_LINE % sha for sha in found]
    narrow = ["--not", base] if base else []
    text = _git(tree, "log", "-F", *greps, "--format=%B", "--branches", tip, *narrow)
    if text is None:
        return None
    return [
        sha for sha in found if PICKED_LINE % sha not in text and LANDED_AS_LINE % sha not in text
    ]


def figures(repos, tips, pins, base):
    """{"dirty", "commits"} for one lease, or {"doubt"} naming the repo git could not read."""
    dirty, commits = 0, {}
    for repo in sorted(repos):
        row = repos[repo]
        status = _git(row["path"], "status", "--porcelain=v2", "--untracked-files=normal")
        if status is None:
            return {"doubt": "git status failed in %s" % repo}
        dirty += dirty_count(status)
        left = unlanded_commits(
            row["path"], row["head"], pins.get(repo, ""), tips.get(repo, ""), base.get(repo, "")
        )
        if left is None:
            return {"doubt": "the landed reading failed in %s" % repo}
        if left:
            commits[repo] = left
    return {"dirty": dirty, "commits": commits}


def _record_orphans(world, trees):
    records = set(world["records"])
    return (
        [(lease_id, ORPHAN_TREE) for lease_id in sorted(trees - records)]
        + [(lease_id, ORPHAN_RECORD) for lease_id in sorted(records - trees)]
        + [(lease_id, ORPHAN_PIN) for lease_id in sorted(set(world["pins"]) - trees - records)]
    )


def survey(root, session_id, items, live_fn, cache):
    """The stop's reading. `items` are the store's folded records, `live_fn` answers `live_work` when first needed, and `cache` is what the last stop returned.

    Returns `unlanded` [{"id", "path", "dirty", "commits"}], `held` and `unknown` (ids), `peers` [{"id", "owner", "path"}], `orphans` [(id, why)], `doubts` [text] and `cache`.
    """
    world = read_world(root)
    out: dict[str, Any] = {
        "unlanded": [],
        "held": [],
        "unknown": [],
        "peers": [],
        "orphans": [],
        "doubts": list(world["doubts"]),
        "cache": {},
    }
    trees = set(world["leases"]) | set(world["dirs"])
    out["orphans"] = _record_orphans(world, trees)
    mine = []
    for lease_id in sorted(trees & set(world["records"])):
        record = world["records"][lease_id]
        if record.get("broken"):
            out["doubts"].append("%s: its record could not be read" % lease_id)
            continue
        owner = str(record.get("owner") or "")[:8] or None
        if C.owned_by_me(owner, session_id):
            mine.append((lease_id, record))
        else:
            out["peers"].append(
                {"id": lease_id, "owner": owner, "path": str(record.get("path") or "")}
            )
    if not mine:
        return out
    live = live_fn()
    leases = wl_scratch.lease_texts(items)
    cwds = wl_scratch.process_cwds()
    for lease_id, record in mine:
        if live is None:
            out["unknown"].append(lease_id)
            continue
        if _holder(lease_id, record, live, leases, cwds):
            out["held"].append(lease_id)
            continue
        repos = world["leases"].get(lease_id)
        if not repos:
            out["doubts"].append("%s: a directory git lists no tree for" % lease_id)
            continue
        pins = world["pins"].get(lease_id) or {}
        sig = signature(repos, world["tips"], pins)
        entry = cache.get(lease_id) if isinstance(cache, dict) else None
        if not isinstance(entry, dict) or entry.get("sig") != sig:
            entry = figures(repos, world["tips"], pins, record.get("base") or {})
            if "doubt" in entry:
                out["doubts"].append("%s: %s" % (lease_id, entry["doubt"]))
                continue
            entry["sig"] = sig
        out["cache"][lease_id] = entry
        # Dirty paths alone block too: a finished lease with edits and no commit still holds work that only `worktree land` carries into the main tree.
        if entry["dirty"] or entry["commits"]:
            out["unlanded"].append(
                {
                    "id": lease_id,
                    "path": str(record.get("path") or ""),
                    "dirty": entry["dirty"],
                    "commits": entry["commits"],
                }
            )
    return out


def unlanded_lines(got):
    """One line per blocking lease, naming the verb that lands it."""
    lines = []
    for row in got["unlanded"]:
        commits = ", ".join(
            "%s %s" % (repo, " ".join(sha[:SHA_SHOWN] for sha in row["commits"][repo]))
            for repo in sorted(row["commits"])
        )
        lines.append(
            "    %s (%s): %d dirty path(s); unlanded commits: %s; ./run.sh worktree land %s"
            % (row["id"], row["path"], row["dirty"], commits or "none", row["id"])
        )
    return "\n".join(lines)


def report_lines(got):
    """The advisory body, one line per orphan, peer lease, doubt or unread lease; "" when nothing is owed."""
    lines = ["  orphan %s: %s" % (lease_id, why) for lease_id, why in got["orphans"]]
    lines.extend(
        "  peer lease %s (session %s): %s" % (row["id"], row["owner"], row["path"])
        for row in got["peers"]
    )
    lines.extend("  unreadable %s" % doubt for doubt in got["doubts"])
    lines.extend(
        "  lease %s: not judged, the roster cannot see its writer" % lease_id
        for lease_id in got["unknown"]
    )
    return "\n".join(lines)
