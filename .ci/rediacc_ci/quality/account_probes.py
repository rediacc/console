"""Behavioural gate for the dev-stack liveness probes in `.ci/lib/account.sh`.

Ported from `.ci/scripts/quality/check-account-probes.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live side by side.

The twin's own header, carried because the incident IS the gate:

    WHY THIS EXISTS. On 2026-08-04 `account_rustfs_alive` reported ALIVE for a
    port with nothing on it, and shipped that way long enough to reach CI. The
    capture was:

        code=$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$url" 2>/dev/null || echo 000)
        [[ "$code" != "000" ]]

    On a refused connection curl PRINTS `000` (that is what %{http_code} yields)
    AND exits non-zero, so `|| echo 000` appended a SECOND one: the captured
    value was `000000`, which is `!= "000"`, so the probe said alive.
    Downstream, account_dev announced "Reusing RustFS already serving on port
    ...", never started the container, exported CONFIG_R2_* anyway, and the
    gateway then advertised a config store that did not exist.

    WHY NO EXISTING GATE COULD HAVE CAUGHT IT. The absence branch of a probe
    that guards a heavy external dependency never executes on a developer
    machine, because the dependency is always present there (RustFS genuinely
    listens on 9100 on the operator's box). It is untested BY CONSTRUCTION, and
    reading the code does not help: the code is not wrong on the path anyone
    runs. The only cure is to exercise the absent case deliberately, which is
    what this does.

    CONTROL-FIRST. Three assertions, and the gate FAILS ITSELF if its own
    control cannot fire:
      1. closed port  -> the probe must say DEAD   (the defect)
      2. live port    -> the probe must say ALIVE  (the CONTROL: without this, a
                         probe hard-wired to `false` would pass assertion 1)
      3. the historical implementation, re-run inline, MUST say ALIVE on the
         same closed port, proving this test targets the real bug and is not
         green by accident against an unrelated code path.

    Usage: check-account-probes.sh

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE SUBJECT IS STILL BASH, SO THE PORT STILL SPAWNS BASH. `account_rustfs_alive` is a shell function; there is no way to exercise it that does not source the library. The port therefore keeps the twin's subshell verbatim, including both letters of `set +eu`, and the twin's paragraph explaining them is carried at the
function that carries the flags rather than summarised here:

    `set +eu` is REQUIRED, and both letters were paid for separately while
    writing this. account.sh is not safe to source under the strict flags this
    gate runs with: errexit trips on its re-source guard (account.sh:8,
    `[[ -n "${ACCOUNT_LIB_LOADED:-}" ]] && return 0`, whose && list returns
    NON-ZERO on a first load), and nounset trips on the unset variables it
    references (`$CONSOLE_ROOT_DIR`, among others; `find-port.sh` used to
    contribute its own until W7P5-b deleted it, and account.sh still has
    enough of its own for the flag to matter). Either one aborts the source
    part-way, leaving every
    function below undefined, and a probe that cannot be called reads as "not
    alive", i.e. the gate would report a PASS on assertion 1 while testing
    nothing at all. run.sh does not hit this because it does not source the
    library under strict flags.

`CI_LIB_DIR` IS EXPORTED FOR THE CHILD, NOT FOR THIS PROCESS. The twin exports it into its own environment and the subshell inherits it; the port passes it in the child's env dict. Same value, `<root>/.ci/lib`, and the twin's reason is unchanged: "account.sh sources siblings through $CI_LIB_DIR (account.sh:12), so that MUST be exported before sourcing or the load half-fails and the
function never exists."

THE LOAD PROBE'S EXIT 3 IS LOAD-BEARING AND IS CARRIED AS A CONSTANT. The twin writes `declare -F account_rustfs_alive >/dev/null || exit 3` and then tests `load_rc -eq 3`. A port that collapsed that into "the probe returned non-zero" would delete the distinction between "the library did not load" and "the port is correctly reporting a closed port as dead", which is the whole
reason the twin comments: "without the check below, a failed source makes `account_rustfs_alive` missing, the subshell returns non-zero, and 'not alive' reads as 'correctly dead' -- assertion 1 would pass while testing nothing at all. That is the exact vacuous-green this gate exists to prevent, and it happened while writing it."

`command -v python3` IS SATISFIED BY CONSTRUCTION and has no counterpart below, the same way `require_cmd python3` is in the editorconfig port. The twin needs the probe because it shells out to a `python3` that may not exist to bind the control listener; this module IS that python3. Inventing a branch for it would be a check that cannot fail. What the port DOES still probe is
`bash`, because that is the interpreter it now shells out to, and the twin's refusal wording is reused for it so a reader meets the same sentence: refusing "to report green
from a run where the control could not fire".

`curl` IS NOT PROBED, ON PURPOSE, IN EITHER IMPLEMENTATION. Assertion 3 re-runs the historical capture through curl, and with no curl on PATH that capture yields the empty string plus the `|| echo 000` fallback, i.e. exactly `000`, which trips "PLANTED DEFECT NO LONGER REPRODUCES". That message is wrong about the cause and right about the verdict, and the port emits the same bytes
because a clearer message here would be a finding the differential scores as a mismatch. Reported as a twin defect rather than repaired.

THE THREE ASSERTIONS ARE INDEPENDENT AND ALL THREE RUN. The twin does not short-circuit after the first failure; it accumulates `failures` and reports the count. The port keeps that, because a run that stopped at assertion 1 would hide whether the CONTROL could still fire, and "the control could not fire" is the finding that matters most.

THE LISTENER IS THE TWIN'S OWN `python3 -m http.server`, spawned as a child rather than served in-process. An in-process `http.server` thread would be tidier and would change what assertion 2 proves: the twin's control demonstrates that a REAL socket on a REAL port answers curl, and a same-process server shares the interpreter with the code asserting about it.

THE READINESS LOOP IS `curl`, 50 attempts, 0.1s apart, as in the twin. A `socket.connect_ex` probe would be faster and would answer a different question: the probe under test speaks HTTP through curl, so the readiness check has to prove HTTP is being answered, not merely that a port is open.
"""

