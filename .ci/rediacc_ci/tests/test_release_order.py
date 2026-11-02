"""`rediacc_ci.release.order.account_refusal`, offline.

Every reader is a fake, so nothing here reaches R2 or releases.rediacc.com. The declaration under test is the real `.ci/config/release-requires.json`, so a malformed edit to it fails here. Ancestry is faked from a table, except in `test_r1_is_cli_behind_against_v2_4_0_with_real_git`, which asks the console's own git whether the R1 commits are in v2.4.0 and skips when the tag or the objects are absent (a shallow clone).
"""

from __future__ import annotations

import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.release import order

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
ENTRIES = order.load_entries(ROOT)
R1 = next(e for e in ENTRIES if e["id"] == "R1-config-envelope")
SINCE = R1["since"]["commit"]
CLI_A, CLI_B = R1["cli_commits"]
POINTER_NEW = "1" * 40  # descends from SINCE
POINTER_OLD = "2" * 40  # predates SINCE
TAG_OLD = "3" * 40  # v2.4.0: lacks both CLI commits
TAG_NEW = "4" * 40  # v2.5.0: carries both


class Ancestry:
    """A git-ancestry fake from a table of (ancestor, descendant) pairs, recording every question."""

    def __init__(self, pairs: set[tuple[str, str]]) -> None:
        self.pairs = pairs
        self.calls: list[tuple[pathlib.Path, str, str]] = []

    def __call__(self, repo: pathlib.Path, ancestor: str, descendant: str) -> bool | None:
        self.calls.append((repo, ancestor, descendant))
        return (ancestor, descendant) in self.pairs


TRUTH = {
    (SINCE, POINTER_NEW),
    (CLI_A, TAG_NEW),
    (CLI_B, TAG_NEW),
}

TAGS = {"v2.4.0": TAG_OLD, "v2.5.0": TAG_NEW}


def refusal(
    pointer=POINTER_NEW, version="2.5.0", sealed=True, tags=None, probe=None, channel="edge"
):
    return order.account_refusal(
        channel,
        pointer,
        manifest_reader=lambda _ch: version,
        sentinel_exists=lambda _v: sealed,
        tag_commit=(TAGS if tags is None else tags).get,
        is_ancestor=probe or Ancestry(TRUTH),
        entries=ENTRIES,
        root=ROOT,
    )


def test_declaration_names_r1_with_full_shas():
    assert R1["component"] == "account"
    assert R1["since"]["repo"] == "private/account"
    for sha in (SINCE, CLI_A, CLI_B):
        assert len(sha) == 40
        assert int(sha, 16) >= 0
    assert SINCE.startswith("aaf3c251")
    assert CLI_A.startswith("9d0172906")
    assert CLI_B.startswith("09d646273")


def test_inactive_entry_admits_without_reading_the_manifest():
    def boom(*_a):
        raise AssertionError("an inactive entry must not read the published CLI")

    probe = Ancestry(TRUTH)
    out = order.account_refusal(
        "edge",
        POINTER_OLD,
        manifest_reader=boom,
        sentinel_exists=boom,
        tag_commit=boom,
        is_ancestor=probe,
        entries=ENTRIES,
        root=ROOT,
    )
    assert out is None
    assert probe.calls == [(ROOT / "private/account", SINCE, POINTER_OLD)]


def test_active_entry_against_v2_4_0_is_cli_behind():
    out = refusal(version="2.4.0")
    assert out == (
        "cli-behind: R1-config-envelope needs %s, %s in a released CLI on edge; published v2.4.0 lacks them"
        % (CLI_A[:9], CLI_B[:9])
    )


def test_one_missing_commit_is_enough_to_refuse():
    out = refusal(version="2.5.0", probe=Ancestry({(SINCE, POINTER_NEW), (CLI_A, TAG_NEW)}))
    assert out is not None
    assert out.startswith("cli-behind: R1-config-envelope")
    assert out.endswith("published v2.5.0 lacks them")


def test_satisfied_when_the_published_cli_carries_every_commit():
    assert refusal(version="2.5.0") is None
    assert refusal(version="2.5.0", channel="stable") is None


def test_missing_sentinel_refuses_even_when_the_tag_carries_the_commits():
    out = refusal(version="2.5.0", sealed=False)
    assert out is not None
    assert out.startswith("cli-behind: R1-config-envelope needs")
    assert out.endswith("published v2.5.0 is not sealed (cli/v2.5.0/.released is absent)")


