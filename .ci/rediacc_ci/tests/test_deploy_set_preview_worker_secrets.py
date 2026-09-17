"""Differential: `rediacc_ci.deploy.set_preview_worker_secrets` against its twin `.ci/scripts/deploy/set-preview-worker-secrets.sh`.

A RECORDING FAKE `npx` ON A SCRATCH PATH. Nothing here reaches Cloudflare: the fake logs its exact argv AND the bytes on its stdin, and every case uses fixture secrets whose values are two characters long, so even a bypassed fake would carry nothing real. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that
the mocked parity ledger is a separate, achievable piece of work. This is that piece.

THE DOCUMENT IS COMPARED, NOT JUST THE STREAMS, and on this script that is the whole point. The observable effect of the program is one JSON document handed to `wrangler secret bulk`; two implementations can print an identical `✓ Set 15 secrets on pr-123 in one bulk call` while sending a different key set, a different key ORDER, or a differently escaped value. Every case that
reaches wrangler asserts the recorded stdin, and `test_the_bulk_call_and_its_document_are_pinned_in_full` pins it against literal bytes rather than against the port's own builders.

TWO STALENESS ALARMS RE-DERIVE THE TWIN'S OWN LISTS. `KEYS` and `REQUIRED_NONEMPTY` are copies, so the day someone adds a sixteenth secret or a twelfth guard to the twin, `test_the_key_list_is_the_twins_key_list` and `test_the_guard_list_is_the_twins_guard_list` fail instead of the port quietly sending a document that is one key short.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import set_preview_worker_secrets as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "set-preview-worker-secrets.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "set_preview_worker_secrets.py"
BASH = shutil.which("bash") or "/bin/bash"

# The eleven values the twin refuses to deploy without, plus the PR number. Two characters each, and visibly not credentials.
FIXTURE_ENV = {
    "PR_NUMBER": "123",
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

# `jq` is a real prerequisite of BOTH sides (the port shells out to the same binary, for the reasons in its docstring), and `uname` / `dirname` are what `common.sh` needs at source time. Nothing else is on the scratch PATH, so a tool leaking in would show up as a behaviour change rather than as a silent convenience.
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
    else:
        assert shutil.which("npx", path=str(stub)) is None, "npx leaked into the stub PATH"
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
    calls = call_log.read_text(encoding="utf-8")
    return proc, calls


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


def test_the_bulk_call_and_its_document_are_pinned_in_full(tmp_path: pathlib.Path) -> None:
    """ONE CALL, PINNED AGAINST LITERAL BYTES rather than against the port's own builders, so a change in both would still be caught. The argv, then the fifteen keys in order with the four legitimately-empty ones present as empty strings."""
    old, new, old_calls, new_calls = run_both(tmp_path)
    assert old.returncode == 0
    assert old_calls.splitlines()[0] == "npx\twrangler\tsecret\tbulk\t--name\tpr-123"
    assert document(old_calls) == (
        "{\n"
        '  "ACCOUNT_ED25519_PRIVATE_KEY": "e1",\n'
        '  "ACCOUNT_ED25519_PUBLIC_KEY": "e2",\n'
        '  "ACCOUNT_X25519_PRIVATE_KEY": "x1",\n'
        '  "ACCOUNT_X25519_PUBLIC_KEY": "x2",\n'
        '  "ACCOUNT_SERVER_API_KEY": "ak",\n'
        '  "ACCOUNT_JWT_SECRET": "jw",\n'
        '  "STRIPE_SECRET_KEY": "",\n'
        '  "STRIPE_WEBHOOK_SECRET": "",\n'
        '  "ROOT_EMAIL": "root@example.invalid",\n'
        '  "AWS_SES_ACCESS_KEY_ID": "sk",\n'
        '  "AWS_SES_SECRET_ACCESS_KEY": "ss",\n'
        '  "AWS_SES_REGION": "eu-west-1",\n'
        '  "AWS_SES_FROM": "",\n'
        '  "AWS_SES_CONFIGURATION_SET": "",\n'
        '  "CLOUDFLARE_TURNSTILE_SECRET_KEY": "ts"\n'
        "}\n"
    )
    assert old.stdout == "Finished processing secrets JSON file.\n", "wrangler's own output"
    assert old.stderr == "✓ Set 15 secrets on pr-123 in one bulk call\n"
    _assert_agree(old, new, "happy-path", old_calls, new_calls)


def test_the_worker_name_is_the_pr_number_prefixed(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, PR_NUMBER="9001")
    assert "--name\tpr-9001" in old_calls
    assert old.stderr == "✓ Set 15 secrets on pr-9001 in one bulk call\n"
    _assert_agree(old, new, "worker-name", old_calls, new_calls)


