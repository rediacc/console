"""Port of `.ci/scripts/test/gates/test-devcontainer-pin-freshness.sh`, retired in W7 P5.

`scripts/gates/check-devcontainer-pin-freshness.ts`, driven entirely through its test seams so it runs offline and deterministically:

  DEVCONTAINER_FRESHNESS_FIXTURE  a JSON map of base -> latest version/date,
                                  used INSTEAD of the network
  DEVCONTAINER_BLOCKLIST_FILE     the blocklist whose BLOCKER convention is enforced
  DEVCONTAINER_DOCKERFILE         the Dockerfile the gate reads, here a copy
  DEVCONTAINER_API_BASE           another API base, here a stub HTTP server on 127.0.0.1
                                  (`upstream_stub.py`), so the request, the status handling
                                  and the retry are the gate's real code path

Proved: it passes when nothing is behind, FIRES on a stale pin with its `npm run pins -- bump devcontainer:<base>` fix line, DEFERS a just-released version (the shared soak), FAILS CLOSED when a source was not compared, and enforces the BLOCKER convention on its blocklist.

FAIL CLOSED (operator ruling 2026-10-13, "Everything fails closed, nightly included"), control first against the stub server: every listing served is green and the token never reaches the stub; a port nothing listens on is RED after three attempts, with the pin, the host and path, the error code and the words "UPSTREAM REACHABILITY FAILURE"; a rate limit is RED at once; a 503 followed by the listing is green inside the retry budget; a listing with no release under the tag prefix is RED; a source with no ARG in the Dockerfile is RED; a held pin is not asked and is counted as held.

THE FIXTURE MAPS COVER EVERY SOURCE, READ FROM THE GATE'S OWN LIST. They used to name `bw` alone, written when the list held one entry. The list grew to five and the other four were "not in fixture", which the gate then reported as could-not-check and passed: every green case here was comparing one pin of five. The bases are now read by importing `DEVCONTAINER_PIN_SOURCES`, and `test_fixture_keys_are_corpus_derived` refuses an empty read.

THE VERSION-AND-HASHES PROPERTY MOVED WITH THE REWRITE. The gate's own `--upgrade` mode, which rewrote the version and its sha256 ARGs, is retired: `npm run pins -- bump devcontainer:<base>` does that rewrite now, and the devcontainer driver's selftest (scripts/lib/pins/drivers/devcontainer-selftest.ts) proves both halves this file used to: the version and both hashes move together, and a release missing one digest is refused whole. The gate only reads, and every case here hands it a COPY of the Dockerfile through `DEVCONTAINER_DOCKERFILE`, so even a regression that made it write could not touch the tracked file.

WHY THE ONE-HOUR TIMESTAMP IS COMPUTED HERE. The twin spells it `date -u -d '1 hour ago'` with a BSD `date -u -v-1H` fallback; the port uses
`datetime.now(UTC) - timedelta(hours=1)` and formats it with the same
`%Y-%m-%dT%H:%M:%SZ`. Same instant, same wire format, and no dependence on which `date` the host ships -- which is the exact portability trap `.ci/media/portable.sh` exists for elsewhere in this tree.

NO `xdist_group`. Every case owns its whole fixture set under `tmp_path` and the tracked Dockerfile is only ever READ; nothing is bound and no module global is mutated.
"""

import datetime
import json
import shutil

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

VALIDATOR = paths.from_root("scripts", "gates", "check-devcontainer-pin-freshness.ts")
REAL_DOCKERFILE = paths.from_root(".devcontainer", "Dockerfile")


SOURCES_FILE = paths.from_root("scripts", "lib", "devcontainer-pin-sources.ts")
LONG_AGO = "2020-01-01T00:00:00Z"

PROBE = (
    "import { DEVCONTAINER_PIN_SOURCES } from './scripts/lib/devcontainer-pin-sources.ts';\n"
    "process.stdout.write(JSON.stringify(DEVCONTAINER_PIN_SOURCES.map((s) => "
    "({ base: s.base, display: s.display, repo: s.repo, tagPrefix: s.tagPrefix }))));"
)

