"""Differential: `.ci/rediacc_ci/private/compose_healthcheck_smoke_test.py`
against its twin `.ci/scripts/private/compose-healthcheck-smoke-test.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new
code is correct", it is "the new code says what the old code said". Only running
BOTH, on the same fixture, in the same run, can support that.

NOTHING REAL IS EVER INVOKED, AND THE NEAR-MISS THAT PROVES IT MATTERS. The twin
registers a worker VM with the `rdc` CLI, provisions renet on it, creates a
2 GB repo, applies a template, brings it up and then polls a Docker healthcheck
over ssh. On this machine `rdc` IS on PATH: `/home/developer/.local/bin/rdc` is
a symlink to the repository's own `rdc.sh`, and during exploratory work a
PREPENDED scratch PATH let one probe fall through to it, which ran
`npm install` and `npm rebuild` inside the live checkout before failing. That is
why PATH here is REPLACED AND NEVER PREPENDED, why the real name is asserted
unreachable on every scratch PATH, and why `_binder` treats a probe it cannot
prove absent as a harness failure rather than a passing case.

ALL FIVE EXTERNALS ARE RECORDING FAKES: `rdc`, `ssh`, `date`, `sleep`, `whoami`.
Each appends its full argv to a shared JSONL log and returns canned bytes and a
canned status.

THE CLOCK AND THE SLEEP ARE FAKES FOR A SECOND REASON, not just isolation. The
twin's window is `TIMEOUT_SECS` seconds of real time with a real `sleep 5`
between probes; a differential that honoured that would take minutes per case
and would be switched off. `date` here is a STEPPED COUNTER driven from a
fixture list, so "the healthcheck converged on the third probe" and "the window
closed with the container still starting" are both exact, instant and
reproducible.

WHAT IS COMPARED, AND WHY THE CALL LOG IS THE MOST IMPORTANT OF THE FOUR. Every
case compares exit code, stdout, stderr AND the recorded argv of every external.
Almost everything this script does is a side effect on a remote machine, and
none of it appears on any stream: the four REMOTE PROGRAMS are multi-line shell
sent as ONE ssh argument each, and a port that reflowed the indentation, dropped
a `2>/dev/null`, or word-split `sudo ss -tlnp 'sport = :5432' 2>&1` into three
arguments would produce byte-identical output and talk to the VM differently.
`test_the_four_remote_programs_survive_as_single_arguments` compares them
character for character.

THE ONE MASK. Bash prefixes its own diagnostics with `<$0>: line <n>: `, naming
the file it is running; the port composes the same prefix from `sys.argv[0]` and
its own live frame. Those can never be equal, so `_mask` collapses exactly that
prefix on both sides, and `test_the_mask_does_not_hide_the_message` pins that it
collapses nothing else.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "private" / "compose-healthcheck-smoke-test.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "private" / "compose_healthcheck_smoke_test.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/private/compose-healthcheck-smoke-test.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/private/compose_healthcheck_smoke_test.py")

# `rdc`, `sleep` and `whoami`: log the argv, write canned bytes to both streams, exit with a status looked up by SUBCOMMAND PREFIX. Keyed on the prefix rather than the tool name because `rdc` is invoked eight times per healthy run with eight different subcommands, and "the run fails at `repo up`" is a different
# case from "the run fails at `machine setup`".
FAKE_TOOL = """#!/usr/bin/env python3
import json, os, pathlib, sys
LOG = %(log)r
NAME = %(name)r
RC = %(rc)r
OUT = %(out)r
ERR = %(err)r
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write(json.dumps([NAME, *sys.argv[1:]]) + "\\n")
joined = " ".join(sys.argv[1:])
if OUT:
    sys.stdout.write(OUT %% {"name": NAME, "joined": joined})
    sys.stdout.flush()
if ERR:
    sys.stderr.write(ERR %% {"name": NAME, "joined": joined})
    sys.stderr.flush()
for prefix, code in sorted(RC.items(), key=lambda kv: -len(kv[0])):
    if joined.startswith(prefix):
        sys.exit(code)
sys.exit(0)
"""

# `date`: a STEPPED CLOCK, not a real one. Each invocation consumes the next entry of `TICKS` (the last entry repeats forever), so a case states its timeline as data. Its status comes from the same list, which is how "the clock itself failed" is driven.
FAKE_DATE = """#!/usr/bin/env python3
import json, os, pathlib, sys
LOG = %(log)r
TICKS = %(ticks)r
STATE = %(state)r
st = pathlib.Path(STATE)
n = int(st.read_text()) if st.exists() else 0
st.write_text(str(n + 1))
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(["date", *sys.argv[1:]]) + "\\n")
text, rc = TICKS[min(n, len(TICKS) - 1)]
if text is not None:
    sys.stdout.write(text + "\\n")
    sys.stdout.flush()