import contextlib
import ctypes
import os
import pathlib
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The library under test, repo-relative exactly as the twin spells it. Printed in the step line and in the two refusal messages, so the reader is told which file was not there rather than which variable was empty. THE TWIN'S MESSAGES CARRY AN EM DASH, and this repository's authoring rule forbids typing one into a source file. The character is therefore named by its code point
# rather than typed, exactly the way `scripts/lib/shadow-gate.ts` names ESC with `String.fromCharCode(27)` instead of embedding a raw control byte. This is byte fidelity, not decoration: the differential compares finding TEXT, so substituting a hyphen would make the port report a different finding
# from its twin on every line below that uses it.
DASH = "\u2014"

PROBE_LIB = ".ci/lib/account.sh"

# The function the whole gate is about. Named once so a rename fails loudly in the load probe rather than silently matching nothing.
PROBE_FN = "account_rustfs_alive"

# The subshell's exit status for "the library loaded but the function is not there". Three, not one, because one is what a healthy probe returns for a closed port and the two must never be confused. See the port notes.
LOAD_FAILED_RC = 3

# The readiness loop, in the twin's numbers: `for _ in $(seq 1 50)` with `sleep 0.1` between attempts, i.e. up to five seconds for a local listener.
READY_ATTEMPTS = 50
READY_DELAY = 0.1


def free_port() -> int:
    """A port that is definitely free: bind :0, read what the kernel handed out, close.

    The twin shells out to python3 for exactly this. The port is that python3, so the three lines are inlined; the socket dance is identical, including the close, which is what makes the port free again rather than merely known.
    """
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def probe_script(port: int) -> str:
    """The twin's subshell body, byte for byte in its load-bearing parts.

    `set +eu` first, the source silenced on both streams, the `declare -F` guard exiting LOAD_FAILED_RC, then the call. Nothing here is reordered: the source must be silenced before the guard so a chatty library cannot be mistaken for output of the probe, and the guard must precede the call so a missing
    function is distinguishable from a dead port.
    """
    return (
        "set +eu\n"
        "# shellcheck disable=SC1090\n"
        'source "%s" >/dev/null 2>&1\n'
        "declare -F %s >/dev/null || exit %d\n"
        '%s "%d"\n' % (PROBE_LIB, PROBE_FN, LOAD_FAILED_RC, PROBE_FN, port)
    )


def ci_lib_dir(root: pathlib.Path) -> str:
    """The twin's `CI_LIB_DIR`, spelled the twin's way.

    `check-account-probes.sh:82` sets `CI_LIB_DIR="$SCRIPT_DIR/../../lib"` and
    never resolves it, then PRINTS that value in the load-failure message. The resolved and unresolved spellings name ONE directory and are DIFFERENT BYTES, and the differential compares bytes. Carrying the tidy form would make the port report a different finding from its twin for the same defect, so the untidy one is carried and named here rather than discovered later.
    """
    return "%s/../../lib" % (root / ".ci" / "scripts" / "quality")


