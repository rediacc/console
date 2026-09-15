"""`rediacc_ci.deploy.verify_edge_endpoints` against its bash twin.

NO NETWORK, EVER, AND THAT IS THE WHOLE DESIGN PROBLEM THIS FILE SOLVES. The
twin's eleven URLs are hard-coded production hostnames -- `edge.rediacc.com`,
`releases.rediacc.com` and the three per-region account endpoints out of
`regions.json` -- with no override knob anywhere. So the subject cannot be
pointed at a local stub the way `wait_for_preview_worker` can be. What CAN be
done is replace the CLIENT: a recording fake `curl` goes first on `PATH`, logs
its exact argv to a file, and answers from a fixture directory. Both
implementations are driven through the SAME fake, and every case compares four
things:

  1. the exit code,
  2. stdout, byte for byte,
  3. stderr, byte for byte,
  4. the fake's CALL LOG, byte for byte.

THE CALL LOG IS THE ASSERTION THAT MATTERS MOST, and it is the one a
stdout-only differential would miss. A port that fetched the right URLs in the
wrong ORDER, or dropped `-f` from one fetch, or stopped suppressing a stderr,
would still print the same eleven OK lines on a healthy fixture. Comparing the
argv sequence is what makes the happy-path case evidence rather than
decoration.

`cb=<digits>` IS THE ONE THING NORMALISED IN THE LOG. The twin busts the cache
with `$RANDOM$RANDOM` and the port with `secrets.randbelow` twice; neither can
be made to agree with the other and neither is supposed to. Only the digits
after `cb=` are masked, so a port that dropped the cache-buster entirely, or
put it on the wrong URL, still fails.

THREE REAL DEFECTS IN THE TWIN ARE PINNED HERE RATHER THAN FIXED. Fixing a twin
belongs to a later cutover box, and a test that quietly tolerated them would
let the next port "correct" one and diverge. They are FINDING 1 (a missing
`regions.json` checks zero regions and still passes) and FINDING 2 (a non-200
region reports `HTTP 404000`).

FINDING 3 IS THE ONE PLACE THE PORT IS DELIBERATELY NOT FAITHFUL, and it has
its own case below with the mechanism spelled out: a fractional
`EDGE_RETRY_SLEEP` makes the twin report `Smoke test passed` and exit 0 on a
deployment that failed. Reproducing a silent pass in a second language is not
a port, so the port answers correctly and this file asserts the DIVERGENCE
rather than pretending it away.

K=5 LEDGER: `.ci/shadow/w7p6-verify-edge-endpoints.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.core import bash_dialect
from rediacc_ci.deploy import verify_edge_endpoints as port
from rediacc_ci.tests import differential as diff

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "verify-edge-endpoints.sh"
STABLE_TWIN = ROOT / ".ci" / "scripts" / "deploy" / "verify-stable-endpoints.sh"
COMMON_LIB = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "verify_edge_endpoints.py"
REGIONS = ROOT / "regions.json"

# The recording fake. `$*` rather than a per-argument encoding because that is
# what a reader compares by eye when a case fails, and no argument here contains
# a space. A per-slug counter file lets a fixture answer DIFFERENTLY on the
# second attempt, which is the only way to exercise `fetch_retry`'s agree-late
# branch without a real eventually-consistent CDN.
FAKE_CURL = r"""#!/bin/bash
printf 'curl %s\n' "$*" >>"$FAKE_LOG"
url="${!#}"
base="${url%%\?*}"
slug="$(printf '%s' "$base" | sed -e 's|^https\?://||' -e 's|[^A-Za-z0-9._-]|_|g')"
d="$FAKE_DIR"
n=$(( $(cat "$d/$slug.n" 2>/dev/null || echo 0) + 1 ))
printf '%s' "$n" > "$d/$slug.n"
pick() {
    [[ -f "$d/$slug.$1@$n" ]] && { printf '%s' "$d/$slug.$1@$n"; return 0; }
    [[ -f "$d/$slug.$1" ]] && { printf '%s' "$d/$slug.$1"; return 0; }
    return 1
}
case "$1" in
    -fsSL)
        if f="$(pick body)"; then
            cat "$f"
            exit 0
        fi
        printf 'curl: (22) The requested URL returned error: 404\n' >&2
        exit 22
        ;;
    -sI)
        if [[ $# -eq 2 ]]; then
            f="$(pick hdr)" && cat "$f"
            exit 0
        fi
        if f="$(pick code)"; then code="$(cat "$f")"; else code=000; fi
        printf '%s' "$code"
        [[ "$code" == "000" ]] && exit 7
        exit 0
        ;;
    -sf)
        if f="$(pick code)"; then code="$(cat "$f")"; else code=000; fi
        printf '%s' "$code"
        case "$code" in
            2*) exit 0 ;;
            000) exit 7 ;;
            *) exit 22 ;;
        esac
        ;;