sys.exit(rc)
"""

# `ssh`: the only fake that reads its input. It classifies the remote program by a marker unique to each of the four, then answers from a per-kind script whose entries are consumed in order with the last repeating. That is what lets one
# case say "starting, starting, healthy" and another say "starting forever".
#
# THE CLASSIFIER IS DELIBERATELY STRICT: an unrecognised remote program is a loud failure rather than a default reply, because the four differ by a few characters and a port that sent the diagnostic dump where the poll belongs would otherwise be answered politely and look equivalent.
FAKE_SSH = """#!/usr/bin/env python3
import json, os, pathlib, sys
LOG = %(log)r
REPLIES = %(replies)r
STATE = %(state)r
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(["ssh", *sys.argv[1:]]) + "\\n")
command = sys.argv[-1]
if "name=^app$" in command:
    kind = "app"
elif "ss -tlnp" in command:
    kind = "ss"
elif "=== $sock ===" in command:
    kind = "diag"
elif "name=^db$" in command:
    kind = "poll"
else:
    sys.stderr.write("FAKE SSH: unrecognised remote program\\n")
    sys.exit(97)
st = pathlib.Path(STATE + "." + kind)
n = int(st.read_text()) if st.exists() else 0
st.write_text(str(n + 1))
script = REPLIES[kind]
out, err, rc = script[min(n, len(script) - 1)]
if out:
    sys.stdout.write(out)
    sys.stdout.flush()
if err:
    sys.stderr.write(err)
    sys.stderr.flush()
sys.exit(rc)
"""

# The five externals both subjects may reach.
TOOLS = ("rdc", "ssh", "date", "sleep", "whoami")

# Everything both subjects need once PATH is rebuilt from scratch, minus the five above. Named rather than derived: a PATH built by copying "everything
# except rdc" is a PATH nobody can state, and the first tool it forgot would
# look like a divergence in the subject rather than a hole in the harness.
NEEDED = ("bash", "sh", "python3", "uname", "dirname", "cat", "grep", "sed", "rm", "env", "ls")

# The default timeline: the deadline is computed at t=1000 and the clock then
# advances 20 seconds per read, so a 120-second window admits 5 probes.
DEFAULT_TICKS = tuple((str(1000 + i * 20), 0) for i in range(40))

# The default replies. `db` converges on the third probe; `app` is running.
HEALTHY_REPLIES = {
    "poll": [("starting|0\n", "", 0), ("starting|1\n", "", 0), ("healthy|0\n", "", 0)],
    "app": [("running\n", "", 0)],
    "diag": [("=== /var/run/rediacc/docker-7.sock ===\nState=running Health=starting/1\n", "", 0)],
    "ss": [("LISTEN 0 244 127.0.0.1:5432 0.0.0.0:*\n", "", 0)],
}

SHELL_PREFIX = re.compile(r"^[^\n]*?: line \d+: ", re.MULTILINE)


def _replies(**overrides):
    """The default reply table with one or more kinds replaced."""
    table = {kind: list(script) for kind, script in HEALTHY_REPLIES.items()}
    table.update(overrides)
    return table


def _mask(text: str, root: pathlib.Path, tmp: pathlib.Path) -> str:
    text = SHELL_PREFIX.sub("<shell>: ", text)
    return text.replace(str(root), "<root>").replace(str(tmp), "<tmp>")


def _fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because the twin sources `../lib/common.sh` relative to its own
    `BASH_SOURCE`, and because both subjects put their own path into every bash
    diagnostic they emit. Driving the tracked files directly would name the real
    checkout in output the differential then has to mask more aggressively.
    """
    root = tmp_path.resolve() / "tree"
    (root / ".ci" / "scripts" / "private").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "rediacc_ci" / "private").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)
    return root


