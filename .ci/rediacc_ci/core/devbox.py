"""`.ci/lib/devbox.sh`, ported function for function: all fifty-five of them.

PORTED FROM `.ci/lib/devbox.sh` (1606 lines, 54 functions).
The twin still exists, is untouched by this file, and is still sourced at `.ci/legacy/run-legacy.sh:456`, `.ci/rediacc_ci/setup/bridge.py:35` (inside the bridged `bash -c` prelude), `.ci/rediacc_ci/setup/shadow_driver.py:136`, `.ci/rediacc_ci/dev/shadow_driver.py:140` and `.ci/lib/account.sh:1090`. Those five are the real `source` sites; nothing is cut over here.
This is a pre-cutover port on the same sequencing every other lib in this campaign used, and `.ci/rediacc_ci/core/local_common.py` is the worked precedent: its twin `.ci/lib/local-common.sh` is still sourced at five sites while the port carries a K=5 ledger.

--------------------------------------------------------------------------
WHAT IS HERE
--------------------------------------------------------------------------
EVERY FUNCTION THE TWIN DEFINES HAS A COUNTERPART, in two shapes.

  THE THREE PURE ONES are module-level functions, exactly as the first slice (2026-09-23) shipped them: `slugify` (`devbox_slugify:186`), `slug_drift` (`devbox_slug_drift:242`) and `route_label` (`devbox_route_label:902`). Their whole answer is computation over their own arguments, and they stay importable without constructing anything.

  THE OTHER FIFTY-ONE are methods of `Devbox`, one per function, named by the function's name minus its `devbox_` / `_devbox_` prefix: `Devbox.worktree` is `devbox_worktree`, `Devbox.bind_if_present` is `_devbox_bind_if_present`, `Devbox.exec` is `devbox_exec`.
  `Devbox` also carries the three pure functions as printing methods, so a caller (and the differential driver) can reach all fifty-five through one surface, `Devbox.invoke("<bash name>", argv)`, which binds positional arguments the way bash does.

EACH METHOD TAKES ITS ARGUMENTS AS BASH DOES, as strings in `*argv`, and RETURNS AN EXIT STATUS. What the function prints goes to the instance's `stdout` and `stderr` streams, never to a return value, because every caller of the twin reads a function's answer by capturing what it PRINTED (`d="$(devbox_docker)"`) and its verdict by its STATUS (`devbox_container_running || ...`).
A port that returned values instead would have to restate, at every call site, which of the two channels the twin's caller really read.

--------------------------------------------------------------------------
THE TECHNIQUE THAT MAKES A SIDE-EFFECTING PORT COMPARABLE
--------------------------------------------------------------------------
The first slice refused the thirty-nine for want of a comparison technique, and the technique this port is licensed by is the STUB-FARM TRANSCRIPT DIFFERENTIAL `rediacc_ci.core.devbox_shadow_driver` runs.
Both sides run with a PATH whose first entry is a directory of stubs for every external that is not safe or not deterministic to run for real (`docker`, `sudo`, `curl`, `sleep`, `getent`, `stat`, `ss`). Each stub appends its argv to a transcript and answers from a scripted table.
`git` runs for real against a fixture repository, and `python3 -m rediacc_ci.core.ports` runs for real (its own `ss` probe lands in the stub farm too).
THE PORT THEREFORE ISSUES THE SAME EXTERNAL CALLS, IN THE SAME ORDER, WITH THE SAME ARGV, AS THE TWIN. That is a stronger constraint than "the same answer", and it is why several methods below look redundant: `devbox_up` asks `docker version` a dozen times because every helper it calls runs `d="$(devbox_docker)"` again, and a port that cached the answer would issue fewer calls and diverge on the transcript.
The redundancy is the twin's, reproduced on purpose, and the transcript is what proves each call is still there.

Externals the stub farm does NOT cover are reimplemented rather than shelled out, where the reimplementation is a few lines of byte handling: `basename`, `head -1`, `cut -d: -f3`, `tr`, the `sed` expressions, `grep -Fx`, `id -u`, `pwd -P`, and the `cat >file` heredoc. Their effect is observed (the answer, the state file's bytes) even though their call is not.
Two are shelled out anyway: `rm -f` in `devbox_remove`, because its failure message belongs to the tool, and `git`, because the fixture repository is real and a reimplemented `rev-parse` would compare the port against itself.

--------------------------------------------------------------------------
THE SHELL SEMANTICS THE PORT MODELS, AND WHY EACH ONE IS OBSERVABLE
--------------------------------------------------------------------------
Every sourcer runs this library under `set -euo pipefail`. Those three flags are not background noise here: they decide several of the twin's observable outcomes, so the port models them explicitly rather than approximating them.

  ERREXIT, WITH ITS SUPPRESSION RULES. `Devbox.errexit` is True at the top of a call, as it is under the driver's `( set -e; "$@" )` and under `run-legacy.sh`'s own `set -e`. A failing command in statement position raises `ShellExit` through `checked()`.
  A function called as a CONDITION (`if f`, `f || x`, `! f`) runs with errexit OFF for its whole body, however deeply it nests, which is `cond()`. A COMMAND SUBSTITUTION does not inherit errexit at all (bash does not set `inherit_errexit` here), which is `sub()`: the function inside it runs to completion and only its final status comes back to the assignment, where errexit judges it.

  PIPEFAIL. A pipeline's status is its rightmost non-zero member. That is what turns `getent group docker | cut -d: -f3` into a death on a host with no docker group (Rule T fix D1 below), and what makes `cid="$(devbox_container_id)"` carry `docker ps`'s failure through `head -1`.

  NOUNSET. `local x="$1"` with no first argument prints `$1: unbound variable` and ends the shell with status 1, whatever the errexit context. `_req()` raises that; the three functions whose bodies read a bare positional (`devbox_state_write`, `devbox_state_get`, `_devbox_bind_if_present`) are the new ones this applies to.

  COMMAND SUBSTITUTION STRIPS EVERY TRAILING NEWLINE and nothing else, and a bare `while read -r x` DROPS a final line with no newline. Both are reproduced wherever the twin relies on them, and the second one is a defect (twin defect 3).

  `log_*` IS `echo -e`. `.ci/scripts/lib/common.sh:35-54` writes every log line with `echo -e`, which interprets backslash escapes IN THE MESSAGE. `rediacc_ci.log` deliberately does not, and for most ports that is the right call; here the messages carry data the twin does not control (a docker label, a worktree path), so the port prints them verbatim: Rule T fix D4.

--------------------------------------------------------------------------
RULE T: ELEVEN TWIN DEFECTS FIXED (PLAN-retire-bash-oracles, task B4)
--------------------------------------------------------------------------
`.ci/lib/*.sh` is not edited by a port, so each of these is an INTENTIONAL DELTA: the twin still has the defect, `test_core_devbox.py` pins the twin's behaviour against the live twin (`SCENARIO_CLAIMS`) and the port's in its `test_delta_*` cases, and the live differential leaves exactly the labels in `DELTA_LABELS` out of its comparison.

  D1. `devbox_up` DIED SILENTLY ON A HOST WITH NO `docker` GROUP (`getent group docker | cut -d: -f3` under pipefail, so getent's status 2 reached errexit). It warns, passes no `--group-add` and carries on: the `${docker_gid:+...}` guards were written for exactly that.
  D2. `devbox_identity_ok` SUCCEEDED WHEN THE DEVBOX WAS NOT RUNNING (`|| true` swallowed the refusal). It fails with a message.
  D3. `devbox_slug_conflicts` DROPPED A FINAL `docker ps` LINE WITH NO NEWLINE (a bare `while read -r cid`). Every line is read.
  D4. `log_*` INTERPRETED BACKSLASHES IN DATA (`echo -e`): a worktree label `/x\\ty` printed a TAB and `\\c` swallowed the rest of the line. Messages print verbatim, and the whole escape table (`echo_e`) is gone with the defect.
  D5. `devbox_exec` WITH NO ARGUMENT RAN `bash -lc "'' "`. It is refused with status 2.
  D6. A ZERO-PADDED `base_port` WAS OCTAL (`$((base_port + 5))`), moving every route to a port nothing listens on. `decimal()` reads it as decimal, for the ready-timing variables too.
  D7. `docker ps` FAILING ENDED A DIRECTLY CALLED FUNCTION SILENTLY with docker's status (`./run.sh devbox stop` printed nothing). It ends with the same status and says "docker ps failed". A caller that reaches it through a command substitution survives, as before.
  D9. `devbox_up`'s "Starting existing devbox container" PATH DIED ON A FAILED `docker start` WITH NO MESSAGE. It says "Could not start the existing devbox container" and returns docker's status.
  D10. THE BASENAME FALLBACK HOSTNAME DEPENDED ON THE CALLER'S LOCALE (`tr` and `sed` without the `LC_ALL=C` its sibling forces). One checkout, one hostname: the C-locale rule.
  D11. `devbox_state_get` INTERPOLATED ITS KEY INTO A `sed` REGULAR EXPRESSION (`base.port` matched `base_port=`). The key is a literal, and so is the slug label key.
  D8 was retired earlier in the twin itself (`devbox_status` dying on a failed label inspect); the labels are fetched once by `devbox_container_labels`.

--------------------------------------------------------------------------
WHAT THIS PORT DOES NOT CLAIM, stated rather than left to a reader
--------------------------------------------------------------------------
  THE TTY ARMS OF `devbox_exec`. `-i` and `-t` depend on whether fd 0 and fd 1 are terminals; the differential runs both sides with stdin on `/dev/null` and stdout on a capture file, so only the both-false arm is compared. The two tty arms are ported line for line and covered by in-process unit cases in `test_core_devbox.py`, not by the ledger.
  THE HOST-FACT ARMS OF `devbox_up`. `[ -e /dev/kvm ]`, `[ -e /dev/net/tun ]` and `[[ -S /var/run/docker.sock ]]` read the real host. Both sides read the same host, so the arm the host takes is compared and the other arm of each is not; on the recording machine all three exist.
  ARITHMETIC ON A `base_port` THAT IS NOT A NUMBER. `bash_int()` covers decimal, octal and hex; anything else (a variable name, which shell arithmetic would dereference, or `08`, which it rejects) raises `DevboxError` rather than guessing.
  THAT THE CONTAINER THESE ARGV DESCRIBE REALLY SERVES. The stub farm proves the argv; `.ci/rediacc_ci/tests/gates/test_gate_devbox_slug.py` names the real-proxy claim as its blind spot 1 for the same reason.

--------------------------------------------------------------------------
THE PURE THREE: WHAT THE FIRST SLICE MEASURED, KEPT
--------------------------------------------------------------------------
All three were run against the live twin before any of them was written, under `LC_ALL=C` and again under `LC_ALL=C.utf8`, with the same corpus and the same answers both times. The whole environment dependency of the three is the presence of `tr` and `sed` on PATH, and the sourcing shell's `set -u`.
Measured 2026-09-23 on this machine: `tr` and `od` are **uutils coreutils 0.8.0**, `sed` is **GNU sed 4.9**, `bash` is **5.3.9**. The differential licence recorded for this port is equivalence against that tool set.
`tr` and `sed` are REIMPLEMENTED rather than shelled out: a port that piped the twin's own pipeline would be the same program, and its differential would prove nothing.

THE PURE THREE: ONE DEFECT FIXED (P3), SIX BEHAVIOURS THAT ARE NOT DEFECTS:
  P3 FIXED. A NEWLINE IN THE INPUT USED TO SURVIVE: `sed` trims per line, so a two-line argument yielded a two-line, unroutable slug. A newline is a dash like any byte outside the DNS alphabet.
  1. AN EMPTY ANSWER IS STILL A LINE. `devbox_slugify ''` prints one newline and exits 0: the final `printf '%s\\n'` runs whatever the pipeline produced. A function that prints a value prints its terminator.
  2. THE 40-CHARACTER CAP IS APPLIED BEFORE THE FINAL TRIM, so the answer can be 39 characters. `${s:0:40}` can land ON a dash, and a trailing dash is not a legal DNS label, which is the whole reason the second `sed` exists. The result is a legal label either way.
  4. MULTIBYTE COLLAPSES TO ONE DASH PER RUN, NOT ONE PER BYTE: `feat/uber` with an umlaut is `feat-ber` because two bytes became two dashes and then one. A readable name, and stable.
  5. `${3:-unknown}` FIRES ON AN EMPTY THIRD ARGUMENT AND IS INERT ANYWAY: the `unknown` it supplies reaches the `*)` arm, and so does every other value that is not `yes` or `no`. Kept for fidelity; removing it moves no observation.
  6. `devbox_slug_drift` NEVER FAILS: it ends in an explicit `return 0`, so its result is what it PRINTED. A reporter, not a check.
  7. NO ARGUMENT AT ALL IS AN UNBOUND VARIABLE, which is NOT A DEFECT: `devbox_slug_drift` and `devbox_route_label` open with `local want="$1"` and `local code="$1"`, and refusing a call with no subject is the strict answer (a default `code` would have the word contradict the code). They raise `DevboxError`; `devbox_slugify` is written `"${1:-}"` and answers the empty string.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import re
import stat
import subprocess
import sys
import time
from typing import Any

from rediacc_ci import log
from rediacc_ci.core import release_age
from rediacc_ci.well_known import ACCOUNT_DEV_PORT, IMAGE_REGISTRY
from rediacc_ci.well_known import DEVBOX_UID_IMAGE_REPO as WK_DEVBOX_UID_IMAGE_REPO

# The DNS-label cap `${s:0:40}` applies. `.ci/lib/devbox.sh:195`. Well under the 63 a label allows, because the slug also gets a `-code` / `-account` / `-db` / `-term` suffix before it becomes a hostname.
SLUG_MAX = 40

# The bytes a slug may keep. Everything else becomes a dash, one per BYTE, before the runs collapse. `.ci/lib/devbox.sh:194`, read under `LC_ALL=C` where a bracket expression is a set of bytes rather than of characters.
SLUG_KEEP = frozenset(b"abcdefghijklmnopqrstuvwxyz0123456789-")

# `tr '[:upper:]' '[:lower:]'` under `LC_ALL=C`: A-Z and nothing else. A byte above 0x7f is NOT lowercased, which is invisible here only because the next stage turns it into a dash either way.
UPPER_A, UPPER_Z = ord("A"), ord("Z")
UPPER_TO_LOWER_DELTA = ord("a") - ord("A")

# The two drift messages, `.ci/lib/devbox.sh:245` and `:248`, as their `printf` formats.
DRIFT_CONTAINER = "drift: the container serves %s, this checkout would use %s\n"
DRIFT_STATE = "drift: .devbox-state records %s, the container serves %s\n"

# The five route labels, `.ci/lib/devbox.sh:904-914`. `ROUTE_LIVE` is both the catch-all and the answer for a 404 the caller has confirmed a router for, which is the one place the same words are reached two ways.
ROUTE_PROXY_UNREACHABLE = "proxy unreachable"
ROUTE_NO_BACKEND = "no backend yet"
ROUTE_NO_ROUTER = "no such router -- nothing serves this hostname"
ROUTE_AMBIGUOUS_404 = "no matching route, or a backend 404 (HTTP %s)"
ROUTE_LIVE = "live (HTTP %s)"
# A 502 whose backend process is ALIVE: coming up or wedged, and the probe cannot tell which, so the row names the command that settles both rather than promising "starting".
ROUTE_NOT_SERVING_YET = "not serving yet -- ./run.sh devbox up re-dispatches it"

# What `${3:-unknown}` supplies for a missing OR EMPTY third argument (behaviour 5 of the pure three).
ROUTED_UNKNOWN = "unknown"

# What bash prints, and the status it exits with, when `local x="$1"` meets `set -u` with no arguments. Behaviour 7 of the pure three. The `<file>: line <N>: ` stamp bash puts in front of it is dropped by the differential on both sides, because a port cannot reproduce a line number in a file it is not.
UNBOUND_MESSAGE = "$1: unbound variable"
UNBOUND_STATUS = 1

# --------------------------------------------------------------------------- the constants `.ci/config/constants.sh:123-157` defines ---------------------------------------------------------------------------
# COPIED, NOT READ, and `test_core_devbox.py::test_the_constants_match_constants_sh` parses the `readonly` lines of that file on every run and fails on any drift. Reading them at import would mean parsing bash from Python at every call; copying them and checking the copy is the pattern `account.py` set.

DEVBOX_IMAGE = IMAGE_REGISTRY + "/devcontainer:latest"
# The LOCAL repository of the per-operator derived image (`.devcontainer/Dockerfile.uid`): the base with `vscode` renumbered to the host's ids. Deliberately not a ghcr.io/ name, so a derived tag can never be mistaken for something to push.
DEVBOX_UID_IMAGE_REPO = WK_DEVBOX_UID_IMAGE_REPO
DEVBOX_PORT_RANGE_START = 17000
DEVBOX_PORT_RANGE_END = 17999
DEVBOX_PORT_BLOCK = 10
# Offsets inside a block. The container publishes nothing and everything is reached through the proxy, so these are the ports processes bind INSIDE the container. TERM is block-derived rather than ttyd's own default 7681 for the reason the block exists at all: two worktrees on one machine must never collide.
DEVBOX_OFFSET_VSCODE = 0
DEVBOX_OFFSET_STUDIO = 3
DEVBOX_OFFSET_TERM = 5
# ONE published port for every worktree and every service. Routing is by Host header, so each app still believes it is at "/" and needs no base-path configuration; Chrome resolves *.localhost to 127.0.0.1 itself, which is the whole point on ChromeOS, where each published port otherwise needs its own manual forward.
DEVBOX_PROXY_IMAGE = "traefik:v3.6"
DEVBOX_PROXY_NAME = "rediacc-devbox-proxy"
DEVBOX_PROXY_PORT = 8090
DEVBOX_NETWORK = "rediacc-devbox"
DEVBOX_DOMAIN = "localhost"
# The state file's name under `CONSOLE_ROOT_DIR`, `.ci/config/constants.sh:135`.
DEVBOX_STATE_NAME = ".devbox-state"

# `.ci/lib/devbox.sh:43` and `:48`. The worktree label is the IDENTITY key (a path never changes under a container); the slug label is a fact about the routers already created, and it is allowed to disagree with what this checkout would compute today.
DEVBOX_LABEL_KEY = "com.rediacc.devbox.worktree"
DEVBOX_SLUG_LABEL_KEY = "com.rediacc.devbox.slug"

# `.ci/lib/devbox.sh:477`.
DEVBOX_CONTAINER_HOME = "/home/vscode"

# `devbox_script_binds`, `.ci/lib/devbox.sh:468-475`: the tracked scripts bound into every devbox, "<source under .devcontainer/>:<container path>". Data rather than inline `-v` flags so `devbox_up` and `devbox_missing_binds` read ONE list: a bind exists only from `docker run` on, so a container created before a line was added lacks it forever, and `devbox_missing_binds` is how `devbox_up` notices and recreates.
# devbox-bws.sh is the login-shell hook that exports BWS_ACCESS_TOKEN from the host's token-only file ~/.config/rediacc/bws-access-token (the file bound read-only by devbox_home_binds, never copied), so `bws` works inside the devbox without the token entering the image, Config.Env, a label or a log.
SCRIPT_BINDS = (
    "devbox-entrypoint.sh:/usr/local/bin/devbox-entrypoint.sh",
    "devbox-autostart.sh:/usr/local/bin/devbox-autostart.sh",
    "start-ttyd.sh:/usr/local/bin/start-ttyd.sh",
    "devbox-bws.sh:/etc/profile.d/zz-devbox-bws.sh",
)

# `DEVBOX_CORE_LEASE_DEST`, `.ci/lib/devbox.sh` (commit 606f7daac): where the host's core lease pool is bound inside the container.
DEVBOX_CORE_LEASE_DEST = "/run/rediacc-cores"
# `devbox_home_binds`, `.ci/lib/devbox.sh:478-490`: host files bound by NAME into the container user's home, "<path relative to $HOME>:<mode>" (mode empty for read-write). Credentials and agent config are named rather than the whole $HOME: ~/.ssh and cloud credentials stay out of the container.
# .config/rediacc/bws-access-token is the console's own bootstrap credential. Its directory is the rdc CLI's READ-WRITE state, so the FILE is bound read-only on top of that directory bind (listed after it): a CLI or E2E run in the container can neither delete nor rewrite it.
HOME_BINDS = (
    ".gitconfig:ro",
    ".git-credentials:ro",
    ".config/gh:",
    ".claude:",
    ".claude.json:",
    ".config/rediacc:",
    ".config/rediacc/bws-access-token:ro",
)

# `devbox_status`'s four routes, `.ci/lib/devbox.sh:986-989`, already split the way `IFS=: read -r _ _label _suffix _hint` splits them: (label, suffix, hint). The driver's `status` scenario is what proves the split, because a mis-split hint would move the 502 row.
# The Terminal row carries NO hint on purpose: ttyd is started by devbox-autostart.sh, so there is no command an operator could run to fix a 502 there -- the answer is the container's ttyd.log, not a verb.
# `_devbox_route_specs`: key, label, suffix, hint, and the pgrep pattern that tells a starting backend from an absent one. The single table `status` prints and `await_ready` waits on.
ROUTE_SPECS = (
    ("code", "VS Code", "", "", ""),
    (
        "account",
        "Account",
        "account",
        "./run.sh account dev (INSIDE the devbox)",
        "run.sh account dev",
    ),
    ("db", "Database", "db", "./run.sh account db (INSIDE the devbox)", "run.sh account db"),
    ("term", "Terminal", "term", "", "ttyd"),
)
# Every label as `key=value`, one per line, in ONE inspect; `devbox_container_labels`.
LABELS_FORMAT = '{{range $k, $v := .Config.Labels}}{{$k}}={{$v}}{{"\\n"}}{{end}}'
# The container's environment, one variable per line; `devbox_autostart_dispatch`.
ENV_FORMAT = "{{range .Config.Env}}{{println .}}{{end}}"
# `devbox_docker_init`'s memo. EXPORTED, so children inherit it; a `$(...)` cannot write it back.
DOCKER_MEMO = "_DEVBOX_DOCKER"
READY_NOMINAL_S = 90
READY_CEILING_S = 300
SPINNER = "|/-\\"

# The environment `devbox_exec` forwards by NAME with `-e`, `.ci/lib/devbox.sh:1085`.
EXEC_FORWARDED_ENV = ("CI", "NO_COLOR", "TERM", "GH_TOKEN", "GITHUB_TOKEN")

# Shell variables BASH ITSELF sets at startup when the environment has none, which `${!v:-}` then sees. Found by the `exec` scenario, not by reading: with no TERM in the environment the twin still forwarded `-e TERM`, because bash's `set_if_not("TERM", "dumb")` creates the variable (unexported, so docker is handed a name with no value behind it). A TERM that is present but EMPTY is left alone by bash and is not forwarded.
SHELL_DEFAULTS = {"TERM": "dumb"}

# What bash exits with when a command is not on PATH, and when it is found but not executable.
STATUS_NOT_FOUND = 127
STATUS_NOT_EXECUTABLE = 126


class DevboxError(RuntimeError):
    """A refusal the twin reports on stderr and then dies on, rather than returning."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


