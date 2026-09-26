"""Asking `docker` something, where "missing" and "refused" are different answers.

THE ONE RULE THIS MODULE EXISTS FOR. "Docker does not work here" is three different facts with three different next actions, and every spelling in this tree flattens them to one:

    ABSENT        no `docker` on PATH at all          -> install it, or skip
    UNREACHABLE   the CLI runs, no engine answers     -> start the engine
    DENIED        the engine is there, this user is not in the group
                                                      -> sg docker / re-login
    FAILED        the engine answered and the COMMAND failed
                                                      -> a real finding

`.ci/lib/setup.sh:565-571` records why the first two must not be merged, and it is the sharpest case in the repo: "Docker Desktop puts a `docker` shim on PATH that EXISTS but cannot reach an engine, so `command -v docker` succeeds and the real problem is a WSL-integration toggle in a Windows GUI, which no error further down would ever name." `.ci/lib/local-common.sh:673-679`
records why the third is separate: "Distinguish 'no docker' from 'docker installed, user not in the group'", and it then re-execs under `sg docker` rather than reporting a failure at all.

------------------------------------------------------------------------------
MEASUREMENT 1: THE EXIT CODE ALONE CANNOT TELL YOU WHICH OF THE FOUR IT IS.
------------------------------------------------------------------------------
Measured on this host, docker 29.7.2, 2026-09-06:

    DOCKER_HOST=unix:///nonexistent/docker.sock docker info      -> exit 1
    DOCKER_HOST=unix:///nonexistent/docker.sock docker ps        -> exit 1
    docker frobnicate                                            -> exit 1

An unreachable daemon and a command that does not exist produce the SAME code. So classification here reads STDERR, and the marker table below is built from that run rather than from memory. The exit code remains the verdict -- non-zero is always a failure -- and the markers only choose which kind, so a docker release that rewords its messages degrades this to FAILED and never to
"fine".

------------------------------------------------------------------------------
MEASUREMENT 2: `docker info` WRITES A FULL, HEALTHY-LOOKING REPORT TO STDOUT
WHILE FAILING.
------------------------------------------------------------------------------
Same run: with an unreachable daemon, `docker info` exits 1 and still prints the entire CLIENT section on stdout -- version, plugins, contexts -- ending with a bare `Server:` line and nothing under it. So a probe written as "did it print anything" answers YES for a machine with no engine. That shape is not hypothetical here: `.ci/legacy/run-legacy.sh:766-768` and
`.ci/lib/devbox.sh:76` both branch on `docker version` output-or-status, and the only reason they are correct is that they happen to redirect to /dev/null and test the status.

Which is the same rule the sibling module states for `gh`: check the status before you use the output. `DockerResult.stdout` is a property that RAISES the classified error unless the call succeeded, so a caller cannot write `docker_info().stdout.splitlines()` and receive a client-only report as though it described a running engine. `.stdout_raw` holds the bytes for diagnostics and
`.stderr` is always readable, because the sentence naming the socket is the only useful thing a failed docker call produces.

------------------------------------------------------------------------------
MEASUREMENT 3: THE OBVIOUS `client_version` SPELLING FORCES YOU TO SKIP THE CHECK.
------------------------------------------------------------------------------
    DOCKER_HOST=unix:///nope.sock docker version --format '{{.Client.Version}}'
        -> prints "29.7.2", exits 1

The right answer on stdout, and a non-zero exit, at once. `.ci/lib/setup.sh:583` wraps the Server variant of that call in `|| echo 'version unknown'`, which is correct there and is also the reason the pattern spreads: the only way to use this call is to ignore its status. So `client_version()` below uses `docker --version` instead, which contacts no daemon and exits 0 offline
(measured), and the status check survives. A module whose own helpers have to break its rule has not got a rule.

------------------------------------------------------------------------------
EXIT 77 IS "COULD NOT RUN", AND IT IS NEVER A VERDICT.
------------------------------------------------------------------------------
The convention is this repo's, not an invention: `scripts/ci-runner/pool.ts:80-89` defines it ("Exit code a gate uses to say 'I could not run' ... 1 is a finding, 2 is usage, 124 is a timeout, 127 is not-found"), `.ci/scripts/quality/ check-python-lint.sh:191` established it for ruff, `.ci/scripts/security/ shfmt.sh:52-60` adopted it, and `.ci/rediacc_ci/check_pytest.py:124` names
it
`EXIT_CANNOT_RUN = 77`. The ci-runner classifies 77 as BLOCKED: counted, named,
recorded in the push receipt and warned about, but not a claim about the code.

`main("require-ready")` below is the entry point a shell gate uses, and the mapping is deliberate and asserted:

    ready                      -> 0
    absent / unreachable / denied -> 77 with the reason and the fix on stderr
    a command that ran and failed -> NEVER 77

That last line is the one that makes 77 mean something. A gate that returns 77
for a genuine failure has converted a red into a shrug.
"""

