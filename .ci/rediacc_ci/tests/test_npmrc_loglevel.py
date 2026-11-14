"""Every tracked `.npmrc` keeps npm's notices off stderr.

npm 12 logs every `npm run` and `npx` as `npm notice run ...` lines on stderr, where npm 11 printed a `> pkg@ver script` banner on stdout. Gates and tests here read stderr exactly, and four pytest cases went red on 2026-11-14 until `.npmrc` set `loglevel=warn`. npm reads the project config from the nearest directory holding a `package.json`, so each project's own `.npmrc` must carry the key; the repo-root one never reaches `workers/proxy` or `private/account/web`.
"""

from __future__ import annotations

import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.quality import npmrc

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()


def _tracked_npmrcs() -> list[pathlib.Path]:
    """The console's tracked `.npmrc` files plus those of each checked-out submodule."""
    found: list[pathlib.Path] = []
    repos = [ROOT]
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "config", "-f", ".gitmodules", "--get-regexp", r"\.path$"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in listing.stdout.splitlines():
        sub = ROOT / line.split()[1]
        if (sub / ".git").exists():
            repos.append(sub)
    for repo in repos:
        files = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "*.npmrc", "**/.npmrc", ".npmrc"],
            capture_output=True,
            text=True,
            check=True,
        )
        found += sorted({repo / rel for rel in files.stdout.split()})
    return found


def test_every_tracked_npmrc_sets_loglevel_warn() -> None:
    files = _tracked_npmrcs()
    # Anti-vacuity: the root file and at least one nested project are in the list.
    assert ROOT / ".npmrc" in files
    assert len(files) >= 2, files
    wrong = {
        str(f.relative_to(ROOT)): npmrc.setting_value(f.read_text(encoding="utf-8"), "loglevel")
        for f in files
        if npmrc.setting_value(f.read_text(encoding="utf-8"), "loglevel") != "warn"
    }
    assert wrong == {}, "these .npmrc files do not set loglevel=warn: %r" % wrong


def test_the_reader_sees_a_missing_and_a_present_loglevel() -> None:
    """Control: the reader this test relies on answers both ways."""
    assert npmrc.setting_value("ignore-scripts=true\n", "loglevel") == ""
    assert npmrc.setting_value("ignore-scripts=true\nloglevel=warn\n", "loglevel") == "warn"