def _binder(
    tmp_path: pathlib.Path,
    *,
    absent: tuple[str, ...] = (),
    rc: dict[str, dict[str, int]] | None = None,
    ticks=DEFAULT_TICKS,
    replies=None,
    stdout: dict[str, str] | None = None,
    stderr: dict[str, str] | None = None,
) -> str:
    """The COMPLETE PATH for one case: named real tools, plus the five fakes.

    `absent` names fakes to LEAVE OUT, which is how every `command not found`
    arm is driven. EACH EXCLUSION IS ASSERTED, because a probe that cannot fire
    is indistinguishable from a subject that cannot fail -- and because this
    machine has a real `rdc` that a leaky PATH would reach.
    """
    rc = rc or {}
    replies = replies if replies is not None else _replies()
    stdout = stdout or {}
    stderr = stderr or {}
    binder = tmp_path.resolve() / "bin"
    if binder.exists():
        shutil.rmtree(binder)
    binder.mkdir(parents=True)
    for tool in NEEDED:
        target = shutil.which(tool)
        if target is None:
            continue
        (binder / tool).symlink_to(target)

    log = str(tmp_path.resolve() / "calls.jsonl")
    state = str(tmp_path.resolve() / "tick")
    for name in TOOLS:
        if name in absent:
            continue
        fake = binder / name
        if name == "date":
            body = FAKE_DATE % {"log": log, "ticks": list(ticks), "state": state}
        elif name == "ssh":
            body = FAKE_SSH % {"log": log, "replies": replies, "state": state}
        else:
            body = FAKE_TOOL % {
                "log": log,
                "name": name,
                "rc": rc.get(name, {}),
                "out": stdout.get(name, ""),
                "err": stderr.get(name, ""),
            }
        fake.write_text(body, encoding="utf-8")
        fake.chmod(0o755)

    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
    for name in absent:
        assert shutil.which(name, path=str(binder)) is None, (
            "the probe cannot fire: %s is still reachable on the scratch PATH" % name
        )
    return str(binder)


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    tmp_path: pathlib.Path,
    binder: str,
    argv: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
    env_drop: tuple[str, ...] = (),
) -> dict[str, object]:
    """Drive one subject from a NEUTRAL cwd and collect all four observables.

    Output is captured as BYTES and decoded with `surrogateescape`, so a remote
    reply that is not valid UTF-8 survives the harness intact instead of raising
    inside it.
    """
    cwd = tmp_path.resolve() / "elsewhere"
    cwd.mkdir(exist_ok=True)
    env = {
        "PATH": binder,
        "HOME": str(tmp_path.resolve()),
        "USER": "labuser",
        "PYTHONDONTWRITEBYTECODE": "1",
        # The port imports `rediacc_ci.log`; the COPY under the fixture is what
        # runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    env.update(env_extra or {})
    for name in env_drop:
        env.pop(name, None)
    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject), *argv],
        capture_output=True,
        env=env,
        cwd=str(cwd),
        check=False,
        timeout=180,
    )
    log = tmp_path.resolve() / "calls.jsonl"
    calls: list[list[str]] = []
    if log.exists():
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
        log.unlink()
    for stale in tmp_path.resolve().glob("tick*"):
        stale.unlink()
    decode = lambda raw: raw.decode("utf-8", "surrogateescape")  # noqa: E731
    mask = lambda text: _mask(text, root, tmp_path.resolve())  # noqa: E731
    return {
        "exit": proc.returncode,
        "stdout": mask(decode(proc.stdout)),
        "stderr": mask(decode(proc.stderr)),
        "calls": [[mask(part) for part in call] for call in calls],
    }


