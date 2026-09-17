"""Differential: `rediacc_ci.deploy.set_account_worker_secrets` against its twin
`.ci/scripts/deploy/set-account-worker-secrets.sh`.

A RECORDING FAKE `npx` ON A SCRATCH PATH. Nothing here reaches Cloudflare: the fake logs its exact argv AND the bytes on its stdin, and every case uses fixture values two characters long. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This
is that piece.

THE DOCUMENT IS THE ONLY EVIDENCE ON THE HAPPY PATH, exactly as for the www sibling: the twin prints nothing of its own when it succeeds. On THIS script that matters more, because this one DECIDES rather than marshals. A port that picked the edge bucket on stable, kept the ASIA region's SES credential instead of borrowing EU's, or shipped an endpoint without its jurisdiction label
would exit 0 with byte-identical streams and break a region at runtime. Every case that reaches wrangler therefore asserts the recorded stdin.

THE GUARD NAME IS NOT ALWAYS THE VARIABLE TO BLANK, and `GUARD_SOURCE` below is where that is written down. Four of the seventeen guards report a Worker key (`AWS_SES_ACCESS_KEY_ID`) whose value came from a suffixed name (`AWS_SES_ACCESS_KEY_ID_EU`), so a test that blanked the reported name would drive nothing at all and pass while proving nothing.

FIVE STALENESS ALARMS RE-DERIVE THE TWIN'S OWN LISTS from its source, because `KEYS`, `REQUIRED_NONEMPTY`, `REQUIRED_NONEMPTY_STABLE`, `MISSING_MESSAGES` and `SUFFIXED_PREFIXES` are all copies of something the twin states.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import set_account_worker_secrets as port
from rediacc_ci.deploy import set_preview_worker_secrets as preview
from rediacc_ci.deploy import set_www_worker_secrets as www

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "set-account-worker-secrets.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "set_account_worker_secrets.py"
BASH = shutil.which("bash") or "/bin/bash"

# A complete stable EU deploy: the seventeen values the twin refuses to go without on that channel, plus the three control variables and the bucket.
FIXTURE_ENV = {
    "WORKER_NAME": "rediacc-account-eu",
    "TARGET": "stable",
    "SUFFIX": "EU",
    "ACCOUNT_ED25519_PRIVATE_KEY": "e1",
    "ACCOUNT_ED25519_PUBLIC_KEY": "e2",
    "ACCOUNT_X25519_PRIVATE_KEY": "x1",
    "ACCOUNT_X25519_PUBLIC_KEY": "x2",
    "ACCOUNT_SERVER_API_KEY": "ak",
    "ACCOUNT_JWT_SECRET": "jw",
    "ROOT_EMAIL": "root@example.invalid",
    "AWS_SES_ACCESS_KEY_ID_EU": "sk-eu",
    "AWS_SES_SECRET_ACCESS_KEY_EU": "ss-eu",
    "AWS_SES_REGION": "eu-central-1",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": "ts",
    "OBS_OTLP_CREDENTIALS_EU": "otlp-eu",
    "ACCOUNT_BACKUP_S3_ENDPOINT": "https://acct.r2.cloudflarestorage.com",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": "bk",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": "bs",
    "BACKUP_BUCKET_STABLE": "rediacc-backups-eu",
    "BACKUP_BUCKET_EDGE": "edge-rediacc-backups-eu",
    "R2_JURISDICTION": "eu",
    "STRIPE_SECRET_KEY": "sk_live_fixture",
    "STRIPE_WEBHOOK_SECRET_EU": "whsec_eu",
}

# The variable to BLANK in order to make a given guard fire, under SUFFIX=EU.
# For four of them it is not the name the guard prints; see the module docstring.
GUARD_SOURCE = {
    "ACCOUNT_ED25519_PRIVATE_KEY": "ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_ED25519_PUBLIC_KEY": "ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_X25519_PRIVATE_KEY": "ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY": "ACCOUNT_X25519_PUBLIC_KEY",
    "ACCOUNT_SERVER_API_KEY": "ACCOUNT_SERVER_API_KEY",
    "ACCOUNT_JWT_SECRET": "ACCOUNT_JWT_SECRET",
    "ROOT_EMAIL": "ROOT_EMAIL",
    "AWS_SES_ACCESS_KEY_ID": "AWS_SES_ACCESS_KEY_ID_EU",
    "AWS_SES_SECRET_ACCESS_KEY": "AWS_SES_SECRET_ACCESS_KEY_EU",
    "AWS_SES_REGION": "AWS_SES_REGION",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": "CLOUDFLARE_TURNSTILE_SECRET_KEY",
    "OBS_OTLP_CREDENTIALS": "OBS_OTLP_CREDENTIALS_EU",
    "ACCOUNT_BACKUP_S3_ENDPOINT": "ACCOUNT_BACKUP_S3_ENDPOINT",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY",
    "STRIPE_SECRET_KEY": "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET": "STRIPE_WEBHOOK_SECRET_EU",
}

FAKE_NPX = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
payload = sys.stdin.read()
log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("npx\\t" + "\\t".join(argv) + "\\n")
    fh.write("STDIN<<<" + payload + ">>>\\n")

rc = int(os.environ.get("FAKE_NPX_RC", "0"))
if rc:
    sys.stderr.write("wrangler: failed to set secrets\\n")
    sys.exit(rc)
sys.stdout.write("Finished processing secrets JSON file.\\n")
"""

