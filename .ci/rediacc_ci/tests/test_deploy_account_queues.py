"""The queues preflight of `deploy_account`: missing queues are created before any migration, and a failure refuses the deploy."""

from __future__ import annotations

import typing

import pytest

from rediacc_ci.deploy import deploy_account as port

if typing.TYPE_CHECKING:
    import pathlib

ENV = {"CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_ACCOUNT_ID": "acct"}
TOML = """name = "w"
[[d1_databases]]
database_name = "db"

[[queues.producers]]
binding = "B"
queue = "q-main"

[[queues.consumers]]
queue = "q-main"
dead_letter_queue = "q-main-dlq"
"""


class Fake:
    def __init__(self, live: list[str], *, ok: bool = True, answer: bool = True) -> None:
        self.live = list(live)
        self.gets: list[int] = []
        self.posts: list[str] = []
        self.ok = ok
        self.answer = answer

    def fetch(self, _url: str, _token: str) -> dict:
        self.gets.append(1)
        return {"success": self.answer, "result": [{"queue_name": n} for n in self.live]}

    def post(self, _url: str, _token: str, payload: dict) -> dict:
        if not self.ok:
            return {"success": False}
        self.posts.append(payload["queue_name"])
        self.live.append(payload["queue_name"])
        return {"success": True}


def _cfg(tmp_path: pathlib.Path, body: str = TOML) -> pathlib.Path:
    path = tmp_path / "wrangler.eu.toml"
    path.write_text(body)
    return path


def test_all_present_makes_no_write(tmp_path: pathlib.Path) -> None:
    fake = Fake(["q-main", "q-main-dlq"])
    assert port.check_queues(_cfg(tmp_path), ENV, fake.fetch, fake.post) == []
    assert fake.posts == []


def test_missing_are_created_dlq_first_and_confirmed(tmp_path: pathlib.Path) -> None:
    fake = Fake([])
    created = port.check_queues(_cfg(tmp_path), ENV, fake.fetch, fake.post)
    assert created == ["q-main-dlq", "q-main"]
    assert fake.posts == ["q-main-dlq", "q-main"]
    assert len(fake.gets) == 2  # the audit, then the confirming re-list


def test_a_create_failure_refuses(tmp_path: pathlib.Path) -> None:
    fake = Fake([], ok=False)
    with pytest.raises(port.QueuePreflightError, match="no migration was applied"):
        port.check_queues(_cfg(tmp_path), ENV, fake.fetch, fake.post)


def test_no_verdict_refuses(tmp_path: pathlib.Path) -> None:
    fake = Fake([], answer=False)
    with pytest.raises(port.QueuePreflightError, match="no verdict"):
        port.check_queues(_cfg(tmp_path), ENV, fake.fetch, fake.post)
    assert fake.posts == []


def test_dry_run_creates_nothing(tmp_path: pathlib.Path) -> None:
    fake = Fake([])
    would = port.check_queues(_cfg(tmp_path), ENV, fake.fetch, fake.post, dry_run=True)
    assert would == ["q-main-dlq", "q-main"]
    assert fake.posts == []


def test_a_config_without_queues_makes_no_api_call(tmp_path: pathlib.Path) -> None:
    fake = Fake([])
    assert port.check_queues(_cfg(tmp_path, 'name = "w"\n'), {}, fake.fetch, fake.post) == []
    assert fake.gets == []


def _tree(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    worker = tmp_path / "workers" / "account"
    worker.mkdir(parents=True)
    (worker / "wrangler.eu.toml").write_text(TOML)
    (worker / "node_modules").mkdir()
    ran: list[list[str]] = []
    monkeypatch.setattr(port.common, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(port, "portal_sitekey_refusal", lambda *_a: None)
    monkeypatch.setattr(port, "check_services", lambda *_a: None)

    def run(argv: list[str]) -> int:
        ran.append(argv)
        return 0

    monkeypatch.setattr(port, "_run", run)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.chdir(tmp_path)
    return ran


def test_main_refuses_before_any_migration(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = _tree(tmp_path, monkeypatch)

    def refuse(*_a: object, **_k: object) -> list[str]:
        raise port.QueuePreflightError("queue create failed; no migration was applied")

    monkeypatch.setattr(port, "check_queues", refuse)
    assert port.main(["--region", "eu"]) == 1
    assert ran == []


def test_main_runs_the_queue_preflight_before_the_migration(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = _tree(tmp_path, monkeypatch)
    order: list[str] = []

    def check_queues(*_a: object, **_k: object) -> list[str]:
        order.append("queues")
        return []

    def run(argv: list[str]) -> int:
        order.append(argv[-3])
        return 0

    monkeypatch.setattr(port, "check_queues", check_queues)
    monkeypatch.setattr(port, "_run", run)
    monkeypatch.setattr(port, "portal_smoke", lambda *_a: None)
    assert port.main(["--region", "eu"]) == 0
    assert order[0] == "queues"
    assert ran == []


def test_main_dry_run_creates_nothing(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ran = _tree(tmp_path, monkeypatch)
    fake = Fake([])
    real = port.check_queues
    monkeypatch.setattr(
        port, "check_queues", lambda cfg, env, **k: real(cfg, env, fake.fetch, fake.post, **k)
    )
    assert port.main(["--region", "eu", "--dry-run"]) == 0
    assert fake.posts == []
    assert ran == []
    out = capsys.readouterr().out
    assert "would create queue: q-main-dlq" in out
    assert "would create queue: q-main" in out
    # Each argv part passes through the log mask on its own and the parts join with single spaces; the preview is not shell-quoted.
    assert "would run: " + " ".join(port.deploy_argv("wrangler.eu.toml")) + "\n" in out


def test_main_dry_run_refuses_a_malformed_queues_section(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real run refuses an unreadable queues section; the preview refuses with the same verdict instead of printing `would run`."""
    ran = _tree(tmp_path, monkeypatch)
    (tmp_path / "workers" / "account" / "wrangler.eu.toml").write_text(
        TOML.replace("[[queues.producers]]", "[queues]\nproducers = 3\n#")
    )
    assert port.main(["--region", "eu", "--dry-run"]) == 1
    assert ran == []
