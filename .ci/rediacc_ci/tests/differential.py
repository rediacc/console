"""Run the bash original and the Python port, and compare the bytes.

WHY THIS FILE EXISTS. Every module in `rediacc_ci` replaces something that is already running in this tree, and "the port looks right" is not evidence. The acceptance rule for the whole workstream is that a port is proven EQUIVALENT to the thing it replaces, in the shape `.ci/scripts/quality/check-python-lint.sh` already uses for its own control: build a specimen, run both
implementations over it, and compare. This module is the plumbing that makes that cheap enough to do for every case rather than for one.

THREE THINGS IT GETS RIGHT THAT AN INLINE `subprocess.run` DOES NOT.

  1. STDOUT AND STDERR ARE NEVER MERGED. `2>&1` is the default reflex and it
     destroys exactly the defect these tests exist to catch. The 2026-09-06
     emit-advisory incident was a STREAM SWAP -- log_info moved from stderr to
     stdout -- and the emit-advisory gate test said so in as many words, at
     `.ci/scripts/test/gates/test-emit-advisory.sh:100-102` before W7 P5 retired
     that twin and `.ci/rediacc_ci/tests/gates/test_gate_emit_advisory.py` took
     the cases over: "The cases below capture stdout and stderr into
     SEPARATE files on purpose. The defect is a stream swap; the `2>&1` used by
     every case above merges the two streams back together and would hide it
     completely." Every function here returns the two separately, and there is
     no option to combine them.

  2. A REAL TTY IS AVAILABLE. Colour is decided by `isatty`, so a differential
     that only ever runs off a tty proves the boring half. `bash_streams(...,
     tty="stderr")` puts a pseudo-terminal on the stream under test, which is
     the only way to exercise the branch a developer actually sees.

  3. THE ENVIRONMENT IS EXPLICIT. `env=` REPLACES rather than extends, with a
     small documented base, because a differential that inherits the caller's
     environment passes or fails depending on whether the developer running it
     happens to export CI or NO_COLOR. Inheriting is how a test becomes green
     on one machine and red on another for reasons nobody can see.

WHAT A PTY DOES TO THE BYTES, since it is the part that surprises people. A tty in its default mode has ONLCR set, so every `\\n` the child writes arrives at the master as `\\r\\n`. That is the terminal discipline, not the program's output, so `read_pty` strips the carriage returns. Without that every tty-mode comparison fails on invisible bytes and the natural "fix" is to compare
stripped strings, which would also stop the comparison seeing a real trailing-whitespace change.
"""

import os
import pathlib
import pty
import re
import selectors
import subprocess

from rediacc_ci import paths, runtmp


def _child_tmpdir() -> str:
    r"""A TMPDIR for every child this module's environments start: `<run dir>/tmp`, one per test process.

    WHY. Without it a child's `mktemp` wrote to /tmp itself, and a twin that leaves its `mktemp` files behind (a call log, a fetch log, a staged index) left them there for good: 4,948 `tmp.XXXXXXXXXX` files had accumulated by 2026-09-24. The run dir is removed at exit and swept by the next run when this one was killed first (`rediacc_ci.runtmp`).

    WHY THE `/tmp` LEAF. Several differentials mask the random `mktemp` suffix with a regex written against its shape, `/tmp/tmp\.[A-Za-z0-9]{10}`. Ending the directory in `/tmp` keeps that shape as the path's tail, and the prefix before it is the same on both sides of a comparison because both run in this process.
    """
    leaf = os.path.join(runtmp.run_dir("difftest-"), "tmp")
    os.mkdir(leaf)
    return leaf


# The environment every differential starts from. Deliberately tiny.
#
# PATH is needed (bash resolves `git`, `timeout`, `sleep` through it). HOME is
# needed because git refuses some operations without one. LC_ALL=C pins message
# text and, more importantly, sort order: `git ls-files` output compared against a Python sort diverges under a locale with different collation, which is a difference in the TEST rather than in the thing under test.
BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "TMPDIR": _child_tmpdir(),
}

# How long any single differential child may run. A hung bash in a test suite is indistinguishable from a slow one until CI's own job timeout fires 15 minutes later, having reported nothing.
DEFAULT_TIMEOUT = 60


def repo() -> str:
    """The repository root as a string, for `cwd=`."""
    return str(paths.repo_root())


