"""wl_gh: the Stop hook's one `gh` layer (agent/plans/PLAN-ci-consolidation.md, Part C).

WHY ONE LAYER. Before this module the hook spawned `gh` in three places with three contracts: `wl_ci._gh_json` returned `(data, error)`, `wl_prreview.run_gh` returned `(rc, out, err)` with a 120 s timeout, and `wl_checks.prreview_runner` rebuilt the same spawn under a budget. Each grew its own arms, and `wl_ci`'s spawn never closed stdin, so a `gh` that prompted (an expired token, a first-run
consent) would have blocked a Stop hook on input nobody can give. Every hook read now comes through here, and `.claude/rediacc_hooks/tests/test_wl_gh.py` refuses a `gh` spawn anywhere else under `.claude/hooks/stop`.

THE TWO CALLS.
- `call(argv, ...)` is the READ. It returns `(data, error)` and never raises: spawn failure, timeout, non-zero exit, non-JSON output and a GraphQL `errors` array delivered with exit 0 each come back as `(None, why)`. A TRANSIENT fault (a 5xx or a connection reset, `rediacc_ci.core.gh_retry.is_transient`) is retried within GH_READ_ATTEMPTS and one GH_READ_PAUSE_S pause, the bound PLAN-gh-retry G13 set for
  the hook budget, never gh_retry's 5 s then 15 s default. A 4xx, a timeout and every other failure come back at once. `call_list` is the `--paginate --slurp` flatten over the same read.
- `write(argv, ...)` is ONE attempt, never retried: a retried POST after a lost response is a second comment.

THE `run=` SEAM. Both calls take an optional `run(argv) -> (rc, stdout, stderr)` that replaces the spawn, so wl_prreview's injected fake and wl_checks' budgeted runner keep working, and the retry, the JSON arms and the error text stay in one place.

THE RETRY POLICY IS IMPORTED, NOT COPIED. `rediacc_ci.core.gh_retry` is loaded on first use through `.claude/rediacc_hooks/syspath.py` (`import_from_ci`, `.ci` on sys.path only while importing), anchored on THIS file, because the policy is a code dependency like an import. A tree where it cannot be imported makes every read answer `(None, "... could not be imported ...")`: blindness said out loud, never a silent one-shot read.

THE CACHE HELPERS. `cache_read(path, ttl, error_ttl, now)` serves a JSON sidecar while it is fresh: an entry whose `error` is set expires after `error_ttl`, any other after `ttl`, both measured from its `at`. `cache_write(path, doc)` is atomic (mkstemp beside the target, then `os.replace`), so a reader in a second session never sees half a document and a failed write leaves no tmp file behind.

SEALED. `.ci/policy/worklist-env-registry.json` lists this file under `sealed_modules`: it reads no environment variable, and GH_READ_ATTEMPTS, GH_READ_PAUSE_S and DEFAULT_TIMEOUT_S are pinned literals. A knob that stretched the retry or the timeout would spend the Stop hook's budget from outside the code.
"""

from __future__ import annotations

import contextlib
import functools
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import time
from collections.abc import Callable
from typing import Any

Runner = Callable[[list[str]], tuple[int, str, str]]

# The hook's bound on one READ (PLAN-gh-retry G13): two attempts and one 2 s pause, so a 5xx costs a stop two seconds. Read at call time, so a test can zero the pause.
GH_READ_ATTEMPTS = 2
GH_READ_PAUSE_S = 2
# Per spawn. The worst READ is therefore 2 * DEFAULT_TIMEOUT_S + GH_READ_PAUSE_S, and only when the first attempt failed transiently rather than timing out (a timeout is not retried).
DEFAULT_TIMEOUT_S = 25
# rc for a spawn that timed out (the coreutils `timeout` convention) and for one that could not run at all (command not found).
RC_TIMEOUT = 124
RC_SPAWN = 127
# rc for a `write` whose argv is not a write: refused before anything is spawned.
RC_REFUSED = 125
ERROR_CHARS = 240


@functools.cache
def import_ci(module: str) -> Any:
    """`module` (a `rediacc_ci.*` name), imported once through the shared scoped loader `rediacc_hooks.syspath.import_from_ci`. The hop file is loaded BY FILE because this module lives outside the `rediacc_hooks` package. Raises ImportError, which every caller here reports as blindness or a refusal."""
    hop = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("_rediacc_syspath", hop)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % hop)
    syspath = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(syspath)
    return syspath.import_from_ci(module)


