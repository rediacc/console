"""preview_signer: a routeless config bound to the preview's own database and the central signer's preview tier, a fresh delegated key only on stdin, the secret list verified, and a fork head refused. Every wrangler call goes to a recording fake; nothing reaches Cloudflare."""

from __future__ import annotations

import io
import json
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_signer as ds
from rediacc_ci.deploy import preview_signer as ps
from rediacc_ci.well_known import GH_REPO

if typing.TYPE_CHECKING:
    import pathlib

NAME = "pv-able-baker-charlie"
PR = "42"
DB_ID = "11111111-2222-4333-8444-555555555555"
VERSION = "0b6c8f2e-1111-4222-8333-944445555666"
PREVIOUS = "7d1e2f3a-aaaa-4bbb-8ccc-ddddeeeeffff"
PRIVATE = "MC4CAQAwBQYDK2VwBCIEIDELEGATEDPRIVATEFORTHETESTONLY000000000"
PUBLIC = "MCowBQYDK2VwAyEADELEGATEDPUBLICFORTHETESTONLY0000000000000000"
ENV = {"CLOUDFLARE_API_TOKEN": "cf-token", "PATH": ""}

# The shape box S2's workers/signer/wrangler.preview.template.toml must have; this module's tokens and refusals are its contract.
TEMPLATE = """name = "@WORKER@"
main = "../src/index.ts"
compatibility_date = "2026-01-20"
compatibility_flags = ["nodejs_compat"]
workers_dev = false
preview_urls = false

[vars]
REGION = "@REGION@"
SHARED_HOSTS = "@PREVIEW_HOST@"

[[d1_databases]]
binding = "SHARED"
database_name = "@SHARED_DB@"
database_id = "@SHARED_DB_ID@"

[[services]]
binding = "CENTRAL_SIGNER"
service = "@CENTRAL_SIGNER@"
entrypoint = "LicenseSigner"
props = { tier = "preview", name = "@PREVIEW_NAME@", host = "@PREVIEW_HOST@", region = "@REGION@" }
"""


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    signer = tmp_path / "workers" / "signer"
    signer.mkdir(parents=True)
    (signer / ps.TEMPLATE).write_text(TEMPLATE, encoding="utf-8")
    bin_dir = signer / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "wrangler").write_text("#!/bin/sh\nexit 99\n")
    return tmp_path


class FakeWrangler:
    def __init__(
        self, *, lists: list[list[str]] | None = None, deploy_rc: int = 0, echo_stdin: bool = False
    ) -> None:
        self.calls: list[tuple[list[str], pathlib.Path, str | None]] = []
        self.lists = list(lists or [list(ps.SECRET_NAMES)])
        self.deploy_rc = deploy_rc
        self.echo_stdin = echo_stdin

    def __call__(self, argv: list[str], cwd: pathlib.Path, stdin: str | None) -> ds.Result:
        self.calls.append((argv, cwd, stdin))
        verb = argv[3:5]
        if verb == ["deployments", "list"]:
            return ds.Result(
                0,
                json.dumps(
                    [{"created_on": "1", "versions": [{"version_id": PREVIOUS, "percentage": 100}]}]
                ),
                "",
            )
        if argv[3] == "deploy":
            if self.deploy_rc:
                return ds.Result(self.deploy_rc, "", "deploy failed")
            return ds.Result(0, "Current Version ID: %s\n" % VERSION, "")
        if verb == ["secret", "bulk"]:
            return ds.Result(0, ("read %s\n" % stdin) if self.echo_stdin else "ok\n", "")
        if verb == ["secret", "list"]:
            names = self.lists.pop(0) if len(self.lists) > 1 else self.lists[0]
            return ds.Result(0, json.dumps([{"name": n} for n in names]), "")
        raise AssertionError("unexpected wrangler call %r" % argv)


