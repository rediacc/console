"""wl_bgsweep: a notify-only sweep for orphan background shells this session's own harness left behind.

WHY THIS EXISTS. The operator: "too many background shells in the background" accumulating over a very long session. Verified live on this machine: this session's own harness process had 10 leftover `bash -B -c source .../shell-snapshots/...` processes still alive as direct descendants, aged from 61.6 to 202.9 minutes, none of them killed. `wl_liveness.py` only ages tasks the harness's own event payload (`live_bg`) currently lists, or the output-file mtime for those same declared tasks.
Nothing walks the OS process tree independently to ask "is there a live shell under this session that nothing is currently bookkeeping?" That is the gap this module closes: a pure safety-net sweep, notify-only, that cannot be tricked (or trick itself) into looking at a different session's processes.

WHY A SEPARATE MODULE, not folded into `wl_liveness.py`. That module's own docstring frames its job as checking a claim the harness ITSELF already makes ("the event payload is authoritative for EXISTENCE"). This sweep is the opposite shape: an unconditional, bookkeeping-agnostic walk of every OS descendant, whether or not anything currently declares it. Folding the two together would blur that boundary. Mirrors the `wl_deflect.py`/`wl_admit.py` precedent of a small, testable sibling module.

THE ANCHOR IS A SINGLE PID, NOT `wl_liveness.harness_ancestors()`'s MULTI-HOP SET, and this is the one deliberate departure from a naive reading of the ask. That function's 8-hop walk reaches the terminal shell, the session leader, and eventually `init` -- nodes that CAN be legitimately shared with a sibling Claude session launched from the same terminal. Descending from the whole ancestor set would then pull in a sibling's entire subtree. Descending from only the harness's own single pid cannot: a process has exactly one parent, so two distinct `claude`-comm harness processes are structurally guaranteed to be in disjoint subtrees (subagents run in-process; background tasks spawn shells, not new harness processes). Verified live: 4 distinct `comm=claude` processes on the machine this was designed on shared no ancestor below `pid 2`.

ANCHOR RESOLUTION IS CROSS-VALIDATED, NEVER TRUSTED BLIND. `CLAUDE_PID` is harness-reported and not referenced anywhere else in this repo, so it is used only after agreeing with an independent comm-walk from this hook's own pid. Disagreement, or either one failing to resolve, refuses (reports nothing for that stop) rather than guessing -- an unresolved anchor is exactly the situation where a wrong guess could reach outside this session.

THE THRESHOLD IS A NEW, DISTINCT CONSTANT (`WORKLIST_BGSWEEP_AGE_MIN`, default 20), never a rename or reuse of `wl_liveness.BG_STALE_MIN` (15). They measure different things: `BG_STALE_MIN` is quiescence (has a DECLARED task stopped writing output, which can fire on a 2-minute-old process with no stdout yet or stay silent on an hours-old process streaming continuously); this constant is raw wall age since process start, independent of output activity and independent of whether the harness still declares the task at all.

DECLARED IS NOT THE SAME AS NEEDED (2026-10-24). The paragraph above once read "independent of whether the harness still declares the task at all", and since `bookkept()` (2026-09-24) that was false: a shell whose stdout is a declared task's `tasks/<id>.output` was dropped before the age test, so a declared shell could never be reported, however old or pointless. The operator's shell list showed 15 "running" shells; 12 were `until [ -s .../tasks/<id>.output ]; do sleep 15; done` waiters a sub-agent armed once per wake and never killed (ten of them polled the same 0-byte file, ages 3 min to 2h20m), and one was a finished writer's `node stub.mjs`. Every one was declared, so the sweep saw nothing.
`findings()` now reports three DECLARED shapes beside the undeclared orphan, each judged by command shape, never by declaration:

  wait-loop       a PURE wait loop (`until|while <probe>; do sleep N; done`, followed by nothing but reporting commands such as `cat`) at least BGSWEEP_AGE_MIN old. A loop does no work; the harness already notifies on task completion.
  duplicate-wait  a younger wait loop whose probe another, newer wait loop repeats: one waiter per target is enough.
  finished-agent  a shell a sub-agent launched (`"backgroundTaskId":"<id>"` in its transcript, the link `wl_roster.shell_waiters` reads) while that agent is not running, its transcript proves the turn ended, and it has been quiet BGSWEEP_AGE_MIN.

EXEMPT BY COMMAND SHAPE (`LONG_WORK`): the session's wake timer (`wl_wake.py`, split out of the declared set by the hook, so it used to be reported as an orphan once 20 minutes old), `ci-trace --wait`, `wl_prreview --wait`, `wl_wait.py`, renders and test runs. None of those is a shell loop, so they never classify as a wait loop; the list keeps them out of `finished-agent`, and the wake timer out of every kind.

NOTIFICATION, NOT ACTION. No code here calls `os.kill`/`terminate()` against a discovered process. `worklist.py --reap` is the existing "retire a roster entry" verb and it only ever mutates bookkeeping; a future, separate `--reap-pid` verb is where a kill step would plug in, requiring an explicit operator invocation and a fresh re-resolution of the anchor at the moment of the kill (a TOCTOU guard, since the pid could have been reaped and reused between notify and act).
"""

