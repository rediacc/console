#!/usr/bin/env python3
"""Control harness for block_away_questions: it refuses an AskUserQuestion while `/awk` stands, and the operator's next message ends it.

Each payload runs through the real dispatcher in a subprocess, with `WL_AWAY_STATE` pointed at a scratch file so the live flag is never touched. Both directions are asserted: refused while away, admitted with no flag, and admitted (with the flag cleared) once the transcript shows the operator after the flag, whether as a typed turn, an interrupt or a message queued mid-turn. The records that are NOT the operator (a task notification, the compaction summary, hook feedback, a tool result, the `/awk` invocation itself) leave the flag standing.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

DISPATCH = pathlib.Path(__file__).resolve().parents[1] / "dispatch.py"
STEM = "block_away_questions"
SINCE = "2026-11-08T20:00:00.000000Z"
AFTER = "2026-11-08T20:05:00.000Z"
BEFORE = "2026-11-08T19:55:00.000Z"


def _user(content, ts=AFTER, **extra):
    return {
        "type": "user",
        "timestamp": ts,
        "message": {"role": "user", "content": content},
        **extra,
    }


def _queued(prompt, ts=AFTER):
    return {
        "type": "attachment",
        "timestamp": ts,
        "attachment": {"type": "queued_command", "prompt": prompt},
    }


def _run(tmp_path, records, flag=True, sibling=None):
    state = tmp_path / "away.json"
    if flag:
        state.write_text(json.dumps({"since": SINCE, "note": "test"}))
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("".join(json.dumps(r) + "\n" for r in records))
    if sibling is not None:
        (tmp_path / "sibling.jsonl").write_text("".join(json.dumps(r) + "\n" for r in sibling))
    payload = {
        "transcript_path": str(transcript),
        "tool_input": {
            "questions": [
                {"question": "Which bucket should the restore test use?", "header": "Bucket"}
            ]
        },
    }
    env = dict(os.environ, WL_AWAY_STATE=str(state), HOME=str(tmp_path), TMPDIR=str(tmp_path))
    proc = subprocess.run(
        ["python3", str(DISPATCH), STEM],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    return proc, state


SAME_MS = "2026-11-08T20:00:00.000Z"

STILL_AWAY = [
    ("a record in the flag's own millisecond", [_user("go on", ts=SAME_MS)]),
    (
        "a malformed attachment",
        [{"type": "attachment", "timestamp": AFTER, "attachment": "queued_command"}],
    ),
    ("a malformed message", [{"type": "user", "timestamp": AFTER, "message": "hello"}]),
    ("no record after the flag", [_user("go on", ts=BEFORE)]),
    (
        "the /awk invocation itself",
        [_user("<command-message>awk</command-message>\n<command-name>/awk</command-name>")],
    ),
    ("/awk queued mid-turn", [_queued("/awk")]),
    ("a task notification", [_user("<task-notification>\n<task-id>b1</task-id>")]),
    (
        "the compaction summary",
        [
            _user(
                "This session is being continued from a previous conversation that ran out of context."
            )
        ],
    ),
    ("hook feedback", [_user("Stop hook feedback: do not stop", isMeta=True)]),
    ("a tool result", [_user([{"type": "tool_result", "tool_use_id": "t1", "content": "rc=0"}])]),
]

BACK = [
    ("a typed turn", [_user("morning, status?")]),
    ("an interrupt", [_user([{"type": "text", "text": "[Request interrupted by user]"}])]),
    ("a message queued mid-turn", [_queued("also look at the bench deploy")]),
]


def main():
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        for i, (label, records) in enumerate(STILL_AWAY):
            d = root / ("away%d" % i)
            d.mkdir()
            proc, state = _run(d, records)
            if (
                proc.returncode == 0
                or "away from the keyboard" not in proc.stderr
                or "--defer" not in proc.stderr
            ):
                fails.append(
                    "still away / %s: admitted or wrong message (rc=%d) %s"
                    % (label, proc.returncode, proc.stderr[-200:])
                )
            elif not state.exists():
                fails.append("still away / %s: the flag was cleared" % label)
        for i, (label, records) in enumerate(BACK):
            d = root / ("back%d" % i)
            d.mkdir()
            proc, state = _run(d, records)
            if proc.returncode != 0:
                fails.append(
                    "back / %s: refused after the operator spoke (rc=%d)" % (label, proc.returncode)
                )
            elif state.exists():
                fails.append("back / %s: the flag survived the operator's message" % label)
        d = root / "noflag"
        d.mkdir()
        proc, _ = _run(d, [], flag=False)
        if proc.returncode != 0:
            fails.append("no flag: refused (rc=%d)" % proc.returncode)
        d = root / "badflag"
        d.mkdir()
        (d / "away.json").write_text("{not json")
        proc, _ = _run(d, [], flag=False)
        if proc.returncode != 0:
            fails.append("unparseable flag: refused (rc=%d)" % proc.returncode)
        d = root / "sibling"
        d.mkdir()
        proc, state = _run(d, [], sibling=[_user("answered in the other session")])
        if proc.returncode != 0 or state.exists():
            fails.append(
                "sibling: the operator's word to another session left the flag standing (rc=%d)"
                % proc.returncode
            )
        d = root / "sibling-busy"
        d.mkdir()
        filler = [
            _user([{"type": "tool_result", "tool_use_id": "t", "content": "x" * 4096}])
            for _ in range(1300)
        ]
        proc, state = _run(d, [], sibling=[_user("answered in the other session"), *filler])
        if proc.returncode != 0 or state.exists():
            fails.append(
                "sibling-busy: a reply followed by 5 MB of the sibling's records was missed (rc=%d)"
                % proc.returncode
            )
        d = root / "sibling-quiet"
        d.mkdir()
        proc, state = _run(d, [], sibling=[_user("<task-notification> x")])
        if proc.returncode == 0 or not state.exists():
            fails.append(
                "sibling-quiet: a notification in another session ended the mode (rc=%d)"
                % proc.returncode
            )
    total = len(STILL_AWAY) + len(BACK) + 5
    for f in fails:
        print("FAIL " + f)
    print("%d of %d case(s) passed" % (total - len(fails), total))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
