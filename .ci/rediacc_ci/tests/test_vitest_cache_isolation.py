"""Every vitest workspace owns its module cache.

vitest's default cache is `node_modules/.vitest-cache`, shared by every workspace of the monorepo. The first vitest process that sees a lockfile hash different from the stored one removes the whole directory, and any sibling workspace running at that moment fails at startup with `ENOTEMPTY: directory not empty, rmdir`, before a single test runs. `npm run ci` starts the workspaces' test runs concurrently, so a lockfile edit during a local run reds one of them. Measured on 2026-10-14: with four workspaces started together over a stale hash, the shared default failed in 8 runs of 8 and per-workspace directories in 0 of 8.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess

from rediacc_ci import paths

CACHE_RE = re.compile(r"fsModuleCachePath:\s*fileURLToPath\(\s*new URL\(\s*'([^']+)'", re.DOTALL)


def _tracked(pattern: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", pattern],
        cwd=paths.repo_root(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(rel for rel in out.split("\0") if rel)


def test_each_vitest_config_names_its_own_cache_directory():
    configs = [
        rel
        for rel in _tracked(":(glob)**/vitest.config.ts")
        if not rel.startswith("private/") and "node_modules" not in rel
    ]
    assert len(configs) >= 7, "the scan found %d vitest config(s): %s" % (len(configs), configs)
    seen: dict[str, str] = {}
    for rel in configs:
        text = paths.from_root(*rel.split("/")).read_text(encoding="utf-8")
        match = CACHE_RE.search(text)
        assert match, "%s leaves vitest's shared default module cache in place" % rel
        target = match.group(1)
        assert target.startswith("../../node_modules/.vitest-cache-"), "%s: %s" % (rel, target)
        assert target not in seen, "%s and %s share the cache %s" % (rel, seen[target], target)
        seen[target] = rel


# The command, not a module path: `vitest/config` and `vitest/node` are imports, so a following '/' ends the match like a '.' or '-' does. The package's own entry files (`vitest/vitest.mjs`, `vitest/dist/cli.js`) are the command run by path.
VITEST_CMD_RE = re.compile(r"(?<![\w.-])vitest(?:/vitest\.m?js|/dist/cli\.m?js)?(?![\w./-])")


SCRIPT_FILE_RE = re.compile(r"[\w./@-]+\.(?:[cm]?[jt]s|sh|py)(?![\w./-])")

# Script files read per workspace, so a cycle or a deep chain ends.
MAX_SCRIPT_FILES = 50


def _inside(workspace: pathlib.Path, name: str) -> pathlib.Path | None:
    """The file a command names under the workspace, or None for an absolute path, a `..` segment or anything that resolves outside it (a symlink included)."""
    rel = pathlib.PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    target = workspace / rel
    try:
        target.resolve().relative_to(workspace.resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


def runs_vitest(scripts: object, workspace: pathlib.Path | None = None) -> bool:
    """True when a package.json `scripts` table names the vitest command in any script, whatever the script is called. A name that merely contains the word (a `.vitest-cache` path, a `vitest-cache` directory, `vitest.config.ts`, an import path such as `vitest/config`) is not the command. With a `workspace` directory, a script file named on a command line (`node scripts/run.js`, `bash x.sh`) is read from that directory too, and so is every script file that one names in turn, each file once and at most MAX_SCRIPT_FILES in all; a name that is absolute or leaves the workspace is not read."""
    if not isinstance(scripts, dict):
        return False
    commands = [str(cmd) for cmd in scripts.values()]
    if any(VITEST_CMD_RE.search(cmd) for cmd in commands):
        return True
    if workspace is None:
        return False
    visited: set[pathlib.Path] = set()
    queue = [name for cmd in commands for name in SCRIPT_FILE_RE.findall(cmd)]
    while queue and len(visited) < MAX_SCRIPT_FILES:
        target = _inside(workspace, queue.pop(0))
        if target is None or target.resolve() in visited:
            continue
        visited.add(target.resolve())
        text = target.read_text(encoding="utf-8", errors="replace")
        if VITEST_CMD_RE.search(text):
            return True
        queue.extend(SCRIPT_FILE_RE.findall(text))
    return False


def test_runs_vitest_reads_the_command_and_not_a_name_that_contains_it():
    assert runs_vitest({"test": "vitest run"})
    assert runs_vitest({"unit": "npx vitest --coverage"})
    assert runs_vitest({"t": "node_modules/.bin/vitest run"})
    assert runs_vitest({"all": "npm run x && vitest"})
    assert runs_vitest({"t": "node node_modules/vitest/vitest.mjs run"})
    assert runs_vitest({"t": "node node_modules/vitest/dist/cli.js run"})
    assert not runs_vitest({"t": "node scripts/x.js node_modules/vitest/config"})
    assert not runs_vitest({"clean": "rm -rf node_modules/.vitest-cache"})
    assert not runs_vitest({"clean": "rm -rf node_modules/vitest-cache-web"})
    assert not runs_vitest({"lint": "eslint vitest.config.ts"})
    assert not runs_vitest({})
    assert not runs_vitest(None)


def test_runs_vitest_follows_a_script_file_named_in_a_command(tmp_path: pathlib.Path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "unit.sh").write_text('#!/bin/sh\nexec npx vitest run "$@"\n')
    (tmp_path / "scripts" / "lint.js").write_text("console.log('lint only')\n")
    through_file = {"test": "bash scripts/unit.sh"}
    assert not runs_vitest(through_file)
    assert runs_vitest(through_file, tmp_path)
    assert runs_vitest({"test": "node ./scripts/unit.sh --ci"}, tmp_path)
    assert not runs_vitest({"test": "node scripts/lint.js"}, tmp_path)
    assert not runs_vitest({"test": "bash scripts/absent.sh"}, tmp_path)


def test_runs_vitest_ignores_an_import_path_and_a_name_outside_the_workspace(
    tmp_path: pathlib.Path,
):
    workspace = tmp_path / "ws"
    (workspace / "scripts").mkdir(parents=True)
    (workspace / "scripts" / "cfg.js").write_text("import { defineConfig } from 'vitest/config';\n")
    (tmp_path / "other.sh").write_text("npx vitest run\n")
    (tmp_path / "abs.sh").write_text("npx vitest run\n")
    assert not runs_vitest({"build": "node scripts/cfg.js"}, workspace)
    assert not runs_vitest({"t": "bash ../other.sh"}, workspace)
    assert not runs_vitest({"t": "bash scripts/../../other.sh"}, workspace)
    assert not runs_vitest({"t": "bash %s" % (tmp_path / "abs.sh")}, workspace)
    (workspace / "link.sh").symlink_to(tmp_path / "other.sh")
    assert not runs_vitest({"t": "bash link.sh"}, workspace)


def test_runs_vitest_follows_script_files_transitively_and_ends_on_a_cycle(
    tmp_path: pathlib.Path,
):
    (tmp_path / "a.sh").write_text("bash b.sh\n")
    (tmp_path / "b.sh").write_text("node c.js\n")
    (tmp_path / "c.js").write_text("run('npx vitest run')\n")
    assert runs_vitest({"t": "bash a.sh"}, tmp_path)
    (tmp_path / "x.sh").write_text("bash y.sh\n")
    (tmp_path / "y.sh").write_text("bash x.sh\n")
    assert not runs_vitest({"t": "bash x.sh"}, tmp_path)
    for i in range(MAX_SCRIPT_FILES + 5):
        (tmp_path / ("n%d.sh" % i)).write_text("bash n%d.sh\n" % (i + 1))
    (tmp_path / ("n%d.sh" % (MAX_SCRIPT_FILES + 5))).write_text("npx vitest run\n")
    assert not runs_vitest({"t": "bash n0.sh"}, tmp_path)


def test_each_workspace_that_runs_vitest_has_a_config():
    missing = []
    for rel in _tracked(":(glob)packages/*/package.json") + _tracked(
        ":(glob)workers/*/package.json"
    ):
        scripts = json.loads(paths.from_root(*rel.split("/")).read_text(encoding="utf-8")).get(
            "scripts"
        )
        workspace = paths.from_root(*rel.split("/")).parent
        if runs_vitest(scripts, workspace):
            config = rel.rsplit("/", 1)[0] + "/vitest.config.ts"
            if not paths.from_root(*config.split("/")).is_file():
                missing.append(config)
    assert not missing, "vitest workspaces without a config, so on the shared cache: %s" % missing
