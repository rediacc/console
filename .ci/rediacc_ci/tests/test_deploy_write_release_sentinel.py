"""`rediacc_ci.deploy.write_release_sentinel` against its bash twin.

NO R2, NO CREDENTIALS, NOTHING THAT LEAVES THIS HOST. `aws` is the only remote
side this script has, so a recording fake `aws` goes first on `PATH`: it logs
its exact argv, captures the UPLOADED BYTES from stdin, and answers each
subcommand from environment knobs. Both implementations are driven through the
same fake and five things are compared:

  1. the exit code,
  2. stdout, byte for byte,
  3. stderr, after ONE documented normalisation (below),
  4. the fake's aws CALL LOG, byte for byte,
  5. THE UPLOADED PAYLOAD, with `released_at` masked.

WHY THE PAYLOAD IS THE ASSERTION THAT MATTERS. Everything this script produces
for a human is three log lines that say the same thing whatever was written.
The ARTIFACT is a JSON object that a forensic sweep reads months later to
reconstruct what CI intended, and its key order, its types and its escaping are
all jq's. A differential that compared only stdout would score a port that
uploaded `{}` as equivalent.

THE ONE NORMALISATION, AND IT IS NOT THIS PORT'S DOING.
`rediacc_ci.core.release_state_validator._log_error` deliberately omits
`common.sh`'s `✗ ` glyph -- its own docstring says so, and that module was
ported and ledgered in an earlier wave. So on the one path that surfaces a
library error (`rsv_binary_count` failing) the twin's stderr carries `✗ ` and
the port's does not. `_normalise_err` strips that prefix and NOTHING else; the
message text, the indented aws diagnostic beneath it and the exit code are all
compared unmasked.

`released_at` CANNOT AGREE and is not supposed to: the twin stamps `date -u`,
the port stamps `datetime.now(UTC)`, and the two processes run seconds apart.
Only that field is masked, and `test_released_at_has_the_same_shape_on_both_sides`
asserts the FORMAT separately so the masking cannot hide a port that wrote a
Unix epoch there.

TWO TWIN DEFECTS ARE PINNED RATHER THAN FIXED, because fixing a twin belongs to
a later cutover box: FINDING 5 (`--version` with no value exits 1 in silence,
not the documented 2 with a message) and FINDING 6 (a failed R2 probe and a
genuine sealed-but-empty refusal share exit code 1).

K=5 LEDGER: `.ci/shadow/w7p6-write-release-sentinel.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import write_release_sentinel as port
from rediacc_ci.tests import differential as diff

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "write-release-sentinel.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "write_release_sentinel.py"
MODULE = "rediacc_ci.deploy.write_release_sentinel"

# The recording fake. Dispatches on the first two argv words, exactly as the `write_once_guard` differential's fake does, so each subcommand is scripted independently. `s3 cp -` is the WRITE (stdin captured to uploaded.json) and
# `s3 cp s3://... -` is the READBACK; telling them apart by which side of the
# pair is `-` is what the real CLI does too.
FAKE_AWS = r"""#!/bin/bash
printf 'aws %s\n' "$*" >>"$FAKE_LOG"
d="$FAKE_DIR"
case "$1 $2" in
    "s3api list-objects-v2")
        if [[ "${FAKE_LIST_RC:-0}" != "0" ]]; then
            printf 'An error occurred (AccessDenied) when calling ListObjectsV2\n' >&2
            exit "${FAKE_LIST_RC}"
        fi
        printf '%s\n' "${FAKE_BINCOUNT:-3}"
        exit 0
        ;;
    "s3 cp")
        if [[ "$3" == "-" ]]; then
            cat >"$d/uploaded.json"
            exit "${FAKE_UPLOAD_RC:-0}"
        fi
        case "${FAKE_READBACK:-echo}" in
            missing) exit 1 ;;
            wrong)   printf '{"version":"v9.9.9"}' ; exit 0 ;;
            echo)    [[ -f "$d/uploaded.json" ]] && cat "$d/uploaded.json"; exit 0 ;;
        esac
        exit 0
        ;;