import json
import os
import sys
import time

from rediacc_ci import proc

# `docker` has no interactive prompt of its own, but it does have two ways to make output unusable in a capture: a plugin's colour, and the CLI hint lines it appends to some commands. Both are switched off so a parsed value is the value.
NONINTERACTIVE = {
    "DOCKER_CLI_HINTS": "false",
    "NO_COLOR": "1",
    "CLICOLOR": "0",
}

# `docker info` against a dead engine "can sit for a long time" -- .ci/lib/setup.sh:573, which is why that site is one of the twelve `timeout(1)` calls in the tree. 30 matches the number it chose. Nothing here is unbounded.
DEFAULT_TIMEOUT = 30.0

# The repo's cannot-run code. Duplicated as a literal on purpose, exactly as shfmt.sh:60 and check-python-lint.sh:191 duplicate it: pool.ts:86-89 explains that shell gates cannot import a TypeScript constant, so the value is written where it is used with the reference beside it.
CANNOT_RUN_RC = 77
NOT_INSTALLED_RC = proc.SPAWN_FAILED_RC

# The four states, and the four failures they map to. Strings, not an Enum: these are printed into operator-facing messages and compared in tests.
STATE_ABSENT = "absent"
STATE_UNREACHABLE = "unreachable"
STATE_DENIED = "permission-denied"
STATE_READY = "ready"
STATE_UNKNOWN = "unknown"

FAILURE_ABSENT = STATE_ABSENT
FAILURE_UNREACHABLE = STATE_UNREACHABLE
FAILURE_DENIED = STATE_DENIED
FAILURE_TIMED_OUT = "timed-out"
FAILURE_FAILED = "failed"

# Every state in which the answer is "no verdict was reached". `docker frobnicate` is deliberately NOT here: the engine answered and the command was wrong, which is a finding.
CANNOT_RUN_STATES = frozenset({STATE_ABSENT, STATE_UNREACHABLE, STATE_DENIED, STATE_UNKNOWN})

# Matched case-insensitively against STDERR. The first entry is docker 29's current wording, captured verbatim on 2026-09-06; the second and third are the older phrasings, kept because a CI runner or a developer laptop may be on an older CLI and a classifier that only knows today's string silently degrades every one of those machines to FAILED.
_UNREACHABLE_MARKERS = (
    "failed to connect to the docker api",
    "cannot connect to the docker daemon",
    "is the docker daemon running",
    "error during connect",
    "the docker client must be run with elevated privileges",
)
# TESTED BEFORE the unreachable markers. A permission failure on the socket also says "cannot connect to the docker daemon socket", so an unreachable-first test would tell the operator to start an engine that is already running.
_DENIED_MARKERS = (
    "permission denied while trying to connect",
    "got permission denied",
)
# A reworded permission failure that this table has not seen still says these words, and a docker message that says them means the socket refused THIS USER. Kept as its own table rather than as an inline `if` so a test can empty it and show that the ordering above is load bearing: a heuristic hidden in a branch is one a control cannot reach, and an unreachable control is not a
# control.
_DENIED_WEAK_MARKERS = ("permission denied",)


class DockerError(RuntimeError):
    """A docker call that did not answer. Carries the evidence."""

    def __init__(self, argv: list[str], returncode: int, stderr: str, failure: str) -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.stderr = stderr
        self.failure = failure
        detail = stderr.strip().splitlines()
        first = detail[0] if detail else "(no stderr)"
        super().__init__(
            "%s exited %d [%s]: %s" % (" ".join(self.argv), returncode, failure, first)
        )


