"""`scripts/ops/r2-oneshot-scrub.sh` against a fake object-store CLI: an empty prefix is empty, a failed listing is a failure.

EVERY LISTING GOES THROUGH `s3_ls`, which follows `simulate-promotion.sh:185-207`: `aws s3 ls` exits 1 with nothing on stderr for a prefix that holds no objects, and that one shape is an empty listing. Before it, all six listing sites ran `aws s3 ls ... 2>/dev/null | awk` behind `|| true` or `set +e`, so an expired credential read as "empty or missing" on every prefix, aws's
message went to /dev/null, and the scrub ended in "Done." with exit 0. `test_a_failed_listing_stops_the_scrub_and_shows_awss_message` is the control for that: it is red against the pre-fix script.

THE PATH IS REPLACED, NEVER PREPENDED, so no real `aws` or `gh` on this machine is reachable: the fake directory holds the fakes and symlinks to the coreutils the subject needs. The subject runs in its default dry-run, so even the fake is never asked to delete.
"""

from __future__ import annotations

import shutil
import subprocess
import typing

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
SUBJECT = ROOT / "scripts" / "ops" / "r2-oneshot-scrub.sh"
BASH = shutil.which("bash") or "/bin/bash"

FAKE_AWS = """#!/bin/bash
echo "aws $*" >>"$FAKE_LOG"
case "$1 $2" in
    "s3 ls")
        [[ -n "${FAKE_LS_OUT:-}" ]] && printf '%s\\n' "$FAKE_LS_OUT"
        [[ -n "${FAKE_LS_ERR:-}" ]] && printf '%s\\n' "$FAKE_LS_ERR" >&2
        exit "${FAKE_LS_RC:-1}"
        ;;
    "s3api list-multipart-uploads") echo "[]"; exit 0 ;;
    "s3api head-object") exit 254 ;;
esac
exit 0
"""

FAKE_GH = "#!/bin/bash\nexit 1\n"

PATH_MINIMUM = (
    "dirname",
    "date",
    "mktemp",
    "rm",
    "cat",
    "sed",
    "awk",
    "grep",
    "tail",
    "head",
    "sort",
    "wc",
    "tr",
    "uname",
    "jq",
)


def _run(tmp_path: pathlib.Path, **extra: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    for name in PATH_MINIMUM:
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    for name, body in (("aws", FAKE_AWS), ("gh", FAKE_GH)):
        fake = stub / name
        fake.write_text(body, encoding="utf-8")
        fake.chmod(0o755)
    assert shutil.which("aws", path=str(stub)) == str(stub / "aws")
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": str(stub),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "LC_ALL": "C",
        "NO_COLOR": "1",
        "FAKE_LOG": str(log),
        "CLOUDFLARE_R2_ACCESS_KEY_ID": "fake",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "fake",
        "CLOUDFLARE_R2_ENDPOINT": "http://fake.invalid",
    }
    env.update(extra)
    proc = subprocess.run(
        [BASH, str(SUBJECT)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    calls = [c for c in log.read_text(encoding="utf-8").splitlines() if c]
    return proc, calls


def test_every_listing_site_is_reached_on_empty_prefixes(tmp_path: pathlib.Path) -> None:
    """Exit 1 with nothing on stderr is an empty prefix: the scrub walks every stage and ends in Done, exit 0."""
    proc, calls = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.rstrip("\n").endswith("Done."), proc.stderr
    listings = [c for c in calls if c.startswith("aws s3 ls ")]
    assert any("--summarize" in c for c in listings), "describe_prefix never listed"
    assert any(c.startswith("aws s3 ls s3://rediacc-releases/desktop/v1.0.1/ ") for c in listings)
    assert any("s3://rediacc-releases/apt/stable/ --recursive" in c for c in listings)
    assert "(empty or missing: desktop/)" in proc.stderr


def test_summarize_totals_alone_are_still_an_empty_prefix(tmp_path: pathlib.Path) -> None:
    proc, _calls = _run(
        tmp_path, FAKE_LS_RC="1", FAKE_LS_OUT="\nTotal Objects: 0\n   Total Size: 0 Bytes"
    )
    assert proc.returncode == 0, proc.stderr
    assert "(empty or missing: staging/)" in proc.stderr
    assert "Would delete s3://rediacc-releases/staging/" not in proc.stderr


def test_a_failed_listing_stops_the_scrub_and_shows_awss_message(tmp_path: pathlib.Path) -> None:
    """THE CONTROL. Before `s3_ls`, this ran to "Done." with exit 0 and no trace of the error."""
    proc, calls = _run(
        tmp_path,
        FAKE_LS_RC="255",
        FAKE_LS_ERR="An error occurred (InvalidAccessKeyId) when calling the ListObjectsV2 operation",
    )
    assert proc.returncode == 255, proc.stderr
    assert "InvalidAccessKeyId" in proc.stderr, "aws's own message was swallowed"
    assert "failed (exit 255)" in proc.stderr
    assert "Done." not in proc.stderr
    assert len([c for c in calls if c.startswith("aws s3 ls ")]) == 1, "the scrub went on listing"


def test_exit_1_with_a_message_is_a_failure_not_an_empty_prefix(tmp_path: pathlib.Path) -> None:
    proc, _calls = _run(
        tmp_path, FAKE_LS_RC="1", FAKE_LS_ERR="Could not connect to the endpoint URL"
    )
    assert proc.returncode == 1
    assert "Could not connect to the endpoint URL" in proc.stderr
    assert "Done." not in proc.stderr


def test_a_listing_with_objects_reaches_the_dry_run_plan(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY: a non-empty listing still drives every stage to its would-delete line, so the empty cases above are not passing because nothing is ever parsed."""
    listing = (
        "2020-01-01 00:00:00         12 apt/stable/rediacc-cli_0.0.0-dev_amd64.deb\n"
        "                           PRE pr-5/\n"
        "                           PRE dryrun-9/\n"
        "Total Objects: 1"
    )
    proc, _calls = _run(tmp_path, FAKE_LS_RC="0", FAKE_LS_OUT=listing)
    assert proc.returncode == 0, proc.stderr
    assert "[DRY-RUN] Would delete s3://rediacc-releases/cli/dryrun-9/" in proc.stderr
    assert "[DRY-RUN] Would reap cli/pr-5/ (stale" in proc.stderr
    assert "0.0.0-dev pollution" in proc.stderr
    assert "Done." in proc.stderr


def test_the_default_dry_run_deletes_nothing(tmp_path: pathlib.Path) -> None:
    """Stage 2c's `aws s3 rm` of stale pr-N/ prefixes once had no DRY_RUN guard, so the DEFAULT run of a script documented as dry-run-by-default deleted them. Red against that script: the call log held one `s3 rm` per format."""
    listing = "2020-01-01 00:00:00         12 cli/pr-5/rdc\n                           PRE pr-5/"
    proc, calls = _run(tmp_path, FAKE_LS_RC="0", FAKE_LS_OUT=listing)
    assert proc.returncode == 0, proc.stderr
    removals = [c for c in calls if c.startswith("aws s3 rm ") or "delete" in c.split(" ")[:3]]
    assert removals == [], removals
