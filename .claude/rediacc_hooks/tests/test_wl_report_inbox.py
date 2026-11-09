"""Ported from `.claude/hooks/stop/test-report-inbox.sh`.

Tests for `wl_report.py` (durable sub-agent report capture plus the unread inbox). The `wl_wait.py` waiter cases (15-22, 25, 25b) were removed with cross-session messaging on 2026-09-24.

EVERY CASE ASSERTS ITS NEGATION TOO. A gate that cannot fail is worthless, and an empty output is only meaningful once a non-empty one has been demonstrated from the same fixture. Where a case has a control it is named `control` and counts like any other assertion, so a control that stops discriminating turns this module red rather than quietly passing.

THE AMBIENT SCRUB is inherited from `wlfix.scrubbed_environ`, and it has the same sharp edge here that it has there. Since v19 every `<me>` argument is checked against the real session id, which resolves WORKLIST_SESSION_ID first and CLAUDE_CODE_SESSION_ID second. Run from inside a Claude session with the ambient id live, this suite's fixture readers (aaaaaaaa, bbbbbbbb, cccccccc)
all mismatch and 16 cases fail; run with it unset, the check silently passes and those cases prove nothing about identity at all. Measured, not predicted: 16 reds locally, green in CI, from one missing unset. `test_28_...` below is the control that proves the scrub ran.

AN ISOLATED UNIVERSE PER CASE. TMPDIR moves the worklist, CLAUDE_CONFIG_DIR moves the projects tree that `--scan` walks, WORKLIST_REPORTS_DIR moves the store, and CLAUDE_PROJECT_DIR moves the repo root the slug derives from. Together they mean a case cannot see, or damage, the live session's worklist, which is running right now.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix

HERE = wlfix.STOP_DIR
READER = "aaaaaaaa-1111"
BIG = "a substantive body. " * 40


class Scratch:
    """One scratch universe, the pytest shape of the bash `scratch` function."""

    def __init__(self, base: pathlib.Path):
        self.t = base
        for rel in ("tmp", "store", "claude/projects", "repo"):
            (self.t / rel).mkdir(parents=True, exist_ok=True)
        # A FILE, like a worktree's: `C.project_root` tests existence.
        (self.t / "repo" / ".git").write_text("", encoding="utf-8")
        self.handles: list = []
        self.env = wlfix.scrubbed_environ()
        self.env.update(
            {
                "TMPDIR": str(self.t / "tmp"),
                "CLAUDE_CONFIG_DIR": str(self.t / "claude"),
                "WORKLIST_REPORTS_DIR": str(self.t / "store"),
                "CLAUDE_PROJECT_DIR": str(self.t / "repo"),
                "WORKLIST_AGENT_BRANCH": "testbr",
                # The DEFAULT reader, matching this suite's default fixture session. Cases acting as a PEER declare that peer's id per call rather than relying on this.
                "WORKLIST_SESSION_ID": READER,
            }
        )

    @property
    def repo(self) -> pathlib.Path:
        return self.t / "repo"

    @property
    def store(self) -> pathlib.Path:
        return self.t / "store"

    @property
    def index(self) -> pathlib.Path:
        return self.store / "index.jsonl"

    def index_lines(self) -> list[str]:
        return self.index.read_text(encoding="utf-8").splitlines()

    def index_text(self) -> str:
        return self.index.read_text(encoding="utf-8")

    def subagents_dir(self, session: str = "sess1") -> pathlib.Path:
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.repo))
        path = self.t / "claude" / "projects" / slug / session / "subagents"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def worklist(self) -> pathlib.Path:
        """The fixture worklist path, resolved under the SCRATCH TMPDIR.

        `wl_core.worklist_for` reads TMPDIR from the ambient environment, which in the bash suite was the case's own because `scratch` exported it. In-process it is the pytest runner's, so the variable is swapped for the length of the call rather than the formula being copied: a second copy of the slug rule would drift from the one under test.
        """
        core = wlfix.import_wl("wl_core")
        previous = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = self.env["TMPDIR"]
        try:
            return pathlib.Path(core.worklist_for(str(self.repo)))
        finally:
            if previous is None:
                os.environ.pop("TMPDIR", None)
            else:
                os.environ["TMPDIR"] = previous

    def stem(self, suffix: str) -> pathlib.Path:
        text = str(self.worklist())
        return pathlib.Path(text[: -len(".md")] + suffix)

    def py(self, script: str, *argv: str, env: dict | None = None, stdin: str = ""):
        proc = subprocess.run(
            [sys.executable, str(HERE / script), *argv],
            input=stdin,
            capture_output=True,
            text=True,
            env=dict(env or self.env),
            check=False,
        )
        return wlfix.Result(proc.stdout, proc.stderr, proc.returncode)

    def report_py(self, *argv: str, env: dict | None = None, stdin: str = ""):
        return self.py("wl_report.py", *argv, env=env, stdin=stdin)

    def stop_event(self, agent_id: str, agent_type: str, body: str, env: dict | None = None):
        """A SubagentStop payload on stdin."""
        used = dict(env or self.env)
        payload = json.dumps(
            {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "session_id": READER,
                "cwd": used["CLAUDE_PROJECT_DIR"],
                "agent_transcript_path": "",
                "last_assistant_message": body,
            }
        )
        return self.report_py("--subagent-stop", env=used, stdin=payload)

    def raw_stop(self, payload: dict, env: dict | None = None):
        """A SubagentStop payload the case composes itself, keys and all."""
        return self.report_py("--subagent-stop", env=env, stdin=json.dumps(payload))

    def surface_as(self, session_id: str, mode: str, source: str, env: dict | None = None) -> str:
        used = dict(env or self.env)
        payload = json.dumps(
            {"cwd": used["CLAUDE_PROJECT_DIR"], "session_id": session_id, "source": source}
        )
        return self.report_py(mode, env=used, stdin=payload).out

    def surface(self, mode: str, source: str, env: dict | None = None) -> str:
        """The default reader, for cases that do not care which session is looking."""
        return self.surface_as(READER, mode, source, env=env)

    def close_handles(self) -> None:
        for handle in self.handles:
            with contextlib.suppress(OSError):
                handle.close()
        self.handles = []


def body_of(path: pathlib.Path) -> str:
    """The captured body, past the front matter."""
    return path.read_text(encoding="utf-8").split("---\n\n", 1)[1]


def one_body(sc: Scratch, needle: str) -> pathlib.Path:
    """The single stored body file whose name carries `needle`."""
    found = sorted((sc.store / "testbr").glob("*%s*.md" % needle))
    assert found, "no body file matching *%s*.md under %s" % (needle, sc.store / "testbr")
    return found[0]


def longest_line(path: pathlib.Path) -> int:
    """The longest index line INCLUDING its newline, as the bash awk counted it."""
    return max(len(line) + 1 for line in path.read_text(encoding="utf-8").splitlines())


def test_06_capture_substantive_versus_silent(sc):
    sc.stop_event("asome-agent-1111222233334444", "some-agent", "TITLE LINE\n" + BIG)
    sc.stop_event("aquiet-one-5555666677778888", "quiet-one", "")
    lines = sc.index_lines()
    assert len(lines) == 2, "one line per capture, got %d" % len(lines)
    assert '"silent":false' in lines[0], lines[0]
    assert '"title":"TITLE LINE"' in lines[0], lines[0]
    # CONTROL: the silent flag must actually be able to take the other value, or the assertion above is satisfied by a field that is hard-coded false.
    assert '"silent":true' in lines[1], lines[1]
    stored = one_body(sc, "some-agent")
    # THE BASH COMPARED A LENGTH WITH ITSELF here (both sides printed the whole file's length), so it could not fail. The property it meant to assert is this one: the stored body carries the message verbatim and entire, under the capture's own heading.
    assert ("TITLE LINE\n" + BIG).strip() in body_of(stored), body_of(stored)[:200]
    assert "TITLE LINE" in stored.read_text(encoding="utf-8")
    widest = longest_line(sc.index)
    assert widest < 1024, "index line %d bytes, over the atomic cap" % widest


def test_06b_a_huge_body_still_yields_a_capped_index_line(sc):
    huge = sc.t / "huge.txt"
    huge.write_text("X" * 400000, encoding="utf-8")
    sc.stop_event("ahuge-agent-9999888877776666", "huge-agent", huge.read_text(encoding="utf-8"))
    widest = longest_line(sc.index)
    assert widest < 1024, "400 KB body gave a %d-byte index line" % widest
    # Counted in the BODY ONLY, past the front matter: a whole-file count also caught the word EXIST in the front-matter marker and read 400001.
    assert body_of(one_body(sc, "huge-agent")).count("X") == 400000, "the body was truncated"
    # CONTROL: the cap is enforced by shrinking values, never by dropping keys.
    assert '"transcript"' in sc.index_text(), "a key was dropped to fit"
    assert '"title"' in sc.index_text(), "the title key was dropped to fit"


def test_06c_the_cap_holds_when_the_oversize_is_not_the_title(sc):
    """6b does NOT exercise the cap: the title is truncated to TITLE_MAX before the line is ever built, so a 400 KB body yields a short line no matter what `_fit` does (disabling `_fit` leaves 6b green, verified by mutation). The cap only has real work when some OTHER field is long. Deep worktree paths make that concrete rather than theoretical; the bash suite tripped
    ENAMETOOLONG on its own first run."""
    sc.raw_stop(
        {
            "agent_id": "along-path-agent-3131313131313131",
            "agent_type": "T" * 300,
            "session_id": READER,
            "cwd": str(sc.repo),
            "agent_transcript_path": "/" + "d" * 3000 + "/agent.jsonl",
            "last_assistant_message": "A REAL TITLE\n" + "body. " * 200,
        }
    )
    widest = longest_line(sc.index)
    assert widest < 1024, (
        "a 3 KB transcript path gave %d bytes, so an atomic append is no longer guaranteed" % widest
    )
    text = sc.index_text()
    assert '"transcript"' in text, "CONTROL: the transcript KEY did not survive the shrink"
    assert '"title"' in text, "CONTROL: the title KEY did not survive the shrink"
    # The id is the LAST 12 characters of the agent id, so the 16-char hex suffix above yields exactly 12 of them.
    assert '"id":"313131313131"' in text, "CONTROL: the id is not intact"
    assert json.loads(sc.index_lines()[0])["ev"] == "report", "the line is not valid JSON"


def test_08_index_atomicity_under_fifty_concurrent_writers(sc):
    """Validates the no-lock choice.

    The counter must vary within the LAST 12 characters: `short_id` is the id's TAIL (a leading truncation would collide on same-named teammates), so ids differing only in a prefix would all fold to one id and 49 of these would be dropped as duplicates, which is what the first draft of this case did, and it looked exactly like a lost-append bug.
    """
    procs = []
    for index in range(50):
        payload = json.dumps(
            {
                "agent_id": "aconc-%016d" % index,
                "agent_type": "conc",
                "session_id": READER,
                "cwd": str(sc.repo),
                "agent_transcript_path": "",
                "last_assistant_message": "concurrent body number %d, long enough to matter %s"
                % (index, BIG),
            }
        )
        procs.append(
            subprocess.Popen(
                [sys.executable, str(HERE / "wl_report.py"), "--subagent-stop"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=dict(sc.env),
                text=True,
            )
        )
        stdin = procs[-1].stdin
        assert stdin is not None, "Popen(stdin=PIPE) always opens a pipe"
        stdin.write(payload)
        stdin.close()
    for proc in procs:
        proc.wait()
    lines = sc.index_lines()
    assert len(lines) == 50, "all 50 lines present, got %d" % len(lines)
    parseable = 0
    for line in lines:
        try:
            json.loads(line)
            parseable += 1
        except ValueError:
            pass
    assert parseable == 50, "%d of 50 lines parseable, so appends interleaved" % parseable


def test_09_branch_keying(sc):
    sc.stop_event("abr-one-1111111111111111", "br-one", "on branch one " + BIG)
    other = dict(sc.env, WORKLIST_AGENT_BRANCH="otherbr")
    sc.stop_event("abr-two-2222222222222222", "br-two", "on branch two " + BIG, env=other)
    dirs = [path for path in sc.store.glob("*br") if path.is_dir()]
    assert len(dirs) == 2, "bodies did not land in separate branch dirs: %s" % dirs
    lines = sc.index_lines()
    assert '"branch":"testbr"' in lines[0], lines[0]
    assert '"branch":"otherbr"' in lines[1], lines[1]


def test_10_surfacing_read_marks_and_the_compaction_rule(sc):
    sc.stop_event("asurf-one-1212121212121212", "surf-one", "SURFACED TITLE\n" + BIG)
    out = sc.surface("--session-start", "startup")
    assert "SURFACED TITLE" in out, out[:300]
    assert "--show" in out, "surfacing does not name the --show command"
    assert "additionalContext" in out, "not emitted as additionalContext"
    rid = json.loads(sc.index_lines()[0])["id"]
    sc.report_py("--read", "aaaaaaaa", rid)
    # The empty half is only meaningful because the non-empty half above ran first.
    assert sc.surface("--session-start", "startup") == "", (
        "CONTROL: marked read by THIS reader, SessionStart must emit nothing"
    )

    # 10b. READ MARKS ARE PER-READER, KEYED ON SESSION ID (an operator decision, which OVERRODE this design's own branch-level recommendation). This is the case the decision exists for, so it is the one that must be provably able to fail: session A marking a report read must NOT hide it from its live peer B. The rejected alternative, one ledger per branch, means B never learns the
    # report existed, which is a quieter restatement of the failure this whole feature fixes. Two concurrent sessions per worktree is this repo's normal state, so it is not a corner case.
    assert "SURFACED TITLE" in sc.surface_as("bbbbbbbb-2222", "--session-start", "startup")
    # As the PEER, declared rather than asserted by hand: since v19 a read mark filed under an identity the caller is not is refused, because it clears nothing for the reader who filed it and hides the report from nobody.
    peer = dict(sc.env, WORKLIST_SESSION_ID="bbbbbbbb-2222")
    sc.report_py("--read", "bbbbbbbb", rid, env=peer)
    assert sc.surface_as("bbbbbbbb-2222", "--session-start", "startup") == "", (
        "CONTROL: the peer's own mark must clear it for the peer"
    )
    # The ACCEPTED COST, asserted so nobody later "fixes" it: a restarted session is a different reader (`same_session` matches by PREFIX) and re-sees the report. That resurfacing IS the compaction-recovery case working.
    assert "SURFACED TITLE" in sc.surface_as("cccccccc-3333", "--session-start", "startup"), (
        "a fresh reader must re-see the branch's reports"
    )
    # CONTROL: proves the emitter can still fire for reader A too, so the empty above is a read mark working and not a surfacing path that is dead.
    sc.stop_event("asurf-two-3434343434343434", "surf-two", "SECOND TITLE\n" + BIG)
    out = sc.surface("--session-start", "startup")
    assert "SECOND TITLE" in out, "CONTROL: a NEW report must still surface to reader A"
    assert "SURFACED TITLE" not in out, "CONTROL: the one A read must stay suppressed for A"
    # Branch isolation: a report captured on testbr is not another branch's business, whoever is reading.
    elsewhere = dict(sc.env, WORKLIST_AGENT_BRANCH="elsewhere")
    assert sc.surface("--session-start", "startup", env=elsewhere) == "", (
        "reports leaked across branches"
    )
    # 11: SessionStart declines source=compact; PostCompact is what emits there.
    assert sc.surface("--session-start", "compact") == "", "SessionStart spoke on source=compact"
    assert "SECOND TITLE" in sc.surface("--post-compact", "compact"), (
        "CONTROL: PostCompact must emit on the same fixture"
    )


def plant_sender_agent(sc: Scratch) -> None:
    """One indexed agent whose report travelled by SendMessage rather than by sign-off.

    RELATIVE TIMESTAMPS, NOT ABSOLUTE. These records carried "2026-08-05T10:00:00.500Z" and the case went red on 2026-09-04 with no code change: `scan()` captures the body and then prunes every body whose `at` is older than RETENTION_DAYS (30), so on the calendar day the fixture aged past the window, `--show` reported the body gone and both body assertions failed. A fixture whose
    date is a constant walks across a retention window on its own.
    """
    proj = sc.subagents_dir()
    aid = "asender-7777777777777777"
    (proj / ("agent-%s.meta.json" % aid)).write_text(
        json.dumps({"agentType": "sender", "name": "sender", "taskKind": "in_process_teammate"}),
        encoding="utf-8",
    )
    start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=10)

    def stamp(minutes: int) -> str:
        return (start + datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.500Z")

    records = [
        {
            "type": "assistant",
            "agentId": aid,
            "sessionId": "sess1",
            "gitBranch": "testbr",
            "timestamp": stamp(0),
            "cwd": str(sc.repo),
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "SendMessage",
                        "input": {
                            "to": "team-lead",
                            "summary": "the report",
                            "message": "THE ACTUAL REPORT\n" + "detail. " * 200,
                        },
                    }
                ]
            },
        },
        {
            "type": "assistant",
            "agentId": aid,
            "sessionId": "sess1",
            "gitBranch": "testbr",
            "timestamp": stamp(1),
            "cwd": str(sc.repo),
            "message": {"content": [{"type": "text", "text": "Released. Task complete."}]},
        },
    ]
    path = proj / ("agent-%s.jsonl" % aid)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    old = time.time() - 3600
    os.utime(path, (old, old))


def test_12_sendmessage_payloads_are_the_report_not_the_signoff(sc):
    plant_sender_agent(sc)
    scan = sc.report_py("--scan").out
    assert "sender" in scan, "scan did not index the agent: %s" % scan[:300]
    assert "THE ACTUAL REPORT" in scan, "the title did not come from the SendMessage"
    assert "Released. Task complete." not in scan, "the sign-off became the title"
    rid = json.loads(sc.index_lines()[0])["id"]
    body = sc.report_py("--show", rid).out
    assert "THE ACTUAL REPORT" in body, body[:300]
    assert "Released. Task complete." in body, "the body dropped the sign-off"
    # CONTROL: WITHOUT the SendMessage harvest this agent reads as silent (24 characters of sign-off is under the 200-character floor). This is the whole finding.
    assert '"silent":false' in sc.index_text(), (
        "CONTROL: an agent that only SendMessages must NOT be silent"
    )


def test_12_control_the_same_signoff_with_no_sends_is_silent(sc):
    sc.stop_event("abare-signoff-4444444444444444", "bare", "Released. Task complete.")
    assert '"silent":true' in sc.index_text(), "CONTROL: a bare sign-off with no sends IS silent"


def test_12b_one_poisoned_agent_must_not_starve_the_pass(sc):
    """The review finding this pins: `scan()`'s per-agent capture was not isolated, so a single entry that raised killed the loop before it reached anything sorted AFTER it, and because a failed entry is never recorded as `known`, the next scan hit the same wall at the same place. The self-heal starved permanently and silently.

    Ordering is load-bearing: `scan()` walks sorted(), so the poison must sort BEFORE the good agent or this proves nothing ("apoison" sorts before "bgood").

    THE POISON WAS ARRIVED AT BY ELIMINATION, worth recording so nobody re-walks it: a >255-byte id fails the WRITE during setup, so the case tests nothing; a giant agentType does NOT poison, because `_fit`'s last-resort stage shrinks the agent field too and the entry captures cleanly. So the poison is a transcript that EXISTS and STATS like a file but cannot be read: a directory
    named agent-*.jsonl. exists() and stat() both succeed, the idle check passes, and `harvest_transcript` raises IsADirectoryError, a real read failure rather than a size one, and independent of permissions (a chmod 000 poison would evaporate under a root-run CI).
    """
    proj = sc.subagents_dir()
    stamp = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M:%S.500Z"
    )
    old = time.time() - 3600
    pid = "apoison-1111111111111111"
    (proj / ("agent-%s.meta.json" % pid)).write_text(
        json.dumps({"agentType": "POISONAGENT"}), encoding="utf-8"
    )
    poison = proj / ("agent-%s.jsonl" % pid)
    poison.mkdir()
    os.utime(poison, (old, old))

    aid = "bgood-5555555555555555"
    (proj / ("agent-%s.meta.json" % aid)).write_text(
        json.dumps({"agentType": "goodagent", "name": "goodagent"}), encoding="utf-8"
    )
    good = proj / ("agent-%s.jsonl" % aid)
    good.write_text(
        json.dumps(
            {
                "type": "assistant",
                "agentId": aid,
                "sessionId": "sess1",
                "gitBranch": "testbr",
                "timestamp": stamp,
                "cwd": str(sc.repo),
                "message": {
                    "content": [{"type": "text", "text": "GOOD AGENT REPORT " + "detail. " * 40}]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    os.utime(good, (old, old))

    scan = sc.report_py("--scan").out
    assert "goodagent" in scan, "the agent sorted AFTER the poison was not indexed"
    # WHAT AN UNREADABLE TRANSCRIPT ACTUALLY DOES, established by elimination rather than assumed: it does NOT raise. `harvest_transcript` absorbs the read failure, so the entry is indexed with an empty body and flagged silent. Both agents therefore index, and the pass completes. That makes the `except Exception: continue` in `scan()` DEFENSIVE rather than load-bearing for this
    # input. This case pins the property that matters and can be observed from outside, that a problematic entry does not cost the entries sorted after it, and deliberately does NOT claim to exercise the except arm. A control that asserted the poison vanished would be asserting something false.
    assert len(sc.index_lines()) == 2, "the bad entry cost more than itself"
    assert '"silent":true' in sc.index_text(), (
        "the unreadable transcript must index as silent, not as an abort"
    )


def test_13_scan_skips_a_still_running_agent(sc):
    proj = sc.subagents_dir("s")
    aid = "arunning-6666666666666666"
    (proj / ("agent-%s.meta.json" % aid)).write_text(
        json.dumps({"agentType": "running"}), encoding="utf-8"
    )
    (proj / ("agent-%s.jsonl" % aid)).write_text(
        json.dumps(
            {
                "type": "assistant",
                "agentId": aid,
                "gitBranch": "testbr",
                "message": {"content": [{"type": "text", "text": "half an answer so far"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert "nothing to index" in sc.report_py("--scan").out, "a fresh transcript was indexed"
    # CONTROL: the same fixture, backdated, IS indexed, so the skip is the idle rule and not a scan that simply cannot see the directory.
    old = time.time() - 3600
    os.utime(proj / ("agent-%s.jsonl" % aid), (old, old))
    assert "running" in sc.report_py("--scan").out, "CONTROL: backdated, the agent must index"


def test_13b_the_harness_roster_outranks_mtime(sc):
    """WHAT CASE 13 CANNOT SEE, and why this is a separate case rather than another arm of it. Case 13 varies exactly ONE thing, mtime, and both of its arms AGREE with the mtime oracle, so it is a faithful test of the rule that was implemented and structurally blind to that rule being wrong. The defect lives in the one quadrant no fixture in this suite had ever built: STALE MTIME
    AND STILL ALIVE. An agent blocked in a single Bash call is silent by construction for the length of that call, so on 2026-09-07 two live agents (one waiting on check:ci-pytest at 661s in this repo's own receipt, one on the bash gate battery at 606s) sailed past the idle check and were captured mid-thought.

    AND THE COST IS A LOST REPORT, not a premature row: `capture()` returns None once an id is indexed, so the mid-flight row PERMANENTLY shadows the real report that arrives at SubagentStop. The half-answer becomes the only artifact that ever exists.

    THE JOIN IS THE WHOLE CLAIM, verified live before this was written: for a type:"subagent" entry the harness's background_tasks[].id is BYTE-IDENTICAL to the transcript's agent-<id>.jsonl stem. If that convention ever changes this case goes red, which is exactly what should happen.
    """
    proj = sc.subagents_dir("s")
    old = time.time() - 3600
    # Both agents are IDENTICAL in every respect the mtime oracle can see: same shape, same body length, same backdated mtime. The ONLY difference between them is the roster. That is what makes this a test of the new oracle and not accidentally a test of something else.
    for aid, atype in (
        ("alive-7777777777777777", "liveagent"),
        ("adone-8888888888888888", "doneagent"),
    ):
        (proj / ("agent-%s.meta.json" % aid)).write_text(
            json.dumps({"agentType": atype}), encoding="utf-8"
        )
        path = proj / ("agent-%s.jsonl" % aid)
        path.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "agentId": aid,
                    "gitBranch": "testbr",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "Now I have the full picture. Let me write the CLI. " * 8,
                            }
                        ]
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        os.utime(path, (old, old))

    # The sidecar `wl_checks.py` writes on every full stop, planted where `C.worklist_for(start)` looks.
    wldir = pathlib.Path(sc.env["TMPDIR"]) / "claude-worklist"
    wldir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(sc.repo)).strip("_")
    (wldir / (slug + ".lastevent-aaaaaaaa.json")).write_text(
        json.dumps(
            {
                "session_id": READER,
                "background_tasks": [
                    # RUNNING, joined to the transcript by id alone.
                    {
                        "id": "alive-7777777777777777",
                        "type": "subagent",
                        "status": "running",
                        "description": "blocked in a 661s gate",
                    },
                    # A FINISHED peer in the SAME roster: proves the filter is `status`, not "appears in background_tasks at all".
                    {
                        "id": "adone-8888888888888888",
                        "type": "subagent",
                        "status": "completed",
                        "description": "finished",
                    },
                    # A RUNNING SHELL task: proves the filter is also `type`, so a shell id can never mask an agent.
                    {
                        "id": "b701wk0zr",
                        "type": "shell",
                        "status": "running",
                        "command": "sleep 900",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    out = sc.report_py("--scan").out
    assert "liveagent" not in out, "a harness-RUNNING agent was indexed despite a stale mtime"
    # THE CONTROL THAT MAKES THIS NON-VACUOUS: the identical fixture beside it, differing ONLY in `status`, IS indexed. Without it, "lacks liveagent" is satisfied by a scan that saw nothing at all.
    assert "doneagent" in out, "CONTROL: the identical twin marked completed must be indexed"
    assert len(sc.index_lines()) == 1, "exactly one of the two should have been captured"
    # STALENESS OF THE ROSTER RELEASES THE HOLD. A dead session's sidecar freezes with its tasks still "running"; if that protected an id forever the self-heal `scan()` exists for would starve permanently and silently. SCAN_LIVE_MIN=0 ages every sidecar out, so mtime decides, which is exactly the pre-fix behaviour.
    aged = dict(sc.env, WORKLIST_REPORT_SCAN_LIVE_MIN="0")
    assert "liveagent" in sc.report_py("--scan", env=aged).out, (
        "CONTROL: a STALE roster must release the hold"
    )


def test_13b_control_with_no_roster_the_scan_still_self_heals_and_names_its_blindness(sc):
    """BLINDNESS IS REPORTED, NOT SILENTLY ASSUMED HEALTHY. With no sidecar at all (a wiped TMPDIR, a fresh worktree, CI) the oracle cannot see, and a check that cannot fail must say so. It must ALSO still capture: skipping everything is fail-OFF, not fail-open, and would make `scan()` a permanent no-op."""
    proj = sc.subagents_dir("s")
    aid = "ablind-999999999999999"
    (proj / ("agent-%s.meta.json" % aid)).write_text(
        json.dumps({"agentType": "blindagent"}), encoding="utf-8"
    )
    path = proj / ("agent-%s.jsonl" % aid)
    path.write_text(
        json.dumps(
            {
                "type": "assistant",
                "agentId": aid,
                "gitBranch": "testbr",
                "message": {"content": [{"type": "text", "text": "a finished report " * 20}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    old = time.time() - 3600
    os.utime(path, (old, old))
    out = sc.report_py("--scan").out
    assert "blindagent" in out, "with no roster the scan must still self-heal"
    assert "BLIND" in out, "the scan must NAME its blindness rather than looking healthy"


def test_14_a_torn_index_tail(sc):
    sc.stop_event("atorn-one-8888888888888888", "torn-one", "a real report " + BIG)
    with sc.index.open("a", encoding="utf-8") as handle:
        handle.write('{"ev":"report","id":"trunc')  # no newline, no close
    listing = sc.report_py("--list", "--all").out
    assert "torn-one" in listing, "a torn tail hid the good line"
    assert "trunc" not in listing, "the torn line itself was not skipped"
    assert "a real report" in sc.surface("--session-start", "startup"), (
        "surfacing did not survive a torn tail"
    )


def test_23_a_transcript_path_that_does_not_resolve_is_recorded_as_absent(sc):
    """Found in LIVE USE, not by the suite: a SubagentStop fired carrying a well-formed transcript path to a file that was never written. The agent here is TYPED on purpose, because a typeless one with no transcript is a phantom and is refused outright (case 26), so a typed agent is what still exercises this. Every other fixture writes its transcript first, so 74 of 74 passed
    while this was broken. A stored path that silently does not exist is worse than a null: readers treat it as readable and quietly get nothing."""
    sc.raw_stop(
        {
            "agent_id": "aghost-agent-7171717171717171",
            "agent_type": "ghost-agent",
            "session_id": READER,
            "cwd": str(sc.repo),
            "agent_transcript_path": "/nonexistent/dir/agent-aghost.jsonl",
            "last_assistant_message": "push it when the agent reports back",
        }
    )
    assert '"tx":"absent"' in sc.index_text(), "the unresolved path was not flagged"
    # The filename comes from the index rather than a guess, so this case does not break again if the name-fallback rules change.
    ghost = sc.store / json.loads(sc.index_lines()[0])["body"]
    text = ghost.read_text(encoding="utf-8")
    assert "push it when the agent reports back" in text, "the body did not survive"
    assert "DID NOT EXIST AT CAPTURE TIME" in text, "the body file does not say the path was absent"
    # CONTROL: a resolvable path is recorded ok, so the flag is not hard-coded.
    real = sc.t / "real.jsonl"
    real.write_text(
        json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "a real body"}]}}
        )
        + "\n",
        encoding="utf-8",
    )
    sc.raw_stop(
        {
            "agent_id": "areal-agent-8181818181818181",
            "agent_type": "real",
            "session_id": READER,
            "cwd": str(sc.repo),
            "agent_transcript_path": str(real),
            "last_assistant_message": "a real body",
        }
    )
    assert '"tx":"ok"' in sc.index_lines()[1], "CONTROL: a resolvable transcript must record ok"


def test_24_worklist_reports_forwards_modifiers_instead_of_rejecting_them(sc):
    """A peer hit this following the broadcast that announced it: `--all` was documented in the announcement and the dispatcher answered "unknown mode --all" (exit 2)."""
    sc.stop_event("adisp-agent-9191919191919191", "disp", "a report for the dispatcher " + BIG)
    got = sc.py("worklist.py", "--reports", "--all")
    assert got.rc == 0, "--reports --all should exit 0, got %d" % got.rc
    assert "disp" in got.out + got.err, "--reports --all did not list the report"
    assert "unknown mode" not in got.out + got.err, "it was rejected as a mode"
    got = sc.py("worklist.py", "--reports", "--unread")
    assert "disp" in got.out + got.err, "--reports --unread does not work"
    # CONTROL: a genuine mode is still dispatched as a mode, not as a modifier.
    got = sc.py("worklist.py", "--reports", "--scan")
    assert "unknown mode" not in got.out + got.err, (
        "CONTROL: a real mode must still dispatch as one"
    )


def test_26_a_main_loop_turn_is_not_captured_as_a_report(sc):
    """THE LOOP THIS CLOSES, found by running the thing rather than testing it. SubagentStop also fires for the session's OWN main-loop turns. Each was captured as a "report"; the (since removed) waiter saw a new report and fired; the session spent a turn reading and re-arming; that turn was captured; the waiter fired again. It does not converge, and every cycle costs the exact turn the waiter
    exists to save. Measured on the live store: 44 of 181 records were these."""
    # A phantom: no agent_type AND a transcript that does not resolve.
    sc.raw_stop(
        {
            "agent_id": "aphantom0000111122223",
            "agent_type": "",
            "session_id": READER,
            "cwd": str(sc.repo),
            "agent_transcript_path": "/nonexistent/subagents/agent-aphantom.jsonl",
            "last_assistant_message": "push it when the agent reports back",
        }
    )
    assert not sc.index.exists() or sc.index.stat().st_size == 0, "the phantom was indexed: %s" % (
        sc.index_text() if sc.index.exists() else ""
    )
    # REJECTS ONLY WHEN BOTH SIGNALS FAIL. These two controls are the whole reason the predicate is an AND: either signal alone would drop a real report. CONTROL A: a real agent whose transcript has not flushed yet still has a TYPE.
    sc.raw_stop(
        {
            "agent_id": "aracer-agent-2222333344445555",
            "agent_type": "some-agent",
            "session_id": READER,
            "cwd": str(sc.repo),
            "agent_transcript_path": "/nonexistent/subagents/agent-aracer.jsonl",
            "last_assistant_message": "a real report whose transcript has not landed yet",
        }
    )
    assert "some-agent" in sc.index_text(), "CONTROL: a TYPED agent must survive an unresolved path"
    # CONTROL B: a typeless agent that DOES have a transcript still survives.
    tx = sc.t / "tx.jsonl"
    tx.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "typeless but real"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sc.raw_stop(
        {
            "agent_id": "atypeless-6666777788889999",
            "agent_type": "",
            "session_id": READER,
            "cwd": str(sc.repo),
            "agent_transcript_path": str(tx),
            "last_assistant_message": "typeless but real",
        }
    )
    assert "typeless" in sc.index_text(), "CONTROL: a TRANSCRIPTED agent must survive an empty type"
    assert len(sc.index_lines()) == 2, "exactly the phantom should have been rejected"
    # And the phantom must not reach the surfaced inbox either.
    assert "push it when the agent reports back" not in sc.surface("--session-start", "startup"), (
        "the phantom surfaced"
    )


def test_27_retire_phantoms_removes_existing_ones_and_keeps_the_real_reports(sc):
    """The filter stops NEW phantoms; 44 were already in the live index and would have kept surfacing as unread forever. Retirement is an APPENDED event, never an edit: the append-only log is what makes the lock-free single-write design sound, and rewriting lines to remove them would trade that away for tidiness."""
    sc.stop_event("areal-one-1010101010101010", "real-one", "a genuine report " + BIG)
    sc.raw_stop(
        {
            "agent_id": "aphantom2-444455556666",
            "agent_type": "",
            "session_id": READER,
            "cwd": str(sc.repo),
            "agent_transcript_path": "/nonexistent/agent-x.jsonl",
            "last_assistant_message": "a main loop turn",
        }
    )
    # Force a legacy phantom in directly, as if captured before the filter existed.
    with sc.index.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ev": "report",
                    "id": "legacyphantom",
                    "at": "2026-08-05T10:00:00Z",
                    "branch": "testbr",
                    "agent": "agent",
                    "type": "",
                    "session": "aaaaaaaa",
                    "body": "testbr/none.md",
                    "bytes": 40,
                    "silent": True,
                    "sends": 0,
                    "tx": "absent",
                    "title": "push it",
                    "transcript": "/gone/x.jsonl",
                    "src": "hook",
                }
            )
            + "\n"
        )
    out = sc.report_py("--retire-phantoms", "--dry-run").out
    assert "legacyphantom" in out, "the dry run did not name the legacy phantom"
    assert "real-one" not in out, "the dry run retired the real report"
    assert "legacyphantom" in sc.report_py("--list", "--all").out, "the dry run changed something"
    out = sc.report_py("--retire-phantoms").out
    assert "1 real report(s) untouched" in out, "it does not report what it kept: %s" % out[:300]
    listing = sc.report_py("--list", "--all").out
    assert "legacyphantom" not in listing, "the phantom is still in the listing"
    assert "real-one" in listing, "CONTROL: the real report did not survive"
    # The retirement is an APPEND: the original report line is still on disk.
    assert '"id":"legacyphantom"' in sc.index_text(), "the log did not stay append-only"
    assert '"ev":"retire"' in sc.index_text(), "no retire event was appended"
    assert "nothing to retire" in sc.report_py("--retire-phantoms").out, (
        "CONTROL: re-running must find nothing left"
    )


def test_29_open_items_handback_from_a_subagent_that_ends_with_work_in_hand(sc):
    """THE GAP THIS CLOSES. `SubagentStop` is a CAPTURE hook and can never refuse a turn, so every rule the Stop hook enforces on the main loop is unenforceable for a sub-agent. The fix is not to make it blocking (a wedged sub-agent costs more than a lost report); it is to RECORD the condition and let the parent's blocking Stop surface it. These assertions prove both
    directions, because a flag that is always on is the same as no flag."""
    sc.stop_event(
        "aopen-handback-1111222233334444",
        "porter",
        "Batch 9 ports, partial.\n\n## Remaining\n"
        "- [ ] four gate tests still unported\n"
        "- [?] whether the twin is deleted here or in P5  DEFAULT: P5\n"
        "- [>] shadow pair re-measure  worker:someworker\n"
        "- [x] the six that landed\n"
        "- [~] withdrawn, was a duplicate\n",
    )
    sc.stop_event(
        "aclean-handback-5555666677778888",
        "porter",
        "All six ports landed.\n\n## Remaining\n- [x] every box closed\n- [~] one withdrawn\n",
    )
    lines = sc.index_lines()
    # THREE open states counted, `[x]` and `[~]` excluded, the same partition the store's own parser draws rather than a second opinion about it.
    assert '"opens":3' in lines[0], lines[0]
    assert '"opens":0' in lines[1], "CONTROL: the clean report must record zero"
    # ALWAYS WRITTEN, never omitted when zero: an absent key cannot be told apart from a capture taken before the field existed.
    assert '"opens"' in lines[1], "zero was omitted rather than written"
    # Selected by CONTENT, not by a guessed filename: `short_id` takes the LAST 12 characters of the agent id, so both fixtures land in `*-porter-*.md`.
    bodies = [
        path
        for path in (sc.store / "testbr").glob("*.md")
        if "four gate tests still unported" in path.read_text(encoding="utf-8")
    ]
    assert bodies, "no body file carries the handback"
    assert "open_boxes: 3" in bodies[0].read_text(encoding="utf-8"), "the front matter lost it"

    out = sc.surface("--session-start", "startup")
    assert "OPEN:3" in out, "the parent Stop does not see the marker"
    assert "ENDED ITS TURN declaring" in out, "there is no legend saying what to do about it"
    # The row prints the SHORT id (the last 12 characters), not the agent id the fixture was created with.
    assert "666677778888" in out, "CONTROL: the clean agent must be surfaced, it is unread"
    # The discriminator: same block, same reader, one marked and one not.
    assert "OPEN:0" not in out, "CONTROL: the clean agent must carry no marker"


def test_29b_a_silent_agent_sprouts_no_handback_marker(sc):
    """A silent agent declares nothing, so it must not sprout a handback marker, and the two flags must not both claim the column."""
    sc.stop_event("asilent-none-1111222233334444", "quiet-one", "")
    out = sc.surface("--session-start", "startup")
    assert "SILENT" in out, "silent no longer reads SILENT"
    assert "OPEN:" not in out, "a silent agent carried an open-items marker"
    assert "ENDED ITS TURN declaring" not in out, "a legend appeared with nothing handed back"


def test_29c_the_capture_hook_stays_non_blocking(sc):
    """This is the invariant the whole design rests on, and it is the one an "improvement" would quietly break, so it is asserted rather than trusted: a sub-agent handing back three open items still exits 0 with no output on stdout."""
    got = sc.stop_event(
        "aexit-check-1111222233334444", "porter", "- [ ] one\n- [ ] two\n- [ ] three"
    )
    assert got.rc == 0, "a handback exited %d" % got.rc
    assert (got.out + got.err) == "", "it said something to the sub-agent: %r" % (got.out + got.err)


def test_29d_the_listing_carries_the_same_marker(sc):
    """`--list --unread` carries the same marker, so the inbox and the surfaced block cannot disagree about which agent handed work back."""
    sc.stop_event(
        "aopen-handback-1111222233334444",
        "porter",
        "Batch 9 ports, partial.\n\n## Remaining\n"
        "- [ ] four gate tests still unported\n"
        "- [?] whether the twin is deleted here or in P5  DEFAULT: P5\n"
        "- [>] shadow pair re-measure  worker:someworker\n",
    )
    assert "[OPEN:3]" in sc.report_py("--list", "--all").out, "the listing does not mark it"


def test_29e_a_legacy_line_with_no_opens_key_still_lists_and_surfaces(sc):
    """BACKWARD COMPATIBILITY, because the index is append-only and never rewritten: every line captured before this field existed has no `opens` key at all. A reader that assumed the key would raise on the whole historical tail, the exact shape that once aborted `scan()` permanently and silently. The fixture is a REAL capture with the key surgically removed rather than a hand-
    typed line, so it cannot drift from what the writer actually produces."""
    sc.stop_event(
        "alegacy-line-1111222233334444",
        "porter",
        "A report from before the field existed.\n"
        "- [ ] this box must NOT be counted, because the line has no opens key\n",
    )
    assert '"opens":1' in sc.index_text(), "CONTROL: the fresh capture must carry the key"
    stripped = []
    for line in sc.index_lines():
        entry = json.loads(line)
        entry.pop("opens", None)
        stripped.append(json.dumps(entry, separators=(",", ":"), ensure_ascii=False))
    sc.index.write_text("\n".join(stripped) + "\n", encoding="utf-8")
    assert '"opens"' not in sc.index_text(), "the key is not really gone from the fixture"
    out = sc.report_py("--list", "--all").out
    assert "222233334444" in out, "a legacy line stopped listing"
    assert "[OPEN:" not in out, "a legacy line sprouted a marker"
    out = sc.surface("--session-start", "startup")
    assert "222233334444" in out, "a legacy line stopped surfacing"
    assert "ENDED ITS TURN declaring" not in out, "the legend appeared for a legacy line"


def test_30_a_resumed_agents_later_reports_are_captured_not_dropped(sc):
    """THE DEFECT, measured live 2026-09-07 on agent a41545ec804647d3b. Dedup was keyed on the agent id alone, so only an agent's FIRST stop was ever recorded. `SendMessage` resumes an agent and every resume ends in another SubagentStop, so the store kept that agent's 75-byte SILENT sign-off and DISCARDED both substantive reports that followed. That is this module's stated
    purpose running backwards: keeping the silence, dropping the substance."""
    sc.stop_event("aresumed-agent-1111222233334444", "porter", "First stop: nothing much yet.")
    sc.stop_event(
        "aresumed-agent-1111222233334444", "porter", "SECOND STOP, THE REAL REPORT.\n" + BIG
    )
    lines = sc.index_lines()
    assert len(lines) == 2, "both stops should be indexed, got %d" % len(lines)
    assert '"id":"222233334444"' in lines[0], lines[0]
    assert '"id":"222233334444-2"' in lines[1], lines[1]
    # WHY A DISTINCT ID IS LOAD-BEARING and not cosmetic: `unread` suppresses by id, so a second capture sharing the id would be born already-read.
    sc.report_py("--read", "aaaaaaaa-1111", "222233334444")
    out = sc.surface("--session-start", "startup")
    assert "First stop: nothing much" not in out, "the first, once read, resurfaced"
    assert "222233334444-2" in out, "the SECOND did not surface"
    assert "SECOND STOP, THE REAL REPORT" in out, "the substantive one is missing"


def test_30b_control_an_identical_recapture_is_still_deduped(sc):
    """CONTROL: the dedup this replaced must still work. The hook captures at the stop and `--scan` self-heals over the same agent later, both producing a byte-identical body; that duplicate is what dedup exists for."""
    sc.stop_event("asame-body-5555666677778888", "porter", "Identical sign-off.")
    sc.stop_event("asame-body-5555666677778888", "porter", "Identical sign-off.")
    assert len(sc.index_lines()) == 1, "an identical re-capture was not deduped"


def test_30c_control_a_legacy_line_still_dedupes_by_id_alone(sc):
    """Without this the first `--scan` after the change would re-capture all 349 already-indexed reports as `-2` duplicates."""
    sc.stop_event("alegacy-dedup-9999aaaabbbbcccc", "porter", "Original body.")
    stripped = []
    for line in sc.index_lines():
        entry = json.loads(line)
        entry.pop("bkey", None)
        stripped.append(json.dumps(entry, separators=(",", ":"), ensure_ascii=False))
    sc.index.write_text("\n".join(stripped) + "\n", encoding="utf-8")
    assert '"bkey"' not in sc.index_text(), "the fixture is not really legacy-shaped"
    sc.stop_event("alegacy-dedup-9999aaaabbbbcccc", "porter", "A DIFFERENT body entirely.")
    assert len(sc.index_lines()) == 1, "a legacy line stopped deduping by id alone"


def test_30d_nothing_unread_and_nothing_captured_are_different_facts(sc):
    """One sentence used to state both: "no reports indexed" was printed for an index holding 349 entries the reader had simply read."""
    empty = sc.report_py("--list", "--unread")
    assert "no reports indexed" in empty.out + empty.err, "an empty store does not say so"
    sc.stop_event(
        "aallread-agent-ddddeeeeffff0000", "porter", "Something substantive here.\n" + BIG
    )
    sc.report_py("--read", "aaaaaaaa-1111", "eeeeffff0000")
    got = sc.report_py("--list", "--unread")
    text = got.out + got.err
    assert "no UNREAD reports" in text, "a fully-read store does not say THAT instead"
    assert "1 indexed, all read" in text, "it does not name how many are indexed"
    assert "no reports indexed" not in text, "it still claims nothing was captured"


def test_28_no_ambient_session_id_survives_the_scrub(sc):
    """META-CONTROL: the ambient scrub really happened.

    A CHECK ON A CHECK, and not redundant. Every identity assertion above depends on WORKLIST_SESSION_ID being the ONLY session id in the environment. If the scrub stops stripping CLAUDE_CODE_SESSION_ID this module splits in two: red from inside a Claude session, and green-but-meaningless in CI. The second is the dangerous one. The probe unsets WORKLIST_SESSION_ID ONLY and issues a
    read mark under an identity no real session could be; it can only succeed if no ambient id survived.
    """
    probe = dict(sc.env)
    probe.pop("WORKLIST_SESSION_ID", None)
    got = sc.report_py("--read", "zzzzzzzz", "nosuchid", env=probe)
    assert "identity mismatch" not in got.out + got.err, (
        "an ambient session id leaked past the scrub"
    )
    # CONTROL: force one back in and the same call must be refused. Without this, the assertion above is satisfied by a check that never runs at all.
    probe["CLAUDE_CODE_SESSION_ID"] = "beef0000-9999"
    got = sc.report_py("--read", "zzzzzzzz", "nosuchid", env=probe)
    assert "identity mismatch" in got.out + got.err, (
        "CONTROL: with an ambient id present the same call must be refused"
    )


# ---- lead-only capture (agent/plans/PLAN-tick-tracking.md, T5) ---------------

FIXTURES = pathlib.Path(__file__).resolve().parent / "tick_tracking_fixtures" / "report"
COORD = "a465aa7e2ca09a227"


def _harvest_all(jsonl):
    """THE PRE-CHANGE `harvest_transcript`, kept here for the CONTROL only: it kept every SendMessage, whatever its `to`."""
    report = wlfix.import_wl("wl_report")
    sends, final, rec = [], "", {}
    for line in report._bounded_lines(jsonl):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not isinstance(r, dict) or r.get("type") != "assistant":
            continue
        rec = r
        content = (r.get("message") or {}).get("content")
        if isinstance(content, str):
            if content.strip():
                final = content
            continue
        if not isinstance(content, list):
            continue
        texts = []
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text" and str(c.get("text") or "").strip():
                texts.append(str(c["text"]))
            elif c.get("type") == "tool_use" and c.get("name") == "SendMessage":
                inp = c.get("input") or {}
                msg = inp.get("message")
                if not isinstance(msg, str):
                    msg = json.dumps(msg, ensure_ascii=False)
                if str(msg).strip():
                    sends.append(
                        {
                            "to": str(inp.get("to") or "?"),
                            "at": str(r.get("timestamp") or ""),
                            "summary": str(inp.get("summary") or ""),
                            "message": str(msg),
                        }
                    )
        if texts:
            final = "\n".join(texts)
    return sends, final, rec


def coordinator_records(extra: list | None = None) -> list[dict]:
    """The fixture transcript (21 sends to 11 agent ids, then a final text), restamped to the last ten minutes so neither scan's lookback nor body pruning sees an old agent."""
    recs = [
        json.loads(line)
        for line in (FIXTURES / "coordinator.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    recs[-1:-1] = list(extra or [])
    start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=10)
    for n, r in enumerate(recs):
        r["timestamp"] = (start + datetime.timedelta(seconds=n)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return recs


def write_transcript(path: pathlib.Path, recs: list[dict]) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return path


def final_text(recs: list[dict]) -> str:
    return recs[-1]["message"]["content"][0]["text"]


def send_to_main() -> dict:
    return {
        "type": "assistant",
        "agentId": COORD,
        "sessionId": "sess1",
        "gitBranch": "testbr",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "SendMessage",
                    "input": {
                        "to": "main",
                        "summary": "round report",
                        "message": "ROUND REPORT FOR THE LEAD\n" + "detail. " * 40,
                    },
                }
            ]
        },
    }