# The source list costs one tsx start-up, paid once per pytest process. A one-slot dict rather than a rebound module global, so no `global` statement is needed.
_SOURCES: dict[str, list[dict]] = {}


def sources(gate) -> list[dict]:
    """The gate's own source list: base, display, repo and tag prefix of each watched pin."""
    if "value" in _SOURCES:
        return _SOURCES["value"]
    for path in (VALIDATOR, SOURCES_FILE):
        if not path.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(path))
    npx = harness.require_tool(
        "npx", "install node; the source list is a TypeScript module read through tsx"
    )
    probe = harness.run([npx, "tsx", "--eval", PROBE], cwd=paths.repo_root())
    found: list[dict] = []
    if probe.rc == 0:
        try:
            found = list(json.loads(probe.out.strip().splitlines()[-1]))
        except (ValueError, IndexError):
            found = []
    if not found:
        gate.log_fail(
            "read ZERO source(s) out of %s (rc=%d, stdout=%r, stderr=%r), so every fixture "
            "below would be an EMPTY map. Either the list moved or DEVCONTAINER_PIN_SOURCES "
            "changed shape."
            % (paths.relative_to_root(SOURCES_FILE), probe.rc, probe.out, probe.err)
        )
    _SOURCES["value"] = found
    return found


def upstream_map(gate, **overrides: dict) -> dict:
    """Every watched source reported far OLDER than any real pin, then `overrides`."""
    data: dict[str, dict] = {src["base"]: {"version": "0.0.1"} for src in sources(gate)}
    data.update(overrides)
    return data


def write_map(directory, name: str, mapping: dict) -> None:
    (directory / name).write_text(json.dumps(mapping) + "\n", encoding="utf-8")


def build_fixtures(gate, directory):
    """Every fixture the cases read, into `directory`.

    Returns the path of the WRITABLE Dockerfile copy. The real one is read and never touched.
    """
    if not VALIDATOR.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(VALIDATOR))
    if not REAL_DOCKERFILE.is_file():
        gate.log_fail("the Dockerfile the gate pins is missing: %s" % REAL_DOCKERFILE)

    dockerfile = directory / "Dockerfile"
    shutil.copy2(REAL_DOCKERFILE, dockerfile)

    # Every source reported far OLDER than the real pin -> nothing is stale.
    write_map(directory, "all-current.json", upstream_map(gate))

    # bw reported far NEWER, published long ago -> confirmed stale (past the soak).
    stale_bw = {"version": "9999.1.0", "publishedAt": LONG_AGO}
    write_map(directory, "stale.json", upstream_map(gate, bw=stale_bw))

    # Newer but published just now -> inside the freshness window (deferred).
    recent = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    write_map(
        directory,
        "fresh.json",
        upstream_map(gate, bw={"version": "9999.1.0", "publishedAt": recent}),
    )

    # Empty fixture -> every source has no entry -> none was compared, which is RED.
    (directory / "empty.json").write_text("{}\n", encoding="utf-8")

    # A blocklist entry with NO BLOCKER reason -> verifyAllBlockers must reject it.
    (directory / "blocklist-bad").write_text("bw\n", encoding="utf-8")

    # And one WITH a substantive reason -> accepted, no error.
    (directory / "blocklist-good").write_text(
        "# BLOCKER: the next Bitwarden CLI dropped the native linux build we depend on; "
        "holding until it returns\nbw\n",
        encoding="utf-8",
    )
    return dockerfile