def test_stripe_is_deliberately_not_demanded(tmp_path: pathlib.Path) -> None:
    """A PREVIEW WITHOUT BILLING IS A LEGITIMATE STATE (twin :48-49): ci.yml feeds the preview the sandbox key, so an absent Stripe key deploys rather than refusing. Pinned in the direction a "consistency" edit would break: adding Stripe to the guard list would turn every preview red."""
    old, new, old_calls, new_calls = run_both(tmp_path)
    assert old.returncode == 0
    assert '"STRIPE_SECRET_KEY": ""' in document(old_calls)
    assert "STRIPE_SECRET_KEY" not in port.REQUIRED_NONEMPTY
    assert "STRIPE_WEBHOOK_SECRET" not in port.REQUIRED_NONEMPTY
    _assert_agree(old, new, "stripe-optional", old_calls, new_calls)


def test_a_present_stripe_key_reaches_the_document(tmp_path: pathlib.Path) -> None:
    # PASSED AS A DICT, not as keyword arguments: ruff's S106 keys on the
    # ARGUMENT NAME, and `STRIPE_SECRET_KEY="sk_test_x"` reads to the linter as a
    # hardcoded credential even though the value is visibly a fixture.
    stripe = {"STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": "whsec_x"}
    old, new, old_calls, new_calls = run_both(tmp_path, **stripe)
    assert '"STRIPE_SECRET_KEY": "sk_test_x"' in document(old_calls)
    assert '"STRIPE_WEBHOOK_SECRET": "whsec_x"' in document(old_calls)
    _assert_agree(old, new, "stripe-present", old_calls, new_calls)


def test_every_one_of_the_eleven_guards_fires_with_its_own_name(
    tmp_path: pathlib.Path,
) -> None:
    """ELEVEN CASES, ONE PER GUARD, and each is driven EMPTY rather than absent:
    `"${NAME:-}"` collapses the two, and a port testing membership in os.environ
    would pass the absent case and deploy the empty one."""
    for name in port.REQUIRED_NONEMPTY:
        case = tmp_path / f"guard-{name}"
        case.mkdir()
        old, new, old_calls, new_calls = run_both(case, **{name: ""})
        assert old.returncode == 1, f"{name}: the twin accepted an empty value"
        assert old.stdout == ""
        assert old.stderr == (
            f"set-preview-worker-secrets.sh: {name} is EMPTY for WORKER_NAME=pr-123.\n"
            "  The Worker's schema either accepts an empty value and silently disables the\n"
            "  feature, or rejects it on every request; this refuses to deploy instead.\n"
        )
        assert old_calls == "", f"{name}: a refused run still called wrangler"
        _assert_agree(old, new, f"guard-{name}", old_calls, new_calls)


def test_an_absent_value_refuses_exactly_as_an_empty_one_does(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, drop_env=("ACCOUNT_JWT_SECRET",))
    assert old.returncode == 1
    assert "ACCOUNT_JWT_SECRET is EMPTY" in old.stderr
    _assert_agree(old, new, "absent-value", old_calls, new_calls)


def test_the_first_empty_guard_wins_and_the_rest_never_run(tmp_path: pathlib.Path) -> None:
    """ORDER IS OBSERVABLE. With every guarded value empty, the message names the FIRST one in the twin's order, not the last and not all eleven."""
    blanks = dict.fromkeys(port.REQUIRED_NONEMPTY, "")
    old, new, old_calls, new_calls = run_both(tmp_path, **blanks)
    assert old.stderr.startswith(
        "set-preview-worker-secrets.sh: ACCOUNT_ED25519_PRIVATE_KEY is EMPTY"
    )
    assert old.stderr.count("is EMPTY") == 1
    _assert_agree(old, new, "first-guard-wins", old_calls, new_calls)


def test_the_guard_message_names_a_variable_this_script_does_not_have(
    tmp_path: pathlib.Path,
) -> None:
    """OBSERVATION 1, PINNED. The guard prints `WORKER_NAME=pr-123`, and this
    script has no WORKER_NAME: the sentence is inherited from the www sibling, where the variable is real. The VALUE is right and the LABEL points a reader at an environment variable that plays no part here. Reproduced, because agreement with the live twin is the deliverable."""
    old, new, old_calls, new_calls = run_both(tmp_path, ROOT_EMAIL="")
    assert "WORKER_NAME=pr-123." in old.stderr

    # The twin names WORKER_NAME exactly once, inside that message, and never assigns or reads it. If either ever changes, this observation is stale and the port's constant should be re-read rather than trusted.
    source = _twin_source()
    assert source.count("WORKER_NAME") == 1
    assert 'WORKER_NAME=$WORKER."' in source
    assert "${WORKER_NAME" not in source
    assert port.GUARD_LABEL_SAYS_WORKER_NAME
    _assert_agree(old, new, "worker-name-label", old_calls, new_calls)