# `jq` is a real prerequisite of BOTH sides, and `uname` / `dirname` are what `common.sh` needs at source time. Nothing else is on the scratch PATH.
PATH_MINIMUM = ("jq", "uname", "dirname")


def _bin(tmp_path: pathlib.Path, name: str, *, drop: str = "") -> str:
    stub = tmp_path / name
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        if real_name == drop:
            continue
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    if drop != "npx":
        npx = stub / "npx"
        npx.write_text(FAKE_NPX, encoding="utf-8")
        npx.chmod(0o755)
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def _run(
    subject: pathlib.Path,
    tmp_path: pathlib.Path,
    *,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    side = "old" if subject.suffix == ".sh" else "new"
    call_log = tmp_path / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin", drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        **FIXTURE_ENV,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, **kw):
    old, old_calls = _run(TWIN, tmp_path, **kw)
    new, new_calls = _run(PORT, tmp_path, **kw)
    return old, new, old_calls, new_calls


def _assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )
    if old_calls is not None:
        assert new_calls == old_calls, (
            f"{label}: the wrangler call or its document diverged:\n"
            f"old: {old_calls!r}\nnew: {new_calls!r}"
        )


def document(calls: str) -> str:
    """The bytes the recorded call put on wrangler's stdin."""
    match = re.search(r"STDIN<<<(.*)>>>\n", calls, re.DOTALL)
    assert match is not None, f"no wrangler call was recorded in {calls!r}"
    return match.group(1)


def _twin_source() -> str:
    return TWIN.read_text(encoding="utf-8")


def test_the_bulk_call_and_its_document_are_pinned_in_full(tmp_path: pathlib.Path) -> None:
    """ONE CALL, PINNED AGAINST LITERAL BYTES. Twenty-nine keys in the twin's
    order, on the stable EU channel: the Stripe pair present, the SES pair fanned in from the EU names, the endpoint carrying its `eu` jurisdiction label, and
    the STABLE bucket rather than the edge one."""
    old, new, old_calls, new_calls = run_both(tmp_path)
    assert old.returncode == 0
    assert old_calls.splitlines()[0] == ("npx\twrangler\tsecret\tbulk\t--name\trediacc-account-eu")
    assert document(old_calls) == (
        "{\n"
        '  "ACCOUNT_ED25519_PRIVATE_KEY": "e1",\n'
        '  "ACCOUNT_ED25519_PUBLIC_KEY": "e2",\n'
        '  "ACCOUNT_X25519_PRIVATE_KEY": "x1",\n'
        '  "ACCOUNT_X25519_PUBLIC_KEY": "x2",\n'
        '  "ACCOUNT_SERVER_API_KEY": "ak",\n'
        '  "ACCOUNT_JWT_SECRET": "jw",\n'
        '  "STRIPE_SECRET_KEY": "sk_live_fixture",\n'
        '  "STRIPE_WEBHOOK_SECRET": "whsec_eu",\n'
        '  "ROOT_EMAIL": "root@example.invalid",\n'
        '  "AWS_SES_ACCESS_KEY_ID": "sk-eu",\n'
        '  "AWS_SES_SECRET_ACCESS_KEY": "ss-eu",\n'
        '  "AWS_SES_REGION": "eu-central-1",\n'
        '  "AWS_SES_FROM": "",\n'
        '  "AWS_SES_CONFIGURATION_SET": "",\n'
        '  "CLOUDFLARE_TURNSTILE_SECRET_KEY": "ts",\n'
        '  "OBS_OTLP_CREDENTIALS": "otlp-eu",\n'
        '  "ACCOUNT_BACKUP_S3_ENDPOINT": "https://acct.eu.r2.cloudflarestorage.com",\n'
        '  "ACCOUNT_BACKUP_S3_BUCKET": "rediacc-backups-eu",\n'
        '  "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": "bk",\n'
        '  "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": "bs",\n'
        '  "SELLER_NAME": "",\n'
        '  "SELLER_VAT_NUMBER": "",\n'
        '  "SELLER_REGISTRATION_NUMBER": "",\n'
        '  "SELLER_ADDRESS_LINE1": "",\n'
        '  "SELLER_ADDRESS_LINE2": "",\n'
        '  "SELLER_CITY": "",\n'
        '  "SELLER_POSTAL_CODE": "",\n'
        '  "SELLER_COUNTRY": "",\n'
        '  "SELLER_EMAIL": ""\n'
        "}\n"
    )
    _assert_agree(old, new, "happy-path", old_calls, new_calls)