class ShellExit(Exception):  # noqa: N818 -- it is not an error, it is a shell ending
    """The shell ends here: errexit, a nounset death, or a status the caller must propagate.

    Raised by `checked()` and `_req()`, caught at the boundaries bash itself has: a command substitution (`sub()`), and the top of an `invoke()`. A condition (`cond()`) does NOT catch it, because a nounset death inside `if f` still ends the shell.
    """

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


class Outcome:
    """A shell function's two observable channels: what it printed, and its status.

    The pure functions answer entirely in what they PRINT while returning 0 regardless. A port returning only a value would drop the half that the callers read.
    """

    __slots__ = ("code", "out")

    def __init__(self, out: str, code: int = 0) -> None:
        self.out = out
        self.code = code

    def __repr__(self) -> str:  # pragma: no cover -- diagnostics only
        return "Outcome(out=%r, code=%d)" % (self.out, self.code)


# --------------------------------------------------------------------------- the slug pipeline, one stage per bash stage ---------------------------------------------------------------------------


def lower_ascii(raw: bytes) -> bytes:
    """`LC_ALL=C tr '[:upper:]' '[:lower:]'`, `.ci/lib/devbox.sh:192`.

    A-Z ONLY. Under `LC_ALL=C` the two classes are the 26 ASCII letters, so a byte above 0x7f passes through untouched and meets the dash rule in the next stage as itself.
    """
    return bytes(
        byte + UPPER_TO_LOWER_DELTA if UPPER_A <= byte <= UPPER_Z else byte for byte in raw
    )


def sanitise_line(line: bytes) -> str:
    """`s/[^a-z0-9-]/-/g; s/--*/-/g; s/^-*//; s/-*$//` over ONE line, `.ci/lib/devbox.sh:194`.

    In that order, which is what makes a multibyte character one dash rather than two or three: every byte outside the set becomes a dash first, and only then do runs collapse. Behaviour 4 of the pure three.
    The answer is ASCII by construction, so this is where the bytes become a `str`.
    """
    dashed = "".join(chr(byte) if byte in SLUG_KEEP else "-" for byte in line)
    collapsed: list[str] = []
    for character in dashed:
        if character == "-" and collapsed and collapsed[-1] == "-":
            continue
        collapsed.append(character)
    return "".join(collapsed).strip("-")


def trim_dashes(line: str) -> str:
    """`s/^-*//; s/-*$//` over ONE line, `.ci/lib/devbox.sh:196`.

    The second pass, after the 40-character cut. It does NOT collapse runs, because the first pass already did and nothing between them can create one. Behaviour 2 of the pure three is why it exists at all.
    """
    return line.strip("-")


def slugify(value: str | None = None) -> str:
    """`devbox_slugify`, `.ci/lib/devbox.sh:186-197`, as a caller CAPTURES it.

    `None` is the no-argument case, which `"${1:-}"` makes the empty string rather than an error; see behaviour 7 of the pure three for why the other two functions differ.
    What is returned is what `s="$(devbox_slugify "$x")"` binds, so the trailing newline the twin prints is absent here exactly as command substitution strips it. `slugify_stdout` is the byte-level answer.

    THE INPUT IS TREATED AS BYTES, with `surrogateescape`, because the twin's pipeline is byte-level under `LC_ALL=C` and the live corpus includes branch names that are not valid UTF-8 at all.
    MEASURED, AND NOT THE CLAIM IT LOOKS LIKE: the byte-versus-character choice is not observable in the answer at all, because `s/--*/-/g` collapses the run either way, and a planted latin-1 port moved no observation in any of the seven differential scenarios.
    What IS observable is LOSING the input: a planted port encoding with `errors="ignore"` dropped every byte that is not valid UTF-8 and diverged on forty observations. The bytes are kept because the twin keeps them, and that is the surviving claim rather than any dash count.
    """
    raw = "" if value is None else value
    lowered = lower_ascii(raw.encode("utf-8", "surrogateescape"))
    # Rule T fix P3: a newline is outside the DNS alphabet like any other byte, so it becomes a dash. The twin's `sed` trimmed per LINE, so a two-line argument answered a two-line, unroutable hostname.
    sanitised = sanitise_line(lowered)
    # `${s:0:40}` counts CHARACTERS in the shell's own locale, and the string is ASCII by the time it gets here, so characters and bytes are the same count. Behaviour 2 of the pure three: the cut comes first and the trim after.
    capped = sanitised[:SLUG_MAX]
    return trim_dashes(capped)


def slugify_stdout(value: str | None = None) -> str:
    """The exact bytes `devbox_slugify` writes to stdout, which is never empty.

    The final `printf '%s\\n'` runs whatever the pipeline produced, so an input that sanitises away still prints one newline. Behaviour 1 of the pure three, and the reason this is a separate function: the value a caller binds and the bytes a differential compares are not the same string.
    """
    return slugify(value) + "\n"


# --------------------------------------------------------------------------- the two reporters ---------------------------------------------------------------------------


def slug_drift(want: str | None = None, baked: str = "", recorded: str = "") -> Outcome:
    """`devbox_slug_drift`, `.ci/lib/devbox.sh:242-253`.

    Three names in, up to two lines out, status ALWAYS 0 (behaviour 6 of the pure three). An empty name on either side of a comparison silences that comparison, which is what makes a checkout with no container and no state file quiet rather than doubly wrong.
    `want=None` is the no-argument call, which under `set -u` is not a quiet default but a dead shell; see behaviour 7 of the pure three.
    """
    if want is None:
        raise DevboxError(UNBOUND_MESSAGE, code=UNBOUND_STATUS)
    out = []
    if baked and want and baked != want:
        out.append(DRIFT_CONTAINER % (baked, want))
    if recorded and baked and recorded != baked:
        out.append(DRIFT_STATE % (recorded, baked))
    return Outcome("".join(out), 0)


def route_label(
    code: str | None = None, hint: str = "", routed: str = ROUTED_UNKNOWN, starting: str = "no"
) -> Outcome:
    """`devbox_route_label`, `.ci/lib/devbox.sh:902-916`.

    THE INVARIANT IT CARRIES IS THAT THE WORD NEVER CONTRADICTS THE CODE, and the twin's own comment records "OK (404)" shipping for one commit as the failure that motivated it.
    A 404 is "live" only when the CALLER has confirmed a router exists for that hostname, because the status code alone cannot tell traefik's no-such-router 404 from a backend's own not-found.
    An EMPTY `routed` is the unknown arm rather than a fourth case, which is behaviour 5 of the pure three and is INERT there, since the unknown arm is also the catch-all; `code=None` is the unbound-variable death, which is behaviour 7 of the pure three and is not inert at all.
    (Different context, deliberately untouched: the proxy health probe in `devbox_proxy_ensure` treats any answer including 404 as a healthy traefik. That is a claim about the PROXY, not about a route.)
    """
    if code is None:
        raise DevboxError(UNBOUND_MESSAGE, code=UNBOUND_STATUS)
    if not routed:
        routed = ROUTED_UNKNOWN
    if code == "000":
        return Outcome(ROUTE_PROXY_UNREACHABLE + "\n", 0)
    if code == "502":
        if starting == "yes":
            return Outcome(ROUTE_NOT_SERVING_YET + "\n", 0)
        suffix = " -- %s" % hint if hint else ""
        return Outcome(ROUTE_NO_BACKEND + suffix + "\n", 0)
    if code == "404":
        if routed == "no":
            return Outcome(ROUTE_NO_ROUTER + "\n", 0)
        if routed == "yes":
            return Outcome(ROUTE_LIVE % code + "\n", 0)
        return Outcome(ROUTE_AMBIGUOUS_404 % code + "\n", 0)
    return Outcome(ROUTE_LIVE % code + "\n", 0)


# --------------------------------------------------------------------------- the shell's own text rules ---------------------------------------------------------------------------

ASCII_LIMIT = 0x80


def locale_is_utf8(env: dict[str, str]) -> bool:
    """Is the shell's character type a UTF-8 one? `LC_ALL`, then `LC_CTYPE`, then `LANG`, as POSIX orders them.

    Decides how `printf '%q'` spells a multibyte character. The first NON-EMPTY of the three wins, which is how the C library resolves them.
    """
    for name in ("LC_ALL", "LC_CTYPE", "LANG"):
        value = env.get(name, "")
        if value:
            return bool(re.search(r"utf-?8", value, re.IGNORECASE))
    return False


