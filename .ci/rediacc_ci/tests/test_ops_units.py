"""In-process unit tests for the pure helpers of the ported operator tools and drills.

The differential files drive each port as a subprocess against its bash twin on a sealed fake PATH; these cases import the modules directly and check the helpers that carry the Rule T fixes (and give coverage tooling a route into them).
"""

from __future__ import annotations

import inspect
import json
import re
import subprocess
import typing
from pathlib import Path

import pytest

from rediacc_ci.drills import universe
from rediacc_ci.ops import (
    apply_cf_redirect_rules,
    backup_cutover_preflight,
    backup_d1,
    deploy_bench,
    linode_cluster_validation,
    scrub_sentinel,
)

if typing.TYPE_CHECKING:
    import pathlib


def test_human_size_uses_the_files_size_not_its_blocks() -> None:
    assert backup_d1._human_size(300) == "300B"
    assert backup_d1._human_size(2048) == "2.0K"
    assert backup_d1._human_size(5 * 1024 * 1024) == "5.0M"


def test_apex_rule_ids_and_payload_agree_on_the_rule_shape() -> None:
    payload = apply_cf_redirect_rules.new_rule_payload()
    assert "rules" not in payload
    rule = {**payload, "id": "r1"}
    ruleset = {"result": {"rules": [rule, {**payload, "id": "r2", "action": "block"}]}}
    assert apply_cf_redirect_rules.apex_rule_ids(ruleset) == ["r1"]
    assert apply_cf_redirect_rules.apex_rule_ids({"result": {}}) == []


def test_the_preflight_ledger_counts_every_verdict(capsys: pytest.CaptureFixture[str]) -> None:
    pf = backup_cutover_preflight.Preflight()
    pf.passed("ok")
    pf.failed("bad", "why")
    pf.failed("worse")
    assert (pf.checks, pf.failures) == (3, 2)
    assert "      why" in capsys.readouterr().err


def test_otlp_credentials_must_be_a_user_pass_object() -> None:
    assert deploy_bench.otlp_credentials_valid(json.dumps({"user": "u", "pass": "p"}))
    assert not deploy_bench.otlp_credentials_valid(json.dumps({"user": "u"}))
    assert not deploy_bench.otlp_credentials_valid(json.dumps({"user": 1, "pass": "p"}))
    assert not deploy_bench.otlp_credentials_valid("not json")
    assert not deploy_bench.otlp_credentials_valid("[]")


def test_require_nonempty_names_the_variable() -> None:
    with pytest.raises(deploy_bench.DeployError, match="ROOT_EMAIL is EMPTY"):
        deploy_bench.require_nonempty("ROOT_EMAIL", "")
    deploy_bench.require_nonempty("ROOT_EMAIL", "x")


def test_the_secret_payload_reads_the_environment_and_never_logs_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "ACCOUNT_ED25519_PRIVATE_KEY",
        "ACCOUNT_ED25519_PUBLIC_KEY",
        "ACCOUNT_X25519_PRIVATE_KEY",
        "ACCOUNT_X25519_PUBLIC_KEY",
        "ACCOUNT_SERVER_API_KEY",
        "ACCOUNT_JWT_SECRET",
    ):
        monkeypatch.setenv(name, "v-" + name)
    monkeypatch.setenv("ROOT_EMAIL", "root@example.invalid")
    monkeypatch.setenv("AWS_SES_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("AWS_SES_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("CLOUDFLARE_TURNSTILE_SECRET_KEY", "turn")
    monkeypatch.setenv("CLOUDFLARE_R2_ENDPOINT", "https://r2.invalid")
    monkeypatch.setenv("CLOUDFLARE_R2_ACCESS_KEY_ID", "r2id")
    monkeypatch.setenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "r2secret")
    monkeypatch.setenv("OBS_OTLP_CREDENTIALS", json.dumps({"user": "u", "pass": "p"}))
    monkeypatch.delenv("ACCOUNT_BACKUP_S3_ENDPOINT", raising=False)
    monkeypatch.delenv("ACCOUNT_BACKUP_S3_BUCKET", raising=False)
    payload = deploy_bench.secrets_payload()
    assert len(payload) == 29
    assert payload["ACCOUNT_BACKUP_S3_ENDPOINT"] == "https://r2.invalid"
    assert payload["ACCOUNT_BACKUP_S3_BUCKET"] == "rediacc-backups-bench"
    assert payload["STRIPE_SECRET_KEY"] == ""
    monkeypatch.delenv("ACCOUNT_JWT_SECRET")
    with pytest.raises(deploy_bench.DeployError, match="ACCOUNT_JWT_SECRET missing"):
        deploy_bench.secrets_payload()


def test_object_count_reads_aws_text_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(stdout: str, rc: int = 0) -> typing.Callable[[list[str]], subprocess.CompletedProcess]:
        return lambda argv: subprocess.CompletedProcess(argv, rc, stdout, "boom" if rc else "")

    for stdout, rc, want in (("3\n", 0, 3), ("None\n", 0, 0), ("x\n", 0, None), ("", 255, None)):
        monkeypatch.setattr(scrub_sentinel, "_aws", fake(stdout, rc))
        assert scrub_sentinel.object_count("cli/v1.0.5/", "https://r2.invalid") == want


