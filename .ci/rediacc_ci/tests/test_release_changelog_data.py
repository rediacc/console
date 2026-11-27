"""`rediacc_ci.release.changelog_data`: the accept cases of PLAN-release-notes box RN8, one test each."""

from __future__ import annotations

import json
import typing

import pytest

from rediacc_ci.release import changelog_data as cd

ORIGIN = "https://releases.test"
REPO = "rediacc/console"
API = cd.GH_API_BASE


def _release(tag: str) -> dict[str, typing.Any]:
    return {
        "tag_name": tag,
        "draft": False,
        "published_at": "2026-11-2%sT00:00:00Z" % tag[-1],
        "html_url": "https://gh/%s" % tag,
    }


def _fake(overrides: dict[str, tuple[int, str]] | None = None) -> cd.Fetch:
    table: dict[str, tuple[int, str]] = {
        "%s/repos/%s/releases?per_page=100&page=1" % (API, REPO): (
            200,
            json.dumps([_release("v4.0.2"), _release("v4.0.1")]),
        ),
        ORIGIN + "/cli/v4.0.2/release-notes.json": (
            200,
            json.dumps(
                {"version": "4.0.2", "groups": {"Added": ["Backups now resume"], "Fixed": []}}
            ),
        ),
        ORIGIN + "/cli/stable/history.json": (
            200,
            json.dumps([{"version": "4.0.2", "promoted_at": "2026-11-26T00:00:00Z"}]),
        ),
    }
    table.update(overrides or {})

    def fetch(url: str) -> tuple[int, str]:
        return table.get(url, (404, ""))

    return fetch


def test_versions_newest_first_with_notes_and_stable_marker():
    doc = cd.build("4.0.3", _fake(), REPO, ORIGIN)
    by = {e["version"]: e for e in doc["versions"]}
    assert [e["version"] for e in doc["versions"]] == ["4.0.3", "4.0.2", "4.0.1"]
    assert by["4.0.2"]["stable_since"] == "4.0.2"
    assert by["4.0.2"]["groups"] == {"Added": ["Backups now resume"]}
    assert by["4.0.1"]["groups"] is None
    assert by["4.0.1"]["stable_since"] == "4.0.2"
    assert by["4.0.3"]["stable_since"] is None


def test_without_app_version_only_published_versions_are_listed():
    doc = cd.build(None, _fake(), REPO, ORIGIN)
    assert [e["version"] for e in doc["versions"]] == ["4.0.2", "4.0.1"]


def test_failed_release_fetch_raises():
    bad = _fake({"%s/repos/%s/releases?per_page=100&page=1" % (API, REPO): (500, "")})
    with pytest.raises(cd.ChangelogError):
        cd.build(None, bad, REPO, ORIGIN)


def test_failed_notes_fetch_raises_but_absent_notes_do_not():
    bad = _fake({ORIGIN + "/cli/v4.0.2/release-notes.json": (503, "")})
    with pytest.raises(cd.ChangelogError):
        cd.build(None, bad, REPO, ORIGIN)


def test_absent_history_is_empty_not_an_error():
    doc = cd.build(None, _fake({ORIGIN + "/cli/stable/history.json": (404, "")}), REPO, ORIGIN)
    assert all(e["stable_since"] is None for e in doc["versions"])


def test_main_exits_non_zero_on_a_failed_fetch(tmp_path, monkeypatch, capsys):
    def boom(_token: str | None) -> cd.Fetch:
        def fetch(_url: str) -> tuple[int, str]:
            raise cd.ChangelogError("network down")

        return fetch

    monkeypatch.setattr(cd, "http_fetch", boom)
    out = tmp_path / "c.json"
    assert cd.main([str(out)]) == 1
    assert not out.exists()
    assert "network down" in capsys.readouterr().err


def test_main_writes_the_document(tmp_path, monkeypatch):
    monkeypatch.setattr(cd, "http_fetch", lambda _t: _fake())
    monkeypatch.setenv("APP_VERSION", "4.0.3")
    monkeypatch.setenv("RELEASES_ORIGIN", ORIGIN)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    out = tmp_path / "sub" / "c.json"
    assert cd.main([str(out)]) == 0
    assert json.loads(out.read_text())["versions"][0]["version"] == "4.0.3"
