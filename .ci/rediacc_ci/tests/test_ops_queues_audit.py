"""Tests for `rediacc_ci.ops.queues_audit` against a fake Cloudflare API and a scratch wrangler config."""

from __future__ import annotations

import typing

import pytest

from rediacc_ci.ops import queues_audit as mod

if typing.TYPE_CHECKING:
    import pathlib

ENV = {"CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_ACCOUNT_ID": "acct"}
TOML = """name = "w"
[[queues.producers]]
binding = "B"
queue = "q-main"

[[queues.consumers]]
queue = "q-main"
dead_letter_queue = "q-main-dlq"
"""


def _config(tmp_path: pathlib.Path, body: str = TOML) -> pathlib.Path:
    path = tmp_path / "wrangler.toml"
    path.write_text(body)
    return path


class Fake:
    """A fake queues API: `live` is the account's queue set, posts are recorded."""

    def __init__(self, live: list[str], *, fail_create: bool = False, lose: bool = False) -> None:
        self.live = list(live)
        self.gets: list[str] = []
        self.posts: list[str] = []
        self.fail_create = fail_create
        self.lose = lose

    def fetch(self, url: str, token: str) -> dict:
        assert token == "tok"
        assert "/accounts/acct/queues" in url
        self.gets.append(url)
        return {"success": True, "result": [{"queue_name": n} for n in self.live]}

    def post(self, url: str, token: str, payload: dict) -> dict:
        assert token == "tok"
        assert url.endswith("/accounts/acct/queues")
        if self.fail_create:
            return {"success": False}
        name = payload["queue_name"]
        self.posts.append(name)
        if not self.lose:
            self.live.append(name)
        return {"success": True}


def test_config_queues_lists_dead_letter_first(tmp_path: pathlib.Path) -> None:
    got = [(q.name, q.role) for q in mod.config_queues(_config(tmp_path))]
    assert got == [("q-main-dlq", "dead-letter"), ("q-main", "consumer")]


def test_all_present_writes_nothing(tmp_path: pathlib.Path) -> None:
    fake = Fake(["q-main", "q-main-dlq"])
    rep = mod.audit(_config(tmp_path), ENV, fake.fetch)
    assert rep["rc"] == 0
    assert rep["missing"] == []
    assert fake.posts == []


def test_missing_are_reported_dlq_first(tmp_path: pathlib.Path) -> None:
    rep = mod.audit(_config(tmp_path), ENV, Fake([]).fetch)
    assert rep["rc"] == 1
    assert rep["missing"] == ["q-main-dlq", "q-main"]
    assert "MISSING" in mod.render(rep)


def test_ensure_creates_in_order_and_confirms() -> None:
    fake = Fake([])
    created = mod.ensure("acct", "tok", ["q-main-dlq", "q-main"], fake.fetch, fake.post)
    assert created == ["q-main-dlq", "q-main"]
    assert fake.posts == ["q-main-dlq", "q-main"]
    assert len(fake.gets) == 1  # the confirming re-list


def test_ensure_refuses_a_refused_create() -> None:
    fake = Fake([], fail_create=True)
    with pytest.raises(mod.QueueCreateError, match="creating queue q"):
        mod.ensure("acct", "tok", ["q"], fake.fetch, fake.post)


def test_ensure_refuses_when_the_relist_lacks_the_queue() -> None:
    fake = Fake([], lose=True)
    with pytest.raises(mod.QueueCreateError, match="absent from the listing"):
        mod.ensure("acct", "tok", ["q"], fake.fetch, fake.post)


def test_ensure_with_nothing_missing_makes_no_call() -> None:
    fake = Fake([])
    assert mod.ensure("acct", "tok", [], fake.fetch, fake.post) == []
    assert fake.gets == []
    assert fake.posts == []


def test_unset_credentials_is_77(tmp_path: pathlib.Path) -> None:
    rep = mod.audit(_config(tmp_path), {}, Fake([]).fetch)
    assert rep["rc"] == 77
    assert "unset" in rep["error"]


def test_api_refusal_is_77(tmp_path: pathlib.Path) -> None:
    def refuse(_url: str, _token: str) -> dict:
        return {"success": False, "result": []}

    assert mod.audit(_config(tmp_path), ENV, refuse)["rc"] == 77


def test_unparseable_config_is_77(tmp_path: pathlib.Path) -> None:
    assert mod.audit(_config(tmp_path, "a = 1\na = 2\n"), ENV, Fake([]).fetch)["rc"] == 77


def test_config_without_queues_makes_no_api_call(tmp_path: pathlib.Path) -> None:
    fake = Fake([])
    rep = mod.audit(_config(tmp_path, 'name = "w"\n'), {}, fake.fetch)
    assert rep["rc"] == 0
    assert fake.gets == []