def env_for(**overrides: str | None) -> dict[str, str]:
    """BASE_ENV plus overrides. A value of None REMOVES the key.

    The removal case is the interesting one: several conditions in this repo are
    `[ -z "${NO_COLOR:-}" ]` or `[ "${CI:-}" != "true" ]`, which distinguish
    unset from empty-string in ways `env["X"] = ""` cannot express.
    """
    out = dict(BASE_ENV)
    for key, value in overrides.items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def read_pty(master_fd: int, proc: subprocess.Popen, timeout: float) -> bytes:
    """Drain a pty master until the child exits and the buffer is empty.

    THE EIO IS NORMAL, NOT AN ERROR. When the last slave descriptor closes, Linux reports EIO to a reader of the master rather than a clean EOF. Treating that as a failure is the classic pty bug; treating it as end-of-stream is correct.

    A selector rather than a blocking read because the child may exit having written nothing, and a blocking read on a master whose slave this process still holds open would never return.
    """
    chunks: list[bytes] = []
    sel = selectors.DefaultSelector()
    sel.register(master_fd, selectors.EVENT_READ)
    deadline_hits = 0
    try:
        while True:
            events = sel.select(timeout=0.25)
            if events:
                try:
                    data = os.read(master_fd, 65536)
                except OSError:
                    break  # EIO: every slave is closed, so this is the end
                if not data:
                    break
                chunks.append(data)
                continue
            if proc.poll() is not None:
                # The child is gone and nothing is pending. One more short pass catches bytes written between the poll and the select.
                deadline_hits += 1
                if deadline_hits >= 2:
                    break
            else:
                deadline_hits += 1
                if deadline_hits * 0.25 > timeout:
                    break
    finally:
        sel.close()
    # ONLCR: the line discipline turns every \n into \r\n on the way out. That is the terminal's doing, not the program's, so it is undone here rather than by every caller comparing stripped strings.
    return b"".join(chunks).replace(b"\r\n", b"\n")


def bash_streams(
    script: str,
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    tty: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, str, str]:
    """Run `script` under bash. Returns (returncode, stdout, stderr), separately.

    `tty` is None, "stdout" or "stderr": the named stream gets a pseudo-terminal and the other gets a pipe. Only one at a time, on purpose -- the whole point of most of these cases is that one stream is a terminal and the other is not, which is precisely the asymmetry the 11-file `[ -t 1 ]`-then-write-to-stderr variant gets wrong.

    `bash`, not `sh`: every script here is `#!/bin/bash` and uses `[[`.
    """
    environ = BASE_ENV if env is None else env
    workdir = repo() if cwd is None else cwd

    if tty is None:
        proc = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
            cwd=workdir,
            env=environ,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr

    if tty not in ("stdout", "stderr"):
        raise ValueError("tty must be None, 'stdout' or 'stderr' (got %r)" % tty)

    master_fd, slave_fd = pty.openpty()
    other = subprocess.PIPE
    kwargs = (
        {"stdout": slave_fd, "stderr": other}
        if tty == "stdout"
        else {
            "stdout": other,
            "stderr": slave_fd,
        }
    )
    proc = subprocess.Popen(
        ["bash", "-c", script],
        cwd=workdir,
        env=environ,
        text=False,
        **kwargs,
    )
    # CLOSED IN THE PARENT IMMEDIATELY. While this process holds the slave open, the master never sees EOF and read_pty would spin until its timeout on every single case -- turning a fast suite into a slow one for a reason that looks like flakiness.
    os.close(slave_fd)
    try:
        tty_text = read_pty(master_fd, proc, timeout).decode("utf-8", "replace")
        pipe_bytes = b""
        pipe = proc.stdout if tty == "stderr" else proc.stderr
        if pipe is not None:
            pipe_bytes = pipe.read()
            pipe.close()
        proc.wait(timeout=timeout)
    finally:
        os.close(master_fd)
    pipe_text = pipe_bytes.decode("utf-8", "replace")
    if tty == "stdout":
        return proc.returncode, tty_text, pipe_text
    return proc.returncode, pipe_text, tty_text


def escape_bytes(text: str) -> int:
    """How many ESC bytes are in `text`.

    The single number that answers "did colour leak into this stream", which is the assertion `test_gate_emit_advisory.py` carries, and `test-emit-advisory.sh:172` made before that twin's W7 P5 retirement, with `tr -cd '\\033' | wc -c`. Counted rather than pattern-matched so a NEW escape sequence nobody anticipated still trips it.
    """
    return text.count("\033")


