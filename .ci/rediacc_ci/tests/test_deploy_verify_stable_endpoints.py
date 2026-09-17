"""`rediacc_ci.deploy.verify_stable_endpoints` against its bash twin.

THE FAKE `curl` AND THE FOUR-WAY COMPARISON ARE THE EDGE DIFFERENTIAL'S, imported rather than copied: `test_deploy_verify_edge_endpoints` owns the recording fake, the fixture-directory convention and `assert_same`, and the two subjects are close enough that a second copy would drift. The reason both are shelled out to `curl` at all is in `verify_edge_endpoints`'s module docstring:
hard-coded production hostnames, no override knob, so the CLIENT is what gets replaced.

WHAT THIS FILE HAS TO PROVE THAT THE EDGE ONE DOES NOT, because the two scripts read almost identically and differ in exactly the places a careless port would smooth over:

  * NO RETRY. Every assertion samples once. `test_a_single_bad_sample_fails`
    plants a surface that recovers on the second attempt and requires BOTH sides
    to fail anyway, which is the direct opposite of the edge case with the same
    fixture.
  * REGION HEALTH ONLY WARNS. `::warning::`, exit still 0.
  * `.domain`, NOT `.edgeDomain`. One jq field, and getting it wrong would probe
    three real production hosts that are not the ones intended.
  * FINDING 4: `set -e` IS OBSERVABLE HERE. Every fetch is a TOP-LEVEL
    `VAR=$(curl ...)`, so a transport failure kills the script with curl's own
    exit code and NO `::error::` annotation. The edge twin cannot do this,
    because its identical probes sit inside `fetch_retry` predicates where
    `set -e` is suspended.

K=5 LEDGER: `.ci/shadow/w7p6-verify-stable-endpoints.observations.jsonl`.
"""

from __future__ import annotations

import shutil
import typing

from rediacc_ci import paths
from rediacc_ci.tests import test_deploy_verify_edge_endpoints as edgediff
from rediacc_ci.tests.test_deploy_verify_edge_endpoints import (
    assert_same,
    region_domains,
    slug_for,
)

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "verify-stable-endpoints.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "verify_stable_endpoints.py"
MODULE = "rediacc_ci.deploy.verify_stable_endpoints"

HEALTHY_HEADERS = edgediff.HEALTHY_HEADERS


def healthy_fixture(target: pathlib.Path) -> None:
    """A fixture set on which every one of the stable twin's assertions passes."""
    target.mkdir(parents=True, exist_ok=True)
    write = {
        "www.rediacc.com/install.sh": ("body", 'REDIACC_CHANNEL="${REDIACC_CHANNEL:-stable}"\n'),
        "www.rediacc.com/install.ps1": ("body", '$Channel = if ($e) { $e } else { "stable" }\n'),
        "www.rediacc.com/about": ("code", "410"),
        "www.rediacc.com/en": ("code", "200"),
        "www.rediacc.com/fonts/inter/Inter-Regular.woff2": ("code", "200"),
        "releases.rediacc.com/cli/stable/install.sh": (
            "body",
            'REDIACC_CHANNEL="${REDIACC_CHANNEL:-stable}"\n',
        ),
        "releases.rediacc.com/cli/stable/install.ps1": ("body", '} else { "stable" }\n'),
    }
    for url, (ext, text) in write.items():
        (target / ("%s.%s" % (slug_for(url), ext))).write_text(text, encoding="utf-8")
    for domain in region_domains("domain"):
        key = slug_for("%s/account/api/v1/.well-known/server-info" % domain)
        (target / ("%s.code" % key)).write_text("200", encoding="utf-8")
        (target / ("%s.hdr" % key)).write_text(HEALTHY_HEADERS, encoding="utf-8")


def drive(tmp_path: pathlib.Path, **kwargs):
    """The edge harness, pointed at the stable pair and the stable fixtures."""
    kwargs.setdefault("twin", TWIN)
    kwargs.setdefault("module", MODULE)
    kwargs.setdefault("fixture", healthy_fixture)
    return edgediff.drive(tmp_path, **kwargs)


def _put(directory: pathlib.Path, url: str, ext: str, text: str) -> None:
    (directory / ("%s.%s" % (slug_for(url), ext))).write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- The happy path, and the proof that it is not vacuous ---------------------------------------------------------------------------


def test_healthy_deployment_agrees_byte_for_byte(tmp_path: pathlib.Path) -> None:
    old, new = drive(tmp_path)
    assert old.rc == 0, old.err
    assert old.out.endswith("Stable verification complete\n")
    for domain in region_domains("domain"):
        assert "  %s health: OK (security headers verified)" % domain in old.out
    # 7 fixed fetches (2 marketing bodies, 3 fingerprints, 2 R2 bodies) plus two per region. There is NO footer fetch and NO latest.json fetch here; the edge twin has both, and a port that copied them in would be caught by this number alone.
    assert old.log.count("curl ") == 7 + 2 * len(region_domains("domain")), old.log
    assert "latest.json" not in old.log
    assert "footer" not in old.out
    assert_same(old, new)