esac
exit 0
"""

CREDS = {
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "test-key-id",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "test-secret",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.invalid",
}

GLYPH = "✗ "  # common.sh's log_error marker; see the module docstring.


def _normalise_err(text: str) -> str:
    """Strip the validator library's missing `✗ ` prefix, and nothing else."""
    return "".join(line.removeprefix(GLYPH) + "\n" for line in text.split("\n")[:-1])


def _normalise_payload(text: str) -> str:
    return re.sub(r'"released_at":"[^"]*"', '"released_at":"<ts>"', text)


class Run:
    def __init__(self, rc: int, out: str, err: str, log: str, payload: str | None) -> None:
        self.rc = rc
        self.out = out
        self.err = err
        self.raw_err = err
        self.log = log
        self.payload = payload


def make_bin(tmp_path: pathlib.Path) -> pathlib.Path:
    binary_dir = tmp_path / "fxbin"
    binary_dir.mkdir(exist_ok=True)
    fake = binary_dir / "aws"
    fake.write_text(FAKE_AWS, encoding="utf-8")
    fake.chmod(0o755)
    return binary_dir


def drive(
    tmp_path: pathlib.Path,
    args: list[str],
    *,
    env_extra: dict[str, str] | None = None,
    creds: dict[str, str] | None = None,
    port_file: pathlib.Path | None = None,
) -> tuple[Run, Run]:
    """Run BOTH implementations with the same argv against their own fake state."""
    binary_dir = make_bin(tmp_path)
    runs: list[Run] = []
    for side in ("old", "new"):
        fixture_dir = tmp_path / ("fx-%s" % side)
        if fixture_dir.exists():
            shutil.rmtree(fixture_dir)
        fixture_dir.mkdir(parents=True)
        log = tmp_path / ("log-%s" % side)
        log.write_text("", encoding="utf-8")
        env = diff.env_for(
            PATH="%s:%s" % (binary_dir, os.environ.get("PATH", "")),
            FAKE_DIR=str(fixture_dir),
            FAKE_LOG=str(log),
            **{**(CREDS if creds is None else creds), **(env_extra or {})},
        )
        quoted = " ".join("'%s'" % a for a in args)
        if side == "old":
            command = "bash %s %s" % (TWIN, quoted)
        else:
            env["PYTHONPATH"] = str(ROOT / ".ci")
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            command = (
                "python3 %s %s" % (port_file, quoted)
                if port_file is not None
                else "python3 -m %s %s" % (MODULE, quoted)
            )
        rc, out, err = diff.bash_streams(command, env=env, timeout=60)
        uploaded = fixture_dir / "uploaded.json"
        payload = uploaded.read_text(encoding="utf-8") if uploaded.exists() else None
        runs.append(Run(rc, out, err, log.read_text(encoding="utf-8"), payload))
    return runs[0], runs[1]


def assert_same(old: Run, new: Run) -> None:
    assert new.rc == old.rc, "exit: twin %s, port %s" % (old.rc, new.rc)
    assert new.out == old.out
    assert _normalise_err(new.err) == _normalise_err(old.err)
    assert new.log == old.log, "the two sides did not make the same aws calls"
    if old.payload is None or new.payload is None:
        assert old.payload == new.payload, "one side uploaded and the other did not"
    else:
        assert _normalise_payload(new.payload) == _normalise_payload(old.payload)


HAPPY = ["--version", "1.0.5", "--channel", "edge", "--commit-sha", "abc123def"]


# --------------------------------------------------------------------------- The happy path, and the artifact it produces ---------------------------------------------------------------------------


def test_a_sealed_release_agrees_byte_for_byte(tmp_path: pathlib.Path) -> None:
    old, new = drive(tmp_path, HAPPY)
    assert old.rc == 0, old.err
    assert old.out == "", "every line this script writes goes to stderr"
    assert "→ writing sentinel: s3://rediacc-releases/cli/v1.0.5/.released" in old.err
    assert "✓   sealed cli/v1.0.5/.released" in old.err
    assert "✓ release v1.0.5 on edge is sealed" in old.err
    assert_same(old, new)


