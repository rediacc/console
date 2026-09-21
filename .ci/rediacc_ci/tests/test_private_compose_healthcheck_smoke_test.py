"""`rediacc_ci.private.compose_healthcheck_smoke_test`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/private/compose-healthcheck-smoke-test.sh` and the port over one fixture apiece and compared four channels: the exit code, stdout, stderr and the recorded argv of every external. Every case now compares against `goldens/compose-healthcheck-smoke-test/`, which holds the twin's OWN recorded bytes; each
golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE LEDGER IS `.ci/shadow/w7p4b-compose-healthcheck-smoke-test.observations.jsonl`, ELEVEN rows over eleven distinct trees, every one EQUIVALENT. The older `w7p6-` file exists with five rows and is deliberately not the citation: the w7p4b rows are the ones whose recorded `old.cmd` names this bash path and whose `new.cmd` names the module spec that replaced it.

NOTHING REAL IS EVER INVOKED, AND THE NEAR-MISS THAT PROVES IT MATTERS. The twin registered a worker VM with the `rdc` CLI, provisioned renet on it, created a 2 GB repo, applied a template, brought it up and then polled a Docker healthcheck over ssh. On this machine `rdc` IS on PATH, a symlink to the repository's own `rdc.sh`, and during exploratory work a PREPENDED scratch PATH
let one probe fall through to it, which ran `npm install` and `npm rebuild` inside the live checkout before failing. That is why PATH here is REPLACED AND NEVER PREPENDED, why the real name is asserted unreachable on every scratch PATH, and why `_binder` treats a probe it cannot prove absent as a harness failure rather than a passing case.

ALL FIVE EXTERNALS ARE RECORDING FAKES: `rdc`, `ssh`, `date`, `sleep`, `whoami`. Each appends its full argv to a shared JSONL log and returns canned bytes and a canned status. No case needs a machine, a docker daemon or a network, which is why this subject could be frozen at all.

THE CLOCK AND THE SLEEP ARE FAKES FOR A SECOND REASON, not just isolation. The twin's window was `TIMEOUT_SECS` seconds of real time with a real `sleep 5` between probes; a recording that honoured that would take minutes per case. `date` is a STEPPED COUNTER driven from a fixture list, so "the healthcheck converged on the third probe" and "the window closed with the container still
starting" are both exact, instant and reproducible.

WHY THE CALL LOG IS THE MOST IMPORTANT OF THE FOUR. Almost everything this script does is a side effect on a remote machine, and none of it appears on any stream.

The four REMOTE PROGRAMS are multi-line shell sent as ONE ssh argument each, and a port that reflowed the indentation, dropped a `2>/dev/null`, or word-split that socket query into three arguments would produce byte-identical output and talk to the VM differently.

`test_the_four_remote_programs_survive_as_single_arguments` compares them character for character, off the recording.

TWO CASES WERE DRIVEN INLINE BY THE DIFFERENTIAL AND ARE NAMED CASES HERE, and the reason is in their own comment: the octal-window defect needs a ten-second clock, because at the fixture's default step a 48-second window and a 60-second one admit the same number of probes and the pair proves nothing.

WHAT IS MASKED: the fixture root as `<root>`, the scratch directory as `<tmp>`, the `<$0>: line <n>: ` prefix that bash writes and the port composes from its own frame, and one byte-level escape for the single case that answers with bytes that are not UTF-8. `_mask` carries all four and says why.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
SLUG = "compose-healthcheck-smoke-test"
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


ESCAPE_RE = re.compile(r"\\x[0-9a-f]{2}")


def _mask(text: str, root: pathlib.Path, tmp: pathlib.Path) -> str:
    """The shell prefix, the two scratch paths, and one byte-level transformation.

    ONE CASE ANSWERS WITH BYTES THAT ARE NOT UTF-8 on purpose (`a-reply-that-is-not-utf8-is-still-ruled-on`), so the streams cannot simply be written to a golden: Python hands them back as lone surrogates and encoding one is an error. They are re-encoded and decoded with `backslashreplace`, which turns each such byte into `\\xNN` and leaves every other byte alone. Both sides go
    through this same function before anything is compared, so it narrows nothing; the only way it could is a stream carrying a LITERAL backslash-x, which `test_the_byte_escape_is_well_formed_over_the_corpus` refuses.
    """
    text = text.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")
    text = SHELL_PREFIX.sub("<shell>: ", text)
    return text.replace(str(root), "<root>").replace(str(tmp), "<tmp>")


def _fixture(tmp_path: pathlib.Path, *, twin: bool = False) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because the twin sources `../lib/common.sh` relative to its own `BASH_SOURCE`, and because both subjects put their own path into every bash diagnostic they emit. Driving the tracked files directly would name the real checkout in output the differential then has to mask more aggressively.
    """
    root = tmp_path.resolve() / "tree"
    (root / ".ci" / "scripts" / "private").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "rediacc_ci" / "private").mkdir(parents=True, exist_ok=True)
    if twin:
        # ONLY WHEN THE TWIN IS THE SUBJECT, which is the one-shot recorder and nothing else. The suite drives the port or a throwaway mutant of it, and the twin is no longer in the tree to copy.
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

    `absent` names fakes to LEAVE OUT, which is how every `command not found` arm is driven. EACH EXCLUSION IS ASSERTED, because a probe that cannot fire is indistinguishable from a subject that cannot fail -- and because this machine has a real `rdc` that a leaky PATH would reach.
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

    Output is captured as BYTES and decoded with `surrogateescape`, so a remote reply that is not valid UTF-8 survives the harness intact instead of raising inside it.
    """
    cwd = tmp_path.resolve() / "elsewhere"
    cwd.mkdir(exist_ok=True)
    env = {
        "PATH": binder,
        "HOME": str(tmp_path.resolve()),
        "USER": "labuser",
        "PYTHONDONTWRITEBYTECODE": "1",
        # The port imports `rediacc_ci.log`; the COPY under the fixture is what runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
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


# name -> the wiring this case is driven with, preserved verbatim from the differential.
CASE_KW = {
    "the-db-converges-and-the-app-is-running": ({}, {}),
    "arguments-are-ignored-entirely": ({}, {"argv": ("--anything", "extra")}),
    "the-first-probe-is-already-healthy": (
        {"replies": _replies(poll=[("healthy|0\n", "", 0)])},
        {},
    ),
    "the-window-closes-with-the-container-still-starting": (
        {"replies": _replies(poll=[("starting|3\n", "", 0)])},
        {},
    ),
    "an-unhealthy-container-never-converges-either": (
        {"replies": _replies(poll=[("unhealthy|9\n", "", 0)])},
        {},
    ),
    "no-db-container-on-any-socket": ({"replies": _replies(poll=[("missing|\n", "", 0)])}, {}),
    "every-probe-fails-so-the-fallback-supplies-the-status": (
        {"replies": _replies(poll=[("", "ssh: connect: no route to host\n", 255)])},
        {},
    ),
    "a-probe-that-prints-AND-fails-appends-the-fallback-to-its-output": (
        {"replies": _replies(poll=[("starting|1\n", "", 4)])},
        {},
    ),
    "trailing-newlines-are-stripped-by-the-capture": (
        {"replies": _replies(poll=[("healthy|0\n\n\n\n", "", 0)])},
        {},
    ),
    "a-reply-with-no-pipe-makes-status-and-streak-the-same-string": (
        {"replies": _replies(poll=[("healthy\n", "", 0)])},
        {},
    ),
    "only-the-first-pipe-splits-the-reply": (
        {"replies": _replies(poll=[("healthy|0|extra\n", "", 0)])},
        {},
    ),
    "an-empty-reply-is-an-empty-status": ({"replies": _replies(poll=[("", "", 0)])}, {}),
    "the-status-comparison-is-case-sensitive": (
        {"replies": _replies(poll=[("HEALTHY|0\n", "", 0)])},
        {},
    ),
    "a-leading-space-is-not-stripped-so-it-is-not-healthy": (
        {"replies": _replies(poll=[(" healthy|0\n", "", 0)])},
        {},
    ),
    "a-reply-that-is-not-utf8-is-still-ruled-on": (
        {"replies": _replies(poll=[("healthy|\udcff\udcfe\n", "", 0)])},
        {},
    ),
    "the-db-is-healthy-but-the-app-never-started": (
        {"replies": _replies(poll=[("healthy|0\n", "", 0)], app=[("exited\n", "", 0)])},
        {},
    ),
    "there-is-no-app-container-at-all": (
        {"replies": _replies(poll=[("healthy|0\n", "", 0)], app=[("missing\n", "", 0)])},
        {},
    ),
    "the-app-probe-cannot-connect": (
        {"replies": _replies(poll=[("healthy|0\n", "", 0)], app=[("", "", 255)])},
        {},
    ),
    "both-diagnostic-probes-fail-and-neither-changes-the-verdict": (
        {
            "replies": _replies(
                poll=[("starting|2\n", "", 0)],
                diag=[("dump line one\ndump line two\n", "docker: no such socket\n", 1)],
                ss=[("", "ss: cannot open netlink\n", 2)],
            )
        },
        {},
    ),
    "ssh-is-not-on-path-at-all": (
        {"absent": ("ssh",), "replies": _replies(poll=[("starting|0\n", "", 0)])},
        {},
    ),
    "rdc-config-ssh-set-fails": ({"rc": {"rdc": {"config ssh set": 3}}}, {}),
    "rdc-machine-add-fails-and-only-warns": ({"rc": {"rdc": {"machine add": 11}}}, {}),
    "rdc-machine-setup-fails": ({"rc": {"rdc": {"machine setup": 5}}}, {}),
    "rdc-repo-create-fails": ({"rc": {"rdc": {"repo create": 6}}}, {}),
    "rdc-template-apply-fails": ({"rc": {"rdc": {"repo admin": 8}}}, {}),
    "rdc-repo-up-fails-and-the-status-survives": ({"rc": {"rdc": {"repo up": 7}}}, {}),
    "a-failing-cleanup-cannot-fail-the-run": (
        {"rc": {"rdc": {"repo down": 9, "repo delete": 9}}},
        {},
    ),
    "rdc-is-not-on-path-at-all": ({"absent": ("rdc",)}, {}),
    "only-the-config-ssh-set-stdout-is-discarded": (
        {
            "stdout": {"rdc": "rdc said this on stdout: %(joined)s\n"},
            "stderr": {"rdc": "rdc said this on stderr: %(joined)s\n"},
        },
        {},
    ),
    "a-zero-window-never-probes-at-all": ({}, {"env_extra": {"TIMEOUT_SECS": "0"}}),
    "a-short-window-admits-one-probe": ({}, {"env_extra": {"TIMEOUT_SECS": "40"}}),
    "a-zero-padded-window-is-read-as-OCTAL-which-is-the-defect": (
        {},
        {"env_extra": {"TIMEOUT_SECS": "060"}},
    ),
    "the-same-window-without-the-leading-zero-for-comparison": (
        {},
        {"env_extra": {"TIMEOUT_SECS": "60"}},
    ),
    "a-hex-window-is-accepted-as-arithmetic": ({}, {"env_extra": {"TIMEOUT_SECS": "0x50"}}),
    "whitespace-around-the-window-is-arithmetic-whitespace": (
        {},
        {"env_extra": {"TIMEOUT_SECS": "  120  "}},
    ),
    "an-unset-identifier-window-is-a-fatal-set-u-violation": (
        {},
        {"env_extra": {"TIMEOUT_SECS": "abc"}},
    ),
    "an-invalid-window-token-does-NOT-stop-the-run-at-the-assignment": (
        {},
        {"env_extra": {"TIMEOUT_SECS": "12abc"}},
    ),
    "an-eight-after-a-leading-zero-is-not-an-octal-digit": (
        {},
        {"env_extra": {"TIMEOUT_SECS": "08"}},
    ),
    "an-empty-window-takes-the-default": ({}, {"env_extra": {"TIMEOUT_SECS": ""}}),
    "a-clock-that-goes-non-numeric-mid-loop-ends-the-loop-quietly": (
        {"ticks": (("1000", 0), ("1010", 0), ("12abc", 0), ("1030", 0))},
        {},
    ),
    "a-failing-clock-is-fatal-at-the-assignment": ({"ticks": (("1000", 3),)}, {}),
    "date-is-not-on-path": ({"absent": ("date",)}, {}),
    "a-failing-sleep-stops-the-poll-loop": (
        {"rc": {"sleep": {"5": 1}}, "replies": _replies(poll=[("starting|0\n", "", 0)])},
        {},
    ),
    "sleep-is-not-on-path": (
        {"absent": ("sleep",), "replies": _replies(poll=[("starting|0\n", "", 0)])},
        {},
    ),
    "the-subnet-base-is-honoured": ({}, {"env_extra": {"VM_NET_BASE": "10.9.8"}}),
    "a-single-worker-id": ({}, {"env_extra": {"VM_WORKERS": "23"}}),
    "only-the-first-worker-id-is-used": ({}, {"env_extra": {"VM_WORKERS": "31 32 33"}}),
    "surrounding-whitespace-around-the-worker-ids-is-discarded": (
        {},
        {"env_extra": {"VM_WORKERS": "  41   42  "}},
    ),
    "only-the-first-LINE-of-worker-ids-is-read": ({}, {"env_extra": {"VM_WORKERS": "51\n52"}}),
    "an-all-whitespace-worker-list-dies-before-the-trap-is-installed": (
        {},
        {"env_extra": {"VM_WORKERS": "   "}},
    ),
    "an-empty-worker-list-takes-the-default": ({}, {"env_extra": {"VM_WORKERS": ""}}),
    "the-machine-alias-is-honoured": ({}, {"env_extra": {"MACHINE_NAME": "worker-9"}}),
    "an-explicit-ssh-key": ({}, {"env_extra": {"SSH_KEY": "/keys/lab_ed25519"}}),
    "an-explicit-ssh-user": ({}, {"env_extra": {"SSH_USER": "root"}}),
    "no-SSH_USER-and-no-USER-falls-through-to-whoami": ({}, {"env_drop": ("USER",)}),
    "whoami-is-not-on-path-either": ({"absent": ("whoami",)}, {"env_drop": ("USER",)}),
    "a-failing-whoami-is-fatal-under-set-e": (
        {"rc": {"whoami": {"": 13}}},
        {"env_drop": ("USER",)},
    ),
    "no-HOME-and-no-SSH_KEY-is-a-fatal-set-u-violation": ({}, {"env_drop": ("HOME",)}),
    "an-explicit-key-means-HOME-is-never-read": (
        {},
        {"env_drop": ("HOME",), "env_extra": {"SSH_KEY": "/keys/explicit"}},
    ),
    # THE OCTAL PAIR, ON A CLOCK FINE ENOUGH TO SEE IT. The differential drove these two inline rather than as cases, with a ten-second step: at the fixture's default of twenty a 48-second window and a 60-second one both admit exactly two probes, so the pair proves nothing about either. An instrument that cannot resolve the difference it is measuring is a broken instrument, not a
    # clean result.
    "a-zero-padded-window-on-a-ten-second-clock": (
        {
            "replies": _replies(poll=[("starting|0\n", "", 0)]),
            "ticks": tuple((str(1000 + i * 10), 0) for i in range(40)),
        },
        {"env_extra": {"TIMEOUT_SECS": "060"}},
    ),
    "the-same-window-undecorated-on-a-ten-second-clock": (
        {
            "replies": _replies(poll=[("starting|0\n", "", 0)]),
            "ticks": tuple((str(1000 + i * 10), 0) for i in range(40)),
        },
        {"env_extra": {"TIMEOUT_SECS": "60"}},
    ),
    "NO_COLOR-and-DEBUG-change-nothing-on-a-pipe": (
        {},
        {"env_extra": {"NO_COLOR": "1", "DEBUG": "true"}},
    ),
}


CASES = tuple(CASE_KW)

CALLS_MARKER = "--- calls ---\n"


def run(
    tmp_path: pathlib.Path, name: str, *, subject_rel: pathlib.PurePosixPath = PORT_REL
) -> dict[str, object]:
    """One subject, once, over this case's own fixture."""
    binder_kw, run_kw = CASE_KW[name]
    root = _fixture(tmp_path, twin=subject_rel.suffix == ".sh")
    binder = _binder(tmp_path, **{k: v for k, v in binder_kw.items() if v is not None})
    return _run(
        subject_rel, root, tmp_path, binder, **{k: v for k, v in run_kw.items() if v is not None}
    )