def run(repo: pathlib.Path, fake: FakeWrangler, **kw):
    out = io.StringIO()
    kwargs = {
        "name": NAME,
        "pr": PR,
        "db_id": DB_ID,
        "env": ENV,
        "run": fake,
        "keygen": lambda: (PRIVATE, PUBLIC),
        "out": out,
        "sleep": lambda _s: None,
    }
    kwargs.update(kw)
    result = ps.deploy(repo, **kwargs)
    return result, out.getvalue()


def rendered(repo: pathlib.Path) -> str:
    return (repo / "workers/signer/.generated" / ("wrangler.%s-signer.toml" % NAME)).read_text()


def test_the_rendered_config_has_no_route_no_key_name_and_binds_only_the_preview(repo):
    run(repo, FakeWrangler())
    text = rendered(repo)
    assert ps.config_refusals(text, NAME, PR) == []
    assert "route" not in text
    for key in (
        "ACCOUNT_ED25519_PRIVATE_KEY",
        "ACCOUNT_ED25519_PUBLIC_KEY",
        "DELEGATED_PRIVATE_KEY",
    ):
        assert key not in text
    assert 'name = "%s-signer"' % NAME in text
    assert 'database_name = "account-pr-42"' in text
    assert 'SHARED_HOSTS = "%s.rediacc.workers.dev"' % NAME in text


GOOD = ds.render(TEMPLATE, ps.render_values(NAME, PR, DB_ID))


def test_the_committed_template_renders_into_a_config_with_no_refusal():
    """Box S2's real template, not the fixture above: a drift between the two would pass every other case here and fail the first real deploy."""
    committed = paths.repo_root().joinpath(*ps.SIGNER_REL, ps.TEMPLATE).read_text(encoding="utf-8")
    assert (
        ps.config_refusals(ds.render(committed, ps.render_values(NAME, PR, DB_ID)), NAME, PR) == []
    )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda t: 'route = "x.example/*"\n' + t, "has `route`"),
        (lambda t: t.replace("workers_dev = false", "workers_dev = true"), "workers_dev"),
        (lambda t: t.replace("preview_urls = false", "preview_urls = true"), "preview_urls"),
        (lambda t: t + "# ACCOUNT_ED25519_PRIVATE_KEY\n", "ACCOUNT_ED25519_PRIVATE_KEY is named"),
        (lambda t: t + "# DELEGATED_PRIVATE_KEY\n", "DELEGATED_PRIVATE_KEY is named"),
        (lambda t: t.replace(NAME + "-signer", "signer-bench-eu", 1), "name is"),
        (lambda t: t.replace("account-pr-42", "account-bench"), "d1 bindings"),
        (
            lambda t: t.replace('service = "signer-bench-eu"', 'service = "signer-eu"'),
            "CENTRAL_SIGNER",
        ),
        (lambda t: t.replace('tier = "preview"', 'tier = "shared"'), "CENTRAL_SIGNER"),
        (
            lambda t: (
                t
                + '[[d1_databases]]\nbinding = "CONTROL"\ndatabase_name = "control-bench-eu"\ndatabase_id = "x"\n'
            ),
            "d1 bindings",
        ),
        (lambda t: t + 'x = "@LEFT@"\n', "unrendered token"),
    ],
)
def test_each_config_refusal_fires_and_the_control_passes(mutate, reason):
    assert ps.config_refusals(GOOD, NAME, PR) == []
    reasons = ps.config_refusals(mutate(GOOD), NAME, PR)
    assert any(reason in r for r in reasons), reasons


def test_the_key_reaches_wrangler_only_on_stdin_and_never_the_output(repo, tmp_path):
    fake = FakeWrangler(echo_stdin=True)
    record = tmp_path / "rec.json"
    result, out = run(repo, fake, record=record)
    for argv, _cwd, _stdin in fake.calls:
        assert not any(PRIVATE in a or PUBLIC in a for a in argv)
    bulk = [stdin for argv, _cwd, stdin in fake.calls if argv[3:5] == ["secret", "bulk"]]
    assert json.loads(bulk[0]) == {ps.PRIVATE_KEY: PRIVATE, ps.PUBLIC_KEY: PUBLIC}
    assert PRIVATE not in out
    assert PUBLIC not in out
    assert ds.REDACTED in out, "the leaky wrangler's echo was redacted"
    text = record.read_text()
    assert PRIVATE not in text
    assert PUBLIC not in text
    assert result["secret_names"] == sorted(ps.SECRET_NAMES)
    assert json.loads(text)["rollback"].startswith("npx --no-install wrangler rollback " + PREVIOUS)


