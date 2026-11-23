"""Run one guard IN THIS PROCESS, observed the way a `python3 dispatch.py <stem>` child would be.

WHY (agent/plans/PLAN-ciquick-cpu.md W15). Almost all of the guard suites' time was process start: every case of `hookcases.STATIC` and of the standalone `guards/test-*.py` suites forked a fresh interpreter, imported the package and ran ONE guard for a few milliseconds. `dispatch.run_one` is the same call the child makes, so a case can be answered here for the cost of the guard itself.

WHAT A CHILD GETS THAT A CALL DOES NOT, and what this module does about each one. The list is the contract; a new difference found is a new line here, not a quiet special case in a suite.

  * The ENVIRONMENT. `os.environ` is SWAPPED for the case's, not passed down, because a guard that shells out to `git` or `gh` hands its children the process environment, not the `env` the event was built with (the reason test_guards_differential.py's `python_fields` swaps it too).
  * The local ZONE. libc reads `TZ` once and caches it, so `time.tzset()` runs after the swap and again after the restore.
  * The temp DIRECTORY. `tempfile.gettempdir()` caches its first answer in `tempfile.tempdir`; a child reads `TMPDIR` afresh, so the cache is cleared for the call and put back afterwards.
  * The working DIRECTORY. A child runs in `cwd`; here the process `chdir`s there for the call, so a relative path or a `git` child with no `cwd=` lands where it would have.
  * A FRESH MODULE. A child imports the guard anew, so whatever its module body computed (a path from the environment, today's date, the temp directory) is that child's, and nothing an earlier case or the caller did to the module object survives. `fresh_guards` gives each call the same: a new module object built from the guard's spec and executed INSIDE the swapped world, put in `sys.modules` for the call only, with the caller's own module object (and any seam a suite patched onto it for its own in-process pass) put back afterwards. Measured 2026-11-23: 0.22 ms per guard at the median, 68 ms for all of them. Found the hard way: test-block_second_open_pr.py patches `_landing_record` onto the live module for its seam pass, and a reused module carried that patch into the next case's dispatcher answer, 19 cases red.
  * STDIN, STDOUT, STDERR. The payload is offered on `sys.stdin`, and anything a guard prints directly is captured and placed before the event's own output, which is the order `dispatch.main` writes them in.
  * EXIT. A `SystemExit` becomes its exit code. An uncaught exception PROPAGATES to the caller, as it does from test_guards_differential.py's `python_fields`, where a child would have exited 1 with the traceback on stderr: both are a red case, and the in-process one names the failing line directly instead of through a captured stderr.
  * A HANG. `subprocess.run(timeout=)` turned a guard that waits on stdin into one named failure. Here SIGALRM does the same, raising `subprocess.TimeoutExpired`, when the call is on the main thread and no other alarm is armed. The alarm is a `BaseException`, so a guard's own `except Exception` cannot swallow it.

WHAT STAYS A REAL PROCESS. Any argv that is not exactly `<python> <dispatch.py> <stem>` (a `--chain` run, a bash program, another script), a call that hands the child a real stdin file, a call from any thread but the main one (the swaps above are process-wide, and test-block_origin_clone.py's thread pool lost its own output to a neighbour's `sys.stdout` swap the first time this ran), and any guard in `PROCESS_STEMS`: the three that read the live process table, whose answer would name this interpreter's command line instead of a dispatcher's. `tests/test_hooks_boundary.py` keeps one real `dispatch.py <stem>` run per guard and compares a deny and an allow per chain against `run_chain`, so the process path is still proven for every guard.

A standalone suite in this directory imports it as `import _hookpath` (which puts `.claude` on `sys.path`) followed by `from rediacc_hooks.guards import _harness`.
"""

import contextlib
import importlib.util
import io
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import time

from rediacc_hooks import dispatch, guards

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = (HERE.parent / "dispatch.py").resolve()

# Read the live process table; an in-process answer would see the test interpreter, not a dispatcher (test_guards_differential.py PROCESS_TABLE_READERS).
PROCESS_STEMS = frozenset(
    {
        "block_self_matching_pgrep",
        "block_bash_write_to_running_script",
        "block_edit_of_running_script",
    }
)


