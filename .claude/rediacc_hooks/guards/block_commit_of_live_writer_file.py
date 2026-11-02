"""Refuse a `git commit` that would take a file a LIVE writer subagent of this session is still editing.

WHY. `git commit -F <msg> -- <path>` commits the WHOLE working-tree file at `<path>`, not the hunks its author meant. On 2026-10-08 commit 252e5e1d1 named `.ci/scripts/ci/greenlight.cjs` while writer W11-B, a live subagent of the same session, had uncommitted edits in that file: its half-finished removal of the `common.sh` entries (ahead of a deletion that was not committed) rode along unannounced, the per-commit review flagged it high (252e5e1d.1), and 32bf7abdb had to undo it. `block_pathspecless_git_commit` cannot see this shape, because the commit DID name its paths; the hazard is that a named path is shared with work still in flight.

WHAT IS LIVE, AND WHERE EACH PIECE COMES FROM. A PreToolUse event carries no background-task list, so the Stop hook's own predicate (`wl_roster.live_writer_paths`, "listed running by the event and not proven finished") cannot be applied as written. This guard keeps its second half and lets the transcript stand in for the first:

  * the session's agents are `wl_roster.load_metas(wl_roster.session_subagents_dir(cwd, session_id))`;
  * an agent is LIVE when its transcript exists and `wl_roster.proven_finished` does NOT say it ended its turn
    (that test is one-directional: every ambiguous shape reads as working, which is the safe side here too);
  * its paths are `wl_roster.edit_paths` over its own transcript and every descendant's
    (`children_map` + `descendants`), since a writer's own sub-writers are part of its unfinished work.

A FINISHED writer's own files are never refused. They are exactly what the lead commits once the output is spot-checked, which is the normal flow (CLAUDE.md rule 1). The one exception is a finished sub-writer with a live ancestor anywhere up its spawn chain (parent, grandparent, ...; finished intermediate writers do not break the chain): its edits count as part of that ancestor's unfinished work, so they are refused until the ancestor ends.

WHAT THE COMMIT TAKES. `commit_policy.judged_paths`, the parser `block_no_review_ineligible` and `block_commit_on_main` already share: the pathspecs expanded to the files git knows under them, else the index (and the modified tracked files under `-a`). Each named pathspec also counts as a prefix in its own right, so a directory pathspec covers a writer's file under it even where `git ls-files` would not list it. The reverse is deliberately NOT a match: `edit_paths` reads a `cp x .ci/` as a write to `.ci`, and letting a directory a writer once wrote INTO cover every file below it would refuse unrelated commits across a whole tree.

FAILS OPEN ONLY WHEN THE ROSTER CANNOT BE READ, and says so on stderr. A session directory that cannot be located (no session id, an ambiguous prefix, no projects store) or a roster read that raises is not evidence of a live writer, and refusing every commit on it would be a deadlock. A session that has simply spawned nothing is an honest empty roster and passes silently.

MEASURED COST, 2026-10-08, on a session with 1,090 subagent metas and a 597 MB lead transcript: the liveness pass reads only each transcript's bounded tail (about one second warm), and full transcripts are read only for the agents that pass it. The lead transcript itself is never read, which is why the harness's completion notifications (`wl_roster._completed_since`) are not consulted: that read covers the whole file from offset 0. On the same session every one of the 1,088 finished agents was already proven finished by its own tail, and the two left were the two writers really running.

NO ENVIRONMENT READ OF ITS OWN. The payload's `cwd` and `session_id` locate the session, as in `block_agent_cap`. The stop-hook modules are loaded by `importlib` inside `run`, after the command is known to be a commit, so the other Bash calls of the chain never pay for them.
"""

import importlib
import json
import os
import pathlib
import time

from rediacc_hooks import commit_policy, hookio, syspath

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 59

# The overlap test itself. With it never matching, a live writer's file rides a commit again, which is the 252e5e1d1 shape.
DEFECT = (
    "if writer == spec or (",
    "if False and (",
)

# What a roster read can raise, including TypeError and AttributeError for a transcript or meta file of an unexpected shape. Each one fails open, and the stderr note carries the exception text, so a bug in this guard's own code inside the same read is visible there rather than silent; any other exception type is reported as a crash by the dispatcher.
ROSTER_ERRORS = (
    OSError,
    ValueError,
    LookupError,
    ImportError,
    RuntimeError,
    TypeError,
    AttributeError,
)

# THE DIFFERENTIAL'S WORLD. A config directory holding one session with a live and a finished writer, so `test_guards_differential` sees this guard refuse and sees its DEFECT stop the refusal: a payload without a locatable session only ever reaches the fail-open branch.
FIXTURE_SESSION = "f1x7ure0-live-writer-guard-000000000000"
FIXTURE_DIR = "zz-live-writer-fixture"
LIVE_AGENT = "afixturelivewriter0001"
DONE_AGENT = "afixturedonewriter0002"


