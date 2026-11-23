"""The test tables of `block_commit_of_live_writer_file`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import json
import os
import pathlib
import subprocess
import time

# THE DIFFERENTIAL'S WORLD. A repository of its own holding a config directory with one session that has a live and a finished writer, so `test_guards_differential` sees this guard refuse and sees its DEFECT stop the refusal: a payload without a locatable session only ever reaches the fail-open branch.
#
# ITS OWN REPOSITORY, NOT THE ONE RUNNING PYTEST, found 2026-11-06 (#d7056e06). The world used to be planted under the munged path of the running checkout, and the cases ran there. From a lease tree that can never refuse: `wl_core.project_root` answers a lease with the main checkout (6fd1f6511), so the session was looked up under a directory nothing planted, and every case took the fail-open branch, where the DEFECT cannot bite. A lease writer's own edits are also dropped by `wl_roster.in_lease_tree`, so no planting from inside a lease could have made a lease commit refusable. So the root is named twice: `CLAUDE_PROJECT_DIR` in the `writers` variant, which is where `wl_core.project_start` starts (above the hook file's own repository and the cwd), and the harness's `CWD_WORLDS` for the cwd the commit's repository is resolved from; the payloads carry no `cwd`, so the guard reads `ev.cwd`.
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

    `agents` is `[(agent_id, description, [calls], live, parent)]`, each call an absolute path planted as an Edit of it, or a `(tool name, tool input)` pair planted as written (a Bash command a writer or a reader ran). A live agent's transcript ends on a tool call still in flight; a finished one ends its turn and is back-dated an hour, well past `wl_roster.FINISHED_QUIET_S`. Shared by the differential fixture and `test-block_commit_of_live_writer_file.py`, so the two cannot drift apart on what a live transcript looks like.
    """
    munged = "".join(ch if ch.isalnum() else "-" for ch in str(root))
    sub = pathlib.Path(config_dir) / "projects" / munged / session_id / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    for aid, desc, paths, live, parent in agents:
        lines = []
        for n, p in enumerate(paths):
            name, tool_input = p if isinstance(p, tuple) else ("Edit", {"file_path": p})
            lines.append(_record("tool_use", [_tool(name, tool_input, n)], str(root)))
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

    root = pathlib.Path(target)
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    write_session(
        root / "config",
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
    return str(root)


FIXTURES = {"live-writer-world": _writer_world}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {}, {}),
    (
        "writers",
        {
            "CLAUDE_CONFIG_DIR": "{FIXTURE:live-writer-world}/config",
            "CLAUDE_PROJECT_DIR": "{FIXTURE:live-writer-world}",
        },
        {},
    ),
]


def _payload(command):
    return {
        "tool_name": "Bash",
        "session_id": FIXTURE_SESSION,
        "tool_input": {"command": command},
    }


EDGE_CASES = [
    ("a live writer's file", _payload("git commit -F m -- %s/live.txt" % FIXTURE_DIR)),
    ("a directory covering a live writer's file", _payload("git commit -F m -- %s/" % FIXTURE_DIR)),
    ("a finished writer's file", _payload("git commit -F m -- %s/done.txt" % FIXTURE_DIR)),
    ("a file no writer touched", _payload("git commit -F m -- %s/other.txt" % FIXTURE_DIR)),
    ("not a commit", _payload("git status --short")),
]