class DockerAbsentError(DockerError):
    """No `docker` on PATH. Never a verdict about anything."""


class DockerUnreachableError(DockerError):
    """The CLI ran and no engine answered. Also never a verdict."""


class DockerPermissionDeniedError(DockerError):
    """The engine is up and this user cannot talk to it.

    Its own class because the fix is neither "install docker" nor "start docker": `.ci/lib/local-common.sh:630-653` re-execs the whole run under `sg docker` for exactly this case, and reporting it as unreachable would send the operator to restart a healthy daemon.
    """


class DockerBadOutputError(DockerError):
    """docker exited 0 and the body was not usable. The `gh` module's TRAP 3, here."""


def _classify(returncode: int, stderr: str, *, timed_out: bool) -> str:
    """Which failure this is. Only ever called for a non-zero exit."""
    if timed_out:
        return FAILURE_TIMED_OUT
    if returncode == NOT_INSTALLED_RC:
        return FAILURE_ABSENT
    lowered = stderr.lower()
    if any(marker in lowered for marker in _DENIED_MARKERS):
        return FAILURE_DENIED
    if "docker" in lowered and any(m in lowered for m in _DENIED_WEAK_MARKERS):
        return FAILURE_DENIED
    if any(marker in lowered for marker in _UNREACHABLE_MARKERS):
        return FAILURE_UNREACHABLE
    return FAILURE_FAILED


_ERROR_CLASSES = {
    FAILURE_ABSENT: DockerAbsentError,
    FAILURE_UNREACHABLE: DockerUnreachableError,
    FAILURE_DENIED: DockerPermissionDeniedError,
}


class DockerResult:
    """What a docker call did, with the success check in front of the output.

    `.stdout` RAISES unless the call succeeded. MEASUREMENT 2 in the module docstring is the reason: a failing `docker info` prints a full client report, so the plain-attribute version of this class would hand a caller a healthy-looking document produced by a machine with no engine.
    """

    __slots__ = ("argv", "duration", "returncode", "stderr", "stdout_raw", "timed_out")

    def __init__(
        self,
        argv: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
        *,
        timed_out: bool = False,
        duration: float = 0.0,
    ) -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.stdout_raw = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.duration = duration

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return "DockerResult(argv=%r, returncode=%d, failure=%r, out=%d B, err=%d B)" % (
            self.argv,
            self.returncode,
            self.failure,
            len(self.stdout_raw),
            len(self.stderr),
        )

    @property
    def failure(self) -> str | None:
        if self.ok:
            return None
        return _classify(self.returncode, self.stderr, timed_out=self.timed_out)

    @property
    def cannot_run(self) -> bool:
        """Is this failure a "no verdict" rather than a finding?

        The single predicate a gate keys its exit code on. FAILED and TIMED_OUT are excluded: a command that reached the engine and failed is a result, and a timeout is a genuine breakage (`proc` maps it to 124 for the same reason).
        """
        return self.failure in (FAILURE_ABSENT, FAILURE_UNREACHABLE, FAILURE_DENIED)

    def error(self) -> DockerError:
        failure = self.failure
        if failure is None:
            raise ValueError("error() on a successful call: %r" % self)
        cls = _ERROR_CLASSES.get(failure, DockerError)
        return cls(self.argv, self.returncode, self.stderr, failure)

    @property
    def stdout(self) -> str:
        """The output -- or the classified exception. THE CHECK THAT CANNOT BE SKIPPED."""
        if not self.ok:
            raise self.error()
        return self.stdout_raw

    def lines(self) -> list[str]:
        """Non-empty output lines. [] means the call SUCCEEDED and printed nothing."""
        return [line for line in self.stdout.splitlines() if line.strip()]

    def value(self, what: str = "value") -> str:
        """One stripped scalar, and an empty one is refused.

        `docker info --format '{{.ServerVersion}}'` against a dead engine prints
        NOTHING and exits 1 (measured). The exit code catches that here; this refusal catches the version of it where a future docker exits 0 with an empty field, which is the same class of bug that put an empty signing key into a production build (docs/dev-environments.md:102-110).
        """
        text = self.stdout.strip()
        if not text:
            raise DockerBadOutputError(
                self.argv,
                self.returncode,
                "docker exited 0 but printed nothing where a %s was required" % what,
                FAILURE_FAILED,
            )
        return text

    def json(self) -> object:
        text = self.stdout
        try:
            return json.loads(text)
        except ValueError as exc:
            raise DockerBadOutputError(
                self.argv,
                self.returncode,
                "docker exited 0 and the body is not JSON (%s). First 200 bytes: %r"
                % (exc, text[:200]),
                FAILURE_FAILED,
            ) from exc

    def json_lines(self) -> list[dict]:
        """One JSON object PER LINE, which is what `--format '{{json .}}'` emits.

        NOT a JSON array. `docker ps --format '{{json .}}'` prints newline
        delimited objects, so `json.loads` over the whole body fails as soon as there are two containers -- and passes with zero or one, which is how that bug reaches production having been tested.
        """
        out = []
        for line in self.lines():
            try:
                parsed = json.loads(line)
            except ValueError as exc:
                raise DockerBadOutputError(
                    self.argv,
                    self.returncode,
                    "line is not JSON (%s): %r" % (exc, line[:200]),
                    FAILURE_FAILED,
                ) from exc
            if not isinstance(parsed, dict):
                raise DockerBadOutputError(
                    self.argv,
                    self.returncode,
                    "expected a JSON object per line, got %s" % type(parsed).__name__,
                    FAILURE_FAILED,
                )
            out.append(parsed)
        return out