def _record(stop_reason, content, cwd):
    return json.dumps(
        {
            "type": "assistant",
            "cwd": cwd,
            "message": {"role": "assistant", "stop_reason": stop_reason, "content": content},
        }
    )


def _tool(name, tool_input, n):
    return {"type": "tool_use", "id": "toolu_fixture_%d" % n, "name": name, "input": tool_input}


def write_session(config_dir, root, session_id, agents):
    """Plant a session under `<config_dir>/projects/<munged root>/<session_id>/subagents`.

    `agents` is `[(agent_id, description, [absolute edited paths], live, parent)]`. A live agent's transcript ends on a tool call still in flight; a finished one ends its turn and is back-dated an hour, well past `wl_roster.FINISHED_QUIET_S`. Shared by the differential fixture and `test-block_commit_of_live_writer_file.py`, so the two cannot drift apart on what a live transcript looks like.
    """
    munged = "".join(ch if ch.isalnum() else "-" for ch in str(root))
    sub = pathlib.Path(config_dir) / "projects" / munged / session_id / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    for aid, desc, paths, live, parent in agents:
        lines = [
            _record("tool_use", [_tool("Edit", {"file_path": p}, n)], str(root))
            for n, p in enumerate(paths)
        ]
        if live:
            lines.append(
                _record("tool_use", [_tool("Bash", {"command": "sleep 1"}, len(paths))], str(root))
            )
        else:
            lines.append(_record("end_turn", [{"type": "text", "text": "done"}], str(root)))
        jsonl = sub / ("agent-%s.jsonl" % aid)
        jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
        meta = {"agentType": "general-purpose", "description": desc}
        if parent:
            meta["parentAgentId"] = parent
        (sub / ("agent-%s.meta.json" % aid)).write_text(json.dumps(meta), encoding="utf-8")
        if not live:
            old = time.time() - 3600
            os.utime(jsonl, (old, old))
    return sub


def _writer_world(target):
    root = pathlib.Path(__file__).resolve().parents[3]
    write_session(
        target,
        root,
        FIXTURE_SESSION,
        [
            (LIVE_AGENT, "fixture live writer", [str(root / FIXTURE_DIR / "live.txt")], True, ""),
            (
                DONE_AGENT,
                "fixture finished writer",
                [str(root / FIXTURE_DIR / "done.txt")],
                False,
                "",
            ),
        ],
    )
    return target


FIXTURES = {"live-writer-world": _writer_world}

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {}, {}),
    ("writers", {"CLAUDE_CONFIG_DIR": "{FIXTURE:live-writer-world}"}, {}),
]


def _payload(command):
    return {
        "tool_name": "Bash",
        "session_id": FIXTURE_SESSION,
        "cwd": "/home/developer/console",
        "tool_input": {"command": command},
    }


EDGE_CASES = [
    ("a live writer's file", _payload("git commit -F m -- %s/live.txt" % FIXTURE_DIR)),
    ("a directory covering a live writer's file", _payload("git commit -F m -- %s/" % FIXTURE_DIR)),
    ("a finished writer's file", _payload("git commit -F m -- %s/done.txt" % FIXTURE_DIR)),
    ("a file no writer touched", _payload("git commit -F m -- %s/other.txt" % FIXTURE_DIR)),
    ("not a commit", _payload("git status --short")),
]

REFUSED = (
    "BLOCKED: this `git commit` would take %(count)d file(s) that a LIVE writer subagent of this\n"
    "session is still editing.\n"
    "\n"
    "%(writers)s\n"
    "\n"
    "`git commit -- <path>` commits the WHOLE working-tree file, so the writer's half-finished\n"
    "edit would ride along unannounced. That is what 252e5e1d1 did to .ci/scripts/ci/greenlight.cjs\n"
    "while writer W11-B was live in it, and 32bf7abdb had to undo it.\n"
    "\n"
    "Do one of these:\n"
    "  - wait for the writer to finish, spot-check its output, and commit these files with it;\n"
    "  - or drop these paths from this commit's pathspec and commit the rest now.\n"
    "\n"
    "Live means the writer's transcript exists, it edited these paths, and its last record has\n"
    "not ended its turn (wl_roster.proven_finished). A finished writer's files are never refused,\n"
    "unless a writer above it in the spawn chain (parent, grandparent, ...) is still running.\n"
)

UNREADABLE = (
    "commit-of-live-writer-file: the subagent roster of session %r could not be read\n"
    "(%s), so this commit was ALLOWED without checking its paths against live\n"
    "writers' uncommitted edits.\n"
)


def _stop_module(name):
    """A `.claude/hooks/stop` module, loaded only once a command is known to be a commit."""
    syspath.on_sys_path(syspath.STOP_DIR)
    return importlib.import_module(name)