def test_a_successful_run_says_nothing_of_its_own(tmp_path: pathlib.Path) -> None:
    """THE PROPERTY THAT MAKES THE DOCUMENT LOAD BEARING, and the reason the
    preview sibling's hard-coded `Set 15 secrets` line has no third occurrence:
    this twin ends on the pipe and prints no closing line at all."""
    old, new, old_calls, new_calls = run_both(tmp_path)
    assert old.stdout == "Finished processing secrets JSON file.\n"
    assert old.stderr == ""
    assert port.SUCCESS_IS_SILENT
    assert "log_info" not in _twin_source(), "the twin grew a closing line; re-read this test"
    _assert_agree(old, new, "silent-success", old_calls, new_calls)


def test_the_edge_channel_blanks_both_stripe_values(tmp_path: pathlib.Path) -> None:
    """DECISION 1. Billing is disabled on edge, so the key and the webhook secret
    are written as EMPTY STRINGS rather than omitted, and neither is demanded. The regional webhook secret is in the environment and must NOT reach the
    document."""
    old, new, old_calls, new_calls = run_both(tmp_path, TARGET="edge")
    assert old.returncode == 0
    doc = document(old_calls)
    assert '"STRIPE_SECRET_KEY": ""' in doc
    assert '"STRIPE_WEBHOOK_SECRET": ""' in doc
    assert "sk_live_fixture" not in doc, "the stable Stripe key leaked onto edge"
    assert "whsec_eu" not in doc, "the regional webhook secret leaked onto edge"
    assert '"ACCOUNT_BACKUP_S3_BUCKET": "edge-rediacc-backups-eu"' in doc
    _assert_agree(old, new, "edge-blanks-stripe", old_calls, new_calls)


def test_any_target_that_is_not_stable_is_the_edge_channel(tmp_path: pathlib.Path) -> None:
    """THE `if` HAS TWO ARMS AND NO THIRD. A typo in TARGET does not refuse; it
    deploys the edge shape, which is worth knowing and is why the port compares
    against the literal `stable` rather than testing for `edge`."""
    old, new, old_calls, new_calls = run_both(tmp_path, TARGET="Stable")
    assert old.returncode == 0
    assert '"STRIPE_SECRET_KEY": ""' in document(old_calls)
    assert '"ACCOUNT_BACKUP_S3_BUCKET": "edge-rediacc-backups-eu"' in document(old_calls)
    _assert_agree(old, new, "target-typo-is-edge", old_calls, new_calls)


def test_asia_borrows_the_eu_ses_credential(tmp_path: pathlib.Path) -> None:
    """DECISION 3. The ASIA pair is read and then DISCARDED: with both pairs
    present, the document must carry EU's. `regions.json` gives asia
    `sesRegion: eu-central-1`, so the borrowed credential and the region agree."""
    asia = {
        "SUFFIX": "ASIA",
        "AWS_SES_ACCESS_KEY_ID_ASIA": "sk-asia",
        "AWS_SES_SECRET_ACCESS_KEY_ASIA": "ss-asia",
        "OBS_OTLP_CREDENTIALS_ASIA": "otlp-asia",
        "STRIPE_WEBHOOK_SECRET_ASIA": "whsec_asia",
        "BACKUP_BUCKET_STABLE": "rediacc-backups-asia",
        "R2_JURISDICTION": "",
    }
    old, new, old_calls, new_calls = run_both(tmp_path, **asia)
    doc = document(old_calls)
    assert '"AWS_SES_ACCESS_KEY_ID": "sk-eu"' in doc, "asia did not borrow the EU key"
    assert '"AWS_SES_SECRET_ACCESS_KEY": "ss-eu"' in doc
    assert "sk-asia" not in doc, "the asia SES key reached the Worker"
    # Only SES is borrowed: OTLP and the webhook secret stay regional.
    assert '"OBS_OTLP_CREDENTIALS": "otlp-asia"' in doc
    assert '"STRIPE_WEBHOOK_SECRET": "whsec_asia"' in doc
    _assert_agree(old, new, "asia-borrow", old_calls, new_calls)


def test_a_region_without_a_jurisdiction_keeps_the_default_host(tmp_path: pathlib.Path) -> None:
    """DECISION 4, the negative half. `regions.json` gives us and asia
    `r2Jurisdiction: null`, which the deploy matrix passes as the empty string."""
    # A `**dict` rather than keyword arguments: ruff's S106 reads a keyword whose NAME looks like a credential as a hardcoded password, and every fan-in name in this file looks exactly like one.
    us = {
        "SUFFIX": "US",
        "R2_JURISDICTION": "",
        "AWS_SES_ACCESS_KEY_ID_US": "sk-us",
        "AWS_SES_SECRET_ACCESS_KEY_US": "ss-us",
        "OBS_OTLP_CREDENTIALS_US": "otlp-us",
        "STRIPE_WEBHOOK_SECRET_US": "whsec_us",
    }
    old, new, old_calls, new_calls = run_both(tmp_path, **us)
    doc = document(old_calls)
    assert '"ACCOUNT_BACKUP_S3_ENDPOINT": "https://acct.r2.cloudflarestorage.com"' in doc
    assert '"AWS_SES_ACCESS_KEY_ID": "sk-us"' in doc
    _assert_agree(old, new, "no-jurisdiction", old_calls, new_calls)