def hook_capture(sc: Scratch, recs: list[dict]) -> dict:
    tx = write_transcript(sc.subagents_dir() / ("agent-%s.jsonl" % COORD), recs)
    sc.raw_stop(
        {
            "agent_id": COORD,
            "agent_type": "general-purpose",
            "session_id": READER,
            "cwd": str(sc.repo),
            "agent_transcript_path": str(tx),
            "last_assistant_message": final_text(recs),
        }
    )
    lines = sc.index_lines()
    assert len(lines) == 1, lines
    return json.loads(lines[0])


def assert_no_orders(sc: Scratch, entry: dict, recs: list[dict]) -> None:
    body = body_of(sc.store / entry["body"])
    # No lead-bound section; every order is still stored, under its own heading.
    assert "## SendMessage" not in body, body[:300]
    assert len(re.findall(r"^## Outgoing \d+ -> a[0-9a-f]{16}\b", body, re.MULTILINE)) == 21, body[
        :300
    ]
    assert final_text(recs) in body, "the final text was dropped"
    assert entry["sends"] == 0, entry
    assert entry["out"] == 21, entry
    assert entry["silent"] is False, "an agent that sent 21 messages is not silent"
    assert not entry["title"].startswith(("Coordinator ruling", "Brief addition")), entry["title"]
    front = (sc.store / entry["body"]).read_text(encoding="utf-8").split("---\n\n", 1)[0]
    assert "\nsends: 0\n" in front, front
    assert "\nout: 21\n" in front, front


