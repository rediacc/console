"""Port of `.ci/scripts/test/gates/test-installmethods-manifest.sh`.

`test_update_check()` in `.ci/scripts/test/test-install-methods.sh`.

WHY THIS EXISTS. The update-manifest check fetched the channel's manifest.json, PRINTED its version, and never compared it:

    manifest_ver=$(echo "$manifest" | jq -r '.version')
    log_info "  Manifest version: $manifest_ver"     # last mention

`$VERSION` did not appear anywhere in the function, so a channel still advertising the previous release looked exactly like a correctly published one. Two more silent passes sat underneath it: the structural guard
`jq -e '.version, .binaries'` accepts `"binaries": {}` because an empty object is
TRUTHY in jq, and the reachability check read the URL with `// empty` and, finding none, skipped itself and returned 0 -- so a manifest naming no binary at all passed twice over.

All three are now failures. Each is asserted against the CURRENT code and against a re-creation of the OLD code, because a negative case only means something if the previous implementation really did admit it.

NOTHING TOUCHES THE NETWORK: `curl` is shimmed inside `tmp_path` and PATH is overlaid for the subprocess only, never for this process. jq is required rather than tolerated -- without it `test_update_check` returns 77 (skip) and this module would run green having exercised nothing.

ARGUMENT ORDER. The twin calls `assert_eq "0" "$(check ...)"`, EXPECTED first, inverting `assert_eq`'s contract. Same verdict, inverted diagnostic; the port uses the contract's order.
"""

import os
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness, shellsubject

BASH_TWIN = ".ci/scripts/test/gates/test-installmethods-manifest.sh"

TARGET = paths.from_root(".ci", "scripts", "test", "test-install-methods.sh")
SUBJECT = shellsubject.Subject(TARGET)

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

# The implementation as it stood before this change, for the red proof.
OLD_UPDATE_CHECK = """
old_update_check() {
    local manifest
    manifest=$(curl -fsSL "url") || return 1
    if ! echo "$manifest" | jq -e '.version, .binaries' >/dev/null 2>&1; then
        return 1
    fi
    local manifest_ver
    manifest_ver=$(echo "$manifest" | jq -r '.version')
    : "$manifest_ver" # printed, never compared
    local binary_url
    binary_url=$(echo "$manifest" | jq -r '.binaries["linux-x64"].url // empty')
    if [[ -n "$binary_url" ]]; then
        curl -fsSL -o /dev/null --head "$binary_url" 2>/dev/null || return 1
    fi
}
"""

# A curl that serves $FAKE_MANIFEST for a GET and answers reachability probes
# with $FAKE_HEAD_RC.
FAKE_CURL = """#!/bin/bash
for a in "$@"; do
    [ "$a" = "--head" ] && exit "${FAKE_HEAD_RC:-0}"
done
[ -n "${FAKE_FETCH_FAILS:-}" ] && exit 22
cat "$FAKE_MANIFEST"
"""


