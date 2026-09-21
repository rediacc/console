"""Port of `.ci/scripts/test/gates/test-devcontainer-pin-freshness.sh`, retired in W7 P5.

`scripts/gates/check-devcontainer-pin-freshness.ts`, driven entirely through its test seams so it runs offline and deterministically:

  DEVCONTAINER_FRESHNESS_FIXTURE  a JSON map of base -> latest version/date/digests,
                                  used INSTEAD of the network
  DEVCONTAINER_BLOCKLIST_FILE     the blocklist whose BLOCKER convention is enforced
  DEVCONTAINER_DOCKERFILE         the file `--upgrade` rewrites

Proved: it passes when nothing is behind, FIRES on a stale pin, DEFERS a just-released version (the shared soak), FAILS SOFT when a source cannot be checked, and enforces the BLOCKER convention on its blocklist.

Plus the assertion this gate exists for, which the embed gate's test has no reason to make: `--upgrade` must move the VERSION and its sha256 ARGs TOGETHER, and must refuse to move the version at all when a digest is missing. A tree carrying a new version beside a stale hash does not build, so an upgrade path that can produce one is worse than no upgrade path.

THE REAL DOCKERFILE IS NEVER WRITTEN, and the twin's comment on that is a correction rather than a tidy-up. Its earlier shape copied the tracked file aside,
let `--upgrade` rewrite it IN PLACE, and restored from an EXIT trap. The restore
was correct as far as it went (`log_fail` exits immediately, so a restore placed after the call is skipped by exactly the runs that need it) but the mutation itself is visible to every other gate sharing the tree: on 2026-09-03 it reddened `check:ci-setup-idempotency` in the pre-push lane, which reported "setup --check changed the working tree" over a file `run.sh` never writes.
The gate therefore takes a Dockerfile PATH and the test hands it a copy.

WHERE THE PORT DIFFERS, and it removes a whole class of coupling. The twin builds ONE fixture directory at file scope and calls `restore_dockerfile` between the two `--upgrade` cases, because the second must not see the first one's `9999.1.0`. Here every case builds its own fixture set under pytest's `tmp_path`, so there is nothing to restore and no ordering between cases at all:
an `--upgrade` case cannot leave a mutated Dockerfile for its neighbour, because its neighbour has a different one. The `chmod u+w` the twin needs survives for the same reason it exists there -- `shutil.copy2` copies the source's mode, and `--upgrade` must be able to rewrite.

WHY THE ONE-HOUR TIMESTAMP IS COMPUTED HERE. The twin spells it `date -u -d '1 hour ago'` with a BSD `date -u -v-1H` fallback; the port uses
`datetime.now(UTC) - timedelta(hours=1)` and formats it with the same
`%Y-%m-%dT%H:%M:%SZ`. Same instant, same wire format, and no dependence on which `date` the host ships -- which is the exact portability trap `.ci/media/portable.sh` exists for elsewhere in this tree.

NO `xdist_group`. Every case owns its whole fixture set under `tmp_path` and the tracked Dockerfile is only ever READ; nothing is bound and no module global is mutated.
"""

import datetime
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

VALIDATOR = paths.from_root("scripts", "gates", "check-devcontainer-pin-freshness.ts")
REAL_DOCKERFILE = paths.from_root(".devcontainer", "Dockerfile")

# The real digests of bw-linux-2026.8.0.zip / bw-linux-arm64-2026.8.0.zip, so a passing `--upgrade` case also re-proves the pins in the tree.
BW_SHA_AMD64 = "367f618e9fcccaac4980ec12c7bafd01df739b5f3cb1af31bc9045cf75eea1d6"
BW_SHA_ARM64 = "74d822a5dceda5896ed8fc07bc61925b29afd98d96a6a3e9e525ae556c3083a8"


