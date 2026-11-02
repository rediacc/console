"""`rediacc_ci.quality.go_deps` (`check:ci-go-deps`) fails closed when the module proxy or OSV does not answer (operator ruling 2026-10-14, "Extend to all seven").

The gate runs for real, by its entry point, against a fixture tree (`REDIACC_CI_ROOT`) holding one Go module that requires `example.test/dep`. The real `go` resolves that module through GOPROXY, pointed at a stub HTTP server on 127.0.0.1 (`upstream_stub.py`) that speaks the module proxy protocol, and `GO_DEPS_OSV_URL` points the advisory screen at the same stub. Nothing reaches the network: GOSUMDB is off and the module cache lives under the test's own directory.

Proved, control first: a dependency already at the proxy's newest version is green; a newer version OSV lists as affected is green ("not demanded") and OSV was asked; a newer version OSV clears is a demand, red, and not an outage; a proxy nothing listens on is RED after three attempts with the reachability sentence naming the proxy; a proxy answering 503 is RED the same way; an OSV nothing listens on is RED with the sentence naming OSV, where until 2026-10-14 it was a warning and an unscreened demand.
"""

import json
import pathlib
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness
from rediacc_ci.tests.gates.upstream_stub import closed_port, ok, status, stub_upstream

ENTRY = paths.from_root(".ci", "scripts", "quality", "check_go_deps.py")
DEP = "example.test/dep"
MOD = b"module example.test/dep\n\ngo 1.21\n"
OSV_ROUTE = "/v1/query"
LIST_ROUTE = "/%s/@v/list" % DEP


def proxy_script(*versions: str) -> dict[str, list[tuple]]:
    """The module proxy protocol for `example.test/dep`, holding `versions` (the first is the one required)."""
    script: dict[str, list[tuple]] = {LIST_ROUTE: [ok("\n".join(versions).encode() + b"\n")]}
    for version in versions:
        base = "/%s/@v/%s" % (DEP, version)
        script[base + ".mod"] = [ok(MOD)]
        script[base + ".info"] = [ok({"Version": version, "Time": "2020-01-01T00:00:00Z"})]
    return script


def tree(tmp: pathlib.Path) -> pathlib.Path:
    """A repository root with one Go module under private/, and the release-age rule the gate delegates to."""
    root = tmp / "root"
    module = root / "private" / "m"
    module.mkdir(parents=True)
    (module / "go.mod").write_text(
        "module example.test/m\n\ngo 1.21\n\nrequire %s v1.0.0\n" % DEP, encoding="utf-8"
    )
    for rel in ("scripts/lib/release-age.ts", ".ci/config/release-age.json"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(paths.from_root(*rel.split("/")), root / rel)
    return root


def run_gate(gate, tmp: pathlib.Path, proxy: str, osv: str):
    if not ENTRY.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(ENTRY))
    harness.require_tool("go", "install Go; the gate shells out to `go list -u -m -json all`")
    return harness.run(
        [str(ENTRY)],
        cwd=paths.repo_root(),
        env={
            "REDIACC_CI_ROOT": str(tree(tmp)),
            "GOPROXY": proxy,
            "GOSUMDB": "off",
            "GOFLAGS": "-mod=mod -modcacherw",
            "GOMODCACHE": str(tmp / "modcache"),
            "GOTOOLCHAIN": "local",
            "GOPRIVATE": "",
            "GONOPROXY": "",
            "GONOSUMDB": "",
            "GO_DEPS_OSV_URL": osv + OSV_ROUTE,
            "CI": "",
        },
    )


def test_control_a_current_dependency_is_green(gate, tmp_path):
    with stub_upstream(proxy_script("v1.0.0")) as stub:
        result = run_gate(gate, tmp_path, stub.base, stub.base)
        gate.assert_eq(stub.asked(LIST_ROUTE), 1, "the proxy was asked for the version list")
        gate.assert_eq(stub.asked(OSV_ROUTE, "POST"), 0, "nothing to screen, so OSV is not asked")
    gate.assert_exit(0, result, "a dependency at the newest version passes")
    gate.assert_contains(result.err, "All Go direct dependencies are up-to-date", "the green line")
    gate.log_pass("the stub proxy, answering, is green")


def test_an_affected_update_osv_names_is_green_and_osv_was_asked(gate, tmp_path):
    script = proxy_script("v1.0.0", "v1.1.0")
    script[OSV_ROUTE] = [ok({"vulns": [{"id": "GO-0000-0001"}]})]
    with stub_upstream(script) as stub:
        result = run_gate(gate, tmp_path, stub.base, stub.base)
        gate.assert_eq(stub.asked(OSV_ROUTE, "POST"), 1, "OSV was asked once")
    gate.assert_exit(0, result, "a newer version OSV lists as affected is not demanded")
    gate.assert_contains(result.out, "(affected by GO-0000-0001)", "the advisory is named")
    gate.log_pass("the stub OSV, answering, screens the candidate")