esac
exit 99
"""

HEALTHY_HEADERS = (
    "HTTP/2 200\r\nstrict-transport-security: max-age=63072000\r\n"
    "x-content-type-options: nosniff\r\n\r\n"
)

# The twin's retry budget is 6 attempts, 5 seconds apart: 25 seconds per failing
# assertion. Two attempts with no sleep keeps the retry LOOP exercised (the
# give-up message names the attempt count) while the whole file stays under a
# second. `0` and not `0.01`: see FINDING 3.
BUDGET = {"EDGE_RETRIES": "2", "EDGE_RETRY_SLEEP": "0"}


def slug_for(url: str) -> str:
    """The fake's fixture key: scheme and query stripped, non-word bytes to `_`."""
    base = url.split("?", 1)[0]
    base = re.sub(r"^https?://", "", base)
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)


def region_domains(field: str = "edgeDomain") -> list[str]:
    """Read `regions.json` the same way the subject does, so the fixture cannot
    go stale when a region is added."""
    proc = subprocess.run(
        ["jq", "-r", ".regions[] | .%s" % field, str(REGIONS)],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in proc.stdout.split("\n") if line]


def make_bin(tmp_path: pathlib.Path) -> pathlib.Path:
    """The fake-`curl` directory, to be put FIRST on PATH."""
    binary_dir = tmp_path / "fxbin"
    binary_dir.mkdir(exist_ok=True)
    fake = binary_dir / "curl"
    fake.write_text(FAKE_CURL, encoding="utf-8")
    fake.chmod(0o755)
    return binary_dir


def healthy_fixture(target: pathlib.Path, version: str = "1.2.3") -> None:
    """A fixture set on which every one of the twin's assertions passes."""
    target.mkdir(parents=True, exist_ok=True)
    write = {
        "edge.rediacc.com/install.sh": ("body", 'REDIACC_CHANNEL="${REDIACC_CHANNEL:-edge}"\n'),
        "edge.rediacc.com/install.ps1": ("body", '$Channel = if ($e) { $e } else { "edge" }\n'),
        "edge.rediacc.com/about": ("code", "410"),
        "edge.rediacc.com/en": ("code", "200"),
        "edge.rediacc.com/fonts/inter/Inter-Regular.woff2": ("code", "200"),
        "edge.rediacc.com/en/": (
            "body",
            '<html><p class="footer-version">v<!-- -->%s</p></html>\n' % version,
        ),
        "releases.rediacc.com/cli/edge/install.sh": (
            "body",
            'REDIACC_CHANNEL="${REDIACC_CHANNEL:-edge}"\n',
        ),
        "releases.rediacc.com/cli/edge/install.ps1": ("body", '} else { "edge" }\n'),
        "releases.rediacc.com/cli/edge/latest.json": ("body", '{"version":"%s"}\n' % version),
    }
    for url, (ext, text) in write.items():
        (target / ("%s.%s" % (slug_for(url), ext))).write_text(text, encoding="utf-8")
    for domain in region_domains():
        key = slug_for("%s/account/api/v1/.well-known/server-info" % domain)
        (target / ("%s.code" % key)).write_text("200", encoding="utf-8")
        (target / ("%s.hdr" % key)).write_text(HEALTHY_HEADERS, encoding="utf-8")


def normalise_log(text: str) -> str:
    """Mask ONLY the cache-buster digits. See the module docstring."""
    return re.sub(r"cb=\d+", "cb=N", text)


class Run:
    """One side's four observable outputs."""

    def __init__(self, rc: int, out: str, err: str, log: str) -> None:
        self.rc = rc
        self.out = out
        self.err = err
        self.log = normalise_log(log)