def test_31_recipient_control_the_old_harvest_kept_every_send(sc):
    """CONTROL: the pre-change harvest reads 21 sends off this fixture, so the zero below is the rule working and not a fixture with nothing in it."""
    report = wlfix.import_wl("wl_report")
    tx = write_transcript(sc.t / "coord.jsonl", coordinator_records())
    old_sends, old_final, _ = _harvest_all(tx)
    assert len(old_sends) == 21, len(old_sends)
    assert len({s["to"] for s in old_sends}) == 11, "the fixture is not 21 sends to 11 ids"
    assert report._title_of(old_sends, old_final).startswith("Coordinator ruling"), (
        "the old reading is not the defect being fixed"
    )
    sends, final, _rec, others = report.harvest_transcript(tx)
    assert sends == [], sends[:1]
    assert len(others) == 21, len(others)
    assert [s["message"] for s in others] == [s["message"] for s in old_sends], (
        "a send to another agent was dropped rather than kept aside"
    )
    assert final == old_final, "the final text must be kept whole"


def writer_records(to: str) -> list[dict]:
    """A writer under a coordinator: its whole report is one long SendMessage to the coordinator, then a short sign-off."""
    start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)
    report_text = "WRITER REPORT FOR THE COORDINATOR\n" + "Landed commit and test evidence. " * 60
    return [
        {
            "type": "assistant",
            "agentId": "awriterundercoord0001",
            "sessionId": "sess1",
            "gitBranch": "testbr",
            "timestamp": start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "SendMessage",
                        "input": {"to": to, "summary": "report", "message": report_text},
                    }
                ]
            },
        },
        {
            "type": "assistant",
            "agentId": "awriterundercoord0001",
            "sessionId": "sess1",
            "gitBranch": "testbr",
            "timestamp": (start + datetime.timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "message": {"content": [{"type": "text", "text": "Report sent."}]},
        },
    ]


