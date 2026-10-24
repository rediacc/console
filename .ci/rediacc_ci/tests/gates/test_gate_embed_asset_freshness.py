"""Port of `.ci/scripts/test/gates/test-embed-asset-freshness.sh`, retired in W7 P5.

Integration test for `scripts/gates/check-embed-asset-freshness.ts`.

Drives the gate through `EMBED_FRESHNESS_FIXTURE` (a JSON map of base -> latest version/date used instead of the network), so it runs offline and deterministically. Proves: it passes when nothing is behind, FIRES on a stale pin, DEFERS a just-released version (the shared soak), and FAILS CLOSED when a source was not compared.

FAIL CLOSED (operator ruling 2026-10-13, "Everything fails closed, nightly included"), control first against a stub HTTP server (`upstream_stub.py`) that `EMBED_UPSTREAM_BASE` stands in for BOTH hosts the gate asks, api.github.com and download.samba.org: every upstream served is green and the token never reaches the stub; a port nothing listens on is RED after three attempts, with each pin, the host and path, the error code and the words "UPSTREAM REACHABILITY FAILURE"; the rsync index alone failing is RED; the tags fallback failing is RED; a failure that clears inside the retry budget is green; an answer that cannot be used is RED; a held pin is not asked and is counted. The one request whose failure is NOT a finding, the HEAD for the rsync tarball's date, is pinned in both directions: it cannot turn a current pin red, and it cannot turn a stale pin green.

THE FIXTURE MAP IS DERIVED FROM THE SUBJECT'S OWN SOURCE LIST, not retyped. The twin hand-lists seven component keys in four separate heredocs; a component added upstream leaves all four short, and the gate's "not in fixture" branch used to turn the new component into a could-not-check that FAILED SOFT -- so the twin kept passing while covering one component less. (Since 2026-10-13 that branch is red.) Here the
keys are obtained by IMPORTING `EMBED_ASSET_SOURCES`, the same module the gate imports, and reading `.base` off each entry. That is behaviour rather than a regex over the source: a list that moves to another file, or changes shape, breaks this loudly instead of matching nothing and quietly producing an empty map.

`test_fixture_keys_are_corpus_derived` is the refusal that keeps that honest: zero keys read means every case below fed the gate an empty map.

THE SUBMODULE-ABSENT PATH IS A REFUSAL HERE, NOT A SILENT `exit 0`; see the same paragraph in `test_gate_embed_credits`.
"""

import datetime
import json

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness
from rediacc_ci.tests.gates.upstream_stub import (
    assert_no_token,
    closed_port,
    ok,
    sentinel,
    status,
    stub_upstream,
)

VALIDATOR = paths.from_root("scripts/gates", "check-embed-asset-freshness.ts")
SOURCES = paths.from_root("scripts", "lib", "embed-asset-sources.ts")
DOCKERFILE = paths.from_root("private", "renet", "Dockerfile")

PROBE = (
    "import { EMBED_ASSET_SOURCES } from './scripts/lib/embed-asset-sources.ts';\n"
    "process.stdout.write(JSON.stringify(EMBED_ASSET_SOURCES.map((s) => "
    "({ base: s.base, display: s.display, kind: s.kind, repo: s.repo ?? null }))));"
)

# The gate keys its upstream map on the `base` of each source it knows about. Importing the list costs one tsx start-up, so it is paid once per pytest process rather than once per case. A ONE-SLOT DICT rather than a rebound module global: the value is memoised, not reassigned, so no `global` statement is needed.
_BASES: dict[str, list[dict]] = {}

SUBMODULE_FIX = (
    "git submodule update --init private/renet; the gate reads the real Dockerfile "
    "pins from there and has nothing to compare against without them"
)


def require_submodule(gate) -> None:
    if not DOCKERFILE.is_file():
        gate.log_fail(
            "%s is absent, so this case could not run at all. Fix: %s"
            % (paths.relative_to_root(DOCKERFILE), SUBMODULE_FIX)
        )