def test_the_uploaded_payload_is_exactly_the_twins_bytes(tmp_path: pathlib.Path) -> None:
    """Key ORDER, types and escaping, not just "the same fields". `jq`'s object
    literal preserves the written order and `--arg` makes every value a string,
    so a `json.dumps` port would differ on both counts."""
    old, new = drive(tmp_path, HAPPY)
    assert old.payload is not None
    assert new.payload is not None
    assert _normalise_payload(old.payload) == (
        '{"version":"v1.0.5","channel":"edge","commit_sha":"abc123def",'
        '"product":"cli","released_at":"<ts>","artifacts_produced":["cli"]}'
    )
    assert _normalise_payload(new.payload) == _normalise_payload(old.payload)
    # No trailing newline: `jq -nc` emits one and `$(...)` / `.rstrip` strip it, and `printf '%s'` adds none back.
    assert not old.payload.endswith("\n")
    assert not new.payload.endswith("\n")


def test_released_at_has_the_same_shape_on_both_sides(tmp_path: pathlib.Path) -> None:
    """The one masked field, checked directly so the mask cannot hide a port
    that wrote a Unix epoch or a fractional-second timestamp there."""
    old, new = drive(tmp_path, HAPPY)
    shape = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    old_ts = json.loads(old.payload)["released_at"]
    new_ts = json.loads(new.payload)["released_at"]
    assert shape.fullmatch(old_ts), old_ts
    assert shape.fullmatch(new_ts), new_ts


def test_the_stable_channel_is_also_accepted(tmp_path: pathlib.Path) -> None:
    old, new = drive(
        tmp_path, ["--version", "2.0.0", "--channel", "stable", "--commit-sha", "deadbeef"]
    )
    assert old.rc == 0
    assert '"channel":"stable"' in old.payload
    assert "✓ release v2.0.0 on stable is sealed" in old.err
    assert_same(old, new)


def test_the_three_aws_calls_are_made_in_order(tmp_path: pathlib.Path) -> None:
    """Probe, write, read back. A port that skipped the readback would produce
    identical stdout, identical stderr and an identical payload."""
    old, new = drive(tmp_path, HAPPY)
    calls = [line for line in old.log.split("\n") if line]
    assert len(calls) == 3, old.log
    assert calls[0].startswith("aws s3api list-objects-v2 --bucket rediacc-releases")
    assert calls[1] == (
        "aws s3 cp - s3://rediacc-releases/cli/v1.0.5/.released "
        "--endpoint-url https://r2.invalid --cache-control no-cache "
        "--content-type application/json"
    )
    assert calls[2] == (
        "aws s3 cp s3://rediacc-releases/cli/v1.0.5/.released - --endpoint-url https://r2.invalid"
    )
    assert_same(old, new)


def test_releases_bucket_is_honoured(tmp_path: pathlib.Path) -> None:
    """`RSV_BUCKET="${RELEASES_BUCKET:-rediacc-releases}"`. Every one of the
    three keys is built from it, so a port that hard-coded the default would
    write the sentinel into the wrong bucket in a staging run."""
    old, new = drive(tmp_path, HAPPY, env_extra={"RELEASES_BUCKET": "rediacc-staging"})
    assert old.rc == 0
    assert old.log.count("rediacc-staging") == 3, old.log
    assert "rediacc-releases" not in old.log
    assert_same(old, new)


# --------------------------------------------------------------------------- The refusals that keep a corrupt release out of R2 ---------------------------------------------------------------------------


def test_an_empty_prefix_is_refused_rather_than_sealed(tmp_path: pathlib.Path) -> None:
    """The sealed-but-empty state: sentinel present, binaries absent, so the
    sentinel blocks re-upload and every versioned install 404s forever."""
    old, new = drive(tmp_path, HAPPY, env_extra={"FAKE_BINCOUNT": "0"})
    assert old.rc == 1
    assert "refusing to seal cli/v1.0.5/: prefix has no binaries (count=0)." in old.err
    assert "Sealing an empty prefix would create the sealed-but-empty corrupt state." in old.err
    assert old.payload is None, "nothing may be uploaded after a refusal"
    assert "s3 cp" not in old.log
    assert_same(old, new)