def test_the_order_is_deploy_then_secrets_then_the_list(repo):
    fake = FakeWrangler()
    run(repo, fake)
    verbs = [argv[3:5] if argv[3] != "deploy" else ["deploy"] for argv, _c, _s in fake.calls]
    assert verbs == [["deployments", "list"], ["deploy"], ["secret", "bulk"], ["secret", "list"]]


def test_a_lagging_list_is_pushed_again_and_an_extra_secret_refused(repo):
    fake = FakeWrangler(lists=[[], list(ps.SECRET_NAMES)])
    result, _out = run(repo, fake)
    assert result["secret_names"] == sorted(ps.SECRET_NAMES)
    assert sum(1 for a, _c, _s in fake.calls if a[3:5] == ["secret", "bulk"]) == 2
    with pytest.raises(ds.RefusedError, match="not exactly"):
        run(repo, FakeWrangler(lists=[[*ps.SECRET_NAMES, "ACCOUNT_ED25519_PRIVATE_KEY"]]))


def test_a_failed_deploy_pushes_no_key(repo):
    fake = FakeWrangler(deploy_rc=1)
    with pytest.raises(ds.RefusedError, match="deploy of the preview signer failed"):
        run(repo, fake)
    assert not [a for a, _c, _s in fake.calls if a[3:5] == ["secret", "bulk"]]


def _event(tmp_path: pathlib.Path, head: str, base: str = GH_REPO) -> dict[str, str]:
    path = tmp_path / "event.json"
    path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "head": {"repo": {"full_name": head}},
                    "base": {"repo": {"full_name": base}},
                }
            }
        )
    )
    return {**ENV, "GITHUB_EVENT_PATH": str(path)}


def test_a_fork_head_is_refused_before_any_call_and_the_same_repository_passes(repo, tmp_path):
    fake = FakeWrangler()
    with pytest.raises(ds.RefusedError, match="fork"):
        run(repo, fake, env=_event(tmp_path, "someone/console"))
    assert fake.calls == []
    result, _out = run(repo, FakeWrangler(), env=_event(tmp_path, GH_REPO))
    assert result["worker"] == NAME + "-signer"


def test_an_unreadable_event_file_is_refused_not_read_as_no_fork(repo, tmp_path):
    fake = FakeWrangler()
    with pytest.raises(ds.RefusedError, match="could not be read"):
        run(repo, fake, env={**ENV, "GITHUB_EVENT_PATH": str(tmp_path / "missing.json")})
    assert fake.calls == []


@pytest.mark.parametrize("bad", ["", "pr-42", NAME + "-signer", "pv-able-baker"])
def test_a_name_that_is_not_a_preview_word_name_is_refused_unechoed(repo, bad):
    fake = FakeWrangler()
    with pytest.raises(ds.RefusedError) as caught:
        run(repo, fake, name=bad)
    assert "pv-<word>-<word>-<word>" in caught.value.lines[0]
    if bad:
        assert bad not in caught.value.lines[0]
    assert fake.calls == []


def test_a_missing_template_names_the_box_that_writes_it(repo):
    (repo / "workers/signer" / ps.TEMPLATE).unlink()
    with pytest.raises(ds.RefusedError, match="box S2"):
        run(repo, FakeWrangler())


def test_a_dry_run_generates_no_key_and_needs_no_token(repo):
    def no_keys():
        raise AssertionError("a dry run generated a key")

    fake = FakeWrangler()
    result, _out = run(repo, fake, env={"PATH": ""}, keygen=no_keys, dry_run=True)
    assert result == {"worker": NAME + "-signer", "dry_run": True}
    assert [a[3] for a, _c, _s in fake.calls] == ["deploy"]
    assert "--dry-run" in fake.calls[0][0]
