"""Tests for `rediacc_ci.ops.service_bindings_audit` against a fake Cloudflare API and a scratch workers tree."""

from __future__ import annotations

import json
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import service_bindings_audit as mod

if typing.TYPE_CHECKING:
    import pathlib

ENV = {"CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_ACCOUNT_ID": "acct"}


def _tree(root: pathlib.Path) -> None:
    acc = root / "workers" / "account"
    acc.mkdir(parents=True)
    (acc / "wrangler.eu.toml").write_text(
        'name = "account-eu"\n[[services]]\nbinding = "EXECUTOR"\nservice = "proxy-eu"\n'
    )
    (acc / "wrangler.bench.toml").write_text(
        'name = "account-bench"\n[[services]]\nbinding = "EXECUTOR"\nservice = "proxy-bench"\n'
    )
    pr = root / "workers" / "proxy"
    pr.mkdir()
    (pr / "wrangler.template.toml").write_text('name = "@@NAME@@"\n')
    (pr / "wrangler.eu.toml").write_text('name = "proxy-eu"\n')


def _fetch(names: list[str]) -> typing.Callable[[str, str], dict]:
    def fetch(url: str, token: str) -> dict:
        assert token == "tok"
        assert "/accounts/acct/workers/scripts" in url
        return {"success": True, "result": [{"id": n} for n in names]}

    return fetch


def test_present_and_missing(tmp_path: pathlib.Path) -> None:
    _tree(tmp_path)
    live = ["account-eu", "proxy-bench", "account-bench"]
    rep = mod.audit(tmp_path, ENV, _fetch(live))
    assert rep["rc"] == 1
    by = {r["service"]: r["status"] for r in rep["bindings"]}
    assert by == {"proxy-eu": "MISSING", "proxy-bench": "present"}
    assert [c["worker"] for c in rep["not_deployed"]] == ["proxy-eu"]
    sides = {r["service"]: (r["side"], r["region"]) for r in rep["bindings"]}
    assert sides["proxy-eu"] == ("shared", "eu")
    assert sides["proxy-bench"] == ("bench", "-")
    assert "MISSING" in mod.render(rep)


def test_all_present_is_zero(tmp_path: pathlib.Path) -> None:
    _tree(tmp_path)
    live = [
        "account-eu",
        "proxy-eu",
        "proxy-bench",
        "account-bench",
    ]
    rep = mod.audit(tmp_path, ENV, _fetch(live))
    assert rep["rc"] == 0
    assert rep["not_deployed"] == []


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
    (pr / "wrangler.eu.toml").write_text('name = "proxy-eu"\n')
    rep = mod.audit(tmp_path, ENV, _fetch(["proxy-eu"]))
    assert rep["rc"] == 0
    assert rep["bindings"] == []
    assert rep["not_deployed"] == []