def test_a_prefix_holding_only_the_sentinel_is_also_refused(tmp_path: pathlib.Path) -> None:
    """`--query length(Contents[?...] || \\`[]\\`)` answers `None` when the
    prefix is genuinely absent, and the library maps that to 0."""
    old, new = drive(tmp_path, HAPPY, env_extra={"FAKE_BINCOUNT": "None"})
    assert old.rc == 1
    assert "prefix has no binaries (count=0)." in old.err
    assert old.payload is None
    assert_same(old, new)


def test_a_failed_probe_refuses_too_and_says_which(tmp_path: pathlib.Path) -> None:
    """FINDING 6, REPRODUCED NOT FIXED. The library separates "the prefix is
    empty" from "the question could not be answered" on purpose; this caller
    collapses both to exit 1, so only the stderr text tells them apart. A
    release engineer reading `exit 1` cannot know whether to investigate R2 or
    the credentials."""
    old, new = drive(tmp_path, HAPPY, env_extra={"FAKE_LIST_RC": "254"})
    assert old.rc == 1, "same code as the genuine refusal above; that is the finding"
    assert "rsv_binary_count: list-objects-v2 failed for s3://rediacc-releases/cli/v1.0.5/" in (
        old.err
    )
    assert "    An error occurred (AccessDenied) when calling ListObjectsV2" in old.err
    assert "no binaries" not in old.err, "the two refusals differ only in wording"
    assert old.payload is None
    assert_same(old, new)


def test_a_failed_upload_propagates_aws_own_exit_code(tmp_path: pathlib.Path) -> None:
    """This script keeps `pipefail` ON, unlike its two verify- siblings, so
    `printf | aws` reports aws's status and `set -e` carries it out. 254 is the
    awscli's own code; a port that normalised it to 1 would lose the signal."""
    old, new = drive(tmp_path, HAPPY, env_extra={"FAKE_UPLOAD_RC": "254"})
    assert old.rc == 254
    assert "→ writing sentinel:" in old.err
    assert "sealed" not in old.err
    assert "aws s3 cp s3://" not in old.log, "no readback after a failed write"
    assert_same(old, new)


def test_a_missing_readback_fails_loud(tmp_path: pathlib.Path) -> None:
    """Do not trust a silent upload."""
    old, new = drive(tmp_path, HAPPY, env_extra={"FAKE_READBACK": "missing"})
    assert old.rc == 1
    assert (
        "sentinel readback failed: s3://rediacc-releases/cli/v1.0.5/.released is missing "
        "immediately after write" in old.err
    )
    assert_same(old, new)


def test_a_readback_naming_a_different_version_fails_loud(tmp_path: pathlib.Path) -> None:
    old, new = drive(tmp_path, HAPPY, env_extra={"FAKE_READBACK": "wrong"})
    assert old.rc == 1
    assert (
        "sentinel readback content mismatch at s3://rediacc-releases/cli/v1.0.5/.released"
        in old.err
    )
    assert "  wrote version=v1.0.5, read back version=v9.9.9" in old.err
    assert_same(old, new)


# --------------------------------------------------------------------------- Usage errors: exit 2, every one ---------------------------------------------------------------------------


def test_an_unknown_flag_is_exit_2(tmp_path: pathlib.Path) -> None:
    old, new = drive(tmp_path, ["--bogus", "x"])
    assert old.rc == 2
    assert old.err == "✗ unknown flag: --bogus\n"
    assert old.log == "", "nothing may reach aws before the arguments are valid"
    assert_same(old, new)


def test_each_required_flag_is_named_when_absent(tmp_path: pathlib.Path) -> None:
    cases = {
        "--version required": ["--channel", "edge", "--commit-sha", "abc"],
        "--channel required": ["--version", "1.0.5", "--commit-sha", "abc"],
        "--commit-sha required": ["--version", "1.0.5", "--channel", "edge"],
    }
    for message, args in cases.items():
        old, new = drive(tmp_path, args)
        assert old.rc == 2, message
        assert old.err == "✗ %s\n" % message
        assert_same(old, new)


