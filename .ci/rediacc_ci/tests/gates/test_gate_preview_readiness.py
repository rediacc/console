"""Port of `.ci/scripts/test/gates/test-preview-readiness.sh`.

Unit test for `.ci/scripts/deploy/wait-for-preview-worker.sh`.

WHAT THIS GUARDS. The preview readiness probe gates smoke-test-preview.ts. If it
reports "ready" while the worker is still flapping, the smoke test gets a cold
worker and the PR goes red for a reason that has nothing to do with the PR. That
happened in runs 30968082228 and 30995469629: the probe logged ready at
10:26:41.557 and the smoke test got HTTP 500 from the very same server-info URL 1.3
seconds later.

WHY THE STREAK IS THE FIX AND NOT THE ENDPOINT. Two earlier commits already tried
changing WHICH endpoint is probed -- 8b7840ed4 added the server-info probe,
cefa43ca7 corrected the body it greps for -- and the failure returned both times,
because a SINGLE success cannot distinguish "up" from "flapping". The deployment
flaps by construction: deploy-www.sh deletes and recreates the per-PR D1 database on
every push, and server-info touches D1 while /health does not.

The load-bearing case is `test_streak_is_load_bearing`: it re-runs the flapping
case with `REQUIRED_STREAK=1`, the pre-fix behaviour, and demands that it PASSES.
Without that, the flapping case failing would prove nothing about why -- it could
be the stub, the URL, or the budget.

THE STUB IS A PYTHON `http.server` RATHER THAN THE TWIN'S NODE SCRIPT, and it runs
IN THIS PROCESS on a thread. Two things follow, both improvements on the twin. The
twin backgrounds `node stub.cjs`, polls for a port file for up to five seconds, and
`kill`s the pid on the way out; a case that raised before `stop_stub` leaked the
process, and its ONE shared `$STUB_PID` meant a leak from one case was inherited by
the next. Here the server's lifetime is a context manager, so a raising body still
tears it down, and the port is read off the socket rather than off a file that has
to be waited for. The RESPONSE BEHAVIOUR -- /health always fine, server-info
steady/flap/late -- is unchanged, including the `n %% 3 == 1` flap cadence that is
what keeps the streak from reaching 2.
"""

import contextlib
import http.server
import json
import os
import threading

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-preview-readiness.sh"

WAIT_SCRIPT = paths.from_root(".ci", "scripts", "deploy", "wait-for-preview-worker.sh")

GOOD_BODY = json.dumps({"e2e": {"keys": [{"keyId": "v1", "publicKeySpki": "AAAA"}]}}).encode()


class _Handler(http.server.BaseHTTPRequestHandler):
    mode = "steady"
    count = 0

    def do_GET(self):
        # `do_GET` is BaseHTTPRequestHandler's required spelling, not a style choice.
        if self.path.endswith("/health"):
            self._send(200, b'{"status":"ok"}')
            return
        if self.path.endswith("/server-info"):
            type(self).count += 1
            n = type(self).count
            # flap: good on 1 of every 3 probes, so the streak never reaches 2. late: cold for the first 3 probes, then steady.
            if self.mode == "steady":
                good = True
            elif self.mode == "flap":
                good = n % 3 == 1
            else:
                good = n > 3
            self._send(200, GOOD_BODY) if good else self._send(500, b'{"error":"cold"}')
            return
        self._send(404, b"")

    def _send(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, *_args) -> None:
        """Silence. The stub's access log is not part of any assertion, and on
        stderr it would interleave with the subject's own diagnostics."""


@contextlib.contextmanager
def stub(mode: str):
    """A preview worker on 127.0.0.1, torn down even when the body raises."""
    handler = type("Handler", (_Handler,), {"mode": mode, "count": 0})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_wait(gate, env: dict[str, str], *, drop: tuple[str, ...] = ()) -> harness.RunResult:
    if not WAIT_SCRIPT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(WAIT_SCRIPT))
    bash = harness.require_tool("bash", "install bash; the subject IS a bash script")
    merged = {k: v for k, v in os.environ.items() if k not in drop}
    merged.update(env)
    return harness.run([bash, str(WAIT_SCRIPT)], env=merged, env_replace=True, timeout=120)