def drive(
    tmp_path: pathlib.Path,
    *,
    mutate=None,
    env_extra: dict[str, str] | None = None,
    tree: pathlib.Path | None = None,
    port_file: pathlib.Path | None = None,
    twin: pathlib.Path | None = None,
    module: str = "rediacc_ci.deploy.verify_edge_endpoints",
    fixture=healthy_fixture,
) -> tuple[Run, Run]:
    """Run BOTH implementations against their own copy of the same fixture set.

    EACH SIDE GETS ITS OWN FIXTURE DIRECTORY because the fake writes per-slug
    counter files into it; sharing one would make whichever side ran second see
    a different sequence of answers, which is a test artifact rather than a
    divergence.
    """
    binary_dir = make_bin(tmp_path)
    runs: list[Run] = []
    for side in ("old", "new"):
        fixture_dir = tmp_path / ("fx-%s" % side)
        if fixture_dir.exists():
            shutil.rmtree(fixture_dir)
        fixture(fixture_dir)
        if mutate is not None:
            mutate(fixture_dir)
        log = tmp_path / ("log-%s" % side)
        log.write_text("", encoding="utf-8")
        env = diff.env_for(
            PATH="%s:%s" % (binary_dir, os.environ.get("PATH", "")),
            FAKE_DIR=str(fixture_dir),
            FAKE_LOG=str(log),
            **{**BUDGET, **(env_extra or {})},
        )
        if side == "old":
            script = twin or TWIN
            if tree is not None:
                script = tree / ".ci" / "scripts" / "deploy" / script.name
            command = "bash %s" % script
        else:
            env["PYTHONPATH"] = str(ROOT / ".ci")
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            if tree is not None:
                env["REDIACC_CI_ROOT"] = str(tree)
            target = port_file
            command = "python3 %s" % target if target is not None else "python3 -m %s" % module
        rc, out, err = diff.bash_streams(command, env=env, timeout=60)
        runs.append(Run(rc, out, err, log.read_text(encoding="utf-8")))
    return runs[0], runs[1]


def assert_same(old: Run, new: Run) -> None:
    assert new.rc == old.rc, "exit: twin %s, port %s" % (old.rc, new.rc)
    assert new.out == old.out
    assert new.err == old.err
    assert new.log == old.log, "the two sides did not make the same curl calls"