def sources(gate) -> list[dict]:
    """The gate's own source list: base, display, kind and repo of each embedded asset."""
    if "value" in _BASES:
        return _BASES["value"]
    for path in (VALIDATOR, SOURCES):
        if not path.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(path))
    npx = harness.require_tool(
        "npx", "install node; the source list is a TypeScript module read through tsx"
    )
    probe = harness.run(
        [
            npx,
            "tsx",
            "--eval",
            PROBE,
        ],
        cwd=paths.repo_root(),
    )
    found: list[dict] = []
    if probe.rc == 0:
        try:
            found = list(json.loads(probe.out.strip().splitlines()[-1]))
        except (ValueError, IndexError):
            found = []
    if not found:
        gate.log_fail(
            "read ZERO source(s) out of %s (rc=%d, stdout=%r, stderr=%r), so every "
            "fixture below would be an EMPTY map, and no case here would be driving the "
            "component it names. Either the list moved or EMBED_ASSET_SOURCES changed shape."
            % (paths.relative_to_root(SOURCES), probe.rc, probe.out, probe.err)
        )
    _BASES["value"] = found
    return found


def source_bases(gate) -> list[str]:
    return [str(src["base"]) for src in sources(gate)]


def upstream_map(gate, **overrides) -> dict:
    """Every known source reported far OLDER than any real pin, then `overrides`."""
    data = {base: {"version": "0.0.1"} for base in source_bases(gate)}
    data.update(overrides)
    return data


def run_gate(tmp_path, mapping: dict, blocklist: str | None = None) -> harness.RunResult:
    fixture = tmp_path / "upstream.json"
    fixture.write_text(json.dumps(mapping), encoding="utf-8")
    env = {"EMBED_FRESHNESS_FIXTURE": str(fixture)}
    # `None` MEANS AN EMPTY BLOCKLIST, NOT THE REPOSITORY'S. Leaving EMBED_BLOCKLIST_FILE unset let the gate read the live `.ci/policy/.embed-assets-upgrade-blocklist`, and every upstream-map case here plants its staleness on k3s -- so the day k3s was first held (2026-09-16, branch 0914-1) `test_fires_when_stale` stopped being able to fire, and `test_twin_parity` reported the twin
    # passing while this port failed on the same tree.
    #
    # These cases are about the GATE, not about today's policy. The bash twin
    # `test-embed-asset-freshness.sh` carries the same fix and the same reason;
    # they were changed together, because a control isolated on one side of a differential and coupled on the other is exactly how a verdict diverges.
    path = tmp_path / "blocklist"
    path.write_text(
        blocklist
        if blocklist is not None
        else "# no holds; this fixture exists so the cases do not read live policy\n",
        encoding="utf-8",
    )
    env["EMBED_BLOCKLIST_FILE"] = str(path)
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(VALIDATOR)], cwd=paths.repo_root(), env=env)


def test_fixture_keys_are_corpus_derived(gate):
    """PORT-ONLY anti-vacuity: the fixtures below cover every source the gate has."""
    require_submodule(gate)
    bases = source_bases(gate)
    if "k3s" not in bases:
        gate.log_fail(
            "the stale and fresh cases below drive component 'k3s', which the subject no "
            "longer declares. Re-point them at a source that exists; a fixture naming a "
            "component the gate does not check cannot make it fire."
        )
    gate.log_pass(
        "%d upstream source(s) read out of the subject, k3s among them: %s"
        % (len(bases), ", ".join(bases))
    )


def test_passes_when_current(gate, tmp_path):
    require_submodule(gate)
    result = run_gate(tmp_path, upstream_map(gate))
    gate.assert_exit(0, result, "nothing behind upstream should pass")
    gate.log_pass("current pins pass")


def test_fires_when_stale(gate, tmp_path):
    require_submodule(gate)
    stale = upstream_map(gate, k3s={"version": "9999.0.0", "publishedAt": "2020-01-01T00:00:00Z"})
    result = run_gate(tmp_path, stale)
    gate.assert_exit(1, result, "a pin behind upstream should fail")
    gate.assert_contains(result.combined, "k3s", "error names the stale component")
    gate.assert_contains(
        result.err, "  fix: npm run pins -- bump embed:k3s\n", "red output gives the pins fix"
    )
    gate.log_pass("stale pin fires")