def run_gate(gate, directory, dockerfile, fixture: str, *args: str) -> harness.RunResult:
    """The gate with its fixture upstream map, streams MERGED as the twin captures them.

    THE FIXTURE REFUSAL IS LOAD-BEARING. `DEVCONTAINER_FRESHNESS_FIXTURE` pointing at a file that is not there does not make the gate fail -- it makes it fall back to the NETWORK, so a mistyped fixture name would turn an offline unit test into a live upstream query whose verdict depends on what Bitwarden released this week.
    """
    if not (directory / fixture).is_file():
        gate.log_fail(
            "the fixture %s was never written, so this case would have queried the real "
            "network instead of the map it names" % fixture
        )
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    # The cases do not read live policy: without this the gate reads the tracked blocklist, and a real hold (gopls, cddf1b670) turned "5 of 5 compared" into "4 of 5, 1 held".
    holds = directory / "blocklist-none"
    holds.write_text("# no holds; the cases do not read live policy\n", encoding="utf-8")
    return harness.run(
        [npx, "tsx", str(VALIDATOR), *args],
        cwd=paths.repo_root(),
        env={
            "DEVCONTAINER_FRESHNESS_FIXTURE": str(directory / fixture),
            "DEVCONTAINER_BLOCKLIST_FILE": str(holds),
            "DEVCONTAINER_DOCKERFILE": str(dockerfile),
        },
    )


def run_gate_blocklist(gate, directory, dockerfile, fixture: str, blocklist: str):
    """The gate with a fixture map AND a fixture blocklist, so the BLOCKER validation is exercised in isolation from the network.

    Both fixtures are refused when absent, for the reason `run_gate` gives about the upstream map, and for a second one about the blocklist: an absent `DEVCONTAINER_BLOCKLIST_FILE` reads as an EMPTY blocklist, which is indistinguishable from "every entry is well formed".
    """
    for name in (fixture, blocklist):
        if not (directory / name).is_file():
            gate.log_fail(
                "the fixture %s was never written; an absent blocklist reads as an empty "
                "one, and an absent map sends the gate to the network" % name
            )
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run(
        [npx, "tsx", str(VALIDATOR)],
        cwd=paths.repo_root(),
        env={
            "DEVCONTAINER_FRESHNESS_FIXTURE": str(directory / fixture),
            "DEVCONTAINER_BLOCKLIST_FILE": str(directory / blocklist),
            "DEVCONTAINER_DOCKERFILE": str(dockerfile),
        },
    )


def arg_value(text: str, name: str) -> str:
    """`grep -oP '^ARG <name>=\\K\\S+'`, reimplemented as a line scan.

    A scan rather than a regex because the twin's spelling needs `grep -P` here (`\\K` is a PCRE construct that `-E` does not have at all), and this repo's `grep -E` is ugrep, which returns SILENT FALSE ZEROS on some alternated-anchor
    patterns. Splitting on the first `=` of an anchored `ARG ` line is the same
    claim with nothing to get wrong.
    """
    prefix = "ARG %s=" % name
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].split()[0]
    return ""


def release(tag: str, published: str = LONG_AGO, **extra: object) -> dict:
    return {
        "tag_name": tag,
        "published_at": published,
        "draft": False,
        "prerelease": False,
        **extra,
    }


def route(src: dict) -> str:
    """The path the gate asks the stub for a source's release list."""
    return "/repos/%s/releases" % src["repo"]


def current_script(gate, dockerfile) -> dict[str, list[tuple]]:
    """A stub script in which every repository's newest release under the prefix IS the pinned version.

    Two sources can share a repository, so the listings are merged per path. The noise entry is a tag no prefix here selects.
    """
    text = dockerfile.read_text(encoding="utf-8")
    listings: dict[str, list[dict]] = {}
    for src in sources(gate):
        pinned = arg_value(text, "%s_VERSION" % src["base"].upper())
        if not pinned:
            gate.log_fail("the Dockerfile copy has no %s_VERSION ARG" % src["base"].upper())
        listings.setdefault(route(src), [release("unrelated-component-v9999.0.0")]).append(
            release(src["tagPrefix"] + pinned)
        )
    return {path: [ok(listing)] for path, listing in listings.items()}


