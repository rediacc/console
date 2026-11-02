"""`scripts/gates/check-real-provider-pin-freshness.ts`, driven through its three seams so it runs offline:

  REAL_PROVIDER_LOCK_FILE          the lock file whose pins are judged
  REAL_PROVIDER_FRESHNESS_FIXTURE  a JSON map of `owner/repo` to the release list as the GitHub API returns it,
                                   read INSTEAD of the network
  REAL_PROVIDER_API_BASE           another API base, here a stub HTTP server on 127.0.0.1, so the request, the
                                   status handling and the retry are the gate's real code path

The fixture is the upstream listing itself, not a pre-digested "latest version", so the tag-prefix filter, the draft and pre-release filter and the version ordering are all under test.

Proved, control first: a pin equal to upstream's newest release passes; a newer release past the release-age window FIRES and the message carries the pin, the new version, its publish date and the bump command; a newer release inside the window passes with a note; the newest ELIGIBLE release is the finding when a still newer one is inside the window; drafts, pre-releases, beta tags and another component's tags are not releases of this pin; a listing that answers and cannot be used is RED; an unreadable lock file is RED.

FAIL CLOSED (operator ruling 2026-10-13), control first against the stub server: both listings served is green and the token never reaches the stub; a port nothing listens on is RED after three attempts; a 403 rate limit is RED at once; a refused token is RED; a 503 that persists is RED; a 503 followed by the listing is green inside the retry budget. Each finding names the pin, the host and path, and the status or error code, and no finding carries the token.

Every case owns its fixtures under `tmp_path`; the tracked lock file is read by one case and never written.
"""

import datetime
import json
import pathlib

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

VALIDATOR = paths.from_root("scripts", "gates", "check-real-provider-pin-freshness.ts")
REAL_LOCK = paths.from_root("private", "account", "e2e", "real-provider.lock.json")

BITWARDEN = "bitwarden/clients"
VAULTWARDEN = "dani-garcia/vaultwarden"
PIN_BW = "2026.9.3"
PIN_VW = "1.37.4"
LONG_AGO = "2020-01-01T00:00:00Z"


def an_hour_ago() -> str:
    moment = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def release(tag: str, published: str = LONG_AGO, **flags: bool) -> dict:
    return {
        "tag_name": tag,
        "published_at": published,
        "draft": flags.get("draft", False),
        "prerelease": flags.get("prerelease", False),
    }


def current_listing() -> dict:
    """Both upstreams with the pinned version as their newest stable release, beside the noise a real listing holds."""
    return {
        BITWARDEN: [
            release("web-v9999.1.0"),
            release("cli-v9999.1.0"),
            release(f"browser-v{PIN_BW}"),
            release("browser-v2026.9.2"),
        ],
        VAULTWARDEN: [release(PIN_VW), release("1.37.3")],
    }


def write_lock(directory: pathlib.Path, **overrides: object) -> pathlib.Path:
    lock: dict[str, object] = {
        "bitwarden": {"version": PIN_BW, "publishedAt": "2026-10-01T18:08:55Z"},
        "vaultwarden": {"version": PIN_VW, "publishedAt": "2026-10-05T23:40:54Z"},
    }
    lock.update(overrides)
    path = directory / "real-provider.lock.json"
    path.write_text(json.dumps(lock), encoding="utf-8")
    return path


def run_gate(gate, directory: pathlib.Path, listing: object, lock: pathlib.Path | None = None):
    """The gate against a stubbed upstream listing. The fixture is always written here, because a fixture variable naming no file would send the gate to the network."""
    if not VALIDATOR.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(VALIDATOR))
    fixture = directory / "listing.json"
    fixture.write_text(json.dumps(listing), encoding="utf-8")
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run(
        [npx, "tsx", str(VALIDATOR)],
        cwd=paths.repo_root(),
        env={
            "REAL_PROVIDER_FRESHNESS_FIXTURE": str(fixture),
            "REAL_PROVIDER_LOCK_FILE": str(lock or write_lock(directory)),
        },
    )


def route(repo: str) -> str:
    """The path the gate asks the stub for a repository's release list."""
    return "/repos/%s/releases" % repo