def live_writers(cwd, session_id, now=None):
    """`(root, [(agent_id, meta, {absolute edited paths})])` for every live writer of the session.

    Raises LookupError when the session's subagent directory cannot be located; an empty list is a located session with no live writer.
    """
    core = _stop_module("wl_core")
    roster = _stop_module("wl_roster")
    sub_dir = roster.session_subagents_dir(cwd, session_id)
    if sub_dir is None:
        msg = "no session directory could be located"
        raise LookupError(msg)
    root = str(core.project_root(core.project_start({"cwd": cwd})))
    metas = roster.load_metas(sub_dir)
    if not metas:
        return root, []
    now = time.time() if now is None else now
    kids = roster.children_map(metas)
    out = []
    for aid, meta in sorted(metas.items()):
        jsonl = meta.get("jsonl")
        if jsonl is None or not jsonl.exists():
            continue
        if roster.proven_finished(jsonl, now, meta.get("name", ""), cwd, session_id):
            continue
        paths = set()
        for member in [aid, *roster.descendants(aid, kids)]:
            member_jsonl = (metas.get(member) or {}).get("jsonl")
            if member_jsonl is not None:
                paths |= roster.edit_paths(member_jsonl, root)
        if paths:
            out.append((aid, meta, {os.path.normpath(os.path.join(root, p)) for p in paths}))
    return root, out


def _in_nested_repo(spec, writer):
    """Whether a directory between `spec` (exclusive) and `writer` is a repository root, a submodule `.git` file or directory. A directory pathspec over it commits the gitlink, never the files inside."""
    here = os.path.dirname(writer)
    top = spec.rstrip("/")
    while here != top and here.startswith(top + "/"):
        if os.path.exists(os.path.join(here, ".git")):
            return True
        here = os.path.dirname(here)
    return False


def overlap(committed, writer_paths):
    """The writer paths a commit takes: equal to a committed path, or under a committed directory pathspec that does not cross into a nested repository."""
    hits = []
    for writer in sorted(writer_paths):
        for spec in committed:
            if writer == spec or (
                writer.startswith(spec.rstrip("/") + "/") and not _in_nested_repo(spec, writer)
            ):
                hits.append(writer)
                break
    return hits


def committed_paths(commit, cmd, repo, base):
    """Absolute paths a walked `git commit` would take, plus each plainly named pathspec as a prefix of its own."""
    judged = commit_policy.judged_paths(commit, cmd, repo, base)
    out = {os.path.normpath(os.path.join(repo, p)) for p in judged}
    here = commit_policy.run_dir(commit, base)
    for spec in commit_policy.commit_paths(cmd, run=commit):
        if spec.startswith(":") or any(ch in spec for ch in "*?["):
            continue
        out.add(os.path.normpath(spec if spec.startswith("/") else os.path.join(here, spec)))
    # A submodule's root is a gitlink: committing it records the submodule's commit pointer and never takes a file of the submodule's working tree, so it must not act as a prefix over a writer's files inside the submodule (#e59c13a0: `git commit -- workers/... private/account` was refused for a writer editing private/account/scripts/rotation/*).
    repo_root = os.path.normpath(repo)
    return {p for p in out if p == repo_root or not os.path.exists(os.path.join(p, ".git"))}


def _shown(path, root):
    return os.path.relpath(path, root) if commit_policy.is_inside(path, root) else path


def _describe(root, found):
    blocks = []
    for aid, meta, hits in found:
        desc = (meta.get("desc") or "")[:60]
        head = "  writer %s (%s) %r:" % (aid, meta.get("type") or "?", desc)
        blocks.append("\n".join([head, *("    %s" % _shown(h, root) for h in hits)]))
    return "\n".join(blocks)


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    commits = commit_policy.git_runs(cmd, "commit")
    if not commits:
        return hookio.ALLOW
    cwd = ev.field("cwd") or ev.cwd
    session_id = ev.field("session_id")
    try:
        root, writers = live_writers(cwd, session_id)
    except ROSTER_ERRORS as exc:
        ev.warn_raw(UNREADABLE % (session_id, exc))
        return hookio.ALLOW
    if not writers:
        return hookio.ALLOW
    created = commit_policy.created_dirs(cmd, cwd)
    found: dict[str, tuple] = {}
    for commit in commits:
        repo = commit_policy.run_repo(commit, cwd, created)
        # A commit resolving to no repository is one git refuses; one outside this checkout takes no file a writer of it edited.
        if not repo or not commit_policy.is_inside(repo, root):
            continue
        committed = committed_paths(commit, cmd, repo, cwd)
        for aid, meta, paths in writers:
            hits = overlap(committed, paths)
            if hits:
                prior = found.setdefault(aid, (aid, meta, []))[2]
                prior.extend(h for h in hits if h not in prior)
    if not found:
        return hookio.ALLOW
    listed = list(found.values())
    count = len({h for _, _, hits in listed for h in hits})
    ev.warn_raw(REFUSED % {"count": count, "writers": _describe(root, listed)})
    return hookio.DENY
