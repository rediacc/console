"""`./run.sh setup` and `./run.sh setup --check`, ported from bash.

WHAT MOVED. `setup()` at `.ci/legacy/run-legacy.sh:543-715` (173 lines) and
`setup_check()` at `:719-817` (99 lines), plus the nine functions in
`.ci/lib/setup.sh` (845 lines) they drive. 1,117 lines of bash, measured
2026-09-09 with `wc -l` and `sed -n`.

WHAT DID NOT MOVE, AND WHY THAT IS THE RIGHT SCOPE. Six of the fifteen phases
live in `.ci/lib/local-common.sh` and `.ci/lib/devbox.sh`, which four other
verbs also call. They are reached through `bridge.py`, so the same bytes run;
see that module's header. This file owns the ORCHESTRATION -- which phase, in
what order, fatal or not -- and `host.py` owns the nine that were only ever
`setup`'s.

THE TWO CONTRACTS THIS FILE IS JUDGED ON.

  IDEMPOTENCE. `.ci/lib/setup.sh:17`: "EVERY FUNCTION HERE IS IDEMPOTENT and
  returns 0 early when its condition is already met ... a second run must do no
  work." Enforced per phase in `host.py` and driven twice per phase by
  `shadow_driver.py`.

  `--check` MUTATES NOTHING. `check()` below runs no installer, writes no file
  and starts no container. `.ci/rediacc_ci/quality/setup_idempotency.py` check B
  proves it the only way it can be proved: it snapshots `git status --porcelain`,
  runs the real `./run.sh setup --check`, and snapshots again.

  AND THE THIRD, WHICH IS THE ONE THAT WENT WRONG ONCE. Every phase `setup()`
  PERFORMS must be REPORTED by `--check`. `.ci/legacy/run-legacy.sh:738-744`
  records the day it did not: "it said '2 item(s) would be acted on' while setup
  would also have installed gh and written a git identity". A phase that acts and
  is not reported makes the count a lie, so `CHECK_ROWS` below is a table and
  `phases.PHASES` is a table, and this package's tests compare them.
"""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.setup import bridge, host, phases
from rediacc_ci.setup.ctx import Ctx

if TYPE_CHECKING:  # pragma: no cover - `pathlib` is only ever an annotation here
    import pathlib

# `--help` for this verb, byte for byte the heredoc at `.ci/legacy/run-legacy.sh:564-574`. A person who has memorised the old output should see no diff, and a gate test can compare the two while both exist.
HELP = """Usage: ./run.sh setup [OPTIONS]

  --check      Report what is missing and change nothing
  --pull       Re-pull the devcontainer image even if present
  --no-start   Prepare the host and image, but do not create the container
  --help       Show this help

Related: ./run.sh devbox [up|status|stop|remove|shell|logs]"""

# `return 2` for an unknown option, `.ci/legacy/run-legacy.sh:578`. Named because 2 is this repository's usage-error code everywhere else too (`rediacc_ci/__main__.py:55`, `core/env.py`, `core/ports.py`).
EXIT_USAGE = 2

# The seven questions `setup_check()` asks `devbox.sh`, as ONE shell program.
# See `_devbox_facts` for why they are batched; held here as a constant so the
# program is readable next to the bash it mirrors and nothing can interpolate into it.
DEVBOX_FACTS = """printf "worktree=%s\\n" "$(devbox_worktree 2>/dev/null || echo "")"
if devbox_image_present; then printf "image=1\\n"; else printf "image=0\\n"; fi
printf "base_port=%s\\n" "$(devbox_base_port 2>/dev/null || echo "")"
if devbox_container_running; then printf "running=1\\n"; else printf "running=0\\n"; fi
printf "container_id=%s\\n" "$(devbox_container_id 2>/dev/null || echo "")"
printf "container_name=%s\\n" "$(devbox_container_name 2>/dev/null || echo "")"
"""


@dataclass(frozen=True)
class Options:
    """Parsed `setup` flags. `error` is set when parsing itself failed."""

    check: bool = False
    pull: bool = False
    start: bool = True
    help: bool = False
    error: str = ""