def probe(gate, mode: str, extra: dict[str, str] | None = None) -> harness.RunResult:
    with stub(mode) as url:
        env = {
            "PREVIEW_URL_OVERRIDE": url,
            "MAX_ATTEMPTS": "9",
            "PROBE_INTERVAL_SECONDS": "0.1",
        }
        env.update(extra or {})
        return run_wait(gate, env)


def test_steady_worker_is_ready(gate):
    result = probe(gate, "steady")
    gate.assert_eq(result.rc, 0, "a steady worker is reported ready")
    gate.assert_contains(
        result.combined, "consecutive probes", "success names the streak it required"
    )
    gate.log_pass("a steady worker passes")


def test_flapping_worker_is_not_ready(gate):
    result = probe(gate, "flap")
    gate.assert_eq(result.rc, 1, "a flapping worker is NOT reported ready")
    gate.assert_contains(
        result.combined, "streak reset", "the flap is reported as a reset, not as a plain wait"
    )
    gate.log_pass("a flapping worker is rejected")


def test_streak_is_load_bearing(gate):
    """ANTI-VACUITY. Same stub, same URL, same budget -- only REQUIRED_STREAK drops
    to 1, which is exactly what this script did before the fix. If this does NOT
    pass, the flapping case above is failing for some other reason and proves
    nothing about the streak.
    """
    result = probe(gate, "flap", {"REQUIRED_STREAK": "1"})
    gate.assert_eq(
        result.rc, 0, "with REQUIRED_STREAK=1 the same flapping worker passes (the old bug)"
    )
    gate.log_pass("the streak is what rejects the flap, not the stub or the budget")


def test_slow_worker_still_becomes_ready(gate):
    """The streak must not turn a merely COLD worker into a failure: this one is down
    for 3 probes and then healthy, which must still end in success.
    """
    result = probe(gate, "late")
    gate.assert_eq(result.rc, 0, "a cold-then-healthy worker still passes")
    gate.log_pass("a slow start is not mistaken for a flap")


def test_override_does_not_need_a_pr_number(gate):
    """PREVIEW_URL_OVERRIDE exists so this script is testable without being copied
    through sed. It has to work with PR_NUMBER unset, or the tests above are quietly
    exercising a different code path than CI does.
    """
    with stub("steady") as url:
        result = run_wait(
            gate,
            {
                "PREVIEW_URL_OVERRIDE": url,
                "MAX_ATTEMPTS": "9",
                "PROBE_INTERVAL_SECONDS": "0.1",
            },
            drop=("PR_NUMBER",),
        )
    gate.assert_eq(result.rc, 0, "the override works with PR_NUMBER unset")
    gate.log_pass("the override needs no PR_NUMBER")


def test_pr_number_still_required_without_override(gate):
    result = run_wait(gate, {}, drop=("PR_NUMBER", "PREVIEW_URL_OVERRIDE"))
    gate.assert_eq(result.rc, 1, "PR_NUMBER is still mandatory when no override is given")
    gate.assert_contains(result.combined, "PR_NUMBER", "the failure names the missing variable")
    gate.log_pass("the override did not make PR_NUMBER optional in CI")


def test_ci_defaults_are_still_strict(gate):
    """The knobs are test-only. If someone weakens the DEFAULTS, CI silently goes
    back to sampling one probe, and every test above would still pass because they
    all set their own values.
    """
    if not WAIT_SCRIPT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(WAIT_SCRIPT))
    src = WAIT_SCRIPT.read_text(encoding="utf-8")
    gate.assert_contains(
        src, 'REQUIRED_STREAK="${REQUIRED_STREAK:-3}"', "the default streak is still 3"
    )
    gate.assert_contains(
        src, 'MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"', "the default budget is still 60"
    )
    gate.assert_contains(
        src,
        'PROBE_INTERVAL_SECONDS="${PROBE_INTERVAL_SECONDS:-2}"',
        "the default spacing is still 2s",
    )
    gate.log_pass("CI defaults are unchanged")