class Fixture:
    def __init__(self, gate, tmp_path: pathlib.Path) -> None:
        harness.require_tool(
            "jq",
            "install jq: without it test_update_check skips itself (77) and these tests "
            "would check nothing",
        )
        harness.require_tool("bash", "install bash; this gate drives the subject's shell functions")
        self.gate = gate
        self.root = tmp_path
        self.manifest_file = tmp_path / "m.json"
        bindir = tmp_path / "bin"
        bindir.mkdir(exist_ok=True)
        curl = bindir / "curl"
        curl.write_text(FAKE_CURL, encoding="utf-8")
        curl.chmod(0o755)
        self.bindir = bindir
        prelude = tmp_path / "prelude.sh"
        prelude.write_text(
            "\n".join(
                [
                    "log_info() { :; }",
                    "log_warn() { :; }",
                    "log_error() { :; }",
                    SUBJECT.shell_fn(gate, "verify_version"),
                    SUBJECT.shell_fn(gate, "test_update_check"),
                    "DRY_RUN=false",
                    'REPO_URL="https://releases.example.invalid"',
                    'REPO_CHANNEL="edge"',
                    OLD_UPDATE_CHECK,
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.prelude = prelude

    def run(self, snippet: str, *args: str, **extra_env: str) -> harness.RunResult:
        env = {
            "PATH": "%s%s%s" % (self.bindir, os.pathsep, os.environ.get("PATH", "")),
            "FAKE_MANIFEST": str(self.manifest_file),
            "FAKE_HEAD_RC": "0",
        }
        env.update(extra_env)
        return harness.run(
            ["bash", "-c", 'source "$1"\n%s' % snippet, "_", str(self.prelude), *args],
            env=env,
            timeout=120,
        )

    def check(self, manifest: str, version: str, **extra_env: str) -> str:
        """The CURRENT function's exit code, as a string."""
        self.manifest_file.write_text(manifest, encoding="utf-8")
        result = self.run(
            'VERSION="$2"\nrc=0\ntest_update_check >/dev/null 2>&1 || rc=$?\necho "$rc"',
            version,
            **extra_env,
        )
        return result.out.strip()

    def old_check(self, manifest: str) -> str:
        """The PRE-FIX function's exit code, as a string."""
        self.manifest_file.write_text(manifest, encoding="utf-8")
        result = self.run('rc=0\nold_update_check >/dev/null 2>&1 || rc=$?\necho "$rc"')
        return result.out.strip()


def test_a_correct_manifest_passes(gate, tmp_path):
    fx = Fixture(gate, tmp_path)
    gate.assert_eq(
        fx.check(GOOD, "1.2.17"), "0", "a manifest matching the expected version must pass"
    )
    gate.log_pass("a correctly published manifest passes")


def test_a_stale_manifest_version_fails(gate, tmp_path):
    """The core hole: the channel still advertising the previous release."""
    fx = Fixture(gate, tmp_path)
    gate.assert_eq(
        fx.check(STALE, "1.2.17"), "1", "a manifest advertising 1.2.16 must FAIL a 1.2.17 run"
    )
    gate.assert_eq(
        fx.old_check(STALE), "0", "the OLD code must accept it, or this test proves nothing"
    )
    gate.log_pass("the manifest version is compared, not merely printed")


def test_an_empty_binaries_map_fails(gate, tmp_path):
    """`jq -e '.version, .binaries'` passes on {} because an empty object is
    truthy, and the reachability check then skipped itself."""
    fx = Fixture(gate, tmp_path)
    gate.assert_eq(fx.check(NO_BINARIES, "1.2.17"), "1", "a manifest with no binaries must FAIL")
    gate.assert_eq(
        fx.old_check(NO_BINARIES),
        "0",
        "the OLD code must accept an empty binaries map, or this test proves nothing",
    )
    gate.log_pass("a manifest that names no binary is a failure")


def test_a_missing_linux_binary_fails(gate, tmp_path):
    fx = Fixture(gate, tmp_path)
    gate.assert_eq(
        fx.check(OTHER_ARCH, "1.2.17"), "1", "a manifest with no linux-x64 entry must FAIL"
    )
    gate.assert_eq(
        fx.old_check(OTHER_ARCH),
        "0",
        "the OLD code must accept it via '// empty', or this test proves nothing",
    )
    gate.log_pass("an absent binary URL is a failure, not a skipped check")


def test_an_empty_version_field_fails(gate, tmp_path):
    fx = Fixture(gate, tmp_path)
    gate.assert_eq(fx.check(NO_VERSION, "1.2.17"), "1", "an empty .version must FAIL")
    gate.assert_eq(fx.check(GOOD, ""), "1", "an empty expected version must FAIL")
    gate.log_pass("a version that could not be established fails")


def test_an_unreachable_binary_still_fails(gate, tmp_path):
    """This one the old code did catch; assert it did not regress."""
    fx = Fixture(gate, tmp_path)
    gate.assert_eq(
        fx.check(GOOD, "1.2.17", FAKE_HEAD_RC="1"), "1", "an unreachable binary URL must FAIL"
    )
    gate.assert_eq(
        fx.check(GOOD, "1.2.17", FAKE_HEAD_RC="0"), "0", "and must pass again once reachable"
    )
    gate.log_pass("reachability is still enforced")


def test_a_failed_fetch_fails(gate, tmp_path):
    fx = Fixture(gate, tmp_path)
    gate.assert_eq(
        fx.check(GOOD, "1.2.17", FAKE_FETCH_FAILS="1"),
        "1",
        "a manifest that cannot be fetched must FAIL",
    )
    gate.log_pass("a fetch failure is a failure")


def test_no_channel_skips_visibly(gate, tmp_path):
    """With no channel the URL would be .../cli//manifest.json, a path that names nothing. 77 is the skip code run_test reports as SKIP; it must not be 0."""
    fx = Fixture(gate, tmp_path)
    fx.manifest_file.write_text(GOOD, encoding="utf-8")
    result = fx.run(
        'VERSION="1.2.17"\nrc=0\nREPO_CHANNEL="" test_update_check >/dev/null 2>&1 || rc=$?\n'
        'echo "$rc"'
    )
    gate.assert_eq(result.out.strip(), "77", "a channel-less run must SKIP, not pass and not fail")
    gate.log_pass("a run with no staged channel skips instead of chasing a dead URL")