def build_fixtures(gate, directory):
    """Every fixture the twin's `setup_fixtures` writes, into `directory`.

    Returns the path of the WRITABLE Dockerfile copy. The real one is read and never touched.
    """
    if not VALIDATOR.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(VALIDATOR))
    if not REAL_DOCKERFILE.is_file():
        gate.log_fail("the Dockerfile the gate pins is missing: %s" % REAL_DOCKERFILE)

    dockerfile = directory / "Dockerfile"
    shutil.copy2(REAL_DOCKERFILE, dockerfile)
    # WRITABLE regardless of the source's mode: copy2 carries the source's permissions across, and `--upgrade` must be able to rewrite the copy. Without this the case depends on the environment rather than on the code.
    dockerfile.chmod(dockerfile.stat().st_mode | 0o200)

    # Reported far OLDER than the real pin -> nothing is stale.
    (directory / "all-current.json").write_text(
        '{ "bw": { "version": "0.0.1" } }\n', encoding="utf-8"
    )

    # Reported far NEWER, published long ago -> confirmed stale (past the soak).
    (directory / "stale.json").write_text(
        "{\n"
        '  "bw": {\n'
        '    "version": "9999.1.0",\n'
        '    "publishedAt": "2020-01-01T00:00:00Z",\n'
        '    "digests": {\n'
        '      "bw-linux-9999.1.0.zip": "%s",\n'
        '      "bw-linux-arm64-9999.1.0.zip": "%s"\n'
        "    }\n"
        "  }\n"
        "}\n" % (BW_SHA_AMD64, BW_SHA_ARM64),
        encoding="utf-8",
    )

    # Stale, but the arm64 asset has NO digest -> `--upgrade` must refuse the whole source rather than write a version whose hash it could not resolve.
    (directory / "stale-missing-digest.json").write_text(
        "{\n"
        '  "bw": {\n'
        '    "version": "9999.1.0",\n'
        '    "publishedAt": "2020-01-01T00:00:00Z",\n'
        '    "digests": { "bw-linux-9999.1.0.zip": "%s" }\n'
        "  }\n"
        "}\n" % BW_SHA_AMD64,
        encoding="utf-8",
    )

    # Newer but published just now -> inside the freshness window (deferred).
    recent = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    (directory / "fresh.json").write_text(
        '{ "bw": { "version": "9999.1.0", "publishedAt": "%s" } }\n' % recent, encoding="utf-8"
    )

    # Empty fixture -> every source "not in fixture" -> could-not-check (fail soft).
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
    return harness.run(
        [npx, "tsx", str(VALIDATOR), *args],
        cwd=paths.repo_root(),
        env={
            "DEVCONTAINER_FRESHNESS_FIXTURE": str(directory / fixture),
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


def test_passes_when_current(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate(gate, tmp_path, dockerfile, "all-current.json")
    gate.assert_exit_code(0, result.rc, "nothing behind upstream should pass")
    gate.log_pass("current pins pass")


def test_fires_when_stale(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate(gate, tmp_path, dockerfile, "stale.json")
    gate.assert_exit_code(1, result.rc, "a pin behind upstream should fail")
    gate.assert_contains(result.combined, "Bitwarden CLI", "error names the stale component")
    gate.assert_contains(result.combined, "--upgrade", "red output gives the --upgrade fix")
    gate.log_pass("stale pin fires")


def test_defers_fresh_release(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate(gate, tmp_path, dockerfile, "fresh.json")
    gate.assert_exit_code(
        0, result.rc, "a just-released upstream version should be deferred, not failed"
    )
    gate.assert_contains(
        result.combined, "deferred", "fresh release is reported as deferred (soak)"
    )
    gate.log_pass("fresh release is deferred by the soak")


def test_fails_soft_when_uncheckable(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate(gate, tmp_path, dockerfile, "empty.json")
    gate.assert_exit_code(0, result.rc, "sources that cannot be checked must not fail the build")
    gate.log_pass("uncheckable sources fail soft")


def test_blocklist_rejects_missing_reason(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate_blocklist(gate, tmp_path, dockerfile, "all-current.json", "blocklist-bad")
    gate.assert_exit_code(
        1, result.rc, "a blocklist entry lacking a BLOCKER reason must fail the gate"
    )
    gate.assert_contains(result.combined, "invalid entries", "error names the malformed blocklist")
    gate.log_pass("blocklist entry without a BLOCKER reason fires")


def test_blocklist_accepts_valid_reason(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate_blocklist(gate, tmp_path, dockerfile, "all-current.json", "blocklist-good")
    gate.assert_exit_code(
        0, result.rc, "a blocklist entry with a substantive BLOCKER reason must be accepted"
    )
    gate.log_pass("well-formed blocklist entry is accepted")


def test_upgrade_moves_version_and_hashes(gate, tmp_path):
    dockerfile = build_fixtures(gate, tmp_path)
    result = run_gate(gate, tmp_path, dockerfile, "stale.json", "--upgrade")
    gate.assert_exit_code(0, result.rc, "--upgrade with every digest resolvable should succeed")
    gate.assert_contains(
        result.combined, "sha256 pin", "output says the hashes moved too, not just the version"
    )
    written = dockerfile.read_text(encoding="utf-8")
    gate.assert_eq(arg_value(written, "BW_VERSION"), "9999.1.0", "--upgrade rewrote BW_VERSION")
    gate.assert_eq(
        arg_value(written, "BW_SHA256_AMD64"),
        BW_SHA_AMD64,
        "--upgrade rewrote BW_SHA256_AMD64 from the release digest",
    )
    gate.assert_eq(
        arg_value(written, "BW_SHA256_ARM64"),
        BW_SHA_ARM64,
        "--upgrade rewrote BW_SHA256_ARM64 from the release digest",
    )
    gate.log_pass("--upgrade moves the version and both sha256 pins together")


def test_upgrade_refuses_when_a_digest_is_missing(gate, tmp_path):
    """THE ASSERTION THIS GATE EXISTS FOR.

    A half-applied upgrade -- new version, old hash -- is a tree that fails `docker build` at `sha256sum -c -`, and an operator who ran `--upgrade` and got that learns to distrust the gate rather than the release. So a missing digest must leave the Dockerfile COMPLETELY untouched.
    """
    dockerfile = build_fixtures(gate, tmp_path)
    before = dockerfile.read_bytes()
    result = run_gate(gate, tmp_path, dockerfile, "stale-missing-digest.json", "--upgrade")
    after = dockerfile.read_bytes()
    gate.assert_exit_code(
        1, result.rc, "--upgrade must fail when a required digest cannot be resolved"
    )
    gate.assert_contains(result.combined, "no digest", "the error names the missing digest")
    gate.assert_eq(after, before, "the Dockerfile must be left untouched, not half-written")
    gate.log_pass("--upgrade refuses a partial rewrite when a digest is missing")