def which_docker(env: dict[str, str] | None = None) -> str | None:
    """Absolute path of `docker`, or None. The ABSENT test, asked before any call."""
    return proc.which("docker", env)


def docker(
    args: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
    host: str | None = None,
    attempts: int = 1,
    sleep=time.sleep,
) -> DockerResult:
    """Run `docker <args>`, bounded. Never raises for a non-zero exit.

    `host` sets DOCKER_HOST for this call only, which is how every repo in this product is addressed: each one has its own daemon at `/var/run/rediacc/docker-<networkId>.sock`. Passing it here rather than exporting it means two repos can be queried from one process without either of them inheriting the other's socket.
    """
    environ = dict(os.environ if env is None else env)
    environ.update(NONINTERACTIVE)
    if host is not None:
        environ["DOCKER_HOST"] = host
    result = proc.retry_command(
        ["docker", *args],
        attempts=attempts,
        sleep=sleep,
        env=environ,
        timeout=timeout,
    )
    return DockerResult(
        result.argv,
        result.returncode,
        result.stdout,
        result.stderr,
        timed_out=result.timed_out,
        duration=result.duration,
    )


def client_version(env: dict[str, str] | None = None) -> str:
    """The CLI's own version string, e.g. "29.7.2". Works with no daemon.

    `docker --version`, NOT `docker version --format '{{.Client.Version}}'`. See
    MEASUREMENT 3: the second one prints the right answer and exits 1 when the daemon is down, so the only way to use it is to ignore the exit code, and a helper that has to ignore exit codes cannot be the one that teaches callers not to. `docker --version` contacts no daemon and exits 0 offline (measured 2026-09-06), so the status check survives.

    THE LINE IS PARSED AND THE PARSE IS CHECKED. "Docker version 29.7.2, build a7dcaa6" is prose, and a caller comparing prose against a version number gets a wrong answer rather than an error. An unparseable line raises instead of being handed back whole.
    """
    result = docker(["--version"], env=env, timeout=10)
    line = result.value("docker version line")
    marker = "version "
    index = line.lower().find(marker)
    token = line[index + len(marker) :].split(",")[0].strip() if index >= 0 else ""
    if not token or not token[0].isdigit():
        raise DockerBadOutputError(
            result.argv,
            result.returncode,
            "cannot read a version out of %r" % line,
            FAILURE_FAILED,
        )
    return token