def test_a_cleared_update_is_a_demand_not_an_outage(gate, tmp_path):
    script = proxy_script("v1.0.0", "v1.1.0")
    script[OSV_ROUTE] = [ok({})]
    with stub_upstream(script) as stub:
        result = run_gate(gate, tmp_path, stub.base, stub.base)
    gate.assert_exit(1, result, "an outdated minor dependency fails")
    gate.assert_contains(result.out, "m: %s v1.0.0 -> v1.1.0" % DEP, "the demand is named")
    gate.assert_not_contains(
        result.err, "UPSTREAM REACHABILITY FAILURE", "a demand is not an outage"
    )
    gate.log_pass("an outdated module is a finding in the tree")


def test_a_proxy_nothing_answers_on_is_red(gate, tmp_path):
    port = closed_port()
    with stub_upstream({}) as osv:
        result = run_gate(gate, tmp_path, "http://127.0.0.1:%d" % port, osv.base)
    gate.assert_exit(1, result, "an unreachable proxy fails closed")
    gate.assert_contains(
        result.err,
        "m: go list -u -m -json all (127.0.0.1:%d) -> network error ECONNREFUSED, after 3 attempt(s)"
        % port,
        "the finding names the module tree, the proxy, the error code and the attempts",
    )
    gate.assert_contains(
        result.err,
        "UPSTREAM REACHABILITY FAILURE (127.0.0.1:%d), not an outdated module" % port,
        "the finding says what kind of red this is",
    )
    gate.assert_contains(result.err, "attempt 2 of 3 failed", "the retries are visible")
    gate.assert_not_contains(result.err, "probe FAILED", "an outage is not a toolchain failure")
    gate.log_pass("an unreachable proxy is red after three attempts")


def test_a_proxy_answering_503_is_red(gate, tmp_path):
    script = proxy_script("v1.0.0", "v1.1.0")
    script[LIST_ROUTE] = [status(503)]
    with stub_upstream(script) as stub:
        result = run_gate(gate, tmp_path, stub.base, stub.base)
    gate.assert_exit(1, result, "a proxy that keeps failing fails closed")
    gate.assert_contains(result.err, "-> HTTP 503, after 3 attempt(s)", "the status and attempts")
    gate.assert_contains(result.err, "UPSTREAM REACHABILITY FAILURE", "it is an outage")
    gate.log_pass("a 503 from the proxy is an outage, red")


def test_an_osv_nothing_answers_on_is_red_not_an_unscreened_demand(gate, tmp_path):
    """THE HOLE THE RULING CLOSES: an OSV that could not be asked was a warning and a demand for a version nobody had screened."""
    port = closed_port()
    with stub_upstream(proxy_script("v1.0.0", "v1.1.0")) as stub:
        result = run_gate(gate, tmp_path, stub.base, "http://127.0.0.1:%d" % port)
    gate.assert_exit(1, result, "an unreachable OSV fails closed")
    gate.assert_contains(
        result.err,
        "m: %s v1.0.0 -> v1.1.0: POST 127.0.0.1:%d%s -> network error ECONNREFUSED, after 3 attempt(s)"
        % (DEP, port, OSV_ROUTE),
        "the finding names the module, the OSV host and path, the code and the attempts",
    )
    gate.assert_contains(result.err, "UPSTREAM REACHABILITY FAILURE (127.0.0.1:%d)" % port, "named")
    gate.assert_not_contains(result.err, "demanding it unscreened", "no unscreened demand")
    gate.assert_not_contains(result.out, "must upgrade", "no demand is made")
    gate.log_pass("an unreachable OSV is red")


def test_the_fixture_tree_holds_no_vendored_answers(gate, tmp_path):
    """Control for the fixture itself: the module the gate judges is the one written here, and the release-age rule was copied, so the greens above are not a gate that found no module."""
    root = tree(tmp_path)
    gate.assert_eq(
        sorted(p.name for p in (root / "private").iterdir()), ["m"], "one module directory"
    )
    gate.assert_eq(
        isinstance(
            json.loads((root / ".ci/config/release-age.json").read_text(encoding="utf-8")), dict
        ),
        True,
        "the release-age config is present and parses",
    )
    gate.assert_eq((root / "scripts/lib/release-age.ts").is_file(), True, "the rule is present")
    gate.log_pass("the fixture tree is what the cases claim")