def parse_args(argv: list[str]) -> Options:
    """The `while [[ $# -gt 0 ]]` loop at `.ci/legacy/run-legacy.sh:549-581`.

    ORDER-INSENSITIVE AND REPEAT-TOLERANT, exactly like the loop: `--check
    --check` is `--check`, and `--pull --check` is the same as `--check --pull`.
    The bash returns 0 immediately on `--help` without reading the rest, so a
    `--help` anywhere wins over a later unknown option; that is carried.
    """
    check = pull = False
    start = True
    for arg in argv:
        if arg == "--check":
            check = True
        elif arg == "--pull":
            pull = True
        elif arg == "--no-start":
            start = False
        elif arg in ("--help", "-h"):
            return Options(check=check, pull=pull, start=start, help=True)
        else:
            return Options(error=arg)
    return Options(check=check, pull=pull, start=start)


# --------------------------------------------------------------------------- the docker-group re-exec ---------------------------------------------------------------------------


def reexec_with_docker_group(root: pathlib.Path, argv: list[str], env: dict[str, str]) -> None:
    """`reexec_with_docker_group`, `.ci/lib/local-common.sh:630`. Returns or EXECS.

    After `usermod -aG docker` the current shell keeps the group set it was
    created with, so `docker ps` keeps failing until the operator logs out. `sg`
    runs a command with a group the user is entitled to but has not activated,
    so re-executing ourselves under it fixes the problem in place.

    MEMBERSHIP IS READ FROM `getent group docker`, NOT FROM `id -nG`, and the
    bash's comment at `:626-628` is the reason: "id reports the CURRENT process's
    groups, which is exactly the stale information we are working around, so it
    would answer 'no' in the one case that matters".

    PORTED RATHER THAN BRIDGED, because it is the one call that cannot be
    bridged: it must `exec`, and a bridged `exec` would replace the bash child
    and leave this process waiting on it.
    """
    if env.get("REDIACC_DOCKER_GROUP_REEXEC"):
        return
    probe = Ctx(root=root, env=env)
    if probe.run(["docker", "version"], timeout=30).rc == 0:
        return
    if not probe.which("docker") or not probe.which("sg"):
        return
    group = probe.run(["getent", "group", "docker"], timeout=10)
    if group.rc != 0:
        return
    # The members field is the 4th colon-separated column of the group line.
    fields = group.out.strip().split(":")
    members = fields[3] if len(fields) > 3 else ""
    user = env.get("USER", "")
    if not user or user not in [m for m in members.split(",") if m]:
        return
    # Prove it actually helps before re-executing, so a broken daemon does not send us round a pointless loop.
    if probe.run(["sg", "docker", "-c", "docker version"], timeout=30).rc != 0:
        return

    probe.info("Applying your docker group membership to this run (no logout needed)")
    os.environ["REDIACC_DOCKER_GROUP_REEXEC"] = "1"
    command = shlex.join([str(root / "run.sh"), "setup", *argv])
    os.execvp("sg", ["sg", "docker", "-c", command])  # noqa: S606


# --------------------------------------------------------------------------- the report ---------------------------------------------------------------------------


def _devbox_facts(root: pathlib.Path, env: dict[str, str]) -> dict[str, str]:
    """Everything `setup_check()` asks `devbox.sh`, in ONE bridged shell.

    SEVEN QUESTIONS, ONE PROCESS. The bash asks each of them with its own
    function call inside one already-sourced shell; a Python port that bridged
    each one separately would pay the whole prelude seven times, which on this
    host is about 0.2s each. Behaviour is identical, so this is the one place the
    port is deliberately not a line-for-line transcription.

    EVERY VALUE IS A STRING AND AN ABSENT ONE IS "", never a raised error: this
    is a REPORT, and a report that dies because one row could not be computed is
    worse than a report with one row missing. `devbox_base_port` in particular is
    allowed to fail; see `_port_block_row`.
    """
    _, out = bridge.capture(DEVBOX_FACTS, root, env)
    facts: dict[str, str] = {}
    for line in out.split("\n"):
        if "=" in line:
            key, _, value = line.partition("=")
            facts[key] = value
    return facts