def test_an_endpoint_already_carrying_the_label_is_left_alone(tmp_path: pathlib.Path) -> None:
    """THE SPLICE IS IDEMPOTENT, which is the whole point of the negative clause
    in the twin's condition: a secret already stored in jurisdictional form must
    not become `acct.eu.eu.r2.cloudflarestorage.com`."""
    already = "https://acct.eu.r2.cloudflarestorage.com"
    old, new, old_calls, new_calls = run_both(tmp_path, ACCOUNT_BACKUP_S3_ENDPOINT=already)
    assert f'"ACCOUNT_BACKUP_S3_ENDPOINT": "{already}"' in document(old_calls)
    assert "eu.eu" not in document(old_calls)
    _assert_agree(old, new, "jurisdiction-idempotent", old_calls, new_calls)


def test_a_non_r2_endpoint_is_never_rewritten(tmp_path: pathlib.Path) -> None:
    """The host test is a substring match on the R2 host, so an endpoint pointing
    anywhere else passes through untouched even with a jurisdiction set."""
    other = "https://s3.eu-central-1.amazonaws.com"
    old, new, old_calls, new_calls = run_both(tmp_path, ACCOUNT_BACKUP_S3_ENDPOINT=other)
    assert f'"ACCOUNT_BACKUP_S3_ENDPOINT": "{other}"' in document(old_calls)
    _assert_agree(old, new, "non-r2-endpoint", old_calls, new_calls)


def test_an_empty_bucket_is_refused_on_both_channels(tmp_path: pathlib.Path) -> None:
    """THE BUCKET GUARD, four lines, and it fires BEFORE every `_require_nonempty`
    one. An empty bucket does not throw inside the Worker: it mints presigned URLs
    against bucket "" and every upload 404s at runtime."""
    for target, blank in (("stable", "BACKUP_BUCKET_STABLE"), ("edge", "BACKUP_BUCKET_EDGE")):
        case = tmp_path / f"bucket-{target}"
        case.mkdir()
        old, new, old_calls, new_calls = run_both(case, TARGET=target, **{blank: ""})
        assert old.returncode == 1
        assert old.stdout == ""
        assert old.stderr == (
            f"set-account-worker-secrets.sh: no backup bucket for TARGET={target}.\n"
            "  Expected BACKUP_BUCKET_STABLE / BACKUP_BUCKET_EDGE from the deploy\n"
            "  matrix (regions.json backupR2/edgeBackupR2). Refusing to deploy a\n"
            "  Worker that would presign against an empty bucket name.\n"
        )
        assert old_calls == "", f"{target}: a refused run still called wrangler"
        _assert_agree(old, new, f"bucket-{target}", old_calls, new_calls)