def test_main_json_and_real_configs(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    configs, bindings = mod.load_configs(paths.repo_root())
    assert any(b.side == "shared" and b.service.startswith("proxy-") for b in bindings)
    assert all("@@" not in c.worker for c in configs)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert mod.main(["--json"]) == 77
    assert json.loads(capsys.readouterr().out)["rc"] == 77


def test_the_local_dev_config_is_not_audited(tmp_path: pathlib.Path) -> None:
    """wrangler.dev.toml binds a stub issuer that only `wrangler dev` starts; nothing deploys it."""
    pr = tmp_path / "workers" / "proxy"
    pr.mkdir(parents=True)
    (pr / "wrangler.dev.toml").write_text(
        'name = "proxy-dev"\n[[services]]\nbinding = "ISSUER"\nservice = "executor-issuer-dev"\n'
    )
    (pr / "wrangler.eu.toml").write_text('name = "proxy-eu"\n')
    rep = mod.audit(tmp_path, ENV, _fetch(["proxy-eu"]))
    assert rep["rc"] == 0
    assert rep["bindings"] == []
    assert rep["not_deployed"] == []


def test_only_naming_a_template_is_refused_not_passed_vacuously(tmp_path: pathlib.Path) -> None:
    _tree(tmp_path)
    (tmp_path / "workers" / "proxy" / "wrangler.template.toml").write_text('name = "@@NAME@@"\n')
    with pytest.raises(mod.AuditError, match="template"):
        mod.load_configs(tmp_path, "workers/proxy/wrangler.template.toml")
    configs, _ = mod.load_configs(tmp_path)
    assert all("template" not in c.config for c in configs)


def test_only_reads_just_the_named_config(tmp_path: pathlib.Path) -> None:
    _tree(tmp_path)
    (tmp_path / "workers" / "proxy" / "wrangler.eu.toml").write_text("not = = toml\n")
    configs, bindings = mod.load_configs(tmp_path, "workers/account/wrangler.eu.toml")
    assert [c.worker for c in configs] == ["account-eu"]
    assert [b.service for b in bindings] == ["proxy-eu"]
    rep = mod.audit(tmp_path, ENV, _fetch(["proxy-eu"]), "workers/account/wrangler.eu.toml")
    assert rep["rc"] == 0
    assert [r["config"] for r in rep["bindings"]] == ["workers/account/wrangler.eu.toml"]
    # Without `only`, the same unreadable sibling is no verdict.
    assert mod.audit(tmp_path, ENV, _fetch([]))["rc"] == mod.EX_UNAVAILABLE


def test_side_region_maps_every_file_name() -> None:
    sr = mod.side_region
    pure = mod.pathlib.PurePosixPath
    assert sr(pure("workers/proxy/wrangler.dev.toml")) == ("dev", "-")
    assert "dev" in mod.LOCAL_SIDES
    assert sr(pure("workers/account/wrangler.toml")) == ("shared", "-")
    assert sr(pure("workers/account/wrangler.eu.toml")) == ("shared", "eu")
    assert sr(pure("workers/account/wrangler.asia.toml")) == ("shared", "asia")
    assert sr(pure("workers/account/wrangler.bench.toml")) == ("bench", "-")


def test_root_wrangler_toml_is_shared(tmp_path: pathlib.Path) -> None:
    acc = tmp_path / "workers" / "account"
    acc.mkdir(parents=True)
    (acc / "wrangler.toml").write_text('name = "account"\n')
    configs, _ = mod.load_configs(tmp_path)
    assert [(c.side, c.region) for c in configs] == [("shared", "-")]


def test_empty_config_tree_is_77_not_green(tmp_path: pathlib.Path) -> None:
    (tmp_path / "workers").mkdir()
    rep = mod.audit(tmp_path, ENV, _fetch(["x"]))
    assert rep["rc"] == 77
    assert "no deployable Worker config" in rep["error"]


def test_non_object_api_body_is_77(tmp_path: pathlib.Path) -> None:
    _tree(tmp_path)
    bodies: list[typing.Any] = [[], None, "x"]
    for body in bodies:

        def fetch(_url: str, _token: str, b: typing.Any = body) -> typing.Any:
            return b

        assert mod.audit(tmp_path, ENV, fetch)["rc"] == 77


def test_truncated_listing_is_77(tmp_path: pathlib.Path) -> None:
    _tree(tmp_path)
    full = {"success": True, "result": [{"id": "w%d" % i} for i in range(mod.PER_PAGE)]}
    rep = mod.audit(tmp_path, ENV, lambda *_a: full)
    assert rep["rc"] == 77
    assert "pages" in rep["error"]


def test_services_that_are_not_tables_is_77(tmp_path: pathlib.Path) -> None:
    pr = tmp_path / "workers" / "proxy"
    pr.mkdir(parents=True)
    (pr / "wrangler.eu.toml").write_text('name = "proxy-eu"\nservices = ["oops"]\n')
    rep = mod.audit(tmp_path, ENV, _fetch(["x"]))
    assert rep["rc"] == 77
    assert "array of tables" in rep["error"]
