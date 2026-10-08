"""Port of `.ci/scripts/test/gates/test-installmethods-manifest.sh`, retired in W7 P5.

`Runner.test_update_check()` in `rediacc_ci.testrun.install_methods` (written against the bash `test_update_check()` of `test-install-methods.sh`, retired behind its golden, PLAN-retire-bash-oracles B3).

WHY THIS EXISTS. The update-manifest check fetched the channel's manifest.json, PRINTED its version, and never compared it:

    manifest_ver=$(echo "$manifest" | jq -r '.version')
    log_info "  Manifest version: $manifest_ver"     # last mention

`$VERSION` did not appear anywhere in the function, so a channel still advertising the previous release looked exactly like a correctly published one. Two more silent passes sat underneath it: the structural guard
`jq -e '.version, .binaries'` accepts `"binaries": {}` because an empty object is
TRUTHY in jq, and the reachability check read the URL with `// empty` and, finding none, skipped itself and returned 0 -- so a manifest naming no binary at all passed twice over.

All three are now failures. Each is asserted against the CURRENT code and against a re-creation of the OLD code, because a negative case only means something if the previous implementation really did admit it.

NOTHING TOUCHES THE NETWORK: the runner's `fetch` and `head_ok` are replaced on the instance, so the manifest text and the reachability answer are the fixture's. The port needs no `jq`.

ARGUMENT ORDER. The retired bash gate called `assert_eq "0" "$(check ...)"`, EXPECTED first, inverting `assert_eq`'s contract. Same verdict, inverted diagnostic; the port uses the contract's order.
"""

import json

from rediacc_ci.testrun import install_methods as port

GOOD = (
    '{"version":"1.2.17","binaries":{"linux-x64":'
    '{"url":"https://x.invalid/rdc-linux-x64","sha256":"deadbeef"}}}'
)
STALE = (
    '{"version":"1.2.16","binaries":{"linux-x64":'
    '{"url":"https://x.invalid/rdc-linux-x64","sha256":"deadbeef"}}}'
)
NO_BINARIES = '{"version":"1.2.17","binaries":{}}'
OTHER_ARCH = (
    '{"version":"1.2.17","binaries":{"mac-arm64":{"url":"https://x.invalid/rdc-mac-arm64"}}}'
)
NO_VERSION = '{"version":"","binaries":{"linux-x64":{"url":"https://x.invalid/rdc-linux-x64"}}}'


def old_update_check(manifest: str, head_ok: bool = True) -> str:
    """The implementation as it stood before this change, for the red proof, as the bash function behaved (its exit code, as a string).

    `jq -e '.version, .binaries'` accepted anything whose LAST output was neither null nor false, so `{}` passed; the version was printed and never compared; the binary URL was read with `// empty` and, when empty, the reachability check skipped itself.
    """
    data = json.loads(manifest)
    if data.get("binaries") in (None, False):
        return "1"
    linux = data["binaries"].get("linux-x64") or {}
    url = linux.get("url") or ""
    if url and not head_ok:
        return "1"
    return "0"


class Fixture:
    def __init__(self, gate, monkeypatch) -> None:
        self.gate = gate
        self.monkeypatch = monkeypatch

    def check(
        self,
        manifest: str,
        version: str,
        *,
        head_ok: bool = True,
        fetch_fails: bool = False,
        channel: str = "edge",
    ) -> str:
        """The CURRENT function's exit code, as a string."""
        runner = port.Runner(
            port.Config(
                version=version, repo_channel=channel, releases="https://releases.example.invalid"
            )
        )

        def fetch(_url: str, _quiet: bool = False) -> str | None:
            return None if fetch_fails else manifest

        def reachable(_url: str) -> bool:
            return head_ok

        self.monkeypatch.setattr(runner, "fetch", fetch)
        self.monkeypatch.setattr(runner, "head_ok", reachable)
        return str(runner.test_update_check())

    def old_check(self, manifest: str) -> str:
        """The PRE-FIX function's exit code, as a string."""
        return old_update_check(manifest)


