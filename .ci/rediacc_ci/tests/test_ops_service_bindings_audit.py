"""Tests for `rediacc_ci.ops.service_bindings_audit` against a fake Cloudflare API and a scratch workers tree."""

from __future__ import annotations

import json
import typing

from rediacc_ci import paths
from rediacc_ci.ops import service_bindings_audit as mod

if typing.TYPE_CHECKING:
    import pathlib

    import pytest

ENV = {"CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_ACCOUNT_ID": "acct"}


def _tree(root: pathlib.Path) -> None:
    acc = root / "workers" / "account"
    acc.mkdir(parents=True)
    (acc / "wrangler.edge-eu.toml").write_text(
        'name = "edge-rediacc-account-eu"\n[[services]]\nbinding = "EXECUTOR"\n'
        'service = "edge-rediacc-proxy-eu"\n'
    )
    (acc / "wrangler.bench.toml").write_text(
        'name = "rediacc-account-bench"\n[[services]]\nbinding = "EXECUTOR"\n'
        'service = "rediacc-proxy-bench"\n'
    )
    pr = root / "workers" / "proxy"
    pr.mkdir()
    (pr / "wrangler.template.toml").write_text('name = "@@NAME@@"\n')
    (pr / "wrangler.eu.toml").write_text('name = "rediacc-proxy-eu"\n')


def _fetch(names: list[str]) -> typing.Callable[[str, str], dict]:
    def fetch(url: str, token: str) -> dict:
        assert token == "tok"
        assert "/accounts/acct/workers/scripts" in url
        return {"success": True, "result": [{"id": n} for n in names]}

    return fetch


def test_present_and_missing(tmp_path: pathlib.Path) -> None:
    _tree(tmp_path)
    live = ["edge-rediacc-account-eu", "rediacc-proxy-bench", "rediacc-account-bench"]
    rep = mod.audit(tmp_path, ENV, _fetch(live))
    assert rep["rc"] == 1
    by = {r["service"]: r["status"] for r in rep["bindings"]}
    assert by == {"edge-rediacc-proxy-eu": "MISSING", "rediacc-proxy-bench": "present"}
    assert [c["worker"] for c in rep["not_deployed"]] == ["rediacc-proxy-eu"]
    sides = {r["service"]: (r["side"], r["region"]) for r in rep["bindings"]}
    assert sides["edge-rediacc-proxy-eu"] == ("edge", "eu")
    assert sides["rediacc-proxy-bench"] == ("bench", "-")
    assert "MISSING" in mod.render(rep)


def test_all_present_is_zero(tmp_path: pathlib.Path) -> None:
    _tree(tmp_path)
    live = [
        "edge-rediacc-account-eu",
        "edge-rediacc-proxy-eu",
        "rediacc-proxy-bench",
        "rediacc-account-bench",
    ]
    rep = mod.audit(tmp_path, ENV, _fetch(live))
    assert rep["rc"] == 0
    assert [c["worker"] for c in rep["not_deployed"]] == ["rediacc-proxy-eu"]


def test_unreadable_account_is_77(tmp_path: pathlib.Path) -> None:
    _tree(tmp_path)

    def boom(*_args: str) -> dict:
        raise mod.AuditError("Cloudflare API answered HTTP 403")

    assert mod.audit(tmp_path, ENV, boom)["rc"] == 77
    assert mod.audit(tmp_path, {}, _fetch(["x"]))["rc"] == 77
    assert mod.audit(tmp_path, ENV, _fetch([]))["rc"] == 77
    assert mod.audit(tmp_path, ENV, lambda *_a: {"success": False})["rc"] == 77


def test_config_without_services(tmp_path: pathlib.Path) -> None:
    pr = tmp_path / "workers" / "proxy"
    pr.mkdir(parents=True)
    (pr / "wrangler.eu.toml").write_text('name = "rediacc-proxy-eu"\n')
    rep = mod.audit(tmp_path, ENV, _fetch(["rediacc-proxy-eu"]))
    assert rep["rc"] == 0
    assert rep["bindings"] == []
    assert rep["not_deployed"] == []


def test_main_json_and_real_configs(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    configs, bindings = mod.load_configs(paths.repo_root())
    assert any(b.side == "edge" and b.service.startswith("edge-rediacc-proxy-") for b in bindings)
    assert all("@@" not in c.worker for c in configs)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert mod.main(["--json"]) == 77
    assert json.loads(capsys.readouterr().out)["rc"] == 77


def test_the_local_dev_config_is_not_audited(tmp_path: pathlib.Path) -> None:
    """wrangler.dev.toml binds a stub issuer that only `wrangler dev` starts; nothing deploys it."""
    pr = tmp_path / "workers" / "proxy"
    pr.mkdir(parents=True)
    (pr / "wrangler.dev.toml").write_text(
        'name = "rediacc-proxy-dev"\n[[services]]\nbinding = "ISSUER"\nservice = "rediacc-executor-issuer-dev"\n'
    )
    (pr / "wrangler.eu.toml").write_text('name = "rediacc-proxy-eu"\n')
    rep = mod.audit(tmp_path, ENV, _fetch(["rediacc-proxy-eu"]))
    assert rep["rc"] == 0
    assert rep["bindings"] == []
    assert rep["not_deployed"] == []


def test_only_reads_just_the_named_config(tmp_path: pathlib.Path) -> None:
    _tree(tmp_path)
    (tmp_path / "workers" / "proxy" / "wrangler.eu.toml").write_text("not = = toml\n")
    configs, bindings = mod.load_configs(tmp_path, "workers/account/wrangler.edge-eu.toml")
    assert [c.worker for c in configs] == ["edge-rediacc-account-eu"]
    assert [b.service for b in bindings] == ["edge-rediacc-proxy-eu"]
    rep = mod.audit(
        tmp_path, ENV, _fetch(["edge-rediacc-proxy-eu"]), "workers/account/wrangler.edge-eu.toml"
    )
    assert rep["rc"] == 0
    assert [r["config"] for r in rep["bindings"]] == ["workers/account/wrangler.edge-eu.toml"]
    # Without `only`, the same unreadable sibling is no verdict.
    assert mod.audit(tmp_path, ENV, _fetch([]))["rc"] == mod.EX_UNAVAILABLE
