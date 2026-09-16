"""Port of `.ci/scripts/test/gates/test-simulate-promotion-serverside.sh`.

Both-ways test for the SERVER-SIDE copy in `.ci/scripts/deploy/simulate-promotion.sh`.

WHAT BROKE. The promotion simulation synced the whole source channel DOWN to /tmp
and then back UP to the promoted channel, so the job cost two full transfers of a
channel that grows with every release. Measured on the `main` push runs: 21m57s
(2026-07-27), 30m51s (2026-08-07, cancelled at the then-30-minute ceiling), 57m01s
(2026-08-18), 61m12s (2026-08-20, run 32423301927, blew the raised 60-minute
ceiling). That cancellation failed CI Complete and Pipeline Sentinel, and the
release sentinel never ran. The failing job's log holds ZERO retry warnings and
died mid-transfer, so it was size and not flakiness.

A PR CANNOT EXERCISE THE REAL PATH: PR runs promote a tiny per-PR channel in
minutes, only `main` promotes the full `edge` channel. So this does not try to
prove the timing. It pins the SHAPE that caused the timing: the bytes must not
travel through the runner. A regression to download-and-reupload is invisible to
every other check in the repo and would simply be slow again.

WHY THE ABSENT `aws` DOES NOT MAKE THIS VACUOUS, and it is worth saying because a
sibling gate test was dropped from this batch for exactly the opposite reason.
`aws` is NOT installed on this machine. It does not matter here, because the
transfers are driven through a STUB `aws` that this fixture WRITES onto PATH and
that records its argv: the assertions read what the script actually invoked. A
gate test whose subject takes a tool-absent branch has two unreachable cases and
cannot be plant-verified; this one shims the tool rather than probing for it, so
every case runs on any machine.

WHERE THE PORT REIMPLEMENTS THE TWIN. Nowhere behaviourally. The fixture tree, the
`aws` stub and the `cf-purge-urls.sh` stub are written from Python instead of from
heredocs, byte for byte the same scripts, and the `rogue` flag is baked into the
stub at write time exactly as the twin's unquoted heredoc bakes it. `get_repo_root()`
resolves from the SCRIPT's own path (`.ci/scripts/lib` -> up 3), so the fixture
still mirrors the tree layout rather than just holding the script.

NO `xdist_group`. Each case builds a complete private fixture under pytest's
`tmp_path`, puts its stub bin FIRST on a PATH used by one subprocess, and writes
nothing in the repository.
"""

import os
import pathlib
import shutil
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-simulate-promotion-serverside.sh"

SUT = paths.from_root(".ci", "scripts", "deploy", "simulate-promotion.sh")
COMMON = paths.from_root(".ci", "scripts", "lib", "common.sh")

AWS_VERSION = "aws-cli/2.31.0 Python/3.12"


class Fixture:
    """One promotion run's world: the script, the stubs, and what they recorded."""

    def __init__(self, base: pathlib.Path) -> None:
        self.base = base
        self.argv_log = base / "argv.log"
        self.purged = base / "purged.txt"
        self.out = base / "out.txt"
        self.target = base / "repo" / ".ci" / "scripts" / "deploy" / "simulate-promotion.sh"
        self.bin = base / "bin"

    def argv(self) -> str:
        return self.argv_log.read_text(encoding="utf-8") if self.argv_log.is_file() else ""

    def purge_list(self) -> str:
        return self.purged.read_text(encoding="utf-8") if self.purged.is_file() else ""

    def output(self) -> str:
        return self.out.read_text(encoding="utf-8") if self.out.is_file() else ""


def _write_exec(path: pathlib.Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_fixture(gate, base: pathlib.Path, *, rogue: bool = False) -> Fixture:
    fx = Fixture(base)
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(SUT))
    if not COMMON.is_file():
        gate.log_fail("the fixture needs %s and it is not there" % paths.relative_to_root(COMMON))
    (base / "repo" / ".ci" / "scripts" / "deploy").mkdir(parents=True)
    (base / "repo" / ".ci" / "scripts" / "lib").mkdir(parents=True)
    fx.bin.mkdir()
    shutil.copy2(SUT, fx.target)
    shutil.copy2(COMMON, base / "repo" / ".ci" / "scripts" / "lib" / "common.sh")

    # The purge step shells out to this; keep it inert but present. It RECORDS the
    # URLs it is handed, so the purge assertions read what the script actually
    # asked to be purged rather than a proxy for it.
    _write_exec(
        base / "repo" / ".ci" / "scripts" / "deploy" / "cf-purge-urls.sh",
        '#!/bin/bash\ncat >"%s"\n' % fx.purged,
    )
    write_fake_aws(fx, rogue=rogue)
    return fx