# `printf %q`'s backslash set, measured by sweeping every printable ASCII character through bash 5.3.9 under `LC_ALL=C`. `~` is quoted only first or after `:` / `=`, and `#` only first.
Q_BACKSLASHED = frozenset(" !\"$&'()*,;<>?[\\]^`{|}")
Q_ANSI_C = {7: "\\a", 8: "\\b", 9: "\\t", 10: "\\n", 11: "\\v", 12: "\\f", 13: "\\r", 27: "\\E"}
PRINTABLE_LOW, PRINTABLE_HIGH = 0x20, 0x7E


def _q_printable_chars(data: bytes, utf8: bool) -> list[tuple[bytes, bool]]:
    """Split `data` into (character bytes, printable?) the way bash's `ansic_shouldquote` sees it."""
    if not utf8:
        return [(bytes([b]), PRINTABLE_LOW <= b <= PRINTABLE_HIGH) for b in data]
    out: list[tuple[bytes, bool]] = []
    text = data.decode("utf-8", "surrogateescape")
    for character in text:
        raw = character.encode("utf-8", "surrogateescape")
        if len(raw) == 1 and 0xDC80 <= ord(character) <= 0xDCFF:
            out.append((raw, False))
        elif ord(character) < ASCII_LIMIT:
            out.append((raw, PRINTABLE_LOW <= ord(character) <= PRINTABLE_HIGH))
        else:
            out.append((raw, character.isprintable()))
    return out


def shell_quote(word: str, utf8: bool = False) -> str:
    """`printf '%q' "$word"`, as bash 5.3.9 spells it. Its empty case spells `''`.

    THREE SHAPES, chosen in this order. The empty word is `''`. A word holding ANY non-printable character is ANSI-C quoted as a whole, `$'...'`, with `\\a \\b \\t \\n \\v \\f \\r \\E`, `\\\\`, `\\'` and three-digit octal for the rest. Otherwise each character in `Q_BACKSLASHED` gets a backslash.
    Under `LC_ALL=C` every byte above 0x7e is non-printable, so `é` is `$'\\303\\251'`; under a UTF-8 locale a printable multibyte character passes through. The differential compares the C form; the UTF-8 form follows the same rule with the locale's own notion of printable.
    """
    if word == "":
        return "''"
    data = word.encode("utf-8", "surrogateescape")
    characters = _q_printable_chars(data, utf8)
    if not all(printable for _, printable in characters):
        parts = []
        for raw, printable in characters:
            if printable:
                text = raw.decode("utf-8", "surrogateescape")
                parts.append({"\\": "\\\\", "'": "\\'"}.get(text, text))
            elif len(raw) == 1 and raw[0] in Q_ANSI_C:
                parts.append(Q_ANSI_C[raw[0]])
            else:
                parts.append("".join("\\%03o" % byte for byte in raw))
        return "$'" + "".join(parts) + "'"
    out = []
    previous = ""
    for position, (raw, _) in enumerate(characters):
        text = raw.decode("utf-8", "surrogateescape")
        if (
            text in Q_BACKSLASHED
            or (text == "#" and position == 0)
            or (text == "~" and (position == 0 or previous in (":", "=")))
        ):
            out.append("\\")
        out.append(text)
        previous = text
    return "".join(out)


def basename(path: str) -> str:
    """coreutils `basename PATH`: trailing slashes dropped first, then the last component; all slashes is `/`."""
    stripped = path.rstrip("/")
    if stripped == "":
        return "/" if path else ""
    return stripped.rsplit("/", 1)[-1]


def slug_basename_rule(name: str) -> str:
    """`basename ... | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g; s/^-*//; s/-*$//'`, `.ci/lib/devbox.sh:199-201`, as PRINTED.

    NOT `slugify`, and two differences are the point of keeping this rule: no run collapse and no 40-character cap. It runs under the C locale like `slugify` (Rule T fix D10): the twin forced no `LC_ALL`, so a multibyte character became one dash per BYTE for one caller and one per CHARACTER for another, and the same checkout got two hostnames.
    Every byte outside the set is a dash. Each input line becomes one output line, newline-terminated, because `sed` terminates every line it prints when its input line was terminated and `basename` always terminates its answer.
    """
    lowered = lower_ascii((name + "\n").encode("utf-8", "surrogateescape"))
    lines = lowered.split(b"\n")[:-1]
    out = []
    for line in lines:
        dashed = "".join(chr(byte) if byte in SLUG_KEEP else "-" for byte in line)
        out.append(dashed.strip("-") + "\n")
    return "".join(out)


def decimal(text: str) -> int:
    """A port number or a duration as a DECIMAL integer, leading zeros included (Rule T fix D6).

    The twin's `$((base_port + 5))` is shell arithmetic, which reads `017000` as octal 7680 and rejects `08`, so a hand-edited state file moved every route to a port nothing listens on. Surrounding blanks are ignored. Anything that is not digits raises `DevboxError`: shell arithmetic would dereference a NAME, which is a different program.
    """
    stripped = text.strip()
    if re.fullmatch(r"[+-]?[0-9]+", stripped):
        return int(stripped, 10)
    raise DevboxError("%r is not a number" % text)


def complete_lines(text: str) -> list[str]:
    """The lines a bare `while read -r x` loop sees: a final line with no newline is DROPPED."""
    lines = text.split("\n")
    lines.pop()
    return lines


def all_lines(text: str) -> list[str]:
    """The lines `sed` or a here-string loop sees: a final unterminated line is still a line."""
    if text == "":
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def ifs_trim(line: str) -> str:
    """`read -r x` into ONE variable: leading and trailing IFS whitespace (space, tab) removed."""
    return line.strip(" \t")


# --------------------------------------------------------------------------- the shell machinery ---------------------------------------------------------------------------

# Redirection targets for `Devbox.run`. INHERIT is "wherever this function's own stream currently goes", which is what a command with no redirection does in bash.
INHERIT = "inherit"
NULL = "null"
CAPTURE = "capture"
TO_ERR = "to_err"  # `>&2`
TO_OUT = "to_out"  # `2>&1`


def _fd(stream) -> int | None:
    """The OS file descriptor behind `stream`, or None for an in-memory buffer."""
    try:
        return stream.fileno()
    except (AttributeError, OSError, ValueError, io.UnsupportedOperation):
        return None


def _flush(stream) -> None:
    with contextlib.suppress(AttributeError, OSError, ValueError):
        stream.flush()


def _isatty(stream) -> bool:
    fd = _fd(stream)
    return fd is not None and os.isatty(fd)


def repo_root_default() -> str:
    """The checkout this module sits in, as `.ci/config/constants.sh:76` derives `CONSOLE_ROOT_DIR`: `<here>/../../..`, logical."""
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
    )


