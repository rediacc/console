"""Behavioural gate for the dev-stack liveness probe `rustfs_alive` in `.ci/rediacc_ci/core/account.py`.

WHY THIS EXISTS. On 2026-08-04 the bash original (`account_rustfs_alive`) reported ALIVE for a port with nothing on it, and shipped that way long enough to reach CI. The capture was:

    code=$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$url" 2>/dev/null || echo 000)
    [[ "$code" != "000" ]]

On a refused connection curl PRINTS `000` (that is what `%{http_code}` yields) AND exits non-zero, so `|| echo 000` appended a SECOND one: the captured value was `000000`, which is `!= "000"`, so the probe said alive. Downstream, account_dev announced "Reusing RustFS already serving on port ...", never started the container, exported CONFIG_R2_* anyway, and the gateway then advertised a config store that did not exist.

The Python port is not immune: a fallback that appends `000` when curl exits non-zero reintroduces the same concatenation.

WHY NO EXISTING GATE COULD HAVE CAUGHT IT. The absence branch of a probe that guards a heavy external dependency never executes on a developer machine, because the dependency is always present there. It is untested BY CONSTRUCTION, and reading the code does not help: the code is not wrong on the path anyone runs. The only cure is to exercise the absent case deliberately.

CONTROL-FIRST. Three assertions, and the gate FAILS ITSELF if its own control cannot fire:
  1. closed port  -> the probe must say DEAD   (the defect)
  2. live port    -> the probe must say ALIVE  (the CONTROL: without this, a probe hard-wired to `False` would pass assertion 1)
  3. the historical implementation, re-run inline, MUST say ALIVE on the same closed port, proving this test targets the real bug and is not green by accident against an unrelated code path.

THE PROBE RUNS IN A CHILD INTERPRETER with `<root>/.ci` prefixed to PYTHONPATH, so a fixture tree carrying a defective copy of `rediacc_ci.core.account` wins over the real package. Importing in-process would read THIS interpreter's copy and every planted-defect control would go permanently green.

THE LOAD PROBE'S EXIT 3 IS LOAD-BEARING AND IS CARRIED AS A CONSTANT. An import failure or a missing `rustfs_alive` must exit LOAD_FAILED_RC, distinct from the probe returning False. A gate that collapsed them would delete the distinction between "the module did not load" and "the probe correctly reports a closed port as dead", and assertion 1 would pass while testing nothing.

`curl` IS NOT PROBED, ON PURPOSE. Assertion 3 re-runs the historical capture through curl, and with no curl on PATH that capture yields the empty string plus the fallback, i.e. exactly `000`, which trips "PLANTED DEFECT NO LONGER REPRODUCES". The message is wrong about the cause and right about the verdict.

THE THREE ASSERTIONS ARE INDEPENDENT AND ALL THREE RUN, because a run that stopped at assertion 1 would hide whether the CONTROL could still fire.

THE LISTENER IS `python3 -m http.server`, spawned as a child rather than served in-process: the control demonstrates that a REAL socket on a REAL port answers curl, and a same-process server shares the interpreter with the code asserting about it. The readiness loop is `curl`, 50 attempts, 0.1s apart, because the probe under test speaks HTTP through curl and the readiness check has to prove HTTP is being answered, not merely that a port is open.
"""

import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import time

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The module under test, repo-relative. Printed in the step line and in the refusal messages. The messages carry an em dash, which this repository's authoring rule forbids typing into a source file, so the character is named by its code point.
DASH = "\u2014"

PROBE_LIB = ".ci/rediacc_ci/core/account.py"

# The function the whole gate is about. Named once so a rename fails loudly in the load probe rather than silently matching nothing.
PROBE_FN = "rustfs_alive"

# The child's exit status for "the module loaded but the function is not there". Three, not one, because one is what a healthy probe returns for a closed port and the two must never be confused. See the port notes.
LOAD_FAILED_RC = 3

# The child's exit status for "the function loaded and then raised". Four, distinct from both the DEAD answer (1) and the load failure (3): an uncaught exception would exit 1 and read as DEAD, so a broken probe would satisfy the dead-port assertion for the wrong reason.
PROBE_RAISED_RC = 4

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