def test_a_non_release_channel_is_refused(tmp_path: pathlib.Path) -> None:
    """A PR channel must never get a sentinel: the sentinel is what makes a
    version permanently unoverwritable."""
    old, new = drive(tmp_path, ["--version", "1.0.5", "--channel", "pr-7", "--commit-sha", "abc"])
    assert old.rc == 2
    assert old.err == (
        "✗ sentinel write is only valid on release channels (edge|stable); got: pr-7\n"
    )
    assert old.log == ""
    assert_same(old, new)


def test_a_flag_with_no_value_exits_1_in_silence(tmp_path: pathlib.Path) -> None:
    """FINDING 5, REPRODUCED NOT FIXED.

    `VERSION="${2:-}"; shift 2` with one argument left: `shift 2` returns
    non-zero, `set -e` fires, and the script dies with exit 1 and NOTHING on
    either stream. The documented behaviour for a usage error is exit 2 with a
    `log_error` line. Every one of the three flags does it.
    """
    for flag in ("--version", "--channel", "--commit-sha"):
        old, new = drive(tmp_path, [flag])
        assert old.rc == 1, flag
        assert old.out == ""
        assert old.err == "", "the silence is the finding"
        assert old.log == ""
        assert_same(old, new)


def test_missing_credentials_are_named_one_at_a_time(tmp_path: pathlib.Path) -> None:
    """`require_var` refuses on the FIRST absent variable, so a run with none of
    the three set names only the first. Reproduced rather than improved."""
    old, new = drive(tmp_path, HAPPY, creds={})
    assert old.rc == 1
    assert old.err == ("✗ Required environment variable 'CLOUDFLARE_R2_ACCESS_KEY_ID' is not set\n")
    assert_same(old, new)

    partial = {"CLOUDFLARE_R2_ACCESS_KEY_ID": "k", "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "s"}
    old, new = drive(tmp_path, HAPPY, creds=partial)
    assert old.rc == 1
    assert old.err == ("✗ Required environment variable 'CLOUDFLARE_R2_ENDPOINT' is not set\n")
    assert_same(old, new)


def test_an_empty_credential_counts_as_absent(tmp_path: pathlib.Path) -> None:
    """`[[ -z "${!var_name:-}" ]]` is an EMPTINESS test, so an exported empty
    string refuses. A port using `"X" in os.environ` would sail past it and hand
    an empty key to aws."""
    creds = dict(CREDS)
    creds["CLOUDFLARE_R2_SECRET_ACCESS_KEY"] = ""
    old, new = drive(tmp_path, HAPPY, creds=creds)
    assert old.rc == 1
    assert "CLOUDFLARE_R2_SECRET_ACCESS_KEY" in old.err
    assert_same(old, new)


def test_a_missing_aws_refuses_identically(tmp_path: pathlib.Path) -> None:
    lean = tmp_path / "leanbin"
    lean.mkdir()
    for tool in ("bash", "jq", "sed", "cat", "env", "python3", "dirname", "uname", "date"):
        found = shutil.which(tool)
        if found:
            (lean / tool).symlink_to(found)
    env = diff.env_for(PATH=str(lean), **CREDS)
    quoted = " ".join("'%s'" % a for a in HAPPY)
    old = diff.bash_streams("bash %s %s" % (TWIN, quoted), env=env, timeout=30)
    env_new = dict(env)
    env_new["PYTHONPATH"] = str(ROOT / ".ci")
    env_new["PYTHONDONTWRITEBYTECODE"] = "1"
    new = diff.bash_streams("python3 -m %s %s" % (MODULE, quoted), env=env_new, timeout=30)
    assert old[0] == 1
    assert new[0] == 1
    assert old[2] == "✗ Required command 'aws' is not available\n"
    assert new[2] == old[2]


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_parse_flags_accepts_any_order_and_lets_the_last_win() -> None:
    assert port.parse_flags(["--channel", "edge", "--version", "1.0.0", "--commit-sha", "s"]) == (
        "1.0.0",
        "edge",
        "s",
    )
    assert port.parse_flags(["--version", "1", "--version", "2"]) == ("2", "", "")
    assert port.parse_flags([]) == ("", "", "")


def test_parse_flags_refuses_an_unknown_flag_before_reading_its_value() -> None:
    with pytest.raises(port.UsageError) as caught:
        port.parse_flags(["--nope", "x"])
    assert caught.value.message == "unknown flag: --nope"


def test_parse_flags_reproduces_the_shift_trap() -> None:
    for flag in ("--version", "--channel", "--commit-sha"):
        with pytest.raises(port._ShiftFailedError):
            port.parse_flags([flag])


def test_build_payload_is_jqs_bytes_not_pythons() -> None:
    got = port.build_payload("v1.2.3", "edge", "sha", "cli", "2026-01-01T00:00:00Z")
    assert got == (
        '{"version":"v1.2.3","channel":"edge","commit_sha":"sha","product":"cli",'
        '"released_at":"2026-01-01T00:00:00Z","artifacts_produced":["cli"]}'
    )


def test_build_payload_escapes_through_jq_not_through_python() -> None:
    """A commit message is not the input here, but a channel or version could
    still carry a quote through a mis-quoted caller. jq owns the escaping."""
    got = port.build_payload('v"1', "edge", "a\\b", "cli", "2026-01-01T00:00:00Z")
    assert json.loads(got)["version"] == 'v"1'
    assert json.loads(got)["commit_sha"] == "a\\b"


def test_released_at_now_matches_the_date_format_the_twin_uses() -> None:
    """Compared against `date -u` ITSELF, run here, rather than against a format
    string copied from the twin by eye."""
    from_date = subprocess.run(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], capture_output=True, text=True, check=True
    ).stdout.strip()
    got = port.released_at_now()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", got)
    assert len(got) == len(from_date)
    assert got[:14] == from_date[:14], "same century, year, month and day-hour prefix"