def served(**answers: list[tuple]) -> dict[str, list[tuple]]:
    """A stub script from `bitwarden=` and `vaultwarden=` answer lists."""
    repos = {"bitwarden": BITWARDEN, "vaultwarden": VAULTWARDEN}
    return {route(repos[name]): listed for name, listed in answers.items()}


def run_gate_over_http(gate, directory: pathlib.Path, base: str):
    """The gate against `base` over real HTTP: no listing fixture, so the fetch, the status handling and the retry all run."""
    if not VALIDATOR.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(VALIDATOR))
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run(
        [npx, "tsx", str(VALIDATOR)],
        cwd=paths.repo_root(),
        env={
            "REAL_PROVIDER_API_BASE": base,
            "REAL_PROVIDER_FRESHNESS_FIXTURE": "",
            "REAL_PROVIDER_LOCK_FILE": str(write_lock(directory)),
            "GITHUB_TOKEN": sentinel(),
        },
    )


def test_control_both_listings_served_over_http_is_green(gate, tmp_path):
    """The control for every red case below: the same stub, answering, is green, so a red there is the failure and not the stub."""
    listing = current_listing()
    script = served(bitwarden=[ok(listing[BITWARDEN])], vaultwarden=[ok(listing[VAULTWARDEN])])
    with stub_upstream(script) as stub:
        result = run_gate_over_http(gate, tmp_path, stub.base)
        gate.assert_exit(0, result, "two listings served over HTTP pass")
        gate.assert_contains(result.out, "2 of 2 compared with upstream", "the count is printed")
        gate.assert_eq(stub.asked(route(BITWARDEN)), 1, "bitwarden is asked once")
        gate.assert_eq(stub.asked(route(VAULTWARDEN)), 1, "vaultwarden is asked once")
        gate.assert_eq(len(stub.requests), 2, "two requests reached the stub")
        gate.assert_eq(stub.tokens_seen(), 0, "the token is not sent to a seam")
    gate.log_pass("the stub upstream, answering, is green")


def test_a_stale_pin_over_http_still_fires(gate, tmp_path):
    listing = current_listing()
    listing[VAULTWARDEN].insert(0, release("1.38.0"))
    script = served(bitwarden=[ok(listing[BITWARDEN])], vaultwarden=[ok(listing[VAULTWARDEN])])
    with stub_upstream(script) as stub:
        result = run_gate_over_http(gate, tmp_path, stub.base)
    gate.assert_exit(1, result, "a pin behind an aged release fails over HTTP too")
    gate.assert_contains(
        result.err, "fix: npm run pins -- bump real-provider:vaultwarden", "the bump is printed"
    )
    gate.assert_not_contains(result.err, "NOT compared", "a stale pin is not a failed fetch")
    gate.log_pass("the HTTP path judges a listing the way the fixture path does")


def test_an_unreachable_upstream_is_red(gate, tmp_path):
    port = closed_port()
    result = run_gate_over_http(gate, tmp_path, "http://127.0.0.1:%d" % port)
    gate.assert_exit(1, result, "an upstream nothing answers on fails closed")
    gate.assert_contains(result.err, "2 real-provider pin(s) were NOT compared", "both are named")
    gate.assert_contains(
        result.err,
        f"Bitwarden browser extension (pinned {PIN_BW}): GET 127.0.0.1:{port}/repos/{BITWARDEN}/releases -> network error ECONNREFUSED, after 3 attempt(s)",
        "the finding names the pin, the host and path, the error code and the attempts",
    )
    gate.assert_contains(
        result.err, f"Vaultwarden (pinned {PIN_VW})", "the second pin is a finding too"
    )
    gate.assert_contains(result.err, "The comparison did not happen", "the finding says so")
    gate.assert_contains(
        result.err,
        "UPSTREAM REACHABILITY FAILURE (127.0.0.1:%d), not a stale pin" % port,
        "the finding says what kind of red this is and names the host",
    )
    gate.assert_contains(result.err, "attempt 2 of 3 failed", "the retries are visible")
    gate.assert_not_contains(result.out, "Every real-provider pin", "no green line is printed")
    gate.assert_not_contains(result.err, "per_page", "the query string is not printed")
    assert_no_token(gate, result)
    gate.log_pass("an unreachable upstream is red after three attempts")