CASES = [
    pytest.param({}, {}, id="the-db-converges-and-the-app-is-running"),
    pytest.param({}, {"argv": ("--anything", "extra")}, id="arguments-are-ignored-entirely"),
    pytest.param(
        {"replies": _replies(poll=[("healthy|0\n", "", 0)])},
        {},
        id="the-first-probe-is-already-healthy",
    ),
    # ---- the timeout arm, which is the whole reason the script exists -------
    pytest.param(
        {"replies": _replies(poll=[("starting|3\n", "", 0)])},
        {},
        id="the-window-closes-with-the-container-still-starting",
    ),
    pytest.param(
        {"replies": _replies(poll=[("unhealthy|9\n", "", 0)])},
        {},
        id="an-unhealthy-container-never-converges-either",
    ),
    pytest.param(
        {"replies": _replies(poll=[("missing|\n", "", 0)])},
        {},
        id="no-db-container-on-any-socket",
    ),
    pytest.param(
        {"replies": _replies(poll=[("", "ssh: connect: no route to host\n", 255)])},
        {},
        id="every-probe-fails-so-the-fallback-supplies-the-status",
    ),
    pytest.param(
        {"replies": _replies(poll=[("starting|1\n", "", 4)])},
        {},
        id="a-probe-that-prints-AND-fails-appends-the-fallback-to-its-output",
    ),
    pytest.param(
        {"replies": _replies(poll=[("healthy|0\n\n\n\n", "", 0)])},
        {},
        id="trailing-newlines-are-stripped-by-the-capture",
    ),
    pytest.param(
        {"replies": _replies(poll=[("healthy\n", "", 0)])},
        {},
        id="a-reply-with-no-pipe-makes-status-and-streak-the-same-string",
    ),
    pytest.param(
        {"replies": _replies(poll=[("healthy|0|extra\n", "", 0)])},
        {},
        id="only-the-first-pipe-splits-the-reply",
    ),
    pytest.param(
        {"replies": _replies(poll=[("", "", 0)])},
        {},
        id="an-empty-reply-is-an-empty-status",
    ),
    pytest.param(
        {"replies": _replies(poll=[("HEALTHY|0\n", "", 0)])},
        {},
        id="the-status-comparison-is-case-sensitive",
    ),
    pytest.param(
        {"replies": _replies(poll=[(" healthy|0\n", "", 0)])},
        {},
        id="a-leading-space-is-not-stripped-so-it-is-not-healthy",
    ),
    pytest.param(
        {"replies": _replies(poll=[("healthy|\udcff\udcfe\n", "", 0)])},
        {},
        id="a-reply-that-is-not-utf8-is-still-ruled-on",
    ),
    # ---- phase 3, the depends_on assertion ---------------------------------
    pytest.param(
        {"replies": _replies(poll=[("healthy|0\n", "", 0)], app=[("exited\n", "", 0)])},
        {},
        id="the-db-is-healthy-but-the-app-never-started",
    ),
    pytest.param(
        {"replies": _replies(poll=[("healthy|0\n", "", 0)], app=[("missing\n", "", 0)])},
        {},
        id="there-is-no-app-container-at-all",
    ),
    pytest.param(
        {"replies": _replies(poll=[("healthy|0\n", "", 0)], app=[("", "", 255)])},
        {},
        id="the-app-probe-cannot-connect",
    ),
    # ---- the diagnostic dump -----------------------------------------------
    pytest.param(
        {
            "replies": _replies(
                poll=[("starting|2\n", "", 0)],
                diag=[("dump line one\ndump line two\n", "docker: no such socket\n", 1)],
                ss=[("", "ss: cannot open netlink\n", 2)],
            )
        },
        {},
        id="both-diagnostic-probes-fail-and-neither-changes-the-verdict",
    ),
    pytest.param(
        {"absent": ("ssh",), "replies": _replies(poll=[("starting|0\n", "", 0)])},
        {},
        id="ssh-is-not-on-path-at-all",
    ),
    # ---- rdc failures, one per phase ---------------------------------------
    pytest.param({"rc": {"rdc": {"config ssh set": 3}}}, {}, id="rdc-config-ssh-set-fails"),
    pytest.param(
        {"rc": {"rdc": {"machine add": 11}}}, {}, id="rdc-machine-add-fails-and-only-warns"
    ),
    pytest.param({"rc": {"rdc": {"machine setup": 5}}}, {}, id="rdc-machine-setup-fails"),
    pytest.param({"rc": {"rdc": {"repo create": 6}}}, {}, id="rdc-repo-create-fails"),
    pytest.param({"rc": {"rdc": {"repo admin": 8}}}, {}, id="rdc-template-apply-fails"),
    pytest.param(
        {"rc": {"rdc": {"repo up": 7}}}, {}, id="rdc-repo-up-fails-and-the-status-survives"
    ),
    pytest.param(
        {"rc": {"rdc": {"repo down": 9, "repo delete": 9}}},
        {},
        id="a-failing-cleanup-cannot-fail-the-run",
    ),
    pytest.param({"absent": ("rdc",)}, {}, id="rdc-is-not-on-path-at-all"),
    pytest.param(
        {
            "stdout": {"rdc": "rdc said this on stdout: %(joined)s\n"},
            "stderr": {"rdc": "rdc said this on stderr: %(joined)s\n"},
        },
        {},
        id="only-the-config-ssh-set-stdout-is-discarded",
    ),
    # ---- the clock ---------------------------------------------------------
    pytest.param({}, {"env_extra": {"TIMEOUT_SECS": "0"}}, id="a-zero-window-never-probes-at-all"),
    pytest.param({}, {"env_extra": {"TIMEOUT_SECS": "40"}}, id="a-short-window-admits-one-probe"),
    pytest.param(
        {},
        {"env_extra": {"TIMEOUT_SECS": "060"}},
        id="a-zero-padded-window-is-read-as-OCTAL-which-is-the-defect",
    ),
    pytest.param(
        {},
        {"env_extra": {"TIMEOUT_SECS": "60"}},
        id="the-same-window-without-the-leading-zero-for-comparison",
    ),
    pytest.param(
        {}, {"env_extra": {"TIMEOUT_SECS": "0x50"}}, id="a-hex-window-is-accepted-as-arithmetic"
    ),
    pytest.param(
        {},
        {"env_extra": {"TIMEOUT_SECS": "  120  "}},
        id="whitespace-around-the-window-is-arithmetic-whitespace",
    ),
    pytest.param(
        {},
        {"env_extra": {"TIMEOUT_SECS": "abc"}},
        id="an-unset-identifier-window-is-a-fatal-set-u-violation",
    ),
    pytest.param(
        {},
        {"env_extra": {"TIMEOUT_SECS": "12abc"}},
        id="an-invalid-window-token-does-NOT-stop-the-run-at-the-assignment",
    ),
    pytest.param(
        {},
        {"env_extra": {"TIMEOUT_SECS": "08"}},
        id="an-eight-after-a-leading-zero-is-not-an-octal-digit",
    ),
    pytest.param({}, {"env_extra": {"TIMEOUT_SECS": ""}}, id="an-empty-window-takes-the-default"),
    pytest.param(
        {"ticks": (("1000", 0), ("1010", 0), ("12abc", 0), ("1030", 0))},
        {},
        id="a-clock-that-goes-non-numeric-mid-loop-ends-the-loop-quietly",
    ),
    pytest.param({"ticks": (("1000", 3),)}, {}, id="a-failing-clock-is-fatal-at-the-assignment"),
    pytest.param({"absent": ("date",)}, {}, id="date-is-not-on-path"),
    pytest.param(
        {"rc": {"sleep": {"5": 1}}, "replies": _replies(poll=[("starting|0\n", "", 0)])},
        {},
        id="a-failing-sleep-stops-the-poll-loop",
    ),
    pytest.param(
        {"absent": ("sleep",), "replies": _replies(poll=[("starting|0\n", "", 0)])},
        {},
        id="sleep-is-not-on-path",
    ),
    # ---- the environment block, which runs BEFORE the trap ------------------
    pytest.param({}, {"env_extra": {"VM_NET_BASE": "10.9.8"}}, id="the-subnet-base-is-honoured"),
    pytest.param({}, {"env_extra": {"VM_WORKERS": "23"}}, id="a-single-worker-id"),
    pytest.param(
        {}, {"env_extra": {"VM_WORKERS": "31 32 33"}}, id="only-the-first-worker-id-is-used"
    ),
    pytest.param(
        {},
        {"env_extra": {"VM_WORKERS": "  41   42  "}},
        id="surrounding-whitespace-around-the-worker-ids-is-discarded",
    ),
    pytest.param(
        {},
        {"env_extra": {"VM_WORKERS": "51\n52"}},
        id="only-the-first-LINE-of-worker-ids-is-read",
    ),
    pytest.param(
        {},
        {"env_extra": {"VM_WORKERS": "   "}},
        id="an-all-whitespace-worker-list-dies-before-the-trap-is-installed",
    ),
    pytest.param(
        {}, {"env_extra": {"VM_WORKERS": ""}}, id="an-empty-worker-list-takes-the-default"
    ),
    pytest.param(
        {}, {"env_extra": {"MACHINE_NAME": "worker-9"}}, id="the-machine-alias-is-honoured"
    ),
    pytest.param({}, {"env_extra": {"SSH_KEY": "/keys/lab_ed25519"}}, id="an-explicit-ssh-key"),
    pytest.param({}, {"env_extra": {"SSH_USER": "root"}}, id="an-explicit-ssh-user"),
    pytest.param(
        {},
        {"env_drop": ("USER",)},
        id="no-SSH_USER-and-no-USER-falls-through-to-whoami",
    ),
    pytest.param(
        {"absent": ("whoami",)},
        {"env_drop": ("USER",)},
        id="whoami-is-not-on-path-either",
    ),
    pytest.param(
        {"rc": {"whoami": {"": 13}}},
        {"env_drop": ("USER",)},
        id="a-failing-whoami-is-fatal-under-set-e",
    ),
    pytest.param(
        {},
        {"env_drop": ("HOME",)},
        id="no-HOME-and-no-SSH_KEY-is-a-fatal-set-u-violation",
    ),
    pytest.param(
        {},
        {"env_drop": ("HOME",), "env_extra": {"SSH_KEY": "/keys/explicit"}},
        id="an-explicit-key-means-HOME-is-never-read",
    ),
    pytest.param(
        {},
        {"env_extra": {"NO_COLOR": "1", "DEBUG": "true"}},
        id="NO_COLOR-and-DEBUG-change-nothing-on-a-pipe",
    ),
]