def test_31g_recipient_a_report_sent_to_the_coordinator_is_stored(sc):
    """Review finding 0009f584.1: dropping every non-lead send lost a writer's report delivered by SendMessage to its coordinator. CONTROL: on 0009f584 the stored body held only "Report sent.", so the report-text assertion below fails there, and `_relay_before` states the relay rule the row is checked against."""
    for n, to in enumerate(("coordinator", COORD)):
        recs = writer_records(to)
        aid = "awriterundercoord%04d" % n
        tx = write_transcript(sc.subagents_dir() / ("agent-%s.jsonl" % aid), recs)
        sc.raw_stop(
            {
                "agent_id": aid,
                "agent_type": "general-purpose",
                "session_id": READER,
                "cwd": str(sc.repo),
                "agent_transcript_path": str(tx),
                "last_assistant_message": "Report sent.",
            }
        )
        entry = json.loads(sc.index_lines()[-1])
        body = body_of(sc.store / entry["body"])
        assert "WRITER REPORT FOR THE COORDINATOR" in body, body[:300]
        assert "## Outgoing 1 -> %s" % to in body, body[:300]
        assert "## SendMessage" not in body, "a send to the coordinator was filed as lead-bound"
        # The send is not lead-bound, so `sends` stays 0; but it went to ONE peer, so it is the writer's report: titled from it and unread.
        assert entry["sends"] == 0, entry
        assert entry["out"] == 1, entry
        assert entry["title"] == "WRITER REPORT FOR THE COORDINATOR", entry["title"]
        assert entry["relay"] is False, entry
        assert entry["silent"] is False, entry
        report = wlfix.import_wl("wl_report")
        parts, final = report.body_parts(body)
        assert [(k, t) for k, t, _m in parts] == [("Outgoing", to)], parts
        assert final.strip() == "Report sent.", final
        # CONTROL: the relay rule of 0009f5844 and of 862dd2246 marked this same row a relay, so it never reached the lead.
        assert _relay_before(entry["sends"], entry["out"], final), (
            "CONTROL: the old relay rule must mark the writer a relay"
        )
    unread = sc.report_py("--list", "--unread").out
    for aid in ("awriterundercoord0000", "awriterundercoord0001"):
        assert aid[-12:] in unread, unread
    assert unread.count("WRITER REPORT FOR THE COORDINATOR") == 2, unread