def test_missing_jq_refuses_before_anything_else(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, drop="jq")
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'jq' is not available\n"
    assert old.stdout == ""
    assert old_calls == ""
    _assert_agree(old, new, "no-jq", old_calls, new_calls)


def test_missing_npx_refuses_after_jq(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, drop="npx")
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'npx' is not available\n"
    _assert_agree(old, new, "no-npx", old_calls, new_calls)


def test_the_tool_checks_run_before_the_pr_number_check(tmp_path: pathlib.Path) -> None:
    """ORDER AGAIN: no jq and no PR_NUMBER names jq, not PR_NUMBER."""
    old, new, old_calls, new_calls = run_both(tmp_path, drop="jq", drop_env=("PR_NUMBER",))
    assert old.stderr == "✗ Required command 'jq' is not available\n"
    _assert_agree(old, new, "tools-first", old_calls, new_calls)


def test_divergence_a_missing_pr_number_is_bashs_own_unbound_variable(
    tmp_path: pathlib.Path,
) -> None:
    """THE ONE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE "FIXED" BY
    ACCIDENT. `${PR_NUMBER:?...}` is bash refusing, and it names the bash FILE and
    a bash LINE NUMBER. The port cannot honestly print that; it prints the `VAR: message` half. Same stream, same status, no call from either."""
    old, new, old_calls, new_calls = run_both(tmp_path, drop_env=("PR_NUMBER",))
    assert old.returncode == new.returncode == 1
    assert old.stderr.endswith("line 38: PR_NUMBER: PR_NUMBER is required\n")
    assert new.stderr == "PR_NUMBER: PR_NUMBER is required\n"
    assert old.stderr != new.stderr
    assert old.stdout == new.stdout == ""
    assert old_calls == new_calls == ""