@pytest.mark.parametrize(("binder_kw", "run_kw"), CASES)
def test_port_and_twin_agree(tmp_path, binder_kw, run_kw):
    root = _fixture(tmp_path)
    run_kw = {k: v for k, v in run_kw.items() if v is not None}
    binder = _binder(tmp_path, **binder_kw)

    old = _run(TWIN_REL, root, tmp_path, binder, **run_kw)
    new = _run(PORT_REL, root, tmp_path, binder, **run_kw)

    for field in ("exit", "stdout", "stderr", "calls"):
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_every_external_is_reached_in_the_same_order(tmp_path):
    """ANTI-VACUITY, and the strongest claim in the file. Every comparison above
    is worthless if the orchestration never happened, and a port that printed
    the same log lines while talking to nothing would satisfy a stdout-only
    comparison exactly."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    out = _run(PORT_REL, root, tmp_path, binder)
    assert out["exit"] == 0, out

    names = [call[0] for call in out["calls"]]
    assert names.count("rdc") == 10, names
    assert names.count("ssh") == 4, names
    assert names.count("date") == 4, names
    assert names.count("sleep") == 2, names

    rdc = [call[1:] for call in out["calls"] if call[0] == "rdc"]
    assert rdc == [
        ["config", "ssh", "set", "--key", "<tmp>/.ssh/id_ed25519"],
        ["machine", "add", "worker-1", "--ip", "192.168.111.11", "--user", "labuser"],
        ["machine", "setup", "worker-1"],
        # The hand-called pre-clean, which is the SAME function as the trap.
        ["repo", "down", "healthcheck-smoke@worker-1"],
        ["repo", "delete", "healthcheck-smoke@worker-1", "--yes"],
        ["repo", "create", "healthcheck-smoke", "-m", "worker-1", "--size", "2G"],
        [
            "repo",
            "admin",
            "template",
            "apply",
            "healthcheck-smoke@worker-1",
            "--template",
            "app-postgres",
        ],
        ["repo", "up", "healthcheck-smoke@worker-1"],
        # And the EXIT trap, on the healthy path.
        ["repo", "down", "healthcheck-smoke@worker-1"],
        ["repo", "delete", "healthcheck-smoke@worker-1", "--yes"],
    ], rdc

    assert [call[1:] for call in out["calls"] if call[0] == "sleep"] == [["5"], ["5"]]
    assert [call[1:] for call in out["calls"] if call[0] == "date"] == [["+%s"]] * 4


def test_the_four_remote_programs_survive_as_single_arguments(tmp_path):
    """THE CONTRACT NO STREAM CAN SHOW. Each remote program is multi-line shell
    carrying quotes, `$` and a pipe, and each must reach ssh as ONE argument
    after five fixed options. A port that reflowed one line of it, or let the
    LOCAL shell expand `$sock`, would print exactly the same transcript and run
    a different program on the VM. Compared character for character, from both
    subjects, on the arm where all four are sent."""
    root = _fixture(tmp_path)
    binder = _binder(
        tmp_path,
        replies=_replies(poll=[("starting|0\n", "", 0)]),
        ticks=(("1000", 0), ("1010", 0), ("2000", 0)),
    )
    recorded = {}
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        ssh_calls = [call for call in out["calls"] if call[0] == "ssh"]
        assert len(ssh_calls) == 3, ssh_calls
        for call in ssh_calls:
            assert call[1:7] == [
                "-i",
                "<tmp>/.ssh/id_ed25519",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=15",
            ], call
            assert call[7] == "labuser@192.168.111.11", call
            assert len(call) == 9, "the remote program was split into %d arguments" % (
                len(call) - 8
            )
        recorded[subject.name] = [call[8] for call in ssh_calls]

    assert recorded[TWIN_REL.name] == recorded[PORT_REL.name], recorded

    poll, diag, sockets = recorded[TWIN_REL.name]
    assert poll.startswith("sudo bash -c '\n      for sock in /var/run/rediacc/docker-*.sock; do")
    assert '--filter name=^db$ --format "{{.ID}}"' in poll
    assert '"{{.State.Health.Status}}|{{.State.Health.FailingStreak}}"' in poll
    assert poll.endswith('echo "missing|"\n    \'')
    assert "--- last 30 container log lines ---" in diag
    assert "logs --tail 30" in diag
    assert sockets == "sudo ss -tlnp 'sport = :5432' 2>&1"


def test_the_healthy_run_is_not_refused(tmp_path):
    """THE NEGATIVE CONTROL. A smoke test with only positive controls will
    happily fail a deployment where nothing is wrong."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 0, "%s refused a converged deployment" % subject.name
        assert "✗" not in out["stderr"], out["stderr"]
        assert "PASS: app-postgres compose converged" in out["stderr"]
        assert "db reached healthy (streak=0)" in out["stderr"]