PROBE_SCRIPT = (
    "import sys\n"
    "try:\n"
    "    from rediacc_ci.core.account import %s as probe\n"
    "except Exception:\n"
    "    sys.exit(%d)\n"
    "try:\n"
    "    alive = probe(int(sys.argv[1]))\n"
    "except Exception:\n"
    "    sys.exit(%d)\n"
    "sys.exit(0 if alive else 1)\n"
) % (PROBE_FN, LOAD_FAILED_RC, PROBE_RAISED_RC)


def probe_rc(root: pathlib.Path, port: int) -> int:
    """Run the probe against `port` from `root`. Returns the child's status.

    Zero means the probe said ALIVE, LOAD_FAILED_RC means the function was never importable, PROBE_RAISED_RC means it raised, and 1 means it said DEAD. The caller must keep those apart; collapsing the last two is the vacuous green the header describes.
    """
    env = dict(os.environ)
    ci_dir = str(root / ".ci")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = ci_dir + (os.pathsep + existing if existing else "")
    proc = subprocess.run(
        [sys.executable, "-c", PROBE_SCRIPT, str(port)],
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
        [sys.executable, "-c", _LISTENER_BOOT, str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# PR_SET_PDEATHSIG: KILL THIS CHILD WHEN ITS PARENT DIES.
#
# Every caller already wraps start_listener in `try/finally: server.kill()`, and that is enough for a normal exit. It is NOT enough when the PARENT is killed: a SIGKILLed interpreter never reaches its finally, the listener survives, and init adopts it. Measured on this box 2026-09-07: 131 orphaned `python3 -m http.server` processes, the oldest 25 hours, parented to pid 1 -- left
# behind by pytest runs that were killed by `timeout` or by hand.
#
# It got worse the moment this suite went parallel: `check:ci-pytest` now runs under `-n 8`, so a killed run strands up to eight workers' worth of listeners instead of one process's worth.
#
# THE CHILD ARMS ITSELF. This used to be a `preexec_fn`, which runs between fork and exec and is documented as unsafe in a threaded parent (ruff PLW1509). The listener now starts through a short bootstrap that calls prctl as its first act and then runs `http.server` as `__main__`, so nothing runs between fork and exec and the parent's threads no longer matter. The window between exec and the prctl call is a few milliseconds of interpreter start-up.
_LISTENER_BOOT = """
import contextlib, ctypes, runpy, signal, sys
# Best effort, never fatal: a platform without libc or without prctl keeps the old behaviour. 1 is PR_SET_PDEATHSIG; Python has no binding for it and the number is part of the kernel ABI.
with contextlib.suppress(Exception):
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)
sys.argv = ["http.server", sys.argv[1], "--bind", "127.0.0.1"]
runpy.run_module("http.server", run_name="__main__", alter_sys=True)
"""


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

    # Fail loudly if the library cannot be loaded at all: a gate that cannot reach its subject must not report on it. Port 1 is closed, so a HEALTHY probe returns non-zero here; only LOAD_FAILED_RC means the load failed.
    first_rc = probe_rc(root, 1)
    if first_rc == LOAD_FAILED_RC:
        log.error("Could not import %s from %s." % (PROBE_FN, PROBE_LIB))
        log.error("Refusing to report on a probe this gate cannot actually call.")
        return 1
    if first_rc == PROBE_RAISED_RC:
        log.error(
            "%s was imported from %s but raised when called on port 1." % (PROBE_FN, PROBE_LIB)
        )
        log.error("Refusing to report on a probe this gate cannot actually call.")
        return 1

    failures = 0

    # --- 1. THE DEFECT: a closed port must read as dead ---------------------
    dead_port = free_port()
    dead_rc = probe_rc(root, dead_port)
    if dead_rc not in (0, 1):
        log.error(
            "%s neither said ALIVE nor DEAD for closed port %d (rc=%d)."
            % (PROBE_FN, dead_port, dead_rc)
        )
        failures += 1
    elif dead_rc == 0:
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

# The fixture module bodies. Written as literals, never by substituting into a copy of the real account.py: a substitution silently yields an unmutated copy the day the targeted line is reworded, and the control then passes against source it never changed.
FIXTURE_HEALTHY = """import subprocess


def rustfs_alive(port):
    proc = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-m", "2", "-w", "%{http_code}", "http://127.0.0.1:%d/" % port],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout not in {"", "000"}
"""

# The 2026-08-04 shape, restored: a fallback appended on a non-zero exit, so a refused connection captures `000000`.
FIXTURE_DEFECTIVE = FIXTURE_HEALTHY.replace(
    '    return proc.stdout not in {"", "000"}',
    '    out = proc.stdout + ("000" if proc.returncode != 0 else "")\n    return out != "000"',
)

# A probe that can never say yes. Assertion 1 passes against it, which is exactly why assertion 2 exists.
FIXTURE_ALWAYS_DEAD = FIXTURE_HEALTHY.replace(
    '    return proc.stdout not in {"", "000"}', "    return False"
)

# A probe that loads and then raises. Its child must exit PROBE_RAISED_RC, not 1, or a broken probe would read as a correctly dead one.
FIXTURE_RAISES = "def rustfs_alive(port):\n    raise RuntimeError('boom')\n"

# A module that loads and defines nothing. The load probe must see this, or "not alive" would read as "correctly dead".
FIXTURE_NO_FUNCTION = "def something_else():\n    return True\n"


def fixture_root(tmp: pathlib.Path, body: str) -> pathlib.Path:
    """A throwaway tree carrying a minimal `rediacc_ci.core.account` and nothing else."""
    core = tmp / ".ci" / "rediacc_ci" / "core"
    core.mkdir(parents=True, exist_ok=True)
    (tmp / ".ci" / "rediacc_ci" / "__init__.py").write_text("", encoding="utf-8")
    (core / "__init__.py").write_text("", encoding="utf-8")
    (core / "account.py").write_text(body, encoding="utf-8")
    return tmp


def selftest() -> int:
    """Both directions for every assertion, plus both directions for each helper.

    A gate with only positive controls will happily flag the whole tree, so every plant below has a mirror: the defective library must be caught AND the healthy one must be cleared, a closed port must read dead AND a live one alive, a missing function must be seen AND a present one must not be mistaken for missing.
    """
    ctl = Controls("account-probes", floor=23, verbose=True)

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

    # -- the probe child carries the load-bearing lines --------------------
    ctl.truthy(
        "the probe imports the function by name", "import %s as probe" % PROBE_FN in PROBE_SCRIPT
    )
    ctl.truthy(
        "the probe exits with the load-failed status when the import fails",
        "sys.exit(%d)" % LOAD_FAILED_RC in PROBE_SCRIPT,
    )

    with tempfile.TemporaryDirectory() as tmp:
        root_healthy = fixture_root(pathlib.Path(tmp) / "healthy", FIXTURE_HEALTHY)
        root_defect = fixture_root(pathlib.Path(tmp) / "defect", FIXTURE_DEFECTIVE)
        root_dead = fixture_root(pathlib.Path(tmp) / "dead", FIXTURE_ALWAYS_DEAD)
        root_nofn = fixture_root(pathlib.Path(tmp) / "nofn", FIXTURE_NO_FUNCTION)
        root_raises = fixture_root(pathlib.Path(tmp) / "raises", FIXTURE_RAISES)

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

        ctl.check(
            "PLANT: a probe that raises exits with the raised status, not the DEAD one",
            probe_rc(root_raises, 1),
            PROBE_RAISED_RC,
        )
        ctl.check(
            "MIRROR: a healthy probe says DEAD (rc 1) for a closed port",
            probe_rc(root_healthy, closed),
            1,
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
        ctl.check("PLANT: a probe that raises reds the whole gate", run(root_raises), 1)

        # An ABSENT library is a failure, never a pass: "a probe library that vanished cannot be verified."
        bare = pathlib.Path(tmp) / "bare"
        bare.mkdir()
        ctl.check("PLANT: a missing probe library reds rather than skipping", run(bare), 1)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
