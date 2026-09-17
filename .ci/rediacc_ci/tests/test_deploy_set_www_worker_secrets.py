"""Differential: `rediacc_ci.deploy.set_www_worker_secrets` against its twin
`.ci/scripts/deploy/set-www-worker-secrets.sh`.

A RECORDING FAKE `npx` ON A SCRATCH PATH. Nothing here reaches Cloudflare: the
fake logs its exact argv AND the bytes on its stdin, and every case uses fixture
values two characters long. `.ci/shadow/w7p5a-status.json` records this path as
blocked only for the "one real run" clause and says in as many words that the
mocked parity ledger is a separate, achievable piece of work. This is that
piece.

THE DOCUMENT IS THE ONLY EVIDENCE ON THE HAPPY PATH, and that is what makes this
script different from its preview sibling. The twin prints NOTHING of its own
when it succeeds: there is no closing `log_info`, so stdout carries wrangler's
line and stderr is empty. A port that sent an empty document, or the wrong
Worker name, would produce byte-identical streams and exit 0. Every case that
reaches wrangler therefore asserts the recorded stdin, and
`test_the_bulk_call_and_its_document_are_pinned_in_full` pins it against literal
bytes rather than against the port's own builders.

TWO STALENESS ALARMS RE-DERIVE THE TWIN'S OWN LISTS, because `KEYS` and
`REQUIRED_NONEMPTY` are copies: the day a twenty-fifth secret or a fourteenth
guard lands in the twin, the alarm fails instead of the port quietly sending a
document one key short. A third test asserts the two SIBLING scripts really are
different where they look the same, since "the preview file with a longer list"
is the assumption that would port this one wrong.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import set_preview_worker_secrets as sibling
from rediacc_ci.deploy import set_www_worker_secrets as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "set-www-worker-secrets.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "set_www_worker_secrets.py"
BASH = shutil.which("bash") or "/bin/bash"

# The thirteen values the twin refuses to deploy without, plus the Worker name.
FIXTURE_ENV = {
    "WORKER_NAME": "www-edge",
    "ACCOUNT_ED25519_PRIVATE_KEY": "e1",
    "ACCOUNT_ED25519_PUBLIC_KEY": "e2",
    "ACCOUNT_X25519_PRIVATE_KEY": "x1",
    "ACCOUNT_X25519_PUBLIC_KEY": "x2",
    "ACCOUNT_SERVER_API_KEY": "ak",
    "ACCOUNT_JWT_SECRET": "jw",
    "ROOT_EMAIL": "root@example.invalid",
    "AWS_SES_ACCESS_KEY_ID": "sk",
    "AWS_SES_SECRET_ACCESS_KEY": "ss",
    "AWS_SES_REGION": "eu-west-1",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": "ts",
    "STRIPE_SECRET_KEY": "sk_fixture",
    "STRIPE_WEBHOOK_SECRET": "whsec_fixture",
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
    """ONE CALL, PINNED AGAINST LITERAL BYTES. Twenty-four keys in the twin's
    order, the eleven legitimately-absent ones present as empty strings."""
    old, new, old_calls, new_calls = run_both(tmp_path)
    assert old.returncode == 0
    assert old_calls.splitlines()[0] == "npx\twrangler\tsecret\tbulk\t--name\twww-edge"
    assert document(old_calls) == (
        "{\n"
        '  "ACCOUNT_ED25519_PRIVATE_KEY": "e1",\n'
        '  "ACCOUNT_ED25519_PUBLIC_KEY": "e2",\n'
        '  "ACCOUNT_X25519_PRIVATE_KEY": "x1",\n'
        '  "ACCOUNT_X25519_PUBLIC_KEY": "x2",\n'
        '  "ACCOUNT_SERVER_API_KEY": "ak",\n'
        '  "ACCOUNT_JWT_SECRET": "jw",\n'
        '  "STRIPE_SECRET_KEY": "sk_fixture",\n'
        '  "STRIPE_WEBHOOK_SECRET": "whsec_fixture",\n'
        '  "ROOT_EMAIL": "root@example.invalid",\n'
        '  "AWS_SES_ACCESS_KEY_ID": "sk",\n'
        '  "AWS_SES_SECRET_ACCESS_KEY": "ss",\n'
        '  "AWS_SES_REGION": "eu-west-1",\n'
        '  "AWS_SES_FROM": "",\n'
        '  "AWS_SES_CONFIGURATION_SET": "",\n'
        '  "CLOUDFLARE_TURNSTILE_SECRET_KEY": "ts",\n'
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
    """THE PROPERTY THAT MAKES THE DOCUMENT LOAD BEARING. stdout is wrangler's
    line and nothing else, stderr is empty: there is no closing `log_info` here,
    unlike `set-preview-worker-secrets.sh:105`."""
    old, new, old_calls, new_calls = run_both(tmp_path)
    assert old.stdout == "Finished processing secrets JSON file.\n"
    assert old.stderr == ""
    assert port.SUCCESS_IS_SILENT
    assert "log_info" not in _twin_source(), "the twin grew a closing line; re-read this test"
    _assert_agree(old, new, "silent-success", old_calls, new_calls)


def test_the_worker_name_is_taken_whole(tmp_path: pathlib.Path) -> None:
    """NO `pr-` COMPOSITION HERE, unlike the preview sibling: whatever
    cd-deploy-worker.yml hands over is the Worker written to."""
    old, new, old_calls, new_calls = run_both(tmp_path, WORKER_NAME="rediacc-www-eu")
    assert old_calls.splitlines()[0].endswith("--name\trediacc-www-eu")
    _assert_agree(old, new, "worker-name", old_calls, new_calls)


def test_the_nine_seller_fields_reach_the_document(tmp_path: pathlib.Path) -> None:
    """THE INVOICE BLOCK, which the preview Worker does not carry at all."""
    seller = {
        "SELLER_NAME": "Rediacc",
        "SELLER_VAT_NUMBER": "VAT1",
        "SELLER_REGISTRATION_NUMBER": "REG1",
        "SELLER_ADDRESS_LINE1": "Line 1",
        "SELLER_ADDRESS_LINE2": "Line 2",
        "SELLER_CITY": "City",
        "SELLER_POSTAL_CODE": "12345",
        "SELLER_COUNTRY": "NL",
        "SELLER_EMAIL": "billing@example.invalid",
    }
    old, new, old_calls, new_calls = run_both(tmp_path, **seller)
    doc = document(old_calls)
    for key, value in seller.items():
        assert f'"{key}": "{value}"' in doc
    _assert_agree(old, new, "seller-block", old_calls, new_calls)


def test_every_one_of_the_thirteen_guards_fires_with_its_own_name(
    tmp_path: pathlib.Path,
) -> None:
    """THIRTEEN CASES, ONE PER GUARD, each driven EMPTY rather than absent:
    `"${NAME:-}"` collapses the two."""
    for name in port.REQUIRED_NONEMPTY:
        case = tmp_path / f"guard-{name}"
        case.mkdir()
        old, new, old_calls, new_calls = run_both(case, **{name: ""})
        assert old.returncode == 1, f"{name}: the twin accepted an empty value"
        assert old.stdout == ""
        assert old.stderr == (
            f"set-www-worker-secrets.sh: {name} is EMPTY for WORKER_NAME=www-edge.\n"
            "  The Worker's schema accepts an empty value and silently disables the feature it\n"
            "  drives, so this refuses to deploy instead. Check the secret store for that name.\n"
        )
        assert old_calls == "", f"{name}: a refused run still called wrangler"
        _assert_agree(old, new, f"guard-{name}", old_calls, new_calls)


def test_stripe_is_demanded_here_and_not_on_the_preview(tmp_path: pathlib.Path) -> None:
    """THE SIBLINGS DISAGREE ON PURPOSE. edge gets the sandbox key and stable the
    live one, so an empty Stripe key on www is never legitimate, while on a
    preview it is. Pinned in both directions."""
    old, new, old_calls, new_calls = run_both(tmp_path, STRIPE_SECRET_KEY="")
    assert old.returncode == 1
    assert "STRIPE_SECRET_KEY is EMPTY" in old.stderr
    assert "STRIPE_SECRET_KEY" in port.REQUIRED_NONEMPTY
    assert "STRIPE_SECRET_KEY" not in sibling.REQUIRED_NONEMPTY
    _assert_agree(old, new, "stripe-demanded", old_calls, new_calls)


def test_the_first_empty_guard_wins_and_the_rest_never_run(tmp_path: pathlib.Path) -> None:
    blanks = dict.fromkeys(port.REQUIRED_NONEMPTY, "")
    old, new, old_calls, new_calls = run_both(tmp_path, **blanks)
    assert old.stderr.startswith("set-www-worker-secrets.sh: ACCOUNT_ED25519_PRIVATE_KEY is EMPTY")
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


def test_the_tool_checks_run_before_the_worker_name_check(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, drop="jq", drop_env=("WORKER_NAME",))
    assert old.stderr == "✗ Required command 'jq' is not available\n"
    _assert_agree(old, new, "tools-first", old_calls, new_calls)


def test_divergence_a_missing_worker_name_is_bashs_own_unbound_variable(
    tmp_path: pathlib.Path,
) -> None:
    """THE ONE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE "FIXED" BY
    ACCIDENT. bash's refusal names the bash FILE and a bash LINE NUMBER, and then
    the twin's own message, which already begins with the script name: the name
    is printed twice. The port prints the `VAR: message` half. Same stream, same
    status, no call from either."""
    old, new, old_calls, new_calls = run_both(tmp_path, drop_env=("WORKER_NAME",))
    assert old.returncode == new.returncode == 1
    assert old.stderr.endswith(
        "line 54: WORKER_NAME: set-www-worker-secrets.sh: WORKER_NAME must be set\n"
    )
    assert new.stderr == "WORKER_NAME: set-www-worker-secrets.sh: WORKER_NAME must be set\n"
    assert old.stderr != new.stderr
    assert old.stdout == new.stdout == ""
    assert old_calls == new_calls == ""


def test_an_empty_worker_name_refuses_too(tmp_path: pathlib.Path) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST. A port checking `"WORKER_NAME" in
    os.environ` would run `wrangler secret bulk --name ''` instead."""
    old, new, old_calls, new_calls = run_both(tmp_path, WORKER_NAME="")
    assert old.returncode == new.returncode == 1
    assert new.stderr == port.MISSING_WORKER_NAME + "\n"
    assert old_calls == new_calls == "", "an empty Worker name still reached wrangler"


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
    awkward = {"SELLER_ADDRESS_LINE1": 'a"b\nc\\d'}
    old, new, old_calls, new_calls = run_both(tmp_path, **awkward)
    assert '"SELLER_ADDRESS_LINE1": "a\\"b\\nc\\\\d"' in document(old_calls)
    _assert_agree(old, new, "escaping", old_calls, new_calls)