def _port_block_row(facts: dict[str, str], constants: dict[str, str]) -> str:
    """The `port block` row. NEVER counted against `pending`.

    THE `'?'` FALLBACK WAS A LANDMINE and the bash records it at
    `.ci/legacy/run-legacy.sh:783-789`: run.sh is `set -euo pipefail` and
    `$(('?' + N))` is an arithmetic syntax error, so the printf never ran and
    `setup_check` ABORTED, surfacing as a gate failure that named the wrong
    cause entirely. Python has no such trap here, and the guard is kept anyway:
    a non-numeric answer takes the "unavailable" arm, which is what the bash
    MEANT to do.
    """
    base = facts.get("base_port", "")
    if base.isdigit():
        block = int(constants.get("DEVBOX_PORT_BLOCK", "0") or 0)
        return "  port block  %s-%s" % (base, int(base) + block - 1)
    return "  port block  unavailable (no free block in %s-%s)" % (
        constants.get("DEVBOX_PORT_RANGE_START", ""),
        constants.get("DEVBOX_PORT_RANGE_END", ""),
    )


def check(ctx: Ctx, constants: dict[str, str]) -> int:
    """`setup_check()`, `.ci/legacy/run-legacy.sh:719`. 0 nothing to do, 1 pending.

    REPORT ONLY. Nothing here writes, installs, pulls or starts anything, which
    is the contract `.ci/rediacc_ci/quality/setup_idempotency.py` check B drives
    against the real command.

    EVERY ROW GOES TO STDOUT and every heading to stderr, because that is where
    the bash's `printf` and `log_step` respectively put them. It reads like a
    detail and it is not: `check:ci-setup-idempotency` greps this output.
    """
    pending = 0
    facts = _devbox_facts(ctx.root, ctx.env)

    ctx.step("Setup status for %s" % facts.get("worktree", ""))
    ctx.say()

    if ctx.which("node"):
        ctx.say("  node        %s" % ctx.run(["node", "--version"], timeout=10).out.strip())
    else:
        ctx.say(
            "  node        MISSING (install Node >= %s)" % constants.get("NODE_VERSION_MIN", "")
        )
        pending += 1

    # NOT COUNTED. Go is only installed when docker is missing, so a machine without it is not a machine with work pending.
    if ctx.which("go"):
        raw = ctx.run(["go", "version"], timeout=30).out.split()
        ctx.say("  go          %s" % (raw[2] if len(raw) > 2 else ""))
    else:
        ctx.say("  go          absent (setup installs it only if docker is missing)")

    if ctx.which("gh"):
        first = ctx.run(["gh", "--version"], timeout=30).first_line().split()
        ctx.say("  gh          %s" % (first[2] if len(first) > 2 else ""))
    else:
        ctx.say("  gh          MISSING (setup installs it; the PR guards fail closed without it)")
        pending += 1

    if ctx.which("cc") or ctx.which("gcc"):
        # `(cc --version 2>/dev/null || gcc --version) | head -1 |
        #  awk '{print $1, $NF}'` -- the first and LAST field of the banner.
        banner = ctx.run(["cc", "--version"], timeout=10)
        if banner.rc != 0 or not banner.out.strip():
            banner = ctx.run(["gcc", "--version"], timeout=10)
        words = banner.first_line().split()
        ctx.say("  compiler    %s" % ("%s %s" % (words[0], words[-1]) if words else ""))
    else:
        ctx.say("  compiler    MISSING (setup installs build-essential; install:natives needs it)")
        pending += 1

    email = host._git_global(ctx, "user.email")
    if email:
        # NOTE THE COLUMN. The bash writes `' git identity %s\n'`, two spaces narrower than every other row because the label is two characters
        # longer. It looks like a typo and it is the existing output; changing it
        # would be a diff in a gate's input for no reason.
        ctx.say("  git identity %s" % email)
    else:
        ctx.say("  git identity UNSET (setup asks for it once, then remembers)")
        pending += 1

    if ctx.run(["docker", "version"], timeout=30).rc == 0:
        version = ctx.run(["docker", "--version"], timeout=15).out.strip()
        ctx.say("  docker      %s" % version.split(",", 1)[0])
    elif ctx.which("docker"):
        ctx.say(
            "  docker      installed but NOT usable as %s (log out/in, or newgrp docker)"
            % ctx.env.get("USER", "")
        )
        pending += 1
    else:
        ctx.say(
            "  docker      MISSING (setup installs it via renet install-docker "
            "--source=docker-repo)"
        )
        pending += 1

    image = constants.get("DEVBOX_IMAGE", "")
    if facts.get("image") == "1":
        ctx.say("  image       present (%s)" % image)
    else:
        ctx.say("  image       MISSING (%s)" % image)
        pending += 1

    ctx.say(_port_block_row(facts, constants))

    if facts.get("running") == "1":
        ctx.say("  devbox      running (%s)" % facts.get("container_name", ""))
    elif facts.get("container_id", ""):
        ctx.say("  devbox      stopped (%s)" % facts.get("container_name", ""))
        pending += 1
    else:
        ctx.say("  devbox      not created")
        pending += 1

    ctx.say()
    if pending == 0:
        ctx.info("Nothing to do; ./run.sh setup would be a no-op")
        bridge.call("devbox_status", ctx.root, ctx.env)
        return 0
    ctx.warn("%d item(s) would be acted on by ./run.sh setup" % pending)
    return 1