@contextlib.contextmanager
def fresh_guards(stems):
    """`stems`' modules re-imported as NEW objects for the length of the block, the caller's own objects put back afterwards.

    Built from the existing spec, so the loader is the one a child's import would use (and check:ci-guard-mutations' redirect, which sits in `SourceFileLoader.get_code`, still hands over its planted copy). The parent package's attribute is swapped with the `sys.modules` entry, since `from rediacc_hooks.guards import <stem>` reads the attribute.
    """
    package = sys.modules[guards.PACKAGE]
    saved = []
    try:
        for stem in stems:
            name = "%s.%s" % (guards.PACKAGE, stem)
            spec = importlib.util.find_spec(name)
            if spec is None or spec.loader is None:
                raise ModuleNotFoundError("no guard module %s" % name)
            saved.append((name, stem, sys.modules.get(name), getattr(package, stem, None)))
            fresh = importlib.util.module_from_spec(spec)
            sys.modules[name] = fresh
            setattr(package, stem, fresh)
            spec.loader.exec_module(fresh)
        yield
    finally:
        for name, stem, module, attribute in reversed(saved):
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
            if attribute is None:
                with contextlib.suppress(AttributeError):
                    delattr(package, stem)
            else:
                setattr(package, stem, attribute)


def dispatch_stem(argv) -> str | None:
    """The guard stem when `argv` is exactly `<python> <dispatch.py> <stem>` for a stem this process may answer, else None."""
    if not isinstance(argv, (list, tuple)) or len(argv) != 3:
        return None
    exe, script, stem = (str(part) for part in argv)
    if exe != sys.executable and os.path.basename(exe) not in ("python", "python3"):
        return None
    if pathlib.Path(script).resolve() != DISPATCH:
        return None
    if stem.startswith("-") or stem in PROCESS_STEMS or stem not in guards.stems():
        return None
    return stem


class _DeadlineError(BaseException):
    """The SIGALRM deadline fired; outside `Exception` so a guard's own broad handler cannot eat it."""