def state(env: dict[str, str] | None = None, *, host: str | None = None) -> str:
    """Which of the four situations this machine is in. One probe, four answers.

    `docker version` rather than `docker info` as the probe, for two reasons. It is what `.ci/lib/local-common.sh:633`, `.ci/lib/devbox.sh:76` and `.ci/legacy/run-legacy.sh:766` already use, so this reports the same thing they act on; and `docker info` is the slower call, which matters when the engine is dead and the timeout is what you are waiting for.

    STATE_UNKNOWN is real and is not a synonym for unreachable: a timeout, or a stderr this module cannot classify, means the question was not answered. It is grouped into CANNOT_RUN_STATES because acting on an unanswered probe is the failure this whole module exists to prevent, but it is REPORTED separately so a message can say "I could not tell" instead of inventing a cause.
    """
    if which_docker(env) is None:
        return STATE_ABSENT
    result = docker(["version"], env=env, host=host, timeout=DEFAULT_TIMEOUT)
    if result.ok:
        return STATE_READY
    failure = result.failure
    if failure == FAILURE_ABSENT:
        return STATE_ABSENT
    if failure == FAILURE_DENIED:
        return STATE_DENIED
    if failure == FAILURE_UNREACHABLE:
        return STATE_UNREACHABLE
    return STATE_UNKNOWN


# The operator-facing next action for each state. Kept as data rather than as branches in a print, because check-python-lint.sh:170-180 records what a wrong one costs: a session that trusts an unusable message concludes the work cannot be done locally and ships it to CI instead.
_ADVICE = {
    STATE_ABSENT: (
        "docker is not on PATH.\n"
        "  install it:  ./run.sh setup      (uses renet's installer, the official repo)\n"
        "  or skip the work that needs it: CLI, www and test work do not."
    ),
    STATE_UNREACHABLE: (
        "the docker CLI is on PATH but no engine answered.\n"
        "  linux:  sudo systemctl start docker\n"
        "  wsl:    Docker Desktop > Settings > Resources > WSL Integration, and enable\n"
        "          this distro. The CLI shim exists without an engine, which is why\n"
        "          `command -v docker` succeeded (.ci/lib/setup.sh:565-571).\n"
        "  mac:    start Docker Desktop."
    ),
    STATE_DENIED: (
        "the docker engine is running and this user cannot talk to its socket.\n"
        "  this run only:  sg docker -c '<command>'\n"
        "  permanently:    sudo usermod -aG docker $USER, then log out and back in\n"
        "  the group is applied automatically by ./run.sh (.ci/lib/local-common.sh:630-653)."
    ),
    STATE_UNKNOWN: (
        "the docker probe did not answer and this module could not classify why.\n"
        "  run `docker version` by hand and read BOTH streams: the message is the\n"
        "  evidence, and it is the thing 2>/dev/null deletes."
    ),
}


def cannot_run_reason(env: dict[str, str] | None = None, *, host: str | None = None) -> str | None:
    """None when docker is usable; otherwise the sentence a gate should print.

    Deliberately returns None for READY rather than a boolean, so a caller writes
    `reason = cannot_run_reason(); if reason: ...` and has the text in hand at
    the moment it decides. Two calls -- one to ask, one to explain -- is how a gate ends up printing advice for a state it is no longer in.
    """
    current = state(env, host=host)
    if current == STATE_READY:
        return None
    return "%s: %s" % (current, _ADVICE.get(current, "unusable"))


def require_ready(env: dict[str, str] | None = None, *, host: str | None = None) -> None:
    """Raise the typed error unless docker is usable. For a library caller."""
    current = state(env, host=host)
    if current == STATE_READY:
        return
    argv = ["docker", "version"]
    message = _ADVICE.get(current, "docker is unusable")
    if current == STATE_ABSENT:
        raise DockerAbsentError(argv, NOT_INSTALLED_RC, message, FAILURE_ABSENT)
    if current == STATE_DENIED:
        raise DockerPermissionDeniedError(argv, 1, message, FAILURE_DENIED)
    if current == STATE_UNREACHABLE:
        raise DockerUnreachableError(argv, 1, message, FAILURE_UNREACHABLE)
    raise DockerError(argv, 1, message, FAILURE_FAILED)


