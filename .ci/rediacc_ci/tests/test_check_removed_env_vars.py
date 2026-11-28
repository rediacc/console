"""`check:ci-removed-env-vars` (`.ci/scripts/quality/check_removed_env_vars.py`): a variable removed with no deprecation window stays out of every tracked file (PLAN-rmcp-config-edit-removal.md, Design 6, box R6).

CONTROL FIRST, AND NEVER ON THE REAL TREE. Every plant goes into a throwaway git repository under `tmp_path` and the gate is pointed at it with `--root`. The unplanted repository must pass first, so a red on a plant is the plant's doing and not a broken fixture. The planted name is not in the real list; the one real name this file needs is spelled in two pieces, which is also the one way a test may name it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import typing

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
GATE = ROOT / ".ci" / "scripts" / "quality" / "check_removed_env_vars.py"
CONFIG_REL = ".ci/config/removed-env-vars.json"
NAME = "PLANTED_REMOVED_VAR"
CONFIG_EDIT = "REDIACC_ALLOW" + "_CONFIG_EDIT"


def _git(cwd: pathlib.Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def repo(
    tmp_path: pathlib.Path,
    files: dict[str, str],
    excluded: dict[str, str] | None = None,
    names: list[str] | None = None,
) -> pathlib.Path:
    config = {
        "removed": [{"name": n, "reason": "test"} for n in ([NAME] if names is None else names)],
        "excluded": excluded or {},
    }
    _git(tmp_path, "init", "-q")
    for rel, text in {CONFIG_REL: json.dumps(config), **files}.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    return tmp_path


def run(root: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_control_a_clean_repository_passes(tmp_path: pathlib.Path) -> None:
    done = run(repo(tmp_path, {"docs/page.md": "nothing removed here\n"}))
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_planted_occurrence_reds_with_its_path_and_line(tmp_path: pathlib.Path) -> None:
    done = run(repo(tmp_path, {"docs/page.md": "intro\nexport %s='*'\n" % NAME}))
    assert done.returncode == 1, done.stdout
    assert "docs/page.md:2: names the removed variable %s" % NAME in done.stdout


def test_a_planted_occurrence_in_a_locale_string_reds(tmp_path: pathlib.Path) -> None:
    locale = json.dumps({"errors": {"agent": {"x": "set %s to override" % NAME}}})
    done = run(repo(tmp_path, {"packages/cli/src/i18n/locales/de/cli.json": locale}))
    assert done.returncode == 1, done.stdout


def test_an_excluded_prefix_is_not_scanned(tmp_path: pathlib.Path) -> None:
    root = repo(
        tmp_path,
        {"agent/ledgers/x.jsonl": NAME + "\n", "docs/page.md": "clean\n"},
        {"agent/ledgers/": "record"},
    )
    done = run(root)
    assert done.returncode == 0, done.stdout


def test_an_excluded_pattern_covers_its_file_in_every_locale_and_nothing_else(
    tmp_path: pathlib.Path,
) -> None:
    files = {
        "blog/de/post.md": NAME + "\n",
        "blog/ja/post.md": NAME + "\n",
        "blog/de/other.md": "uses %s\n" % NAME,
    }
    done = run(repo(tmp_path, files, {"blog/*/post.md": "announcement"}))
    assert done.returncode == 1, done.stdout
    assert "blog/de/other.md:1" in done.stdout
    assert "post.md" not in done.stdout


def test_a_split_spelling_passes(tmp_path: pathlib.Path) -> None:
    done = run(
        repo(tmp_path, {"src/a.test.ts": "const V = ['PLANTED', 'REMOVED', 'VAR'].join('_');\n"})
    )
    assert done.returncode == 0, done.stdout


def test_a_dead_exclusion_reds(tmp_path: pathlib.Path) -> None:
    done = run(repo(tmp_path, {"docs/page.md": "clean\n"}, {"agent/gone/": "dead"}))
    assert done.returncode == 1, done.stdout
    assert "'agent/gone/' matches no tracked path" in done.stdout


def test_a_dead_pattern_reds(tmp_path: pathlib.Path) -> None:
    done = run(repo(tmp_path, {"docs/page.md": "clean\n"}, {"blog/*/gone.md": "dead"}))
    assert done.returncode == 1, done.stdout


def test_an_empty_removed_list_is_a_refusal_not_a_pass(tmp_path: pathlib.Path) -> None:
    done = run(repo(tmp_path, {"docs/page.md": "clean\n"}, names=[]))
    assert done.returncode == 1, done.stdout
    assert "refusing an empty check" in done.stdout


def test_the_real_config_lists_the_config_edit_override_with_its_decision() -> None:
    data = json.loads((ROOT / CONFIG_REL).read_text(encoding="utf-8"))
    entries = {entry["name"]: entry for entry in data["removed"]}
    assert CONFIG_EDIT in entries
    assert "D17" in entries[CONFIG_EDIT]["decision"]
    assert set(data["excluded"]) >= {
        "agent/ledgers/",
        "agent/reviews/",
        "agent/programs/remote-mcp/",
    }


def test_the_selftest_passes() -> None:
    done = subprocess.run(
        [sys.executable, str(GATE), "--selftest"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr
