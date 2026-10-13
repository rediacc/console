"""`scripts/gates/check-real-provider-pin-freshness.ts`, driven through its two seams so it runs offline:

  REAL_PROVIDER_LOCK_FILE          the lock file whose pins are judged
  REAL_PROVIDER_FRESHNESS_FIXTURE  a JSON map of `owner/repo` to the release list as the GitHub API returns it,
                                   read INSTEAD of the network

The fixture is the upstream listing itself, not a pre-digested "latest version", so the tag-prefix filter, the draft and pre-release filter and the version ordering are all under test.

Proved, control first: a pin equal to upstream's newest release passes; a newer release past the release-age window FIRES and the message carries the pin, the new version, its publish date and the bump command; a newer release inside the window passes with a note; the newest ELIGIBLE release is the finding when a still newer one is inside the window; drafts, pre-releases, beta tags and another component's tags are not releases of this pin; an upstream that cannot be reached is soft; a listing that answers and cannot be used is RED; an unreadable lock file is RED.

Every case owns its fixtures under `tmp_path`; the tracked lock file is read by one case and never written.
"""

import datetime
import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

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
        "npm run real-provider:bump -- --bitwarden 2026.10.0",
        "the finding gives the bump command with the version filled in",
    )
    gate.assert_not_contains(
        result.err, "--vaultwarden", "a current pin is not in the bump command"
    )
    gate.log_pass("a stale pin fires with the pin, the release, its date and the bump command")


def test_both_pins_behind_share_one_bump_command(gate, tmp_path):
    listing = current_listing()
    listing[BITWARDEN].insert(0, release("browser-v2026.10.0"))
    listing[VAULTWARDEN].insert(0, release("1.38.0"))
    result = run_gate(gate, tmp_path, listing)
    gate.assert_exit(1, result, "two pins behind fail")
    gate.assert_contains(
        result.err,
        "npm run real-provider:bump -- --bitwarden 2026.10.0 --vaultwarden 1.38.0",
        "one command bumps both",
    )
    gate.log_pass("two stale pins are bumped by one command")


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
    gate.assert_contains(result.err, "--bitwarden 2026.10.0", "the bump targets the aged release")
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


def test_fails_soft_when_upstream_cannot_be_reached(gate, tmp_path):
    listing = current_listing()
    del listing[VAULTWARDEN]
    result = run_gate(gate, tmp_path, listing)
    gate.assert_exit(0, result, "an upstream that did not answer must not fail the build")
    gate.assert_contains(
        result.out, "Vaultwarden: could not check", "the run says what it could not check"
    )
    gate.log_pass("an unreachable upstream is reported and soft")


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