def render(out: dict[str, object]) -> str:
    return "%s%s%s\n" % (
        frozen.render(out["exit"], out["stdout"], out["stderr"]),
        CALLS_MARKER,
        json.dumps(out["calls"], indent=2),
    )


def recorded(name: str) -> dict[str, object]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return {
        "exit": int(exit_line.removeprefix("exit: ")),
        "stdout": stdout,
        "stderr": stderr,
        "calls": json.loads(calls),
    }


def compare(tmp_path: pathlib.Path, name: str) -> dict[str, object]:
    want = recorded(name)
    got = run(tmp_path, name)
    for field in ("exit", "stdout", "stderr", "calls"):
        assert got[field] == want[field], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            field,
            want[field],
            got[field],
        )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path, name):
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned():
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_host_path():
    """The scratch tree and the fixture root are masked, so a golden naming either would be one that reds on another machine."""
    for name in CASES:
        out = recorded(name)
        blob = "\n".join([out["stdout"], out["stderr"], json.dumps(out["calls"])])
        assert str(ROOT) not in blob, name
        assert "/tmp/" not in blob, name


def test_the_byte_escape_is_well_formed_over_the_corpus():
    """THE CONTROL ON THE ONE BYTE-LEVEL TRANSFORMATION.

    `backslashreplace` is injective only while no recorded stream carries a literal backslash-x of its own, so every `\\x` left in a golden must be a well-formed `\\xNN` escape. A corpus that grew one would make two different byte strings compare equal, and this is what refuses it.
    """
    for name in CASES:
        out = recorded(name)
        for stream in (out["stdout"], out["stderr"]):
            assert "\\x" not in ESCAPE_RE.sub("", stream), name