def _relay_before(lead_sends, out, final):
    """THE RELAY RULE OF 371592b85 AND 5e591cec2, kept for the CONTROL only: no lead-bound send, any outgoing send, and a final text under the relay floor, whatever the outgoing sends held or how many recipients they had."""
    report = wlfix.import_wl("wl_report")
    return lead_sends == 0 and out > 0 and len(str(final or "").strip()) < report.RELAY_FLOOR


def test_31h_recipient_one_peer_with_a_short_send_and_fan_out_stay_relays():
    """The narrowed rule keeps the coordinator shape a relay: sends to two or more recipients with a short final. A one-peer send under the silent floor ("Sent the status request", measured on the legacy rows) is not a report either."""
    report = wlfix.import_wl("wl_report")
    fan = [("a%016d" % n, "Coordinator ruling: x " + "y" * 400) for n in range(11)]
    assert report.judge([], fan, "Waiting for the remaining nine.")[0] is True
    assert report.judge([], fan, "A real report. " * 50)[0] is False
    assert report.judge([], [("coordinator", "status?")], "Sent; waiting.")[0] is True
    relay, title = report.judge([], [("coordinator", "REPORT\n" + "z" * 300)], "Done.")
    assert relay is False
    assert title == "REPORT"
    assert report.judge(["LEAD\nx"], fan, "")[0] is False