def test_a_container_that_never_converges_is_the_failure_this_exists_for(tmp_path):
    """THE POSITIVE CONTROL, and the single assertion whose failure would mean
    the smoke test had become vacuous: a `db` that stays `starting` for the whole
    window must exit 1, say so, and dump diagnostics. Both subjects."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, replies=_replies(poll=[("starting|7\n", "", 0)]))
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1, "%s exited %r on a container that never converged" % (
            subject.name,
            out["exit"],
        )
        assert (
            "✗ db did not reach healthy within 120s (last status=starting streak=7)"
            in out["stderr"]
        ), out["stderr"]
        assert "[diag] db container state + recent logs" in out["stderr"]
        assert "[diag] postgres listening sockets on host" in out["stderr"]
        kinds = [call[-1] for call in out["calls"] if call[0] == "ssh"]
        assert any("=== $sock ===" in cmd for cmd in kinds), "no diagnostic dump was requested"
        assert any("ss -tlnp" in cmd for cmd in kinds), "the listening sockets were never dumped"
        assert "PASS:" not in out["stderr"]


def test_the_app_assertion_is_a_second_independent_verdict(tmp_path):
    """`db` healthy and `app` not running is a DIFFERENT regression class from
    the healthcheck itself, and the twin reports it with no diagnostic dump at
    all. A port that folded the two into one check would still exit 1 here and
    would have lost the distinction."""
    root = _fixture(tmp_path)
    binder = _binder(
        tmp_path, replies=_replies(poll=[("healthy|0\n", "", 0)], app=[("exited\n", "", 0)])
    )
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1, out
        assert "✗ app container state=exited (want 'running')" in out["stderr"], out["stderr"]
        assert "[diag]" not in out["stderr"], "the app arm must not dump diagnostics"
        assert "did not reach healthy" not in out["stderr"]


def test_the_exit_trap_runs_on_every_path_including_the_happy_one(tmp_path):
    """`trap cleanup EXIT` plus one hand-called pre-clean. Four `rdc repo
    down`/`delete` calls and TWO "Cleanup (best-effort)" lines on a healthy run;
    two calls and one line when the run dies before the pre-clean. A port that
    cleaned up only on failure would leave a 2 GB repo on the VM after every
    green run."""
    root = _fixture(tmp_path)

    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["stderr"].count("Cleanup (best-effort)") == 2, out["stderr"]
        assert len([c for c in out["calls"] if c[:3] == ["rdc", "repo", "down"]]) == 2

    early = _binder(tmp_path, rc={"rdc": {"machine setup": 5}})
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, early)
        assert out["exit"] == 5, "%s lost the status the trap fired on" % subject.name
        assert out["stderr"].count("Cleanup (best-effort)") == 1, out["stderr"]
        assert len([c for c in out["calls"] if c[:3] == ["rdc", "repo", "down"]]) == 1


def test_the_environment_block_dies_before_the_trap_is_installed(tmp_path):
    """ORDERING THAT ONLY THE CALL LOG CAN SHOW. `VM_WORKERS="   "` collapses to
    an empty array and `${WORKER_IDS[0]}` is a `set -u` violation, and it happens
    ABOVE `trap cleanup EXIT`, so NOTHING is cleaned up and no `rdc` runs at all.
    A port that installed its trap at the top of `main` would run two pointless
    `rdc` calls against a machine it never registered."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, env_extra={"VM_WORKERS": "   "})
        assert out["exit"] == 1, out
        assert out["calls"] == [], "%s reached an external: %r" % (subject.name, out["calls"])
        assert "Cleanup (best-effort)" not in out["stderr"], out["stderr"]
        assert "<shell>: WORKER_IDS[0]: unbound variable" in out["stderr"], out["stderr"]