def test_every_external_is_reached_in_the_same_order():
    """ANTI-VACUITY, and the strongest claim in the file. Every comparison above is worthless if the orchestration never happened, and a port that printed the same log lines while talking to nothing would satisfy a stdout-only comparison exactly."""
    out = recorded("the-db-converges-and-the-app-is-running")
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


def test_the_four_remote_programs_survive_as_single_arguments():
    """THE CONTRACT NO STREAM CAN SHOW. Each remote program is multi-line shell carrying quotes, `$` and a pipe, and each must reach ssh as ONE argument after five fixed options. A port that reflowed one line of it, or let the LOCAL shell expand `$sock`, would print exactly the same transcript and run a different program on the VM.

    Compared character for character, off the recording of the arm where all four are sent.
    """
    out = recorded("the-window-closes-with-the-container-still-starting")
    ssh_calls = [call for call in out["calls"] if call[0] == "ssh"]
    assert len(ssh_calls) == 7, ssh_calls
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
        assert len(call) == 9, "the remote program was split into %d arguments" % (len(call) - 8)

    programs = [call[8] for call in ssh_calls]
    poll = next(p for p in programs if "name=^db$" in p and "=== $sock ===" not in p)
    diag = next(p for p in programs if "=== $sock ===" in p)
    sockets = next(p for p in programs if "ss -tlnp" in p)
    assert poll.startswith("sudo bash -c '\n      for sock in /var/run/rediacc/docker-*.sock; do")
    assert '--filter name=^db$ --format "{{.ID}}"' in poll
    assert '"{{.State.Health.Status}}|{{.State.Health.FailingStreak}}"' in poll
    assert poll.endswith('echo "missing|"\n    \'')
    assert "--- last 30 container log lines ---" in diag
    assert "logs --tail 30" in diag
    assert sockets == "sudo ss -tlnp 'sport = :5432' 2>&1"