def probe_rc(root: pathlib.Path, port: int) -> int:
    """Run the probe against `port` from `root`. Returns the subshell's status.

    Zero means the probe said ALIVE, LOAD_FAILED_RC means the function was never defined, and anything else means it said DEAD. The caller must keep those three apart; collapsing the last two is the vacuous green the twin's header describes.
    """
    env = dict(os.environ)
    # account.sh sources siblings through $CI_LIB_DIR (account.sh:12).
    env["CI_LIB_DIR"] = ci_lib_dir(root)
    proc = subprocess.run(
        ["bash", "-c", probe_script(port)],
        cwd=str(root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode


def probe_says_alive(root: pathlib.Path, port: int) -> bool:
    """True when the probe reports ALIVE. LOAD_FAILED_RC is NOT alive."""
    return probe_rc(root, port) == 0


def historical_capture(port: int) -> str:
    """Re-run the 2026-08-04 implementation and return what it captured.

        code=$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$url" 2>/dev/null || echo 000)

    THE CONCATENATION IS THE BUG AND IT IS REPRODUCED EXACTLY. Command substitution captures the stdout of the WHOLE `||` list, so on a refused connection curl's own `000` and the fallback's `000` are both captured and the value is `000000`. A port that returned a boolean here would have discarded the evidence; the value is returned as a string because the twin prints it, and a
    reader comparing `'000000'` against `'000'` is the point.

    Trailing newlines are stripped, which is what command substitution does. The `2>/dev/null` is reproduced as a discarded stderr, and the missing-curl case falls through to the same empty-plus-fallback value bash would produce.
    """
    url = "http://127.0.0.1:%d/" % port
    argv = ["curl", "-s", "-o", "/dev/null", "-m", "2", "-w", "%{http_code}", url]
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        out = proc.stdout.decode("utf-8", "replace")
        rc = proc.returncode
    except OSError:
        # No curl on PATH. bash would print nothing for the failed command and then run the fallback, so the captured value is exactly the fallback.
        out, rc = "", 1
    if rc != 0:
        out += "000\n"
    return re.sub(r"\n+$", "", out)


def listener_ready(port: int) -> bool:
    """Poll the control listener with curl until it answers, up to five seconds.

    `curl -s -o /dev/null -m 1 URL`, the twin's exact invocation. Returns False when nothing ever answered, which the caller must treat as a CONTROL THAT COULD NOT FIRE rather than as a probe failure: a green from an assertion that could not fail proves nothing.
    """
    url = "http://127.0.0.1:%d/" % port
    for _ in range(READY_ATTEMPTS):
        try:
            proc = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-m", "1", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            return False
        if proc.returncode == 0:
            return True
        time.sleep(READY_DELAY)
    return False


def start_listener(port: int) -> subprocess.Popen:
    """`python3 -m http.server <port> --bind 127.0.0.1`, both streams discarded.

    A CHILD PROCESS, not an in-process server. See the port notes: the control is worth something only if it demonstrates a real socket answering real HTTP, and a thread inside this interpreter shares its fate with the code asserting about it.
    """
    return subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=_die_with_parent,  # noqa: PLW1509 - see the comment below
    )


# PR_SET_PDEATHSIG: KILL THIS CHILD WHEN ITS PARENT DIES.
#
# Every caller already wraps start_listener in `try/finally: server.kill()`, and that is enough for a normal exit. It is NOT enough when the PARENT is killed: a SIGKILLed interpreter never reaches its finally, the listener survives, and init adopts it. Measured on this box 2026-09-07: 131 orphaned `python3 -m http.server` processes, the oldest 25 hours, parented to pid 1 -- left
# behind by pytest runs that were killed by `timeout` or by hand.
#
# It got worse the moment this suite went parallel: `check:ci-pytest` now runs under `-n 8`, so a killed run strands up to eight workers' worth of listeners instead of one process's worth.
#
# `preexec_fn` runs in the child between fork and exec. It is documented as
# unsafe in a threaded parent, which is why it carries the noqa above rather
# than a silent suppression: this helper is called from single-threaded gate and test code, and the alternative (a wrapper process, or a reaper) costs more than the two lines it saves. If this is ever called from a thread, replace it
# with a process-group kill rather than removing the protection.
def _die_with_parent() -> None:
    """prctl(PR_SET_PDEATHSIG, SIGKILL). Best effort: Linux-only, never fatal."""
    # Suppressed wholesale, deliberately: this runs between fork and exec, so a raise here would kill the spawn rather than the listener. A platform without libc or without prctl simply keeps the old behaviour.
    with contextlib.suppress(Exception):
        # 1 is PR_SET_PDEATHSIG. Named here rather than imported because Python has no binding for it and the number is part of the kernel ABI.
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 when all three assertions hold, 1 otherwise.

    `--selftest` is intercepted BEFORE anything is probed. The twin documents itself as taking no arguments ("Usage: check-account-probes.sh") and ignores any it is given, so nothing observable changes for a real caller.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()

    log.step("Checking dev-stack liveness probes in %s..." % PROBE_LIB)

    if not (root / PROBE_LIB).is_file():
        log.error("%s not found %s this gate has nothing to check, which is a" % (PROBE_LIB, DASH))
        log.error("failure, not a pass: a probe library that vanished cannot be verified.")
        return 1

    # The twin probes python3 here because it shells out to one. This module is that python3; what it shells out to is bash, so bash is what is probed, in the twin's own words about refusing a green the control could not earn.
    if shutil.which("bash") is None:
        log.error("bash is required to source the probe library. Refusing to report")
        log.error("green from a run where the control could not fire.")
        return 1

    # Fail loudly if the library cannot be loaded at all: a gate that cannot reach its subject must not report on it. Port 1 is closed, so a HEALTHY probe returns non-zero here; only LOAD_FAILED_RC means the load failed.
    if probe_rc(root, 1) == LOAD_FAILED_RC:
        log.error(
            "Could not load %s from %s (CI_LIB_DIR=%s)." % (PROBE_FN, PROBE_LIB, ci_lib_dir(root))
        )
        log.error("Refusing to report on a probe this gate cannot actually call.")
        return 1

    failures = 0

    # --- 1. THE DEFECT: a closed port must read as dead ---------------------
    dead_port = free_port()
    if probe_says_alive(root, dead_port):
        log.error("%s reported ALIVE for closed port %d." % (PROBE_FN, dead_port))
        log.error("This is the 2026-08-04 defect: check for a reintroduced")
        log.error("`|| echo 000` in the curl capture %s curl already prints 000 on a" % DASH)
        log.error("refused connection, so the fallback concatenates to 000000 and")
        log.error("defeats the comparison. Use `|| true` INSIDE the substitution.")
        failures += 1
    else:
        log.info("closed port %d reads as dead" % dead_port)

    # --- 2. THE CONTROL: a live port must read as alive --------------------- Without this, a probe that always returned false would satisfy assertion 1.
    live_port = free_port()
    listener = start_listener(live_port)
    try:
        if not listener_ready(live_port):
            log.error("CONTROL COULD NOT FIRE: no listener came up on %d, so a green" % live_port)
            log.error("result here would prove nothing. Failing rather than reporting a")
            log.error("pass from an assertion that could not fail.")
            failures += 1
        elif probe_says_alive(root, live_port):
            log.info("live port %d reads as alive (control fired)" % live_port)
        else:
            log.error("CONTROL FAILED: %s reported DEAD for port" % PROBE_FN)
            log.error(
                "%d, which is serving. The probe now under-reports %s it can" % (live_port, DASH)
            )
            log.error("never say yes, which makes assertion 1 meaningless.")
            failures += 1
    finally:
        # The twin's `trap cleanup EXIT`, which is `kill "$listener_pid" || true`. A finally block rather than atexit, so the listener dies even when the assertions above raise.
        listener.kill()
        listener.wait()

    # --- 3. PLANTED DEFECT: the old shape must still be detectable ---------- Re-run the historical implementation against the same closed port. If it does NOT report alive, this gate is no longer testing the bug it was written for (curl changed its behaviour, or the port is not actually closed).
    old_code = historical_capture(dead_port)
    if old_code != "000":
        log.info("planted defect reproduces (old capture = '%s' on a closed port)" % old_code)
    else:
        log.error("PLANTED DEFECT NO LONGER REPRODUCES: the historical capture yielded")
        log.error("'%s' rather than a concatenated value. This gate can no longer" % old_code)
        log.error("prove it is testing the original defect %s re-derive it before trusting" % DASH)
        log.error("a green run.")
        failures += 1

    if failures > 0:
        log.error("%d probe check(s) failed" % failures)
        return 1

    log.info(
        "Dev-stack liveness probes behave correctly (dead, alive, and planted-defect "
        "controls all fired)"
    )
    return 0


# --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------

# THE FIXTURES CARRY `$CONSOLE_ROOT_DIR`, WHICH IS UNSET, ON PURPOSE. It is the line at `.ci/lib/account.sh:19` that makes nounset abort the source, and it is the reason the twin needs the `u` of `set +eu` as well as the `e`. A fixture without it loads cleanly under strict flags, and the control asserting that `set +eu` matters then passes for a reason that has nothing to do with
# the flags. Measured: with the line removed, the strict form of probe_script exits 0 against a live port, i.e. it proves nothing.
#
# The fixture library bodies. Written as literals, never by substituting into a copy of the real account.sh: a substitution silently yields an unmutated copy the day the targeted line is reworded, and the control then passes against source it never changed. That is the failure check-control-vacuity.sh exists
# for, and the twin builds its own controls the same way.
FIXTURE_HEALTHY = """#!/bin/bash
[[ -n "${ACCOUNT_LIB_LOADED:-}" ]] && return 0
readonly ACCOUNT_LIB_LOADED=1
source "$CI_LIB_DIR/find-port.sh"
ACCOUNT_DIR="$CONSOLE_ROOT_DIR/private/account"
account_rustfs_alive() {
    local port="$1"
    local code
    code=$(curl -s -o /dev/null -m 2 -w '%{http_code}' "http://127.0.0.1:${port}/" 2>/dev/null || true)
    [[ -n "$code" && "$code" != "000" ]]
}
"""

# The 2026-08-04 shape, restored exactly: `|| echo 000` instead of `|| true`.
FIXTURE_DEFECTIVE = FIXTURE_HEALTHY.replace(
    "2>/dev/null || true)", "2>/dev/null || echo 000)"
).replace('[[ -n "$code" && "$code" != "000" ]]', '[[ "$code" != "000" ]]')

# A probe that can never say yes. Assertion 1 passes against it, which is exactly why assertion 2 exists.
FIXTURE_ALWAYS_DEAD = FIXTURE_HEALTHY.replace('[[ -n "$code" && "$code" != "000" ]]', "false")

# A library that loads and defines nothing. The load probe must see this, or "not alive" would read as "correctly dead".
FIXTURE_NO_FUNCTION = """#!/bin/bash
source "$CI_LIB_DIR/find-port.sh"
ACCOUNT_DIR="$CONSOLE_ROOT_DIR/private/account"
account_something_else() { return 0; }
"""

# The sibling the FIXTURES source. Empty is enough: the point is that the source succeeds, not what it defines.
#
# ARCHAEOLOGY, DELIBERATELY KEPT. The real `.ci/lib/find-port.sh` is DELETED (W7P5-b) and the real account.sh no longer sources it. These fixtures are the 2026-08-04 shape frozen as literals, exactly so that they do NOT track the live file -- see the paragraph above on why substituting into a copy of the real account.sh would silently yield an unmutated control. Removing the line
# would re-key the fixtures against a shape the incident never had.
FIXTURE_FIND_PORT = '#!/bin/bash\n: "${FIND_PORT_LOADED:=1}"\n'


def _fixture_root(tmp: pathlib.Path, body: str) -> pathlib.Path:
    """A throwaway tree carrying `.ci/lib/{account,find-port}.sh` and nothing else."""
    lib = tmp / ".ci" / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    # `.ci/scripts/quality` must EXIST, because CI_LIB_DIR is the twin's unresolved `<root>/.ci/scripts/quality/../../lib` and the kernel resolves `..` against real directories. Without it the source fails, every function is undefined, and "not alive" would read as "correctly dead".
    (tmp / ".ci" / "scripts" / "quality").mkdir(parents=True, exist_ok=True)
    (lib / "account.sh").write_text(body, encoding="utf-8")
    (lib / "find-port.sh").write_text(FIXTURE_FIND_PORT, encoding="utf-8")
    return tmp


def selftest() -> int:
    """Both directions for every assertion, plus both directions for each helper.

    A gate with only positive controls will happily flag the whole tree, so every plant below has a mirror: the defective library must be caught AND the healthy one must be cleared, a closed port must read dead AND a live one alive, a missing function must be seen AND a present one must not be mistaken for missing.
    """
    ctl = Controls("account-probes", floor=18, verbose=True)

    # -- free_port ---------------------------------------------------------
    port_a = free_port()
    port_b = free_port()
    ctl.check("free_port returns a usable TCP port", 1 <= port_a <= 65535, True)
    ctl.truthy("free_port hands out a port the kernel chose", port_a != 0)
    # Not an equality: the kernel may reuse the number. What must hold is that binding it again succeeds, i.e. the socket really was closed.
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port_b))
        rebound = True
    except OSError:
        rebound = False
    finally:
        probe.close()
    ctl.check("free_port leaves the port free (it closed the socket)", rebound, True)

    # -- historical_capture, both directions -------------------------------
    closed = free_port()
    ctl.check(
        "PLANT: the historical capture concatenates on a closed port",
        historical_capture(closed),
        "000000",
    )
    live = free_port()
    server = start_listener(live)
    try:
        ctl.check("CONTROL: the listener answers curl", listener_ready(live), True)
        ctl.check(
            "MIRROR: the historical capture is a real code on a live port",
            historical_capture(live),
            "200",
        )
    finally:
        server.kill()
        server.wait()

    # -- probe_script carries the load-bearing lines -----------------------
    body = probe_script(4242)
    ctl.truthy("probe_script disables errexit and nounset", "set +eu" in body)
    ctl.truthy("probe_script guards on declare -F", "declare -F %s" % PROBE_FN in body)
    ctl.truthy("probe_script exits 3 when the function is missing", "|| exit 3" in body)
    ctl.truthy("probe_script calls the probe with the port", '%s "4242"' % PROBE_FN in body)

    # The unresolved CI_LIB_DIR spelling, asserted in BOTH directions: it must carry the twin's `../../lib` tail, and it must not be the tidy resolved form that would print different bytes for the same defect.
    ctl.check(
        "CI_LIB_DIR keeps the twin's unresolved spelling",
        ci_lib_dir(pathlib.Path("/x")),
        "/x/.ci/scripts/quality/../../lib",
    )
    ctl.falsy(
        "CI_LIB_DIR is NOT the resolved form",
        ci_lib_dir(pathlib.Path("/x")) == "/x/.ci/lib",
    )

    with tempfile.TemporaryDirectory() as tmp:
        root_healthy = _fixture_root(pathlib.Path(tmp) / "healthy", FIXTURE_HEALTHY)
        root_defect = _fixture_root(pathlib.Path(tmp) / "defect", FIXTURE_DEFECTIVE)
        root_dead = _fixture_root(pathlib.Path(tmp) / "dead", FIXTURE_ALWAYS_DEAD)
        root_nofn = _fixture_root(pathlib.Path(tmp) / "nofn", FIXTURE_NO_FUNCTION)

        closed = free_port()
        # -- assertion 1, both directions ----------------------------------
        ctl.check(
            "MIRROR: the healthy probe reads a closed port as DEAD",
            probe_says_alive(root_healthy, closed),
            False,
        )
        ctl.check(
            "PLANT: the 2026-08-04 probe reads a closed port as ALIVE",
            probe_says_alive(root_defect, closed),
            True,
        )

        # -- assertion 2, the control ---------------------------------------
        live = free_port()
        server = start_listener(live)
        try:
            ctl.check("CONTROL: the fixture listener came up", listener_ready(live), True)
            ctl.check(
                "CONTROL: the healthy probe reads a LIVE port as alive",
                probe_says_alive(root_healthy, live),
                True,
            )
            ctl.check(
                "PLANT: a probe hard-wired to false reads a LIVE port as dead",
                probe_says_alive(root_dead, live),
                False,
            )
        finally:
            server.kill()
            server.wait()

        # -- the load probe, both directions --------------------------------
        ctl.check(
            "PLANT: a library defining no probe exits with the load-failed status",
            probe_rc(root_nofn, 1),
            LOAD_FAILED_RC,
        )
        ctl.falsy(
            "MIRROR: a healthy library does NOT report a load failure on a closed port",
            probe_rc(root_healthy, 1) == LOAD_FAILED_RC,
        )

        # -- the whole gate, over each fixture ------------------------------
        def run(root: pathlib.Path) -> int:
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        ctl.check("CONTROL: the healthy library passes the whole gate", run(root_healthy), 0)
        ctl.check("PLANT: the 2026-08-04 library reds the whole gate", run(root_defect), 1)
        ctl.check("PLANT: an always-dead probe reds the whole gate", run(root_dead), 1)
        ctl.check("PLANT: a library with no probe function reds the whole gate", run(root_nofn), 1)

        # An ABSENT library is a failure, never a pass: "a probe library that vanished cannot be verified."
        bare = pathlib.Path(tmp) / "bare"
        bare.mkdir()
        ctl.check("PLANT: a missing probe library reds rather than skipping", run(bare), 1)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