def test_an_empty_release_list_is_not_compared(gate, tmp_path):
    """The same empty-list case as the devcontainer gate (scripts/lib/upstream.ts emptyReleaseList): reachability, not an unusable listing."""
    listing = current_listing()
    script = served(bitwarden=[ok(listing[BITWARDEN])], vaultwarden=[ok([])])
    with stub_upstream(script) as stub:
        result = run_gate_over_http(gate, tmp_path, stub.base)
    gate.assert_exit(1, result, "an empty release list fails closed")
    gate.assert_contains(
        result.err, "1 real-provider pin(s) were NOT compared", "one not-compared finding"
    )
    gate.assert_contains(
        result.err, "HTTP 200 with an empty release list", "it names the empty answer"
    )
    gate.log_pass("an empty release list is not compared")


def test_a_rate_limit_is_red(gate, tmp_path):
    listing = current_listing()
    script = served(bitwarden=[ok(listing[BITWARDEN])], vaultwarden=[RATE_LIMITED])
    with stub_upstream(script) as stub:
        result = run_gate_over_http(gate, tmp_path, stub.base)
        gate.assert_eq(stub.asked(route(VAULTWARDEN)), 1, "a primary rate limit is not asked again")
    gate.assert_exit(1, result, "a rate limit fails closed")
    gate.assert_contains(
        result.err, "1 real-provider pin(s) were NOT compared", "one pin is the finding"
    )
    gate.assert_contains(
        result.err,
        f"/repos/{VAULTWARDEN}/releases -> HTTP 403 (rate limit, resets 2026-10-",
        "the finding names the path, the status and the reset",
    )
    gate.assert_contains(result.err, "after 1 attempt(s)", "the attempt count is printed")
    gate.assert_contains(
        result.out, "Bitwarden browser extension: %s is the newest" % PIN_BW, "the other is judged"
    )
    assert_no_token(gate, result)
    gate.log_pass("a rate limit is red at once")


def test_a_refused_token_is_red(gate, tmp_path):
    listing = current_listing()
    script = served(bitwarden=[status(401)], vaultwarden=[ok(listing[VAULTWARDEN])])
    with stub_upstream(script) as stub:
        result = run_gate_over_http(gate, tmp_path, stub.base)
        gate.assert_eq(stub.asked(route(BITWARDEN)), 1, "a refused token is not asked again")
    gate.assert_exit(1, result, "an authentication failure fails closed")
    gate.assert_contains(result.err, "HTTP 401 (the token was refused)", "the status is named")
    assert_no_token(gate, result)
    gate.log_pass("a refused token is red")


def test_a_persistent_server_error_is_red(gate, tmp_path):
    listing = current_listing()
    script = served(bitwarden=[ok(listing[BITWARDEN])], vaultwarden=[status(503)])
    with stub_upstream(script) as stub:
        result = run_gate_over_http(gate, tmp_path, stub.base)
        gate.assert_eq(stub.asked(route(VAULTWARDEN)), 3, "a 5xx is asked three times and no more")
    gate.assert_exit(1, result, "a 5xx that outlasts the retry budget fails closed")
    gate.assert_contains(result.err, "-> HTTP 503, after 3 attempt(s)", "status and attempts")
    gate.log_pass("a persistent 5xx is red after the budget")


def test_a_transient_failure_then_success_is_green(gate, tmp_path):
    listing = current_listing()
    script = served(
        bitwarden=[status(503), ok(listing[BITWARDEN])],
        vaultwarden=[(429, {"retry-after": "1"}, {}), ok(listing[VAULTWARDEN])],
    )
    with stub_upstream(script) as stub:
        result = run_gate_over_http(gate, tmp_path, stub.base)
        gate.assert_eq(stub.asked(route(BITWARDEN)), 2, "the 503 is asked again once")
        gate.assert_eq(stub.asked(route(VAULTWARDEN)), 2, "the 429 is asked again once")
    gate.assert_exit(0, result, "a failure that clears inside the retry budget passes")
    gate.assert_contains(result.err, "attempt 1 of 3 failed (HTTP 503)", "the retry is visible")
    gate.assert_contains(result.out, "2 of 2 compared with upstream", "both were compared")
    gate.log_pass("a transient failure followed by the listing is green")