def test_the_healthy_run_is_not_refused():
    """THE NEGATIVE CONTROL. A smoke test with only positive controls will happily fail a deployment where nothing is wrong."""
    out = recorded("the-db-converges-and-the-app-is-running")
    assert out["exit"] == 0, "a converged deployment was refused"
    assert "✗" not in out["stderr"], out["stderr"]
    assert "PASS: app-postgres compose converged" in out["stderr"]
    assert "db reached healthy (streak=0)" in out["stderr"]


def test_a_container_that_never_converges_is_the_failure_this_exists_for():
    """THE POSITIVE CONTROL, and the single assertion whose failure would mean the smoke test had become vacuous: a `db` that stays `starting` for the whole window must exit 1, say so, and dump diagnostics."""
    out = recorded("the-window-closes-with-the-container-still-starting")
    assert out["exit"] == 1
    assert (
        "✗ db did not reach healthy within 120s (last status=starting streak=3)" in out["stderr"]
    ), out["stderr"]
    assert "[diag] db container state + recent logs" in out["stderr"]
    assert "[diag] postgres listening sockets on host" in out["stderr"]
    kinds = [call[-1] for call in out["calls"] if call[0] == "ssh"]
    assert any("=== $sock ===" in cmd for cmd in kinds), "no diagnostic dump was requested"
    assert any("ss -tlnp" in cmd for cmd in kinds), "the listening sockets were never dumped"
    assert "PASS:" not in out["stderr"]