def test_defers_fresh_release(gate, tmp_path):
    require_submodule(gate)
    recent = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(hours=1)
    fresh = upstream_map(
        gate,
        k3s={"version": "9999.0.0", "publishedAt": recent.strftime("%Y-%m-%dT%H:%M:%SZ")},
    )
    result = run_gate(tmp_path, fresh)
    gate.assert_exit(0, result, "a just-released upstream version should be deferred, not failed")
    gate.assert_contains(
        result.combined, "deferred", "fresh release is reported as deferred (soak)"
    )
    gate.log_pass("fresh release is deferred by the soak")


def test_a_source_absent_from_the_fixture_is_red(gate, tmp_path):
    """Was `test_fails_soft_when_uncheckable`, which asserted exit 0 here. A source with no upstream answer was not compared, and that is not a pass."""
    require_submodule(gate)
    result = run_gate(tmp_path, {})
    gate.assert_exit(1, result, "sources that were not compared fail the gate")
    gate.assert_contains(
        result.err,
        "%d embed-asset pin(s) were NOT compared with upstream" % len(source_bases(gate)),
        "every source is a finding",
    )
    gate.assert_contains(result.err, "k3s (pinned ", "the finding names the pin")
    gate.assert_contains(
        result.err, "fixture k3s -> no entry in the fixture", "the miss says what was absent"
    )
    gate.assert_not_contains(
        result.err, "attempt(s)", "a fixture lookup makes no request, so it claims no attempt"
    )
    gate.assert_not_contains(result.out, "Every embed-asset pin", "no green line is printed")
    gate.log_pass("a source that was not compared is red")


# ---- fail closed, over real HTTP ------------------------------------------------------
#
# EMBED_UPSTREAM_BASE points the gate at a stub that serves both hosts: the GitHub API under /repos/ and the rsync index under /pub/rsync/src/. Every source answers version 0.0.1, older than any real pin, unless a case says otherwise.

LONG_AGO = "2020-01-01T00:00:00Z"
RSYNC_INDEX = "/pub/rsync/src/"
# The one project that tags without cutting releases, so its /releases/latest answers 404 and the gate reads its tag list.
TAGS_ONLY = "criu"


def latest_route(src: dict) -> str:
    return "/repos/%s/releases/latest" % src["repo"]


def tags_route(src: dict) -> str:
    return "/repos/%s/tags" % src["repo"]


def rsync_tarball(version: str) -> str:
    return "%srsync-%s.tar.gz" % (RSYNC_INDEX, version)


def rsync_index(version: str) -> tuple:
    return ok(b'<a href="rsync-%s.tar.gz">rsync-%s.tar.gz</a>' % ((version.encode(),) * 2))


def by_base(gate, base: str) -> dict:
    return next(src for src in sources(gate) if src["base"] == base)


def current_script(gate) -> dict[str, list[tuple]]:
    """A stub script in which every upstream reports 0.0.1: releases for most, the tag list and its commit for TAGS_ONLY, the Samba index and its tarball for rsync."""
    script: dict[str, list[tuple]] = {}
    for src in sources(gate):
        if src["kind"] != "github":
            script[RSYNC_INDEX] = [rsync_index("0.0.1")]
            script[rsync_tarball("0.0.1")] = [
                ok(b"", last_modified="Wed, 01 Jan 2020 00:00:00 GMT")
            ]
        elif src["base"] == TAGS_ONLY:
            script[tags_route(src)] = [ok([{"name": "v0.0.1"}, {"name": "v0.0.1-rc1"}])]
            script["/repos/%s/commits/v0.0.1" % src["repo"]] = [
                ok({"commit": {"committer": {"date": LONG_AGO}}})
            ]
        else:
            script[latest_route(src)] = [ok({"tag_name": "v0.0.1", "published_at": LONG_AGO})]
    return script


def run_gate_over_http(tmp_path, base: str, blocklist: str | None = None) -> harness.RunResult:
    """The gate against `base` over real HTTP: no fixture map, so the fetch, the status handling and the retry all run. The blocklist is a fixture for the reason `run_gate` gives."""
    holds = tmp_path / "blocklist"
    holds.write_text(
        blocklist or "# no holds; the cases do not read live policy\n", encoding="utf-8"
    )
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run(
        [npx, "tsx", str(VALIDATOR)],
        cwd=paths.repo_root(),
        env={
            "EMBED_UPSTREAM_BASE": base,
            "EMBED_FRESHNESS_FIXTURE": "",
            "EMBED_BLOCKLIST_FILE": str(holds),
            "GITHUB_TOKEN": sentinel(),
        },
    )