def test_a_wait_longer_than_the_budget_is_not_retried(gate, tmp_path):
    listing = current_listing()
    script = served(
        bitwarden=[ok(listing[BITWARDEN])],
        vaultwarden=[(429, {"retry-after": "3600"}, {}), ok(listing[VAULTWARDEN])],
    )
    with stub_upstream(script) as stub:
        result = run_gate_over_http(gate, tmp_path, stub.base)
        gate.assert_eq(stub.asked(route(VAULTWARDEN)), 1, "an hour's wait is not slept through")
    gate.assert_exit(1, result, "a wait the budget cannot hold fails closed")
    gate.assert_contains(result.err, "HTTP 429 (rate limit), after 1 attempt(s)", "named")
    gate.log_pass("a Retry-After beyond the budget is red at once")


def test_a_response_that_is_not_json_is_red(gate, tmp_path):
    listing = current_listing()
    script = served(
        bitwarden=[(200, {}, b"<html>proxy</html>")], vaultwarden=[ok(listing[VAULTWARDEN])]
    )
    with stub_upstream(script) as stub:
        result = run_gate_over_http(gate, tmp_path, stub.base)
    gate.assert_exit(1, result, "a 200 that is not JSON is not a pass")
    gate.assert_contains(result.err, "the response is not JSON", "the error says what answered")
    gate.assert_contains(result.err, "The comparison did not happen", "the finding says so")
    gate.log_pass("a non-JSON answer is red")


def test_passes_when_the_pin_is_the_newest_release(gate, tmp_path):
    result = run_gate(gate, tmp_path, current_listing())
    gate.assert_exit(0, result, "a pin equal to upstream's newest stable release passes")
    gate.assert_contains(
        result.out, "Every real-provider pin is current", "the green line is printed"
    )
    gate.log_pass("current pins pass")


def test_fires_on_a_newer_release_past_the_window(gate, tmp_path):
    listing = current_listing()
    listing[BITWARDEN].insert(0, release("browser-v2026.10.0", "2026-10-08T12:00:00Z"))
    result = run_gate(gate, tmp_path, listing)
    gate.assert_exit(1, result, "a pin behind an aged release fails")
    gate.assert_contains(
        result.err, "Bitwarden browser extension", "the finding names the artifact"
    )
    gate.assert_contains(result.err, f"pinned {PIN_BW}", "the finding names the current pin")
    gate.assert_contains(result.err, "2026.10.0", "the finding names the newer version")
    gate.assert_contains(
        result.err, "published 2026-10-08T12:00:00Z", "the finding names its publish date"
    )
    gate.assert_contains(
        result.err,
        "  fix: npm run pins -- bump real-provider:bitwarden\n",
        "the finding gives the pins bump command for the stale pin",
    )
    gate.assert_not_contains(
        result.err, "real-provider:vaultwarden", "a current pin is not in the fix"
    )
    gate.log_pass("a stale pin fires with the pin, the release, its date and the bump command")


def test_both_pins_behind_each_get_their_bump_line(gate, tmp_path):
    listing = current_listing()
    listing[BITWARDEN].insert(0, release("browser-v2026.10.0"))
    listing[VAULTWARDEN].insert(0, release("1.38.0"))
    result = run_gate(gate, tmp_path, listing)
    gate.assert_exit(1, result, "two pins behind fail")
    for pin in ("bitwarden", "vaultwarden"):
        gate.assert_contains(
            result.err,
            "  fix: npm run pins -- bump real-provider:%s\n" % pin,
            "each stale pin names its own bump",
        )
    gate.log_pass("two stale pins each name their pins bump")


def test_defers_a_release_inside_the_window(gate, tmp_path):
    listing = current_listing()
    listing[VAULTWARDEN].insert(0, release("1.38.0", an_hour_ago()))
    result = run_gate(gate, tmp_path, listing)
    gate.assert_exit(0, result, "a release published an hour ago is not a finding yet")
    gate.assert_contains(result.out, "1.38.0", "the note names the deferred release")
    gate.assert_contains(result.out, "inside the release-age window", "the note says why")
    gate.log_pass("a fresh release is deferred with a note")


def test_the_newest_eligible_release_is_the_finding(gate, tmp_path):
    listing = current_listing()
    listing[BITWARDEN].insert(0, release("browser-v2026.10.0"))
    listing[BITWARDEN].insert(0, release("browser-v2026.10.1", an_hour_ago()))
    result = run_gate(gate, tmp_path, listing)
    gate.assert_exit(1, result, "an aged release behind a fresh one is still a finding")
    gate.assert_contains(
        result.err, "->  2026.10.0, published", "the finding names the aged release"
    )
    gate.assert_contains(result.out, "2026.10.1", "the fresh release is noted as deferred")
    gate.assert_not_contains(result.err, "2026.10.1", "the fresh release is not the finding")
    gate.log_pass("a fresh release does not hide an aged one behind it")