class Devbox:
    """The fifty-one side-effecting functions, over one environment and one pair of streams.

    CONSTRUCT ONE PER TOP-LEVEL CALL. The instance carries the shell state bash would carry across one invocation (errexit, the current streams) and the configuration bash resolves at SOURCE time (`CONSOLE_ROOT_DIR`, the state file, `DEVBOX_LIB_DIR`, `DEVBOX_CI_DIR`, whether stderr gets colour). A long-lived instance would freeze the source-time answers across calls, which is also what a long-lived shell does, and is fine; it is the per-call mutable part that must not leak.

    `env` is the whole environment children see and the only one the methods read; `os.environ` is never consulted after construction. `stdout`/`stderr` are BINARY streams; one with a real file descriptor is handed to children directly, exactly as a shell hands its fds down, and an in-memory one is filled from a pipe.
    """

    def __init__(
        self,
        env: dict[str, str] | None = None,
        *,
        cwd: str | None = None,
        stdout=None,
        stderr=None,
        stdin=None,
        repo_root: str | None = None,
    ) -> None:
        self.env = dict(os.environ if env is None else env)
        self.cwd = cwd or os.getcwd()
        self.stdout = stdout if stdout is not None else sys.stdout.buffer
        self.stderr = stderr if stderr is not None else sys.stderr.buffer
        self.stdin = stdin if stdin is not None else sys.stdin
        self.errexit = True
        root = repo_root or repo_root_default()
        # `.ci/config/constants.sh:76`: `${CONSOLE_ROOT_DIR:-<its own checkout>}`, so an EMPTY value falls back as well as a missing one.
        self.console_root = self.env.get("CONSOLE_ROOT_DIR") or root
        self.state_file = self.console_root + "/" + DEVBOX_STATE_NAME
        # `.ci/lib/devbox.sh:22`: the directory the twin was sourced from, logical.
        self.lib_dir = os.path.join(root, ".ci", "lib")
        # `.ci/lib/devbox.sh:32-33`: REDIACC_CI_ROOT wins, else `$DEVBOX_LIB_DIR/..`.
        ci_root = self.env.get("REDIACC_CI_ROOT", "")
        self.ci_dir = ci_root + "/.ci" if ci_root else os.path.join(root, ".ci")
        self.utf8 = locale_is_utf8(self.env)
        # `.ci/scripts/lib/common.sh:18`: colour when fd 2 is a terminal and NO_COLOR is empty, decided ONCE when the library is sourced. `CI` is not consulted; `rediacc_ci.log`'s own rule differs there on purpose, and this is the twin's rule.
        self.colour = _isatty(self.stderr) and not self.env.get("NO_COLOR")
        self._logger = log.Logger(stream=io.StringIO(), colour=self.colour, env=self.env)

    # ------------------------------------------------------------------ streams and shell control

    def write(self, text: str | bytes, stream=None) -> None:
        """Write to the current stdout (or `stream`), as `printf`/`echo` would."""
        data = text if isinstance(text, bytes) else text.encode("utf-8", "surrogateescape")
        target = self.stdout if stream is None else stream
        target.write(data)
        _flush(target)

    def log(self, level: str, message: str) -> None:
        """`log_info` / `log_warn` / `log_error` / `log_step` / `log_debug`, `.ci/scripts/lib/common.sh:35-54`.

        `echo -e "${COLOUR}<glyph>${NC} $*" >&2`. The glyph and colour are `rediacc_ci.log`'s, which carries common.sh's table. The message is printed VERBATIM (Rule T fix D4): the twin's `-e` applied to the whole argument, so a backslash in DATA (a worktree label) became a tab or swallowed the rest of the line.
        `log_debug` is silent unless `DEBUG` is exactly `true` at CALL time.
        """
        if level == "debug" and self.env.get(log.DEBUG_ENV, "false") != log.DEBUG_ON:
            return
        glyph_line = self._logger.format(level, "")
        self.write(
            glyph_line.encode("utf-8") + message.encode("utf-8", "surrogateescape") + b"\n",
            self.stderr,
        )

    def checked(self, status: int) -> int:
        """errexit: a non-zero status in statement position ends the shell, when errexit is armed."""
        if status != 0 and self.errexit:
            raise ShellExit(status)
        return status

    def cond(self, fn, *argv: str) -> int:
        """Call `fn` as a CONDITION (`if fn`, `fn || x`): errexit is off for its whole body, however deep."""
        saved = self.errexit
        self.errexit = False
        try:
            return fn(*argv)
        finally:
            self.errexit = saved

    def sub(self, fn, *argv: str, err: str = INHERIT) -> tuple[int, str]:
        """`x="$(fn args)"`: (the subshell's status, what it printed minus EVERY trailing newline).

        errexit is NOT inherited into a command substitution here (no `inherit_errexit`), and a `ShellExit` inside ends only the subshell. NUL bytes are dropped, as bash drops them with a warning. `err` is the substitution's own stderr redirection: INHERIT, NULL (`2>/dev/null`) or TO_OUT (`2>&1`, captured with stdout).
        """
        buffer = io.BytesIO()
        saved = (self.stdout, self.stderr, self.errexit)
        # A SUBSHELL'S ENVIRONMENT DIES WITH IT. `d="$(devbox_docker)"` may seed the docker memo inside the substitution, and bash drops that on the way out; only `devbox_docker_init` called from the parent persists it.
        saved_env = dict(self.env)
        self.stdout = buffer
        if err == NULL:
            self.stderr = open(os.devnull, "wb")  # noqa: SIM115 -- closed in the finally below
        elif err == TO_OUT:
            self.stderr = buffer
        self.errexit = False
        try:
            status = fn(*argv)
        except ShellExit as exc:
            status = exc.code
        finally:
            if err == NULL:
                self.stderr.close()
            self.stdout, self.stderr, self.errexit = saved
            self.env = saved_env
        text = buffer.getvalue().replace(b"\0", b"").decode("utf-8", "surrogateescape")
        return status, text.rstrip("\n")

    @contextlib.contextmanager
    def redirected(self, out: str = INHERIT, err: str = INHERIT):
        """`fn >/dev/null 2>&1` and friends around a FUNCTION call rather than an external."""
        saved = (self.stdout, self.stderr)
        null = open(os.devnull, "wb") if NULL in (out, err) else None  # noqa: SIM115 -- closed below
        try:
            if out == NULL:
                self.stdout = null
            elif out == TO_ERR:
                self.stdout = saved[1]
            if err == NULL:
                self.stderr = null
            elif err == TO_OUT:
                self.stderr = self.stdout
            yield
        finally:
            self.stdout, self.stderr = saved
            if null is not None:
                null.close()

    def _req(self, argv: tuple[str, ...], index: int) -> str:
        """`"$N"` under `set -u`: the argument, or the nounset death with bash's message."""
        if len(argv) > index:
            return argv[index]
        self.write("$%d: unbound variable\n" % (index + 1), self.stderr)
        raise ShellExit(UNBOUND_STATUS)

    @staticmethod
    def _opt(argv: tuple[str, ...], index: int, default: str = "") -> str:
        """`${N:-default}`: the default for a MISSING or an EMPTY argument alike."""
        value = argv[index] if len(argv) > index else ""
        return value or default

    # ------------------------------------------------------------------ externals

    def _target(self, mode: str, own):
        if mode == NULL:
            return subprocess.DEVNULL
        if mode == CAPTURE:
            return subprocess.PIPE
        return own

    def run(
        self,
        argv: list[str],
        out: str = INHERIT,
        err: str = INHERIT,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        """One external command with bash's redirection semantics: (status, captured stdout if `out=CAPTURE`).

        A stream with a real fd is handed down after a flush, so a child writes exactly where the shell's child would; an in-memory stream is filled from a pipe afterwards. A command not on PATH is bash's `<name>: command not found` on the command's OWN stderr target and status 127, which is why `docker version &>/dev/null` stays silent when docker is absent.
        """
        out_stream = {INHERIT: self.stdout, TO_ERR: self.stderr}.get(out)
        err_stream = {INHERIT: self.stderr, TO_OUT: out_stream}.get(err)
        env = dict(self.env)
        if extra_env:
            env.update(extra_env)
        stdout_arg = self._target(out, out_stream)
        copy_out = None
        if out_stream is not None:
            fd = _fd(out_stream)
            if fd is None:
                stdout_arg, copy_out = subprocess.PIPE, out_stream
            else:
                _flush(out_stream)
                stdout_arg = fd
        stderr_arg: Any
        if err == TO_OUT and out == CAPTURE:
            stderr_arg = subprocess.STDOUT
            copy_err = None
        else:
            stderr_arg = subprocess.DEVNULL if err == NULL else err_stream
            copy_err = None
            if err_stream is not None:
                fd = _fd(err_stream)
                if fd is None:
                    if err_stream is out_stream and copy_out is not None:
                        stderr_arg = subprocess.STDOUT
                    else:
                        stderr_arg, copy_err = subprocess.PIPE, err_stream
                else:
                    _flush(err_stream)
                    stderr_arg = fd
        stdin_fd = _fd(self.stdin)
        try:
            proc = subprocess.run(
                argv,
                stdin=stdin_fd,
                stdout=stdout_arg,
                stderr=stderr_arg,
                env=env,
                cwd=self.cwd,
                check=False,
            )
        except FileNotFoundError:
            return self._spawn_failure(
                argv[0], "command not found", STATUS_NOT_FOUND, err, err_stream
            )
        except PermissionError:
            return self._spawn_failure(
                argv[0], "Permission denied", STATUS_NOT_EXECUTABLE, err, err_stream
            )
        captured = ""
        if proc.stdout is not None:
            if copy_out is not None:
                self.write(proc.stdout, copy_out)
            else:
                captured = proc.stdout.decode("utf-8", "surrogateescape")
        if copy_err is not None and proc.stderr is not None:
            self.write(proc.stderr, copy_err)
        return proc.returncode, captured

    def _spawn_failure(
        self, name: str, reason: str, status: int, err: str, err_stream
    ) -> tuple[int, str]:
        if err != NULL and err_stream is not None:
            self.write("%s: %s\n" % (name, reason), err_stream)
        return status, ""

    def value(
        self, argv: list[str], err: str = INHERIT, extra_env: dict[str, str] | None = None
    ) -> tuple[int, str]:
        """`x="$(cmd args)"` for an EXTERNAL: its status and its stdout minus every trailing newline."""
        status, text = self.run(argv, out=CAPTURE, err=err, extra_env=extra_env)
        return status, text.replace("\0", "").rstrip("\n")

    def _ports(self, *args: str) -> list[str]:
        """`PYTHONPATH="$DEVBOX_CI_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 -m rediacc_ci.core.ports ...`, `.ci/lib/devbox.sh:87` and `:152`."""
        return ["python3", "-m", "rediacc_ci.core.ports", *args]

    def _ports_env(self) -> dict[str, str]:
        existing = self.env.get("PYTHONPATH", "")
        return {"PYTHONPATH": self.ci_dir + (":" + existing if existing else "")}

    # ------------------------------------------------------------------ the pure three, as printing methods

    def slugify(self, *argv: str) -> int:
        """`devbox_slugify`: prints `slugify_stdout`, status 0."""
        self.write(slugify_stdout(argv[0] if argv else None))
        return 0

    def slug_drift(self, *argv: str) -> int:
        """`devbox_slug_drift`: prints `slug_drift`'s lines, status 0, or the nounset death."""
        want = self._req(argv, 0)
        self.write(slug_drift(want, self._opt(argv, 1), self._opt(argv, 2)).out)
        return 0

    def route_label(self, *argv: str) -> int:
        """`devbox_route_label`: prints `route_label`'s one line, status 0, or the nounset death."""
        code = self._req(argv, 0)
        self.write(
            route_label(
                code,
                self._opt(argv, 1),
                self._opt(argv, 2, ROUTED_UNKNOWN),
                self._opt(argv, 3, "no"),
            ).out
        )
        return 0

    # ------------------------------------------------------------------ IDENTITY

    def worktree_path(self) -> str:
        """`$(devbox_worktree)`'s value, which reaches nothing but the filesystem."""
        path = self.console_root or self.cwd
        target = path if path.startswith("/") else os.path.join(self.cwd, path)
        if os.path.isdir(target) and os.access(target, os.X_OK):
            return os.path.realpath(target)
        return path.rstrip("\n")

    def worktree(self, *_argv: str) -> int:
        """`devbox_worktree`, `.ci/lib/devbox.sh:55-62`: the worktree this checkout is, resolved absolutely (the label and port key).

        `(cd "$path" 2>/dev/null && pwd -P) || printf '%s\\n' "$path"`: the PHYSICAL path when the directory is there, and the LITERAL value when it is gone.
        The fallback is the twin's answer to a real loss: `cd` into a deleted worktree fails, the substitution yields EMPTY, and every caller then builds `label=com.rediacc.devbox.worktree=` -- a filter that matches nothing, so a removed worktree's container could never be found again. `identity-gone` drives it.
        """
        self.write(self.worktree_path() + "\n")
        return 0

    def mount_root(self, *_argv: str) -> int:
        """`devbox_mount_root`, `.ci/lib/devbox.sh:70-82`: the directory that must be bind-mounted.

        NOT simply the worktree: a git worktree's .git file holds an ABSOLUTE gitdir path back into the main checkout, so mounting only the worktree gives a container where every git command fails. Mounting the main checkout covers both, because worktrees live under it (scripts/dev/worktree.sh:22).
        `--git-common-dir` may be relative to the worktree (it is `.git` in a main checkout) or absolute (in a linked worktree); `identity` and `identity-worktree` drive one each.
        """
        wt = self.worktree_path()
        status, common = self.value(["git", "-C", wt, "rev-parse", "--git-common-dir"], err=NULL)
        if status == 0:
            if not common.startswith("/"):
                common = self.worktree_path() + "/" + common
            parent = common + "/.."
            if os.path.isdir(parent) and os.access(parent, os.X_OK):
                self.write(os.path.realpath(parent) + "\n")
            else:
                self.write("cd: %s: No such file or directory\n" % parent, self.stderr)
                self.checked(1)
            return 0
        self.write(self.worktree_path() + "\n")
        return 0

    def container_name(self, *_argv: str) -> int:
        """`devbox_container_name`, `.ci/lib/devbox.sh:84-90`: `rediacc-devbox-<slot>-<basename>`.

        The slot is `rediacc_ci.core.ports derive-slot <worktree> 100`, run as the same child program the twin runs, so the key is hashed by one implementation for both sides. A failing child is an errexit death on the bare `slot=` assignment.
        """
        wt = self.worktree_path()
        status, slot = self.value(
            self._ports("derive-slot", wt, "100"), extra_env=self._ports_env()
        )
        self.checked(status)
        self.write("rediacc-devbox-%s-%s\n" % (slot, basename(wt)))
        return 0

    def docker_words(self) -> list[str]:
        """`d="$(devbox_docker)"` then `$d` unquoted: the one or two words every docker call starts with."""
        return self.sub(self.docker)[1].split()

    def docker_init(self, *_argv: str) -> int:
        """`devbox_docker_init`: resolve docker vs sudo docker ONCE and export it as `_DEVBOX_DOCKER`.

        Three probes in order, each silenced: `docker version`, then `sudo -n docker version`, then `sudo docker version` (which may prompt). The answer is `docker` again when all three fail, so the caller's next command fails with docker's own message. An already-set memo returns at once.
        THE MEMO IS THE ENVIRONMENT, not an attribute: every twin call site is `d="$(devbox_docker)"`, a subshell, so only a value exported from the parent (here, `self.env` outside any `sub`) survives to the next call, and children inherit it the same way.
        """
        if self.env.get(DOCKER_MEMO):
            return 0
        if self.run(["docker", "version"], out=NULL, err=NULL)[0] == 0:
            answer = "docker"
        elif (
            self.run(["sudo", "-n", "docker", "version"], out=NULL, err=NULL)[0] == 0
            or self.run(["sudo", "docker", "version"], out=NULL, err=NULL)[0] == 0
        ):
            answer = "sudo docker"
        else:
            answer = "docker"
        self.env[DOCKER_MEMO] = answer
        return 0

    def docker(self, *_argv: str) -> int:
        """`devbox_docker`: the memo, seeding it first when nothing did. Seeded inside a `sub`, the seed dies with the substitution, exactly as the twin's does."""
        if not self.env.get(DOCKER_MEMO):
            self.docker_init()
        self.write(self.env[DOCKER_MEMO] + "\n")
        return 0

    def docker_reset(self, *_argv: str) -> int:
        """`devbox_docker_reset`: drop the memo after anything that changes whether docker is usable."""
        self.env.pop(DOCKER_MEMO, None)
        return 0

    # ------------------------------------------------------------------ STATE

    def state_write(self, *argv: str) -> int:
        """`devbox_state_write`, `.ci/lib/devbox.sh:107-122`: `cat >"$DEVBOX_STATE_FILE" <<EOF`.

        Four required positionals under `set -u` and an optional slug; a missing one is the nounset death, reported for the FIRST missing position because bash expands `local a="$1" b="$2" ...` left to right. `uid`/`gid` are `id -u`/`id -g`, the EFFECTIVE ids. A redirection that cannot open the file is bash's `<path>: <reason>` and status 1, with nothing written.
        """
        base_port = self._req(argv, 0)
        container = self._req(argv, 1)
        digest = self._req(argv, 2)
        docker_gid = self._req(argv, 3)
        slug = self._opt(argv, 4)
        lines = [
            "# Generated by ./run.sh setup - do not edit",
            "worktree=" + self.worktree_path(),
            "container=" + container,
            "base_port=" + base_port,
            "slug=" + slug,
            "image=" + DEVBOX_IMAGE,
            "image_digest=" + digest,
            "docker_gid=" + docker_gid,
            "uid=%d" % os.geteuid(),
            "gid=%d" % os.getegid(),
            "gate_lane=" + (self.env.get("REDIACC_GATE_LANE") or "devbox"),
        ]
        try:
            with open(self.state_file, "wb") as handle:
                handle.write(("\n".join(lines) + "\n").encode("utf-8", "surrogateescape"))
        except OSError as exc:
            self.write("%s: %s\n" % (self.state_file, exc.strerror), self.stderr)
            return 1
        return 0

    def state_get(self, *argv: str) -> int:
        """`devbox_state_get`, `.ci/lib/devbox.sh:124-128`: `sed -n "s/^${key}=//p" "$DEVBOX_STATE_FILE" | head -1`.

        Status 1 ONLY when the file is missing; a file without the key prints nothing and succeeds, and callers reject the EMPTY value themselves. The FIRST matching line wins, printed with the matched prefix removed and its own newline kept, so a last line with no newline prints without one. The key is a LITERAL (Rule T fix D11): the twin interpolated it into a `sed` regular expression, so `base.port` matched `base_port=`.
        """
        key = self._req(argv, 0)
        if not os.path.isfile(self.state_file):
            return 1
        prefix = (key + "=").encode("utf-8", "surrogateescape")
        with open(self.state_file, "rb") as handle:
            data = handle.read()
        position = 0
        while position < len(data):
            newline = data.find(b"\n", position)
            end = len(data) if newline < 0 else newline
            line = data[position:end]
            if line.startswith(prefix):
                self.write(line[len(prefix) :] + (b"" if newline < 0 else b"\n"))
                break
            position = end + 1
        return 0

    # ------------------------------------------------------------------ PORTS

    def base_port(self, *_argv: str) -> int:
        """`devbox_base_port`, `.ci/lib/devbox.sh:136-155`: the state file's `base_port`, else a free block derived from the worktree path.

        The state file is the record: the container publishes NO ports, so there is nothing to ask the daemon for. A previously allocated base is reused so a temporarily busy neighbour cannot shuffle an established devbox. First time, `rediacc_ci.core.ports find-port-block <worktree> 17000 17999 10`, whose `ss` probes land in the stub farm.
        """
        status, saved = self.sub(self.state_get, "base_port")
        if status == 0 and saved:
            self.write(saved + "\n")
            return 0
        return self.run(
            self._ports(
                "find-port-block",
                self.worktree_path(),
                str(DEVBOX_PORT_RANGE_START),
                str(DEVBOX_PORT_RANGE_END),
                str(DEVBOX_PORT_BLOCK),
            ),
            extra_env=self._ports_env(),
        )[0]

    # ------------------------------------------------------------------ HOSTNAME

    def branch_value(self) -> str:
        return self.sub(self.branch)[1]

    def branch(self, *_argv: str) -> int:
        """`devbox_branch`, `.ci/lib/devbox.sh:176-178`: the checked-out branch, or nothing.

        `symbolic-ref --quiet`, NOT `rev-parse --abbrev-ref HEAD`: the latter prints the literal string HEAD when detached, which sanitises to the perfectly valid hostname `head.localhost`, so every detached worktree on the machine would converge on ONE hostname and ONE router name. symbolic-ref answers empty for detached, mid-rebase and mid-bisect alike. `|| true`: always status 0.
        """
        self.run(
            ["git", "-C", self.worktree_path(), "symbolic-ref", "--quiet", "--short", "HEAD"],
            err=NULL,
        )
        return 0

    def slug_basename(self, *_argv: str) -> int:
        """`devbox_slug_basename`, `.ci/lib/devbox.sh:199-201`: the pre-branch rule, kept EXACTLY as it was.

        It is the fallback, and being the old rule is what makes existing containers keep their names. `slug_basename_rule` carries the rule and Rule T fix D10, which pins it to the C locale.
        """
        self.write(slug_basename_rule(basename(self.worktree_path())))
        return 0

    def slug(self, *_argv: str) -> int:
        """`devbox_slug`, `.ci/lib/devbox.sh:204-218`: what THIS checkout would be hosted as right now.

        `DEVBOX_SLUG` first, still sanitised, because an invalid Host rule is a route traefik silently ignores; it is the manual escape hatch for two checkouts on one branch. Then the branch, slugified; then the basename rule when the branch slugifies to nothing (detached, mid-rebase, or a branch made only of punctuation).
        """
        manual = self.env.get("DEVBOX_SLUG", "")
        if manual:
            s = slugify(manual)
            if s:
                self.write(s + "\n")
                return 0
        s = slugify(self.branch_value())
        if not s:
            s = self.sub(self.slug_basename)[1]
        self.write(s + "\n")
        return 0

    def container_labels(self, *argv: str) -> int:
        """`devbox_container_labels [cid]`: every label on the devbox container as `key=value` lines, in ONE inspect.

        `devbox_slug_active` and `devbox_router_hosts` each used to run their own inspect for a subset of this, plus a `docker ps` each to find the container. A caller that already holds the id passes it. The inspect is `|| true`, so the status is 0 whatever docker says.
        """
        cid = self._opt(argv, 0)
        if not cid:
            status, cid = self.sub(self.container_id)
            self.checked(status)
        if not cid:
            return 0
        d = self.docker_words()
        self.run([*d, "inspect", "-f", LABELS_FORMAT, cid], err=NULL)
        return 0

    def slug_active(self, *argv: str) -> int:
        """`devbox_slug_active [labels]`: what the RUNNING container was built with.

        Everything the operator is shown, and every probe, must use this and not a freshly computed slug: after a branch rename the two disagree, and a probe against the recomputed name reaches no router at all. No container is `devbox_slug`; a container with no slug label predates the label and is hosted under the old basename rule, which is exactly what it was created with.
        The slug is read out of `labels` (fetched here when the caller has none) through `sed -n "s/^${KEY}=//p" | head -1`, matched as a LITERAL key (Rule T fix D11).
        """
        labels = self._opt(argv, 0)
        if not labels:
            status, cid = self.sub(self.container_id)
            self.checked(status)
            if not cid:
                self.checked(self.slug())
                return 0
            status, labels = self.sub(self.container_labels, cid)
            self.checked(status)
        prefix = (DEVBOX_SLUG_LABEL_KEY + "=").encode("utf-8", "surrogateescape")
        found = ""
        for line in (labels + "\n").encode("utf-8", "surrogateescape").split(b"\n")[:-1]:
            if line.startswith(prefix):
                found = line[len(prefix) :].decode("utf-8", "surrogateescape")
                break
        if found == "<no value>":
            found = ""
        if not found:
            found = self.sub(self.slug_basename)[1]
        self.write(found + "\n")
        return 0

    def slug_conflicts(self, *argv: str) -> int:
        """`devbox_slug_conflicts`, `.ci/lib/devbox.sh:255-270`: other checkouts' containers already claiming this hostname.

        Prints their worktree paths; empty output means no conflict. Every `docker ps` line is read, an unterminated final one included (Rule T fix D3: the twin's bare `while read -r cid` dropped it), and blanks around each id are trimmed. A container whose worktree label is this checkout's own path, or is missing, is not a conflict.
        """
        slug = self._opt(argv, 0)
        if not slug:
            status, slug = self.sub(self.slug)
            self.checked(status)
        if not slug:
            return 0
        wt = self.worktree_path()
        d = self.docker_words()
        _, listing = self.run(
            [*d, "ps", "-aq", "--filter", "label=%s=%s" % (DEVBOX_SLUG_LABEL_KEY, slug)],
            out=CAPTURE,
            err=NULL,
        )
        for line in all_lines(listing):
            cid = ifs_trim(line)
            if not cid:
                continue
            _, other = self.value(
                [*d, "inspect", "-f", '{{index .Config.Labels "%s"}}' % DEVBOX_LABEL_KEY, cid],
                err=NULL,
            )
            if other == "<no value>":
                other = ""
            if other and other != wt:
                self.write(other + "\n")
        return 0

    def router_hosts(self, *argv: str) -> int:
        """`devbox_router_hosts [labels]`: every hostname the running container declares a router for.

        The authority for "is this 404 traefik saying no-such-router, or the backend saying not-found?", a question the status code alone cannot answer. Every label line through `sed -n 's/.*Host(`\\([^`]*\\)`).*/\\1/p'`: the LAST `Host(` on a line wins because the leading `.*` is greedy. The labels arrive through `printf '%s\\n'`, so every line is terminated and the status is sed's, 0.
        """
        labels = self._opt(argv, 0)
        if not labels:
            status, labels = self.sub(self.container_labels)
            self.checked(status)
        if not labels:
            return 0
        for line in (labels + "\n").encode("utf-8", "surrogateescape").split(b"\n")[:-1]:
            match = re.match(rb".*Host\(`([^`]*)`\)", line, re.DOTALL)
            if match:
                self.write(match.group(1) + b"\n")
        return 0

    def url(self, *argv: str) -> int:
        """`devbox_url`, `.ci/lib/devbox.sh:283-291`: `http://<slug>[-<suffix>].localhost:8090`.

        The slug defaults to the CONTAINER's name, never a recomputed one: printing a URL this checkout would use, for a container hosted under another name, is the exact lie the parameter exists to prevent. That default is why this is not a pure function, and why a failing `docker ps` ends it (now with a message: Rule T fix D7).
        """
        suffix = self._opt(argv, 0)
        slug = self._opt(argv, 1)
        if not slug:
            status, slug = self.sub(self.slug_active)
            self.checked(status)
        if suffix:
            slug = slug + "-" + suffix
        self.write("http://%s.%s:%d\n" % (slug, DEVBOX_DOMAIN, DEVBOX_PROXY_PORT))
        return 0

    # ------------------------------------------------------------------ REVERSE PROXY (one per machine, shared by every worktree)

    def network_ensure(self, *_argv: str) -> int:
        """`devbox_network_ensure`, `.ci/lib/devbox.sh:297-303`: inspect, else create. The create's status is the function's."""
        d = self.docker_words()
        if self.run([*d, "network", "inspect", DEVBOX_NETWORK], out=NULL, err=NULL)[0] == 0:
            return 0
        self.log("step", "Creating docker network %s" % DEVBOX_NETWORK)
        return self.run([*d, "network", "create", DEVBOX_NETWORK], out=NULL)[0]

    def proxy_running(self, *_argv: str) -> int:
        """`devbox_proxy_running`, `.ci/lib/devbox.sh:305-309`: `.State.Running` is exactly `true`."""
        d = self.docker_words()
        _, running = self.value(
            [*d, "inspect", "-f", "{{.State.Running}}", DEVBOX_PROXY_NAME], err=NULL
        )
        return 0 if running == "true" else 1

    def proxy_ensure(self, *_argv: str) -> int:
        """`devbox_proxy_ensure`, `.ci/lib/devbox.sh:311-354`: the one traefik per machine, started and answering.

        A stopped leftover is STARTED rather than fought over by name; when that start fails the function falls through to `docker run`, which then fails on the name. The docker provider reads labels off the containers themselves, so adding a worktree needs no proxy config change; `exposedByDefault=false` means a container is only routed when it opts in with `traefik.enable=true`.
        The readiness probe is thirty rounds of `curl` then `sleep 1`: ANY HTTP answer counts, because a 404 is a healthy traefik with no matching route while connection refused is not. On timeout the last twenty log lines go to stderr.
        """
        d = self.docker_words()
        if self.cond(self.network_ensure) != 0:
            return 1
        if self.cond(self.proxy_running) == 0:
            return 0
        if (
            self.run([*d, "inspect", DEVBOX_PROXY_NAME], out=NULL, err=NULL)[0] == 0
            and self.run([*d, "start", DEVBOX_PROXY_NAME], out=NULL)[0] == 0
        ):
            return 0
        self.log("step", "Starting the devbox proxy on :%d" % DEVBOX_PROXY_PORT)
        argv = [
            *d,
            "run",
            "-d",
            "--name",
            DEVBOX_PROXY_NAME,
            "--restart",
            "unless-stopped",
            "--network",
            DEVBOX_NETWORK,
            "-p",
            "%d:80" % DEVBOX_PROXY_PORT,
            "-v",
            "/var/run/docker.sock:/var/run/docker.sock:ro",
            DEVBOX_PROXY_IMAGE,
            "--providers.docker=true",
            "--providers.docker.exposedByDefault=false",
            "--providers.docker.network=%s" % DEVBOX_NETWORK,
            "--entrypoints.web.address=:80",
            "--log.level=WARN",
        ]
        if self.run(argv, out=NULL)[0] != 0:
            self.log("error", "Could not start the devbox proxy")
            return 1
        for _ in range(30):
            probe = [
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "--max-time",
                "2",
                "http://127.0.0.1:%d/" % DEVBOX_PROXY_PORT,
            ]
            if self.run(probe)[0] == 0:
                return 0
            self.checked(self.run(["sleep", "1"])[0])
        self.log("error", "Proxy started but is not answering on :%d" % DEVBOX_PROXY_PORT)
        self.run([*d, "logs", "--tail", "20", DEVBOX_PROXY_NAME], out=TO_ERR)
        return 1

    def proxy_stop(self, *_argv: str) -> int:
        """`devbox_proxy_stop`, `.ci/lib/devbox.sh:356-364`: a proxy that is not running is a WARNING and status 0; a failed stop is the stop's status."""
        d = self.docker_words()
        if self.cond(self.proxy_running) != 0:
            self.log("warn", "Proxy is not running")
            return 0
        status = self.run([*d, "stop", DEVBOX_PROXY_NAME], out=NULL)[0]
        if status == 0:
            self.log("info", "Proxy stopped")
        return status

    # ------------------------------------------------------------------ IMAGE

    def image_present(self, *_argv: str) -> int:
        """`devbox_image_present`, `.ci/lib/devbox.sh:370-374`."""
        d = self.docker_words()
        return self.run([*d, "image", "inspect", DEVBOX_IMAGE], out=NULL, err=NULL)[0]

    def image_digest(self, *_argv: str) -> int:
        """`devbox_image_digest`, `.ci/lib/devbox.sh:376-380`: the first repo digest, or `unknown`; whatever a FAILING inspect printed stays in front of the `unknown`."""
        d = self.docker_words()
        status = self.run(
            [*d, "image", "inspect", "--format", "{{index .RepoDigests 0}}", DEVBOX_IMAGE], err=NULL
        )[0]
        if status != 0:
            self.write("unknown\n")
        return 0

    def ensure_image(self, *argv: str) -> int:
        """`devbox_ensure_image`, `.ci/lib/devbox.sh:382-409`: present (and not forced), else pull, else build; then `ensure_uid_image` in every arm that obtained the base.

        ghcr.io/rediacc/* is private. A GitHub token needs the read:packages scope to pull it -- repo+workflow is NOT enough, and the registry's only signal is the word "denied", which reads like the image does not exist. So a failed pull explains that and falls back to building from .devcontainer/Dockerfile, and the build's status is the function's.
        """
        force_pull = self._opt(argv, 0, "false")
        d = self.docker_words()
        if self.cond(self.image_present) == 0 and force_pull != "true":
            self.log("debug", "Image present: %s" % DEVBOX_IMAGE)
            return self.checked(self.ensure_uid_image())
        self.log("step", "Pulling %s" % DEVBOX_IMAGE)
        self.log(
            "info",
            "This image carries node, go, playwright deps and a desktop; the first pull is several GB and takes a while.",
        )
        if self.run([*d, "pull", DEVBOX_IMAGE])[0] == 0:
            return self.checked(self.ensure_uid_image())
        self.log("warn", "Could not pull %s" % DEVBOX_IMAGE)
        self.log(
            "info",
            "That registry is private. To pull it, a GitHub token needs the read:packages scope:",
        )
        self.log("info", "    echo $PAT | docker login ghcr.io -u <user> --password-stdin")
        self.log(
            "info", "Falling back to building the image locally from .devcontainer/Dockerfile."
        )
        if self.cond(self.build_image) != 0:
            return 1
        return self.checked(self.ensure_uid_image())

    def build_image(self, *_argv: str) -> int:
        """`devbox_build_image`, `.ci/lib/devbox.sh:413-429`: build the devcontainer image from source.

        The fallback for a machine with no registry access. Slower than a pull (this Dockerfile installs a Go toolchain, Node, a desktop and Playwright deps), but it needs no credentials, which is the whole point. The Dockerfile is looked for under the MOUNT ROOT, so a linked worktree builds from its main checkout's `.devcontainer`.
        """
        d = self.docker_words()
        status, root = self.sub(self.mount_root)
        self.checked(status)
        dockerfile_dir = root + "/.devcontainer"
        if not os.path.isfile(dockerfile_dir + "/Dockerfile"):
            self.log("error", "No Dockerfile at %s" % dockerfile_dir)
            return 1
        # NPM_BEFORE: the release-age cutoff the Dockerfile's `npm install -g` lines require (an empty one fails the build). `.ci/lib/devbox.sh` asks the same module through its `npm-before` verb.
        npm_before = release_age.npm_before()
        self.log("step", "Building %s locally (this takes a while)" % DEVBOX_IMAGE)
        build = [
            *d,
            "build",
            "-t",
            DEVBOX_IMAGE,
            "--build-arg",
            "NPM_BEFORE=%s" % npm_before,
            "-f",
            dockerfile_dir + "/Dockerfile",
            dockerfile_dir,
        ]
        if self.run(build)[0] != 0:
            self.log("error", "Local image build failed")
            return 1
        self.log("info", "Built %s" % DEVBOX_IMAGE)
        return 0

    # ------------------------------------------------------------------ THE RUN IMAGE

    def base_user_ids(self, *_argv: str) -> int:
        """`devbox_base_user_ids`: vscode's `<uid>:<gid>` in the base image, from its own /etc/passwd.

        `entry="$($d run --rm --entrypoint getent "$DEVBOX_IMAGE" passwd vscode)" || return 1`, then `IFS=: read -r _ _ uid gid _ <<<"$entry"`: the FIRST line, split on colons, the fourth variable taking only its own field because a fifth follows it. Status 1 when either id is empty.
        """
        d = self.docker_words()
        status, entry = self.value(
            [*d, "run", "--rm", "--entrypoint", "getent", DEVBOX_IMAGE, "passwd", "vscode"]
        )
        if status != 0:
            return 1
        fields = entry.split("\n", 1)[0].split(":", 4)
        uid = fields[2] if len(fields) > 2 else ""
        gid = fields[3] if len(fields) > 3 else ""
        if not uid or not gid:
            return 1
        self.write("%s:%s\n" % (uid, gid))
        return 0

    def uid_image(self, *_argv: str) -> int:
        """`devbox_uid_image`: `<DEVBOX_UID_IMAGE_REPO>:uid<UID>-gid<GID>-<base image id, 12>-<Dockerfile.uid sha256, 12>`.

        Keyed on the base's IMAGE ID, so a re-pulled base re-derives, and on the recipe's hash, so an edited `Dockerfile.uid` re-derives too. The twin hashes with a `python3 -c` hashlib one-liner; that is reimplemented here with hashlib rather than shelled out, as `tr` and `sed` are. A missing recipe is a logged refusal, checked before any hashing.
        """
        d = self.docker_words()
        status, base_id = self.value([*d, "image", "inspect", "--format", "{{.Id}}", DEVBOX_IMAGE])
        if status != 0:
            return 1
        base_id = base_id.removeprefix("sha256:")
        if not base_id:
            return 1
        status, root = self.sub(self.mount_root)
        self.checked(status)
        recipe = root + "/.devcontainer/Dockerfile.uid"
        if not os.path.isfile(recipe):
            self.log("error", "No derive recipe at %s" % recipe)
            return 1
        with open(recipe, "rb") as handle:
            recipe_hash = hashlib.sha256(handle.read()).hexdigest()
        self.write(
            "%s:uid%d-gid%d-%s-%s\n"
            % (DEVBOX_UID_IMAGE_REPO, os.geteuid(), os.getegid(), base_id[:12], recipe_hash[:12])
        )
        return 0

    def host_ids(self) -> str:
        """`$(id -u):$(id -g)`, the EFFECTIVE ids."""
        return "%d:%d" % (os.geteuid(), os.getegid())

    def run_image(self, *_argv: str) -> int:
        """`devbox_run_image`: the base when its vscode already carries this host's ids, else the derived tag. Resolves; never builds."""
        status, ids = self.sub(self.base_user_ids)
        if status != 0:
            return 1
        if ids == self.host_ids():
            self.write(DEVBOX_IMAGE + "\n")
            return 0
        return self.uid_image()

    def ensure_uid_image(self, *_argv: str) -> int:
        """`devbox_ensure_uid_image`: build the derived tag from `.devcontainer/Dockerfile.uid` when it is needed and absent; skip when the ids match; reuse a present tag."""
        d = self.docker_words()
        status, image = self.sub(self.run_image)
        if status != 0:
            self.log(
                "error",
                "Could not resolve the devbox run image from %s (reading vscode's ids, or its image id, failed)"
                % DEVBOX_IMAGE,
            )
            return 1
        if image == DEVBOX_IMAGE:
            self.log(
                "debug",
                "%s already runs vscode as %s; nothing to derive" % (DEVBOX_IMAGE, self.host_ids()),
            )
            return 0
        if self.run([*d, "image", "inspect", image], out=NULL, err=NULL)[0] == 0:
            self.log("debug", "Derived image present: %s" % image)
            return 0
        status, root = self.sub(self.mount_root)
        self.checked(status)
        dockerfile_dir = root + "/.devcontainer"
        self.log(
            "step",
            "Deriving %s (vscode renumbered to %s, once per base image)" % (image, self.host_ids()),
        )
        build = [
            *d,
            "build",
            "-t",
            image,
            "--build-arg",
            "BASE=" + DEVBOX_IMAGE,
            "--build-arg",
            "HOST_UID=%d" % os.geteuid(),
            "--build-arg",
            "HOST_GID=%d" % os.getegid(),
            "-f",
            dockerfile_dir + "/Dockerfile.uid",
            dockerfile_dir,
        ]
        if self.run(build)[0] != 0:
            self.log("error", "Deriving %s failed" % image)
            return 1
        self.log("info", "Built %s" % image)
        return 0

    # ------------------------------------------------------------------ CONTAINER

    def container_id(self, *_argv: str) -> int:
        """`devbox_container_id`, `.ci/lib/devbox.sh:438-442`: this worktree's container, found by LABEL, first line only.

        By label and not by name: two different checkouts can each contain a worktree called 0824-1, and the daemon is the truth while the state file is only a cache. The status is `docker ps`'s through pipefail, and a failure is NAMED on stderr (Rule T fix D7): the twin's bare callers ended silently with that status.
        """
        d = self.docker_words()
        status, listing = self.run(
            [*d, "ps", "-aq", "--filter", "label=%s=%s" % (DEVBOX_LABEL_KEY, self.worktree_path())],
            out=CAPTURE,
            err=NULL,
        )
        if status != 0:
            # Rule T fix D7: the twin ended every bare caller of this function SILENTLY with docker's status.
            self.log(
                "error",
                "docker ps failed (exit %d); cannot look up this worktree's devbox container"
                % status,
            )
        cut = listing.find("\n")
        self.write(listing if cut < 0 else listing[: cut + 1])
        return status

    def container_running(self, *argv: str) -> int:
        """`devbox_container_running [cid]`: a caller that already resolved the id passes it, saving the `docker ps`."""
        d = self.docker_words()
        cid = self._opt(argv, 0)
        if not cid:
            status, cid = self.sub(self.container_id)
            self.checked(status)
        if not cid:
            return 1
        _, running = self.value([*d, "inspect", "-f", "{{.State.Running}}", cid], err=NULL)
        return 0 if running == "true" else 1

    def bind_if_present(self, *argv: str) -> int:
        """`_devbox_bind_if_present`, `.ci/lib/devbox.sh:452-463`: a `-v` pair, one word per line, only when the source exists.

        Docker CREATES a missing source as a root-owned directory on the host, which is how a bind mount silently turns into an unwritable ~/.claude. `-e` follows symlinks, so a dangling link is absent.
        """
        src = self._req(argv, 0)
        dst = self._req(argv, 1)
        mode = self._opt(argv, 2)
        if not os.path.exists(src):
            return 0
        self.write("-v\n%s:%s%s\n" % (src, dst, ":" + mode if mode else ""))
        return 0

    def script_binds(self, *_argv: str) -> int:
        """`devbox_script_binds`, `.ci/lib/devbox.sh:468-475`: `SCRIPT_BINDS`, one per line."""
        self.write("".join(pair + "\n" for pair in SCRIPT_BINDS))
        return 0

    def home_binds(self, *_argv: str) -> int:
        """`devbox_home_binds`, `.ci/lib/devbox.sh:478-490`: `HOME_BINDS`, one per line."""
        self.write("".join(pair + "\n" for pair in HOME_BINDS))
        return 0

    @staticmethod
    def make_lease_dir(path: str) -> bool:
        """`mkdir -m 700 <path>`: exactly the one directory, mode 700 whatever the umask; False when it cannot be made."""
        try:
            os.mkdir(path, 0o700)
            os.chmod(path, 0o700)
        except OSError:
            return False
        return True

    def core_lease_src(self, *_argv: str) -> int:
        """`devbox_core_lease_src`, `.ci/lib/devbox.sh` (commit 606f7daac): the host directory of the machine-wide core lease pool, `/run/user/<uid>/rediacc-cores`.

        Printed only when `/run/user/<uid>` is a directory this user owns (a systemd host); nothing otherwise. Status 0 on every path.
        """
        runtime = "/run/user/%d" % os.geteuid()
        with contextlib.suppress(OSError):
            if os.path.isdir(runtime) and os.stat(runtime).st_uid == os.geteuid():
                self.write(runtime + "/rediacc-cores\n")
        return 0

    def missing_binds(self, *_argv: str) -> int:
        """`devbox_missing_binds`, `.ci/lib/devbox.sh:492-513`: each bind destination the existing container does NOT have mounted.

        Every script bind, plus every home bind whose host source exists NOW (one created on the host after the container was, such as .config/rediacc/bws-access-token, is drift too). Empty when there is no container, or when docker cannot inspect it: an unanswerable probe must never be the reason a container is destroyed. Status 0 on every path the loops can take.
        """
        d = self.docker_words()
        status, cid = self.sub(self.container_id)
        self.checked(status)
        if not cid:
            return 0
        status, mounts = self.value(
            [*d, "inspect", "-f", '{{range .Mounts}}{{.Destination}}{{"\\n"}}{{end}}', cid],
            err=NULL,
        )
        if status != 0 or not mounts:
            return 0
        present = mounts.split("\n")
        for pair in SCRIPT_BINDS:
            dest = pair.split(":", 1)[1]
            if dest not in present:
                self.write(dest + "\n")
        home = self.env.get("HOME", "")
        for pair in HOME_BINDS:
            relative = pair.split(":", 1)[0]
            if not os.path.exists(home + "/" + relative):
                continue
            dest = DEVBOX_CONTAINER_HOME + "/" + relative
            if dest not in present:
                self.write(dest + "\n")
        status, lease_src = self.sub(self.core_lease_src)
        self.checked(status)
        if lease_src and DEVBOX_CORE_LEASE_DEST not in present:
            self.write(DEVBOX_CORE_LEASE_DEST + "\n")
        return 0

    def service_process_alive(self, *argv: str) -> int:
        """`devbox_service_process_alive <pattern>`: a process matching it is alive INSIDE the devbox.

        Used only to word a 502 and to decide whether a 502 is worth waiting on; never to call a service healthy, which is the port probe's job.
        """
        pattern = self._req(argv, 0)
        if not pattern:
            return 1
        status, cid = self.sub(self.container_id)
        self.checked(status)
        if not cid:
            return 1
        d = self.docker_words()
        return self.run([*d, "exec", cid, "pgrep", "-f", pattern], out=NULL, err=NULL)[0]

    def route_specs(self, *_argv: str) -> int:
        """`_devbox_route_specs`: the four routed services, one line each carrying the colon-separated fields key, label, suffix, hint, pattern."""
        for spec in ROUTE_SPECS:
            self.write(":".join(spec) + "\n")
        return 0

    def probe_services(self, *argv: str) -> int:
        """`_devbox_probe_services <slug> <hosts>`: one probe round, one line per service carrying the colon-separated fields key, label, suffix, hint, pattern, code, routed, starting.

        The twin fires the four curls CONCURRENTLY (background subshells writing to a `mktemp -d`), so their order in a transcript is not fixed; this port fires them in table order and the differential driver sorts that one run of probe calls on both sides. Everything after the curls is sequential in both: the `pgrep` behind a 502 is asked in table order.
        A probe that cannot reach a route reports `000` (`|| true` inside the substitution), never an abort.
        """
        slug = self._req(argv, 0)
        hosts = self._req(argv, 1)
        codes: dict[str, str] = {}
        for key, _label, suffix, _hint, _pattern in ROUTE_SPECS:
            host = "%s%s.%s" % (slug, "-" + suffix if suffix else "", DEVBOX_DOMAIN)
            _, code = self.value(
                [
                    "curl",
                    "-s",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "--max-time",
                    "3",
                    "-H",
                    "Host: %s" % host,
                    "http://127.0.0.1:%d/" % DEVBOX_PROXY_PORT,
                ],
                err=NULL,
            )
            codes[key] = code or "000"
        routers = hosts.split("\n")
        for key, label, suffix, hint, pattern in ROUTE_SPECS:
            host = "%s%s.%s" % (slug, "-" + suffix if suffix else "", DEVBOX_DOMAIN)
            code = codes[key]
            routed = "yes" if host in routers else "no"
            starting = "no"
            if code == "502" and self.cond(self.service_process_alive, pattern) == 0:
                starting = "yes"
            self.write(
                "%s:%s:%s:%s:%s:%s:%s:%s\n"
                % (key, label, suffix, hint, pattern, code, routed, starting)
            )
        return 0

    def clock(self) -> int:
        """Bash `SECONDS`: whole seconds on a monotonic clock. A method so a test can replace it."""
        return int(time.monotonic())

    def await_ready(self, *argv: str) -> int:
        """`devbox_await_ready [cid]`: wait, with an on-screen cycle, until no route is a 502 in front of a live backend.

        That is exactly the state `route_label` words as "not serving yet", and the one `devbox_up` used to report the instant it (re)dispatched a container, though Astro's content sync alone measured 114.8s on an arm64 Crostini box. VS Code and the terminal never sit in it, so in practice this waits on Account and Database.
        NEVER FAILS: it returns 0 whether the routes converge, the container stops, or the ceiling passes, because a slow but healthy service must not turn `devbox_up` into a failure. Past `DEVBOX_READY_NOMINAL_S` (90) it says so once and keeps going; at `DEVBOX_READY_CEILING_S` (300) it stops waiting.
        A spinner on a terminal (stderr a tty, NO_COLOR unset, not CI); otherwise one plain line every ten seconds. `sleep 1` is the external the transcript records.
        """
        from rediacc_ci.core.common import is_ci  # noqa: PLC0415 -- only this method needs it

        cid = self._opt(argv, 0)
        if not cid:
            status, cid = self.sub(self.container_id)
            self.checked(status)
        if not cid:
            return 0
        status, labels = self.sub(self.container_labels, cid)
        self.checked(status)
        status, slug = self.sub(self.slug_active, labels)
        self.checked(status)
        status, hosts = self.sub(self.router_hosts, labels)
        self.checked(status)
        nominal_text = self.env.get("DEVBOX_READY_NOMINAL_S") or str(READY_NOMINAL_S)
        ceiling_text = self.env.get("DEVBOX_READY_CEILING_S") or str(READY_CEILING_S)
        nominal = decimal(nominal_text)
        ceiling = decimal(ceiling_text)
        start = self.clock()
        announced = False
        last_plain = -10
        frame = 0
        interactive = _isatty(self.stderr) and not self.env.get("NO_COLOR") and not is_ci(self.env)
        clear = "\r%s\r" % (" " * 60)
        while True:
            pending: list[str] = []
            _, listing = self.sub(self.probe_services, slug, hosts)
            for line in listing.split("\n"):
                key, label, _suffix, _hint, _pattern, code, _routed, starting = (
                    line.split(":", 7) + [""] * 8
                )[:8]
                if key and code == "502" and starting == "yes":
                    pending.append(label)
            if not pending:
                if interactive:
                    self.write(clear, self.stderr)
                return 0
            if self.cond(self.container_running, cid) != 0:
                if interactive:
                    self.write(clear, self.stderr)
                self.log(
                    "warn", "Devbox container stopped while waiting for: %s" % " ".join(pending)
                )
                return 0
            elapsed = self.clock() - start
            if elapsed >= ceiling:
                if interactive:
                    self.write(clear, self.stderr)
                self.log(
                    "warn",
                    "%s still not serving after %ss; giving up waiting (not failing)"
                    % (" ".join(pending), ceiling_text),
                )
                return 0
            if elapsed >= nominal and not announced:
                self.log(
                    "warn",
                    "%s is slower than %ss on this machine; still starting"
                    % (" ".join(pending), nominal_text),
                )
                self.log("info", "Set DEVBOX_READY_NOMINAL_S to raise the initial budget")
                announced = True
            if interactive:
                frame = (frame + 1) % len(SPINNER)
                self.write(
                    "\r%s waiting for: %s (%ss)  " % (SPINNER[frame], ",".join(pending), elapsed),
                    self.stderr,
                )
            elif elapsed - last_plain >= 10:
                self.log("step", "Still waiting for: %s (%ss)" % (",".join(pending), elapsed))
                last_plain = elapsed
            self.checked(self.run(["sleep", "1"])[0])

    def autostart_dispatch(self, *_argv: str) -> int:
        """`devbox_autostart_dispatch`: re-run the service autostart inside a container that is ALREADY UP.

        Autostart used to run only on a container-lifecycle event, so a service that died mid-life stayed dead and `devbox up` could only print a hint. Safe unconditionally: the script no-ops for every service already answering on its port and honours DEVBOX_AUTOSTART=0.
        THE CONTAINER'S OWN workspace (its `DEVBOX_WORKSPACE`), not this shell's, and the WORKSPACE copy of the script rather than the single-file bind, which docker pins to a stale inode. `-u vscode` by name. Never fatal; every output line is logged indented.
        """
        status, cid = self.sub(self.container_id)
        self.checked(status)
        if not cid:
            return 0
        d = self.docker_words()
        _, environment = self.run(
            [*d, "inspect", cid, "--format", ENV_FORMAT], out=CAPTURE, err=NULL
        )
        picked = [
            line.split("=", 1)[1]
            for line in environment.split("\n")
            if line.startswith("DEVBOX_WORKSPACE=")
        ]
        workspace = "\n".join(picked).rstrip("\n")
        if not workspace:
            status, workspace = self.sub(self.worktree)
            self.checked(status)
        status, base_port = self.sub(self.base_port, err=NULL)
        self.checked(status)
        script = workspace + "/.devcontainer/devbox-autostart.sh"
        forwarded = ["-e", "DEVBOX_WORKSPACE=%s" % workspace]
        if base_port:
            base = decimal(base_port)
            forwarded += ["-e", "DEVBOX_DB_PORT=%d" % (base + DEVBOX_OFFSET_STUDIO)]
            forwarded += ["-e", "DEVBOX_TERM_PORT=%d" % (base + DEVBOX_OFFSET_TERM)]
        _, output = self.run(
            [*d, "exec", "-u", "vscode", *forwarded, cid, "bash", script], out=CAPTURE, err=TO_OUT
        )
        for line in complete_lines(output):
            if line:
                self.log("info", "  %s" % line)
        return 0

    def _destroy_banner(self, closing: str) -> None:
        """The four lines `devbox_up` prints before it destroys a container, `.ci/lib/devbox.sh:547-551` and `:573-577`."""
        self.log("info", "  container:  %s" % self.sub(self.container_name)[1])
        self.log(
            "info",
            "  killed:     anything running inside it (account dev, VS Code sessions, agents)",
        )
        self.log("info", "  kept:       the repo itself -- it is a bind mount from the host")
        self.log("info", closing)

    def up(self, *argv: str) -> int:
        """`devbox_up`, `.ci/lib/devbox.sh:515-879`: rehost on drift, rebind on drift, reuse, start, or create.

        REHOST ON DRIFT. The routers are baked at `docker run`, so a container created on another branch keeps serving the old hostname forever. It is recreated, with two guards: say exactly what is about to be destroyed BEFORE destroying it (the container may be running `account dev`, a VS Code session, or an agent), and never rehost while `devbox_branch` is EMPTY.
        Mid-rebase and detached HEAD both drift the name to the basename fallback, and churning the container back and forth across a rebase is worse than a stale URL. `--no-rehost` (the positional flag, also `false`/`no`) and `DEVBOX_NO_REHOST=1|true` are the opt-out, honoured from either side.
        RECREATE ON BIND DRIFT, under the same guard and opt-out as the hostname: without it, a bind added to `devbox_script_binds` never reaches an existing container, because "already running" returns early and `docker start` keeps the old mount table.

        THE CREATE PATH, in the twin's order: image, proxy, base port, mount root, workspace, name, docker gid, kvm gid, tun, the bind list, the slug and its conflict refusal, the labels, `docker run`, the state file, then sixty rounds of an HTTP probe through the proxy with the Host header.
        `is_port_in_use` is useless for that probe: docker-proxy binds the published port the instant the container starts, so the port is "in use" even when the process inside crashed on startup. An HTTP response through the proxy is the only honest readiness signal.

        KVM PASSTHROUGH IS CONDITIONAL, AND THE GID IS DERIVED. Until 2026-09-07 this `docker run` passed no `--device` at all, so a devbox on a KVM-capable host had NO /dev/kvm and `rdc ops` could never boot a VM inside it, though the image has shipped qemu-kvm, libvirt-daemon-system, virtinst and dnsmasq-base since the beginning (.devcontainer/Dockerfile:148-155).
        `--device` reproduces the host's owning GROUP inside the container, not the container's own `kvm` group: measured, the host device is gid 991 while the image's `kvm` group is gid 105, so `usermod -aG kvm vscode` grants NOTHING on the bound node and start-kvm.sh papered over that with a world-writable `sudo chmod 0666 /dev/kvm`. Adding the HOST gid needs no sudo and widens nothing beyond what the host models.
        libvirt's default network is a NAT bridge: starting it needs NET_ADMIN, and it ALSO writes the per-bridge sysctl `/proc/sys/net/ipv6/conf/virbr0/disable_ipv6`, which no capability can grant because docker mounts /proc/sys read-only. SYS_ADMIN plus a remount in start-kvm.sh is how /proc/sys becomes writable.
        Operator ruling 2026-09-07, on measurements: `--security-opt systempaths=unconfined` works with no capability but flips /proc/sysrq-trigger and /proc/sys/kernel/core_pattern to WRITABLE (a host reboot and a documented container-escape vector); `--cap-add SYS_ADMIN` + remount keeps docker's /proc masks; `--privileged` is strictly wider and buys nothing.
        Two unprivileged routes were tried and refuted: network XML with ipv6="yes" (0 active; libvirt writes the sysctl regardless) and `--sysctl net.ipv6.conf.{all,default}.disable_ipv6=1` (0 active). The minimum was measured: NET_ADMIN+NET_RAW+unconfined 1 active, NET_ADMIN+unconfined 1 active, no caps+unconfined 0 active, so NET_RAW was dropped.
        /dev/net/tun IS A SECOND DEVICE (found 2026-09-07: with /dev/kvm bound and the network ACTIVE, `./rdc.sh ops up --basic` still died in virt-install with "Unable to open /dev/net/tun"), gated on the node existing rather than on the kvm gid because they are separate host facts. NO `--group-add` for it: the host's tun is 0666 root:root, and adding its gid would mean adding gid 0.

        THE BIND LIST. The repo at its IDENTICAL path, non-negotiable: worktree gitdir links are absolute, and a nested `docker -v $(pwd)` is resolved by the host daemon, so only an identical path is correct in both. The tracked scripts read-only from `devbox_script_binds`, bound rather than baked because they are edited far more often than the image is rebuilt.
        Missing the autostart bind is silent -- the entrypoint's `[ -x "$AUTOSTART" ]` guard turns "not there" into "autostart disabled". start-ttyd.sh is ALSO baked into the image, and binding it anyway is what made a stale August 23 copy (whose idempotency guard read a PID file nothing wrote) visible. The docker socket when it is a socket, then the named home files.

        THE SLUG CONFLICT IS A REFUSAL, NOT A SUFFIX. The slug names the ROUTERS and SERVICES, not just the Host rules, so a duplicate is two definitions of one router, and traefik drops one at --log.level=WARN with nothing on stdout. An automatic suffix would silently destroy the memorable URL the change exists for.
        THE LABELS. The account gateway is the ONLY app door (marketing site at /, portal at /account/, API at /account/api/); a second hostname pointed straight at Astro 404'd on /account. The database route serves sqlite_web from the same origin, so there is no hosted third-party page and no Local Network Access permission to grant.
        ttyd's terminal is a WebSocket upgrade that traefik v3 proxies with no middleware, and a BROKEN upgrade still answers 200 on `/`, so only a browser can see it. The container publishes on 0.0.0.0 inside the proxy's network: on ChromeOS the browser is outside the VM and reaches it by address.

        Rule T fixes D1 (the docker group), D6 (octal base port) and D9 (the silent start failure) all live in this function.
        """
        # One `docker version` for the whole run, seeded in the PARENT so every `d="$(devbox_docker)"` below inherits it.
        self.docker_init()
        force_pull = self._opt(argv, 0, "false")
        rehost = self._opt(argv, 1) not in ("--no-rehost", "false", "no")
        if self.env.get("DEVBOX_NO_REHOST", "") in ("1", "true"):
            rehost = False
        d = self.docker_words()

        status, cid = self.sub(self.container_id)
        self.checked(status)
        if cid:
            status, want = self.sub(self.slug)
            self.checked(status)
            status, baked = self.sub(self.slug_active)
            self.checked(status)
            status, branch = self.sub(self.branch)
            self.checked(status)
            if branch and baked and baked != want:
                drift = "Hostname drift: the container serves %s.%s, this checkout is now %s.%s" % (
                    baked,
                    DEVBOX_DOMAIN,
                    want,
                    DEVBOX_DOMAIN,
                )
                if not rehost:
                    self.log("warn", drift)
                    self.log(
                        "info", "--no-rehost given: leaving it alone. Its URLs keep the OLD name."
                    )
                else:
                    self.log("warn", drift)
                    self.log(
                        "warn",
                        "About to DESTROY and recreate this container so the URL matches the branch:",
                    )
                    self._destroy_banner(
                        "  keep the old hostname instead: DEVBOX_NO_REHOST=1 ./run.sh devbox up"
                    )
                    if self.cond(self.remove) != 0:
                        return 1
                    cid = ""

        if cid:
            status, missing = self.sub(self.missing_binds)
            self.checked(status)
            if missing:
                self.log("warn", "Bind drift: the container predates these bind mounts:")
                for line in missing.split("\n"):
                    self.log("info", "  %s" % line)
                if not rehost:
                    self.log(
                        "info",
                        "--no-rehost given: leaving it alone. Those files stay absent inside it.",
                    )
                else:
                    self.log("warn", "About to DESTROY and recreate this container to add them:")
                    self._destroy_banner(
                        "  keep the container as it is instead: DEVBOX_NO_REHOST=1 ./run.sh devbox up"
                    )
                    if self.cond(self.remove) != 0:
                        return 1
                    cid = ""

        if self.cond(self.container_running) == 0:
            self.log("info", "Devbox already running for this worktree")
            # CONVERGE ON "EVERY ROUTE ANSWERS", not on "a container exists": revive a dead service, then wait for the routes before the snapshot.
            self.checked(self.autostart_dispatch())
            self.checked(self.await_ready())
            self.checked(self.status())
            return 0

        status, cid = self.sub(self.container_id)
        self.checked(status)
        if cid:
            self.log("step", "Starting existing devbox container")
            status = self.run([*d, "start", cid], out=NULL)[0]
            if status != 0:
                # Rule T fix D9: the twin's bare `docker start` ended here with docker's own words and no explanation of what was being started.
                self.log("error", "Could not start the existing devbox container %s" % cid)
                return status
            self.checked(self.await_ready(cid))
            self.checked(self.status())
            return 0

        if self.cond(self.ensure_image, force_pull) != 0:
            return 1
        status, run_image = self.sub(self.run_image)
        if status != 0:
            self.log("error", "Could not resolve the devbox run image from %s" % DEVBOX_IMAGE)
            return 1
        if self.cond(self.proxy_ensure) != 0:
            return 1

        status, base_port = self.sub(self.base_port)
        if status != 0:
            self.log(
                "error",
                "No free port block in %d-%d" % (DEVBOX_PORT_RANGE_START, DEVBOX_PORT_RANGE_END),
            )
            return 1
        status, mount_root = self.sub(self.mount_root)
        self.checked(status)
        status, workspace = self.sub(self.worktree)
        self.checked(status)
        status, name = self.sub(self.container_name)
        self.checked(status)
        status, group = self.run(["getent", "group", "docker"], out=CAPTURE, err=NULL)
        # `| cut -d: -f3`: the third colon field of every line, the WHOLE line when it has no colon, and pipefail keeps getent's status (Rule T fix D1).
        fields = [
            (line.split(":")[2] if len(line.split(":")) > 2 else "") if ":" in line else line
            for line in all_lines(group)
        ]
        docker_gid = "\n".join(fields).rstrip("\n")
        if status != 0 or not docker_gid:
            # Rule T fix D1: no `docker` group is a warning and an empty gid, the case the `--group-add` guards below were written for. The twin's pipeline took getent's status into errexit and ended `devbox_up` silently.
            self.log(
                "warn",
                "No docker group on this host; the devbox container gets no docker socket access",
            )
            docker_gid = ""

        kvm_gid = ""
        if os.path.exists("/dev/kvm"):
            _, kvm_gid = self.value(["stat", "-c", "%g", "/dev/kvm"], err=NULL)
        tun_dev = "/dev/net/tun" if os.path.exists("/dev/net/tun") else ""

        base = decimal(base_port)
        vscode_port = base + DEVBOX_OFFSET_VSCODE
        studio_port = base + DEVBOX_OFFSET_STUDIO
        term_port = base + DEVBOX_OFFSET_TERM

        binds = ["-v", "%s:%s" % (mount_root, mount_root)]
        for pair in SCRIPT_BINDS:
            source, target = pair.split(":", 1)
            binds += ["-v", "%s/../../.devcontainer/%s:%s:ro" % (self.lib_dir, source, target)]
        with contextlib.suppress(OSError):
            if stat.S_ISSOCK(os.stat("/var/run/docker.sock").st_mode):
                binds += ["-v", "/var/run/docker.sock:/var/run/docker.sock"]
        home = self.env.get("HOME", "")
        for pair in HOME_BINDS:
            relative, mode = pair.split(":", 1)
            _, lines = self.sub(
                self.bind_if_present,
                home + "/" + relative,
                DEVBOX_CONTAINER_HOME + "/" + relative,
                mode,
            )
            binds += [line for line in lines.split("\n") if line]

        lease_env: list[str] = []
        status, lease_src = self.sub(self.core_lease_src)
        self.checked(status)
        if lease_src and (os.path.isdir(lease_src) or self.make_lease_dir(lease_src)):
            binds += ["-v", "%s:%s" % (lease_src, DEVBOX_CORE_LEASE_DEST)]
            lease_env = ["-e", "REDIACC_CORE_LEASE_DIR=%s" % DEVBOX_CORE_LEASE_DEST]

        status, slug = self.sub(self.slug)
        self.checked(status)
        status, conflicts = self.sub(self.slug_conflicts, slug)
        self.checked(status)
        if conflicts:
            self.log(
                "error",
                "The hostname %s.%s is already claimed by another checkout:"
                % (slug, DEVBOX_DOMAIN),
            )
            for line in conflicts.split("\n"):
                if line:
                    self.log("info", "  %s" % line)
            self.log(
                "info",
                "Two checkouts on one branch produce duplicate traefik router names and one route is silently dropped.",
            )
            self.log(
                "info", "Give this checkout its own name: DEVBOX_SLUG=<name> ./run.sh devbox up"
            )
            return 1

        labels = [
            "--label",
            "traefik.enable=true",
            "--label",
            "traefik.docker.network=%s" % DEVBOX_NETWORK,
        ]
        for route, host_suffix, port in (
            ("code", "", vscode_port),
            ("account", "-account", 4800),
            ("db", "-db", studio_port),
            ("term", "-term", term_port),
        ):
            router = "traefik.http.routers.%s-%s" % (slug, route)
            labels += [
                "--label",
                "%s.rule=Host(`%s%s.%s`)" % (router, slug, host_suffix, DEVBOX_DOMAIN),
                "--label",
                "%s.entrypoints=web" % router,
                "--label",
                "%s.service=%s-%s" % (router, slug, route),
                "--label",
                "traefik.http.services.%s-%s.loadbalancer.server.port=%d" % (slug, route, port),
            ]

        self.log("step", "Creating devbox for %s" % workspace)
        self.log("info", "container: %s" % name)
        self.log("info", "hostname:  %s.%s" % (slug, DEVBOX_DOMAIN))
        self.log("info", "image:     %s" % run_image)
        self.log(
            "info",
            "reachable ONLY through the proxy on :%d; the container publishes no ports"
            % DEVBOX_PROXY_PORT,
        )

        run = [
            *d,
            "run",
            "-d",
            "--name",
            name,
            "--label",
            "%s=%s" % (DEVBOX_LABEL_KEY, workspace),
            "--label",
            "%s=%s" % (DEVBOX_SLUG_LABEL_KEY, slug),
            "--restart",
            "unless-stopped",
            "--init",
            "--shm-size=1g",
            "--hostname",
            "%s-devbox" % basename(workspace),
            "--network",
            DEVBOX_NETWORK,
            *labels,
            *binds,
        ]
        if docker_gid:
            run += ["--group-add", docker_gid]
        if kvm_gid:
            run += ["--device", "/dev/kvm"]
        if tun_dev:
            run += ["--device", tun_dev]
        if kvm_gid:
            run += ["--group-add", kvm_gid, "--cap-add", "NET_ADMIN", "--cap-add", "SYS_ADMIN"]
        run += [
            "-e",
            "HOST_UID=%d" % os.geteuid(),
            "-e",
            "HOST_GID=%d" % os.getegid(),
            "-e",
            "DOCKER_GID=%s" % docker_gid,
            "-e",
            "DEVBOX_PORT=%d" % vscode_port,
            "-e",
            "DEVBOX_TERM_PORT=%d" % term_port,
            "-e",
            "DEVBOX_DB_PORT=%d" % studio_port,
            "-e",
            "DEVBOX_WORKSPACE=%s" % workspace,
            "-e",
            "REDIACC_NPM_RUNTIME=devbox",
            "-e",
            "REDIACC_DEV_BIND=0.0.0.0",
            "-e",
            "REDIACC_DEV_PORT_BASE=%d" % ACCOUNT_DEV_PORT,
            *lease_env,
            "-w",
            workspace,
            "--entrypoint",
            "/usr/local/bin/devbox-entrypoint.sh",
            run_image,
        ]
        if self.run(run, out=NULL)[0] != 0:
            self.log("error", "docker run failed")
            return 1

        _, digest = self.sub(self.image_digest)
        self.checked(self.state_write(base_port, name, digest, docker_gid, slug))

        for _ in range(60):
            probe = [
                "curl",
                "-fsS",
                "-o",
                "/dev/null",
                "--max-time",
                "2",
                "-H",
                "Host: %s.%s" % (slug, DEVBOX_DOMAIN),
                "http://127.0.0.1:%d/" % DEVBOX_PROXY_PORT,
            ]
            if self.run(probe, err=NULL)[0] == 0:
                self.checked(self.await_ready())
                self.checked(self.status())
                return 0
            if self.cond(self.container_running) != 0:
                self.log("error", "Devbox container exited during startup. Last output:")
                _, last = self.sub(self.container_id)
                self.run([*d, "logs", "--tail", "30", last], out=TO_ERR)
                return 1
            self.checked(self.run(["sleep", "1"])[0])

        self.log("error", "Devbox started but nothing is listening on %d after 60s" % vscode_port)
        _, last = self.sub(self.container_id)
        self.run([*d, "logs", "--tail", "30", last], out=TO_ERR)
        return 1

    def status(self, *_argv: str) -> int:
        """`devbox_status`, `.ci/lib/devbox.sh:918-1002`: the container, its drift, its conflicts, and a PROBED route table.

        PROBE each route rather than listing URLs and hoping. Traefik answers a bare 502 when a router matches but nothing is listening behind it, and that page names neither the service nor the reason, so an operator reads "Bad Gateway" for a backend that was simply never started, or was started on the HOST instead of inside the devbox.
        The CONTAINER's name is computed once: every URL and every probe Host must be the name its routers actually carry. `|| true` on the probe is load-bearing under `set -e`: curl exits non-zero on a timeout (28) or a refused connection (7), and a probe that cannot reach a route must report "000", not abort the status command (observed as `setup --check` exiting 28).
        Two containers defining one router make every reachability claim dishonest, so a conflict turns every row into "ambiguous". The row is `printf '  %-9s %-46s %s\\n'`, padded by BYTES. Retired twin defect 8 (a failing label inspect killing the command) is retired: the labels are fetched once, `|| true`.
        """
        self.docker_init()
        status, _ = self.sub(self.base_port, err=NULL)
        self.checked(status)
        # The container is resolved ONCE and handed to every helper that would otherwise `docker ps` for it again, and its labels are fetched once for the same reason.
        status, cid0 = self.sub(self.container_id)
        self.checked(status)
        if self.cond(self.container_running, cid0) == 0:
            self.log("info", "Devbox running: %s" % self.sub(self.container_name)[1])
            status, labels = self.sub(self.container_labels, cid0)
            self.checked(status)
            status, active = self.sub(self.slug_active, labels)
            self.checked(status)
            status, wanted = self.sub(self.slug)
            self.checked(status)
            _, recorded = self.sub(self.state_get, "slug", err=NULL)
            status, hosts = self.sub(self.router_hosts, labels)
            self.checked(status)
            status, conflicts = self.sub(self.slug_conflicts, active)
            self.checked(status)
            status, drift = self.sub(self.slug_drift, wanted, active, recorded)
            self.checked(status)
            if drift:
                for line in drift.split("\n"):
                    if line:
                        self.log("warn", line)
                self.log("info", "Rehost it (this DESTROYS the container): ./run.sh devbox up")
            if conflicts:
                self.log(
                    "warn",
                    "Another checkout also claims %s.%s, so traefik has duplicate routers:"
                    % (active, DEVBOX_DOMAIN),
                )
                for line in conflicts.split("\n"):
                    if line:
                        self.log("info", "  %s" % line)
                self.log(
                    "info",
                    "Which container answers is not knowable from here. Give one of them DEVBOX_SLUG=<name>.",
                )
            self.write("\n")
            _, listing = self.sub(self.probe_services, active, hosts)
            for line in listing.split("\n"):
                key, label, suffix, hint, _pattern, code, routed, starting = (
                    line.split(":", 7) + [""] * 8
                )[:8]
                if not key:
                    continue
                link = self.sub(self.url, suffix, active)[1]
                verdict = (
                    "ambiguous -- two checkouts claim this hostname"
                    if conflicts
                    else self.sub(self.route_label, code, hint, routed, starting)[1]
                )
                self.write(
                    b"  "
                    + _pad(label + ":", 9)
                    + b" "
                    + _pad(link, 46)
                    + b" "
                    + _enc(verdict)
                    + b"\n"
                )
            self.write("\n")
            if self.cond(self.proxy_running) != 0:
                self.log("warn", "The proxy is not running, so those hostnames will not resolve.")
                self.log("info", "Start it with: ./run.sh devbox up")
            self.write("  On ChromeOS forward ONE port -- %d -- in\n" % DEVBOX_PROXY_PORT)
            self.write(
                "  Settings > Linux > Port forwarding. Chrome resolves *.localhost itself,\n"
            )
            self.write("  so every worktree and service is reachable through it.\n")
            self.write("\n")
            return 0
        if cid0:
            self.log(
                "warn", "Devbox container exists but is stopped. Start it with: ./run.sh devbox up"
            )
            return 1
        self.log("warn", "No devbox for this worktree. Create it with: ./run.sh setup")
        return 1

    def stop(self, *_argv: str) -> int:
        """`devbox_stop`, `.ci/lib/devbox.sh:1004-1014`: no container is a WARNING and status 0; a failed stop is the stop's status."""
        d = self.docker_words()
        status, cid = self.sub(self.container_id)
        self.checked(status)
        if not cid:
            self.log("warn", "No devbox container for this worktree")
            return 0
        self.log("step", "Stopping devbox")
        status = self.run([*d, "stop", cid], out=NULL)[0]
        if status == 0:
            self.log("info", "Stopped")
        return status

    def remove(self, *_argv: str) -> int:
        """`devbox_remove`, `.ci/lib/devbox.sh:1016-1026`: `docker rm -f`, then `rm -f` the state file, then "Removed", each only after the last succeeded."""
        d = self.docker_words()
        status, cid = self.sub(self.container_id)
        self.checked(status)
        if not cid:
            self.log("warn", "No devbox container for this worktree")
            return 0
        self.log("step", "Removing devbox")
        status = self.run([*d, "rm", "-f", cid], out=NULL)[0]
        if status != 0:
            return status
        status = self.run(["rm", "-f", self.state_file])[0]
        if status != 0:
            return status
        self.log("info", "Removed")
        return 0

    def logs(self, *argv: str) -> int:
        """`devbox_logs`, `.ci/lib/devbox.sh:1028-1038`: `docker logs "${1:---tail=100}" "$cid"`; a second argument is ignored."""
        d = self.docker_words()
        status, cid = self.sub(self.container_id)
        self.checked(status)
        if not cid:
            self.log("error", "No devbox container for this worktree")
            return 1
        return self.run([*d, "logs", self._opt(argv, 0, "--tail=100"), cid])[0]

    def shell(self, *_argv: str) -> int:
        """`devbox_shell`, `.ci/lib/devbox.sh:1040-1053`: `docker exec -it -u vscode -w <worktree> <cid> bash`.

        `-u vscode` BY NAME: the entrypoint has already renumbered `vscode` to the host identity, so the name is right on Linux, macOS (501:20, where gid 20 is dialout) and WSL2, while a numeric id is right only where the host's numbering means something inside the container. The cid is resolved BEFORE the running check, which resolves it again.
        """
        d = self.docker_words()
        status, cid = self.sub(self.container_id)
        self.checked(status)
        if self.cond(self.container_running) != 0:
            self.log("error", "Devbox is not running. Start it with: ./run.sh devbox up")
            return 1
        return self.run(
            [
                *d,
                "exec",
                "-it",
                "-u",
                "vscode",
                "-e",
                "USER=vscode",
                "-e",
                "LOGNAME=vscode",
                "-w",
                self.worktree_path(),
                cid,
                "bash",
            ]
        )[0]

    def exec(self, *argv: str) -> int:
        """`devbox_exec`, `.ci/lib/devbox.sh:1070-1131`: non-interactive exec, the lane every gate routes through.

        -u vscode BY NAME, never `$(id -u):$(id -g)`: exec as root and git refuses the worktree with "dubious ownership", `git ls-files` returns empty, and a gate reports a green over zero files (measured live on 2026-08-25). `-t` ONLY when both stdin and stdout are TTYs: `docker exec -t` allocates a pty, which injects carriage returns, and a piped `--json` gate then fails to parse for reasons that name nothing.
        `bash -lc`, not `bash -c`: PATH for go and node comes from /etc/environment, which only a login shell reads. THE COST, paid for on 2026-09-04: the login shell re-sources the profile AFTER any PATH the caller exported, so a caller-side PATH override runs the IMAGE's tool; to probe another version, invoke its absolute path.
        `devbox_docker` answers TWO WORDS when the docker group is not active yet, and quoting that as one command name produces `sudo docker: command not found` (measured 2026-08-26), so it is split with `read -r -a`.
        TWO CALL SHAPES: one argument is shell syntax and passes verbatim; several are real argv and are re-quoted word by word with `printf '%q '` (on 2026-09-04 joining them with spaces ran `bash -c npm` inside the box and returned npm's exit code, not the gate's). Zero arguments are refused with status 2 (Rule T fix D5): the twin took the second branch and ran `bash -lc "'' "`.
        """
        if not argv:
            # Rule T fix D5: the twin ran `bash -lc "'' "` inside the container for zero arguments.
            self.log("error", "devbox exec needs a command")
            return 2
        d = self.sub(self.docker)[1]
        status, cid = self.sub(self.container_id)
        self.checked(status)
        if self.cond(self.container_running) != 0:
            self.log("error", "Devbox is not running. Start it with: ./run.sh devbox up")
            return 1
        workdir = self.worktree_path()
        flags = ["exec", "-u", "vscode", "-w", workdir]
        stdin_tty = _isatty(self.stdin)
        if stdin_tty:
            flags.append("-i")
        if stdin_tty and _isatty(self.stdout):
            flags.append("-t")
        flags += ["-e", "REDIACC_IN_DEVBOX=1"]
        # docker exec -u sets no USER or LOGNAME, and tools that read them (SSHExecutor, renet InitVM) then fall back to root.
        flags += ["-e", "USER=vscode", "-e", "LOGNAME=vscode"]
        for name in EXEC_FORWARDED_ENV:
            if self.env.get(name, SHELL_DEFAULTS.get(name, "")):
                flags += ["-e", name]
        words = d.split()
        command = (
            argv[0]
            if len(argv) == 1
            else "".join(shell_quote(arg, self.utf8) + " " for arg in argv)
        )
        return self.run([*words, *flags, cid, "bash", "-lc", command])[0]

    # ------------------------------------------------------------------ THE THREE PROBES

    def mount_ok(self, *_argv: str) -> int:
        """`devbox_mount_ok`, `.ci/lib/devbox.sh:1140-1149`: is the repo actually THERE, verified by CONTENT, never by existence.

        macOS Docker Desktop (a path outside its file-sharing list) and WSL2 with Docker Desktop integration both AUTO-CREATE an empty directory for a bind mount whose source they cannot see. The container then has the path, and every gate reads an empty tree.
        """
        status, root = self.sub(self.mount_root)
        self.checked(status)
        command = "test -f '%s/run.sh' && git -C '%s' rev-parse --git-dir" % (
            root,
            self.worktree_path(),
        )
        with self.redirected(out=NULL, err=NULL):
            status = self.cond(self.exec, command)
        if status != 0:
            self.log(
                "error",
                "devbox mount is not usable: %s does not contain this repo inside the container"
                % root,
            )
            self.log(
                "info",
                "On macOS the path must be inside Docker Desktop's file sharing list; on WSL2 use docker-ce inside the distro, not Desktop integration.",
            )
            return 1
        return 0

    def identity_ok(self, *_argv: str) -> int:
        """`devbox_identity_ok`, `.ci/lib/devbox.sh:1151-1166`: is the exec identity one git will accept? The root-exec trap.

        `[ -n "$(printf '%s' "$out" | grep ...)" ]`, not `| grep -q`: $out is `git status --porcelain` over the whole worktree, so it is UNBOUNDED, and losing grep -q's race under an inherited pipefail is silent in the worst direction. Rule T fix D2 is the other half: a devbox that is not running now fails the probe, where the twin swallowed the exec's refusal.
        """
        command = "git -C '%s' status --porcelain" % self.worktree_path()
        status, out = self.sub(self.exec, command, err=TO_OUT)
        if status == 1 and "Devbox is not running" in out:
            # Rule T fix D2: a devbox that is not running has no usable identity. The twin swallowed the refusal and reported success.
            self.log("error", "devbox identity cannot be verified: the devbox is not running")
            return 1
        if "dubious ownership" in out:
            self.log(
                "error", "devbox exec identity is wrong: git refuses the worktree as another user's"
            )
            self.log(
                "info", "Exec as 'vscode' (the entrypoint renumbers it to your uid), never as root."
            )
            return 1
        return 0

    def writable_ok(self, *_argv: str) -> int:
        """`devbox_writable_ok`, `.ci/lib/devbox.sh:1169-1175`: is it writable? colima mounts $HOME read-only unless started with --mount $HOME:w, and every stamp write and formatter then fails EROFS."""
        probe = "%s/.ci/cache/.devbox-write-probe" % self.worktree_path()
        command = "touch '%s' && rm -f '%s'" % (
            probe,
            "%s/.ci/cache/.devbox-write-probe" % self.worktree_path(),
        )
        with self.redirected(out=NULL, err=NULL):
            status = self.cond(self.exec, command)
        if status != 0:
            self.log("error", "devbox cannot write into the repo (read-only mount?)")
            self.log("info", "colima needs: colima start --mount $HOME:w")
            return 1
        return 0

    def doctor(self, *_argv: str) -> int:
        """`devbox_doctor`, `.ci/lib/devbox.sh:1177-1184`: all three probes, every one run even after a failure, then one verdict."""
        status = 0
        if self.cond(self.mount_ok) != 0:
            status = 1
        if self.cond(self.identity_ok) != 0:
            status = 1
        if self.cond(self.writable_ok) != 0:
            status = 1
        if status == 0:
            self.log("info", "devbox is usable: mount, identity and writability all verified")
        return status

    # ------------------------------------------------------------------ one entry point for all fifty-five

    def invoke(self, name: str, argv: list[str] | tuple[str, ...] = ()) -> int:
        """`( set -e; <name> "$@" )`: call a twin function by its BASH name, and return the subshell's status.

        errexit is armed, as it is under every sourcer. A `ShellExit` is the subshell ending; a `DevboxError` is a refusal of an input this port does not reproduce, reported on stderr with status 1 rather than as a traceback.
        """
        method = getattr(self, BASH_NAMES[name])
        self.errexit = True
        try:
            return method(*argv)
        except ShellExit as exc:
            return exc.code
        except DevboxError as exc:
            self.write("%s\n" % exc, self.stderr)
            return exc.code
        finally:
            _flush(self.stdout)
            _flush(self.stderr)


def _enc(text: str) -> bytes:
    return text.encode("utf-8", "surrogateescape")


def _pad(text: str, width: int) -> bytes:
    """`printf '%-Ns'`, padded by BYTES: bash counts bytes for a field width under both `C` and `C.utf8` (measured)."""
    data = _enc(text)
    return data + b" " * max(0, width - len(data))


# The fifty-five, bash name -> `Devbox` attribute. `test_core_devbox.py` asserts this is exactly the set the twin defines.
BASH_NAMES = {
    "devbox_worktree": "worktree",
    "devbox_mount_root": "mount_root",
    "devbox_container_name": "container_name",
    "devbox_docker": "docker",
    "devbox_docker_init": "docker_init",
    "devbox_docker_reset": "docker_reset",
    "devbox_container_labels": "container_labels",
    "devbox_service_process_alive": "service_process_alive",
    "_devbox_route_specs": "route_specs",
    "_devbox_probe_services": "probe_services",
    "devbox_await_ready": "await_ready",
    "devbox_autostart_dispatch": "autostart_dispatch",
    "devbox_state_write": "state_write",
    "devbox_state_get": "state_get",
    "devbox_base_port": "base_port",
    "devbox_branch": "branch",
    "devbox_slugify": "slugify",
    "devbox_slug_basename": "slug_basename",
    "devbox_slug": "slug",
    "devbox_slug_active": "slug_active",
    "devbox_slug_drift": "slug_drift",
    "devbox_slug_conflicts": "slug_conflicts",
    "devbox_router_hosts": "router_hosts",
    "devbox_url": "url",
    "devbox_network_ensure": "network_ensure",
    "devbox_proxy_running": "proxy_running",
    "devbox_proxy_ensure": "proxy_ensure",
    "devbox_proxy_stop": "proxy_stop",
    "devbox_image_present": "image_present",
    "devbox_image_digest": "image_digest",
    "devbox_ensure_image": "ensure_image",
    "devbox_build_image": "build_image",
    "devbox_base_user_ids": "base_user_ids",
    "devbox_uid_image": "uid_image",
    "devbox_run_image": "run_image",
    "devbox_ensure_uid_image": "ensure_uid_image",
    "devbox_container_id": "container_id",
    "devbox_container_running": "container_running",
    "_devbox_bind_if_present": "bind_if_present",
    "devbox_script_binds": "script_binds",
    "devbox_home_binds": "home_binds",
    "devbox_core_lease_src": "core_lease_src",
    "devbox_missing_binds": "missing_binds",
    "devbox_up": "up",
    "devbox_route_label": "route_label",
    "devbox_status": "status",
    "devbox_stop": "stop",
    "devbox_remove": "remove",
    "devbox_logs": "logs",
    "devbox_shell": "shell",
    "devbox_exec": "exec",
    "devbox_mount_ok": "mount_ok",
    "devbox_identity_ok": "identity_ok",
    "devbox_writable_ok": "writable_ok",
    "devbox_doctor": "doctor",
}