def test_the_bucket_guard_precedes_every_value_guard(tmp_path: pathlib.Path) -> None:
    """ORDER IS OBSERVABLE. With the bucket AND the first secret both empty, the
    message a caller reads is the bucket's."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, BACKUP_BUCKET_STABLE="", ACCOUNT_ED25519_PRIVATE_KEY=""
    )
    assert old.stderr.startswith("set-account-worker-secrets.sh: no backup bucket")
    assert "is EMPTY" not in old.stderr
    _assert_agree(old, new, "bucket-first", old_calls, new_calls)


def test_every_one_of_the_seventeen_guards_fires_with_its_own_name(
    tmp_path: pathlib.Path,
) -> None:
    """SEVENTEEN CASES ON STABLE, ONE PER GUARD, each driven EMPTY rather than
    absent, and each blanking the variable the value really comes from rather
    than the name the guard prints."""
    demanded = port.REQUIRED_NONEMPTY + port.REQUIRED_NONEMPTY_STABLE
    assert len(demanded) == 17
    for name in demanded:
        case = tmp_path / f"guard-{name}"
        case.mkdir()
        old, new, old_calls, new_calls = run_both(case, **{GUARD_SOURCE[name]: ""})
        assert old.returncode == 1, f"{name}: the twin accepted an empty value"
        assert old.stdout == ""
        assert old.stderr == (
            f"set-account-worker-secrets.sh: {name} is EMPTY for "
            "WORKER_NAME=rediacc-account-eu TARGET=stable SUFFIX=EU.\n"
            "  The Worker's schema accepts an empty value and silently disables the feature it\n"
            "  drives, so this refuses to deploy instead. Check the secret store for that name.\n"
        )
        assert old_calls == "", f"{name}: a refused run still called wrangler"
        _assert_agree(old, new, f"guard-{name}", old_calls, new_calls)


def test_the_two_stripe_guards_are_demanded_on_stable_only(tmp_path: pathlib.Path) -> None:
    """THE CONDITIONAL HALF OF THE GUARD LIST, pinned in BOTH directions: the same
    blank value refuses on stable and deploys on edge."""
    for name in port.REQUIRED_NONEMPTY_STABLE:
        blank = {GUARD_SOURCE[name]: ""}

        on_stable = tmp_path / f"stripe-{name}-stable"
        on_stable.mkdir()
        old, new, old_calls, new_calls = run_both(on_stable, **blank)
        assert old.returncode == 1
        assert f"{name} is EMPTY" in old.stderr
        _assert_agree(old, new, f"stripe-stable-{name}", old_calls, new_calls)

        on_edge = tmp_path / f"stripe-{name}-edge"
        on_edge.mkdir()
        old, new, old_calls, new_calls = run_both(on_edge, TARGET="edge", **blank)
        assert old.returncode == 0, f"{name}: edge refused a value it deliberately blanks"
        _assert_agree(old, new, f"stripe-edge-{name}", old_calls, new_calls)


def test_the_first_empty_guard_wins_and_the_rest_never_run(tmp_path: pathlib.Path) -> None:
    blanks = dict.fromkeys(GUARD_SOURCE.values(), "")
    old, new, old_calls, new_calls = run_both(tmp_path, **blanks)
    assert old.stderr.startswith(
        "set-account-worker-secrets.sh: ACCOUNT_ED25519_PRIVATE_KEY is EMPTY"
    )
    assert old.stderr.count("is EMPTY") == 1
    _assert_agree(old, new, "first-guard-wins", old_calls, new_calls)


def test_missing_jq_refuses_before_anything_else(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, drop="jq")
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'jq' is not available\n"
    assert old_calls == ""
    _assert_agree(old, new, "no-jq", old_calls, new_calls)


def test_missing_npx_refuses_after_jq(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, drop="npx")
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'npx' is not available\n"
    _assert_agree(old, new, "no-npx", old_calls, new_calls)


def test_the_tool_checks_run_before_the_three_control_variables(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, drop="jq", drop_env=("WORKER_NAME", "TARGET", "SUFFIX")
    )
    assert old.stderr == "✗ Required command 'jq' is not available\n"
    _assert_agree(old, new, "tools-first", old_calls, new_calls)


def test_divergence_a_the_three_control_variables_are_bashs_own_refusals(
    tmp_path: pathlib.Path,
) -> None:
    """THE FIRST DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE "FIXED"
    BY ACCIDENT. bash names its own FILE and LINE NUMBER and then the twin's message, which already begins with the script name, so the name is printed TWICE. The port prints the `VAR: message` half. Same stream, same status, no
    call from either side."""
    lines = {"WORKER_NAME": 106, "TARGET": 107, "SUFFIX": 108}
    for name, line in lines.items():
        case = tmp_path / f"missing-{name}"
        case.mkdir()
        old, new, old_calls, new_calls = run_both(case, drop_env=(name,))
        expected = f"{name}: set-account-worker-secrets.sh: {name} must be set"
        assert old.returncode == new.returncode == 1
        assert old.stderr.endswith(f"line {line}: {expected}\n"), old.stderr
        assert old.stderr.startswith(str(TWIN)), "bash stopped naming its own file"
        assert new.stderr == expected + "\n"
        assert old.stderr != new.stderr
        assert old.stdout == new.stdout == ""
        assert old_calls == new_calls == ""


def test_the_first_missing_control_variable_wins(tmp_path: pathlib.Path) -> None:
    """ORDER IS OBSERVABLE for the three `:?` refusals too: with all three gone,
    both sides name WORKER_NAME and stop. The expected line is a LITERAL rather than `port.MISSING_MESSAGES[0]`, because reading the order out of the port is
    how a reordered tuple passes its own test."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, drop_env=("WORKER_NAME", "TARGET", "SUFFIX")
    )
    assert old.returncode == new.returncode == 1
    assert old.stderr.endswith("WORKER_NAME must be set\n")
    assert new.stderr == "WORKER_NAME: set-account-worker-secrets.sh: WORKER_NAME must be set\n"
    assert old.stderr.count("must be set") == new.stderr.count("must be set") == 1
    assert old_calls == new_calls == ""