def test_an_empty_pr_number_refuses_too(tmp_path: pathlib.Path) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST. A port checking `"PR_NUMBER" in os.environ` would sail past this and write fifteen secrets to a Worker named `pr-`."""
    old, new, old_calls, new_calls = run_both(tmp_path, PR_NUMBER="")
    assert old.returncode == new.returncode == 1
    assert new.stderr == port.MISSING_PR_NUMBER + "\n"
    assert old_calls == new_calls == "", "an empty PR number still reached wrangler"


def test_a_wrangler_failure_ends_the_run_with_its_status(tmp_path: pathlib.Path) -> None:
    """PIPEFAIL, the right-hand half. wrangler's status becomes the script's, and the closing line does NOT print: a caller must not read "Set 15 secrets" over a failed bulk call."""
    old, new, old_calls, new_calls = run_both(tmp_path, FAKE_NPX_RC="7")
    assert old.returncode == 7
    assert old.stderr == "wrangler: failed to set secrets\n"
    assert "Set 15 secrets" not in old.stderr
    assert old.stdout == ""
    _assert_agree(old, new, "wrangler-fails", old_calls, new_calls)


def test_the_document_carries_raw_utf8_the_way_jq_writes_it(tmp_path: pathlib.Path) -> None:
    """WHY THE PORT SHELLS OUT TO `jq` INSTEAD OF CALLING `json.dumps`. jq emits raw UTF-8; `json.dumps` defaults to `\\uXXXX` escapes. A secret is opaque bytes chosen by someone else, so this is not a hypothetical difference, and the assertion below shows the two answers side by side."""
    exotic = "Ünïcødé 7Ω"
    old, new, old_calls, new_calls = run_both(tmp_path, ROOT_EMAIL=exotic)
    assert f'"ROOT_EMAIL": "{exotic}"' in document(old_calls)
    escaped = '{"ROOT_EMAIL": "\\u00dcn\\u00efc\\u00f8d\\u00e9 7\\u03a9"}'
    assert json.dumps({"ROOT_EMAIL": exotic}) == escaped, (
        "json.dumps stopped escaping non-ASCII; the reasoning in the port's docstring changed"
    )
    _assert_agree(old, new, "utf8", old_calls, new_calls)


def test_a_value_with_quotes_and_newlines_survives_intact(tmp_path: pathlib.Path) -> None:
    awkward = {"ACCOUNT_JWT_SECRET": 'a"b\nc\\d'}
    old, new, old_calls, new_calls = run_both(tmp_path, **awkward)
    assert '"ACCOUNT_JWT_SECRET": "a\\"b\\nc\\\\d"' in document(old_calls)
    _assert_agree(old, new, "escaping", old_calls, new_calls)


def _twin_source() -> str:
    return TWIN.read_text(encoding="utf-8")


def test_the_key_list_is_the_twins_key_list() -> None:
    """STALENESS ALARM. `KEYS` is a copy of the twin's `--arg` list, so this re-derives that list from the twin's source and fails if the two drift. A sixteenth secret added to the twin must not leave the port sending fifteen."""
    pairs = re.findall(r'--arg (\w+) "\$\{(\w+):-\}"', _twin_source())
    assert pairs, "the --arg shape changed; this alarm is no longer reading anything"
    assert [(env, var) for var, env in pairs] == list(port.KEYS)

    # The object constructor must bind the SAME variables to the SAME keys.
    body = re.search(r"'\{(.*?)\}'", _twin_source(), re.DOTALL)
    assert body is not None
    built = re.findall(r"(\w+): \$(\w+)", body.group(1))
    assert built == list(port.KEYS)


def test_the_guard_list_is_the_twins_guard_list() -> None:
    """STALENESS ALARM for the eleven `_require_nonempty` calls, in order."""
    names = re.findall(r'^_require_nonempty (\w+) "', _twin_source(), re.MULTILINE)
    assert names, "the _require_nonempty shape changed; this alarm reads nothing"
    assert tuple(names) == port.REQUIRED_NONEMPTY


def test_the_closing_line_counts_what_is_actually_sent() -> None:
    """"15" IS A LITERAL IN THE TWIN, not a tally, so the day a sixteenth key lands without touching that line the log under-reports. This is the alarm."""
    assert len(port.KEYS) == port.SECRET_COUNT_CLAIM
    assert 'log_info "Set 15 secrets' in _twin_source()


def test_pure_helpers() -> None:
    assert port.SELF == "set-preview-worker-secrets.sh"
    assert port.worker_name("42") == "pr-42"
    assert len(port.KEYS) == 15
    assert len(port.REQUIRED_NONEMPTY) == 11

    argv = port.jq_argv({"ROOT_EMAIL": "a@b", "AWS_SES_FROM": "f@g"})
    assert argv[:2] == ["jq", "-n"]
    assert argv[2:5] == ["--arg", "ed25519_priv", ""], "an absent value is the empty string"
    assert "--arg" not in argv[-1], "the filter is last"
    assert argv[-1].startswith("{")
    assert argv.count("--arg") == 15
    assert "admin" in argv
    assert "a@b" in argv
    assert port.jq_filter().startswith("{ACCOUNT_ED25519_PRIVATE_KEY: $ed25519_priv")
    assert port.jq_filter().endswith("CLOUDFLARE_TURNSTILE_SECRET_KEY: $turnstile}")

    assert port.wrangler_argv("pr-7") == [
        "npx",
        "wrangler",
        "secret",
        "bulk",
        "--name",
        "pr-7",
    ]

    guard = port.GuardError("ROOT_EMAIL", "pr-7")
    assert guard.lines()[0] == (
        "set-preview-worker-secrets.sh: ROOT_EMAIL is EMPTY for WORKER_NAME=pr-7."
    )
    assert len(guard.lines()) == 3


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the ONE property no printed line can show: the key order of the document. `✓ Set 15 secrets on pr-123 in one bulk call` is identical either way, the exit code is 0 either way, and only the recorded stdin sees it. In production a reordered document is harmless; a REORDERED PORT is the same class of edit as a dropped key, and this is the control
    that proves the comparison would catch either. Driven red, then the source is confirmed byte-identical and green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        '    ("STRIPE_SECRET_KEY", "stripe"),\n    ("STRIPE_WEBHOOK_SECRET", "stripe_wh"),\n',
        '    ("STRIPE_WEBHOOK_SECRET", "stripe_wh"),\n    ("STRIPE_SECRET_KEY", "stripe"),\n',
        1,
    )
    assert mutated != original, "the lines this plant targets are no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    old, old_calls = _run(TWIN, tmp_path)
    bad, bad_calls = _run(mutant, tmp_path)
    assert bad.returncode == old.returncode == 0, (
        "the plant is invisible in the exit code, which is why the document is compared"
    )
    assert bad.stderr == old.stderr, "the plant is invisible on stderr too"
    assert bad_calls != old_calls, "the mutant's document matched the twin's"
    assert document(bad_calls).index('"STRIPE_WEBHOOK_SECRET"') < document(bad_calls).index(
        '"STRIPE_SECRET_KEY"'
    )

    _good, good_calls = _run(PORT, tmp_path)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