def test_31b_recipient_hook_path_keeps_only_the_final_text(sc):
    recs = coordinator_records()
    entry = hook_capture(sc, recs)
    assert_no_orders(sc, entry, recs)
    # A coordinator's turn-end status, under the relay floor, is not a report for the lead.
    assert entry["relay"] is True, entry
    got = sc.report_py("--list", "--unread")
    assert COORD[-12:] not in got.out, got.out
    assert "no UNREAD reports" in got.out, got.out


def test_31c_recipient_scan_path_keeps_only_the_final_text(sc):
    recs = coordinator_records()
    proj = sc.subagents_dir()
    (proj / ("agent-%s.meta.json" % COORD)).write_text(
        json.dumps({"agentType": "general-purpose"}), encoding="utf-8"
    )
    tx = write_transcript(proj / ("agent-%s.jsonl" % COORD), recs)
    old = time.time() - 3600
    os.utime(tx, (old, old))
    got = sc.report_py("--scan")
    assert "indexed %s" % COORD[-12:] in got.out, got.out + got.err
    lines = sc.index_lines()
    assert len(lines) == 1, lines
    entry = json.loads(lines[0])
    assert entry["src"] == "scan", entry
    assert_no_orders(sc, entry, recs)


def test_31d_recipient_a_send_to_main_is_kept(sc):
    recs = coordinator_records([send_to_main()])
    entry = hook_capture(sc, recs)
    body = body_of(sc.store / entry["body"])
    assert "## SendMessage 1 -> main" in body, body[:300]
    assert "ROUND REPORT FOR THE LEAD" in body
    assert "## SendMessage 2" not in body, "an order to a writer rode along with the lead's send"
    assert entry["sends"] == 1, entry
    assert entry["out"] == 22, entry
    assert entry["relay"] is False, entry
    assert entry["title"] == "ROUND REPORT FOR THE LEAD", entry["title"]
    got = sc.report_py("--list", "--unread")
    assert COORD[-12:] in got.out, "CONTROL: a row with a lead-bound send must stay unread"


