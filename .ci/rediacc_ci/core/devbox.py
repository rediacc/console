"""The three PURE functions of `.ci/lib/devbox.sh`, ported function for function.

PORTED FROM `.ci/lib/devbox.sh` (1184 lines, 42 functions).
The twin still exists, is untouched by this file, and is still sourced at `.ci/legacy/run-legacy.sh:456`, `.ci/rediacc_ci/setup/bridge.py:35` (inside the bridged `bash -c` prelude), `.ci/rediacc_ci/setup/shadow_driver.py:136`, `.ci/rediacc_ci/dev/shadow_driver.py:140` and `.ci/lib/account.sh:1090`. Those five are the real `source` sites; nothing is cut over here.
This is a pre-cutover port on the same sequencing every other lib in this campaign used, and `.ci/rediacc_ci/core/local_common.py` is the worked precedent from the same day: its twin `.ci/lib/local-common.sh` is still sourced at five sites while the port carries a K=5 ledger.

--------------------------------------------------------------------------
WHAT IS HERE AND WHAT IS DELIBERATELY ABSENT
--------------------------------------------------------------------------
THREE FUNCTIONS ARE PORTED, and they are the three whose whole answer is computation over their own arguments: `devbox_slugify` (`:186`), `devbox_slug_drift` (`:242`) and `devbox_route_label` (`:902`). Two of the three say so in the twin's own comments, which this port re-measured rather than believed.

THIRTY-NINE ARE NOT, and saying so here rather than leaving an absence is the point. THERE IS NO PYTHON FUNCTION BELOW FOR ANY OF THEM:

  git-coupled                                           `devbox_worktree:55`, `devbox_branch:176`, `devbox_slug_basename:199` (`basename` of a git-derived path), `devbox_slug:204` (calls `devbox_branch`).
  docker-coupled                                        `devbox_docker:93`, `devbox_container_name:84`, `devbox_container_id:438`, `devbox_container_running:444`, `devbox_slug_active:224`, `devbox_slug_conflicts:255`, `devbox_router_hosts:274`, `devbox_network_ensure:297`, `devbox_proxy_running:305`,
  `devbox_proxy_ensure:311`, `devbox_proxy_stop:356`, `devbox_image_present:370`, `devbox_image_digest:376`, `devbox_ensure_image:382`, `devbox_build_image:413`, `devbox_missing_binds:492`, `devbox_up:515`, `devbox_stop:1004`, `devbox_remove:1016`, `devbox_logs:1028`, `devbox_shell:1040`, `devbox_exec:1070`, `devbox_mount_ok:1140`, `devbox_identity_ok:1151`, `devbox_writable_ok:1169`, `devbox_doctor:1177`.
  filesystem-coupled or port-allocating                 `devbox_mount_root:70`, `devbox_state_write:107`, `devbox_state_get:124`, `devbox_base_port:136` (runs `rediacc_ci.core.ports` as a child), `_devbox_bind_if_present:452`.
  constant data                                         `devbox_script_binds:468` and `devbox_home_binds:480`, the bind lists `devbox_up` and `devbox_missing_binds` both read; nothing but those two docker-coupled readers calls them.
  network-probing                                       `devbox_status:918` curls every route, `devbox_url:283` builds its answer from `devbox_slug_active`.

`devbox_url:283` deserves its own sentence, because it is the near miss: its body is pure string formatting, and its DEFAULT for the slug argument is `devbox_slug_active`, which inspects a running container. A port of it would be pure only for callers that pass both arguments, and a function that is pure on some call paths is not a function this campaign ports.

--------------------------------------------------------------------------
THE PURITY CLAIM WAS DRIVEN, NOT READ
--------------------------------------------------------------------------
All three were run against the live twin before any of this was written, under `LC_ALL=C` and again under `LC_ALL=C.utf8`, with the same corpus and the same answers both times. The whole environment dependency of the three is the presence of `tr` and `sed` on PATH, and the sourcing shell's `set -u`, which is reproduced below rather than assumed away.
Measured 2026-09-23 on this machine: `tr` and `od` are **uutils coreutils 0.8.0**, `sed` is **GNU sed 4.9**, `bash` is **5.3.9**. The differential licence recorded for this port is equivalence against that tool set.

`tr` and `sed` are REIMPLEMENTED here rather than shelled out, which is the opposite of the choice `local_common.py` made for `git` and `sed`.
The reason is the same rule read the other way: a port that piped the twin's own pipeline would be the same program, and its differential would prove nothing. The pipeline is four byte-level rewrites, so reimplementing it is honest work rather than packaging.

--------------------------------------------------------------------------
SEVEN TWIN BEHAVIOURS REPRODUCED ON PURPOSE, NOT FIXED
--------------------------------------------------------------------------
  1. AN EMPTY ANSWER IS STILL A LINE. `devbox_slugify ''` prints one newline and exits 0, because the final `printf '%s\n'` runs whatever the pipeline produced, including nothing. Callers spell it `s="$(devbox_slugify ...)"` and then test `[[ -n "$s" ]]`, so the newline is invisible to them and visible to anything comparing bytes.
  2. THE 40-CHARACTER CAP IS APPLIED BEFORE THE FINAL TRIM, so the answer can be 39 characters. `${s:0:40}` can land ON a dash, and a trailing dash is not a legal DNS label, which is the whole reason the second `sed` exists.
  3. A NEWLINE IN THE INPUT SURVIVES. `sed` works line by line, so `s/^-*//` and `s/-*$//` trim EVERY line rather than the whole string, and a two-line argument yields a two-line answer. Nothing in the tree passes one today; the port reproduces it because the twin does it, not because it is wanted.
  4. MULTIBYTE COLLAPSES TO ONE DASH PER RUN, NOT ONE PER BYTE, and that is the `s/--*/-/g` stage rather than any awareness of UTF-8: `feat/uber` with an umlaut is `feat-ber` because two bytes became two dashes and then one. A byte that is not valid UTF-8 at all takes the same path.
  5. `${3:-unknown}` FIRES ON AN EMPTY THIRD ARGUMENT AND IS INERT ANYWAY, which is worth writing down precisely because it reads as load-bearing. The `unknown` it supplies reaches the `*)` arm, and so does every other value that is not `yes` or `no`, so nothing in the twin can tell an empty third argument from a missing one or from `maybe`.
  The port applies the default for fidelity rather than for behaviour, and that is a measurement and not a reading: a planted variant that dropped the default moved no observation in any of the seven differential scenarios, while one that read an empty claim as `no` moved two.
  `${2:-}` does not have that shape, and the hint IS observable: a plant that dropped the `${hint:+ -- $hint}` suffix moved fourteen.
  6. `devbox_slug_drift` NEVER FAILS: it ends in an explicit `return 0`, so a caller under `set -e` is safe no matter how many drift lines it printed. Its result is what it PRINTED, never its status.
  7. NO ARGUMENT AT ALL IS AN UNBOUND VARIABLE, AND THAT IS NOT A RETURN. `devbox_slug_drift` and `devbox_route_label` open with `local want="$1"` and `local code="$1"`; under the `set -u` every sourcer of this library runs with, a call with no arguments prints `$1: unbound variable` on stderr and KILLS the shell with status 1.
  `devbox_slugify` is written `"${1:-}"` and therefore has no such case: with no arguments it is the empty string. The three are not uniform here, and the port keeps the difference rather than smoothing it: `None` means the argument was not supplied, and the two that would die raise `DevboxError` while the one that would not answers.

--------------------------------------------------------------------------
WHAT THIS PORT DOES NOT CLAIM
--------------------------------------------------------------------------
That the labels these strings go into become the traefik routers an operator's browser resolves. That claim needs a container and a proxy, and `.ci/rediacc_ci/tests/gates/test_gate_devbox_slug.py` names it as blind spot 1 for the same reason. What is ported here is the STRING RULE, and the ledger licences the string rule alone.
"""

