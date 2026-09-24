"""scripts/ops/lib/bench-preflight.sh: the two checks deploy-bench.sh runs before its first remote write.

Both were paid for on 2026-09-24: a deploy applied 21 D1 migrations and then died on an R2 bucket nothing had created, and the retry bundled from a drifted node_modules that Cloudflare refused at startup. `npm` and `npx` are stubs on PATH, so nothing here reaches the network.
"""

import os
import subprocess

from rediacc_ci import paths

LIB = paths.from_root("scripts", "ops", "lib", "bench-preflight.sh")


def _stub(bin_dir, name, body):
    path = bin_dir / name
    path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _run(tmp_path, call, npm_ls_rc=0, listed=(), config=None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "npx.log"
    _stub(bin_dir, "npm", 'if [ "$1" = ls ]; then exit %d; fi\nexit 0\n' % npm_ls_rc)
    names = "".join("name:           %s\\n" % b for b in listed)
    _stub(
        bin_dir,
        "npx",
        'echo "$*" >> %s\nif [ "$3 $4" = "bucket list" ]; then printf "%s"; fi\nexit 0\n'
        % (log, names),
    )
    cfg = tmp_path / "wrangler.test.toml"
    cfg.write_text(config or "", encoding="utf-8")
    env = dict(os.environ, PATH="%s:%s" % (bin_dir, os.environ["PATH"]))
    done = subprocess.run(
        ["bash", "-c", 'source "%s"; %s' % (LIB, call.replace("CFG", str(cfg)))],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        check=False,
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return done, calls


TWO_BUCKETS = (
    '[[r2_buckets]]\nbucket_name = "have-it"\n\n[[r2_buckets]]\nbucket_name = "missing-one"\n'
)


def test_a_missing_bound_bucket_is_created_before_anything_else(tmp_path):
    done, calls = _run(
        tmp_path, "bench_preflight_buckets CFG", listed=("have-it",), config=TWO_BUCKETS
    )
    assert done.returncode == 0, done.stderr
    assert "wrangler r2 bucket create missing-one" in calls
    assert not any("create have-it" in c for c in calls)


def test_control_nothing_is_created_when_every_bucket_exists(tmp_path):
    done, calls = _run(
        tmp_path,
        "bench_preflight_buckets CFG",
        listed=("have-it", "missing-one"),
        config=TWO_BUCKETS,
    )
    assert done.returncode == 0, done.stderr
    assert not any("create" in c for c in calls)


def test_a_jurisdictional_binding_is_refused_not_guessed(tmp_path):
    cfg = TWO_BUCKETS + 'jurisdiction = "eu"\n'
    done, calls = _run(tmp_path, "bench_preflight_buckets CFG", config=cfg)
    assert done.returncode == 1
    assert "jurisdiction" in done.stderr
    assert not any("create" in c for c in calls)


def test_a_drifted_install_is_refused(tmp_path):
    done, _ = _run(tmp_path, 'bench_preflight_lockfile "%s"' % tmp_path, npm_ls_rc=1)
    assert done.returncode == 1
    assert "does not match its package-lock.json" in done.stderr


def test_control_a_clean_install_passes(tmp_path):
    done, _ = _run(tmp_path, 'bench_preflight_lockfile "%s"' % tmp_path, npm_ls_rc=0)
    assert done.returncode == 0, done.stderr


def test_deploy_bench_runs_both_preflights_before_the_first_migration():
    text = paths.from_root("scripts", "ops", "deploy-bench.sh").read_text(encoding="utf-8")
    migrate = text.index("d1 migrations apply")
    assert -1 < text.index("bench_preflight_lockfile ") < migrate
    assert -1 < text.index("bench_preflight_buckets ") < migrate
