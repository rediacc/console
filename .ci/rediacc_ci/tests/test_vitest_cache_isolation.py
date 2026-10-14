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


def test_each_workspace_that_runs_vitest_has_a_config():
    missing = []
    for rel in _tracked(":(glob)packages/*/package.json") + _tracked(
        ":(glob)workers/*/package.json"
    ):
        scripts = json.loads(paths.from_root(*rel.split("/")).read_text(encoding="utf-8")).get(
            "scripts", {}
        )
        # Any script that runs vitest counts, whatever it is named: an indirection such as "test": "npm run x" reaches vitest through the script it names.
        if any(re.search(r"\bvitest\b", str(cmd)) for cmd in scripts.values()):
            config = rel.rsplit("/", 1)[0] + "/vitest.config.ts"
            if not paths.from_root(*config.split("/")).is_file():
                missing.append(config)
    assert not missing, "vitest workspaces without a config, so on the shared cache: %s" % missing