def test_the_region_field_is_domain_not_edgedomain(tmp_path: pathlib.Path) -> None:
    """One jq field is the entire difference between this loop and the edge
    twin's, and getting it wrong would silently probe the WRONG production
    hosts while still printing three OK lines."""
    old, new = drive(tmp_path)
    assert old.rc == 0
    for domain in region_domains("domain"):
        assert "https://%s/account" % domain in old.log
    for edge_domain in region_domains("edgeDomain"):
        assert edge_domain not in old.log, "the stable script must not probe edge hosts"
    assert_same(old, new)


# --------------------------------------------------------------------------- The channel-bake assertions ---------------------------------------------------------------------------


def test_install_sh_baked_to_the_wrong_channel(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "www.rediacc.com/install.sh", "body", 'REDIACC_CHANNEL="${X:-edge}"\n')

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 1
    assert "::error::www.rediacc.com/install.sh is not baked to channel=stable" in old.out
    assert 'REDIACC_CHANNEL="${X:-edge}"' in old.out
    assert_same(old, new)


def test_install_ps1_baked_to_the_wrong_channel(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "www.rediacc.com/install.ps1", "body", '} else { "edge" }\n$Channel = 1\n')

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 1
    assert "::error::www.rediacc.com/install.ps1 is not baked to channel=stable" in old.out
    assert "$Channel = 1" in old.out
    assert_same(old, new)


def test_r2_backstop_not_rebaked_to_stable(tmp_path: pathlib.Path) -> None:
    """The re-bake in `promote-r2-to-stable.sh` rewrites `:-edge` to `:-stable`.
    This is the assertion that proves it landed."""

    def mutate(d: pathlib.Path) -> None:
        _put(
            d,
            "releases.rediacc.com/cli/stable/install.sh",
            "body",
            'REDIACC_CHANNEL="${REDIACC_CHANNEL:-edge}"\n',
        )

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 1
    assert (
        "::error::releases.rediacc.com/cli/stable/install.sh not baked to channel=stable" in old.out
    )
    assert_same(old, new)


def test_r2_ps1_backstop_not_rebaked_to_stable(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "releases.rediacc.com/cli/stable/install.ps1", "body", '} else { "edge" }\n')

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 1
    assert (
        "::error::releases.rediacc.com/cli/stable/install.ps1 not baked to channel=stable"
        in old.out
    )
    assert_same(old, new)


# --------------------------------------------------------------------------- Worker fingerprints ---------------------------------------------------------------------------


def test_redirect_table_fingerprint(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "www.rediacc.com/about", "code", "200")

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 1
    # The escape, not the character; see the edge differential.
    assert "got 200 \u2014 old worker bundle likely live" in old.out
    assert_same(old, new)


def test_html_handling_fingerprint(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "www.rediacc.com/en", "code", "307")

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 1
    assert "::error::www /en expected 200 (html_handling=drop-trailing-slash), got 307" in old.out
    assert_same(old, new)


def test_asset_path_guard_fingerprint(tmp_path: pathlib.Path) -> None:
    def mutate(d: pathlib.Path) -> None:
        _put(d, "www.rediacc.com/fonts/inter/Inter-Regular.woff2", "code", "404")

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 1
    assert "::error::www mixed-case font expected 200 (asset-path guard), got 404" in old.out
    assert_same(old, new)


# --------------------------------------------------------------------------- FINDING 4: `set -e` on a top-level command substitution ---------------------------------------------------------------------------


def test_a_404_on_install_sh_exits_22_with_no_annotation(tmp_path: pathlib.Path) -> None:
    """FINDING 4, REPRODUCED NOT FIXED.

    `INSTALL_SH=$(curl -fsSL https://www.rediacc.com/install.sh)` is a top-level
    assignment under `set -e`. When curl's `-f` turns a 404 into exit 22, the script dies THERE: the `::error::www.rediacc.com/install.sh is not baked to
    channel=stable` branch two lines below is never reached, so the CI job shows
    a bare non-zero step with curl's own one-line diagnostic and no annotation. The exit code is 22, which nothing in the pipeline maps to anything.
    """

    def mutate(d: pathlib.Path) -> None:
        (d / ("%s.body" % slug_for("www.rediacc.com/install.sh"))).unlink()

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 22, "curl's own status, not 1"
    assert old.out == "Verifying stable deployment...\n"
    assert "::error::" not in old.out, "the annotation branch is never reached"
    assert old.err == "curl: (22) The requested URL returned error: 404\n"
    assert_same(old, new)