def test_an_empty_control_variable_refuses_exactly_as_an_absent_one(
    tmp_path: pathlib.Path,
) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST. A port checking `"TARGET" in os.environ`
    would sail past this and deploy the edge shape to a stable Worker."""
    for name, message in port.MISSING_MESSAGES:
        case = tmp_path / f"empty-{name}"
        case.mkdir()
        old, new, old_calls, new_calls = run_both(case, **{name: ""})
        assert old.returncode == new.returncode == 1
        assert new.stderr == message + "\n"
        assert old.stderr.endswith(message + "\n")
        assert old_calls == new_calls == "", f"{name}: an empty value still reached wrangler"


def test_divergence_b_a_suffix_that_is_not_an_identifier(tmp_path: pathlib.Path) -> None:
    """THE SECOND DIVERGENCE. `${!var}` refuses a constructed name bash cannot
    parse, and WHICH name it is depends on the channel: the Stripe webhook is evaluated first on stable, the SES key first on edge. Both sides exit 1 with
    the same sentence; only bash's file-and-line prefix differs."""
    cases = (
        ("stable", "STRIPE_WEBHOOK_SECRET_EU-1", 115),
        ("edge", "AWS_SES_ACCESS_KEY_ID_EU-1", 124),
    )
    for target, name, line in cases:
        case = tmp_path / f"badsuffix-{target}"
        case.mkdir()
        old, new, old_calls, new_calls = run_both(case, TARGET=target, SUFFIX="EU-1")
        assert old.returncode == new.returncode == 1
        assert old.stderr == f"{TWIN}: line {line}: {name}: invalid variable name\n"
        assert new.stderr == f"{name}: invalid variable name\n"
        assert old.stdout == new.stdout == ""
        assert old_calls == new_calls == ""


def test_divergence_b_an_array_subscript_suffix_is_the_one_shape_not_reproduced(
    tmp_path: pathlib.Path,
) -> None:
    """THE COROLLARY, NAMED RATHER THAN HIDDEN AND MEASURED RATHER THAN REASONED
    ABOUT. bash accepts an ARRAY REFERENCE as the target of `${!var}`, and a
    SCALAR answers to subscript 0, so `SUFFIX=EU[0]` reads
    `AWS_SES_ACCESS_KEY_ID_EU[0]`, which is the EU credential itself: the twin DEPLOYS, exit 0, with a perfectly ordinary document. The port refuses.

    Unreachable in production, since SUFFIX is `regions.json`'s `secretSuffix`, one of EU / US / ASIA. Asserted so a later reader finds the divergence written down instead of discovering it, and so nobody "fixes" the identifier rule without reading this. It is also the safe direction: the port refuses
    where the twin would deploy."""
    old, new, old_calls, new_calls = run_both(tmp_path, TARGET="edge", SUFFIX="EU[0]")
    assert old.returncode == 0, "bash no longer resolves the subscript form"
    assert "invalid variable name" not in old.stderr
    assert '"AWS_SES_ACCESS_KEY_ID": "sk-eu"' in document(old_calls), (
        "the subscript resolved to something other than the scalar's own value"
    )
    assert new.returncode == 1
    assert new.stderr == "AWS_SES_ACCESS_KEY_ID_EU[0]: invalid variable name\n"
    assert new_calls == "", "the port must not call wrangler when it refuses"


def test_a_wrangler_failure_ends_the_run_with_its_status(tmp_path: pathlib.Path) -> None:
    """PIPEFAIL, the right-hand half, and the reason the twin's header says
    `-uo pipefail` were added: a jq failure used to be hidden because wrangler's
    status won."""
    old, new, old_calls, new_calls = run_both(tmp_path, FAKE_NPX_RC="7")
    assert old.returncode == 7
    assert old.stderr == "wrangler: failed to set secrets\n"
    assert old.stdout == ""
    _assert_agree(old, new, "wrangler-fails", old_calls, new_calls)


def test_a_value_with_quotes_and_newlines_survives_intact(tmp_path: pathlib.Path) -> None:
    awkward = {"SELLER_ADDRESS_LINE1": 'a"b\nc\\d', "STRIPE_WEBHOOK_SECRET_EU": "wh\tsec"}
    old, new, old_calls, new_calls = run_both(tmp_path, **awkward)
    doc = document(old_calls)
    assert '"SELLER_ADDRESS_LINE1": "a\\"b\\nc\\\\d"' in doc
    assert '"STRIPE_WEBHOOK_SECRET": "wh\\tsec"' in doc
    _assert_agree(old, new, "escaping", old_calls, new_calls)


def test_a_non_ascii_secret_is_byte_identical_through_both(tmp_path: pathlib.Path) -> None:
    """WHY `jq` IS CALLED RATHER THAN REIMPLEMENTED: `json.dumps` would emit
    `\\uXXXX` here and jq emits raw UTF-8. A secret is opaque bytes chosen by
    someone else."""
    old, new, old_calls, new_calls = run_both(tmp_path, SELLER_CITY="Zürich \x7f")
    assert '"SELLER_CITY": "Zürich \\u007f"' in document(old_calls)
    _assert_agree(old, new, "non-ascii", old_calls, new_calls)