# --------------------------------------------------------------------------- The control: a planted defect must turn this suite red ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_differential(tmp_path: pathlib.Path) -> None:
    """Delete the empty-prefix refusal from a COPY of the port.

    That check is the only thing standing between a cancelled upload and the
    corrupt sealed-but-empty state, and it is invisible on every healthy run:
    a port without it agrees with the twin on the happy path and every usage
    error, and disagrees only against a scrubbed prefix.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    anchor = """    if bin_count <= 0:
        raise SentinelFailedError("""
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken = tmp_path / "write_release_sentinel_broken.py"
    broken.write_text(
        source.replace(anchor, """    if False:\n        raise SentinelFailedError("""),
        encoding="utf-8",
    )

    old, new = drive(tmp_path, HAPPY, env_extra={"FAKE_BINCOUNT": "0"}, port_file=broken)
    assert old.rc == 1, "the twin must refuse an empty prefix"
    assert new.rc != old.rc or new.payload != old.payload, (
        "PLANT DID NOT FIRE: this differential is vacuous"
    )
    assert new.payload is not None, "the broken port sealed an empty prefix, as designed"
    good_old, good_new = drive(tmp_path, HAPPY, env_extra={"FAKE_BINCOUNT": "0"})
    assert_same(good_old, good_new)


def test_a_port_that_skipped_the_readback_is_caught_by_the_call_log(
    tmp_path: pathlib.Path,
) -> None:
    """The second control, aimed at the assertion nothing else covers.

    Removing the readback changes NO stdout byte, NO stderr byte, NO exit code
    and NO uploaded payload on a healthy run. Only the aws call log differs,
    which is why it is compared.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    anchor = "    readback = rsv.get_sentinel_payload(product, version_tag)"
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken = tmp_path / "write_release_sentinel_noreadback.py"
    broken.write_text(source.replace(anchor, "    readback = payload"), encoding="utf-8")

    old, new = drive(tmp_path, HAPPY, port_file=broken)
    assert old.rc == new.rc == 0, "the defect is invisible to the exit code"
    assert _normalise_err(old.err) == _normalise_err(new.err), "and to stderr"
    assert _normalise_payload(old.payload) == _normalise_payload(new.payload)
    assert new.log != old.log, "PLANT DID NOT FIRE: the aws call log is not being compared"