# `<cache>/shfmt-3.13.1/shfmt.1R2NkECK` -> `.../shfmt.<tmp>`, and the same for shellcheck's `sc.XXXXXXXX` and actionlint's `al.XXXXXXXX` staging directories.
#
# BOTH toolchain download helpers give every process its OWN temp name, because the single fixed path they shared before was a data-corruption race between concurrent acquirers (the reasoning is at `.ci/scripts/lib/toolchain.sh`, in `_toolchain_download_shfmt`). The randomness IS the fix, so it is the one token a twin/port differential must not demand equality of -- `mktemp` and
# `tempfile` draw from different alphabets and always will. Masking it leaves every observable claim intact: the flags, the URL, the order, and the fact that a temp path is used at all.
#
# Shared rather than copied into each differential, because the first version of this lived in the shfmt module alone and the shellcheck module failed the same way twenty minutes later.
_TOOLCHAIN_TMP_RE = re.compile(r"(/(?:shfmt|sc|al))\.[A-Za-z0-9_]{8}\b")


def mask_toolchain_tmp(text: str) -> str:
    """Replace per-process toolchain temp names with a stable `<tmp>`."""
    return _TOOLCHAIN_TMP_RE.sub(r"\1.<tmp>", text)


# --------------------------------------------------------------------------- Goldens: the bash side, frozen ---------------------------------------------------------------------------
#
# PLAN-retire-bash-oracles B3. A differential proves a port MATCHES its bash twin, which keeps the twin on disk forever. `twin_streams` is the seam that lets the twin go: it answers exactly what `bash_streams` answered for the twin's command, but out of a frozen golden, so a test written against `old, new = twin..., port...` keeps comparing the port against the bash
# behaviour after the bash file is deleted.
#
# THE FORMAT IS THE HOOKS' FORMAT, NOT A LOOK-ALIKE. `.claude/rediacc_hooks/tests/goldenio.py` (A1, commit b9714c304) owns the JSONL framing: a `_header` line, a `_silent` key list, then one `rc`/`out`/`err` record per non-silent key, with `intentional: "<reason>"` on a record a Rule-T change moved. It is loaded here BY PATH rather than copied, so there is one writer, one reader and
# one `diff_and_mark` for both trees; `.ci` cannot import it by name because pytest only puts `.claude` on sys.path once a hook test has been collected, which a `.ci`-only run never does.
#
# THE ONE THING ADDED FOR `.ci` IS THE HEADER'S `twin_blob`: the git blob sha of the bash file the answers were recorded from (`git hash-object`), which is what the 2026-09-21 ruling asks a retired twin's golden to carry. The bash text stays recoverable with `git cat-file -p <twin_blob>` after the file is gone.
#
# THREE MODES, chosen by `REDIACC_CI_REGOLDEN` (only `regolden.py` sets it):
#   unset   COMPARE. The answer comes from the golden; a key the golden lacks FAILS, naming the verb that records it. The twin file is never read, so deleting it changes nothing.
#   bash    RECORD FROM THE TWIN. Runs bash exactly as before and keeps the answer. Only possible while the `.sh` still exists: this is the freeze.
#   port    RECORD FROM THE PORT. For a Rule-T change after the twin is gone. Needs the call site to pass `port=`; every record whose value moved is stamped `intentional: <reason>`.