def server_version(env: dict[str, str] | None = None, *, host: str | None = None) -> str:
    """The ENGINE's version. Raises when there is no engine; never "unknown".

    `.ci/lib/setup.sh:583` spells this `|| echo 'version unknown'`, which is right for a log line and wrong for anything a program then compares. Here the absence of an engine is an exception, so it cannot be compared against a version number by accident.
    """
    return docker(
        ["version", "--format", "{{.Server.Version}}"], env=env, host=host, timeout=15
    ).value("server version")


def containers(
    *,
    all_states: bool = False,
    env: dict[str, str] | None = None,
    host: str | None = None,
) -> list[dict]:
    """`docker ps` as dicts. RAISES when the engine cannot be asked; [] means none.

    The same rule as `ghx.pr_list`: there is no return value meaning "I could not ask". `scripts/dev/worktree.sh:201-202` guards this call with two `return 1`s that make an unreachable daemon and an empty container list the same answer, which is safe there only because the caller's next step is a no-op either way.
    """
    args = ["ps", "--format", "{{json .}}"]
    if all_states:
        args.append("--all")
    return docker(args, env=env, host=host).json_lines()


def container_names(
    *,
    all_states: bool = False,
    env: dict[str, str] | None = None,
    host: str | None = None,
) -> list[str]:
    """Sorted container names. Raises when the engine cannot be asked."""
    return sorted(
        str(row["Names"])
        for row in containers(all_states=all_states, env=env, host=host)
        if row.get("Names")
    )


# --------------------------------------------------------------------------- argv dispatch -- the surface a shell gate uses for its 77 ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    """Verbs for shell callers. `require-ready` is the one that produces 77.

    THE MAPPING IS THE CONTRACT AND IT IS ASSERTED IN THE TESTS:

        ready                            -> 0
        absent, unreachable, denied      -> 77, reason and fix on STDERR
        unknown                          -> 77, saying it could not classify
        a command that ran and failed    -> 1, because that IS a verdict

    `state` prints one word on stdout and always exits 0, for a caller that wants to branch in shell without a subshell full of pattern matching.
    """
    if not argv:
        print("usage: python3 -m rediacc_ci.core.dockerx <verb> [args]", file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]
    host = rest[0] if rest else None

    if verb == "state":
        print(state(host=host))
        return 0
    if verb == "client-version":
        try:
            print(client_version())
        except DockerError as exc:
            print("docker: %s" % exc, file=sys.stderr)
            return 1
        return 0
    if verb == "require-ready":
        reason = cannot_run_reason(host=host)
        if reason is None:
            return 0
        print("error: %s" % reason, file=sys.stderr)
        print(
            "  NOT skipping: exit %d means NO VERDICT was reached, which the ci-runner\n"
            "  classifies as BLOCKED. A check that cannot run is a check that cannot\n"
            "  fail, and reporting 0 here would say the thing passed." % CANNOT_RUN_RC,
            file=sys.stderr,
        )
        return CANNOT_RUN_RC
    if verb == "server-version":
        try:
            print(server_version(host=host))
        except DockerError as exc:
            print("docker: %s" % exc, file=sys.stderr)
            # 77 ONLY for the three cannot-run states. A malformed answer from a live engine is a finding and exits 1, which is the distinction that keeps 77 meaningful.
            return CANNOT_RUN_RC if exc.failure in CANNOT_RUN_STATES else 1
        return 0

    print("unknown verb: %s" % verb, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


__all__ = [
    "CANNOT_RUN_RC",
    "CANNOT_RUN_STATES",
    "DEFAULT_TIMEOUT",
    "FAILURE_ABSENT",
    "FAILURE_DENIED",
    "FAILURE_FAILED",
    "FAILURE_TIMED_OUT",
    "FAILURE_UNREACHABLE",
    "NONINTERACTIVE",
    "NOT_INSTALLED_RC",
    "STATE_ABSENT",
    "STATE_DENIED",
    "STATE_READY",
    "STATE_UNKNOWN",
    "STATE_UNREACHABLE",
    "DockerAbsentError",
    "DockerBadOutputError",
    "DockerError",
    "DockerPermissionDeniedError",
    "DockerResult",
    "DockerUnreachableError",
    "cannot_run_reason",
    "client_version",
    "container_names",
    "containers",
    "docker",
    "main",
    "require_ready",
    "server_version",
    "state",
    "which_docker",
]