def test_control_every_upstream_served_over_http_is_green(gate, tmp_path):
    """The control for every red HTTP case below: the same stub, answering, is green."""
    require_submodule(gate)
    count = len(sources(gate))
    criu = by_base(gate, TAGS_ONLY)
    with stub_upstream(current_script(gate)) as stub:
        result = run_gate_over_http(tmp_path, stub.base)
        gate.assert_exit(0, result, "every upstream served over HTTP passes")
        gate.assert_contains(
            result.out,
            "%d of %d compared with upstream, 0 held" % (count, count),
            "the count of compared pins is printed",
        )
        gate.assert_eq(stub.asked(latest_route(criu)), 1, "a 404 on releases/latest is not retried")
        gate.assert_eq(stub.asked(tags_route(criu)), 1, "the tag list is the fallback")
        gate.assert_eq(stub.asked(RSYNC_INDEX), 1, "the rsync index is asked")
        gate.assert_eq(stub.asked(rsync_tarball("0.0.1"), "HEAD"), 1, "the tarball date is asked")
        gate.assert_eq(stub.tokens_seen(), 0, "the token is not sent to a seam")
    gate.log_pass("the stub upstreams, answering, are green")


def test_a_stale_pin_over_http_still_fires(gate, tmp_path):
    require_submodule(gate)
    script = current_script(gate)
    script[latest_route(by_base(gate, "zot"))] = [
        ok({"tag_name": "v9999.0.0", "published_at": LONG_AGO})
    ]
    with stub_upstream(script) as stub:
        result = run_gate_over_http(tmp_path, stub.base)
    gate.assert_exit(1, result, "a pin behind an aged release fails over HTTP too")
    gate.assert_contains(result.err, "upstream 9999.0.0", "the finding names the newer version")
    gate.assert_not_contains(result.err, "NOT compared", "a stale pin is not a failed fetch")
    gate.log_pass("the HTTP path judges an answer the way the fixture path does")


def test_an_unreachable_upstream_is_red(gate, tmp_path):
    require_submodule(gate)
    count = len(sources(gate))
    zot = by_base(gate, "zot")
    port = closed_port()
    result = run_gate_over_http(tmp_path, "http://127.0.0.1:%d" % port)
    gate.assert_exit(1, result, "upstreams nothing answers on fail closed")
    gate.assert_contains(
        result.err, "%d embed-asset pin(s) were NOT compared with upstream" % count, "all are named"
    )
    gate.assert_contains(
        result.err,
        "GET 127.0.0.1:%d%s -> network error ECONNREFUSED, after 3 attempt(s)"
        % (port, latest_route(zot)),
        "a GitHub finding names the host and path, the error code and the attempts",
    )
    gate.assert_contains(
        result.err,
        "GET 127.0.0.1:%d%s -> network error ECONNREFUSED, after 3 attempt(s)"
        % (port, RSYNC_INDEX),
        "the rsync index is a finding too",
    )
    gate.assert_contains(result.err, "zot (pinned ", "a finding names its pin")
    gate.assert_contains(
        result.err,
        "UPSTREAM REACHABILITY FAILURE (127.0.0.1:%d), not a stale pin" % port,
        "the finding says what kind of red this is and names the host",
    )
    gate.assert_contains(result.err, "attempt 2 of 3 failed", "the retries are visible")
    gate.assert_not_contains(result.out, "Every embed-asset pin", "no green line is printed")
    assert_no_token(gate, result)
    gate.log_pass("unreachable upstreams are red after three attempts")


def test_the_rsync_index_alone_failing_is_red(gate, tmp_path):
    """The second host. GitHub answering does not make the Samba index optional."""
    require_submodule(gate)
    script = current_script(gate)
    script[RSYNC_INDEX] = [status(503)]
    with stub_upstream(script) as stub:
        result = run_gate_over_http(tmp_path, stub.base)
        gate.assert_eq(stub.asked(RSYNC_INDEX), 3, "a 5xx is asked three times and no more")
    gate.assert_exit(1, result, "the rsync index not answering fails closed")
    gate.assert_contains(result.err, "1 embed-asset pin(s) were NOT compared", "one finding")
    gate.assert_contains(
        result.err, "%s -> HTTP 503, after 3 attempt(s)" % RSYNC_INDEX, "path, status and attempts"
    )
    gate.assert_contains(result.err, "rsync (pinned ", "the finding names the pin")
    gate.log_pass("the rsync index failing is red by itself")