def fixture_tree(tmp_path: pathlib.Path, *, with_regions: bool) -> pathlib.Path:
    """A `.ci` skeleton both sides resolve their repo root inside.

    The twin resolves it from `${BASH_SOURCE[0]}` so it is COPIED here; the port
    resolves it through `paths.repo_root()`, whose documented single override is
    `$REDIACC_CI_ROOT`. Both then read (or fail to read) the same
    `regions.json`.
    """
    tree = tmp_path / "tree"
    (tree / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (tree / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, tree / ".ci" / "scripts" / "deploy" / TWIN.name)
    shutil.copy2(STABLE_TWIN, tree / ".ci" / "scripts" / "deploy" / STABLE_TWIN.name)
    shutil.copy2(COMMON_LIB, tree / ".ci" / "scripts" / "lib" / COMMON_LIB.name)
    if with_regions:
        shutil.copy2(REGIONS, tree / "regions.json")
    return tree


# ---------------------------------------------------------------------------
# The happy path, and the proof that it is not vacuous
# ---------------------------------------------------------------------------


def test_healthy_deployment_agrees_byte_for_byte(tmp_path: pathlib.Path) -> None:
    old, new = drive(tmp_path, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 0, old.err
    assert old.out.endswith("Smoke test passed\n")
    # Anti-vacuity: a green run must have SAID something, and the region loop in
    # particular must have run for every region in regions.json.
    for domain in region_domains():
        assert "  %s health: OK (security headers verified)" % domain in old.out
    assert old.log.count("curl ") == 9 + 2 * len(region_domains()), old.log
    assert_same(old, new)


def test_workers_only_skips_every_version_dependent_assertion(tmp_path: pathlib.Path) -> None:
    old, new = drive(tmp_path, env_extra={"VERSION": "1.2.3", "WORKERS_ONLY": "true"})
    assert old.rc == 0
    assert "  R2 backstop: skipped (workers-only deployment)" in old.out
    assert "  R2 version check: skipped (workers-only)" in old.out
    assert "footer version" not in old.out
    assert_same(old, new)


# ---------------------------------------------------------------------------
# Every documented failure mode
# ---------------------------------------------------------------------------


def _put(directory: pathlib.Path, url: str, ext: str, text: str) -> None:
    (directory / ("%s.%s" % (slug_for(url), ext))).write_text(text, encoding="utf-8")


def test_install_sh_baked_to_the_wrong_channel(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "edge.rediacc.com/install.sh", "body", 'REDIACC_CHANNEL="${X:-stable}"\n')

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert "::error::edge.rediacc.com/install.sh is not baked to channel=edge" in old.out
    # The diagnostic grep must print the offending line, not just the header.
    assert 'REDIACC_CHANNEL="${X:-stable}"' in old.out
    assert "  install.sh channel: still disagreeing after 2 attempts" in old.err
    assert_same(old, new)


def test_install_sh_that_404s_leaves_the_diagnostic_grep_empty(tmp_path: pathlib.Path) -> None:
    """`INSTALL_SH=$(curl ...) || return 1` still ASSIGNS, so the error path
    greps an empty body rather than a stale one. A port that skipped the
    assignment on failure would print the previous attempt's body."""

    def mutate(d: pathlib.Path) -> None:
        (d / ("%s.body" % slug_for("edge.rediacc.com/install.sh"))).unlink()

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert old.out.rstrip("\n").endswith(
        "::error::edge.rediacc.com/install.sh is not baked to channel=edge"
    )
    assert_same(old, new)


def test_install_ps1_baked_to_the_wrong_channel(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(
            d,
            "edge.rediacc.com/install.ps1",
            "body",
            '} else { "stable" }\n$Channel = 1\n',
        )

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert "::error::edge.rediacc.com/install.ps1 is not baked to channel=edge" in old.out
    assert "$Channel = 1" in old.out
    assert_same(old, new)


def test_a_stale_worker_bundle_fails_the_redirect_table_fingerprint(
    tmp_path: pathlib.Path,
) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "edge.rediacc.com/about", "code", "200")

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    # The em dash is the twin's own byte, and the port emits it from an escape.
    # The escape, not the character: the twin emits a literal U+2014 here and this
    # assertion must match that byte, but a literal em dash in authored source is
    # banned house-wide.
    assert "got 200 \u2014 old worker bundle likely live" in old.out
    assert_same(old, new)


def test_a_transport_failure_on_a_fingerprint_probe_is_a_000(tmp_path: pathlib.Path) -> None:
    """Inside `fetch_retry` the predicate runs in an `if`, so `set -e` is
    SUSPENDED and curl's non-zero status becomes a retryable "000" rather than
    an abort. The stable twin, whose identical probe is at top level, exits 7
    instead; that asymmetry is asserted in the stable differential."""

    def mutate(d: pathlib.Path) -> None:
        _put(d, "edge.rediacc.com/en", "code", "000")

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert "got 000" in old.out
    assert_same(old, new)


def test_asset_path_guard_fingerprint(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "edge.rediacc.com/fonts/inter/Inter-Regular.woff2", "code", "404")

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert "::error::edge mixed-case font expected 200 (asset-path guard), got 404" in old.out
    assert_same(old, new)


def test_footer_diagnostic_prints_at_most_three_matches(tmp_path: pathlib.Path) -> None:
    """`grep -oE ... | head -3`. FOUR candidates are planted, one of them the
    SECOND match on its own line, so a port that iterated lines instead of
    matches would print a different set."""

    def mutate(d: pathlib.Path) -> None:
        _put(
            d,
            "edge.rediacc.com/en/",
            "body",
            '<p class="footer-version">v<!-- -->9.9.9</p>\n'
            '<p class="footer-version">v<!-- -->8.8.8</p>'
            '<span class="footer-version x">v<!-- -->7.7.7</span>\n'
            '<p class="footer-version">v<!-- -->6.6.6</p>\n',
        )

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert "::error::edge.rediacc.com footer does not render v1.2.3" in old.out
    assert old.out.count("footer-version") == 3, old.out
    assert "6.6.6" not in old.out, "head -3 must have truncated the fourth"
    assert "7.7.7" in old.out, "the second match on line two must be reached"
    assert_same(old, new)


def test_the_html_comment_stripper_is_load_bearing(tmp_path: pathlib.Path) -> None:
    """Astro SSR inserts `<!-- -->` between the `v` and the semver. Without the
    `sed` both sides must FAIL; with it both must pass. Asserting only the
    passing direction would leave a port that dropped the sed looking correct."""

    def mutate(d: pathlib.Path) -> None:
        _put(
            d,
            "edge.rediacc.com/en/",
            "body",
            '<p class="footer-version">v<!--x--><!--y-->1.2.3</p>\n',
        )

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 0, "two consecutive comments must still collapse"
    assert "  marketing (footer version): OK (v1.2.3)" in old.out
    assert_same(old, new)


def test_r2_backstop_not_rebaked(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "releases.rediacc.com/cli/edge/install.sh", "body", "REDIACC_CHANNEL=stable\n")

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert "::error::releases.rediacc.com/cli/edge/install.sh not baked to channel=edge" in old.out
    assert_same(old, new)


def test_r2_ps1_backstop_not_rebaked(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "releases.rediacc.com/cli/edge/install.ps1", "body", '} else { "stable" }\n')

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert "::error::releases.rediacc.com/cli/edge/install.ps1 not baked to channel=edge" in old.out
    assert_same(old, new)


def test_latest_json_absent_empty_and_malformed_all_read_as_unreadable(
    tmp_path: pathlib.Path,
) -> None:
    """`jq -re '.version'` answers with THREE different exit codes here (4 on
    empty input, 1 on a JSON `null`, 5 on a parse error) and the twin folds all
    three into one message. Each is driven; the parse-error case also proves
    jq's stderr reaches the log unredirected on both sides."""
    for body in (None, "{}\n", "not json at all\n"):

        def mutate(d: pathlib.Path, body: str | None = body) -> None:
            key = slug_for("releases.rediacc.com/cli/edge/latest.json")
            if body is None:
                (d / ("%s.body" % key)).unlink()
            else:
                (d / ("%s.body" % key)).write_text(body, encoding="utf-8")

        old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
        assert old.rc == 1
        assert "::error::releases.rediacc.com/cli/edge/latest.json is not readable" in old.out
        assert_same(old, new)
    assert "jq: parse error" in new.err, "the malformed case must leak jq's own diagnostic"


def test_a_version_mismatch_is_tolerated_not_failed(tmp_path: pathlib.Path) -> None:
    """The retry-mode carve-out. A port that treated this as an error would fail
    every legitimate re-run of the smoke test, and the happy path would not
    notice."""

    def mutate(d: pathlib.Path) -> None:
        _put(d, "releases.rediacc.com/cli/edge/latest.json", "body", '{"version":"9.9.9"}\n')

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 0
    assert (
        "  version mismatch: edge has v9.9.9, expected v1.2.3 (acceptable in retry mode)" in old.out
    )
    assert_same(old, new)


# ---------------------------------------------------------------------------
# The retry loop, in both directions
# ---------------------------------------------------------------------------


def test_a_surface_that_agrees_on_the_second_attempt_passes(tmp_path: pathlib.Path) -> None:
    """The 2026-08-08 incident in miniature: one unlucky sample must not fail a
    healthy deploy."""

    def mutate(d: pathlib.Path) -> None:
        _put(d, "edge.rediacc.com/about", "code@1", "500")

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3", "EDGE_RETRIES": "3"})
    assert old.rc == 0
    assert "  about 410: agreed on attempt 2/3" in old.out
    assert_same(old, new)


def test_the_retry_budget_is_load_bearing(tmp_path: pathlib.Path) -> None:
    """Anti-vacuity for the case above: with the budget cut to ONE attempt the
    same fixture must FAIL on both sides, or "agreed on attempt 2" proved
    nothing about retrying."""

    def mutate(d: pathlib.Path) -> None:
        _put(d, "edge.rediacc.com/about", "code@1", "500")

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3", "EDGE_RETRIES": "1"})
    assert old.rc == 1
    assert "  about 410: still disagreeing after 1 attempts over 0s of waiting" in old.err
    assert_same(old, new)


def test_a_fractional_retry_sleep_makes_the_twin_pass_without_running(
    tmp_path: pathlib.Path,
) -> None:
    """FINDING 3, REPRODUCED AND DELIBERATELY NOT MATCHED.

    THE MECHANISM, driven down to a 25-line minimal case rather than reasoned
    about. `fetch_retry`'s give-up branch is

        echo "  ${what}: still disagreeing after ... over \
             $(((EDGE_RETRIES - 1) * EDGE_RETRY_SLEEP))s of waiting" >&2
        return 1

    and bash arithmetic has no floats. With `EDGE_RETRY_SLEEP=0.01` the
    expansion raises `arithmetic syntax error`, which aborts the FUNCTION
    before its `return 1` ever runs. Every one of the six call sites invokes
    `fetch_retry` under `||` or `if !`, and in that context bash suppresses the
    exit-on-expansion-error and hands the caller status 0. So `fetch_retry`
    reports SUCCESS for a check that just failed on every attempt, the caller
    prints its `OK` line, and the run ends `Smoke test passed`, exit 0.

    That is a gate that is green because it did not run, and it is the exact
    class this whole differential exists to catch, so the port does NOT
    reproduce it: it renders the number with `float` and refuses correctly.
    The assertion below is therefore an inequality, and it is the only one in
    this file.
    """

    def mutate(d: pathlib.Path) -> None:
        _put(d, "edge.rediacc.com/about", "code", "200")

    old, new = drive(
        tmp_path,
        mutate=mutate,
        env_extra={"VERSION": "1.2.3", "EDGE_RETRY_SLEEP": "0.01"},
    )
    assert old.rc == 0, "the twin PASSES a deployment whose /about returned 200"
    assert old.out.endswith("Smoke test passed\n")
    assert "  worker fingerprint (redirect table): OK (/about=410)" in old.out
    # Asked of the running bash: 5.3 says "arithmetic syntax error", 5.2 says
    # "syntax error", and CI is 5.2 while every host here is 5.3.
    assert bash_dialect.arith_syntax_error() in old.err
    assert "::error::" not in old.out, "and it never says a word about the failure"

    assert new.rc == 1, "the port refuses, which is the whole point of not being faithful"
    assert "::error::edge /about expected 410" in new.out
    assert "  about 410: still disagreeing after 2 attempts over 0.01s of waiting" in new.err


def test_an_integer_retry_sleep_is_still_byte_identical(tmp_path: pathlib.Path) -> None:
    """The control for the case above, and the reason the divergence is narrow.

    Every integer `EDGE_RETRY_SLEEP` -- including the production default of 5 --
    must still render exactly as bash arithmetic renders it, with no decimal
    point. Without this, "the port answers correctly" would be cover for a
    reworded message on the path that actually runs in CI.
    """

    def mutate(d: pathlib.Path) -> None:
        _put(d, "edge.rediacc.com/about", "code", "200")

    for retries, sleep_s, expect in (("2", "0", "0"), ("3", "1", "2"), ("2", "5", "5")):
        old, new = drive(
            tmp_path,
            mutate=mutate,
            env_extra={
                "VERSION": "1.2.3",
                "EDGE_RETRIES": retries,
                "EDGE_RETRY_SLEEP": sleep_s,
            },
        )
        assert old.rc == 1
        assert "over %ss of waiting" % expect in old.err, (retries, sleep_s)
        assert "." not in old.err.split("over ")[1].split("s of waiting")[0]
        assert_same(old, new)


# ---------------------------------------------------------------------------
# Region health, including the two defects it carries
# ---------------------------------------------------------------------------


def test_a_non_200_region_fails_the_run_and_reports_finding_2(tmp_path: pathlib.Path) -> None:
    """FINDING 2, REPRODUCED NOT FIXED. `HTTP_CODE=$(curl -sf -w '%{http_code}'
    ... || echo "000")` puts BOTH outputs inside the substitution, so a real 404
    is reported as `HTTP 404000`. Driven against the live script; a reader of a
    CI log sees a status code that does not exist."""
    domain = region_domains()[1]

    def mutate(d: pathlib.Path) -> None:
        _put(d, "%s/account/api/v1/.well-known/server-info" % domain, "code", "404")

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert "::error::%s health check failed (HTTP 404000)" % domain in old.out
    assert "HTTP 404)" not in old.out, "if this ever passes the twin was fixed; update FINDING 2"
    assert_same(old, new)


def test_an_unreachable_region_reports_http_000000(tmp_path: pathlib.Path) -> None:
    domain = region_domains()[0]

    def mutate(d: pathlib.Path) -> None:
        _put(d, "%s/account/api/v1/.well-known/server-info" % domain, "code", "000")

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert "::error::%s health check failed (HTTP 000000)" % domain in old.out
    assert_same(old, new)


def test_hsts_without_nosniff_is_a_finding(tmp_path: pathlib.Path) -> None:
    """The header gate activates the moment HSTS appears. Case is mixed on
    purpose: both greps are `-i`."""
    domain = region_domains()[2]

    def mutate(d: pathlib.Path) -> None:
        _put(
            d,
            "%s/account/api/v1/.well-known/server-info" % domain,
            "hdr",
            "HTTP/2 200\r\nSTRICT-TRANSPORT-SECURITY: max-age=1\r\n\r\n",
        )

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert "::error::%s has HSTS but missing X-Content-Type-Options: nosniff" % domain in old.out
    assert_same(old, new)


def test_no_hsts_yet_still_passes(tmp_path: pathlib.Path) -> None:
    """The pre-Phase-1 no-op branch. Without this the gate above could be a port
    that simply always fires."""
    domain = region_domains()[2]

    def mutate(d: pathlib.Path) -> None:
        _put(
            d,
            "%s/account/api/v1/.well-known/server-info" % domain,
            "hdr",
            "HTTP/2 200\r\ncontent-type: application/json\r\n\r\n",
        )

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 0
    assert "  %s health: OK (security headers not yet enabled)" % domain in old.out
    assert_same(old, new)


def test_nosniff_with_no_space_after_the_colon_still_matches(tmp_path: pathlib.Path) -> None:
    """`grep -qi '^x-content-type-options: *nosniff'` is ` *`, ZERO or more. A
    port that transcribed it as one-or-more would flag a compliant region."""
    domain = region_domains()[0]

    def mutate(d: pathlib.Path) -> None:
        _put(
            d,
            "%s/account/api/v1/.well-known/server-info" % domain,
            "hdr",
            "HTTP/2 200\r\nStrict-Transport-Security: max-age=1\r\n"
            "X-Content-Type-Options:nosniff\r\n\r\n",
        )

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 0
    assert "  %s health: OK (security headers verified)" % domain in old.out
    assert_same(old, new)


def test_every_failing_region_is_reported_not_just_the_first(tmp_path: pathlib.Path) -> None:
    """`FAILED=1; continue` rather than an early exit. A port that returned on
    the first bad region would hide the other two."""
    domains = region_domains()

    def mutate(d: pathlib.Path) -> None:
        for domain in domains:
            _put(d, "%s/account/api/v1/.well-known/server-info" % domain, "code", "503")

    old, new = drive(tmp_path, mutate=mutate, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 1
    assert old.out.count("health check failed (HTTP 503000)") == len(domains)
    assert_same(old, new)


# ---------------------------------------------------------------------------
# FINDING 1: the vacuity hole, on a fixture tree
# ---------------------------------------------------------------------------


def test_a_missing_regions_json_checks_zero_regions_and_still_passes(
    tmp_path: pathlib.Path,
) -> None:
    """FINDING 1, REPRODUCED NOT FIXED.

    `done < <(jq -r ... regions.json)` is a PROCESS SUBSTITUTION, whose exit
    status the loop never sees and `set -e` never inspects. With `regions.json`
    absent, jq writes one line to stderr, the loop body runs zero times, and the
    smoke test prints `Smoke test passed` and exits 0 having verified no region
    at all. That is the exact shape of a gate that is green because it did not
    run.
    """
    tree = fixture_tree(tmp_path, with_regions=False)
    old, new = drive(tmp_path, tree=tree, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 0
    assert old.out.endswith("Smoke test passed\n")
    assert "jq: error: Could not open file regions.json" in old.err
    assert "health: OK" not in old.out, "zero regions were checked"
    assert_same(old, new)


def test_the_same_tree_with_regions_json_present_does_check_them(
    tmp_path: pathlib.Path,
) -> None:
    """The control for the case above: the fixture tree is not the reason the
    regions vanished."""
    tree = fixture_tree(tmp_path, with_regions=True)
    old, new = drive(tmp_path, tree=tree, env_extra={"VERSION": "1.2.3"})
    assert old.rc == 0
    assert old.out.count("health: OK") == len(region_domains())
    assert_same(old, new)


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------


def test_version_unset_refuses_on_both_sides_reworded(tmp_path: pathlib.Path) -> None:
    """Exit code and the named variable agree; the wording does not, and is not
    supposed to (the twin's carries bash's own `line 87:` prefix). This is the
    ONLY path in the script where the bytes are allowed to differ, which is why
    it is asserted narrowly here rather than through `assert_same`."""
    old, new = drive(tmp_path, env_extra={"VERSION": None})
    assert old.rc == 1
    assert new.rc == 1
    assert "VERSION" in old.err
    assert "VERSION must be set" in old.err
    assert new.err == "verify-edge-endpoints.py: VERSION must be set\n"
    assert old.out == ""
    assert new.out == ""
    assert old.log == "", "neither side may reach the network without a VERSION"
    assert new.log == ""


def test_a_missing_curl_refuses_identically(tmp_path: pathlib.Path) -> None:
    """`require_cmd curl`. The message and the exit code are `common.sh`'s, and
    `rediacc_ci.core.common.require_cmd` is the ported same."""
    lean = tmp_path / "leanbin"
    lean.mkdir()
    # `uname` and `dirname` are common.sh's own needs; omitting them turns this
    # case into a test of the fixture rather than of `require_cmd`.
    for tool in ("bash", "jq", "sed", "cat", "env", "python3", "tr", "grep", "dirname", "uname"):
        found = shutil.which(tool)
        if found:
            (lean / tool).symlink_to(found)
    env = diff.env_for(PATH=str(lean), VERSION="1.2.3", **BUDGET)
    old = diff.bash_streams("bash %s" % TWIN, env=env, timeout=30)
    env_new = dict(env)
    env_new["PYTHONPATH"] = str(ROOT / ".ci")
    env_new["PYTHONDONTWRITEBYTECODE"] = "1"
    new = diff.bash_streams(
        "python3 -m rediacc_ci.deploy.verify_edge_endpoints", env=env_new, timeout=30
    )
    assert old[0] == 1
    assert new[0] == 1
    assert old[2] == "✗ Required command 'curl' is not available\n"
    assert new[2] == old[2]
    assert old[1] == new[1] == ""


# ---------------------------------------------------------------------------
# Pure helpers, exercised directly
# ---------------------------------------------------------------------------


def test_substitute_strips_every_trailing_newline() -> None:
    assert port.substitute("a\n\n\n") == "a"
    assert port.substitute("") == ""
    assert port.substitute("\n") == ""
    assert port.substitute("a\nb") == "a\nb"


def test_lines_matches_what_echo_pipe_grep_sees() -> None:
    assert port.lines("") == [""]
    assert port.lines("a") == ["a"]
    assert port.lines("a\nb") == ["a", "b"]


def test_lines_agrees_with_the_real_shell() -> None:
    """Not asserted from reading bash's manual: bash is RUN and counted."""
    for value in ("", "a", "a\nb", "a\n\nb"):
        proc = subprocess.run(
            ["bash", "-c", 'echo "$1" | grep -c ""', "_", value],
            capture_output=True,
            text=True,
            check=False,
        )
        assert int(proc.stdout.strip()) == len(port.lines(value)), repr(value)


def test_fetch_retry_returns_on_the_first_success() -> None:
    calls = []

    def predicate() -> bool:
        calls.append(1)
        return True

    assert port.fetch_retry("x", predicate, 6, "0") is True
    assert len(calls) == 1


def test_fetch_retry_exhausts_the_budget_exactly_once_per_attempt() -> None:
    calls = []

    def predicate() -> bool:
        calls.append(1)
        return False

    assert port.fetch_retry("x", predicate, 4, "0") is False
    assert len(calls) == 4, "N attempts means N predicate calls, not N+1"


# ---------------------------------------------------------------------------
# The control: a planted defect must turn this suite red
# ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_differential(tmp_path: pathlib.Path) -> None:
    """Drop the HTML-comment stripper from a COPY of the port.

    That `sed` is invisible on every failing run and on every run against a
    non-Astro body; the only thing it changes is whether a HEALTHY deploy is
    recognised. A port without it agrees with the twin on eight of the eleven
    assertions and disagrees exactly where the twin's own header says the
    subtlety lives.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    anchor = 'comment = re.compile(r"<!--[^>]*-->")'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken = tmp_path / "verify_edge_endpoints_broken.py"
    broken.write_text(
        source.replace(anchor, 'comment = re.compile(r"NEVERMATCHES")'), encoding="utf-8"
    )

    old, new = drive(tmp_path, env_extra={"VERSION": "1.2.3"}, port_file=broken)
    assert old.rc == 0, "the twin must still pass the healthy fixture"
    assert new.rc != old.rc or new.out != old.out, (
        "PLANT DID NOT FIRE: this differential is vacuous"
    )
    # And the real port still agrees against the same fixture.
    good_old, good_new = drive(tmp_path, env_extra={"VERSION": "1.2.3"})
    assert_same(good_old, good_new)


def test_a_port_that_forgot_the_cache_buster_is_caught_by_the_call_log(
    tmp_path: pathlib.Path,
) -> None:
    """The second control, aimed at the assertion nothing else covers.

    Dropping `?cb=` changes NO stdout byte and NO exit code on any fixture: the
    fake answers the same either way. Only the recorded argv differs, which is
    the whole reason the call log is compared.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    anchor = 'about = probe("%s/about?cb=%s" % (EDGE, rnda), "410")'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken = tmp_path / "verify_edge_endpoints_nocb.py"
    broken.write_text(
        source.replace(anchor, 'about = probe("%s/about" % EDGE, "410")'), encoding="utf-8"
    )

    old, new = drive(tmp_path, env_extra={"VERSION": "1.2.3"}, port_file=broken)
    assert old.rc == new.rc == 0, "the defect is invisible to the exit code"
    assert old.out == new.out, "and invisible to stdout, which is the point"
    assert new.log != old.log, "PLANT DID NOT FIRE: the call log is not being compared"
