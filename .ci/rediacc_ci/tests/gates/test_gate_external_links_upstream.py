"""`scripts/gates/check-external-links.ts` fails closed when a linked host does not answer (operator ruling 2026-10-14, "Extend to all seven").

`EXTERNAL_LINKS_FIXTURE_ROOT` runs the scan over a fixture tree holding every SCAN_ROOT, with an empty allowlist and KNOWN_BROKEN and loopback URLs checked, so a link can point at the stub HTTP server on 127.0.0.1 (`upstream_stub.py`). The request, the HEAD-then-GET fallback and the shared retry in `scripts/lib/upstream.ts` are the gate's real code path.

Proved, control first: links the stub answers are green with the count printed; a HEAD the stub refuses with 405 and a GET it serves is green; a 404 is a BROKEN link and NOT an outage; a port nothing listens on is RED with the reachability sentence and "NOT checked"; a 503 that persists is RED the same way; a 503 that clears is green; and once twenty links in a row went unanswered with no host answering at all, the rest are NOT asked and the run says why.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness
from rediacc_ci.tests.gates.upstream_stub import closed_port, ok, status, stub_upstream

VALIDATOR = paths.from_root("scripts", "gates", "check-external-links.ts")
SCAN_ROOTS = (
    "packages/www/src/content/docs",
    "packages/www/src/content/blog",
    "docs",
    ".ci/docs",
    ".github",
    "packages/cli",
)
# Where the fixture cites its links: the first scan root.
CITED = SCAN_ROOTS[0] + "/page.md:1"


def fixture(tmp: pathlib.Path, urls: list[str]) -> pathlib.Path:
    """A tree with one markdown file under every scan root; the first one cites `urls`."""
    root = tmp / "tree"
    for index, scan in enumerate(SCAN_ROOTS):
        directory = root / scan
        directory.mkdir(parents=True, exist_ok=True)
        body = (
            "".join("- [link %d](%s)\n" % (i, url) for i, url in enumerate(urls))
            if index == 0
            else "# empty\n"
        )
        (directory / "page.md").write_text(body, encoding="utf-8")
    return root


def run_gate(gate, root: pathlib.Path):
    if not VALIDATOR.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(VALIDATOR))
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run(
        [npx, "tsx", str(VALIDATOR)],
        cwd=paths.repo_root(),
        env={"EXTERNAL_LINKS_FIXTURE_ROOT": str(root), "GITHUB_TOKEN": ""},
    )


def test_control_answered_links_are_green(gate, tmp_path):
    with stub_upstream({"/a": [ok("page")], "/b": [ok("page")]}) as stub:
        result = run_gate(gate, fixture(tmp_path, [stub.base + "/a", stub.base + "/b"]))
        gate.assert_eq(stub.asked("/a", "HEAD"), 1, "a link is asked with HEAD first")
    gate.assert_exit(0, result, "links the stub answers pass")
    gate.assert_contains(result.out, "FIXTURE RUN", "a fixture run says so")
    gate.assert_contains(result.out, "All external links are valid (2 checked", "count printed")
    gate.log_pass("the stub, answering, is green")


def test_a_head_refusal_falls_back_to_get(gate, tmp_path):
    with stub_upstream({"/a": [status(405), ok("page")]}) as stub:
        result = run_gate(gate, fixture(tmp_path, [stub.base + "/a"]))
        gate.assert_eq(stub.asked("/a", "GET"), 1, "GET is asked after the HEAD refusal")
    gate.assert_exit(0, result, "a host that serves GET but not HEAD passes")
    gate.log_pass("HEAD 405 then GET 200 is green")


def test_a_404_is_a_broken_link_not_an_outage(gate, tmp_path):
    with stub_upstream({}) as stub:
        result = run_gate(gate, fixture(tmp_path, [stub.base + "/gone"]))
    gate.assert_exit(1, result, "a dead link fails")
    gate.assert_contains(result.err, "BROKEN [404]: %s/gone" % stub.base, "it is BROKEN")
    gate.assert_contains(result.err, "-> " + CITED, "the citing file and line are named")
    gate.assert_not_contains(result.err, "UPSTREAM REACHABILITY FAILURE", "a 404 is an answer")
    gate.log_pass("a 404 is a finding in the tree")


def test_an_unreachable_host_is_red_and_named_as_an_outage(gate, tmp_path):
    port = closed_port()
    url = "http://127.0.0.1:%d/a" % port
    result = run_gate(gate, fixture(tmp_path, [url]))
    gate.assert_exit(1, result, "a host nothing answers on fails closed")
    gate.assert_contains(result.err, "1 external link(s) were NOT compared with upstream", "named")
    gate.assert_contains(
        result.err,
        "%s (%s): HEAD 127.0.0.1:%d/a -> network error ECONNREFUSED, after 3 attempt(s)"
        % (url, CITED, port),
        "the finding names the link, where it is cited, the host and path, the code and attempts",
    )
    gate.assert_contains(
        result.err,
        "UPSTREAM REACHABILITY FAILURE (127.0.0.1:%d), not a broken link" % port,
        "the finding says what kind of red this is",
    )
    gate.assert_contains(result.err, "were NOT checked: their host did not answer", "summary")
    gate.assert_not_contains(result.err, "BROKEN [", "an outage is not reported as a dead link")
    gate.log_pass("an unreachable host is red, as an outage")


def test_a_persistent_503_is_red_and_a_cleared_one_is_green(gate, tmp_path):
    with stub_upstream({"/a": [status(503)]}) as stub:
        red = run_gate(gate, fixture(tmp_path / "red", [stub.base + "/a"]))
        gate.assert_eq(stub.asked("/a", "HEAD"), 3, "a 5xx is asked three times")
    gate.assert_exit(1, red, "a 503 that persists fails closed")
    gate.assert_contains(red.err, "-> HTTP 503, after 3 attempt(s)", "status and attempts")
    gate.assert_contains(red.err, "UPSTREAM REACHABILITY FAILURE", "it is an outage")
    with stub_upstream({"/a": [status(503), ok("page")]}) as stub:
        green = run_gate(gate, fixture(tmp_path / "green", [stub.base + "/a"]))
    gate.assert_exit(0, green, "a 503 that clears inside the budget passes")
    gate.assert_contains(green.err, "attempt 1 of 3 failed (HTTP 503)", "the retry is visible")
    gate.log_pass("the retry budget holds in both directions")


def test_a_network_outage_stops_asking_and_says_so(gate, tmp_path):
    port = closed_port()
    urls = ["http://127.0.0.1:%d/p%d" % (port, i) for i in range(30)]
    result = run_gate(gate, fixture(tmp_path, urls))
    gate.assert_exit(1, result, "an outage is red")
    gate.assert_contains(result.err, "external link(s) were NOT asked", "the rest are not asked")
    gate.assert_contains(result.err, "rather than 20 dead links", "the reason is printed")
    gate.log_pass("the outage breaker keeps an offline run short and red")