def test_missing_tag_refuses():
    out = refusal(version="2.5.0", tags={"v2.4.0": TAG_OLD})
    assert out is not None
    assert out.endswith("published v2.5.0 has no tag v2.5.0")


def test_no_published_manifest_refuses():
    for version in ("", "null"):
        out = refusal(version=version)
        assert out is not None
        assert out.endswith("no CLI version is published on edge")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"version": None},
        {"sealed": None},
    ],
)
def test_an_unanswered_probe_refuses_as_unknown(kwargs):
    out = refusal(**kwargs)
    assert out is not None
    assert out.startswith("unknown: ")


def test_an_unknown_ancestry_refuses_as_unknown():
    out = refusal(probe=lambda *_a: None)
    assert out is not None
    assert out.startswith("unknown: R1-config-envelope cannot tell")


def test_non_account_entries_are_ignored():
    other = dict(R1, id="X-other", component="www")
    out = order.account_refusal(
        "edge",
        POINTER_NEW,
        manifest_reader=lambda _ch: "2.4.0",
        sentinel_exists=lambda _v: True,
        tag_commit=TAGS.get,
        is_ancestor=Ancestry(TRUTH),
        entries=[other],
        root=ROOT,
    )
    assert out is None


def test_bad_config_version_is_refused(tmp_path):
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    (tmp_path / order.CONFIG_REL).write_text('{"version": 2, "entries": []}', encoding="utf-8")
    with pytest.raises(order.ConfigError):
        order.load_entries(tmp_path)


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        '{"version": 1, "entries": ["not an object"]}',
        '{"version": 1, "entries": [{"id": "x", "component": "account", "since": "abc", "cli_commits": ["a"]}]}',
    ],
)
def test_a_non_object_config_or_entry_is_a_config_error(tmp_path, text):
    """A config error, so `main` exits 2 with the reason, never a traceback with the refusal code 1."""
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    (tmp_path / order.CONFIG_REL).write_text(text, encoding="utf-8")
    with pytest.raises(order.ConfigError):
        order.load_entries(tmp_path)


def _curl(monkeypatch, stdout: str, rc: int = 0) -> list[list[str]]:
    seen: list[list[str]] = []

    def run(argv, **_kw):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, rc, stdout, "")

    monkeypatch.setattr(order.subprocess, "run", run)
    return seen


def test_a_404_manifest_is_no_manifest(monkeypatch):
    _curl(monkeypatch, "<Error>NoSuchKey</Error>\n404")
    assert order.live_manifest_version("edge") == ""


@pytest.mark.parametrize("status", ["403", "500", "503"])
def test_an_http_error_other_than_404_could_not_answer(monkeypatch, status):
    """`curl -f` exits 22 on all of these; only the 404 is a published-state answer."""
    _curl(monkeypatch, "oops\n" + status)
    assert order.live_manifest_version("edge") is None


def test_a_200_manifest_is_its_version(monkeypatch):
    seen = _curl(monkeypatch, '{"version": "1.2.3"}\n200')
    assert order.live_manifest_version("edge") == "1.2.3"
    assert "-f" not in seen[0]
    assert "-sf" not in seen[0]


def test_a_transport_failure_could_not_answer(monkeypatch):
    _curl(monkeypatch, "", rc=6)
    assert order.live_manifest_version("edge") is None


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
    )


def test_r1_is_cli_behind_against_v2_4_0_with_real_git():
    tag = order.live_tag_commit("v2.4.0", ROOT)
    if tag is None:
        pytest.skip("tag v2.4.0 is not in this clone")
    for sha in (CLI_A, CLI_B):
        if _git("cat-file", "-e", sha + "^{commit}").returncode != 0:
            pytest.skip("R1 CLI commits are not in this clone")

    def probe(repo, ancestor, descendant):
        if ancestor == SINCE:
            return True  # the account submodule may be absent; activity is tested above
        return order.git_is_ancestor(repo, ancestor, descendant)

    out = order.account_refusal(
        "edge",
        POINTER_NEW,
        manifest_reader=lambda _ch: "2.4.0",
        sentinel_exists=lambda _v: True,
        tag_commit=lambda t: order.live_tag_commit(t, ROOT),
        is_ancestor=probe,
        entries=ENTRIES,
        root=ROOT,
    )
    assert out is not None
    assert out.endswith("published v2.4.0 lacks them")


def test_usage_names_the_module_not_an_environment_assignment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        order.main(["--help"])
    usage = capsys.readouterr().out.split("\n", 1)[0]
    assert usage.startswith("usage: python3 -m " + order.SELF)
    assert "PYTHONPATH=" not in usage
