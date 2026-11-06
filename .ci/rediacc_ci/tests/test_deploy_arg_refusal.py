"""A deploy module refuses a flag it does not handle, and its `--dry-run` runs nothing.

The defect this pins: `common.parse_args` turned `--dry-run` into `ARG_DRY_RUN=true`, `deploy_account.main` never read it, and under production credentials the run applied the D1 migrations and executed `wrangler deploy`. `deploy_edge` discarded every argument. The fake runner here replaces each module's `_run`, the single door to a child process, so a call it records is a side effect that would have happened.
"""

from __future__ import annotations

import ast
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.core import common
from rediacc_ci.deploy import deploy_account, deploy_edge, deploy_www

if typing.TYPE_CHECKING:
    import pathlib

DEPLOY_DIR = paths.repo_root() / ".ci" / "rediacc_ci" / "deploy"

FIXTURE_TOML = (
    '[[d1_databases]]\nbinding = "DB"\ndatabase_name = "account-db-eu"\ndatabase_id = "x"\n'
)


class FakeRunner:
    """Records every would-be child process and fails it, so a run stops at the first one."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(list(argv))
        return 1


@pytest.fixture
def tree(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    account = tmp_path / "workers" / "account"
    account.mkdir(parents=True)
    (account / "wrangler.eu.toml").write_text(FIXTURE_TOML, encoding="utf-8")
    www = tmp_path / "workers" / "www"
    www.mkdir(parents=True)
    (www / deploy_edge.CONFIG).write_text('name = "rediacc-www-edge"\n', encoding="utf-8")
    (www / "wrangler.toml").write_text('name = "rediacc-www"\n', encoding="utf-8")
    monkeypatch.setenv("REDIACC_CI_ROOT", str(tmp_path))
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.chdir(tmp_path)
    assert common.repo_root() == tmp_path, "the fixture root is not the root the module reads"
    return tmp_path


def _no_refusal(*_args: object) -> None:
    """`common.refuse_unknown` with the check removed, for the control."""


def _fake(monkeypatch: pytest.MonkeyPatch, module: typing.Any) -> FakeRunner:
    fake = FakeRunner()
    monkeypatch.setattr(module, "_run", fake)
    return fake


@pytest.mark.usefixtures("tree")
def test_account_dry_run_runs_no_child_and_prints_the_plan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _fake(monkeypatch, deploy_account)
    assert deploy_account.main(["--region", "eu", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert fake.calls == []
    assert "would run: " in out
    assert "d1 migrations apply account-db-eu --remote --config wrangler.eu.toml" in out
    assert "deploy --config wrangler.eu.toml" in out


@pytest.mark.usefixtures("tree")
def test_account_dry_run_needs_no_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    fake = _fake(monkeypatch, deploy_account)
    assert deploy_account.main(["--region", "eu", "--dry-run"]) == 0
    assert fake.calls == []


@pytest.mark.usefixtures("tree")
def test_edge_dry_run_runs_no_child_and_prints_the_plan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _fake(monkeypatch, deploy_edge)
    assert deploy_edge.main(["--dry-run"]) == 0
    assert fake.calls == []
    assert "deploy --config wrangler.edge.toml" in capsys.readouterr().out


@pytest.mark.usefixtures("tree")
@pytest.mark.parametrize(
    ("module", "argv", "flag"),
    [
        (deploy_account, ["--region", "eu", "--bogus"], "--bogus"),
        (deploy_account, ["--region", "eu", "--dryrun"], "--dryrun"),
        (deploy_edge, ["--region", "eu"], "--region"),
        (deploy_edge, ["--bogus"], "--bogus"),
        (deploy_www, ["--dry-run"], "--dry-run"),
    ],
)
def test_an_unknown_flag_is_refused_before_any_call(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module: typing.Any,
    argv: list[str],
    flag: str,
) -> None:
    fake = _fake(monkeypatch, module)
    assert module.main(argv) == 2
    assert fake.calls == []
    err = capsys.readouterr().err
    assert "unknown option(s)" in err
    assert flag in err


@pytest.mark.usefixtures("tree")
@pytest.mark.parametrize(
    ("module", "argv"),
    [
        (deploy_account, ["--region", "eu", "--bogus"]),
        (deploy_edge, ["--bogus"]),
    ],
)
def test_control_without_the_check_the_fake_runner_sees_a_deploy_call(
    monkeypatch: pytest.MonkeyPatch, module: typing.Any, argv: list[str]
) -> None:
    """The refusal is what stops the run: with it disabled the same argv reaches `_run`."""
    monkeypatch.setattr(common, "refuse_unknown", _no_refusal)
    fake = _fake(monkeypatch, module)
    module.main(argv)
    assert fake.calls, "the control is vacuous: the run reached no child even unguarded"


def test_known_flags_are_accepted_by_the_parser() -> None:
    assert common.parse_args(["--region", "eu"], allowed={"ARG_REGION"}) == {"ARG_REGION": "eu"}
    with pytest.raises(common.RefusalError) as info:
        common.parse_args(["--region", "eu", "--dry-run"], allowed={"ARG_REGION"})
    assert info.value.code == 2
    assert "--dry-run" in info.value.lines[0]
    assert common.parse_args(["--anything"]) == {"ARG_ANYTHING": "true"}  # no allowlist, no refusal


def test_every_deploy_module_that_uses_the_shared_parser_passes_an_allowlist() -> None:
    """The sweep: a new module calling `common.parse_args(argv)` bare cannot land."""
    callers = 0
    bare: list[str] = []
    for path in sorted(DEPLOY_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "parse_args"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "common"
            ):
                callers += 1
                if not any(k.arg == "allowed" for k in node.keywords):
                    bare.append("%s:%d" % (path.name, node.lineno))
    assert callers >= 2, "the sweep found %d callers; it is not seeing the tree" % callers
    assert not bare, "common.parse_args without allowed= (flags silently ignored): %s" % bare


def test_refuse_arguments_refuses_any_argument_and_passes_none(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert common.refuse_arguments([]) is None
    assert common.refuse_arguments(["--dry-run"]) == 2
    assert "unknown option(s) --dry-run" in capsys.readouterr().err


def test_no_deploy_main_discards_its_argv() -> None:
    """The sweep for the no-argument modules: `del argv` in a `main` makes every flag look accepted, so a promote or a delete ran under `--dry-run`. Each such module calls `common.refuse_arguments` instead."""
    mains = 0
    discarding: list[str] = []
    for path in sorted(DEPLOY_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                mains += 1
                discarding.extend(
                    "%s:%d" % (path.name, stmt.lineno)
                    for stmt in ast.walk(node)
                    if isinstance(stmt, ast.Delete)
                    and any(isinstance(t, ast.Name) and t.id == "argv" for t in stmt.targets)
                )
    assert mains >= 20, "the sweep found %d mains; it is not seeing the tree" % mains
    assert not discarding, "main() discards argv (use common.refuse_arguments): %s" % discarding


@pytest.mark.usefixtures("tree")
@pytest.mark.parametrize(
    ("module", "argv"),
    [
        (deploy_account, ["--region", "eu", "--dry-run", ""]),
        (deploy_account, ["--region", "eu", "--dry-run=false"]),
        (deploy_edge, ["--dry-run", ""]),
        (deploy_edge, ["--dry-run=false"]),
    ],
)
def test_a_dry_run_flag_with_an_empty_or_false_value_still_runs_nothing(
    monkeypatch: pytest.MonkeyPatch, module: typing.Any, argv: list[str]
) -> None:
    fake = _fake(monkeypatch, module)
    assert module.main(argv) == 0
    assert fake.calls == []


@pytest.mark.usefixtures("tree")
def test_a_dry_run_over_an_unreadable_database_name_refuses_like_the_real_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _fake(monkeypatch, deploy_account)
    monkeypatch.setattr(deploy_account, "database_name", lambda _config: "")
    assert deploy_account.main(["--region", "eu", "--dry-run"]) == 1
    assert fake.calls == []
    assert "would run" not in capsys.readouterr().out
