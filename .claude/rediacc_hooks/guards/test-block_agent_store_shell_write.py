#!/usr/bin/env python3
"""Control harness for block_agent_store_shell_write: the shell half of "an append-only agent store is written only by its verbs" (review finding 896a95d5.3). The edit half is the agent store row of block_guarded_path_edit, judged by `test-block_guarded_path_edit.py`.

THE WORLD is a scratch checkout under the system temp directory holding real stores (`agent/reggate/main.jsonl`, `agent/worklist/d778be9d.jsonl`, `agent/ledgers/effort-outcomes.jsonl`), the files beside them that are not stores, a link to a store file and a link to a store directory, and two copies of one store-writing script: one under `.claude/hooks/stop/` (a changed hook script, which the guard admits) and one under `tools/` (which it refuses). Every payload runs with that directory as its `cwd`, so the on-disk readings (a glob, a link, a `cd`) meet files that exist.

The rows are `SHELL_CASES` in tests/fixtures/guards/block_agent_store_shell_write.json, refusals first, plus the world-bound rows below. Every case runs through dispatch.py in both directions with a floor of four each way, then the guard's DEFECT (its landing test removed) is planted in-process and at least one case must turn: a suite that stays green with the landing test gone proves nothing.

    test-block_agent_store_shell_write.py
"""

import atexit
import pathlib
import shutil
import sys
import tempfile

import _hookpath

from rediacc_hooks.guards import _edit_suite
from rediacc_hooks.tests.fixtures.guards.loader import load_table

STEM = "block_agent_store_shell_write"
WORLD = pathlib.Path(tempfile.mkdtemp(prefix="test-agent-store-"))
atexit.register(shutil.rmtree, str(WORLD), True)

_RETIRE = '{"kind":"retire","sig":"0123abcd","asked":"ASKED:2026-11-27T10:00Z"}\n'
FILES = {
    "agent/reggate/main.jsonl": _RETIRE,
    "agent/worklist/d778be9d.jsonl": '{"op":"add","id":"1234abcd"}\n',
    "agent/worklist/README.md": "# worklist\n",
    "agent/worklist/epics.jsonl.lock": "",
    "agent/ledgers/effort-outcomes.jsonl": "{}\n",
    "agent/ledgers/feedback-snapshot.json": "{}\n",
}
for rel, body in FILES.items():
    (WORLD / rel).parent.mkdir(parents=True, exist_ok=True)
    (WORLD / rel).write_text(body, encoding="utf-8")
(WORLD / "agent" / "reggate-old").mkdir()
(WORLD / "rg").symlink_to(WORLD / "agent" / "reggate", target_is_directory=True)
(WORLD / "wl").symlink_to(WORLD / "agent" / "worklist" / "d778be9d.jsonl")

# One store-writing program, placed twice: the admission is by where the script lives, so the same text outside `.claude/hooks/` must be refused.
_FORGER = "open('agent/reggate/main.jsonl', 'a').write('x\\n')\n"
for rel in (".claude/hooks/stop/wl_probe.py", "tools/forge.py"):
    (WORLD / rel).parent.mkdir(parents=True, exist_ok=True)
    (WORLD / rel).write_text(_FORGER, encoding="utf-8")

WORLD_CASES = [
    ("append through a link to the reggate directory", "echo x >> rg/main.jsonl", True),
    ("tee through a link to the worklist log", "echo x | tee wl", True),
    ("a store-writing script outside .claude/hooks", "python3 tools/forge.py", True),
    ("the same script as a changed hook script", "python3 .claude/hooks/stop/wl_probe.py", False),
    ("read through a link to the reggate directory", "cat rg/main.jsonl", False),
]

SHELL_CASES = load_table(STEM, "SHELL_CASES")
# A refused row must name a real store of the world: a fixture that drifted to paths nothing holds would judge nothing.
if not all((WORLD / rel).exists() for rel in FILES):
    raise SystemExit("the scratch world is incomplete under %s" % WORLD)
if not any("agent/reggate/" in c for _n, c, refused in SHELL_CASES if refused):
    raise SystemExit("no refused fixture row names agent/reggate/; the rows have drifted")

STYLE = _edit_suite.Style(says="append-only agent store", width=56, rc=True)


def cases():
    rows = list(SHELL_CASES) + WORLD_CASES
    return [
        (n, {"tool_name": "Bash", "tool_input": {"command": c}, "cwd": str(WORLD)}, r)
        for n, c, r in rows
    ]


def main():
    return _edit_suite.finish(_edit_suite.judge(STEM, cases(), STYLE))


if __name__ == "__main__":
    sys.exit(main())