def write_fake_aws(fx: Fixture, *, rogue: bool = False) -> None:
    """A stub that records every invocation and answers `s3 ls --recursive`.

    The listing includes a key containing a SPACE, which is exactly what a naive
    field-split would corrupt. `rogue` makes the listing return a key OUTSIDE the
    requested prefix, which is what the doubled-destination guard must catch.
    """
    rogue_line = '    prefix="somewhere-else/"\n' if rogue else ""
    _write_exec(
        fx.bin / "aws",
        "#!/bin/bash\n"
        'printf \'%%s\\n\' "$*" >>"%s"\n'
        'case "$1" in\n'
        '    --version) echo "%s" ;;\n'
        "    configure) exit 0 ;;\n"
        "    s3)\n"
        "        # Real `aws s3 ls <prefix> --recursive` prints FULL keys under the\n"
        "        # prefix asked for. A stub that ignored the prefix would hide the\n"
        "        # strip-and-rebuild logic entirely, so derive the keys from argv[3].\n"
        '        if [[ "$2" == "ls" ]]; then\n'
        '            prefix="${3#s3://rediacc-releases/}"\n'
        "%s"
        '            echo "2026-08-20 12:00:01       1234 ${prefix}dists/Release"\n'
        '            echo "2026-08-20 12:00:02         12 ${prefix}dists/with space/InRelease"\n'
        "        fi\n"
        "        # The sed-fix step downloads a config file and then edits it in\n"
        "        # place. A download takes the form: cp s3://SRC LOCALPATH\n"
        "        # --endpoint-url URL, so the destination is argv[4] and NOT the last\n"
        "        # argument, which is the endpoint value.\n"
        '        if [[ "$2" == "cp" && "$3" == s3://* && "$4" != s3://* ]]; then\n'
        "            printf 'baseurl=https://releases.rediacc.com/rpm/edge/\\n' >\"$4\"\n"
        "        fi\n"
        "        exit 0\n"
        "        ;;\n"
        "esac\n"
        "exit 0\n" % (fx.argv_log, AWS_VERSION, rogue_line),
    )


PROMOTION_ENV = {
    "CHANNEL": "edge",
    "AWS_ACCESS_KEY_ID": "k",
    "AWS_SECRET_ACCESS_KEY": "s",
    "CLOUDFLARE_R2_ENDPOINT": "https://example.invalid",
    "CLOUDFLARE_ZONE_ID": "z",
    "CLOUDFLARE_API_TOKEN": "t",
}


def run_promotion(fx: Fixture) -> harness.RunResult:
    fx.argv_log.write_text("", encoding="utf-8")
    result = harness.run(
        ["bash", str(fx.target)],
        env={**PROMOTION_ENV, "PATH": "%s%s%s" % (fx.bin, os.pathsep, os.environ["PATH"])},
    )
    fx.out.write_text(result.combined, encoding="utf-8")
    return result


def promote_or_fail(gate, fx: Fixture) -> harness.RunResult:
    """Run it, and surface the script's OWN output when it dies.

    The twin does this so `set -e` cannot kill the test with an empty transcript,
    which hides the reason entirely.
    """
    result = run_promotion(fx)
    if result.rc != 0:
        gate.log_error("simulate-promotion.sh exited %d under the stub:" % result.rc)
        gate.log_fail(
            "simulate-promotion.sh exited %d under the stub:\n%s" % (result.rc, result.combined)
        )
    return result


def test_the_copy_is_server_side(gate, tmp_path: pathlib.Path):
    gate.log_test("THE INVARIANT: every recursive transfer has an s3:// destination")
    fx = build_fixture(gate, tmp_path)
    promote_or_fail(gate, fx)
    gate.assert_contains(
        fx.argv(),
        "s3api copy-object --bucket rediacc-releases --key apt/edge-promoted/dists/Release "
        "--copy-source rediacc-releases/apt/edge/dists/Release",
        "apt objects are copied bucket-to-bucket, and the destination key is rebuilt correctly",
    )
    gate.assert_not_contains(
        fx.argv(), "/tmp/promote-", "no transfer stages the channel through a local tmp directory"
    )
    # THE R2 CONSTRAINT, pinned. `aws s3 sync`/`cp` reach for object tagging on
    # every s3-to-s3 path and R2 implements neither side of it: --copy-props
    # default needs GetObjectTagging, and any other value sends
    # x-amz-tagging-directive: REPLACE, which R2 answered with NotImplemented on
    # every object of run 32465461193. s3api sends only what is named here.
    gate.assert_not_contains(
        fx.argv(), "--copy-props", "no --copy-props: it forces a tagging directive R2 rejects"
    )
    gate.assert_not_contains(
        fx.argv(), "--tagging-directive", "no --tagging-directive: the exact header R2 rejected"
    )
    gate.log_pass(
        "the channel is copied server-side via s3api, never through the runner and never "
        "touching tags"
    )


