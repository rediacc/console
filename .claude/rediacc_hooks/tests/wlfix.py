"""The fixture layer for the worklist Stop-hook control suite, ported from bash.

REPLACES `.claude/hooks/stop/worklist-cases/_harness.sh`, which was the ONE copy of every fixture helper for a 16,000-line bash suite whose whole subject is Python: `worklist.py` and the `wl_*` modules beside it. The suite drove that Python through `python3 "$HOOK"` and asserted on its stdout with `grep -qF`, so every helper below is the same subprocess call with the same
environment; what moves is the language the assertions are written in, not what is executed.

WHY THE SANDBOX IS REBUILT PER TEST RATHER THAN SHARED. The bash suite carried one `$BASE` for all 802 cases and `setup()` began with `rm -rf "$BASE"`, so a case that forgot the call inherited its predecessor's world. pytest gives each test its own `tmp_path`, which makes that inheritance unrepresentable instead of merely discouraged, and the cases that DELIBERATELY chain (a second
stop on an unmoved world, a third that trips the stuck detector) chain inside one test function, where the sequence is visible in one place.

THE AMBIENT SCRUB IS STILL LOAD-BEARING and is done here rather than once at import. The hook reads ~65 `WORKLIST_*` knobs; a value exported in the shell that launched pytest silently retunes it, and `CLAUDE_CODE_SESSION_ID` is worse than that. Since v19 every `<me>` argument is checked against the real session id (`wl_core.check_me`), which resolves `WORKLIST_SESSION_ID` first and
`CLAUDE_CODE_SESSION_ID` second. Run from inside a Claude session with the ambient id live, every fixture prefix mismatches and the call sites refuse: mass breakage that looks like a broken feature. Run with it unset, `check_me` takes its silent-pass path and every identity case passes VACUOUSLY, a green proving nothing. The second is the dangerous one, because it is green.
`WORKLIST_SESSION_ID` is therefore pinned to the fixture id, and the identity module carries the meta-control that proves the scrub happened.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import time

import pytest
from rediacc_ci import paths

# The hook under test, and the directory `wl_*` imports resolve against.
STOP_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"
HOOK = STOP_DIR / "worklist.py"

# The suite's own session, and the prefix every `<me>` argument uses.
SID = "deadbeef-1111-2222-3333-444444444444"
ME = "deadbeef"

# A STATE.md fresh enough and well-shaped enough to satisfy the gate. Keeps the literal phrase "ci-overhaul session" (the PostCompact cases grep for it in the additionalContext) and carries the mandatory '## Next action' section.
STATE_BODY = """You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2. Round 23 went red on a dead-shell finding, now fixed by running the stop-gate suite from test-hooks.sh. The rediacc-autopilot App already exists and is validated, so never report it as blocked on the operator.

## Next action

Push and watch the run, then bump the submodule pointers to the squash commits before the merge chain."""

# TWO live crons by default, since v9: the enforced shape is one work loop plus the 5-minute inbox poll, and a session missing the poll now blocks.
DEFAULT_CRONS = [
    {"id": "w", "schedule": "17 * * * *"},
    {"id": "p", "schedule": "*/5 * * * *"},
]

# Reset by `setup()` for the reason the bash comment gave: a plain assignment in one case leaked into the next two and silently suppressed a check.
RESET_KNOBS = (
    "WORKLIST_OUTQ_MAX",
    "WORKLIST_BG_OUTPUT_DIR",
    "WORKLIST_HARNESS_PID",
    "WORKLIST_QUIET_WAKES",
    "WORKLIST_PROJECTS_DIR",
    "WORKLIST_DEAD_HOURS",
    "WORKLIST_ARCHIVE_HOURS",
    "WORKLIST_AGENT_HINT",
    "WORKLIST_AGENT_HINT_MAX_PER_SESSION",
    "WORKLIST_AGENT_HINT_MIN_SCORE",
    "WORKLIST_AGENT_HINT_MIN_MARGIN",
    "WORKLIST_FOCUS",
    "WORKLIST_HINTS_FILE",
)

BIN_ONLY = ("python3", "sh", "bash", "cat", "date")


def scrubbed_environ() -> dict[str, str]:
    """`os.environ` with every knob the suite must not inherit removed."""
    out = {}
    for key, value in os.environ.items():
        if key.startswith("WORKLIST_"):
            continue
        if key in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID"):
            continue
        out[key] = value
    return out


def peer_id(prefix: str) -> str:
    """The full session id a fixture PREFIX stands for."""
    return "%s-1111-2222-3333-444444444444" % prefix


def decision_of(raw: str) -> str:
    """The hook's verdict, defaulting to `allow` exactly as the bash reader did."""
    text = raw.strip()
    if not text:
        return "allow"
    try:
        return json.loads(text).get("decision", "allow")
    except (ValueError, AttributeError):
        return "allow"


