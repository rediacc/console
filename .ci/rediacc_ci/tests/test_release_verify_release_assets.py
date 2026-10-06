"""`rediacc_ci.release.verify_release_assets` against its bash twin.

`gh` is faked on PATH (prepended, real `jq` stays reachable); `jq` itself is real on both sides, since it is a generic JSON tool with no credentials and no production traffic, same reasoning as every other release-side port in this box.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.release import verify_release_assets
from rediacc_ci.tests import differential as diff
from rediacc_ci.well_known import GH_REPO

if TYPE_CHECKING:
    import pathlib

# SERIALISED, BECAUSE THE SUBJECT HARD-CODES ITS SCRATCH PATHS. Both sides write `/tmp/release.json` and `/tmp/release.err` and then read them back (verify-release-assets.sh:34,41 and the port's mirror of it), so under `--dist loadgroup` the four cases in this file land on four different workers and overwrite one another's file between the write and the read. The failure is a lie
# about the CODE: a case whose fixture says two assets reads a neighbour's empty one and reports "Release v1.2.3 has no rdc-* CLI assets".
#
# Observed in CI on 2026-09-15 (job 104583449222) after unrelated provisioning made the suite busier -- it is a RACE, so it had been winning silently, not absent. The same class and the same remedy as `deploy-fixed-tmp`, whose own note states the principle: "the group name is the mutex, so every module sharing a fixed /tmp path has to share one name."
#
# ITS OWN NAME RATHER THAN `deploy-fixed-tmp`, and that is the principle applied rather than ignored: swept first, and `/tmp/release.json` and `/tmp/release.err` are touched by exactly one twin/port pair, driven by exactly this module. It shares no path with the deploy trio, so joining their mutex would serialise it against tests it can never collide with.
pytestmark = pytest.mark.xdist_group("release-fixed-tmp")

TWIN = ".ci/scripts/release/verify-release-assets.sh"
MODULE = "verify_release_assets"

FAKE_GH_TEMPLATE = """#!{python}
import sys
sys.stdout.write({stdout!r})
sys.stderr.write({stderr!r})
sys.exit({rc})
"""


def _make_fake_gh(
    tmp_path: pathlib.Path, *, rc: int, stdout: str = "", stderr: str = ""
) -> pathlib.Path:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "gh"
    script.write_text(
        FAKE_GH_TEMPLATE.format(python=sys.executable, stdout=stdout, stderr=stderr, rc=rc)
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def run_both(
    bindir: pathlib.Path, env_extra: dict[str, str]
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    path_with_fake = f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    old_env = diff.env_for(**env_extra, PATH=path_with_fake)
    new_env = diff.env_for(
        **env_extra, PATH=path_with_fake, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"
    )
    old = diff.twin_call(
        TWIN,
        sorted("%s=%s" % kv for kv in env_extra.items()),
        lambda: diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30),
        work=(bindir.parent,),
    )
    new = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, timeout=30)
    return old, new


def test_a_release_with_a_cli_asset_passes_on_both_sides(tmp_path: pathlib.Path) -> None:
    body = json.dumps(
        {"tagName": "v1.2.3", "assets": [{"name": "rdc-linux-x64"}, {"name": "checksums.txt"}]}
    )
    bindir = _make_fake_gh(tmp_path, rc=0, stdout=body)
    old, new = run_both(bindir, {"VERSION": "v1.2.3", "GITHUB_REPOSITORY": GH_REPO})
    assert old == (0, "✓ Release v1.2.3 has 1 rdc-* CLI asset(s)\n", "")
    assert new == old


def test_a_release_with_no_cli_assets_fails_on_both_sides(tmp_path: pathlib.Path) -> None:
    body = json.dumps(
        {"tagName": "v1.2.3", "assets": [{"name": "checksums.txt"}, {"name": "notes.md"}]}
    )
    bindir = _make_fake_gh(tmp_path, rc=0, stdout=body)
    old, new = run_both(bindir, {"VERSION": "v1.2.3", "GITHUB_REPOSITORY": GH_REPO})
    assert old[0] == 1
    assert new[0] == 1
    assert "no rdc-* CLI assets" in old[1]
    assert "no rdc-* CLI assets" in new[1]
    assert '"checksums.txt"' in old[1]
    assert '"checksums.txt"' in new[1]
    assert new[1] == old[1]


def test_a_missing_release_fails_on_both_sides(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_gh(tmp_path, rc=1, stderr="release not found\n")
    old, new = run_both(bindir, {"VERSION": "v9.9.9", "GITHUB_REPOSITORY": GH_REPO})
    assert old == (1, "::error::no GitHub Release found for v9.9.9\nrelease not found\n", "")
    assert new == old


def test_missing_version_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_gh(tmp_path, rc=0, stdout="{}")
    old, new = run_both(bindir, {"GITHUB_REPOSITORY": GH_REPO})
    assert old[0] == 1
    assert new[0] == 1
    assert "VERSION" in old[2]
    assert "VERSION" in new[2]


# --- gh_retry (PLAN-gh-retry G12): a transient read fault is retried, a non-transient one is not ---


class _FakeGh:
    """Scripted `gh` outcomes (rc, stdout, stderr), one per attempt, the last repeating. Patched in as the `runner` and `sleep` of `gh_retry.gh`, so nothing touches the network or the clock."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.slept = []

    def install(self, monkeypatch, module):
        real = module.gh_retry.gh
        fake = self

        def runner(args, **_kw):
            fake.calls.append(list(args))
            rc, out, err = fake.outcomes[min(len(fake.calls), len(fake.outcomes)) - 1]
            return module.gh_retry.ghx.GhResult(["gh", *args], rc, out, err)

        monkeypatch.setattr(
            module.gh_retry,
            "gh",
            lambda args, **kw: real(args, runner=runner, **{**kw, "sleep": fake.slept.append}),
        )
        return self


def _verify(monkeypatch, fake):
    mod = verify_release_assets

    fake.install(monkeypatch, mod)
    monkeypatch.setenv("VERSION", "v1.2.3")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    return mod


BODY = '{"tagName":"v1.2.3","assets":[{"name":"rdc-linux"}]}'


def test_a_502_then_success_verifies(monkeypatch, capsys) -> None:
    fake = _FakeGh((1, "", "gh: Server Error (HTTP 502)"), (0, BODY, ""))
    mod = _verify(monkeypatch, fake)
    assert mod.main([]) == 0
    assert len(fake.calls) == 2
    assert fake.slept == [5.0]
    assert "has 1 rdc-* CLI asset" in capsys.readouterr().out


def test_persistent_5xx_refuses_to_seal(monkeypatch, capsys) -> None:
    fake = _FakeGh((1, "", "gh: Server Error (HTTP 502)"))
    mod = _verify(monkeypatch, fake)
    assert mod.main([]) == 1
    out = capsys.readouterr().out
    assert "no GitHub Release found" in out
    assert "HTTP 502" in out
    assert len(fake.calls) == 3


def test_a_404_is_not_retried(monkeypatch) -> None:
    fake = _FakeGh((1, "", "release not found (HTTP 404)"))
    mod = _verify(monkeypatch, fake)
    assert mod.main([]) == 1
    assert len(fake.calls) == 1
    assert fake.slept == []