def test_the_app_assertion_is_a_second_independent_verdict():
    """`db` healthy and `app` not running is a DIFFERENT regression class from the healthcheck itself, and it is reported with no diagnostic dump at all. A port that folded the two into one check would still exit 1 here and would have lost the distinction."""
    out = recorded("the-db-is-healthy-but-the-app-never-started")
    assert out["exit"] == 1
    assert "✗ app container state=exited (want 'running')" in out["stderr"], out["stderr"]
    assert "[diag]" not in out["stderr"], "the app arm must not dump diagnostics"
    assert "did not reach healthy" not in out["stderr"]


def test_the_exit_trap_runs_on_every_path_including_the_happy_one():
    """`trap cleanup EXIT` plus one hand-called pre-clean. Four `rdc repo down`/`delete` calls and TWO "Cleanup (best-effort)" lines on a healthy run; two calls and one line when the run dies before the pre-clean. A port that cleaned up only on failure would leave a 2 GB repo on the VM after every green run."""
    healthy = recorded("the-db-converges-and-the-app-is-running")
    assert healthy["stderr"].count("Cleanup (best-effort)") == 2, healthy["stderr"]
    assert len([c for c in healthy["calls"] if c[:3] == ["rdc", "repo", "down"]]) == 2

    early = recorded("rdc-machine-setup-fails")
    assert early["exit"] == 5, "the status the trap fired on was lost"
    assert early["stderr"].count("Cleanup (best-effort)") == 1, early["stderr"]
    assert len([c for c in early["calls"] if c[:3] == ["rdc", "repo", "down"]]) == 1