def test_the_key_list_is_the_twins_key_list() -> None:
    """STALENESS ALARM. `KEYS` is a copy of the twin's `--arg` list, re-derived
    from the twin's source, in order, and in BOTH shapes: a direct
    `"${ENV:-}"` read and a `"$local"` computed value. The third field of each
    `KEYS` row is asserted to say which of the two it was."""
    pairs = re.findall(r'--arg (\w+) "(?:\$\{(\w+):-\}|\$(\w+))"', _twin_source())
    assert pairs, "the --arg shape changed; this alarm is no longer reading anything"
    assert [(var, env) for var, env, _local in pairs] == [
        (var, source) for _key, var, source in port.KEYS
    ]
    computed = [var for var, env, _local in pairs if not env]
    assert len(computed) == 7, "the set of COMPUTED values changed; re-read `resolve`"

    body = re.search(r"'\{(.*?)\}'", _twin_source(), re.DOTALL)
    assert body is not None
    built = re.findall(r"(\w+): \$(\w+)", body.group(1))
    assert built == [(key, var) for key, var, _source in port.KEYS]


def test_the_guard_lists_are_the_twins_guard_lists() -> None:
    """STALENESS ALARM for the `_require_nonempty` calls, and for the SPLIT
    between the unconditional fifteen (column 0) and the two the twin indents
    inside `if [[ "$TARGET" == "stable" ]]`."""
    src = _twin_source()
    always = re.findall(r'^_require_nonempty (\w+) "', src, re.MULTILINE)
    conditional = re.findall(r'^    _require_nonempty (\w+) "', src, re.MULTILINE)
    assert always, "the _require_nonempty shape changed; this alarm reads nothing"
    assert conditional, "the stable-only guards are no longer indented; re-read this alarm"
    assert tuple(always) == port.REQUIRED_NONEMPTY
    assert tuple(conditional) == port.REQUIRED_NONEMPTY_STABLE
    assert set(GUARD_SOURCE) == set(always) | set(conditional)


def test_the_control_variables_are_the_twins_control_variables() -> None:
    """STALENESS ALARM for the three `${VAR:?message}` refusals, in order, with
    the twin's own message text, doubled script name and all."""
    found = re.findall(r': "\$\{(\w+):\?([^}]*)\}"', _twin_source())
    assert found, "the :? shape changed; this alarm reads nothing"
    assert [(name, f"{name}: {message}") for name, message in found] == list(port.MISSING_MESSAGES)


def test_the_four_region_fan_ins_are_the_twins_fan_ins() -> None:
    """STALENESS ALARM for the constructed names. A find-and-replace cannot see
    `${!var}`, so the day a fifth fan-in lands, or a suffix is dropped, this is
    the thing that notices."""
    found = re.findall(r'^\s*\w+_var="(\w+)_\$\{SUFFIX\}"$', _twin_source(), re.MULTILINE)
    assert tuple(found) == port.SUFFIXED_PREFIXES


def test_the_asia_borrow_names_are_the_twins_names() -> None:
    src = _twin_source()
    for name in port.ASIA_BORROWS:
        assert f'"${{{name}:-}}"' in src, f"{name} is no longer the borrowed value"
    assert f'"$SUFFIX" == "{port.ASIA}"' in src


def test_the_three_sibling_scripts_are_not_the_same_script() -> None:
    """THE ASSUMPTION THAT WOULD PORT THIS ONE WRONG, refuted in one place. This
    is the only member of the family that decides anything, and every difference
    below is driven by a test above."""
    assert len(port.KEYS) == 29
    assert len(www.KEYS) == 24
    assert len(preview.KEYS) == 15
    assert len(port.REQUIRED_NONEMPTY) == 15
    assert len(port.REQUIRED_NONEMPTY_STABLE) == 2
    # Neither sibling has a conditional guard list, a channel, or a fan-in.
    assert not hasattr(www, "REQUIRED_NONEMPTY_STABLE")
    assert not hasattr(preview, "REQUIRED_NONEMPTY_STABLE")
    assert not hasattr(www, "SUFFIXED_PREFIXES")
    assert not hasattr(preview, "SUFFIXED_PREFIXES")
    # The explanation under a failed guard is www's, not the preview's.
    assert port.GUARD_EXPLANATION == www.GUARD_EXPLANATION
    assert port.GUARD_EXPLANATION != preview.GUARD_EXPLANATION
    # The four backup-plane keys are this script's alone.
    backup = [key for key, _var, _source in port.KEYS if key.startswith("ACCOUNT_BACKUP_")]
    assert len(backup) == 4
    assert not [key for key, _var in www.KEYS if key.startswith("ACCOUNT_BACKUP_")]
    # OBS_OTLP_CREDENTIALS too: neither sibling carries telemetry credentials.
    assert "OBS_OTLP_CREDENTIALS" in [key for key, _var, _source in port.KEYS]
    assert "OBS_OTLP_CREDENTIALS" not in [key for key, _var in www.KEYS]


