"""Asking an upstream, for the Python external gate (`rediacc_ci.quality.go_deps`).

THE RULE IS `scripts/lib/upstream.ts`'s, carried here for the one gate that is not TypeScript (operator rulings 2026-10-13, "Everything fails closed, nightly included", and 2026-10-14, "Extend to all seven"). A thing whose upstream answer was not obtained was NOT compared, and that is a red finding, never a note beside a green and never a warning on the nightly.

THE RETRY BUDGET, the same four numbers as the TypeScript: up to MAX_ATTEMPTS (3) tries, HTTP_TIMEOUT_S (15 s) each, BACKOFF_S (2 s, then 4 s) between them, for a failure that can clear in seconds (a network error, a timeout, 408, 429, a 5xx). Every other status is answered at once. `.ci/rediacc_ci/tests/test_core_upstream.py` reads both files and fails when the numbers disagree, so the two copies cannot drift.

THE WORDING IS THE TYPESCRIPT'S TOO. The retry note (`? <who>: attempt 1 of 3 failed (<what>), asking again in 2 s`) is what `ci_diagnose.py`'s RETRY_NOTE_RE skips, and `report_unreachable` prints "were NOT compared with upstream" and "UPSTREAM REACHABILITY FAILURE", which its `upstream-unreachable` signature reads, so a nightly red from this gate is triaged as the outage it is.

A FINDING NAMES the method, the host and path asked (no query, no header), the status or the error's own code (never the error's message, which can carry a URL), and the number of attempts.
"""

import http.client
import json
import socket
import ssl
import sys
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass

HTTP_TIMEOUT_S = 15
MAX_ATTEMPTS = 3
BACKOFF_S = (2, 4)


class NotComparedError(Exception):
    """The upstream's answer was not obtained, so the thing it was asked about was not compared: red."""

    def __init__(
        self, what: str, host: str, asked: str, attempts: int, status: int | None = None
    ) -> None:
        self.what = what
        self.host = host
        self.asked = asked
        self.attempts = attempts
        self.status = status
        super().__init__("%s -> %s, after %d attempt(s)" % (asked, what, attempts))


@dataclass(frozen=True)
class Failure:
    """One failed attempt: what answered, and whether asking again within the budget can help."""

    what: str
    retry: bool
    status: int | None = None


@dataclass(frozen=True)
class Answer[T]:
    """One successful attempt. Generic in what `once` produced, so `retry` hands back that type rather than `object` and no caller has to cast its own answer back."""

    value: T


# The gate's sleep, swapped by a selftest so a control that drives the retry does not wait for real.
SLEEP_SEAM: dict[str, Callable[[float], None]] = {"sleep": time.sleep}


def retry[T](asked: str, host: str, who: str, once: Callable[[], Answer[T] | Failure]) -> T:
    """Call `once` up to MAX_ATTEMPTS times. Returns the answer's value; raises NotComparedError when the budget is spent or the failure is not worth asking again."""
    tries = 0
    while True:
        tries += 1
        outcome = once()
        if isinstance(outcome, Answer):
            return outcome.value
        if tries >= MAX_ATTEMPTS or not outcome.retry:
            raise NotComparedError(outcome.what, host, asked, tries, outcome.status)
        wait = BACKOFF_S[tries - 1] if tries - 1 < len(BACKOFF_S) else 0
        # Progress, so stderr: a caller printing JSON on stdout must stay parseable.
        print(
            "? %s: attempt %d of %d failed (%s), asking again in %d s"
            % (who, tries, MAX_ATTEMPTS, outcome.what, wait),
            file=sys.stderr,
            flush=True,
        )
        SLEEP_SEAM["sleep"](wait)


def _classify_error(exc: BaseException) -> Failure:
    """What a request that produced no response means. The error's own code, never its message."""
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return Failure("timeout after %d s" % HTTP_TIMEOUT_S, True)
    if isinstance(exc, socket.gaierror):
        return Failure("network error ENOTFOUND", True)
    if isinstance(exc, ConnectionRefusedError):
        return Failure("network error ECONNREFUSED", True)
    if isinstance(exc, ConnectionResetError):
        return Failure("network error ECONNRESET", True)
    return Failure("network error %s" % type(exc).__name__, True)


def _connection(parts: urllib.parse.SplitResult) -> http.client.HTTPConnection:
    """https for a real upstream; plain http only for a test seam's stub."""
    if parts.scheme == "https":
        return http.client.HTTPSConnection(
            parts.netloc, timeout=HTTP_TIMEOUT_S, context=ssl.create_default_context()
        )
    return http.client.HTTPConnection(parts.netloc, timeout=HTTP_TIMEOUT_S)


def ask_json(url: str, who: str, body: object | None = None) -> object:
    """POST `body` as JSON (or GET when it is None) and return the parsed answer. Raises NotComparedError when no usable response arrived, ValueError when one arrived and is not JSON."""
    parts = urllib.parse.urlsplit(url)
    method = "GET" if body is None else "POST"
    asked = "%s %s%s" % (method, parts.netloc, parts.path)
    data = None if body is None else json.dumps(body).encode()
    target = parts.path + ("?" + parts.query if parts.query else "")

    def once() -> Answer[bytes] | Failure:
        conn = _connection(parts)
        try:
            conn.request(
                method, target or "/", body=data, headers={"Content-Type": "application/json"}
            )
            response = conn.getresponse()
            raw = response.read()
        except (OSError, http.client.HTTPException) as exc:
            return _classify_error(exc)
        finally:
            conn.close()
        if 200 <= response.status < 300:
            return Answer(raw)
        transient = response.status in (408, 429) or response.status >= 500
        return Failure("HTTP %d" % response.status, transient, response.status)

    raw = retry(asked, parts.netloc, who, once)
    return json.loads(raw)


DEFAULT_HINT = ("  and re-run the failed job when this is a nightly.",)


def report_unreachable(
    subject: str,
    items: list[tuple[str, str, str]],
    not_a: str,
    hint: tuple[str, ...] = DEFAULT_HINT,
) -> None:
    """Print the fail-closed finding, in `scripts/lib/upstream.ts` `reportUnreachable`'s words, on stderr. Each item is (who, host, finding), the finding being `str(NotComparedError)`."""
    if not items:
        return
    hosts = ", ".join(dict.fromkeys(host for _, host, _ in items))
    lines = [
        "",
        "✗ %d %s were NOT compared with upstream:" % (len(items), subject),
        *("  %s: %s" % (who, finding) for who, _, finding in items),
        "  UPSTREAM REACHABILITY FAILURE (%s), not %s and not a defect in the tree."
        % (hosts, not_a),
        "  The comparison did not happen, so this run says nothing about whether these",
        "  are current, and it fails closed instead of passing unchecked. Nothing in the tree",
        "  needs a change for this finding: run the gate again once the host answers",
        *hint,
    ]
    for line in lines:
        print(line, file=sys.stderr)