def plant_legacy(
    sc: Scratch, rid: str, fixture: str, title: str, sends: int, body: str = ""
) -> None:
    """A row as the pre-change capture wrote it: no `out` key, `sends` counting every send, titled from the last order."""
    text = body or (FIXTURES / fixture).read_text(encoding="utf-8")
    rel = "testbr/%s.md" % rid
    (sc.store / "testbr").mkdir(parents=True, exist_ok=True)
    (sc.store / rel).write_text(text, encoding="utf-8")
    row = {
        "ev": "report",
        "id": rid,
        "at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": "testbr",
        "agent": "general-purpose",
        "type": "general-purpose",
        "session": READER[:8],
        "body": rel,
        "bytes": len(text.encode("utf-8")),
        "silent": False,
        "sends": sends,
        "opens": 0,
        "bkey": rid[:16],
        "tx": "ok",
        "title": title,
        "transcript": "",
        "src": "hook",
    }
    with sc.index.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def test_31e_recipient_legacy_coordinator_rows_are_not_unread(sc):
    plant_legacy(
        sc,
        "a7e2ca09a227",
        "coordinator-report-01.body",
        "Brief addition (operator order): the report must end with a TICK block",
        11,
    )
    plant_legacy(
        sc,
        "a7e2ca09a227-15",
        "coordinator-report-15.body",
        "Coordinator ruling: the boundary now also covers the matching test directory",
        21,
    )
    report = wlfix.import_wl("wl_report")
    assert report.unread(sc.store, "testbr", READER) == [], (
        "a legacy coordinator row read as unread"
    )
    got = sc.report_py("--list", "--unread")
    assert "no UNREAD reports" in got.out, got.out
    assert "a7e2ca09a227" not in got.out, got.out
    assert sc.surface("--session-start", "startup") == "", "a coordinator row surfaced"
    # History still lists both, re-judged: marked relay and titled from the final message.
    listing = sc.report_py("--list").out
    assert listing.count("[relay]") == 2, listing
    assert "Coordinator ruling" not in listing, listing
    assert "Brief addition" not in listing, listing
    for entry in report.read_index(sc.store):
        judged = report.rejudge(sc.store, entry)
        assert judged["sends"] == 0, judged
        assert judged["out"] in (11, 21), judged
        assert not judged["title"].startswith("Coordinator ruling"), judged["title"]


def test_31f_recipient_control_legacy_rows_with_lead_substance_still_surface(sc):
    """CONTROL: the re-judge drops orders, not reports. One copy differs only in one header naming `main`; the other only in a final message long enough to be a report."""
    fifteen = (FIXTURES / "coordinator-report-15.body").read_text(encoding="utf-8")
    to_main = re.sub(r"^(## SendMessage 21 -> )\S+", r"\1main", fifteen, flags=re.MULTILINE)
    assert to_main != fifteen, "the fixture has no 21st send header to retarget"
    plant_legacy(sc, "aaaa00000001", "", "Coordinator ruling: x", 21, body=to_main)
    long_final = fifteen + "\n" + "A real report paragraph for the lead. " * 20
    plant_legacy(sc, "aaaa00000002", "", "Coordinator ruling: y", 21, body=long_final)
    report = wlfix.import_wl("wl_report")
    got = {e["id"]: e for e in report.unread(sc.store, "testbr", READER)}
    assert set(got) == {"aaaa00000001", "aaaa00000002"}, got
    assert got["aaaa00000001"]["sends"] == 1, got["aaaa00000001"]
    assert got["aaaa00000001"]["title"].startswith("Coordinator ruling: the boundary"), got
    assert got["aaaa00000002"]["title"].startswith("Load is"), got["aaaa00000002"]["title"]
    # And a legacy row with no sends at all is returned exactly as indexed.
    plant_legacy(sc, "aaaa00000003", "", "plain final", 0, body="## Final message\n\n" + BIG)
    row = next(e for e in report.read_index(sc.store) if e["id"] == "aaaa00000003")
    assert report.rejudge(sc.store, row) is row
    # Both header kinds in one body: an `## Outgoing` section never counts as lead-bound, even when its `to` reads `main`.
    mixed = (
        "## SendMessage 1 -> main\n\nLEAD PART\n\n"
        "## Outgoing 1 -> main\n\nmislabelled order\n\n"
        "## Outgoing 2 -> a0000000000000001\n\nan order\n\n"
        "## Final message\n\nDone."
    )
    plant_legacy(sc, "aaaa00000004", "", "an order", 3, body=mixed)
    row = next(e for e in report.read_index(sc.store) if e["id"] == "aaaa00000004")
    judged = report.rejudge(sc.store, row)
    assert judged["sends"] == 1, judged
    assert judged["out"] == 3, judged
    assert judged["title"] == "LEAD PART", judged["title"]
    assert judged["relay"] is False, judged


# ---- direction from the spawn lineage (review findings 4e34cbde.2, 862dd224.1) ----

PARENT_ID = "a1111111111111111"
CHILD_ID = "a2222222222222222"
SIBLING_ID = "a3333333333333333"
BRIEF = "Coordinator ruling: own exactly these files and nothing else.\n" + "Detail. " * 80
SHORT_REPORT = "DONE: commit abc1234, tests rc=0."


def plant_meta(sc: Scratch, aid: str, parent: str = "", sub: str = "", name: str = "") -> None:
    """The meta sidecar the harness writes beside a sub-agent transcript; `parent` is its `parentAgentId` ("" for one the lead spawned), `sub` a `workflows/<run>` subdirectory."""
    where = sc.subagents_dir() / sub if sub else sc.subagents_dir()
    where.mkdir(parents=True, exist_ok=True)
    info: dict = {"agentType": "general-purpose", "spawnDepth": 2 if parent else 1}
    if parent:
        info["parentAgentId"] = parent
    if name:
        info["name"] = name
    (where / ("agent-%s.meta.json" % aid)).write_text(json.dumps(info), encoding="utf-8")


def sends_records(sender: str, sends: list, final: str) -> list[dict]:
    start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)

    def rec(n, content):
        return {
            "type": "assistant",
            "agentId": sender,
            "sessionId": "sess1",
            "gitBranch": "testbr",
            "timestamp": (start + datetime.timedelta(seconds=n)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "message": {"content": content},
        }

    recs = [
        rec(n, [{"type": "tool_use", "name": "SendMessage", "input": {"to": to, "message": msg}}])
        for n, (to, msg) in enumerate(sends)
    ]
    return [*recs, rec(len(sends), [{"type": "text", "text": final}])]


def stop_with(sc: Scratch, sender: str, sends: list, final: str, sub: str = "") -> dict:
    where = sc.subagents_dir() / sub if sub else sc.subagents_dir()
    tx = write_transcript(where / ("agent-%s.jsonl" % sender), sends_records(sender, sends, final))
    sc.raw_stop(
        {
            "agent_id": sender,
            "agent_type": "general-purpose",
            "session_id": READER,
            "cwd": str(sc.repo),
            "agent_transcript_path": str(tx),
            "last_assistant_message": final,
        }
    )
    return json.loads(sc.index_lines()[-1])


def family(sc: Scratch) -> None:
    plant_meta(sc, PARENT_ID)
    plant_meta(sc, CHILD_ID, parent=PARENT_ID)
    plant_meta(sc, SIBLING_ID, parent=PARENT_ID)


def test_31i_direction_a_coordinators_long_brief_to_its_own_child_is_a_relay(sc):
    """4e34cbde.2: one long brief to one writer is the one-peer SHAPE of a report, but the writer's meta names the sender as its parent, so it is an order and stays out of the lead's inbox."""
    report = wlfix.import_wl("wl_report")
    assert len(BRIEF.strip()) >= report.SILENT_FLOOR
    # CONTROL: the shape rule alone reads this exact capture as a report titled from the order.
    shape = report.judge([], [(CHILD_ID, BRIEF)], "Brief sent; waiting.")
    assert shape == (False, "Coordinator ruling: own exactly these files and nothing else."), shape
    family(sc)
    entry = stop_with(sc, PARENT_ID, [(CHILD_ID, BRIEF)], "Brief sent; waiting.")
    assert entry["relay"] is True, entry
    assert not entry["title"].startswith("Coordinator ruling"), entry["title"]
    assert entry["dir"] == "down", entry
    assert entry["silent"] is False, entry
    got = sc.report_py("--list", "--unread")
    assert PARENT_ID[-12:] not in got.out, got.out
    # Fan-out to two children is a relay too.
    entry = stop_with(sc, PARENT_ID, [(CHILD_ID, BRIEF + " 2"), (SIBLING_ID, BRIEF)], "Waiting.")
    assert (entry["dir"], entry["relay"]) == ("down", True), entry
    # A coordinator whose final text reaches RELAY_FLOOR still surfaces, titled from that final.
    long_final = "ROUND SUMMARY FOR THE LEAD\n" + "Finding with evidence. " * 40
    assert len(long_final) >= report.RELAY_FLOOR
    entry = stop_with(sc, PARENT_ID, [(CHILD_ID, BRIEF + " 3")], long_final)
    assert (entry["dir"], entry["relay"]) == ("down", False), entry
    assert entry["title"] == "ROUND SUMMARY FOR THE LEAD", entry["title"]


def test_31j_direction_a_childs_short_report_to_its_parent_is_shown(sc):
    """862dd224.1: a report under SILENT_FLOOR to the coordinator, with a short sign-off, is the shape of a relay; the sender's meta names the recipient as its parent, so it is a report and reaches the lead's inbox, titled from the report."""
    report = wlfix.import_wl("wl_report")
    assert len(SHORT_REPORT) < report.SILENT_FLOOR
    # CONTROL: the shape rule alone hides this exact capture.
    assert report.judge([], [(PARENT_ID, SHORT_REPORT)], "Sent.")[0] is True
    family(sc)
    entry = stop_with(sc, CHILD_ID, [(PARENT_ID, SHORT_REPORT)], "Sent.")
    assert entry["relay"] is False, entry
    assert entry["title"] == SHORT_REPORT, entry["title"]
    assert entry["dir"] == "up", entry
    got = sc.report_py("--list", "--unread")
    assert CHILD_ID[-12:] in got.out, got.out


def test_31k_direction_unknown_lineage_keeps_the_shape_rule(sc):
    """No meta for either side, and a send to a sibling, both leave the direction unsettled: the shape rule decides exactly as before, and the row says so with `dir` "?"."""
    # No metas at all: the 862dd224.1 shape is still a relay, the 4e34cbde.2 shape still a report.
    entry = stop_with(sc, CHILD_ID, [(PARENT_ID, SHORT_REPORT)], "Sent.")
    assert (entry["dir"], entry["relay"]) == ("?", True), entry
    entry = stop_with(sc, PARENT_ID, [(CHILD_ID, BRIEF)], "Brief sent; waiting.")
    assert (entry["dir"], entry["relay"]) == ("?", False), entry
    assert entry["title"].startswith("Coordinator ruling"), entry["title"]
    # Siblings (both children of one coordinator) do not settle it either.
    family(sc)
    entry = stop_with(sc, CHILD_ID, [(SIBLING_ID, SHORT_REPORT + " sib")], "Sent.")
    assert (entry["dir"], entry["relay"]) == ("?", True), entry
    # A send to the lead is the report whatever the lineage, and a capture with no non-lead send says so.
    entry = stop_with(sc, SIBLING_ID, [("main", "LEAD REPORT\n" + BIG)], "Done.")
    assert (entry["dir"], entry["relay"]) == ("-", False), entry
    assert entry["title"] == "LEAD REPORT", entry["title"]


def test_31l_direction_helpers():
    """`judge` without lineage is the shape rule; `direction` shows on ONE send up and hides only on EVERY send down."""
    report = wlfix.import_wl("wl_report")
    shape = report.judge([], [(CHILD_ID, BRIEF)], "w")
    assert report.judge([], [(CHILD_ID, BRIEF)], "w", None) == shape
    assert report.judge([], [(CHILD_ID, BRIEF)], "w", {}) == shape
    kin = {PARENT_ID: "parent", CHILD_ID: "child"}
    assert report.direction([], kin) == "-"
    assert report.direction([(CHILD_ID, "x")], kin) == "down"
    assert report.direction([(CHILD_ID, "x"), (PARENT_ID, "y")], kin) == "up"
    assert report.direction([(CHILD_ID, "x"), (SIBLING_ID, "y")], kin) == "?"
    # Up wins over down, and the title is the report to the parent, not the order.
    relay, title = report.judge([], [(PARENT_ID, "UP REPORT"), (CHILD_ID, BRIEF)], "ok", kin)
    assert (relay, title) == (False, "UP REPORT")


def test_31m_direction_kin_of_reads_the_sidecars(sc):
    """Both edges, by id and by teammate name, a workflow agent's meta dir, and a `to` that is not an id refused before it touches a path."""
    report = wlfix.import_wl("wl_report")
    plant_meta(sc, PARENT_ID, name="coord")
    plant_meta(sc, CHILD_ID, parent=PARENT_ID, name="writer-1")
    plant_meta(sc, SIBLING_ID, parent=PARENT_ID, sub="workflows/run1")
    tx = sc.subagents_dir() / ("agent-%s.jsonl" % PARENT_ID)
    tos = {CHILD_ID, SIBLING_ID, "writer-1", "main", "../evil", "console-34"}
    got = report.kin_of(PARENT_ID, str(tx), tos)
    assert got == {CHILD_ID: "child", SIBLING_ID: "child", "writer-1": "child"}, got
    wf_tx = sc.subagents_dir() / "workflows" / "run1" / ("agent-%s.jsonl" % SIBLING_ID)
    assert report.kin_of(SIBLING_ID, str(wf_tx), {PARENT_ID}) == {PARENT_ID: "parent"}
    assert report.kin_of(CHILD_ID, str(tx), {"coord", "writer-1"}) == {"coord": "parent"}
    # No transcript, or one outside any `subagents` directory: unknown.
    assert report.kin_of(CHILD_ID, "", {PARENT_ID}) == {}
    assert report.kin_of(CHILD_ID, str(sc.t / "x.jsonl"), {PARENT_ID}) == {}
    # A workflow agent's own capture reads its lineage too.
    entry = stop_with(sc, SIBLING_ID, [(PARENT_ID, SHORT_REPORT)], "Sent.", sub="workflows/run1")
    assert (entry["dir"], entry["relay"]) == ("up", False), entry


def test_31n_direction_hook_and_scan_agree(sc):
    """`--scan` captures through the same `capture`, so it reaches the hook's verdict on the same transcript."""
    family(sc)
    hooked = stop_with(sc, PARENT_ID, [(CHILD_ID, BRIEF)], "Brief sent; waiting.")
    tx = write_transcript(
        sc.subagents_dir() / ("agent-%s.jsonl" % CHILD_ID),
        sends_records(CHILD_ID, [(PARENT_ID, SHORT_REPORT)], "Sent."),
    )
    old = time.time() - 3600
    os.utime(tx, (old, old))
    got = sc.report_py("--scan")
    assert "indexed %s" % CHILD_ID[-12:] in got.out, got.out + got.err
    scanned = json.loads(sc.index_lines()[-1])
    assert scanned["src"] == "scan", scanned
    assert (scanned["dir"], scanned["relay"], scanned["title"]) == ("up", False, SHORT_REPORT)
    assert (hooked["dir"], hooked["relay"]) == ("down", True), hooked


def test_31o_direction_rows_without_the_field_read_as_before(sc):
    """A row captured before `dir` keeps its stored `relay` (it carries `out`, so `rejudge` leaves it alone), and a legacy row with no `out` is still re-judged by the shape rule."""
    report = wlfix.import_wl("wl_report")
    family(sc)
    shown = stop_with(sc, CHILD_ID, [(PARENT_ID, SHORT_REPORT)], "Sent.")
    assert shown["dir"] == "up", shown
    assert shown["relay"] is False, shown
    old = {k: v for k, v in shown.items() if k != "dir"}
    old.update({"id": "abcdabcdabcd", "relay": True, "bkey": "0" * 16})
    with sc.index.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(old, separators=(",", ":")) + "\n")
    assert report.rejudge(sc.store, old) is old
    ids = {str(e["id"]) for e in report.unread(sc.store, "testbr", READER)}
    assert CHILD_ID[-12:] in ids, ids
    assert "abcdabcdabcd" not in ids, "a pre-field row was re-judged by the lineage"
    fifteen = (FIXTURES / "coordinator-report-15.body").read_text(encoding="utf-8")
    plant_legacy(sc, "aaaa00000009", "", "Coordinator ruling: z", 21, body=fifteen)
    row = next(e for e in report.read_index(sc.store) if e["id"] == "aaaa00000009")
    judged = report.rejudge(sc.store, row)
    assert judged["relay"] is True, judged
    assert "dir" not in judged, judged


def test_lead_recipients_match_in_any_case_and_a_blank_lead_title_falls_back():
    """Reviews 0009f584.3 and 4e34cbde.3: "Team-Lead" is the lead, and a lead-bound send with no text titles from the final message."""
    report = wlfix.import_wl("wl_report")
    assert report.is_lead("Main")
    assert report.is_lead(" Team-Lead ")
    assert not report.is_lead("worker")
    assert report.judge(["\n  \n"], [], "Final words here")[1] == "Final words here"


def test_an_agent_id_with_a_trailing_newline_is_refused(tmp_path):
    """Review 1468d197.1: `$` matched before a trailing newline."""
    report = wlfix.import_wl("wl_report")
    (tmp_path / "agent-a1111.meta.json").write_text("{}", encoding="utf-8")
    assert report._meta(tmp_path, "a1111") == {}
    assert report._meta(tmp_path, "a1111\n") is None


def test_kin_of_reads_the_sidecars_once_per_name(tmp_path, monkeypatch):
    """Review 1468d197.2: two sends to one unresolved name walked the sidecar tree once, not twice per send."""
    report = wlfix.import_wl("wl_report")
    root = tmp_path / "s" / "subagents"
    root.mkdir(parents=True)
    (root / "agent-asender.meta.json").write_text("{}", encoding="utf-8")
    calls: list[str] = []
    real = report._named

    def counting(r, n):
        calls.append(n)
        return real(r, n)

    monkeypatch.setattr(report, "_named", counting)
    report.kin_of("asender", str(root / "agent-asender.jsonl"), ["bob", "bob", "bob"])
    assert calls == ["bob"]


def test_a_payload_quoting_a_section_heading_stays_in_its_section():
    """Review 862dd224.3: a lead-bound message holding a `## Outgoing 1 -> x` line was split into a second section on read-back."""
    report = wlfix.import_wl("wl_report")
    quoted = "see this heading:\n## Outgoing 1 -> x\nand this one\n## Final message\n\nnot final"
    body = report.assemble_body([{"to": "main", "message": quoted}], "the sign-off")
    parts, final = report.body_parts(body)
    assert [(k, t) for k, t, _m in parts] == [("SendMessage", "main")]
    assert final == "the sign-off"
    assert "not final" in parts[0][2]


def test_a_body_stored_by_the_old_defang_reads_back_as_written():
    """Review d412dae6.2: the old `_defang` wrote a quoted heading as `\\## Outgoing 1 -> x` (one backslash, no escape of lines that were already backslashed). That form is the same one the new `_defang` writes for such a line, so both storages read back to the original; no stored body on disk carries a backslash-led heading line that the old writer left verbatim (grep of ~/.claude/agent-reports, 2026-11-07)."""
    report = wlfix.import_wl("wl_report")
    old = "## SendMessage 1 -> main\n\nsee\n\\## Outgoing 1 -> x\nend\n\n## Final message\n\ndone"
    parts, final = report.body_parts(old)
    assert parts[0][2] == "see\n## Outgoing 1 -> x\nend"
    assert final == "done"


# ---- R20261101.4: the unread-reports block names the listing verb ------------------------------


def test_r4_the_unread_block_and_its_older_row_name_the_reports_verb():
    msgs = wlfix.import_wl("worklist_messages")
    block = msgs.N_UNREAD_REPORTS % (
        3,
        "br",
        "    row",
        "/x/wl_report.py",
        "/x/wl_report.py",
        "aaaaaaaa",
    )
    assert "worklist.py --reports" in block, block
    older = msgs.N_UNREAD_OLDER % (4, "    row")
    assert "4 older not shown" in older, older
    assert "worklist.py --reports" in older, older


def test_r4_an_unknown_mode_prints_the_usage_line(sc):
    got = sc.py("wl_report.py", "--unread")
    assert got.rc == 2, got.rc
    assert "unknown mode --unread" in got.err, got.err
    assert "usage: wl_report.py --subagent-stop" in got.err, got.err
    assert "--list [--unread|--all]" in got.err, got.err
    # CONTROL: a real mode does not print the unknown-mode line.
    ok = sc.py("wl_report.py", "--list", "--unread")
    assert "unknown mode" not in ok.out + ok.err