def gh_retry_module() -> Any:
    """`rediacc_ci.core.gh_retry`, the one transient-retry policy."""
    return import_ci("rediacc_ci.core.gh_retry")


def spawn(
    argv: list[str], *, cwd: Any = None, timeout: float = DEFAULT_TIMEOUT_S
) -> tuple[int, str, str]:
    """(rc, stdout, stderr) of ONE `gh <argv>`. Never raises: a timeout is rc 124 and a spawn failure rc 127, each with the reason on stderr. stdin is closed, so a `gh` that prompts fails instead of waiting for input a hook cannot give."""
    try:
        done = subprocess.run(
            ["gh", *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
            cwd=None if cwd is None else str(cwd),
        )
    except subprocess.TimeoutExpired:
        return RC_TIMEOUT, "", "gh timed out after %ss" % timeout
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return RC_SPAWN, "", "gh could not run: %s" % exc
    return done.returncode, done.stdout or "", done.stderr or ""


def runner(
    cwd: Any = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    budget_s: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Runner:
    """The one raw runner: each call is ONE `spawn` bound to `cwd` and `timeout`, never retried, because it is what `call` hands to retry_transient as a single attempt and what `write` runs once. With `budget_s` it is also bounded in total, for a caller that makes several reads inside one stop (wl_checks' review read): once the budget is spent, or within a second of it, every further call answers rc 124 at once without spawning."""
    deadline = None if budget_s is None else clock() + budget_s

    def one_attempt(argv: list[str]) -> tuple[int, str, str]:
        limit = timeout
        if deadline is not None:
            left = deadline - clock()
            if left <= 1:
                return (
                    RC_TIMEOUT,
                    "",
                    "the Stop hook's %ds gh budget for this read is spent" % (budget_s or 0),
                )
            limit = min(timeout, left)
        return spawn(argv, cwd=cwd, timeout=limit)

    return one_attempt


def _attempt(once: Runner, argv: list[str]) -> tuple[int, str, str]:
    """One runner call that cannot raise into the hook: an injected runner that throws reads as a spawn failure."""
    try:
        rc, out, err = once(list(argv))
    except Exception as exc:  # noqa: BLE001 -- the contract is "never raises"; the reason is kept
        return RC_SPAWN, "", "gh runner raised %s: %s" % (type(exc).__name__, exc)
    return rc, out or "", err or ""


def _why(argv: list[str], rc: int, out: str, err: str) -> str:
    text = (err or out or "").strip() or "no output"
    return "`gh %s` exited %d: %s" % (" ".join(argv[:2]), rc, text[-ERROR_CHARS:])


def read_raw(
    argv: list[str],
    *,
    cwd: Any = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    run: Runner | None = None,
    sleep: Callable[[float], None] | None = None,
) -> tuple[str | None, str]:
    """(stdout, "") of the READ `gh <argv>`, or (None, why not): `call` without the JSON parse. The transient retry lives here."""
    try:
        retry = gh_retry_module()
    except (ImportError, OSError) as exc:
        return None, "rediacc_ci.core.gh_retry could not be imported: %s" % str(exc)[:160]
    once = run or runner(cwd, timeout)
    nap = sleep or time.sleep
    rc, out, err = retry.retry_transient(
        lambda: _attempt(once, argv),
        lambda r: None if r[0] == 0 else (r[2] or r[1] or "failed"),
        attempts=GH_READ_ATTEMPTS,
        sleep=lambda _scheduled: nap(GH_READ_PAUSE_S),
    )
    if rc != 0:
        return None, _why(argv, rc, out, err)
    return out, ""


def call(
    argv: list[str],
    *,
    cwd: Any = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    run: Runner | None = None,
    sleep: Callable[[float], None] | None = None,
) -> tuple[Any, str]:
    """(data, "") from the READ `gh <argv>` parsed as JSON, or (None, why not). Never raises."""
    raw, err = read_raw(argv, cwd=cwd, timeout=timeout, run=run, sleep=sleep)
    if raw is None:
        return None, err
    try:
        data = json.loads(raw)
    except ValueError:
        return None, "non-JSON from `gh %s`: %r" % (" ".join(argv[:2]), raw[:80])
    # GraphQL reports field errors with exit 0 and an `errors` array; a partial answer that still carries its repository is kept.
    if (
        isinstance(data, dict)
        and data.get("errors")
        and not (data.get("data") or {}).get("repository")
    ):
        return None, "graphql errors from `gh %s`: %s" % (
            " ".join(argv[:2]),
            json.dumps(data["errors"])[:ERROR_CHARS],
        )
    return data, ""


def call_list(
    argv: list[str],
    *,
    cwd: Any = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    run: Runner | None = None,
    sleep: Callable[[float], None] | None = None,
) -> tuple[list[dict] | None, str]:
    """(rows, "") of every page of a REST list (`argv` plus `--paginate --slurp`, which wraps each page in an outer array), flattened; or (None, why not). Never raises."""
    pages, err = call(
        [*argv, "--paginate", "--slurp"], cwd=cwd, timeout=timeout, run=run, sleep=sleep
    )
    if pages is None:
        return None, err
    if not isinstance(pages, list):
        return None, "expected a list of pages from `gh %s`" % " ".join(argv[:2])
    out: list[dict] = []
    for page in pages:
        if isinstance(page, list):
            out.extend(row for row in page if isinstance(row, dict))
        elif isinstance(page, dict):
            out.append(page)
    return out, ""


def write_refusal(argv: list[str]) -> str:
    """The empty string when `gh <argv>` is a WRITE by check:ci-gh-retry-reads' own classifier (`rediacc_ci.quality.gh_retry_reads.classify`, imported, not copied), else why `write` refuses it. Fails closed: a classifier that cannot be imported refuses."""
    try:
        # The classifier reads a whole argv, binary first. Built by insert rather than as a `["gh", ...]` literal, because it is data handed to a pure function, not a spawn.
        tokens = list(argv)
        tokens.insert(0, "gh")
        kind, verb = import_ci("rediacc_ci.quality.gh_retry_reads").classify(tokens)
    except Exception as exc:  # noqa: BLE001 -- an unknowable verdict refuses, it never admits
        return "the write classifier could not be loaded (%s: %s)" % (type(exc).__name__, exc)
    if kind != "write":
        return (
            "`gh %s` is a %s (%s), not a write; a read goes through wl_gh.call, which retries a "
            "transient fault" % (" ".join(argv[:2]), kind, verb)
        )
    return ""


def write(
    argv: list[str],
    *,
    cwd: Any = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    run: Runner | None = None,
) -> tuple[int, str, str]:
    """(rc, stdout, stderr) of the WRITE `gh <argv>`: ONE attempt, never retried, because a retried POST after a lost response posts twice. An argv that is not a write is refused with RC_REFUSED and nothing is spawned, so this one-shot door cannot carry a read. Never raises."""
    refused = write_refusal(argv)
    if refused:
        return RC_REFUSED, "", "wl_gh.write refused: %s" % refused
    once = run or runner(cwd, timeout)
    try:
        rc, out, err = once(list(argv))
    except Exception as exc:  # noqa: BLE001 -- the contract is "never raises"; the reason is kept
        return RC_SPAWN, "", "gh runner raised %s: %s" % (type(exc).__name__, exc)
    return rc, out or "", err or ""


# ---- the cache helpers ----


def load_json(path: Any) -> Any:
    """The JSON value at `path`, or None when it is absent, unreadable or corrupt."""
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def cache_load(path: Any) -> dict | None:
    """The JSON object at `path`, or None when it is absent, unreadable, corrupt or not an object. No freshness judgement."""
    doc = load_json(path)
    return doc if isinstance(doc, dict) else None


def cache_fresh(doc: dict | None, ttl: float, error_ttl: float, now: float | None = None) -> bool:
    """Whether `doc` is inside its TTL: `error_ttl` when it carries a non-empty `error`, `ttl` otherwise, measured from `at`."""
    if not isinstance(doc, dict):
        return False
    now = time.time() if now is None else now
    try:
        age = now - float(doc.get("at") or 0)
    except (TypeError, ValueError):
        return False
    return age <= (error_ttl if doc.get("error") else ttl)


def cache_read(path: Any, ttl: float, error_ttl: float, now: float | None = None) -> dict | None:
    """The cached document at `path` while it is fresh (`cache_fresh`), else None."""
    doc = cache_load(path)
    return doc if cache_fresh(doc, ttl, error_ttl, now) else None


def cache_write(path: Any, doc: Any) -> bool:
    """Write `doc` as JSON to `path` atomically: a tmp file beside it, then `os.replace`. False when it could not be written, and no tmp file is left either way."""
    path = pathlib.Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    except OSError:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError):
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        return False
    return True
