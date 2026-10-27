"""The removal hint `check-worker-secret-names.ts` prints must be a command the prune verb accepts."""

from __future__ import annotations

import re
import shlex

from rediacc_ci import paths
from rediacc_ci.ops import prune_worker_secrets as verb

GATE = "scripts/gates/check-worker-secret-names.ts"
ENV = {"CLOUDFLARE_API_TOKEN": "t", "CLOUDFLARE_ACCOUNT_ID": "a"}


def _hint_argv(region: str) -> list[str]:
    src = paths.repo_root().joinpath(GATE).read_text(encoding="utf-8")
    match = re.search(r"const PRUNE_HINT =\s*'([^']+)'", src)
    assert match, "PRUNE_HINT constant not found in the gate"
    words = shlex.split(match.group(1).replace("<region>", region))
    assert words[:3] == ["PYTHONPATH=.ci", "python3", "-m"]
    assert words[3] == verb.SELF
    return words[4:]


def test_hint_argv_parses_with_an_explicit_region() -> None:
    opts = verb.parse(_hint_argv("eu"))
    assert opts is not None
    assert opts.region == "eu"
    assert opts.archive
    # --archive alone archives, confirms, then deletes the original: no --delete is needed.
    assert not opts.delete


def test_hint_is_not_refused() -> None:
    code, lines, _rows = verb.run(_hint_argv("eu"), ENV, lambda *_a, **_k: [])
    assert code == 0, lines


def test_the_old_bare_delete_hint_is_refused() -> None:
    code, _lines, _rows = verb.run(["--delete"], ENV, lambda *_a, **_k: [])
    assert code == 2


def test_archive_without_a_region_is_refused() -> None:
    code, lines, _rows = verb.run(["--archive"], ENV, lambda *_a, **_k: [])
    assert code == 2
    assert "--archive needs --region" in lines[0]