# --------------------------------------------------------------------------- the verb ---------------------------------------------------------------------------


def run_setup(ctx: Ctx, options: Options, constants: dict[str, str]) -> int:
    """`setup()`'s body after argument parsing. `.ci/legacy/run-legacy.sh:591`.

    THE PHASE ORDER IS `phases.PHASES` AND NOTHING ELSE. This function is written
    as a straight line rather than a loop over the table on purpose: each phase's
    failure message is different, three of them are conditional, and a loop with a
    per-phase callback table would be the same code with an indirection that makes
    the order harder to read, not easier. `phases.plan()` is the machine-readable
    statement of the same order and the tests compare the two.
    """
    # THE CONDITIONALS COME FROM `phases.plan`, NOT FROM A SECOND COPY HERE. `.gitmodules` and the credential-drift pair were written out twice while this function was first drafted, which is two predicates that can disagree about the same question: the table would then describe a run nobody performs, and `check:ci-setup-port-parity` A1 would still pass because it compares NAMES
    # and not conditions. One evaluation, consulted twice.
    selected = set(phases.plan(ctx.root, ctx.env, start=options.start))

    ctx.step("Rediacc console setup")
    ctx.say()

    if host.node_toolchain(ctx) != 0:
        return 1
    # NO `:-22.0.0` DEFAULT. `bridge.constants` refuses an empty floor rather
    # than substituting a looser one; see `.ci/lib/setup.sh:44-51` for the day
    # that mattered.
    if bridge.call('check_node_version "$NODE_VERSION_MIN"', ctx.root, ctx.env) != 0:
        return 1
    ctx.say()

    # Before npm install: install:natives hard-requires a compiler.
    if host.system_tools(ctx) != 0:
        return 1
    ctx.say()

    # SUBMODULES BEFORE THE FIRST PHASE THAT READS ONE, and `setup_go_toolchain` below is that phase: it reads `private/renet/go.mod`. Getting this edge wrong resurrects "Cannot determine the required Go version" on a fresh clone, a message that never mentions submodules. `check:ci-setup-idempotency` check G is the gate that refuses it.
    if "init-submodules.sh" in selected:
        ctx.step("Initializing submodules")
        # Best effort, `|| true`: a developer without access to every private submodule should still get a working devbox.
        ctx.run(
            ["bash", str(ctx.root / ".devcontainer" / "init-submodules.sh"), "--quiet"],
            timeout=1800,
        )
        ctx.say()

    if host.go_toolchain(ctx) != 0:
        return 1
    ctx.say()

    if host.gh_cli(ctx) != 0:
        return 1
    ctx.say()

    # KEPT, not replaced by `system_tools`. `ensure_host_tools` also checks zstd, curl and git, which none of the installers cover, so deleting it would quietly narrow the preflight while looking like a simplification.
    if bridge.call("ensure_host_tools", ctx.root, ctx.env) != 0:
        return 1
    bridge.call("ensure_bashcov_sup", ctx.root, ctx.env)
    ctx.say()

    ctx.step("Git and GitHub account")
    # NOT FATAL, and the bash is the same: `setup_git_identity` is called without `|| return 1` while the credential check on the next line has it.
    host.git_identity(ctx)
    if host.git_credentials(ctx) != 0:
        return 1
    ctx.say()

    # Dependencies THROUGH ensure_deps, never a raw npm install: it hashes
    # package.json, package-lock.json and .npmrc and skips on a match.
    bridge.call("ensure_deps", ctx.root, ctx.env)

    if "check:env-credential-drift" in selected:
        _credential_drift(ctx)

    if bridge.call("ensure_docker_installed", ctx.root, ctx.env) != 0:
        ctx.error("Docker could not be prepared; cannot continue")
        return 1

    if bridge.call('devbox_ensure_image "%s"' % _bool_word(options.pull), ctx.root, ctx.env) != 0:
        ctx.error("Could not obtain %s" % constants.get("DEVBOX_IMAGE", ""))
        return 1

    if "devbox_up" not in selected:
        ctx.info("Host prepared. Create the container with: ./run.sh devbox up")
        return 0

    if bridge.call("devbox_up", ctx.root, ctx.env) != 0:
        return 1

    # THE URLS ARE THE DELIVERABLE. `devbox_up` has already printed the probed route table, so these two lines are the bookmark, not the report.
    _, url = bridge.capture("devbox_url", ctx.root, ctx.env)
    _, term = bridge.capture("devbox_url term", ctx.root, ctx.env)
    ctx.say()
    ctx.info("Setup complete.")
    ctx.info("  VS Code:  %s" % url.strip())
    ctx.info("  Terminal: %s   tmux in the browser" % term.strip())
    ctx.say()
    ctx.info("Everything below runs INSIDE the devbox:")
    ctx.info("  ./run.sh account dev    start the account dev stack")
    ctx.info("  ./run.sh account db     browse the dev database")
    ctx.info("  ./run.sh devbox shell   a shell in the container")
    return 0