def test_the_key_list_is_the_twins_key_list() -> None:
    """STALENESS ALARM. `KEYS` is a copy of the twin's `--arg` list, re-derived
    here from the twin's source, in order."""
    pairs = re.findall(r'--arg (\w+) "\$\{(\w+):-\}"', _twin_source())
    assert pairs, "the --arg shape changed; this alarm is no longer reading anything"
    assert [(env, var) for var, env in pairs] == list(port.KEYS)

    body = re.search(r"'\{(.*?)\}'", _twin_source(), re.DOTALL)
    assert body is not None
    built = re.findall(r"(\w+): \$(\w+)", body.group(1))
    assert built == list(port.KEYS)


def test_the_guard_list_is_the_twins_guard_list() -> None:
    """STALENESS ALARM for the thirteen `_require_nonempty` calls, in order."""
    names = re.findall(r'^_require_nonempty (\w+) "', _twin_source(), re.MULTILINE)
    assert names, "the _require_nonempty shape changed; this alarm reads nothing"
    assert tuple(names) == port.REQUIRED_NONEMPTY


def test_the_two_sibling_scripts_are_not_the_same_script() -> None:
    """THE ASSUMPTION THAT WOULD PORT THIS ONE WRONG, refuted in one place. Every
    difference below is load bearing, and each is driven by a test above."""
    assert len(port.KEYS) == 24
    assert len(sibling.KEYS) == 15
    assert len(port.REQUIRED_NONEMPTY) == 13
    assert len(sibling.REQUIRED_NONEMPTY) == 11
    assert port.GUARD_EXPLANATION != sibling.GUARD_EXPLANATION
    assert not hasattr(port, "WORKER_PREFIX"), "www takes its Worker name whole"
    assert sibling.WORKER_PREFIX == "pr-"
    # The nine SELLER_* keys are this script's alone.
    seller = [key for key, _var in port.KEYS if key.startswith("SELLER_")]
    assert len(seller) == 9
    assert not [key for key, _var in sibling.KEYS if key.startswith("SELLER_")]


