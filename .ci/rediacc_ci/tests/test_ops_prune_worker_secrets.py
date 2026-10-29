"""The removal hint `check-worker-secret-names.ts` prints must be a command the prune verb accepts."""

from __future__ import annotations

import ast
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


def test_the_cd_owned_console_switch_is_never_an_extra() -> None:
    live: list[dict[str, object]] = [
        {"name": "EXECUTOR_MODE", "type": "secret_text"},
        {"name": "STALE_KEY", "type": "secret_text"},
        {"name": "ACCOUNT_JWT_SECRET", "type": "secret_text"},
    ]
    assert verb.extras(live, ["ACCOUNT_JWT_SECRET"]) == ["STALE_KEY"]


def _payload_keys_by_ast() -> list[str]:
    """The keys of the dict `deploy_bench.secrets_payload()` returns, read from its AST (independent of the gate's text extractor)."""
    src = paths.repo_root().joinpath(".ci/rediacc_ci/ops/deploy_bench.py").read_text("utf-8")
    fn = next(
        n
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.FunctionDef) and n.name == "secrets_payload"
    )
    ret = [n.value for n in ast.walk(fn) if isinstance(n, ast.Return)]
    dicts = [v for v in ret if isinstance(v, ast.Dict)]
    assert len(dicts) == 1
    return [str(k.value) for k in dicts[0].keys if isinstance(k, ast.Constant)]


def test_a_bench_row_is_loaded_only_on_request() -> None:
    plain = verb.load_workers()
    assert all(r.region != "bench" for r in plain)
    with_bench = verb.load_workers(bench=True)
    assert [r.region for r in with_bench][-1] == "bench"
    row = with_bench[-1]
    assert row.target == "bench"
    toml = paths.repo_root().joinpath("workers/account/wrangler.bench.toml").read_text("utf-8")
    assert re.search(r'^name = "%s"$' % re.escape(row.worker), toml, re.MULTILINE)


def test_the_bench_expected_set_is_the_deploy_bench_payload() -> None:
    row = verb.load_workers(bench=True)[-1]
    want = verb.expected_for(row)
    assert want == _payload_keys_by_ast()
    assert len(want) > 20
    assert want != verb.expected_for(verb.load_workers()[0])


def test_bench_argv_selects_bench_and_archive_accepts_it() -> None:
    opts = verb.parse(["--region", "bench", "--archive", "--dry-run"])
    assert opts is not None
    assert opts.region == "bench"
    assert opts.archive
    assert opts.dry_run


def test_bench_extras_are_the_seven_legacy_names_and_each_maps_to_a_bws_key() -> None:
    legacy = [
        "API_KEY",
        "ED25519_PRIVATE_KEY",
        "ED25519_PUBLIC_KEY",
        "JWT_SECRET",
        "TURNSTILE_SECRET_KEY",
        "X25519_PRIVATE_KEY",
        "X25519_PUBLIC_KEY",
    ]
    row = verb.load_workers(bench=True)[-1]
    live: list[dict[str, object]] = [
        {"name": n, "type": "secret_text"} for n in [*verb.expected_for(row), *legacy]
    ]
    live += [{"name": "EXECUTOR_MODE", "type": "secret_text"}]
    live += [{"name": "__ARCHIVE_OLD", "type": "secret_text"}]
    assert verb.extras(live, verb.expected_for(row)) == legacy
    assert all(verb.bws_key(n, "", "bench") for n in legacy)
    assert verb.bws_key("JWT_SECRET", "", "bench") == "ACCOUNT_JWT_SECRET_DEV"


def test_run_region_bench_lists_the_extras_and_never_all() -> None:
    calls: list[str] = []

    def fetch(*args: object, **_kw: object) -> object:
        path = str(args[1])
        calls.append(path)
        return [{"name": "API_KEY", "type": "secret_text"}]

    code, lines, rows = verb.run(["--region", "bench"], ENV, fetch)
    assert code == 1, lines
    assert [r.region for r in rows] == ["bench"]
    assert rows[0].extras == ["API_KEY"]
    assert all("rediacc-account-bench" in c for c in calls)
    _c, _l, all_rows = verb.run([], ENV, lambda *_a, **_k: [])
    assert all(r.region != "bench" for r in all_rows)