def test_all_four_formats_are_copied(gate, tmp_path: pathlib.Path):
    gate.log_test("all four repo formats are promoted")
    fx = build_fixture(gate, tmp_path)
    promote_or_fail(gate, fx)
    for fmt in ("apt", "rpm", "apk", "archlinux"):
        # s3api addresses objects by --bucket/--key, not an s3:// URL.
        gate.assert_contains(fx.argv(), "--key %s/edge-promoted/" % fmt, "%s is promoted" % fmt)
        gate.assert_contains(
            fx.argv(),
            "--copy-source rediacc-releases/%s/edge/" % fmt,
            "%s is sourced from the unpromoted channel" % fmt,
        )
    gate.log_pass("all four repo formats are promoted")


def test_a_key_outside_the_prefix_is_REFUSED(gate, tmp_path: pathlib.Path):  # noqa: N802
    gate.log_test("a listing key outside the source prefix must be refused")
    # A key that does not start with the source prefix would make the strip a
    # silent no-op and write to a DOUBLED destination such as
    # apk/edge-promoted/apt/edge/... The install tests that follow would then read
    # a channel nobody wrote, so this must fail loudly instead.
    fx = build_fixture(gate, tmp_path, rogue=True)
    result = run_promotion(fx)
    if result.rc == 0:
        gate.log_fail(
            "a key outside the source prefix was accepted; the destination would be doubled"
        )
    gate.assertions += 1
    gate.assert_contains(result.combined, "not under expected prefix", "the guard names the reason")
    gate.log_pass("a key outside the source prefix is refused rather than silently doubled")


def test_cache_control_is_still_applied(gate, tmp_path: pathlib.Path):
    gate.log_test("promoted objects stay uncacheable")
    # Channel paths reuse filenames per release, so promoted bytes must never be
    # cacheable. Losing this in the rewrite would be silent until a stale POP
    # served an old Packages.gz to the install tests.
    fx = build_fixture(gate, tmp_path)
    promote_or_fail(gate, fx)
    gate.assert_contains(fx.argv(), "--cache-control no-cache", "promoted objects stay uncacheable")
    gate.log_pass("cache-control no-cache survives the rewrite")


def test_purge_urls_come_from_the_listing_and_survive_spaces(gate, tmp_path: pathlib.Path):
    gate.log_test("purge URLs are enumerated by listing, and a space survives")
    # The old code walked the local tmp tree to build purge URLs. That tree is
    # gone, so the listing replaces it; a key containing a space must round-trip
    # intact rather than being split into two bogus URLs.
    fx = build_fixture(gate, tmp_path)
    promote_or_fail(gate, fx)
    gate.assert_contains(
        fx.argv(),
        "s3 ls s3://rediacc-releases/apt/edge/ --recursive",
        "purge URLs are derived from a listing, not a transfer",
    )
    gate.assert_contains(
        fx.purge_list(),
        "https://releases.rediacc.com/apt/edge-promoted/dists/Release",
        "a promoted URL is queued for purge",
    )
    gate.assert_contains(
        fx.purge_list(),
        "https://releases.rediacc.com/apt/edge-promoted/dists/with space/InRelease",
        "a key containing a space survives into its purge URL intact",
    )
    gate.assert_contains(fx.output(), "Promotion simulated", "the script ran to completion")
    gate.log_pass("purge URLs are enumerated by listing the promoted channel")


def test_the_stub_is_actually_being_exercised(gate, tmp_path: pathlib.Path):
    gate.log_test("THE CONTROL: an empty argv log must be impossible")
    # If the stub were never called, every assertion above would be vacuous.
    fx = build_fixture(gate, tmp_path)
    promote_or_fail(gate, fx)
    lines = len(fx.argv().splitlines())
    if lines <= 4:
        gate.log_fail(
            "the fake aws recorded only %d invocation(s); the assertions above would be vacuous"
            % lines
        )
    gate.assertions += 1
    gate.log_pass("the stub recorded %d invocations, so the assertions read real calls" % lines)