import os
import re
import time
from typing import Any, NamedTuple

import wl_common
import wl_liveness
import wl_wake

#: Raw wall age since process start, independent of BG_STALE_MIN's output-quiescence question -- see this module's own docstring for why the two are not merged.
BGSWEEP_AGE_MIN = int(os.environ.get("WORKLIST_BGSWEEP_AGE_MIN", "20"))


def _read_comm(pid):
    """The bare comm string for `pid`, or "" on any failure. Never raises."""
    try:
        with open("/proc/%d/comm" % pid, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def _clk_tck():
    try:
        return os.sysconf("SC_CLK_TCK")
    except (ValueError, OSError, AttributeError):
        return 100


def _proc_table_with_age_linux(uptime_s):
    """[(pid, ppid, cmdline, age_seconds_or_None)] -- the Linux path, one extra `/proc/<pid>/stat` field (starttime, field 22) beyond what `wl_liveness._proc_table_linux` reads, plus `/proc/uptime`.

    `st_mtime` is never used for age: it is not process start time. `uptime_s` is a parameter, not read internally, so the real end-to-end smoke test can inject an artificially large value and prove the age arithmetic on a REAL short-lived child without an actual 20-minute wait.
    """
    clk = _clk_tck()
    out: list[Any] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return out
    for name in entries:
        if not name.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % name, "rb") as f:
                stat = f.read().decode("utf-8", "replace")
            after = stat.rsplit(")", 1)[-1].split()
            ppid = int(after[1])
            starttime_ticks = int(after[19])
            with open("/proc/%s/cmdline" % name, "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
        except (OSError, ValueError, IndexError):
            continue
        age = (uptime_s - starttime_ticks / clk) if uptime_s is not None else None
        out.append((int(name), ppid, cmd, age))
    return out


def _proc_table_with_age_ps():
    """[(pid, ppid, cmdline, age_seconds_or_None)] -- the no-/proc fallback (macOS), `etimes=` added to `wl_liveness._proc_table_ps`'s own invocation so age arrives with no uptime arithmetic needed on this path.

    A row whose `etimes` field fails to parse degrades to age=None ("OS-visible, age unknown"), never a crash and never a guessed zero -- older BSD `ps` builds report `etime=` as a `[[dd-]hh:]mm:ss` string instead, which this deliberately does not attempt to parse.
    """
    r = wl_common.run_quiet(["ps", "-axo", "pid=,ppid=,etimes=,args="])
    if r is None or r.returncode != 0:
        return []
    out = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        age = int(parts[2]) if parts[2].isdigit() else None
        cmd = parts[3] if len(parts) > 3 else ""
        out.append((int(parts[0]), int(parts[1]), cmd, age))
    return out


def proc_table_with_age(uptime_s=None):
    """[(pid, ppid, cmdline, age_seconds_or_None)] for every readable process, Linux or the `ps` fallback."""
    if os.path.isdir("/proc"):
        if uptime_s is None:
            try:
                with open("/proc/uptime", encoding="utf-8") as f:
                    uptime_s = float(f.read().split()[0])
            except (OSError, ValueError, IndexError):
                uptime_s = None
        return _proc_table_with_age_linux(uptime_s)
    return _proc_table_with_age_ps()


def resolve_anchor(table=None):
    """The single pid this sweep may descend from, or None (refuse) -- never a guess.

    `WORKLIST_HARNESS_PID` overrides for tests, matching `wl_liveness.harness_ancestors`'s own convention. Otherwise `CLAUDE_PID` (harness-reported) must AGREE with an independent comm-walk from this hook's own pid before either is trusted; disagreement or either one failing to resolve refuses.
    """
    override = os.environ.get("WORKLIST_HARNESS_PID", "")
    if override.isdigit():
        return int(override)
    if table is None:
        table = wl_liveness.proc_table()
    if not table:
        return None
    parents = {pid: ppid for pid, ppid, _cmd in table}
    claude_pid_env = os.environ.get("CLAUDE_PID", "")
    env_pid = int(claude_pid_env) if claude_pid_env.isdigit() else None
    walk_pid = None
    cur: int | None = os.getpid()
    for _ in range(8):
        cur = parents.get(cur)
        if not cur or cur <= 1:
            break
        if _read_comm(cur) == "claude":
            walk_pid = cur
            break
    if env_pid is not None and walk_pid is not None and env_pid == walk_pid:
        return env_pid
    return None


def descendants(anchor_pid, table_with_age):
    """[(pid, ppid, cmdline, age)] for every transitive descendant of `anchor_pid`, BFS over the ppid->children map. `anchor_pid` itself is never included."""
    children: dict[Any, Any] = {}
    for pid, ppid, cmdline, age in table_with_age:
        children.setdefault(ppid, []).append((pid, ppid, cmdline, age))
    out, seen, queue = [], {anchor_pid}, [anchor_pid]
    while queue:
        cur = queue.pop()
        for row in children.get(cur, ()):
            pid = row[0]
            if pid in seen:
                continue
            seen.add(pid)
            out.append(row)
            queue.append(pid)
    return out


_TASK_OUTPUT = re.compile(r"/tasks/([A-Za-z0-9_-]+)\.output$")


def _stdout_task(pid):
    """The background task id whose `tasks/<id>.output` this pid writes to (fd 1 or 2), or None."""
    for fd in (1, 2):
        try:
            target = os.readlink("/proc/%d/fd/%d" % (pid, fd))
        except OSError:
            continue
        m = _TASK_OUTPUT.search(target)
        if m:
            return m.group(1)
    return None


def bookkept(rows, live_ids, stdout_task=_stdout_task):
    """The pids that belong to a task the harness lists as running: a process whose stdout (or an ancestor's, within `rows`) is that task's `tasks/<id>.output`.

    2026-09-24: the sweep reported 21 "orphans" that were the process trees of two LISTED tasks (an M-live run's `devbox exec -> run-legacy.sh -> docker exec` chain and a writer's `pytest -n 8`), and blocked every stop on them.
    """
    if not live_ids:
        return set()
    parent = {pid: ppid for pid, ppid, _c, _a in rows}
    owned: dict[Any, bool] = {}

    def is_owned(pid, depth=0):
        if pid in owned:
            return owned[pid]
        task = stdout_task(pid)
        if task is not None:
            owned[pid] = task in live_ids
            if owned[pid]:
                return True
        up = parent.get(pid)
        owned[pid] = bool(
            up is not None and up in parent and depth < 64 and is_owned(up, depth + 1)
        )
        return owned[pid]

    return {pid for pid, _pp, _c, _a in rows if is_owned(pid)}


ORPHAN, WAIT_LOOP, DUPLICATE_WAIT, FINISHED_AGENT = (
    "orphan",
    "wait-loop",
    "duplicate-wait",
    "finished-agent",
)


class Finding(NamedTuple):
    pid: int
    pgid: int | None
    age_min: float | None
    cmd: str  # the command as typed (the harness wrapper peeled off)
    kind: str  # ORPHAN, WAIT_LOOP, DUPLICATE_WAIT or FINISHED_AGENT
    target: str  # the polled probe for the two wait kinds, the owning agent id for FINISHED_AGENT
    note: str  # the target file's state, or the agent's quiet time; "" when nothing is known


# Legitimately long work, by command shape. Each entry names its exemption; see the module docstring. A tool name counts only as a WORD (`_W`): never inside a path or a file name, so `until [ -s /tmp/ms-render-ar.log ]` or a probe under `/tmp/pytest-of-<user>/` stays a poll (the first draft matched both).
_W = r"(?<![\w/.-])%s(?![\w-])"
LONG_WORK = (
    ("wake timer", wl_wake.WAKER_RE),
    ("ci-trace --wait", re.compile(r"\bci-trace(?:\.py)?\b.*\s--wait\b")),
    ("wl_prreview --wait", re.compile(r"\bwl_prreview(?:\.py)?\b.*\s--wait\b")),
    ("wl_wait", re.compile(r"\bwl_wait\.py\b")),
    (
        "render",
        re.compile(
            "|".join(_W % w for w in ("render", "remotion", "ffmpeg")) + r"|\btutorials\s+video\b"
        ),
    ),
    (
        "test run",
        re.compile(
            "|".join(_W % w for w in ("pytest", "vitest", "playwright", r"vm:check"))
            + r"|\bnpm\s+(?:run\s+)?test\b|\bnpm\s+run\s+ci\b|\bgo\s+test\b"
        ),
    ),
)


def long_work(cmd):
    """The name of the LONG_WORK exemption `cmd` matches, or ""."""
    for name, rx in LONG_WORK:
        if rx.search(cmd or ""):
            return name
    return ""


_EVAL = re.compile(r"\beval '")
_EVAL_END = "' < /dev/null"


def inner_command(cmdline):
    """The command as typed: the payload of the harness's `... && eval '<cmd>' < /dev/null && pwd -P ...` wrapper, its quoting undone; the cmdline itself when there is no wrapper."""
    m = _EVAL.search(cmdline or "")
    if not m:
        return (cmdline or "").strip()
    end = cmdline.rfind(_EVAL_END)
    if end <= m.end():
        return cmdline[m.end() :].strip()
    return cmdline[m.end() : end].replace("'\"'\"'", "'").replace("'\\''", "'").strip()


_LOOP = re.compile(
    r"^(?:cd\s+\S+\s*(?:&&|;)\s*)*(?:until|while)\s+(?P<cond>.+?)\s*(?:;|\n)\s*do\b(?P<body>.*?)"
    r"(?:;|\n)\s*done\b(?P<tail>.*)$",
    re.DOTALL,
)
_SPLIT = re.compile(r"\s*(?:;|&&|\|\||\n)\s*")
_BODY_OK = re.compile(
    r"^(?:sleep\s+\S+|:|true|break|fi|else|if\s+.+|then(?:\s+(?:break|:|true|exit\b.*))?"
    r"|echo\b[^>]*|printf\b[^>]*|\[\[?\s.*|test\s.*|)$",
    re.DOTALL,
)
_TAIL_OK = re.compile(
    r"^(?:cat|tail|head|echo|printf|ls|wc|grep|jq|true|date|stat|du|:|exit)\b.*$|^$", re.DOTALL
)
_PATH = re.compile(r"(/[^\s'\"\]\)]+)")


def wait_target(cmd):
    """The normalised probe of a PURE wait loop, or "" when `cmd` is anything else.

    Pure: the command is one `until|while` loop (an optional leading `cd`), its body only sleeps and tests, and what follows `done` only reports (`cat`, `tail`, `echo`, ...). A loop that gates real work after it, or does work inside it, is not pure; a loop whose probe is LONG_WORK is a retry around real work, not a poll.
    """
    m = _LOOP.match((cmd or "").strip())
    if not m:
        return ""
    cond, body, tail = m.group("cond"), m.group("body"), m.group("tail").strip()
    if long_work(cond):
        return ""
    stmts = [x for x in _SPLIT.split(body.strip()) if x]
    if not any(x.startswith("sleep") for x in stmts) or not all(_BODY_OK.match(x) for x in stmts):
        return ""
    if tail:
        if not re.match(r"^(?:;|&&|\|\||\n)", tail):
            return ""
        if not all(_TAIL_OK.match(x) for x in _SPLIT.split(tail) if x):
            return ""
    return re.sub(r"\s+", " ", cond).strip()


def _target_note(target, now=None):
    """`<path>: N bytes, unchanged M min` for the first absolute path in the probe, or ""."""
    m = _PATH.search(target or "")
    if not m:
        return ""
    try:
        st = os.stat(m.group(1))
    except OSError:
        return "%s: absent" % m.group(1)
    now = time.time() if now is None else now
    return "%s: %d bytes, unchanged %d min" % (
        m.group(1),
        st.st_size,
        max(0, int((now - st.st_mtime) / 60)),
    )


def _pgid(pid):
    """The process group of `pid`, or None. Never raises."""
    try:
        with open("/proc/%d/stat" % pid, "rb") as f:
            return int(f.read().decode("utf-8", "replace").rsplit(")", 1)[-1].split()[2])
    except (OSError, ValueError, IndexError):
        try:
            return os.getpgid(pid)
        except (OSError, AttributeError):
            return None


def kill_command(f):
    """The exact command that ends finding `f`: the whole group when the row leads its own group (a harness task is started with setsid, so the group is the task and nothing else), else the pid."""
    if f.pgid is not None and f.pgid == f.pid:
        return "kill -- -%d" % f.pid
    return "kill %d" % f.pid


def describe(f):
    """One phrase naming why finding `f` is reported."""
    if f.kind == WAIT_LOOP:
        why = "pure wait loop past %d min, polling %s" % (BGSWEEP_AGE_MIN, f.target)
    elif f.kind == DUPLICATE_WAIT:
        why = "duplicate wait loop: a newer one polls the same %s" % f.target
    elif f.kind == FINISHED_AGENT:
        why = "launched by sub-agent %s, which has finished" % f.target
    else:
        why = "undeclared: no running task owns it"
    return "%s (%s)" % (why, f.note) if f.note else why


def findings(
    table_with_age=None,
    anchor_table=None,
    live_ids=None,
    stdout_task=_stdout_task,
    owners=None,
    pgid_of=_pgid,
    target_note=_target_note,
):
    """[Finding] for this session's harness: undeclared orphans, and the declared shapes no declaration excuses (module docstring). [] when the anchor cannot be resolved.

    `owners` is a callable `owners({task id: age seconds}) -> ({task id: agent id}, {finished agent ids}, {agent id: quiet minutes})`, `owner_context` bound to the event in the hook. It is called only when a declared, non-loop, non-LONG_WORK task is old enough to matter, so a quiet stop reads no transcript. A row with age=None (unreadable start time) is an orphan "age unknown" when undeclared, never treated as 0 or as infinite; the declared kinds need a known age.
    """
    if table_with_age is None:
        table_with_age = proc_table_with_age()
    if not table_with_age:
        return []
    anchor_source = (
        anchor_table
        if anchor_table is not None
        else [(p, pp, c) for p, pp, c, _a in table_with_age]
    )
    anchor = resolve_anchor(anchor_source)
    if anchor is None:
        return []
    limit = BGSWEEP_AGE_MIN * 60
    rows = descendants(anchor, table_with_age)
    owned = bookkept(rows, set(live_ids or ()), stdout_task)
    out: list[Finding] = []

    def emit(pid, age, cmdline, kind, target="", note=""):
        out.append(
            Finding(
                pid,
                pgid_of(pid),
                (age / 60.0) if age is not None else None,
                inner_command(cmdline),
                kind,
                target,
                note,
            )
        )

    # UNDECLARED: every unowned row old enough, collapsed to the top of each flagged subtree (one kill ends the rest). The wake timer is split out of the declared set by the hook itself, so it is excused here by shape.
    # LONG_WORK is excused here as well, with its whole subtree: an undeclared `ci-trace --wait` or render is a long run by shape, and its `sleep` child must not be reported on its own.
    exempt = {
        pid
        for pid, _pp, cmd, _age in rows
        if wl_wake.WAKER_RE.search(cmd) or long_work(inner_command(cmd))
    }
    grew = True
    while grew:
        grew = False
        for pid, ppid, _cmd, _age in rows:
            if ppid in exempt and pid not in exempt:
                exempt.add(pid)
                grew = True
    flagged = {
        pid
        for pid, _pp, _cmd, age in rows
        if pid not in owned and (age is None or age >= limit) and pid not in exempt
    }
    for pid, ppid, cmd, age in rows:
        if pid in flagged and ppid not in flagged:
            emit(pid, age, cmd, ORPHAN)
    # DECLARED: one candidate per harness task, the topmost row writing that task's output (its parent writes elsewhere). Not "the anchor's direct child": a wrapper on PATH (a `bash` shim) can put a layer between, and the task is still the row that owns the output.
    live = set(live_ids or ())
    task_of = {pid: stdout_task(pid) for pid, _pp, _c, _a in rows if pid in owned}
    tops = [r for r in rows if task_of.get(r[0]) in live and task_of.get(r[1]) != task_of.get(r[0])]
    waits = []
    candidates = []
    for pid, _pp, cmdline, age in tops:
        cmd = inner_command(cmdline)
        if wl_wake.WAKER_RE.search(cmd):
            continue
        target = wait_target(cmd)
        if target:
            waits.append((pid, age, cmdline, target))
            continue
        task = task_of.get(pid)
        if task and age is not None and age >= limit and not long_work(cmd):
            candidates.append((pid, age, cmdline, task))
    if candidates and owners is not None:
        try:
            owner_of, finished, quiet = owners({t: a for _p, a, _c, t in candidates})
        except Exception:
            owner_of, finished, quiet = {}, set(), {}
        for pid, age, cmdline, task in candidates:
            agent = (owner_of or {}).get(task)
            if agent and agent in (finished or ()):
                q = (quiet or {}).get(agent)
                emit(
                    pid,
                    age,
                    cmdline,
                    FINISHED_AGENT,
                    agent,
                    ("agent quiet %d min" % q) if q is not None else "",
                )
    newest: dict[str, float] = {}
    for _pid, age, _c, target in waits:
        if age is not None and (target not in newest or age < newest[target]):
            newest[target] = age
    for pid, age, cmdline, target in waits:
        if age is not None and age >= limit:
            emit(pid, age, cmdline, WAIT_LOOP, target, target_note(target))
        elif age is not None and newest.get(target, age) < age:
            emit(pid, age, cmdline, DUPLICATE_WAIT, target, target_note(target))
    return out


def sweep(table_with_age=None, anchor_table=None, live_ids=None, stdout_task=_stdout_task):
    """[(pid, age_min_or_None, cmdline)] -- the undeclared orphans alone, the shape this module first shipped with. `findings()` is the full report."""
    return [
        (f.pid, f.age_min, f.cmd)
        for f in findings(
            table_with_age, anchor_table, live_ids, stdout_task, pgid_of=lambda _p: None
        )
        if f.kind == ORPHAN
    ]


def owner_context(event, cwd, session_id, task_ages, now=None):
    """({task id: agent id}, {finished agent ids}, {agent id: quiet minutes}) for the shells in `task_ages` ({task id: age seconds}). Never raises; any failure is ({}, set(), {}).

    The link is the `"backgroundTaskId":"<id>"` an agent's transcript records when it launches a shell (wl_roster.shell_waiters reads the same). Only transcripts written since the oldest of these shells could have started are read. FINISHED: the event does not list the agent as running, `wl_roster.proven_finished` holds, and the transcript has been quiet BGSWEEP_AGE_MIN.
    """
    try:
        import wl_roster as R

        task_ids = {str(t) for t in task_ages or () if t}
        if not task_ids:
            return {}, set(), {}
        now = time.time() if now is None else now
        metas = R.load_metas(R.session_subagents_dir(cwd, session_id))
        running = {
            str(b.get("id") or "")
            for b in (event.get("background_tasks") or [])
            if isinstance(b, dict) and b.get("type") == "subagent" and b.get("status") == "running"
        }
        # A transcript last written before the oldest shell started cannot have launched it.
        since = now - max(float(a or 0) for a in task_ages.values()) - 60
        owners: dict[str, str] = {}
        finished: set[str] = set()
        quiet: dict[str, int] = {}
        for aid, m in metas.items():
            jsonl = m.get("jsonl")
            try:
                mtime = jsonl.stat().st_mtime
            except (OSError, AttributeError):
                continue
            if mtime < since:
                continue
            try:
                data = jsonl.read_bytes()
            except OSError:
                continue
            hit = False
            for mm in re.finditer(rb'"backgroundTaskId":"([A-Za-z0-9_-]+)"', data):
                sid = mm.group(1).decode()
                if sid in task_ids:
                    owners[sid] = aid
                    hit = True
            if not hit:
                continue
            quiet[aid] = int((now - mtime) / 60)
            if (
                aid not in running
                and now - mtime >= BGSWEEP_AGE_MIN * 60
                and R.proven_finished(jsonl, now, m.get("name", ""), cwd, session_id)
            ):
                finished.add(aid)
        return owners, finished, quiet
    except Exception:
        return {}, set(), {}