def test_a_zero_padded_timeout_is_read_as_octal_and_that_is_a_defect(tmp_path):
    """A REAL DEFECT IN THE TWIN, PINNED RATHER THAN FIXED.

    `deadline=$(($(date +%s) + TIMEOUT_SECS))` evaluates the variable as an
    ARITHMETIC EXPRESSION, so a leading zero selects base 8: `TIMEOUT_SECS=060`
    is a 48-second window, not a 60-second one, while the log line one row above
    still prints `timeout 060s`. Measured against a 10-second-per-read clock: 4
    probes at `060` against 5 at `60`.

    THE CLOCK STEP IS 10 HERE AND NOT THE FIXTURE DEFAULT OF 20, and the reason
    is a control that failed to fire. At 20 seconds a 48-second window and a
    60-second one both admit exactly 2 probes, so the first draft of this test
    "passed" the octal read and the plain one identically and proved nothing
    about either. A step that cannot resolve the difference it is measuring is a
    broken instrument, not a clean result.

    THE DIAGNOSTIC DUMP ALSO CONTAINS `name=^db$`, which is the second way this
    count goes wrong: filtering on that string alone silently adds one to every
    total. The poll program is the one WITHOUT the `=== $sock ===` echo.

    A caller who writes `060` for tidiness gets a window 20 percent shorter than
    the one the transcript claims, and the transcript will not say so. Both
    subjects are asserted; the day the twin quotes the variable or validates it,
    this goes red and names the decision.
    """
    root = _fixture(tmp_path)
    ticks = tuple((str(1000 + i * 10), 0) for i in range(40))
    counts = {}
    for value in ("060", "60"):
        binder = _binder(tmp_path, replies=_replies(poll=[("starting|0\n", "", 0)]), ticks=ticks)
        for subject in (TWIN_REL, PORT_REL):
            out = _run(subject, root, tmp_path, binder, env_extra={"TIMEOUT_SECS": value})
            probes = [
                c
                for c in out["calls"]
                if c[0] == "ssh" and "name=^db$" in c[-1] and "=== $sock ===" not in c[-1]
            ]
            counts.setdefault(value, []).append(len(probes))
            assert "timeout %ss" % value in out["stderr"], (
                "the log line must still print the raw string, not the parsed value"
            )
    assert counts["060"] == [4, 4], counts
    assert counts["60"] == [5, 5], counts
    assert counts["060"] != counts["60"], (
        "the octal read no longer changes the window; the defect may have been fixed, "
        "in which case this test is the record of what changed"
    )


def test_an_invalid_timeout_token_does_not_stop_the_run_where_it_should(tmp_path):
    """A SECOND REAL DEFECT IN THE TWIN, PINNED RATHER THAN FIXED.

    `set -e` does NOT fire on an arithmetic expansion error inside an assignment
    IN A SCRIPT FILE. So `TIMEOUT_SECS=12abc` prints `value too great for base`,
    leaves `deadline` UNSET, carries on, and dies one line later on
    `deadline: unbound variable` -- two diagnostics for one cause, the second of
    which names a variable the caller never heard of.

    Confirmed 2026-09-14 to be file-specific: the identical fragment run through
    `bash -c` exits at the first diagnostic. An unset identifier
    (`TIMEOUT_SECS=abc`) is a `set -u` violation instead and IS fatal at once,
    and the asymmetry is asserted in the same test because a port that treated
    both the same would pass either half alone.
    """
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)

    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, env_extra={"TIMEOUT_SECS": "12abc"})
        assert out["exit"] == 1, out
        assert '<shell>: 12abc: value too great for base (error token is "12abc")' in out["stderr"]
        assert "<shell>: deadline: unbound variable" in out["stderr"], (
            "%s stopped at the arithmetic error; the defect pinned here is that it does not"
            % subject.name
        )
        assert len([c for c in out["calls"] if c[0] == "date"]) == 2, (
            "%s must consult the clock twice: once for the deadline, once for the "
            "condition that then dies" % subject.name
        )

    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, env_extra={"TIMEOUT_SECS": "abc"})
        assert out["exit"] == 1, out
        assert "<shell>: abc: unbound variable" in out["stderr"], out["stderr"]
        assert "value too great for base" not in out["stderr"], out["stderr"]
        assert "deadline: unbound variable" not in out["stderr"], (
            "%s carried on past a set -u violation" % subject.name
        )