def test_linode_phases_and_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    for name in ("CLUSTER_NAME", "PROVIDER", "NETWORK_CIDR", "CLUSTER_POOLS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    v = linode_cluster_validation.Validation(yes=False)
    assert (v.cluster, v.provider, v.cidr) == ("lval", "my-linode", "10.0.0.0/24")
    assert v.pools == "k8s:k8s-server:2:g6-nanode-1"
    with pytest.raises(linode_cluster_validation.PhaseError) as exc:
        v.phase_provision()
    assert exc.value.status == 3


def test_the_universe_drill_builds_its_cli_commands_from_the_drills_root() -> None:
    class FakeDrill:
        root = "/repo"

        def __init__(self) -> None:
            self.calls: list[tuple[list[str], dict[str, str]]] = []

        def run_with(self, argv: list[str], **env: str) -> None:
            self.calls.append((argv, env))

    class Root:
        def __str__(self) -> str:
            return "/repo"

        def __truediv__(self, other: str) -> str:
            return "/repo/" + other

    fake = FakeDrill()
    fake.root = Root()  # type: ignore[assignment]
    drill = universe.Universe(fake, restart_gateway=False)  # type: ignore[arg-type]
    drill.cli("config", "current", "-o", "json", REDIACC_CONFIG="drill-a")
    assert fake.calls == [
        (["/repo/rdc.sh", "config", "current", "-o", "json"], {"REDIACC_CONFIG": "drill-a"})
    ]


class _FakeCheck:
    """Stands in for the `rotation check` child: stderr lines and an exit code."""

    def __init__(self, rc: int, stderr: str) -> None:
        self.returncode = rc
        self.stderr = iter(stderr.splitlines(keepends=True))

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _fake_check(monkeypatch: pytest.MonkeyPatch, rc: int, stderr: str) -> None:
    def popen(*_args: object, **_kwargs: object) -> _FakeCheck:
        return _FakeCheck(rc, stderr)

    monkeypatch.setattr(deploy_bench.subprocess, "Popen", popen)


_UNCHECKED = "! could not check 1 credential (NOT drift):\n  otlp-bench: observability query failed: ssh exit 255: Permission denied (publickey).\n"


def test_a_rotation_check_refuses_on_could_not_check_naming_the_credential_and_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The comparison must always run: an unread credential refuses the push, is worded as not-drift, and is never answered with "rotate".
    _fake_check(monkeypatch, 2, _UNCHECKED)
    with pytest.raises(deploy_bench.DeployError) as caught:
        deploy_bench._rotation_check(Path("."))
    message = str(caught.value)
    assert "not checked, otlp-bench: observability query failed: ssh exit 255" in message
    assert "NOT drift" in message
    assert "rotation rotate" not in message
    assert "drift detected" not in message


def test_a_rotation_check_has_no_way_to_proceed_unchecked() -> None:
    # No parameter, flag or environment name may reopen the bench exception that let an unchecked push through.
    assert list(inspect.signature(deploy_bench._rotation_check).parameters) == ["root"]
    assert "proceed_on_unchecked" not in inspect.getsource(deploy_bench)


def test_a_rotation_check_passes_when_in_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    # The control for the refusals above: exit 0 returns without raising.
    _fake_check(monkeypatch, 0, "")
    deploy_bench._rotation_check(Path("."))


def test_a_rotation_check_refuses_on_drift_and_on_an_unknown_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_check(monkeypatch, 1, "")
    with pytest.raises(deploy_bench.DeployError, match="rotation drift detected"):
        deploy_bench._rotation_check(Path("."))
    _fake_check(monkeypatch, 3, "")
    with pytest.raises(deploy_bench.DeployError, match="exit 3"):
        deploy_bench._rotation_check(Path("."))


def test_deploy_bench_is_the_only_caller_of_rotation_check() -> None:
    # No production deploy path consumes `rotation check` today. Should one be added it must be listed here deliberately, and it must refuse on every non-zero exit, as this one does.
    root = Path(__file__).resolve().parents[3]
    pattern = re.compile(r"rotation[\"',\s]+check|rotation check")
    callers = set()
    for base in (".ci/rediacc_ci", "scripts", ".github/workflows"):
        for path in (root / base).rglob("*"):
            if path.suffix not in {".py", ".sh", ".yml", ".yaml"} or "tests" in path.parts:
                continue
            if pattern.search(path.read_text(errors="ignore")):
                callers.add(str(path.relative_to(root)))
    invokers = {c for c in callers if _invokes_rotation_check(root / c)}
    assert invokers == {".ci/rediacc_ci/ops/deploy_bench.py"}


def _invokes_rotation_check(path: Path) -> bool:
    text = path.read_text(errors="ignore")
    return bool(re.search(r"\[[^\]]*\"rotation\",\s*\"check\"", text)) or bool(
        re.search(r"^\s*[^#\n]*run\.sh\s+rotation\s+check", text, re.MULTILINE)
    )