def test_a_transport_failure_on_a_fingerprint_probe_exits_7(tmp_path: pathlib.Path) -> None:
    """The same defect on the `-sI` probes, and the sharpest contrast with the
    edge twin: the identical fixture there yields `got 000` plus a real `::error::` and exit 1, because the probe runs inside a `fetch_retry`
    predicate where `set -e` is suspended."""

    def mutate(d: pathlib.Path) -> None:
        _put(d, "www.rediacc.com/en", "code", "000")

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 7
    assert "::error::" not in old.out
    assert_same(old, new)


# --------------------------------------------------------------------------- No retry, which is the other structural difference ---------------------------------------------------------------------------


def test_a_single_bad_sample_fails_here_though_it_would_retry_on_edge(
    tmp_path: pathlib.Path,
) -> None:
    """The SAME fixture the edge differential uses to prove retrying works.
    Here it must FAIL, on both sides. A port that copied `fetch_retry` across
    would pass this and nothing else in the file would notice."""

    def mutate(d: pathlib.Path) -> None:
        _put(d, "www.rediacc.com/about", "code@1", "500")

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 1
    assert "got 500" in old.out
    assert old.log.count("www.rediacc.com/about") == 1, "exactly one sample, no retry"
    assert_same(old, new)


# --------------------------------------------------------------------------- Region health: WARN only ---------------------------------------------------------------------------


def test_a_slow_region_warns_and_the_run_still_passes(tmp_path: pathlib.Path) -> None:
    """The deliberate asymmetry with the edge twin, which reds on the same
    condition. Promotion has already happened by this point."""
    domain = region_domains("domain")[1]

    def mutate(d: pathlib.Path) -> None:
        _put(d, "%s/account/api/v1/.well-known/server-info" % domain, "code", "503")

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 0, "a slow region must not red a completed promotion"
    # FINDING 2 again, in the warn-only twin: `503000`, not `503`.
    assert "::warning::%s health check returned HTTP 503000" % domain in old.out
    assert "::error::" not in old.out
    assert old.out.endswith("Stable verification complete\n")
    assert_same(old, new)


def test_hsts_without_nosniff_only_warns(tmp_path: pathlib.Path) -> None:
    domain = region_domains("domain")[2]

    def mutate(d: pathlib.Path) -> None:
        _put(
            d,
            "%s/account/api/v1/.well-known/server-info" % domain,
            "hdr",
            "HTTP/2 200\r\nSTRICT-TRANSPORT-SECURITY: max-age=1\r\n\r\n",
        )

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 0
    assert "::warning::%s has HSTS but missing X-Content-Type-Options" % domain in old.out
    assert "nosniff" not in old.out, "the stable wording omits the header VALUE"
    assert_same(old, new)


def test_no_hsts_yet_still_passes(tmp_path: pathlib.Path) -> None:
    domain = region_domains("domain")[0]

    def mutate(d: pathlib.Path) -> None:
        _put(
            d,
            "%s/account/api/v1/.well-known/server-info" % domain,
            "hdr",
            "HTTP/2 200\r\ncontent-type: application/json\r\n\r\n",
        )

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 0
    assert "  %s health: OK (security headers not yet enabled)" % domain in old.out
    assert_same(old, new)


def test_every_region_is_still_probed_after_one_warns(tmp_path: pathlib.Path) -> None:
    """`continue`, not a break. A port that stopped at the first bad region
    would still exit 0, so only the per-region output can catch it."""
    domains = region_domains("domain")

    def mutate(d: pathlib.Path) -> None:
        _put(d, "%s/account/api/v1/.well-known/server-info" % domains[0], "code", "500")

    old, new = drive(tmp_path, mutate=mutate)
    assert old.rc == 0
    assert "::warning::%s" % domains[0] in old.out
    for domain in domains[1:]:
        assert "  %s health: OK" % domain in old.out
    assert_same(old, new)


# --------------------------------------------------------------------------- FINDING 1 again: the vacuity hole is in this twin too ---------------------------------------------------------------------------


def test_a_missing_regions_json_warns_about_nothing_and_passes(
    tmp_path: pathlib.Path,
) -> None:
    """FINDING 1, second instance. The process-substitution loop sees zero
    domains, `Stable verification complete` prints, exit 0. Here it is even quieter than in the edge twin, because region health only warns anyway: nothing about the output distinguishes "three healthy regions" from "no
    regions were looked at"."""
    tree = edgediff.fixture_tree(tmp_path, with_regions=False)
    old, new = drive(tmp_path, tree=tree)
    assert old.rc == 0
    assert old.out.endswith("Stable verification complete\n")
    assert "jq: error: Could not open file regions.json" in old.err
    assert "health: OK" not in old.out
    assert_same(old, new)