def test_the_environment_block_dies_before_the_trap_is_installed():
    """ORDERING THAT ONLY THE CALL LOG CAN SHOW. `VM_WORKERS="   "` collapses to an empty array and `${WORKER_IDS[0]}` is a `set -u` violation, and it happens ABOVE `trap cleanup EXIT`, so NOTHING is cleaned up and no `rdc` runs at all. A port that installed its trap at the top of `main` would run two pointless `rdc` calls against a machine it never registered."""
    out = recorded("an-all-whitespace-worker-list-dies-before-the-trap-is-installed")
    assert out["exit"] == 1
    assert out["calls"] == [], "an external was reached: %r" % out["calls"]
    assert "Cleanup (best-effort)" not in out["stderr"], out["stderr"]
    assert "<shell>: WORKER_IDS[0]: unbound variable" in out["stderr"], out["stderr"]


def _probe_count(out) -> int:
    """Poll probes only: the diagnostic dump also names `name=^db$` and would otherwise be counted as one."""
    return len(
        [
            c
            for c in out["calls"]
            if c[0] == "ssh" and "name=^db$" in c[-1] and "=== $sock ===" not in c[-1]
        ]
    )


def test_a_zero_padded_timeout_is_read_as_octal_and_that_is_a_defect():
    """A REAL DEFECT IN THE TWIN, PINNED RATHER THAN FIXED.

    `deadline=$(($(date +%s) + TIMEOUT_SECS))` evaluated the variable as an ARITHMETIC EXPRESSION, so a leading zero selected base 8: `TIMEOUT_SECS=060` is a 48-second window, not a 60-second one, while the log line one row above still prints `timeout 060s`.

    THE CLOCK STEP IS TEN SECONDS IN THESE TWO RECORDINGS AND NOT THE FIXTURE DEFAULT OF TWENTY, and the reason is a control that failed to fire. At twenty a 48-second window and a 60-second one both admit exactly two probes, so the first draft of this comparison "passed" the octal read and the plain one identically and proved nothing about either.

    A caller who writes `060` for tidiness gets a window 20 percent shorter than the one the transcript claims, and the transcript will not say so. The day the variable is quoted or validated, these recordings go red and name the decision.
    """
    octal = recorded("a-zero-padded-window-on-a-ten-second-clock")
    plain = recorded("the-same-window-undecorated-on-a-ten-second-clock")
    assert _probe_count(octal) == 4, octal["calls"]
    assert _probe_count(plain) == 5, plain["calls"]
    assert "timeout 060s" in octal["stderr"], octal["stderr"]
    assert octal["exit"] == plain["exit"] == 1