def mk_section(owner: str, minutes_ago: float, body: str) -> str:
    """One stamped `## SESSION` section, backdated by `minutes_ago`."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes_ago * 60))
    return "## SESSION %s %s\n\n%s\n" % (owner, stamp, body.strip())


def section_now(owner: str, body: str) -> str:
    """One section stamped now."""
    return mk_section(owner, 0, body)


def import_wl(name: str):
    """Import a `wl_*` module from the hook directory, as the bash `python3 -c` did."""
    paths.on_sys_path(STOP_DIR)
    return __import__(name)


class Result:
    """One hook invocation: its stdout, its stderr and its exit code."""

    def __init__(self, stdout: str, stderr: str, rc: int):
        self.out = stdout
        self.err = stderr
        self.rc = rc

    @property
    def decision(self) -> str:
        return decision_of(self.out)

    def __contains__(self, needle: str) -> bool:
        return needle in self.out


class Fixture:
    """The sandbox `_harness.sh` built, with one method per bash helper."""

    def __init__(self, base: pathlib.Path):
        self.base = base
        self.hook = HOOK
        self.sid = SID
        # Exported suite-wide immediately after the scrub, for the reason the bash comment gave: every case passes `deadbeef` as its `<me>`, so one export arms the identity check for all of them.
        self.env: dict[str, str] = scrubbed_environ()
        self.env["WORKLIST_SESSION_ID"] = SID
        self.bg = "[]"
        self.crons = json.dumps(DEFAULT_CRONS)
        self.judge_mode = "off"
        self.cadence = "off"
        self.gha = ""
        self.wl = base / "placeholder.md"

    @property
    def proj(self) -> pathlib.Path:
        return self.base / "proj"

    @property
    def transcript(self) -> pathlib.Path:
        return self.base / "t.jsonl"

    @property
    def events(self) -> pathlib.Path:
        """The legacy event log beside the worklist markdown."""
        return self.stem(".events.jsonl")

    @property
    def sessions(self) -> pathlib.Path:
        """The session-brief ledger beside the worklist markdown."""
        return self.stem(".sessions")

    @property
    def store_dir(self) -> pathlib.Path:
        return pathlib.Path(self.env.get("WORKLIST_STORE_DIR", str(self.base / "store")))

    def stem(self, suffix: str) -> pathlib.Path:
        """A sibling of the worklist markdown, e.g. `.reggate-deadbeef`."""
        return pathlib.Path(str(self.wl)[: -len(".md")] + suffix)

    def state_file(self, owner: str = ME) -> pathlib.Path:
        return self.proj / "agent" / owner / "STATE.md"

    def owner_state_file(self, owner: str) -> pathlib.Path:
        """The file that OWNS `owner`'s section.

        A real session (deadbeef, cafe1234) writes its own agent/<owner>/STATE.md, while a PLANTED pseudo-owner exists only as a heading inside the default session's document, which is how those cases fabricate a peer without running one.
        """
        own = self.state_file(owner)
        return own if own.is_file() else self.state_file(ME)

    def wl_events(self) -> str:
        """The WHOLE store: every writer file plus the legacy log the reader unions."""
        parts = []
        store = self.store_dir
        if store.is_dir():
            parts.extend(path.read_text(encoding="utf-8") for path in sorted(store.glob("*.jsonl")))
        if self.events.is_file():
            parts.append(self.events.read_text(encoding="utf-8"))
        return "".join(parts)

    def setup(self) -> None:
        """Rebuild the fixture world and reset EVERY knob `run()` reads."""
        self.bg = "[]"
        self.crons = json.dumps(DEFAULT_CRONS)
        self.judge_mode = "off"
        self.cadence = "off"
        # PINNED, NOT INHERITED. The hook no-ops when GITHUB_ACTIONS=true, so a suite that inherits the ambient value passes locally and silently no-ops in CI, where the empty output reads as a failure.
        self.gha = ""
        for knob in RESET_KNOBS:
            self.env.pop(knob, None)

        if self.base.exists():
            shutil.rmtree(self.base)
        for rel in ("proj/.git", "tmp/claude-worklist", "tasks/session-deadbeef"):
            (self.base / rel).mkdir(parents=True, exist_ok=True)

        # THE STORE GOES OUTSIDE THE FIXTURE REPO, and AFTER the rmtree above: several cases build a real git repo at proj/ and assert on ITS state, and a store written inside it made those cases fail for a reason that had nothing to do with what they test.
        store = self.base / "store"
        store.mkdir(parents=True, exist_ok=True)
        self.env["WORKLIST_STORE_DIR"] = str(store)
        # EXPORTED BESIDE IT, and the pairing is the point: the store has two halves, the writer files under WORKLIST_STORE_DIR and everything still resolved from the worklist path under TMPDIR. One call that straddled the two wrote three fixture items into the operator's real worklist.
        self.env["TMPDIR"] = str(self.base / "tmp")
        # The fixture .git is a plain directory, so `git symbolic-ref` exits 128 and every branch-dependent check would be SKIPPED as no-branch.
        self.env["WORKLIST_AGENT_BRANCH"] = "agenttest"
        # PINNED INTO THE FIXTURE: unset, the unread-reports surface reads the OPERATOR'S REAL report store on every stop in this suite.
        self.env["WORKLIST_REPORTS_DIR"] = str(self.base / "reports")
        # PINNED for the same reason: unset, the specialist-agent matcher scores every case against the operator's real .claude/agents, so a verdict would change whenever somebody edited an agent description.
        (self.base / "agents").mkdir(parents=True, exist_ok=True)
        self.env["WORKLIST_AGENTS_DIR"] = str(self.base / "agents")

        (self.proj / "agent" / ME).mkdir(parents=True, exist_ok=True)
        (self.proj / ".agent").mkdir(parents=True, exist_ok=True)

        slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(self.proj)).lstrip("_")
        self.wl = self.base / "tmp" / "claude-worklist" / ("%s.md" % slug)
        self.wl.write_text("", encoding="utf-8")

        self.transcript.write_text(
            json.dumps({"type": "user", "message": {"content": "go"}}) + "\n", encoding="utf-8"
        )

        binonly = self.base / "binonly"
        binonly.mkdir(parents=True, exist_ok=True)
        (self.base / "nohome").mkdir(parents=True, exist_ok=True)
        for name in BIN_ONLY:
            found = shutil.which(name)
            if found:
                link = binonly / name
                if link.is_symlink() or link.exists():
                    link.unlink()
                link.symlink_to(found)

    def say(self, text: str) -> None:
        """One assistant TEXT block.

        Does NOT imply a turn boundary, and must not: several cases depend on two `say` calls landing in ONE turn, which is exactly the shape that once hid a '## Remaining' section from this hook.
        """
        self.append_transcript(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
        )

    def used_tool(self, name: str) -> None:
        """One assistant record whose only block is a tool_use.

        A gate whose subject is the difference between announcing a tool call and making one cannot be tested without it. Like `say`, this implies no turn boundary.
        """
        self.append_transcript(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "id": "tu_1", "name": name, "input": {}}]
                },
            }
        )

    def operator_says(self, text: str) -> None:
        """A REAL operator turn carrying words.

        The shape is the one `wl_admit._is_operator_turn` recognises: type=user, content a STRING, and NO isMeta. Hook feedback carries isMeta:true and tool results carry an array, and neither is a person speaking.
        """
        self.append_transcript({"type": "user", "message": {"content": text}})

    def newturn(self) -> None:
        """A fresh user record; `transcript_tail` only reads back to the last one."""
        self.append_transcript({"type": "user", "message": {"content": "go"}})

    def append_transcript(self, record: dict) -> None:
        with self.transcript.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def task(self, ident, status: str, subject: str, blocked_by: str = "") -> None:
        payload = {
            "id": str(ident),
            "status": status,
            "subject": subject,
            "blockedBy": blocked_by.split(",") if blocked_by else [],
        }
        path = self.base / "tasks" / "session-deadbeef" / ("%s.json" % ident)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    def mk_agent(self, name: str, description: str) -> None:
        """One fixture agent in the corpus.

        INVENTED NOUNS ONLY in the cases: a fixture that borrows the real agents' vocabulary would pass or fail depending on prose nobody thinks of as test data, which is the coupling WORKLIST_AGENTS_DIR removes.
        """
        body = "---\nname: %s\ndescription: %s\ntools: Bash\nmodel: opus\n---\nbody text\n" % (
            name,
            description,
        )
        (self.base / "agents" / ("%s.md" % name)).write_text(body, encoding="utf-8")

    def add_item(self, line: str) -> None:
        """Append one raw markdown line to the fixture worklist."""
        with self.wl.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def plant_state(self, body: str) -> None:
        """Plant a STATE.md DIRECTLY on disk, bypassing `--state`.

        The CLI refuses a badly-shaped body at write time, so piping one through it produces no file and the previous document survives. The Stop check's shape detection must still work regardless, because a document can reach that path without the CLI.
        """
        self.state_file().write_text(body, encoding="utf-8")

    def plant_doc(self, body: str) -> None:
        """The same raw plant, named for a whole multi-section DOCUMENT."""
        self.plant_state(body)

    def age_state(self, owner: str, minutes_ago: float) -> None:
        """Backdate that section's heading stamp.

        The heading stamp is the age source now, so touching the file's mtime no longer ages a section written by `--state`: it moves the FALLBACK. This RAISES when the owner's heading is not there rather than aging nothing and passing quietly.
        """
        path = self.owner_state_file(owner)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes_ago * 60))
        text = path.read_text(encoding="utf-8")
        new, count = re.subn(
            r"(?m)^(##[ \t]+SESSION[ \t]+%s\b)[ \t]*.*$" % re.escape(owner),
            lambda m: m.group(1) + " " + stamp,
            text,
        )
        if count != 1:
            raise AssertionError(
                "age_state: expected ONE '## SESSION %s' heading, found %d" % (owner, count)
            )
        path.write_text(new, encoding="utf-8")

    def section_of(self, owner: str) -> str:
        """That owner's section rendered, or the empty string."""
        store = import_wl("wl_store")
        path = self.owner_state_file(owner)
        try:
            text = path.read_text(encoding="utf-8")
            mtime = path.stat().st_mtime
        except OSError:
            return ""
        for section in store.agent_state_parse(text, mtime):
            if section["owner"] == owner:
                return store.agent_state_render([section])
        return ""

    def state_as(self, prefix: str, body: str) -> None:
        """Write STATE.md as ANOTHER session, LOUDLY on failure.

        The tool refuses to create a session folder, so the peer's directory is made first. And the refusal is raised rather than swallowed: a peer body two characters under the floor was once silently refused, and three cases then asserted the ABSENCE of a section that had never been written.
        """
        (self.proj / "agent" / prefix).mkdir(parents=True, exist_ok=True)
        env = dict(self.env)
        env["WORKLIST_SESSION_ID"] = peer_id(prefix)
        result = self.python(["--state", prefix], stdin=body, env=env)
        if result.rc != 0:
            raise AssertionError(
                "FIXTURE BROKEN: state_as %s was refused (rc=%d): %s"
                % (prefix, result.rc, (result.out + result.err)[:200])
            )

    def hand_now(self) -> None:
        """The canonical fresh handover document for the default session."""
        self.python(["--state", ME], stdin=STATE_BODY)

    def brief_now(self, who: str = ME, text: str = "doing the thing") -> None:
        self.brief_at(who, 0, text)

    def brief_at(self, who: str, minutes_ago: float, text: str = "old") -> None:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes_ago * 60))
        with self.sessions.open("a", encoding="utf-8") as handle:
            handle.write("%s %s %s\n" % (who, stamp, text))

    def brief_other(self, prefix: str) -> None:
        """A fresh brief for another live session."""
        self.brief_at(prefix, 0, "other session")

    def phantom_store(self, prefix: str, age_minutes: float) -> None:
        """Plant three events by `prefix` at that age, each owning one open item."""
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - age_minutes * 60))
        with self.events.open("a", encoding="utf-8") as handle:
            for index in range(3):
                handle.write(
                    json.dumps(
                        {
                            "ev": "add",
                            "id": "ph%s%d" % (prefix[:4], index),
                            "at": stamp,
                            "by": prefix,
                            "s": " ",
                            "o": prefix,
                            "t": "phantom-owned item %d" % index,
                        }
                    )
                    + "\n"
                )

    def shim_judge(self, regression_gate: str = "") -> None:
        """A canned `claude` on the fixture PATH that always says stop."""
        payload = {
            "is_error": False,
            "structured_output": {"verdict": "stop", "reason": "ok", "next_action": "none"},
        }
        if regression_gate:
            payload["structured_output"]["regression_gate"] = json.loads(regression_gate)
        script = self.base / "binonly" / "claude"
        script.write_text(
            "#!/bin/bash\necho %s\n" % json.dumps(json.dumps(payload)), encoding="utf-8"
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

    def git(self, *args: str):
        return subprocess.run(
            ["git", *args], cwd=str(self.proj), capture_output=True, text=True, check=False
        )

    def reg_repo(self) -> pathlib.Path:
        """A git repo with one base commit; the marker will init at this HEAD."""
        self.git("init", "-q")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        (self.proj / "base.txt").write_text("base\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "chore: base")
        return self.marker()

    def marker(self) -> pathlib.Path:
        """The regression-gate marker for the default session."""
        return self.stem(".reggate-deadbeef")

    def fixcommit(self, relative: str, subject: str) -> None:
        target = self.proj / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write("x\n")
        self.git("add", "-A")
        self.git("commit", "-qm", subject)

    def python(self, argv: list[str], stdin: str = "", env: dict | None = None) -> Result:
        base = dict(env or self.env)
        base.setdefault("CLAUDE_PROJECT_DIR", str(self.proj))
        base.setdefault("WORKLIST_TASKS_DIR", str(self.base / "tasks"))
        proc = subprocess.run(
            [sys.executable, str(self.hook), *argv],
            input=stdin,
            capture_output=True,
            text=True,
            env=base,
            check=False,
        )
        return Result(proc.stdout, proc.stderr, proc.returncode)

    def cli(self, *argv: str, env: dict | None = None, stdin: str = "") -> Result:
        """Drive the worklist CLI against the fixture store."""
        return self.python(list(argv), stdin=stdin, env=env)

    def cli_as(self, prefix: str, *argv: str, stdin: str = "") -> Result:
        """Drive the CLI as ANOTHER session, without leaking that id onward."""
        env = dict(self.env)
        env["WORKLIST_SESSION_ID"] = peer_id(prefix)
        return self.python(list(argv), stdin=stdin, env=env)

    def askid(self, *argv: str) -> str:
        """`--ask ...`, returning the new request id the CLI printed."""
        out = self.cli("--ask", *argv).out
        found = re.search(r"#([0-9a-f]{8})", out)
        return found.group(1) if found else ""

    def askid_as(self, prefix: str, *argv: str) -> str:
        """The same, for a request sent BY another session.

        IT DOES NOT MIRROR THE BASH HELPER OF THIS NAME, and the difference costs a caller nine red tests if it is missed. Bash `askid_as` was `as_peer "$1" askid "$@"`, and `"$@"` still carried its own first argument, so the prefix was both the identity and the `<from>` argument of the `--ask`.

        Here the first argument ONLY chooses the identity, so the faithful call repeats the prefix: `askid_as("cafe1234", "cafe1234", "deadbeef", text)`. Doubling is explicit rather than implied because a helper that silently supplies an argument posts nothing when a caller supplies it too, and an `allow` control then passes for the wrong reason.
        """
        out = self.cli_as(prefix, "--ask", *argv).out
        found = re.search(r"#([0-9a-f]{8})", out)
        return found.group(1) if found else ""

    def event(self, session_id: str | None = None) -> str:
        return json.dumps(
            {
                "session_id": session_id or self.sid,
                "cwd": str(self.proj),
                "transcript_path": str(self.transcript),
                "session_crons": json.loads(self.crons),
                "background_tasks": json.loads(self.bg),
            }
        )

    def stop_env(self, extra: dict | None = None) -> dict[str, str]:
        env = dict(self.env)
        env["CLAUDE_PROJECT_DIR"] = str(self.proj)
        env["WORKLIST_TASKS_DIR"] = str(self.base / "tasks")
        env["WORKLIST_JUDGE"] = self.judge_mode
        env["GITHUB_ACTIONS"] = self.gha
        env["WORKLIST_CADENCE"] = self.cadence
        if extra:
            env.update(extra)
        return env

    def run(self, extra_env: dict | None = None, event: str | None = None) -> Result:
        """Feed the hook a Stop event and return its raw verdict.

        CADENCE OFF BY DEFAULT, deliberately: the cadence stands the hook down for one turn after it demanded and the session answered, so any case shaped block, then a new say, then a block would see a pause instead of the second block. The dedicated cadence tests set it on explicitly.
        """
        return self.python([], stdin=event or self.event(), env=self.stop_env(extra_env))

    def run_as(self, prefix: str, extra_env: dict | None = None) -> Result:
        """Drive a Stop event as ANOTHER live session.

        Both the event's session_id and WORKLIST_SESSION_ID move together, exactly as they do for a real peer: the whole point of the per-session STATE.md rule is that two sessions on one branch get DIFFERENT verdicts.
        """
        sid = peer_id(prefix)
        extra = dict(extra_env or {})
        extra["WORKLIST_SESSION_ID"] = sid
        return self.python([], stdin=self.event(sid), env=self.stop_env(extra))

    def runj(self, extra_env: dict | None = None) -> Result:
        """Like `run` but with the shim `claude` on PATH and the judge ON."""
        extra = dict(extra_env or {})
        extra["PATH"] = "%s:%s" % (self.base / "binonly", self.env.get("PATH", ""))
        extra["WORKLIST_JUDGE"] = "on"
        return self.python([], stdin=self.event(), env=self.stop_env(extra))

    def post_compact(self, extra_env: dict | None = None) -> Result:
        payload = json.dumps({"session_id": self.sid, "cwd": str(self.proj)})
        env = dict(self.env)
        env["CLAUDE_PROJECT_DIR"] = str(self.proj)
        if extra_env:
            env.update(extra_env)
        return self.python(["--post-compact"], stdin=payload, env=env)

    def check(
        self, want: str, needle: str, label: str = "", result: Result | None = None
    ) -> Result:
        """`check <label> <expect-decision> <must-contain>` from the bash harness."""
        got = result if result is not None else self.run()
        if got.decision != want or needle not in got.out:
            raise AssertionError(self.why(label, want, got, needle))
        return got

    def check_as(self, prefix: str, want: str, needle: str, label: str = "") -> Result:
        return self.check(want, needle, label, result=self.run_as(prefix))

    def checkj(self, want: str, needle: str, label: str = "") -> Result:
        return self.check(want, needle, label, result=self.runj())

    def check_absent(
        self, want: str, needle: str, label: str = "", result: Result | None = None
    ) -> Result:
        got = result if result is not None else self.run()
        if got.decision != want or needle in got.out:
            raise AssertionError(self.why(label, want, got, needle))
        return got

    def check_quiet(self, needle: str, label: str = "", result: Result | None = None) -> Result:
        """DECISION-AGNOSTIC absence, which still refuses to pass on SILENCE.

        An empty stdout means the hook died before deciding, and a needle is trivially absent from nothing, which is the vacuity this suite exists to catch.
        """
        got = result if result is not None else self.run()
        if not got.out.strip():
            raise AssertionError(
                "%s: the needle %r is absent, but the hook produced NO output at all. err: %s"
                % (label or "check_quiet", needle, got.err[:200])
            )
        if needle in got.out:
            raise AssertionError(self.why(label, got.decision, got, needle))
        return got

    def why(self, label: str, want: str, got: Result, needle: str) -> str:
        return "%s (want=%s got=%s, needle %r %s)\n  out: %s\n  err: %s" % (
            label or "check",
            want,
            got.decision,
            needle,
            "present" if needle in got.out else "MISSING",
            got.out[:400],
            got.err[:300],
        )


@pytest.fixture
def wl(tmp_path):
    """One sandbox per test, torn down with `tmp_path`."""
    fixture = Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture
