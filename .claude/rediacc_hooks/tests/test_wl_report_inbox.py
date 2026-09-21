"""Ported from `.claude/hooks/stop/test-report-inbox.sh`.

Tests for `wl_report.py` (durable sub-agent report capture plus the unread inbox) and `wl_wait.py` (the blocking waiter that replaces the poll cron).

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

import pytest

from rediacc_hooks.tests import wlfix

HERE = wlfix.STOP_DIR
READER = "aaaaaaaa-1111"
BIG = "a substantive body. " * 40

XDIST_GROUP = "stop-hook-harnesses"


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

    def mkreq(self, rid: str, frm: str, to: str, body: str) -> None:
        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.stem(".requests").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"ev": "ask", "id": rid, "from": frm, "to": to, "at": stamp, "body": body}
                )
                + "\n"
            )

    def waiter(self, *argv: str, out: pathlib.Path):
        """`wl_wait.py` in the background, its stdout captured to a file.

        The write handle is kept and closed at teardown rather than left to the garbage collector: pytest promotes an unraisable exception from a finalized file object into a test failure, so an unclosed redirect target fails the case it belongs to for a reason that has nothing to do with the waiter.
        """
        handle = out.open("w", encoding="utf-8")
        self.handles.append(handle)
        return subprocess.Popen(
            [sys.executable, str(HERE / "wl_wait.py"), *argv],
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=dict(self.env),
        )

    def close_handles(self) -> None:
        for handle in self.handles:
            with contextlib.suppress(OSError):
                handle.close()
        self.handles = []


@pytest.fixture
def sc(tmp_path):
    """The base for every scratch universe, captured ONCE.

    Deriving it from TMPDIR at call time instead would nest each case inside the previous case's TMPDIR, and the slugified worklist name (which embeds the whole absolute path) then grows until it trips ENAMETOOLONG a dozen cases in, which is exactly what the first run of the bash suite did.
    """
    scratch = Scratch(tmp_path / "case")
    yield scratch
    scratch.close_handles()


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


def alive(proc: subprocess.Popen) -> bool:
    return proc.poll() is None


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
        procs[-1].stdin.write(payload)
        procs[-1].stdin.close()
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


def test_15_wl_wait_misuse(sc):
    got = sc.py("wl_wait.py")
    assert got.rc == 2, "no argument should exit 2, got %d" % got.rc
    # The needle tracks the help text: the bare-usage path prints the full contract, not a "usage:" one-liner. Case 22 owns the detail; this one only asserts that misuse is explained on stderr at all.
    assert "BACKGROUND TASK" in got.out + got.err, "the contract was not printed on stderr"
    got = sc.py("wl_wait.py", "abc")
    assert got.rc == 2, "a short prefix should exit 2, got %d" % got.rc
    assert "bad prefix" in got.out + got.err, "a short prefix must name the problem"
    got = sc.py("wl_wait.py", "aaaaaaaa", "--timeout", "0")
    assert got.rc == 2, "a non-positive timeout should exit 2, got %d" % got.rc


LOCK_RE = re.compile(r"_flock\(|fcntl\.flock\(|import fcntl")


def lock_hits(name: str) -> int:
    """Lines matching the lock pattern, the same count `grep -cE` produced."""
    return sum(
        1 for line in (HERE / name).read_text(encoding="utf-8").splitlines() if LOCK_RE.search(line)
    )


def test_16_wl_wait_takes_no_lock():
    """Structural, with a proven-live control."""
    assert lock_hits("wl_wait.py") == 0, "wl_wait.py makes a lock call"
    assert lock_hits("wl_report.py") == 0, "wl_report.py makes a lock call"
    # CONTROL: the SAME pattern must fire on a file that really does lock, or it is a pattern that can never match and the two assertions above prove nothing.
    hits = lock_hits("wl_store.py")
    assert hits > 0, "CONTROL: the pattern is dead, it found 0 hits in wl_store.py"


def test_17_wl_wait_wakes_on_a_new_request_not_a_pre_existing_one(sc):
    """17a is the spin-loop regression: arming on "the slice is non-empty" would fire instantly, forever. 17b is its control: with that same request still unresolved, a NEW one DOES wake it, and prints ONLY the new one."""
    out = sc.t / "w1.out"
    sc.mkreq("preexist", "bbbbbbbb", "aaaaaaaa", "a request the session has already seen")
    proc = sc.waiter("aaaaaaaa", "--timeout", "0.15", out=out)
    try:
        time.sleep(4)
        assert alive(proc), "a pre-existing request woke the waiter: %s" % out.read_text()
        assert out.read_text(encoding="utf-8") == "", "the waiter printed while waiting"
        sc.mkreq("fresh001", "bbbbbbbb", "aaaaaaaa", "THE NEW REQUEST")
        time.sleep(5)
        assert not alive(proc), "CONTROL: a new request did not wake the waiter"
    finally:
        if alive(proc):
            proc.kill()
        proc.wait()
    text = out.read_text(encoding="utf-8")
    assert "THE NEW REQUEST" in text, text[:300]
    assert "already seen" not in text, "it reprinted the pre-existing request"
    assert "--answer" in text, "it did not print the answer command"


def test_17c_the_baseline_suppresses_a_request_already_seen_when_the_signature_moves(sc):
    """17a alone does NOT prove the request baseline: with no new appends the cheap signature gate never opens, so the fold never runs and the baseline is never consulted. Mutating the baseline away leaves 17a green. THIS case forces the signature to move while the only classified item is one the session already had, a third session declining a pre-existing BROADCAST whose id
    counts as ours in `my_requests_sig`, so the fold DOES run and only the baseline can suppress the wake."""
    store = wlfix.import_wl("wl_store")
    req = sc.stem(".requests")
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with req.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ev": "ask",
                    "id": "bcast001",
                    "from": "bbbbbbbb",
                    "to": "*",
                    "at": stamp,
                    "body": "A BROADCAST ALREADY IN CONTEXT",
                }
            )
            + "\n"
        )
    out = sc.t / "w5.out"
    proc = sc.waiter("aaaaaaaa", "--timeout", "0.2", out=out)
    try:
        time.sleep(2)
        worklist = sc.worklist()
        before = store.my_requests_sig(worklist, "aaaaaaaa")
        with req.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "ev": "decline",
                        "id": "bcast001",
                        "by": "cccccccc",
                        "at": stamp,
                        "reason": "not my area",
                    }
                )
                + "\n"
            )
        after = store.my_requests_sig(worklist, "aaaaaaaa")
        # The premise of this case, asserted rather than assumed: if the signature did NOT move, the fold would be skipped and the case would prove nothing.
        assert before != after, (
            "the third-party decline did not move the signature (%s), so this case is vacuous"
            % before
        )
        time.sleep(5)
        assert alive(proc), (
            "an already-seen request woke it once the fold ran: %s" % out.read_text()
        )
        assert out.read_text(encoding="utf-8") == "", "the waiter printed something"
    finally:
        if alive(proc):
            proc.kill()
        proc.wait()


def test_18_foreign_traffic_does_not_wake_the_waiter(sc):
    out = sc.t / "w2.out"
    proc = sc.waiter("aaaaaaaa", "--timeout", "0.3", out=out)
    try:
        time.sleep(2)
        sc.mkreq("foreign1", "bbbbbbbb", "cccccccc", "traffic between two other sessions")
        time.sleep(5)
        assert alive(proc), "foreign traffic woke the waiter: %s" % out.read_text()
        assert out.read_text(encoding="utf-8") == "", "the waiter printed for foreign traffic"
        # CONTROL: the same fixture, addressed to us, DOES wake it, so the silence above is a signature gate working and not a waiter that is simply deaf.
        sc.mkreq("mine0001", "bbbbbbbb", "aaaaaaaa", "ADDRESSED TO ME")
        time.sleep(5)
        assert not alive(proc), "CONTROL: an addressed append did not wake it"
    finally:
        if alive(proc):
            proc.kill()
        proc.wait()
    assert "ADDRESSED TO ME" in out.read_text(encoding="utf-8")


def test_19_wl_wait_wakes_on_a_new_subagent_report(sc):
    out = sc.t / "w3.out"
    proc = sc.waiter("aaaaaaaa", "--timeout", "0.3", out=out)
    try:
        time.sleep(2)
        sc.stop_event(
            "await-report-5151515151515151",
            "waiter-report",
            "A REPORT THAT SHOULD WAKE IT\n" + BIG,
        )
        time.sleep(5)
        assert not alive(proc), "a new report did not wake the waiter"
    finally:
        if alive(proc):
            proc.kill()
        proc.wait()
    text = out.read_text(encoding="utf-8")
    assert "A REPORT THAT SHOULD WAKE IT" in text, text[:300]
    assert "--show" in text, "it did not name the read command"


def test_20_wl_wait_timeout_prints_one_bounded_line_and_exits_zero(sc):
    got = sc.py("wl_wait.py", "aaaaaaaa", "--timeout", "0.05")
    assert got.rc == 0, "timeout should exit 0, got %d" % got.rc
    text = (got.out + got.err).strip()
    assert "INBOX-WAIT" in text, text[:300]
    assert len(text.splitlines()) == 1, "the timeout line is not ONE line: %r" % text


def test_21_wl_wait_does_not_block_a_concurrent_worklist_write(sc):
    store = wlfix.import_wl("wl_store")
    out = sc.t / "w4.out"
    proc = sc.waiter("aaaaaaaa", "--timeout", "0.4", out=out)
    try:
        time.sleep(2)
        path = store.requests_path(sc.worklist())
        start = time.monotonic()
        store._append_lines(path, str(path) + ".lock", [{"ev": "probe"}])
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, "a locked write took %.3fs while the waiter ran" % elapsed
    finally:
        if alive(proc):
            proc.kill()
        proc.wait()
    # CONTROL: the SAME measurement, against a deliberate LOCK_EX holder, must show blocking. Without it, "fast" could just mean the timer cannot detect a stall.
    path = store.requests_path(sc.worklist())
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            'import fcntl,sys,time\nf=open(sys.argv[1],"w")\nfcntl.flock(f, fcntl.LOCK_EX)\ntime.sleep(3)\n',
            str(path) + ".lock",
        ]
    )
    time.sleep(1)
    start = time.monotonic()
    store._append_lines(path, str(path) + ".lock", [{"ev": "probe2"}])
    held = time.monotonic() - start
    holder.wait()
    assert held > 1.0, (
        "CONTROL: a real LOCK_EX holder blocked for only %.3fs, so the timer cannot detect a stall "
        "and the assertion above is vacuous" % held
    )


def test_22_wl_wait_help_explains_how_to_invoke_it(sc):
    """The help was ONE usage line. A tool whose entire value depends on being launched in the BACKGROUND, and whose help does not say so, does not get used, and that is not hypothetical: it shipped, and the session that built it kept polling instead. These pin the facts a reader cannot infer from the signature."""
    got = sc.py("wl_wait.py", "--help")
    assert got.rc == 0, "--help should exit 0, got %d" % got.rc
    text = got.out + got.err
    for needle in (
        "BACKGROUND TASK",
        "EXIT IS THE NOTIFICATION",
        "BACKLOG DETECTOR",
        "NO QUOTES",
        "ONLY FIRES ONCE",
        "EXIT CODES",
    ):
        assert needle in text, "--help never says %r" % needle
    # The bare-usage path must carry the SAME text, on stderr, exit 2. Help only reachable by asking for it is not reachable by the reader who needs it.
    bare = sc.py("wl_wait.py")
    assert bare.rc == 2, "a bare invocation should exit 2, got %d" % bare.rc
    assert "EXIT IS THE NOTIFICATION" in bare.err, (
        "CONTROL: bare usage must print the contract, not a one-liner"
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


def store_bytes(sc: Scratch) -> int:
    """Every byte of the event store: the tracked writer files plus the legacy log.

    THE BASH MEASURED ONE PATH THAT DOES NOT EXIST in this fixture. `wc -c < <missing>` prints nothing, so its before and after were both the empty string and the comparison passed whatever the nudge did. Summing the whole store gives the control the discrimination it was written to have.
    """
    total = 0
    for path in sorted((sc.repo / "agent" / "worklist").glob("*.jsonl")):
        total += path.stat().st_size
    legacy = sc.stem(".events.jsonl")
    if legacy.is_file():
        total += legacy.stat().st_size
    return total


def nudge(sc: Scratch) -> str:
    payload = json.dumps({"session_id": READER, "cwd": str(sc.repo), "tool_name": "Bash"})
    return sc.py("wl_wait.py", "--nudge", stdin=payload).out


def item_id(result: wlfix.Result) -> str:
    found = re.search(r"#([0-9a-f]+)", result.out)
    assert found, "--add produced no item id: %s" % result.out[:200]
    return found.group(1)


def test_25_the_posttooluse_nudge_fires_and_is_throttled(sc):
    """The waiter fires ONCE and exits; nothing relaunches it, so a session goes deaf after its first event, worse than the cron, which at least fires again. Measured live: a waiter fired at 16:13, a peer answered at 16:16, and the answer was never seen. This is the re-arm.

    v20: THE FIXTURE NOW OWES SOMETHING, and that is not scaffolding. The nudge became work-aware, so an empty worklist is a DRAINED session and this case would have gone silent, passing its controls and losing its subject. Case 25b owns the drained half; this case keeps owning "with work to do and nobody listening, the nudge fires".
    """
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sc.stem(".sessions").write_text("bbbbbbbb %s peer session\n" % stamp, encoding="utf-8")
    item_id(sc.py("worklist.py", "--add", "aaaaaaaa", "the thing this session still owes"))
    out = nudge(sc)
    assert "NOT LISTENING" in out, (
        "with a live peer and work to do the nudge must fire: %s" % out[:200]
    )
    assert "wl_wait.py" in out, "it does not carry the exact command"
    assert "BACKGROUND task" in out, "it does not say background"
    # CONTROL 1: throttled. This is what stops it becoming noise, and noise is how a mechanism gets switched off.
    assert nudge(sc) == "", "CONTROL: the second call must be silent"
    # CONTROL 2: a fresh heartbeat silences it once the throttle is cleared.
    sc.stem(".waiternudge-aaaaaaaa").unlink(missing_ok=True)
    sc.stem(".waiter-aaaaaaaa").write_text("", encoding="utf-8")
    assert nudge(sc) == "", "CONTROL: a live waiter heartbeat must silence it"
    # CONTROL 3: a STALE heartbeat must NOT silence it, or a dead waiter looks alive forever and the nudge never fires again. This is the case a marker written once at launch would fail, and it is why the waiter re-touches every tick.
    old = time.time() - 3600
    os.utime(sc.stem(".waiter-aaaaaaaa"), (old, old))
    assert "NOT LISTENING" in nudge(sc), "CONTROL: a STALE heartbeat must not silence it"


def test_25_control_with_no_live_peer_there_is_nothing_to_listen_for(sc):
    """There is nobody who could send anything, so a waiter would be pure cost; over-firing is how this gets routed around. The OPEN ITEM is carried over deliberately: without it this control would be satisfied by the work-awareness gate and would stop saying anything about peers at all, and a control that passes for the wrong reason is not a control."""
    sc.py("worklist.py", "--add", "aaaaaaaa", "still owed, and still nobody to hear from")
    assert nudge(sc) == "", "the nudge fired with no live peer"


def test_25b_the_nudge_is_work_aware_and_a_drained_session_is_not_nagged(sc):
    """THE DEFECT, observed live 2026-08-19. A session that had finished everything (no open items, no background jobs, its VMs torn down) was still told "NOT LISTENING: 1 live peer session(s)" on EVERY tool call, and the only way to satisfy it was to hold an hour-long process it had no use for. The waiter is worth its keep while there is something to do with what it hears; past
    that it is a process plus a nag.

    EVERY ASSERTION BELOW IS PAIRED WITH ITS OPPOSITE ON THE SAME FIXTURE: the silence is only evidence once the identical call has been shown to speak.
    """
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sc.stem(".sessions").write_text("bbbbbbbb %s peer session\n" % stamp, encoding="utf-8")

    def unnudge():
        """Clear the 10-minute throttle."""
        sc.stem(".waiternudge-aaaaaaaa").unlink(missing_ok=True)

    def wl_cli(*argv: str):
        return sc.py("worklist.py", *argv)

    first = item_id(wl_cli("--add", "aaaaaaaa", "the one thing this session owes"))
    assert "NOT LISTENING" in nudge(sc), "RED: an open item and a live peer must make it fire"
    # THE FIX: tick the only item and the same call goes quiet. Same peer, same absent waiter, same throttle state, and the item is the only thing that moved.
    unnudge()
    wl_cli("--tick", "aaaaaaaa", first, "drained, exit 0 from this suite")
    assert nudge(sc) == "", "GREEN: a drained session must be left alone"
    # CONTROL: an IN-FLIGHT item is outstanding work too. A `[>]` lease is how a background worker is tracked in this repo, and a session supervising one is the case that most needs to hear its report, so "no OPEN items" alone must never buy the silence.
    unnudge()
    leased = item_id(wl_cli("--add", "aaaaaaaa", "delegated to a worker"))
    wl_cli("--lease", "aaaaaaaa", leased, "+30", "worker:bg1", "watching it")
    assert "NOT LISTENING" in nudge(sc), "CONTROL: a fresh [>] lease must still nudge"
    # CONTROL: a `[?]` is NOT outstanding work for this purpose, and the reason is the mechanism rather than tidiness. A deferral is parked on the OPERATOR, whose answer arrives in this session's own turn or executes as its DEFAULT. No peer can deliver one, so there is nothing here for a waiter to hear.
    unnudge()
    wl_cli("--tick", "aaaaaaaa", leased, "worker reported, exit 0")
    parked = item_id(wl_cli("--add", "aaaaaaaa", "flip the flag?"))
    wl_cli(
        "--defer",
        "aaaaaaaa",
        parked,
        "flip the flag? DEFAULT: leave it off WHY: flipping it changes billing for live users, "
        "an operator-only call HOW: the operator confirms, or the DEFAULT leaves it off",
    )
    assert nudge(sc) == "", "CONTROL: a session holding only a [?] is still drained"
    # CONTROL: and the probe must not have EATEN the throttle it never wrote. A silent nudge that still stamps the counter would drive the Stop-side backstop (V_NO_WAITER, keyed on nudges_ignored) to accuse a session that was never asked for anything.
    assert not sc.stem(".waiternudge-aaaaaaaa").exists(), (
        "CONTROL: a silent nudge stamped the ignored-count anyway"
    )
    # CONTROL: the probe READS the store and never writes it. `wl_wait` must not take the events lock (case 16 owns the structural half); folding with sync=True takes a BLOCKING LOCK_EX, which is the one thing this process is forbidden to do, and the module docstring says why: an hour-long holder would stall every --ask/--add/--tick in the repo and silently no-op the two
    # LOCK_NB paths.
    #
    # THE UNSYNCED MARKDOWN LINE IS THE WHOLE CONTROL. Without it the fixture's markdown hash already matches the fold's, sync=True has nothing to append, and the byte comparison passes under BOTH spellings: measured, not assumed, since a first draft of this control could not tell them apart.
    unnudge()
    with sc.worklist().open("a", encoding="utf-8") as handle:
        handle.write("- [ ] (aaaaaaaa) a legacy markdown line the event log has never seen\n")
    before = store_bytes(sc)
    assert "NOT LISTENING" in nudge(sc), (
        "the unsynced markdown item is outstanding work in its own right"
    )
    after = store_bytes(sc)
    assert after == before, "CONTROL: the nudge did not leave the event log byte-identical"


def test_26_a_main_loop_turn_is_not_captured_as_a_report(sc):
    """THE LOOP THIS CLOSES, found by running the thing rather than testing it. SubagentStop also fires for the session's OWN main-loop turns. Each was captured as a "report"; the waiter saw a new report and fired; the session spent a turn reading and re-arming; that turn was captured; the waiter fired again. It does not converge, and every cycle costs the exact turn the waiter
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