def run_gate_over_http(dockerfile, base: str, *args: str, blocklist=None):
    """The gate against `base` over real HTTP: no fixture map, so the fetch, the status handling and the retry all run."""
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    holds = dockerfile.parent / "blocklist-none"
    holds.write_text("# no holds; the cases do not read live policy\n", encoding="utf-8")
    return harness.run(
        [npx, "tsx", str(VALIDATOR), *args],
        cwd=paths.repo_root(),
        env={
            "DEVCONTAINER_API_BASE": base,
            "DEVCONTAINER_FRESHNESS_FIXTURE": "",
            "DEVCONTAINER_BLOCKLIST_FILE": str(blocklist or holds),
            "DEVCONTAINER_DOCKERFILE": str(dockerfile),
            "GITHUB_TOKEN": sentinel(),
        },
    )


def by_base(gate, base: str) -> dict:
    return next(src for src in sources(gate) if src["base"] == base)


def test_fixture_keys_are_corpus_derived(gate):
    """Anti-vacuity: the fixture maps cover every source the gate has, and `bw`, which the stale cases drive, is one of them."""
    found = sources(gate)
    if "bw" not in [src["base"] for src in found]:
        gate.log_fail("the stale and fresh cases drive 'bw', which the subject no longer declares")
    gate.log_pass(
        "%d source(s) read out of the subject, bw among them: %s"
        % (len(found), ", ".join(src["base"] for src in found))
    )


def test_control_every_listing_served_over_http_is_green(gate, tmp_path):
    """The control for every red HTTP case below: the same stub, answering, is green."""
    dockerfile = build_fixtures(gate, tmp_path)
    count = len(sources(gate))
    with stub_upstream(current_script(gate, dockerfile)) as stub:
        result = run_gate_over_http(dockerfile, stub.base)
        gate.assert_exit(0, result, "every listing served over HTTP passes")
        gate.assert_contains(
            result.out,
            "%d of %d compared with upstream, 0 held" % (count, count),
            "the count of compared pins is printed",
        )
        gate.assert_eq(len(stub.requests), count, "one request per source reached the stub")
        gate.assert_eq(stub.tokens_seen(), 0, "the token is not sent to a seam")
    gate.log_pass("the stub upstream, answering, is green")