def test_the_tags_fallback_failing_is_red(gate, tmp_path):
    """A 404 on releases/latest is the documented fallback and not a finding; the request it falls back to failing is one."""
    require_submodule(gate)
    script = current_script(gate)
    criu = by_base(gate, TAGS_ONLY)
    script[tags_route(criu)] = [status(404)]
    with stub_upstream(script) as stub:
        result = run_gate_over_http(tmp_path, stub.base)
    gate.assert_exit(1, result, "a repository that answers 404 to both requests was not compared")
    gate.assert_contains(result.err, "1 embed-asset pin(s) were NOT compared", "one finding")
    gate.assert_contains(
        result.err,
        "%s -> HTTP 404, after 1 attempt(s)" % tags_route(criu),
        "the tags path is named",
    )
    gate.log_pass("the tags fallback failing is red")


def test_a_transient_failure_then_success_is_green(gate, tmp_path):
    require_submodule(gate)
    script = current_script(gate)
    zot = by_base(gate, "zot")
    script[latest_route(zot)].insert(0, status(503))
    script[RSYNC_INDEX].insert(0, (429, {"retry-after": "1"}, {}))
    count = len(sources(gate))
    with stub_upstream(script) as stub:
        result = run_gate_over_http(tmp_path, stub.base)
        gate.assert_eq(stub.asked(latest_route(zot)), 2, "the 503 is asked again once")
        gate.assert_eq(stub.asked(RSYNC_INDEX), 2, "the 429 is asked again once")
    gate.assert_exit(0, result, "a failure that clears inside the retry budget passes")
    gate.assert_contains(result.err, "attempt 1 of 3 failed (HTTP 503)", "the retry is visible")
    gate.assert_contains(
        result.out, "%d of %d compared with upstream" % (count, count), "every pin was compared"
    )
    gate.log_pass("a transient failure followed by the answer is green")


def test_an_answer_that_cannot_be_used_is_red(gate, tmp_path):
    require_submodule(gate)
    script = current_script(gate)
    zot = by_base(gate, "zot")
    script[latest_route(zot)] = [ok({"message": "a release with no tag"})]
    script[RSYNC_INDEX] = [ok(b"<html>an index with no tarball</html>")]
    with stub_upstream(script) as stub:
        result = run_gate_over_http(tmp_path, stub.base)
    gate.assert_exit(1, result, "an answer the gate cannot read would pass forever if soft")
    gate.assert_contains(result.err, "cannot use", "the error says the answer is unusable")
    gate.assert_contains(result.err, "no tag_name in release", "the release is named")
    gate.assert_contains(result.err, "no rsync tarballs found in index", "the index is named")
    gate.assert_not_contains(
        result.err, "NOT compared", "an unusable answer is not a network failure"
    )
    gate.log_pass("an answer that cannot be used is red")


def test_the_rsync_date_request_failing_cannot_change_a_verdict_to_green(gate, tmp_path):
    """The one request whose failure is not a finding. CONTROL: with rsync current, the HEAD failing leaves the gate green and says so. THE DIRECTION THAT MATTERS: with rsync stale, the HEAD failing leaves it RED (no date means no soak)."""
    require_submodule(gate)
    script = current_script(gate)
    script[rsync_tarball("0.0.1")] = [status(503)]
    with stub_upstream(script) as stub:
        current = run_gate_over_http(tmp_path, stub.base)
        gate.assert_eq(stub.asked(rsync_tarball("0.0.1"), "HEAD"), 3, "the HEAD is retried")
    gate.assert_exit(0, current, "a current rsync with no date is still current")
    gate.assert_contains(current.out, "no publish date for 0.0.1", "the failure is printed")
    gate.assert_contains(current.out, "judged without the soak", "and what it means")

    stale = current_script(gate)
    stale[RSYNC_INDEX] = [rsync_index("9999.0.0")]
    stale[rsync_tarball("9999.0.0")] = [status(503)]
    with stub_upstream(stale) as stub:
        behind = run_gate_over_http(tmp_path, stub.base)
    gate.assert_exit(
        1, behind, "a stale rsync with no date is reported, not deferred and not skipped"
    )
    gate.assert_contains(behind.err, "upstream 9999.0.0", "the finding names the newer version")
    gate.log_pass("the rsync date request failing never produces a green that hides a stale pin")