def test_the_guard_label_defect_has_no_third_occurrence() -> None:
    """`set-preview-worker-secrets.sh:53` prints `WORKER_NAME=` for a script whose
    variable is `WORKER`, inherited verbatim from the www twin. This twin really does have WORKER_NAME, and prints TARGET and SUFFIX beside it, so every label
    in its guard message names a variable it holds."""
    assert preview.GUARD_LABEL_SAYS_WORKER_NAME
    assert "WORKER_NAME" not in preview.__doc__.split("K=5 LEDGER")[0].split("1. THE GUARD")[0]
    src = _twin_source()
    guard = re.search(r'^    local name="\$1" value="\$2"$', src, re.MULTILINE)
    assert guard is not None
    for label in ("WORKER_NAME=$WORKER_NAME", "TARGET=$TARGET", "SUFFIX=$SUFFIX"):
        assert label in src, f"{label} is no longer in the guard message"
        variable = label.split("=$")[1]
        assert f'"${{{variable}:?' in src or f'{variable}="' in src, (
            f"{variable} is printed but never set"
        )


def test_pure_helpers() -> None:
    assert port.SELF == "set-account-worker-secrets.sh"

    # apply_jurisdiction, all four arms.
    plain = "https://acct.r2.cloudflarestorage.com"
    assert port.apply_jurisdiction(plain, "") == plain
    assert port.apply_jurisdiction(plain, "eu") == "https://acct.eu.r2.cloudflarestorage.com"
    labelled = "https://acct.eu.r2.cloudflarestorage.com"
    assert port.apply_jurisdiction(labelled, "eu") == labelled
    assert port.apply_jurisdiction("https://s3.amazonaws.com", "eu") == "https://s3.amazonaws.com"

    # indirect, both outcomes.
    assert port.indirect({"OBS_OTLP_CREDENTIALS_US": "v"}, "OBS_OTLP_CREDENTIALS", "US") == "v"
    assert port.indirect({}, "OBS_OTLP_CREDENTIALS", "US") == ""
    with pytest.raises(port.ScriptRefusalError) as caught:
        port.indirect({}, "OBS_OTLP_CREDENTIALS", "U-S")
    assert caught.value.lines == ["OBS_OTLP_CREDENTIALS_U-S: invalid variable name"]
    assert caught.value.code == 1

    argv = port.jq_argv({"seller_city": "Delft"})
    assert argv[:2] == ["jq", "-n"]
    assert argv.count("--arg") == 29
    assert "Delft" in argv
    assert argv[2:5] == ["--arg", "ed25519_priv", ""], "an absent value is the empty string"
    assert argv[-1].startswith("{ACCOUNT_ED25519_PRIVATE_KEY: $ed25519_priv")
    assert argv[-1].endswith("SELLER_EMAIL: $seller_email}")

    assert port.wrangler_argv("rediacc-account-us") == [
        "npx",
        "wrangler",
        "secret",
        "bulk",
        "--name",
        "rediacc-account-us",
    ]

    guard = port.GuardError("OBS_OTLP_CREDENTIALS", "w", "stable", "US")
    assert guard.lines[0] == (
        "set-account-worker-secrets.sh: OBS_OTLP_CREDENTIALS is EMPTY for "
        "WORKER_NAME=w TARGET=stable SUFFIX=US."
    )
    assert len(guard.lines) == 3


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on THE DECISION rather than on a key: the mutant
    picks the EDGE bucket on the stable channel. That is the exact defect the twin's header records as already having happened once in the other direction (one global bucket secret against six per-region bindings), and it is invisible everywhere a reader would look -- exit 0 on both sides, the same stdout, the same empty stderr. Only the document shows it. Driven red, then
    the source is confirmed byte-identical and green again."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        "    bucket_var = BUCKET_VAR_STABLE if target == STABLE else BUCKET_VAR_EDGE\n",
        "    bucket_var = BUCKET_VAR_EDGE\n",
        1,
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    old, old_calls = _run(TWIN, tmp_path)
    bad, bad_calls = _run(mutant, tmp_path)
    assert bad.returncode == old.returncode == 0, (
        "the plant is invisible in the exit code, which is why the document is compared"
    )
    assert bad.stdout == old.stdout, "the plant is invisible on stdout"
    assert bad.stderr == old.stderr, (
        "the plant is invisible on stderr too: this script says nothing when it works"
    )
    assert '"ACCOUNT_BACKUP_S3_BUCKET": "rediacc-backups-eu"' in document(old_calls)
    assert '"ACCOUNT_BACKUP_S3_BUCKET": "edge-rediacc-backups-eu"' in document(bad_calls)
    assert (
        hashlib.sha256(document(bad_calls).encode()).hexdigest()
        != hashlib.sha256(document(old_calls).encode()).hexdigest()
    )

    _good, good_calls = _run(PORT, tmp_path)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