def test_an_invalid_timeout_token_does_not_stop_the_run_where_it_should():
    """A SECOND REAL DEFECT IN THE TWIN, PINNED RATHER THAN FIXED.

    `set -e` does NOT fire on an arithmetic expansion error inside an assignment IN A SCRIPT FILE. So `TIMEOUT_SECS=12abc` printed `value too great for base`, left `deadline` UNSET, carried on, and died one line later on `deadline: unbound variable`, two diagnostics for one cause, the second of which names a variable the caller never heard of.

    An unset identifier (`TIMEOUT_SECS=abc`) is a `set -u` violation instead and IS fatal at once, and the asymmetry is asserted here because a port that treated both the same would satisfy either half alone.
    """
    loose = recorded("an-invalid-window-token-does-NOT-stop-the-run-at-the-assignment")
    assert loose["exit"] == 1
    assert '<shell>: 12abc: value too great for base (error token is "12abc")' in loose["stderr"]
    assert "<shell>: deadline: unbound variable" in loose["stderr"], (
        "the run stopped at the arithmetic error; the defect pinned here is that it does not"
    )
    assert len([c for c in loose["calls"] if c[0] == "date"]) == 2, (
        "the clock must be consulted twice: once for the deadline, once for the condition "
        "that then dies"
    )

    strict = recorded("an-unset-identifier-window-is-a-fatal-set-u-violation")
    assert strict["exit"] == 1
    assert "<shell>: abc: unbound variable" in strict["stderr"], strict["stderr"]
    assert "value too great for base" not in strict["stderr"], strict["stderr"]
    assert "deadline: unbound variable" not in strict["stderr"], (
        "the run carried on past a set -u violation"
    )


def test_the_poll_fallback_is_appended_not_substituted():
    """`$(_ssh ... 2>/dev/null || echo "ssh-error|")` captures the whole AND-OR list, so an ssh that PRINTS and then FAILS contributes both. The resulting two-line state splits into `starting` and `1\\nssh-error|`, and the streak the transcript reports therefore contains a newline. Ugly, real, and the exact shape a port that used the fallback as an else-branch would miss."""
    out = recorded("a-probe-that-prints-AND-fails-appends-the-fallback-to-its-output")
    assert out["exit"] == 1
    assert "status=starting streak=1\nssh-error|" in out["stderr"], out["stderr"]


def test_a_missing_ssh_is_silently_indistinguishable_from_a_failing_one():
    """Bash performs `2>/dev/null` BEFORE the command lookup fails, so during POLLING `command not found` is discarded along with everything else ssh would have said, and the `||` arm reports `ssh-error`. Nothing in the transcript says the binary was missing.

    THE DIAGNOSTIC DUMP HAS NO SUCH REDIRECTION, so there the same missing binary IS reported, twice. That asymmetry is the assertion: five silent lookups followed by two loud ones. Counting rather than testing for absence is deliberate, since a bare `not in` over the whole transcript was the first draft and it failed on the two lines it should have been counting.
    """
    out = recorded("ssh-is-not-on-path-at-all")
    assert out["exit"] == 1
    assert "status=ssh-error streak=" in out["stderr"], out["stderr"]
    # The per-probe log line, not the summary line: the failure summary also spells `status=ssh-error streak=`, so counting that substring alone yields 6 and quietly credits the summary as a sixth probe.
    assert out["stderr"].count("waiting...") == 5, "there were not five silent probes"
    assert out["stderr"].count("<shell>: ssh: command not found") == 2, (
        "the missing binary was reported %d times; the five poll lookups must be silent and "
        "the two diagnostic ones must not be"
        % out["stderr"].count("<shell>: ssh: command not found")
    )