def _load_goldenio():
    import importlib.util  # noqa: PLC0415 - only this loader needs it

    path = paths.repo_root() / ".claude" / "rediacc_hooks" / "tests" / "goldenio.py"
    spec = importlib.util.spec_from_file_location("rediacc_ci_tests_goldenio", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("%s is missing: the shared golden format has no reader" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


goldenio = _load_goldenio()

GOLDEN_DIR = paths.repo_root() / ".ci" / "rediacc_ci" / "tests" / "goldens" / "twins"
REGOLDEN_ENV = "REDIACC_CI_REGOLDEN"
# The stems a regolden run is recording, comma-separated. A module that touches the named twin may touch OTHER twins too (initialize's differential also drives the pointer-bump detector), and those must keep answering from their goldens: re-recording a twin nobody asked about, or failing because its `.sh` is already gone, is not this run's business.
ONLY_ENV = "REDIACC_CI_REGOLDEN_ONLY"
REGOLDEN_VERB = "PYTHONPATH=.ci python3 -m rediacc_ci.tests.regolden"

Answer = tuple[int, str, str]

# Recording state for one regolden process: {stem: {key: (rc, out, err)}} and {stem: twin path}. Empty in every ordinary run.
RECORDED: dict[str, dict[str, Answer]] = {}
RECORDED_TWINS: dict[str, str] = {}
_LOADED: dict[str, tuple[dict, set[str], dict[str, dict]]] = {}
_OCCURRENCE: dict[tuple[str, str], int] = {}


def regolden_mode(twin: str | None = None) -> str | None:
    """None (compare), "bash" or "port". Anything else is refused rather than read as compare. With `twin`, a run recording other stems answers None for this one."""
    mode = os.environ.get(REGOLDEN_ENV) or None
    if mode not in (None, "bash", "port"):
        raise RuntimeError("%s=%r: expected 'bash' or 'port'" % (REGOLDEN_ENV, mode))
    only = os.environ.get(ONLY_ENV)
    if mode is not None and twin is not None and only and golden_stem(twin) not in only.split(","):
        return None
    return mode


def golden_stem(twin: str) -> str:
    """`.ci/scripts/ci/assert-job-succeeded.sh` -> `ci.assert-job-succeeded`. The directory is kept because two twins share a basename (`build/build-renet.sh`, `infra/build-renet.sh`)."""
    rel = str(twin).replace("\\", "/")
    root = str(paths.repo_root()).rstrip("/") + "/"
    rel = rel.removeprefix(root).removeprefix(".ci/scripts/").removeprefix(".ci/")
    return rel.removesuffix(".sh").replace("/", ".")


def golden_file(twin: str) -> pathlib.Path:
    return GOLDEN_DIR / ("%s.jsonl" % golden_stem(twin))


def _folds(work: tuple[str, ...]) -> list[tuple[str, str]]:
    """(literal, token) pairs, LONGEST literal first so a tmp root inside the checkout or under HOME wins over its prefix.

    Each token names something that differs between the recording machine and every later one: the caller's scratch roots, this process's run dir, the checkout, HOME and the inherited PATH. Nothing else is folded, so a real change in a message still shows.
    """
    pairs = [(str(w), "<WORK%d>" % i) for i, w in enumerate(work) if str(w)]
    run = os.path.dirname(BASE_ENV["TMPDIR"])
    pairs += [
        (run, "<RUN>"),
        (str(paths.repo_root()), "<REPO>"),
        (BASE_ENV["PATH"], "<PATH>"),
    ]
    # Not when HOME is `/` or `/tmp` (an unset HOME falls back to the latter): folding a root every scratch path lives under would fold all of them.
    if BASE_ENV["HOME"] not in ("/", "/tmp"):
        pairs.append((BASE_ENV["HOME"], "<HOME>"))
    return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def fold(text: str, work: tuple[str, ...] = ()) -> str:
    for literal, token in _folds(work):
        text = text.replace(literal, token)
    return text


def unfold(text: str, work: tuple[str, ...] = ()) -> str:
    """The inverse of `fold` for THIS run: a golden recorded elsewhere reads back with this machine's paths in it, so the call site compares raw text exactly as it did when bash answered live."""
    for literal, token in sorted(_folds(work), key=lambda p: len(p[1]), reverse=True):
        text = text.replace(token, literal)
    return text


def _current_label() -> str:
    """The test that is asking, from pytest's own `PYTEST_CURRENT_TEST`.

    A call made from a fixture's setup is labelled `fixture`, not after the test that happened to trigger it first: which test sets up a module-scoped fixture depends on scheduling, and a key that moved with the scheduler would miss under xdist.
    """
    current = os.environ.get("PYTEST_CURRENT_TEST", "")
    node, _, phase = current.rpartition(" ")
    if not node:
        return "outside-pytest"
    if phase != "(call)":
        return "fixture"
    return node.split("::", 1)[-1]


def case_key(parts: list[str], *, work: tuple[str, ...], label: str | None) -> str:
    """`<label>#<content hash>[/<n>]`. `parts` are folded before hashing, so the key is the same on any machine; `/n` separates the n-th identical call inside one test (a call repeated after the test changed a fixture).

    An EXPLICIT `label` names a value shared by every call with the same content (a frozen input corpus read by several tests), so it gets no `/n`: the n-th read of one shared value is the same record, not a new one.
    """
    if label is not None:
        return goldenio.case_key(label, *[fold(p, work) for p in parts])
    name = _current_label()
    key = goldenio.case_key(name, *[fold(p, work) for p in parts])
    seen = _OCCURRENCE.get((name, key), 0)
    _OCCURRENCE[(name, key)] = seen + 1
    return key if seen == 0 else "%s/%d" % (key, seen)


def twin_key(
    script: str,
    *,
    env: dict[str, str] | None,
    cwd: str | None,
    tty: str | None,
    work: tuple[str, ...],
    label: str | None,
) -> str:
    """The key `twin_streams` uses: the command, the environment, cwd and tty."""
    child_env = BASE_ENV if env is None else env
    parts = [script, "tty=%s" % tty, "cwd=%s" % (cwd or repo())]
    parts += ["%s=%s" % (k, child_env[k]) for k in sorted(child_env)]
    return case_key(parts, work=work, label=label)


def load_golden(twin: str) -> tuple[dict, set[str], dict[str, dict]]:
    stem = golden_stem(twin)
    if stem not in _LOADED:
        path = golden_file(twin)
        header, silent, records = goldenio.read_golden(path)
        if header is None:
            raise AssertionError(
                "no golden for %s at %s. While the twin exists, freeze it with:\n  %s %s "
                '--source bash --reason "<why>"' % (twin, path, REGOLDEN_VERB, twin)
            )
        _LOADED[stem] = (header, silent, records)
    return _LOADED[stem]


def golden_answer(twin: str, key: str, work: tuple[str, ...] = ()) -> Answer:
    _header, silent, records = load_golden(twin)
    row = goldenio.lookup(silent, records, key)
    if row is None:
        raise AssertionError(
            "golden %s has no answer for %s. A NEW case has no bash left to record it from: "
            'add it with `%s %s --source port --reason "<why>"` and review the diff.'
            % (golden_stem(twin), key, REGOLDEN_VERB, twin)
        )
    out = goldenio.decode_field(row.get("out", ""))
    err = goldenio.decode_field(row.get("err", ""))
    return int(row["rc"]), unfold(out, work), unfold(err, work)


def _record(twin: str, key: str, answer: Answer, work: tuple[str, ...]) -> None:
    stem = golden_stem(twin)
    rc, out, err = answer
    RECORDED.setdefault(stem, {})[key] = (rc, fold(out, work), fold(err, work))
    RECORDED_TWINS[stem] = str(twin)


def _work_tuple(work) -> tuple[str, ...]:
    return tuple(str(w) for w in (work if isinstance(work, (list, tuple)) else (work,)))


# What a file the twin did NOT write is recorded as, so "absent" and "empty" stay different answers.
ABSENT = "\x00absent"


def twin_run(
    twin: str,
    parts: list[str],
    bash,
    *,
    files=(),
    extras=None,
    port=None,
    work=(),
    label: str | None = None,
) -> tuple[int, str, str, dict[str, str]]:
    """The general seam, for a twin whose answer is more than two streams.

    `bash()` is how the differential ran the twin (any harness, any fixture) and returns `(rc, out, err)`; `parts` is what distinguishes this call inside its test. `files` are paths the twin WRITES (a `$GITHUB_OUTPUT`, a report): recorded after the run, and in compare mode written back from the golden (or removed, when the twin wrote nothing), so the test reads them exactly as
    it did. `extras` maps a name to a zero-argument callable read after the run (a call log, a hash of a written tree); compare mode returns the frozen strings. Each is a record of its own under `<key>|<name>`, so one bash run yields every record and compare mode runs nothing.
    """
    work_t = _work_tuple(work)
    key = case_key(list(parts), work=work_t, label=label)
    names = ["file%d" % i for i in range(len(files))]
    extras = extras or {}
    mode = regolden_mode(twin)
    if mode is None:
        rc, out, err = golden_answer(twin, key, work_t)
        for name, path in zip(names, files, strict=True):
            content = golden_answer(twin, "%s|%s" % (key, name), work_t)[1]
            if content == ABSENT:
                if os.path.lexists(path):
                    os.unlink(path)
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)
        frozen = {n: golden_answer(twin, "%s|%s" % (key, n), work_t)[1] for n in extras}
        return rc, out, err, frozen
    if mode == "bash":
        answer = bash()
    else:
        if port is None:
            raise RuntimeError(
                "%s cannot be re-recorded from the port: this call site passes no `port=`" % key
            )
        answer = port()
    rc, out, err = int(answer[0]), answer[1] or "", answer[2] or ""
    _record(twin, key, (rc, out, err), work_t)
    for name, path in zip(names, files, strict=True):
        try:
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        except FileNotFoundError:
            content = ABSENT
        _record(twin, "%s|%s" % (key, name), (0, content, ""), work_t)
    live = {}
    for name, fn in extras.items():
        live[name] = fn()
        _record(twin, "%s|%s" % (key, name), (0, live[name], ""), work_t)
    return rc, out, err, live


def twin_call(
    twin: str, parts: list[str], bash, *, port=None, work=(), label: str | None = None
) -> Answer:
    """`twin_run` for the common case: `(rc, out, err)` and nothing else."""
    rc, out, err, _ = twin_run(twin, parts, bash, port=port, work=work, label=label)
    return rc, out, err


def twin_streams(
    twin: str,
    script: str,
    *,
    port=None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    tty: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    work=(),
    label: str | None = None,
) -> Answer:
    """What `bash_streams(script, ...)` answered for the twin, from the golden.

    `twin` is the bash file's repo-relative path; `script` is the exact command the differential used to run it (it is part of the key). `work` lists the scratch roots this case built (a `tmp_path`, a fixture clone) so paths under them fold to stable tokens. `port`, a zero-argument callable returning the port's `(rc, out, err)` for the same case, is only needed to re-record
    from the port after the twin is deleted.
    """
    work_t = _work_tuple(work)
    key = twin_key(script, env=env, cwd=cwd, tty=tty, work=work_t, label=label)
    mode = regolden_mode(twin)
    if mode is None:
        return golden_answer(twin, key, work_t)
    if mode == "bash":
        answer = bash_streams(script, env=env, cwd=cwd, tty=tty, timeout=timeout)
    else:
        if port is None:
            raise RuntimeError(
                "%s cannot be re-recorded from the port: this call site passes no `port=`" % key
            )
        answer = port()
    _record(twin, key, answer, work_t)
    return answer


def blob_sha(path: str) -> str:
    """`git hash-object` of the file as recorded: the sha `git cat-file -p` answers once it is committed, and the one a reader of a deleted twin needs."""
    proc = subprocess.run(
        ["git", "hash-object", "--", path],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo(),
    )
    return proc.stdout.strip()


def write_recorded(
    source: str, reason: str, only: set[str] | None = None, keep_unseen: bool = False
) -> list[str]:
    """Flush `RECORDED` into the goldens. Returns one summary line per stem.

    Merged through the hooks' `diff_and_mark`, so a first freeze writes no markers, an unchanged re-record is a byte-identical no-op, and a moved value carries `intentional: <reason>`. A key the old golden had and this run never asked for is DROPPED and counted: the run covers every module naming the twin, so an unasked key is a case that no longer exists.
    """
    lines = []
    for stem in sorted(RECORDED):
        if only is not None and stem not in only:
            continue
        twin = RECORDED_TWINS[stem]
        path = golden_file(twin)
        old_header, old_silent, old_records = goldenio.read_golden(path)
        answers = {k: (str(v[0]), v[1], v[2]) for k, v in RECORDED[stem].items()}
        silent, records, changed = goldenio.diff_and_mark(answers, old_silent, old_records, reason)
        dropped = (set(old_silent) | set(old_records)) - set(answers)
        if keep_unseen:
            # A selective re-record (`regolden.py -k`): the cases this run did not ask about keep exactly the record they had, marker and all.
            silent |= dropped & set(old_silent)
            records.update({k: old_records[k] for k in dropped if k in old_records})
            dropped = set()
        if source == "bash":
            blob = blob_sha(twin)
        else:
            blob = (old_header or {}).get("twin_blob", "")
            if not blob:
                raise RuntimeError("%s: no twin_blob to carry over; freeze from bash first" % stem)
        header = {
            "bash_version": goldenio.bash_version_line()
            if source == "bash"
            else (old_header or {}).get("bash_version", ""),
            "case_count": len(silent) + len(records),
            "source": source,
            "twin": twin,
            "twin_blob": blob,
        }
        goldenio.write_golden(path, header, silent, records)
        lines.append(
            "%s: %d case(s), %d silent -> %s (%d changed, %d dropped)"
            % (
                stem,
                len(silent) + len(records),
                len(silent),
                os.path.relpath(path, repo()),
                len(changed),
                len(dropped),
            )
        )
    return lines
