"""Every vitest workspace owns its module cache.

vitest's default cache is `node_modules/.vitest-cache`, shared by every workspace of the monorepo. The first vitest process that sees a lockfile hash different from the stored one removes the whole directory, and any sibling workspace running at that moment fails at startup with `ENOTEMPTY: directory not empty, rmdir`, before a single test runs. `npm run ci` starts the workspaces' test runs concurrently, so a lockfile edit during a local run reds one of them. Measured on 2026-10-14: with four workspaces started together over a stale hash, the shared default failed in 8 runs of 8 and per-workspace directories in 0 of 8.
"""

from __future__ import annotations

import json
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


VITEST_CMD_RE = re.compile(r"(?<![\w.-])vitest(?![\w.-])")


def runs_vitest(scripts: object) -> bool:
    """True when a package.json `scripts` table names the vitest command in any script, whatever the script is called. Only the commands written in that table are read: a script that reaches vitest through a file it runs is not seen, and its workspace is covered by the config scan above instead. A name that merely contains the word (a `.vitest-cache` path, a `vitest-cache` directory, `vitest.config.ts`) is not the command."""
    if not isinstance(scripts, dict):
        return False
    return any(VITEST_CMD_RE.search(str(cmd)) for cmd in scripts.values())


def test_runs_vitest_reads_the_command_and_not_a_name_that_contains_it():
    assert runs_vitest({"test": "vitest run"})
    assert runs_vitest({"unit": "npx vitest --coverage"})
    assert runs_vitest({"t": "node_modules/.bin/vitest run"})
    assert runs_vitest({"all": "npm run x && vitest"})
    assert not runs_vitest({"clean": "rm -rf node_modules/.vitest-cache"})
    assert not runs_vitest({"clean": "rm -rf node_modules/vitest-cache-web"})
    assert not runs_vitest({"lint": "eslint vitest.config.ts"})
    assert not runs_vitest({})
    assert not runs_vitest(None)


def test_each_workspace_that_runs_vitest_has_a_config():
    missing = []
    for rel in _tracked(":(glob)packages/*/package.json") + _tracked(
        ":(glob)workers/*/package.json"
    ):
        scripts = json.loads(paths.from_root(*rel.split("/")).read_text(encoding="utf-8")).get(
            "scripts"
        )
        if runs_vitest(scripts):
            config = rel.rsplit("/", 1)[0] + "/vitest.config.ts"
            if not paths.from_root(*config.split("/")).is_file():
                missing.append(config)
    assert not missing, "vitest workspaces without a config, so on the shared cache: %s" % missing