def _bool_word(value: bool) -> str:
    """`true` / `false`, because `devbox_ensure_image` takes the bash spelling."""
    return "true" if value else "false"


def _credential_drift(ctx: Ctx) -> None:
    """The advisory drift report. `.ci/legacy/run-legacy.sh:672-684`. Never fatal.

    ADVISORY BY DECISION, not by omission: "blocking a developer's bootstrap on a
    credential only an ops owner can rotate strands the one person who cannot fix
    it". It compares IDENTIFIERS against `rotation-manifest.json`, never secrets,
    and never contacts a provider.
    """
    if ctx.env.get("SKIP_ENV_DRIFT_CHECK") == "1":
        return
    if not (ctx.root / "private" / "account" / ".env").is_file():
        return
    ctx.say()
    ctx.step("Credential drift check")
    if ctx.run(["npm", "run", "--silent", "check:env-credential-drift"], timeout=600).rc != 0:
        ctx.warn("A credential in private/account/.env is not in the rotation manifest.")
        ctx.warn("ROTATION IS AN OPS TASK, NOT A DEVELOPER ONE, so this does not stop setup.")
        ctx.warn("It surfaces later as an unrelated failure (a 403 from an API days on),")
        ctx.warn("and the developer who hits that is not the person who can fix it.")
        ctx.warn("Whoever owns rotation: ./run.sh rotation rotate <slug>")


def main(argv: list[str] | None = None) -> int:
    """The verb entry point. `argv` is everything after `setup`.

    THE RE-EXEC HAPPENS FIRST, exactly as `.ci/legacy/run-legacy.sh:547` does it,
    and before argument parsing: a bad flag under a stale docker group should
    still be reported by the process that can see docker, not by the one that
    cannot.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    root = paths.repo_root()
    env = dict(os.environ)

    reexec_with_docker_group(root, args, env)

    options = parse_args(args)
    # NAMED `printer`, NOT `logger`, and the reason is a lint rule rather than a style: ruff's flake8-logging family (G002, G010) recognises a `logger` binding as a STDLIB logging.Logger and objects to `%` formatting and to a `warn` method. `rediacc_ci.log.Logger` is neither of those things, and the honest fix is to stop calling it by the stdlib's name.
    printer = log.Logger()
    if options.error:
        printer.emit("error", "Unknown option for setup: %s" % options.error)
        return EXIT_USAGE
    if options.help:
        print(HELP)
        return 0

    ctx = Ctx(root=root, env=env, stdin_tty=sys.stdin.isatty(), logger=printer)
    try:
        constants = bridge.constants(root, env)
    except bridge.BridgeError as exc:
        # A HARNESS FAULT, NAMED AS ONE. Without this the first symptom is an empty Node floor deep inside `host.node_toolchain`, which reports the wrong subject entirely.
        printer.emit("error", str(exc))
        return 1
    # The floor and the major reach `host.py` through the env, which is how the bash passes them too: `constants.sh` exports them and the functions read `$NODE_VERSION_MIN`. One mechanism, not two.
    env.update(constants)

    if options.check:
        return check(ctx, constants)
    return run_setup(ctx, options, constants)


if __name__ == "__main__":
    raise SystemExit(main())