def test_a_correct_manifest_passes(gate, capsys, monkeypatch):
    fx = Fixture(gate, monkeypatch)
    gate.assert_eq(
        fx.check(GOOD, "1.2.17"), "0", "a manifest matching the expected version must pass"
    )
    capsys.readouterr()
    gate.log_pass("a correctly published manifest passes")


def test_a_stale_manifest_version_fails(gate, capsys, monkeypatch):
    """The core hole: the channel still advertising the previous release."""
    fx = Fixture(gate, monkeypatch)
    gate.assert_eq(
        fx.check(STALE, "1.2.17"), "1", "a manifest advertising 1.2.16 must FAIL a 1.2.17 run"
    )
    gate.assert_eq(
        fx.old_check(STALE), "0", "the OLD code must accept it, or this test proves nothing"
    )
    capsys.readouterr()
    gate.log_pass("the manifest version is compared, not merely printed")


def test_an_empty_binaries_map_fails(gate, capsys, monkeypatch):
    """`jq -e '.version, .binaries'` passes on {} because an empty object is
    truthy, and the reachability check then skipped itself."""
    fx = Fixture(gate, monkeypatch)
    gate.assert_eq(fx.check(NO_BINARIES, "1.2.17"), "1", "a manifest with no binaries must FAIL")
    gate.assert_eq(
        fx.old_check(NO_BINARIES),
        "0",
        "the OLD code must accept an empty binaries map, or this test proves nothing",
    )
    capsys.readouterr()
    gate.log_pass("a manifest that names no binary is a failure")


def test_a_missing_linux_binary_fails(gate, capsys, monkeypatch):
    fx = Fixture(gate, monkeypatch)
    gate.assert_eq(
        fx.check(OTHER_ARCH, "1.2.17"), "1", "a manifest with no linux-x64 entry must FAIL"
    )
    gate.assert_eq(
        fx.old_check(OTHER_ARCH),
        "0",
        "the OLD code must accept it via '// empty', or this test proves nothing",
    )
    capsys.readouterr()
    gate.log_pass("an absent binary URL is a failure, not a skipped check")


def test_an_empty_version_field_fails(gate, capsys, monkeypatch):
    fx = Fixture(gate, monkeypatch)
    gate.assert_eq(fx.check(NO_VERSION, "1.2.17"), "1", "an empty .version must FAIL")
    gate.assert_eq(fx.check(GOOD, ""), "1", "an empty expected version must FAIL")
    capsys.readouterr()
    gate.log_pass("a version that could not be established fails")


def test_an_unreachable_binary_still_fails(gate, capsys, monkeypatch):
    """This one the old code did catch; assert it did not regress."""
    fx = Fixture(gate, monkeypatch)
    gate.assert_eq(
        fx.check(GOOD, "1.2.17", head_ok=False), "1", "an unreachable binary URL must FAIL"
    )
    gate.assert_eq(
        fx.check(GOOD, "1.2.17", head_ok=True), "0", "and must pass again once reachable"
    )
    capsys.readouterr()
    gate.log_pass("reachability is still enforced")


def test_a_failed_fetch_fails(gate, capsys, monkeypatch):
    fx = Fixture(gate, monkeypatch)
    gate.assert_eq(
        fx.check(GOOD, "1.2.17", fetch_fails=True),
        "1",
        "a manifest that cannot be fetched must FAIL",
    )
    capsys.readouterr()
    gate.log_pass("a fetch failure is a failure")


def test_no_channel_skips_visibly(gate, capsys, monkeypatch):
    """With no channel the URL would be .../cli//manifest.json, a path that names nothing. 77 is the skip code run_test reports as SKIP; it must not be 0."""
    fx = Fixture(gate, monkeypatch)
    gate.assert_eq(
        fx.check(GOOD, "1.2.17", channel=""),
        "77",
        "a channel-less run must SKIP, not pass and not fail",
    )
    capsys.readouterr()
    gate.log_pass("a run with no staged channel skips instead of chasing a dead URL")