def test_the_same_tree_with_regions_json_present_does_check_them(
    tmp_path: pathlib.Path,
) -> None:
    tree = edgediff.fixture_tree(tmp_path, with_regions=True)
    old, new = drive(tmp_path, tree=tree)
    assert old.rc == 0
    assert old.out.count("health: OK") == len(region_domains("domain"))
    assert_same(old, new)


# --------------------------------------------------------------------------- Preconditions ---------------------------------------------------------------------------


def test_a_missing_curl_refuses_identically(tmp_path: pathlib.Path) -> None:
    from rediacc_ci.tests import differential as diff  # noqa: PLC0415

    lean = tmp_path / "leanbin"
    lean.mkdir()
    for tool in ("bash", "jq", "sed", "cat", "env", "python3", "tr", "grep", "dirname", "uname"):
        found = shutil.which(tool)
        if found:
            (lean / tool).symlink_to(found)
    env = diff.env_for(PATH=str(lean))
    old = diff.bash_streams("bash %s" % TWIN, env=env, timeout=30)
    env_new = dict(env)
    env_new["PYTHONPATH"] = str(ROOT / ".ci")
    env_new["PYTHONDONTWRITEBYTECODE"] = "1"
    new = diff.bash_streams("python3 -m %s" % MODULE, env=env_new, timeout=30)
    assert old[0] == 1
    assert new[0] == 1
    assert old[2] == "✗ Required command 'curl' is not available\n"
    assert new[2] == old[2]
    assert old[1] == new[1] == ""


def test_the_script_takes_no_environment_input(tmp_path: pathlib.Path) -> None:
    """The twin's header says "Takes no env input". Setting the edge twin's
    whole knob set must change nothing, or the two ports share state they
    should not."""
    plain_old, plain_new = drive(tmp_path)
    noisy_old, noisy_new = drive(
        tmp_path,
        env_extra={"VERSION": "9.9.9", "WORKERS_ONLY": "true", "EDGE_RETRIES": "1"},
    )
    assert noisy_old.out == plain_old.out
    assert noisy_new.out == plain_new.out
    assert_same(noisy_old, noisy_new)


# --------------------------------------------------------------------------- The control: a planted defect must turn this suite red ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_differential(tmp_path: pathlib.Path) -> None:
    """Swap `.domain` for `.edgeDomain` in a COPY of the port.

    This is the single most dangerous one-character-class error available here: the run still exits 0, still prints three `health: OK` lines, and the only trace is WHICH hosts were contacted. On a real run it would report the edge fleet's health as the stable fleet's.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    anchor = 'edge.jq_run(["-r", ".regions[] | .domain", "regions.json"])'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken = tmp_path / "verify_stable_endpoints_broken.py"
    broken.write_text(
        source.replace(anchor, 'edge.jq_run(["-r", ".regions[] | .edgeDomain", "regions.json"])'),
        encoding="utf-8",
    )

    old, new = drive(tmp_path, port_file=broken)
    assert old.rc == 0, "the twin still passes"
    assert new.rc == 0, "and so does the broken port, which is exactly the danger"
    assert new.out != old.out or new.log != old.log, (
        "PLANT DID NOT FIRE: this differential is vacuous"
    )
    good_old, good_new = drive(tmp_path)
    assert_same(good_old, good_new)


def test_a_port_that_retried_would_be_caught(tmp_path: pathlib.Path) -> None:
    """The second control, aimed at the structural difference from the edge
    twin. A port that reused `fetch_retry` here passes every healthy fixture."""
    source = PORT_FILE.read_text(encoding="utf-8")
    anchor = '    status = _status_or_die("%s/about?cb=%s" % (WWW, rnda))\n    if status != "410":'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken = tmp_path / "verify_stable_endpoints_retry.py"
    broken.write_text(
        source.replace(
            anchor,
            '    status = _status_or_die("%s/about?cb=%s" % (WWW, rnda))\n'
            '    if status != "410":\n'
            '        status = _status_or_die("%s/about?cb=%s" % (WWW, rnda))\n'
            '    if status != "410":',
        ),
        encoding="utf-8",
    )

    def mutate(d: pathlib.Path) -> None:
        _put(d, "www.rediacc.com/about", "code@1", "500")

    old, new = drive(tmp_path, mutate=mutate, port_file=broken)
    assert old.rc == 1, "the twin must fail on the first bad sample"
    assert new.rc != old.rc, "PLANT DID NOT FIRE: the no-retry property is not being checked"