def test_ignores_what_is_not_a_stable_release_of_the_pin(gate, tmp_path):
    listing = current_listing()
    listing[BITWARDEN][:0] = [
        release("browser-v2026.11.0", prerelease=True),
        release("browser-v2026.11.1", draft=True),
        release("browser-v2026.11.2-beta.1"),
        release("desktop-v2026.11.3"),
    ]
    listing[VAULTWARDEN].insert(0, release("1.38.0", prerelease=True))
    result = run_gate(gate, tmp_path, listing)
    gate.assert_exit(
        0, result, "a pre-release, a draft, a beta tag and another component are not findings"
    )
    gate.log_pass("pre-releases, drafts, beta tags and other components are ignored")


def test_a_listing_absent_from_the_fixture_is_red(gate, tmp_path):
    listing = current_listing()
    del listing[VAULTWARDEN]
    result = run_gate(gate, tmp_path, listing)
    gate.assert_exit(1, result, "a pin with no listing was not compared, which is not a pass")
    gate.assert_contains(result.err, "NOT compared", "the finding says the pin was not compared")
    gate.assert_contains(result.err, f"Vaultwarden (pinned {PIN_VW})", "the finding names the pin")
    gate.assert_contains(
        result.out,
        "Bitwarden browser extension: %s is the newest" % PIN_BW,
        "the other pin is judged",
    )
    gate.assert_not_contains(result.out, "Every real-provider pin", "no green line is printed")
    gate.log_pass("a pin with no listing is red")


def test_a_listing_that_is_not_a_release_list_is_red(gate, tmp_path):
    listing = current_listing()
    listing[BITWARDEN] = {"message": "Moved Permanently"}
    result = run_gate(gate, tmp_path, listing)
    gate.assert_exit(1, result, "an answer that is not a release list is not a network failure")
    gate.assert_contains(result.err, "cannot use", "the error says the listing is unusable")
    gate.assert_contains(result.err, "bitwarden/clients", "the error names the repository")
    gate.log_pass("a malformed listing is red")


def test_a_listing_without_the_tag_scheme_is_red(gate, tmp_path):
    listing = current_listing()
    listing[BITWARDEN] = [release("web-v2026.10.0"), release("extension-2026.10.0")]
    result = run_gate(gate, tmp_path, listing)
    gate.assert_exit(
        1, result, "a listing with no release under the prefix would pass forever if soft"
    )
    gate.assert_contains(
        result.err, 'no stable release tagged "browser-v', "the error names the prefix"
    )
    gate.log_pass("a listing that lost the tag scheme is red")


def test_an_unreadable_lock_file_is_red(gate, tmp_path):
    missing = run_gate(gate, tmp_path, current_listing(), tmp_path / "absent.json")
    gate.assert_exit(1, missing, "no lock file means no pins were judged")
    gate.assert_contains(
        missing.err, "submodule must be checked out", "the error says what is missing"
    )
    shapeless = run_gate(
        gate, tmp_path, current_listing(), write_lock(tmp_path, bitwarden={"version": "latest"})
    )
    gate.assert_exit(1, shapeless, "a pin that is not a version cannot be compared")
    gate.assert_contains(shapeless.err, "bitwarden.version", "the error names the field")
    gate.log_pass("a missing or shapeless lock file is red")


def test_the_tracked_lock_file_is_readable(gate, tmp_path):
    """The one case on the real file: the gate and the account repository agree on the lock file's shape."""
    if not REAL_LOCK.is_file():
        gate.log_fail("the tracked lock file is missing: %s" % paths.relative_to_root(REAL_LOCK))
    listing = {BITWARDEN: [release("browser-v0.0.1")], VAULTWARDEN: [release("0.0.1")]}
    result = run_gate(gate, tmp_path, listing, REAL_LOCK)
    gate.assert_exit(0, result, "the tracked pins are read and are newer than 0.0.1")
    gate.log_pass("the tracked lock file parses")