@contextlib.contextmanager
def _deadline(seconds):
    """SIGALRM after `seconds`, only where it is safe: the main thread, with no alarm already armed."""
    usable = (
        seconds
        and threading.current_thread() is threading.main_thread()
        and signal.getitimer(signal.ITIMER_REAL)[0] == 0
    )
    if not usable:
        yield
        return

    def fire(_signum, _frame):
        raise _DeadlineError

    previous = signal.signal(signal.SIGALRM, fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _exit_code(code) -> int:
    if code is None:
        return 0
    if isinstance(code, bool):
        return int(code)
    if isinstance(code, int):
        return code & 0xFF
    return 1


@contextlib.contextmanager
def child_world(env, cwd, payload):
    """The process state a dispatcher child would start with, for the length of one call, then the runner's own put back."""
    saved_env = dict(os.environ)
    saved_cwd = os.getcwd()
    saved_tempdir = tempfile.tempdir
    saved_streams = (sys.stdin, sys.stdout, sys.stderr)
    out, err = io.StringIO(), io.StringIO()
    if env is not None:
        os.environ.clear()
        os.environ.update({str(k): str(v) for k, v in env.items()})
    time.tzset()
    tempfile.tempdir = None
    try:
        if cwd is not None:
            os.chdir(cwd)
        sys.stdin = io.StringIO(payload)
        sys.stdout, sys.stderr = out, err
        yield out, err
    finally:
        sys.stdin, sys.stdout, sys.stderr = saved_streams
        os.chdir(saved_cwd)
        tempfile.tempdir = saved_tempdir
        if env is not None:
            os.environ.clear()
            os.environ.update(saved_env)
        time.tzset()


def _answer(stems, payload, env, cwd, timeout, argv):
    """`(rc, stdout, stderr)` of one dispatcher child that runs `stems` in order through `dispatch.run_one`, stopping at the first non-zero exit: ONE world and ONE set of fresh modules for the whole run, as one child process has."""
    if threading.current_thread() is not threading.main_thread():
        msg = "the in-process runner swaps process-wide state and runs only on the main thread; off it, use run()"
        raise RuntimeError(msg)
    rc, outs, errs = 0, [], []
    with child_world(env, cwd, payload) as (direct_out, direct_err):
        try:
            with _deadline(timeout), fresh_guards(stems):
                for stem in stems:
                    rc, out, err = dispatch.run_one(stem, payload)
                    rc = _exit_code(rc)
                    outs.append(out)
                    errs.append(err)
                    if rc != 0:
                        break
        except _DeadlineError:
            raise subprocess.TimeoutExpired(argv, timeout) from None
        except SystemExit as exc:
            rc = _exit_code(exc.code)
            if isinstance(exc.code, str):
                direct_err.write(exc.code + "\n")
    return rc, direct_out.getvalue() + "".join(outs), direct_err.getvalue() + "".join(errs)


def run_inprocess(stem, payload, env=None, cwd=None, timeout=None):
    """`(rc, stdout, stderr)` of `dispatch.py <stem>` with `payload` on stdin, answered in this process.

    `env` None keeps this process's environment and `cwd` None its directory, which is what a child spawned with neither would inherit.
    """
    return _answer([stem], payload, env, cwd, timeout, ["dispatch.py", stem])


def run_chain_inprocess(chain, payload, env=None, cwd=None, timeout=None):
    """`(rc, stdout, stderr)` of `dispatch.py --chain <chain>`, answered here: one child world, the chain's guards imported afresh once, and each guard through `dispatch.run_one` in `guards.by_chain` order, stopping at the first non-zero exit, which is `dispatch.run_chain`'s rule. An empty chain refuses with `dispatch.EMPTY_CHAIN`, as the dispatcher does.

    ONE WORLD FOR THE CHAIN, as one child has. Measured 2026-11-23 on a pre-bash payload whose guards fork git 191 times: a world and an import per guard cost 2.28 s against 1.41 s for the same chain in one world, the forks being equal.

    One difference is kept visible rather than papered over: a guard that RAISES propagates here, where the dispatcher names the crash and runs the rest of the chain. The caller's case then fails on that payload, which is the right answer to a crashing guard.
    """
    stems = [module.__name__.rsplit(".", 1)[-1] for module in guards.by_chain(chain)]
    if not stems:
        return 2, "", dispatch.EMPTY_CHAIN % (chain, chain)
    return _answer(stems, payload, env, cwd, timeout, ["dispatch.py", "--chain", chain])


def _real_run(argv, options):
    kwargs = {key: value for key, value in options.items() if value is not None}
    if kwargs.get("capture_output"):
        kwargs.pop("stdout", None)
        kwargs.pop("stderr", None)
    return subprocess.run(argv, check=kwargs.pop("check", False), **kwargs)


def run(argv, **options):
    """`subprocess.run` for a guard suite: the same keywords and the same `CompletedProcess`, answered in this process when `argv` is a dispatcher run (`dispatch_stem`) and handed to the real `subprocess.run` otherwise.

    A suite swaps `subprocess.run(GUARD_ARGV, ...)` for `_harness.run(GUARD_ARGV, ...)` and changes nothing else. A keyword this function does not model (a real stdin file, `preexec_fn`, `start_new_session`, ...) sends the call to a real process rather than being ignored.
    """
    modelled = {
        "input",
        "env",
        "cwd",
        "timeout",
        "check",
        "text",
        "encoding",
        "errors",
        "capture_output",
        "stdout",
        "stderr",
        "stdin",
        "universal_newlines",
    }
    stem = dispatch_stem(argv) if threading.current_thread() is threading.main_thread() else None
    if (
        stem is None
        or set(options) - modelled
        or options.get("stdin") not in (None, subprocess.PIPE)
    ):
        return _real_run(argv, options)
    as_text = bool(
        options.get("text")
        or options.get("universal_newlines")
        or options.get("encoding")
        or options.get("errors")
    )
    data = options.get("input")
    if data is None:
        payload = ""
    elif isinstance(data, bytes):
        payload = data.decode(options.get("encoding") or "utf-8", options.get("errors") or "strict")
    else:
        payload = data
    rc, out, err = run_inprocess(
        stem,
        payload,
        env=options.get("env"),
        cwd=options.get("cwd"),
        timeout=options.get("timeout"),
    )
    capture = options.get("capture_output")
    stdout_opt, stderr_opt = options.get("stdout"), options.get("stderr")
    if stderr_opt is subprocess.STDOUT:
        out, err = out + err, ""
    keep_out = capture or stdout_opt is subprocess.PIPE
    keep_err = (capture or stderr_opt is subprocess.PIPE) and stderr_opt is not subprocess.STDOUT
    # Inherited streams: a child with no redirect writes to the runner's own stdout and stderr.
    if not capture and stdout_opt is None:
        sys.stdout.write(out)
    if not capture and stderr_opt is None:
        sys.stderr.write(err)
    if not as_text:
        out, err = out.encode("utf-8", "surrogateescape"), err.encode("utf-8", "surrogateescape")
    done = subprocess.CompletedProcess(
        list(argv), rc, out if keep_out else None, err if keep_err else None
    )
    if options.get("check"):
        done.check_returncode()
    return done