def test_pure_helpers() -> None:
    assert port.SELF == "set-www-worker-secrets.sh"

    argv = port.jq_argv({"SELLER_CITY": "Delft"})
    assert argv[:2] == ["jq", "-n"]
    assert argv.count("--arg") == 24
    assert "Delft" in argv
    assert argv[2:5] == ["--arg", "ed25519_priv", ""], "an absent value is the empty string"
    assert argv[-1].startswith("{ACCOUNT_ED25519_PRIVATE_KEY: $ed25519_priv")
    assert argv[-1].endswith("SELLER_EMAIL: $seller_email}")
    assert "seller_city" in argv

    assert port.wrangler_argv("www-edge") == [
        "npx",
        "wrangler",
        "secret",
        "bulk",
        "--name",
        "www-edge",
    ]

    guard = port.GuardError("SELLER_EMAIL", "www-edge")
    assert guard.lines()[0] == (
        "set-www-worker-secrets.sh: SELLER_EMAIL is EMPTY for WORKER_NAME=www-edge."
    )
    assert len(guard.lines()) == 3


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on a DROPPED KEY, which is the failure this script
    can suffer in production: `SELLER_VAT_NUMBER` missing from the document means
    the Worker's zod schema rejects the config and every request 500s, or the
    field silently disappears from issued invoices. Nothing on either stream
    shows it -- this twin prints nothing at all when it succeeds -- and the exit
    code is 0 either way. Driven red, then the source is confirmed byte-identical
    and green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace('    ("SELLER_VAT_NUMBER", "seller_vat"),\n', "", 1)
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
    assert "SELLER_VAT_NUMBER" in document(old_calls)
    assert "SELLER_VAT_NUMBER" not in document(bad_calls), "the mutant still sent the key"

    _good, good_calls = _run(PORT, tmp_path)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