def test_a_held_pin_is_not_asked_and_is_counted(gate, tmp_path):
    """A hold is an explicit, reasoned exemption, so a held pin is the one pin a green may leave uncompared, and the green line counts it."""
    require_submodule(gate)
    script = current_script(gate)
    zot = by_base(gate, "zot")
    script[latest_route(zot)] = [status(503)]
    hold = (
        "# BLOCKER: upstream zot 2.2 changed the storage layout the embedded registry "
        "reads; holding until the migration lands\nzot\n"
    )
    count = len(sources(gate))
    with stub_upstream(script) as stub:
        result = run_gate_over_http(tmp_path, stub.base, blocklist=hold)
        gate.assert_eq(stub.asked(latest_route(zot)), 0, "a held pin's upstream is not asked")
    gate.assert_exit(0, result, "a held pin whose upstream is down does not fail the gate")
    gate.assert_contains(
        result.out,
        "%d of %d compared with upstream, 1 held" % (count - 1, count),
        "counted as held",
    )
    gate.log_pass("a held pin is not asked, and the green line says one was held")


def test_blocklist_rejects_missing_reason(gate, tmp_path):
    """The blocklist is a BLOCKER-gated suppression list; a bare entry with no substantive reason must fail the gate, not silently hold the pin."""
    require_submodule(gate)
    result = run_gate(tmp_path, upstream_map(gate), blocklist="criu\n")
    gate.assert_exit(1, result, "a blocklist entry lacking a BLOCKER reason must fail the gate")
    gate.assert_contains(result.combined, "invalid entries", "error names the malformed blocklist")
    gate.log_pass("blocklist entry without a BLOCKER reason fires")


def test_blocklist_accepts_valid_reason(gate, tmp_path):
    """A properly-reasoned blocklist entry is accepted (freshness itself passes here)."""
    require_submodule(gate)
    good = (
        "# BLOCKER: upstream criu 4.3 regressed cgroup-v2 restore; holding at 4.2 until "
        "fixed\ncriu\n"
    )
    result = run_gate(tmp_path, upstream_map(gate), blocklist=good)
    gate.assert_exit(
        0, result, "a blocklist entry with a substantive BLOCKER reason must be accepted"
    )
    gate.log_pass("well-formed blocklist entry is accepted")


# ---- own-property lookups: a component named like an Object.prototype key is ABSENT -----
#
# Every table keyed by component name (the lockfile's components, SHA256_SOURCES, SOURCE_CONSTS, the freshness fixture) is read with `Object.hasOwn`. A bracket lookup returns an inherited value for each (the inherited function for `constructor` and `toString`, Object.prototype itself for `__proto__`), which reads as a found entry. The cases below drive the exported helpers directly (a real source list never contains such a base, so the gate cannot reach them) and each fails when ITS lookup is reverted to a bracket.

PROTO_NAMES = ("constructor", "toString", "__proto__")

UPGRADE_PROBE = (
    "import { upgradeComponent, fixtureEntry } from './scripts/lib/embed-pin-upgrade.ts';\n"
    "(async () => {\n"
    "const inp = JSON.parse(process.env.PROBE_INPUT);\n"
    "const none = { commitOf: async () => { throw new Error('unexpected'); },"
    " text: async () => { throw new Error('unexpected'); } };\n"
    "if (inp.fixture !== undefined) {\n"
    "  process.stdout.write(JSON.stringify({ hit: fixtureEntry(inp.fixture, inp.base) ?? null }));\n"
    "} else {\n"
    "  const r = await upgradeComponent({ dockerfile: inp.dockerfile, lock: inp.lock, consts: {} },"
    " { base: inp.base, display: inp.base, pinned: '1.0.0', latest: '2.0.0', repo: 'o/r' }, none);\n"
    "  process.stdout.write(JSON.stringify({ ok: r.ok, reason: r.ok ? '' : r.reason,"
    " consts: r.ok ? r.files.consts : null }));\n"
    "}\n"
    "})();"
)