def test_a_stale_pin_over_http_still_fires(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    script = current_script(gate, dockerfile)
    bw = by_base(gate, "bw")
    script[route(bw)][0][2].insert(0, release(bw["tagPrefix"] + "9999.1.0"))
    with stub_upstream(script) as stub:
        result = run_gate_over_http(dockerfile, stub.base)
    gate.assert_exit(1, result, "a pin behind an aged release fails over HTTP too")
    gate.assert_contains(result.err, "upstream 9999.1.0", "the finding names the newer version")
    gate.assert_contains(
        result.err, "  fix: npm run pins -- bump devcontainer:bw\n", "the fix is printed"
    )
    gate.assert_not_contains(result.err, "NOT compared", "a stale pin is not a failed fetch")
    gate.log_pass("the HTTP path judges a listing the way the fixture path does")


def test_an_unreachable_upstream_is_red(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    count = len(sources(gate))
    bw = by_base(gate, "bw")
    pinned = arg_value(dockerfile.read_text(encoding="utf-8"), "BW_VERSION")
    port = closed_port()
    result = run_gate_over_http(dockerfile, "http://127.0.0.1:%d" % port)
    gate.assert_exit(1, result, "an upstream nothing answers on fails closed")
    gate.assert_contains(
        result.err,
        "%d devcontainer pin(s) were NOT compared with upstream" % count,
        "all are named",
    )
    gate.assert_contains(
        result.err,
        "%s (pinned %s): GET 127.0.0.1:%d%s -> network error ECONNREFUSED, after 3 attempt(s)"
        % (bw["display"], pinned, port, route(bw)),
        "the finding names the pin, the host and path, the error code and the attempts",
    )
    gate.assert_contains(
        result.err,
        "UPSTREAM REACHABILITY FAILURE (127.0.0.1:%d), not a stale pin" % port,
        "the finding says what kind of red this is and names the host",
    )
    gate.assert_contains(result.out, "attempt 2 of 3 failed", "the retries are visible")
    gate.assert_not_contains(result.out, "Every devcontainer pin", "no green line is printed")
    gate.assert_not_contains(result.err, "per_page", "the query string is not printed")
    assert_no_token(gate, result)
    gate.log_pass("an unreachable upstream is red after three attempts")


def test_a_rate_limit_is_red(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    script = current_script(gate, dockerfile)
    dlv = by_base(gate, "dlv")
    script[route(dlv)] = [RATE_LIMITED]
    with stub_upstream(script) as stub:
        result = run_gate_over_http(dockerfile, stub.base)
        gate.assert_eq(stub.asked(route(dlv)), 1, "a primary rate limit is not asked again")
    gate.assert_exit(1, result, "a rate limit fails closed")
    gate.assert_contains(result.err, "1 devcontainer pin(s) were NOT compared", "one finding")
    gate.assert_contains(
        result.err,
        "%s -> HTTP 403 (rate limit, resets 2026-10-" % route(dlv),
        "the finding names the path, the status and the reset",
    )
    gate.assert_contains(result.err, "after 1 attempt(s)", "the attempt count is printed")
    assert_no_token(gate, result)
    gate.log_pass("a rate limit is red at once")


def test_a_persistent_server_error_is_red(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    script = current_script(gate, dockerfile)
    dlv = by_base(gate, "dlv")
    script[route(dlv)] = [status(503)]
    with stub_upstream(script) as stub:
        result = run_gate_over_http(dockerfile, stub.base)
        gate.assert_eq(stub.asked(route(dlv)), 3, "a 5xx is asked three times and no more")
    gate.assert_exit(1, result, "a 5xx that outlasts the retry budget fails closed")
    gate.assert_contains(result.err, "-> HTTP 503, after 3 attempt(s)", "status and attempts")
    gate.log_pass("a persistent 5xx is red after the budget")


def test_a_transient_failure_then_success_is_green(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    script = current_script(gate, dockerfile)
    dlv = by_base(gate, "dlv")
    bw = by_base(gate, "bw")
    script[route(dlv)].insert(0, status(503))
    script[route(bw)].insert(0, (429, {"retry-after": "1"}, {}))
    count = len(sources(gate))
    with stub_upstream(script) as stub:
        result = run_gate_over_http(dockerfile, stub.base)
        gate.assert_eq(stub.asked(route(dlv)), 2, "the 503 is asked again once")
        gate.assert_eq(stub.asked(route(bw)), 2, "the 429 is asked again once")
    gate.assert_exit(0, result, "a failure that clears inside the retry budget passes")
    gate.assert_contains(result.out, "attempt 1 of 3 failed (HTTP 503)", "the retry is visible")
    gate.assert_contains(
        result.out, "%d of %d compared with upstream" % (count, count), "every pin was compared"
    )
    gate.log_pass("a transient failure followed by the listing is green")


def test_a_listing_without_the_tag_prefix_is_red(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    script = current_script(gate, dockerfile)
    dlv = by_base(gate, "dlv")
    script[route(dlv)] = [ok([release("renamed-scheme-1.0.0")])]
    with stub_upstream(script) as stub:
        result = run_gate_over_http(dockerfile, stub.base)
    gate.assert_exit(1, result, "a listing with no release under the prefix would pass forever")
    gate.assert_contains(result.err, "cannot use", "the error says the listing is unusable")
    gate.assert_contains(result.err, dlv["repo"], "the error names the repository")
    gate.assert_not_contains(
        result.err, "NOT compared", "an unusable answer is not a network failure"
    )
    gate.log_pass("a listing that lost the tag scheme is red")


def test_an_empty_release_list_is_not_compared_not_a_lost_tag_scheme(gate, tmp_path):
    """2026-10-22, during GitHub's Actions Results incident: four sources answered 200 with an empty list and the gate called it a lost tag scheme. An empty list is the API not answering, so it is the reachability class."""
    dockerfile = build_fixtures(gate, tmp_path)
    script = current_script(gate, dockerfile)
    dlv = by_base(gate, "dlv")
    script[route(dlv)] = [ok([])]
    with stub_upstream(script) as stub:
        result = run_gate_over_http(dockerfile, stub.base)
    gate.assert_exit(1, result, "an empty release list still fails closed")
    gate.assert_contains(
        result.err, "1 devcontainer pin(s) were NOT compared", "one not-compared finding"
    )
    gate.assert_contains(
        result.err, "HTTP 200 with an empty release list", "the finding names the empty answer"
    )
    gate.assert_contains(
        result.err, "UPSTREAM REACHABILITY FAILURE", "it is reported as reachability"
    )
    gate.assert_not_contains(result.err, "cannot use", "it is not the unusable-listing class")
    gate.log_pass("an empty release list is not compared, not a lost tag scheme")


def test_a_held_pin_is_not_asked_and_is_counted(gate, tmp_path):
    """A hold is an explicit, reasoned exemption, so a held pin is the one pin a green may leave uncompared, and the green line counts it."""
    dockerfile = build_fixtures(gate, tmp_path)
    script = current_script(gate, dockerfile)
    dlv = by_base(gate, "dlv")
    script[route(dlv)] = [status(503)]
    holds = tmp_path / "blocklist-dlv"
    holds.write_text(
        "# BLOCKER: the next Delve release drops the Go version this image builds with; "
        "holding until the image moves\ndlv\n",
        encoding="utf-8",
    )
    count = len(sources(gate))
    with stub_upstream(script) as stub:
        result = run_gate_over_http(dockerfile, stub.base, blocklist=holds)
        gate.assert_eq(stub.asked(route(dlv)), 0, "a held pin's upstream is not asked")
    gate.assert_exit(0, result, "a held pin whose upstream is down does not fail the gate")
    gate.assert_contains(
        result.out,
        "%d of %d compared with upstream, 1 held" % (count - 1, count),
        "counted as held",
    )
    gate.log_pass("a held pin is not asked, and the green line says one was held")


def test_a_source_with_no_arg_is_red(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    text = dockerfile.read_text(encoding="utf-8")
    kept = [
        line for line in text.splitlines(keepends=True) if not line.startswith("ARG DLV_VERSION=")
    ]
    gate.assert_eq(len(text.splitlines()) - len(kept), 1, "exactly one ARG line was removed")
    dockerfile.write_text("".join(kept), encoding="utf-8")
    result = run_gate(gate, tmp_path, dockerfile, "all-current.json")
    gate.assert_exit(1, result, "a watched tool with no pin was not compared, which is not a pass")
    gate.assert_contains(result.err, "no DLV_VERSION ARG in the Dockerfile", "the ARG is named")
    gate.assert_not_contains(result.out, "Every devcontainer pin", "no green line is printed")
    gate.log_pass("a source with no ARG is red")


def test_passes_when_current(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate(gate, tmp_path, dockerfile, "all-current.json")
    gate.assert_exit(0, result, "nothing behind upstream should pass")
    count = len(sources(gate))
    gate.assert_contains(
        result.out, "%d of %d compared with upstream" % (count, count), "every pin was compared"
    )
    gate.log_pass("current pins pass")


def test_fires_when_stale(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate(gate, tmp_path, dockerfile, "stale.json")
    gate.assert_exit(1, result, "a pin behind upstream should fail")
    gate.assert_contains(result.combined, "Bitwarden CLI", "error names the stale component")
    gate.assert_contains(
        result.err, "  fix: npm run pins -- bump devcontainer:bw\n", "red output gives the pins fix"
    )
    gate.log_pass("stale pin fires")


def test_defers_fresh_release(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate(gate, tmp_path, dockerfile, "fresh.json")
    gate.assert_exit(0, result, "a just-released upstream version should be deferred, not failed")
    gate.assert_contains(
        result.combined, "deferred", "fresh release is reported as deferred (soak)"
    )
    gate.log_pass("fresh release is deferred by the soak")


def test_a_source_absent_from_the_fixture_is_red(gate, tmp_path):
    """Was `test_fails_soft_when_uncheckable`, which asserted exit 0 here. A source with no upstream answer was not compared, and that is not a pass."""
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate(gate, tmp_path, dockerfile, "empty.json")
    gate.assert_exit(1, result, "sources that were not compared fail the gate")
    gate.assert_contains(
        result.err,
        "%d devcontainer pin(s) were NOT compared with upstream" % len(sources(gate)),
        "every source is a finding",
    )
    gate.assert_contains(result.err, "Bitwarden CLI (pinned ", "the finding names the pin")
    gate.assert_not_contains(result.out, "Every devcontainer pin", "no green line is printed")
    gate.log_pass("a source that was not compared is red")


def test_blocklist_rejects_missing_reason(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate_blocklist(gate, tmp_path, dockerfile, "all-current.json", "blocklist-bad")
    gate.assert_exit(1, result, "a blocklist entry lacking a BLOCKER reason must fail the gate")
    gate.assert_contains(result.combined, "invalid entries", "error names the malformed blocklist")
    gate.log_pass("blocklist entry without a BLOCKER reason fires")


def test_blocklist_accepts_valid_reason(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate_blocklist(gate, tmp_path, dockerfile, "all-current.json", "blocklist-good")
    gate.assert_exit(
        0, result, "a blocklist entry with a substantive BLOCKER reason must be accepted"
    )
    gate.log_pass("well-formed blocklist entry is accepted")


def test_pins_driver_selftest_holds_the_version_and_hash_properties_upgrade_proved(gate):
    """The retired `--upgrade` cases (the version and both sha256 ARGs moving together, and a release missing one digest refused) live in the devcontainer pins driver's selftest, which no other gate runs. Running it here keeps them proved: it must exit 0 and print a PASS line for each."""
    npx = harness.require_tool(
        "npx", "install node; the selftest is a TypeScript program driven through tsx"
    )
    result = harness.run(
        [npx, "tsx", "scripts/lib/pins/drivers/devcontainer-selftest.ts"], cwd=paths.repo_root()
    )
    gate.assert_exit(0, result, "the devcontainer pins driver selftest must pass")
    for line in (
        "bw: the version and both sha256 ARGs move together, by the asset filenames the registry names",
        "bw: a release with no digest for one hashed asset is refused, not moved with a stale hash",
    ):
        gate.assert_contains(result.out, "PASS  " + line, "the selftest proves: " + line)
    gate.log_pass("the devcontainer driver selftest proves the retired upgrade properties")


GOPLS_MODULE = "golang.org/x/tools/gopls"


def run_gate_gomod(gate, directory, dockerfile, upstream: dict, gomods: dict, go: str = "1.26.5"):
    """The gate over an upstream map and a go.mod map (`DEVCONTAINER_GOMOD_FIXTURE`), for the `go install`ed pins (worklist #e023eb0d).

    Under a release fixture the gate reads go.mod files from this map only, never the network, so a key it lacks is a go.mod that was not obtained.
    """
    if "gopls" not in [src["base"] for src in sources(gate)]:
        gate.log_fail("the go.mod cases drive 'gopls', which the subject no longer declares")
    write_map(directory, "gomod-upstream.json", upstream_map(gate, **upstream))
    write_map(directory, "gomods.json", gomods)
    holds = directory / "blocklist-none"
    holds.write_text("# no holds; the cases do not read live policy\n", encoding="utf-8")
    # The image's Go is the fixture's too, not the live .devcontainer/toolchain.env (review dcd54c44.3): a Go bump must not change what these cases mean.
    toolchain = directory / "toolchain.env"
    toolchain.write_text("GO_VERSION=%s\n" % go, encoding="utf-8")
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run(
        [npx, "tsx", str(VALIDATOR)],
        cwd=paths.repo_root(),
        env={
            "DEVCONTAINER_FRESHNESS_FIXTURE": str(directory / "gomod-upstream.json"),
            "DEVCONTAINER_GOMOD_FIXTURE": str(directory / "gomods.json"),
            "DEVCONTAINER_TOOLCHAIN_ENV": str(toolchain),
            "DEVCONTAINER_BLOCKLIST_FILE": str(holds),
            "DEVCONTAINER_DOCKERFILE": str(dockerfile),
        },
    )


def gomod(go: str) -> str:
    return "module %s\n\ngo %s\n" % (GOPLS_MODULE, go)


def test_a_release_needing_a_newer_go_defers_to_the_buildable_one(gate, tmp_path):
    """gopls 999.0.0 needs go 1.999.0, newer than the image's Go: it is printed as deferred, naming the Go it needs, and the pin is judged against 998.0.0, whose go.mod builds, so the pin is behind THAT one. Without the go.mod judgement the finding would name 999.0.0."""
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate_gomod(
        gate,
        tmp_path,
        dockerfile,
        {
            "gopls": {
                "version": "999.0.0",
                "publishedAt": LONG_AGO,
                "older": [{"version": "998.0.0", "publishedAt": LONG_AGO}],
            }
        },
        {
            "%s@999.0.0" % GOPLS_MODULE: gomod("1.999.0"),
            "%s@998.0.0" % GOPLS_MODULE: gomod("1.20.0"),
        },
    )
    gate.assert_exit(1, result, "the pin is behind the newest release the image can build")
    gate.assert_contains(result.err, "upstream 998.0.0", "the finding names the buildable release")
    gate.assert_not_contains(result.err, "upstream 999.0.0", "not the one that needs a newer Go")
    gate.assert_contains(result.out, "999.0.0 deferred", "the unbuildable release is deferred")
    gate.assert_contains(result.out, "needs go 1.999.0", "the deferral names the Go it needs")
    gate.log_pass("a release needing a newer Go is deferred and the newest buildable one is judged")


def test_every_newer_release_needing_a_newer_go_is_not_behind(gate, tmp_path):
    """The 2026-10-18 shape: the only newer gopls needs a newer Go than the image (0.24.0, go 1.27.0, on a 1.26.x Go). The pin is deferred, not behind, so the gate is green. This is the control that goes red without the go.mod judgement: the gate would call gopls behind 999.0.0 and exit 1."""
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate_gomod(
        gate,
        tmp_path,
        dockerfile,
        {"gopls": {"version": "999.0.0", "publishedAt": LONG_AGO}},
        {"%s@999.0.0" % GOPLS_MODULE: gomod("1.999.0")},
    )
    gate.assert_exit(0, result, "a pin whose every newer release needs a newer Go is not behind")
    gate.assert_contains(result.out, "needs go 1.999.0", "the deferral names the Go it needs")
    gate.assert_not_contains(result.err, "behind upstream", "the pin is not called behind")
    gate.log_pass("a pin whose newer releases all need a newer Go is deferred")


def test_control_the_same_release_is_behind_once_the_image_has_its_go(gate, tmp_path):
    """CONTROL for the case above: the identical upstream and go.mod on an image whose Go meets the directive make gopls behind, so that case's green comes from the go.mod judgement and from nothing else."""
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate_gomod(
        gate,
        tmp_path,
        dockerfile,
        {"gopls": {"version": "999.0.0", "publishedAt": LONG_AGO}},
        {"%s@999.0.0" % GOPLS_MODULE: gomod("1.999.0")},
        go="9.999.0",
    )
    gate.assert_exit(1, result, "a release the image's Go can build makes the pin behind")
    gate.assert_contains(result.err, "behind upstream", "the pin is called behind")
    gate.log_pass("the same release is behind on an image with a new enough Go")


def test_a_go_mod_that_was_not_obtained_is_red(gate, tmp_path):
    """FAIL CLOSED: a newer gopls whose go.mod was not obtained is not eligible and not deferred; the pin was not compared, which is red."""
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate_gomod(
        gate,
        tmp_path,
        dockerfile,
        {"gopls": {"version": "999.0.0", "publishedAt": LONG_AGO}},
        {},
    )
    gate.assert_exit(1, result, "a go.mod that was not obtained fails the gate")
    gate.assert_contains(result.err, "NOT compared", "the pin is reported as not compared")
    gate.assert_contains(result.err, "gopls", "the finding names the pin")
    gate.assert_not_contains(result.out, "Every devcontainer pin", "no green line is printed")
    gate.log_pass("a go.mod that was not obtained is red")
