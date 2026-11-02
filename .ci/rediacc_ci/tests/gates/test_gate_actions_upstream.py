"""`scripts/gates/check-actions.ts` fails closed when upstream does not answer (operator ruling 2026-10-14, "Extend to all seven").

The gate reads the real `.github` tree for its action pins, and `ACTIONS_API_BASE` points its `GET /repos/<owner>/<repo>/releases/latest` requests at a stub HTTP server on 127.0.0.1 (`upstream_stub.py`), so the request, the status handling and the shared retry in `scripts/lib/upstream.ts` are the gate's real code path. The stub's DEFAULT answer serves every action an old release (`v0.0.1`, 2020), so every pin compares as current and the
green control does not depend on how many actions the tree pins.

Proved, control first: every action answered is green, prints the count, and the token never reaches the stub; a port nothing listens on is RED after three attempts with the reachability sentence; ONE rate-limited action is RED (until 2026-10-14 it passed as "1 unknown"); a 503 that persists is RED; a 503 followed by an answer is green inside the budget; a 404 (no published release) is RED as an unusable answer and not as an outage.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness
from rediacc_ci.tests.gates.upstream_stub import (
    RATE_LIMITED,
    assert_no_token,
    closed_port,
    ok,
    sentinel,
    status,
    stub_upstream,
)

VALIDATOR = paths.from_root("scripts", "gates", "check-actions.ts")
CHECKOUT = "/repos/actions/checkout/releases/latest"
OLD_RELEASE = {
    "tag_name": "v0.0.1",
    "html_url": "https://github.invalid/r",
    "target_commitish": "main",
    "published_at": "2020-01-01T00:00:00Z",
}


def run_gate(gate, base: str):
    if not VALIDATOR.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(VALIDATOR))
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run(
        [npx, "tsx", str(VALIDATOR)],
        cwd=paths.repo_root(),
        env={"ACTIONS_API_BASE": base, "GITHUB_TOKEN": sentinel()},
    )


def test_control_every_action_answered_is_green(gate):
    with stub_upstream({}, default=[ok(OLD_RELEASE)]) as stub:
        result = run_gate(gate, stub.base)
        gate.assert_exit(0, result, "every action answered with an older release passes")
        gate.assert_contains(result.out, "compared with upstream, 0 held", "the count is printed")
        gate.assert_eq(stub.asked(CHECKOUT), 1, "actions/checkout is asked once")
        gate.assert_eq(stub.tokens_seen(), 0, "the token is not sent to a seam")
    gate.log_pass("the stub upstream, answering, is green")


def test_an_unreachable_upstream_is_red(gate):
    port = closed_port()
    result = run_gate(gate, "http://127.0.0.1:%d" % port)
    gate.assert_exit(1, result, "an upstream nothing answers on fails closed")
    gate.assert_contains(result.err, "action pin(s) were NOT compared with upstream", "named")
    gate.assert_contains(
        result.err,
        "GET 127.0.0.1:%d%s -> network error ECONNREFUSED, after 3 attempt(s)" % (port, CHECKOUT),
        "the finding names the host and path, the error code and the attempts",
    )
    gate.assert_contains(
        result.err,
        "UPSTREAM REACHABILITY FAILURE (127.0.0.1:%d)" % port,
        "the finding says what kind of red this is",
    )
    gate.assert_contains(result.err, "attempt 2 of 3 failed", "the retries are visible")
    gate.assert_not_contains(result.out, "All GitHub Actions are up-to-date", "no green line")
    assert_no_token(gate, result)
    gate.log_pass("an unreachable upstream is red after three attempts")


def test_one_rate_limited_action_is_red_not_unknown(gate):
    """THE HOLE THE RULING CLOSES: one action unanswered beside fourteen answered used to print `(1 unknown)` and exit 0."""
    with stub_upstream({CHECKOUT: [RATE_LIMITED]}, default=[ok(OLD_RELEASE)]) as stub:
        result = run_gate(gate, stub.base)
        gate.assert_eq(stub.asked(CHECKOUT), 1, "a primary rate limit is not asked again")
    gate.assert_exit(1, result, "a partial lookup failure fails closed")
    gate.assert_contains(result.err, "1 action pin(s) were NOT compared", "exactly one is named")
    gate.assert_contains(result.err, "actions/checkout (pinned v", "the pin is named")
    gate.assert_contains(result.err, "HTTP 403 (rate limit", "the status is named")
    gate.assert_not_contains(result.out, "unknown", "nothing is folded into unknown")
    gate.log_pass("one unanswered action is red")


def test_a_persistent_503_is_red_and_a_cleared_one_is_green(gate):
    with stub_upstream({CHECKOUT: [status(503)]}, default=[ok(OLD_RELEASE)]) as stub:
        red = run_gate(gate, stub.base)
        gate.assert_eq(stub.asked(CHECKOUT), 3, "a 5xx is asked three times")
    gate.assert_exit(1, red, "a 503 that persists fails closed")
    gate.assert_contains(red.err, "-> HTTP 503, after 3 attempt(s)", "the status and attempts")
    with stub_upstream(
        {CHECKOUT: [status(503), ok(OLD_RELEASE)]}, default=[ok(OLD_RELEASE)]
    ) as stub:
        green = run_gate(gate, stub.base)
        gate.assert_eq(stub.asked(CHECKOUT), 2, "the second attempt answered")
    gate.assert_exit(0, green, "a 503 that clears inside the budget passes")
    gate.assert_contains(green.err, "attempt 1 of 3 failed (HTTP 503)", "the retry is visible")
    gate.log_pass("the retry budget holds in both directions")


def test_no_published_release_is_red_as_an_unusable_answer(gate):
    with stub_upstream({CHECKOUT: [status(404)]}, default=[ok(OLD_RELEASE)]) as stub:
        result = run_gate(gate, stub.base)
    gate.assert_exit(1, result, "an action with no release cannot be compared, so it is red")
    gate.assert_contains(
        result.err, "actions/checkout: publishes no GitHub release", "the finding names why"
    )
    gate.assert_not_contains(result.err, "UPSTREAM REACHABILITY FAILURE", "a 404 is an answer")
    gate.log_pass("a 404 is an unusable answer, not an outage")