def probe(gate, payload: dict) -> dict:
    npx = harness.require_tool("npx", "install node; the helpers are TypeScript read through tsx")
    result = harness.run(
        [npx, "tsx", "--eval", UPGRADE_PROBE],
        cwd=paths.repo_root(),
        env={"PROBE_INPUT": json.dumps(payload)},
    )
    gate.assert_exit(0, result, "the helper must return, not throw, for base %r" % payload["base"])
    return json.loads(result.out.strip().splitlines()[-1])


def probe_upgrade(gate, name: str, component: dict | None) -> dict:
    components = {} if component is None else {name: component}
    return probe(
        gate,
        {
            "base": name,
            "dockerfile": "ARG %s_VERSION=1.0.0\n" % name.upper(),
            "lock": json.dumps({"components": components}),
        },
    )


def test_hasown_lockfile_components_lookup(gate):
    for name in PROTO_NAMES:
        got = probe_upgrade(gate, name, None)
        gate.assert_eq(got["ok"], False, "%s is not a lockfile component" % name)
        gate.assert_contains(
            got["reason"], "has no components.%s entry" % name, "reported as ABSENT, not found"
        )
    gate.log_pass("a prototype-named base is absent from the lockfile components")


def test_hasown_sha256_sources_lookup(gate):
    pinned = {"version": "1.0.0", "arches": {"amd64": {"sha256": "a" * 64}}}
    for name in PROTO_NAMES:
        got = probe_upgrade(gate, name, pinned)
        gate.assert_eq(got["ok"], False, "%s has no published checksum source" % name)
        gate.assert_contains(
            got["reason"],
            "sha256 pin cannot be resolved",
            "no checksum source, not an inherited one",
        )
    gate.log_pass("a prototype-named base has no SHA256 source")


def test_hasown_source_consts_lookup(gate):
    for name in PROTO_NAMES:
        got = probe_upgrade(gate, name, {"version": "1.0.0"})
        gate.assert_eq(got["ok"], True, "%s has no Go constant sites, so the bump succeeds" % name)
        gate.assert_eq(got["consts"], {}, "no Go file is touched for %s" % name)
    gate.log_pass("a prototype-named base has no SOURCE_CONSTS sites")


def test_hasown_fixture_lookup(gate):
    for name in PROTO_NAMES:
        got = probe(gate, {"base": name, "fixture": {}})
        gate.assert_eq(got["hit"], None, "%s is not in the fixture" % name)
    own = probe(gate, {"base": "k3s", "fixture": {"k3s": {"version": "9.9.9"}}})
    gate.assert_eq(own["hit"], {"version": "9.9.9"}, "CONTROL: an own key is still found")
    gate.log_pass("a prototype-named base is absent from the fixture, an own key is found")


def test_pins_driver_selftest_holds_the_refusals_the_retired_upgrade_cases_proved(gate):
    """The retired `--upgrade` cases (the shared snapshotter clone, a pin with no published checksum, an unresolvable commit, the version moving with its commit) live in the embed pins driver's selftest, which no other gate runs. Running it here keeps them proved: it must exit 0 and print a PASS line for each."""
    require_submodule(gate)
    npx = harness.require_tool(
        "npx", "install node; the selftest is a TypeScript program driven through tsx"
    )
    result = harness.run(
        [npx, "tsx", "scripts/lib/pins/drivers/embed-selftest.ts"], cwd=paths.repo_root()
    )
    gate.assert_exit(0, result, "the embed pins driver selftest must pass")
    for line in (
        "csisnapshotter bump: Dockerfile commit and both versions move together",
        "a release whose tag cannot be resolved to a commit is refused whole",
        "a held sibling that shares the clone refuses the bump of the other",
        "rsync bump: no published checksum, so the plan is refused rather than leaving the digest behind",
    ):
        gate.assert_contains(result.out, "PASS  " + line, "the selftest proves: " + line)
    gate.log_pass("the embed driver selftest proves the retired upgrade properties")