def test_the_poll_fallback_is_appended_not_substituted(tmp_path):
    """`$(_ssh ... 2>/dev/null || echo "ssh-error|")` captures the whole AND-OR
    list, so an ssh that PRINTS and then FAILS contributes both. The resulting
    two-line state splits into `starting` and `1\\nssh-error|`, and the streak
    the transcript reports therefore contains a newline. Ugly, real, and the
    exact shape a port that used the fallback as an else-branch would miss."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, replies=_replies(poll=[("starting|1\n", "", 4)]))
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1, out
        assert "status=starting streak=1\nssh-error|" in out["stderr"], out["stderr"]


def test_a_missing_ssh_is_silently_indistinguishable_from_a_failing_one(tmp_path):
    """Bash performs `2>/dev/null` BEFORE the command lookup fails, so during
    POLLING `command not found` is discarded along with everything else ssh
    would have said, and the `||` arm reports `ssh-error`. Nothing in the
    transcript says the binary was missing.

    THE DIAGNOSTIC DUMP HAS NO SUCH REDIRECTION, so there the same missing
    binary IS reported, twice. That asymmetry is the assertion: five silent
    lookups followed by two loud ones. Counting rather than testing for absence
    is deliberate -- a bare `not in` over the whole transcript was the first
    draft, and it failed on the two lines it should have been counting.
    """
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, absent=("ssh",))
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1, out
        assert "status=ssh-error streak=" in out["stderr"], out["stderr"]
        # The per-probe log line, not the summary line: the failure summary also
        # spells `status=ssh-error streak=`, so counting that substring alone
        # yields 6 and quietly credits the summary as a sixth probe.
        assert out["stderr"].count("waiting...") == 5, (
            "%s did not make five silent probes" % subject.name
        )
        assert out["stderr"].count("<shell>: ssh: command not found") == 2, (
            "%s reported the missing binary %d times; the five poll lookups must be "
            "silent and the two diagnostic ones must not be"
            % (subject.name, out["stderr"].count("<shell>: ssh: command not found"))
        )


def test_the_log_glyph_is_doubled_on_both_success_lines(tmp_path):
    """A COSMETIC DEFECT IN THE TWIN, PINNED RATHER THAN FIXED. `log_info`
    already prefixes U+2713, and both call sites pass a second one in the
    message, so the transcript reads `<check> <check> db reached healthy`. A
    port that tidied it would be nicer and would not be the same script."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert "✓ ✓ db reached healthy" in out["stderr"], out["stderr"]
        assert "✓ ✓ app container running" in out["stderr"], out["stderr"]


def test_only_the_config_ssh_set_stdout_is_discarded(tmp_path):
    """`>/dev/null` appears exactly once, on `rdc config ssh set`. Every other
    `rdc` call's stdout reaches the caller, and the two cleanup calls have their
    STDERR discarded instead. Three different redirection shapes in one script,
    and a port that used one shape everywhere would look identical on the happy
    path and hide a credential error on the first call."""
    root = _fixture(tmp_path)
    binder = _binder(
        tmp_path,
        stdout={"rdc": "OUT<%(joined)s>\n"},
        stderr={"rdc": "ERR<%(joined)s>\n"},
    )
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert "OUT<config ssh set" not in out["stdout"], out["stdout"]
        assert "ERR<config ssh set" in out["stderr"], out["stderr"]
        assert "OUT<machine add" in out["stdout"], out["stdout"]
        assert "ERR<machine add" not in out["stderr"], (
            "the machine-add stderr must be discarded, it is the arm that only warns"
        )
        assert "OUT<repo down healthcheck-smoke@worker-1>" in out["stdout"], out["stdout"]
        assert "ERR<repo down" not in out["stderr"], out["stderr"]


def test_the_mask_does_not_hide_the_message(tmp_path):
    """A CONTROL ON THE CONTROL. `_mask` collapses the `<$0>: line <n>: ` prefix
    on both sides; if it were greedier it would hide real divergences and every
    case above would pass for the wrong reason. And if the two prefixes were
    already equal the mask would be unnecessary, so that is asserted too."""
    sample = "/a/b/twin.sh: line 38: HOME: unbound variable\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: HOME: unbound variable\nkept: line noise\n", masked

    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    raw = {}
    for subject in (TWIN_REL, PORT_REL):
        proc = subprocess.run(
            ["bash" if subject.suffix == ".sh" else "python3", str(root / subject)],
            capture_output=True,
            text=True,
            env={
                "PATH": binder,
                "USER": "labuser",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(ROOT / ".ci"),
            },
            cwd=str(tmp_path),
            check=False,
            timeout=180,
        )
        raw[subject.name] = proc.stderr
    assert raw[TWIN_REL.name] != raw[PORT_REL.name], (
        "the two prefixes are identical, so the mask is unnecessary and should be deleted"
    )
    for name, text in raw.items():
        assert "HOME: unbound variable" in text, "%s said %r" % (name, text)