from __future__ import annotations

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

# What `${3:-unknown}` supplies for a missing OR EMPTY third argument. Reproduced behaviour 5.
ROUTED_UNKNOWN = "unknown"

# What bash prints, and the status it exits with, when `local x="$1"` meets `set -u` with no arguments. Reproduced behaviour 7. The `<file>: line <N>: ` stamp bash puts in front of it is dropped by the differential on both sides, because a port cannot reproduce a line number in a file it is not.
UNBOUND_MESSAGE = "$1: unbound variable"
UNBOUND_STATUS = 1


class DevboxError(RuntimeError):
    """A refusal the twin reports on stderr and then dies on, rather than returning."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


class Outcome:
    """A shell function's two observable channels: what it printed, and its status.

    The twin's functions are SHELL functions, and two of the three here answer entirely in what they PRINT while returning 0 regardless. A port returning only a value would drop the half that the callers read.
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

    In that order, which is what makes a multibyte character one dash rather than two or three: every byte outside the set becomes a dash first, and only then do runs collapse. Reproduced behaviour 4.
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

    The second pass, after the 40-character cut. It does NOT collapse runs, because the first pass already did and nothing between them can create one. Reproduced behaviour 2 is why it exists at all.
    """
    return line.strip("-")


def slugify(value: str | None = None) -> str:
    """`devbox_slugify`, `.ci/lib/devbox.sh:186-197`, as a caller CAPTURES it.

    `None` is the no-argument case, which `"${1:-}"` makes the empty string rather than an error; see reproduced behaviour 7 for why the other two functions differ.
    What is returned is what `s="$(devbox_slugify "$x")"` binds, so the trailing newline the twin prints is absent here exactly as command substitution strips it. `slugify_stdout` is the byte-level answer.

    THE INPUT IS TREATED AS BYTES, with `surrogateescape`, because the twin's pipeline is byte-level under `LC_ALL=C` and the live corpus includes branch names that are not valid UTF-8 at all.
    MEASURED, AND NOT THE CLAIM IT LOOKS LIKE: the byte-versus-character choice is not observable in the answer at all, because `s/--*/-/g` collapses the run either way, and a planted latin-1 port moved no observation in any of the seven differential scenarios.
    What IS observable is LOSING the input: a planted port encoding with `errors="ignore"` dropped every byte that is not valid UTF-8 and diverged on forty observations. The bytes are kept because the twin keeps them, and that is the surviving claim rather than any dash count.
    """
    raw = "" if value is None else value
    lowered = lower_ascii(raw.encode("utf-8", "surrogateescape"))
    # `sed` reads LINES, so the trims are per line and a final chunk with no newline is still a line. The join and the strip together reproduce both that and the command substitution the twin's own callers wrap this in.
    sanitised = "\n".join(sanitise_line(line) for line in lowered.split(b"\n")).rstrip("\n")
    # `${s:0:40}` counts CHARACTERS in the shell's own locale, and the string is ASCII by the time it gets here, so characters and bytes are the same count. Reproduced behaviour 2: the cut comes first and the trim after.
    capped = sanitised[:SLUG_MAX]
    return "\n".join(trim_dashes(line) for line in capped.split("\n"))


def slugify_stdout(value: str | None = None) -> str:
    """The exact bytes `devbox_slugify` writes to stdout, which is never empty.

    The final `printf '%s\\n'` runs whatever the pipeline produced, so an input that sanitises away still prints one newline. Reproduced behaviour 1, and the reason this is a separate function: the value a caller binds and the bytes a differential compares are not the same string.
    """
    return slugify(value) + "\n"


# --------------------------------------------------------------------------- the two reporters ---------------------------------------------------------------------------


def slug_drift(want: str | None = None, baked: str = "", recorded: str = "") -> Outcome:
    """`devbox_slug_drift`, `.ci/lib/devbox.sh:242-253`.

    Three names in, up to two lines out, status ALWAYS 0 (reproduced behaviour 6). An empty name on either side of a comparison silences that comparison, which is what makes a checkout with no container and no state file quiet rather than doubly wrong.
    `want=None` is the no-argument call, which under `set -u` is not a quiet default but a dead shell; see reproduced behaviour 7.
    """
    if want is None:
        raise DevboxError(UNBOUND_MESSAGE, code=UNBOUND_STATUS)
    out = []
    if baked and want and baked != want:
        out.append(DRIFT_CONTAINER % (baked, want))
    if recorded and baked and recorded != baked:
        out.append(DRIFT_STATE % (recorded, baked))
    return Outcome("".join(out), 0)


def route_label(code: str | None = None, hint: str = "", routed: str = ROUTED_UNKNOWN) -> Outcome:
    """`devbox_route_label`, `.ci/lib/devbox.sh:902-916`.

    THE INVARIANT IT CARRIES IS THAT THE WORD NEVER CONTRADICTS THE CODE, and the twin's own comment records "OK (404)" shipping for one commit as the failure that motivated it.
    A 404 is "live" only when the CALLER has confirmed a router exists for that hostname, because the status code alone cannot tell traefik's no-such-router 404 from a backend's own not-found.
    An EMPTY `routed` is the unknown arm rather than a fourth case, which is reproduced behaviour 5 and is INERT there, since the unknown arm is also the catch-all; `code=None` is the unbound-variable death, which is reproduced behaviour 7 and is not inert at all.
    """
    if code is None:
        raise DevboxError(UNBOUND_MESSAGE, code=UNBOUND_STATUS)
    if not routed:
        routed = ROUTED_UNKNOWN
    if code == "000":
        return Outcome(ROUTE_PROXY_UNREACHABLE + "\n", 0)
    if code == "502":
        suffix = " -- %s" % hint if hint else ""
        return Outcome(ROUTE_NO_BACKEND + suffix + "\n", 0)
    if code == "404":
        if routed == "no":
            return Outcome(ROUTE_NO_ROUTER + "\n", 0)
        if routed == "yes":
            return Outcome(ROUTE_LIVE % code + "\n", 0)
        return Outcome(ROUTE_AMBIGUOUS_404 % code + "\n", 0)
    return Outcome(ROUTE_LIVE % code + "\n", 0)