def test_the_log_glyph_is_doubled_on_both_success_lines():
    """A COSMETIC DEFECT IN THE TWIN, PINNED RATHER THAN FIXED. `log_info` already prefixes U+2713, and both call sites passed a second one in the message, so the transcript reads it twice. A port that tidied it would be nicer and would not be the same script."""
    out = recorded("the-db-converges-and-the-app-is-running")
    assert "✓ ✓ db reached healthy" in out["stderr"], out["stderr"]
    assert "✓ ✓ app container running" in out["stderr"], out["stderr"]


def test_only_the_config_ssh_set_stdout_is_discarded():
    """`>/dev/null` appears exactly once, on `rdc config ssh set`. Every other `rdc` call's stdout reaches the caller, and the two cleanup calls have their STDERR discarded instead. Three different redirection shapes in one script, and a port that used one shape everywhere would look identical on the happy path and hide a credential error on the first call."""
    out = recorded("only-the-config-ssh-set-stdout-is-discarded")
    assert "rdc said this on stdout: config ssh set" not in out["stdout"], out["stdout"]
    assert "rdc said this on stderr: config ssh set" in out["stderr"], out["stderr"]
    assert "rdc said this on stdout: machine add" in out["stdout"], out["stdout"]
    assert "rdc said this on stderr: machine add" not in out["stderr"], (
        "the machine-add stderr must be discarded, it is the arm that only warns"
    )
    assert "rdc said this on stdout: repo down healthcheck-smoke@worker-1" in out["stdout"]
    assert "rdc said this on stderr: repo down" not in out["stderr"], out["stderr"]


def test_the_mask_does_not_hide_the_message():
    """A CONTROL ON THE CONTROL, and half of it is what the deletion cost.

    `_mask` collapses the `<$0>: line <n>: ` prefix; if it were greedier it would hide real divergences and every case above would pass for the wrong reason. The unit half below still drives that directly. What is gone is the half that ran BOTH subjects and asserted their raw prefixes DIFFER, which was the proof that the mask was necessary rather than decorative; the twin's own
    prefix survives only in the blob every golden header names.
    """
    sample = "/a/b/twin.sh: line 38: HOME: unbound variable\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: HOME: unbound variable\nkept: line noise\n", masked

    out = recorded("no-HOME-and-no-SSH_KEY-is-a-fatal-set-u-violation")
    assert out["exit"] == 1
    assert "<shell>: HOME: unbound variable" in out["stderr"], out["stderr"]


def test_a_planted_skip_of_the_app_assertion_is_caught(tmp_path):
    """THE CONTROL ON THE GOLDENS. Stop asking whether the app container is running.

    The healthcheck and the app assertion are two independent verdicts: a compose file whose `db` converges while `app` sits in `exited` is a broken deployment that the poll alone calls healthy. A mutant that drops the second question still prints the same PASS line for the first and still exits 0 over the healthy fixture, so the streams are no help; it is the recorded argv that
    loses an ssh call, and the one it loses is the only one that ever asks about `app`.

    The mutant is a throwaway copy placed at the port's own path inside the fixture tree, which is where the subject resolves its root from; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "        app_state = _capture_or(ssh_argv(ssh_key, ssh_user, vm_ip, APP_REMOTE), APP_FALLBACK)\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, '        app_state = "running"\n')

    name = "the-db-converges-and-the-app-is-running"
    want = recorded(name)
    binder_kw, run_kw = CASE_KW[name]
    root = _fixture(tmp_path / "planted")
    (root / PORT_REL).write_text(mutated, encoding="utf-8")
    binder = _binder(tmp_path / "planted", **{k: v for k, v in binder_kw.items() if v is not None})
    got = _run(
        PORT_REL,
        root,
        tmp_path / "planted",
        binder,
        **{k: v for k, v in run_kw.items() if v is not None},
    )

    want_app = [c for c in want["calls"] if c[0] == "ssh" and "name=^app$" in c[-1]]
    got_app = [c for c in got["calls"] if c[0] == "ssh" and "name=^app$" in c[-1]]
    assert len(want_app) == 1, "the recorded corpus moved"
    assert got_app == [], "the plant did not drop the app probe"
    assert got["exit"] == want["exit"] == 0
    assert got["stdout"] == want["stdout"]

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
