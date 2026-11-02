"""rediacc_ci.ops.bench_preflight: the two checks rediacc_ci.ops.deploy_bench runs before its first remote write.

Both were paid for on 2026-09-24: a deploy applied 21 D1 migrations and then died on an R2 bucket nothing had created, and the retry bundled from a drifted node_modules that Cloudflare refused at startup. `npm` and `npx` are stubs on PATH, so nothing here reaches the network.
"""

import json
import os
import shlex
import subprocess
import sys

from rediacc_ci import paths

CI_DIR = str(paths.from_root(".ci"))


def _stub(bin_dir, name, body):
    path = bin_dir / name
    path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _run(tmp_path, call, npm_ls_rc=0, listed=(), config=None, npm_ls_out=""):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "npx.log"
    report = tmp_path / "npm-ls.json"
    report.write_text(npm_ls_out, encoding="utf-8")
    _stub(
        bin_dir,
        "npm",
        'if [ "$1" = ls ]; then cat %s; exit %d; fi\nexit 0\n'
        % (shlex.quote(str(report)), npm_ls_rc),
    )
    names = "".join("name:           %s\\n" % b for b in listed)
    _stub(
        bin_dir,
        "npx",
        'echo "$*" >> %s\nif [ "$4 $5" = "bucket list" ]; then printf "%s"; fi\nexit 0\n'
        % (log, names),
    )
    cfg = tmp_path / "wrangler.test.toml"
    cfg.write_text(config or "", encoding="utf-8")
    env = dict(os.environ, PATH="%s:%s" % (bin_dir, os.environ["PATH"]), PYTHONPATH=CI_DIR)
    argv = [a.replace("CFG", str(cfg)) for a in call.split()]
    done = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.ops.bench_preflight", *argv],
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
    done, calls = _run(tmp_path, "buckets CFG", listed=("have-it",), config=TWO_BUCKETS)
    assert done.returncode == 0, done.stderr
    assert "--no-install wrangler r2 bucket create missing-one" in calls
    assert not any("create have-it" in c for c in calls)


def test_control_nothing_is_created_when_every_bucket_exists(tmp_path):
    done, calls = _run(
        tmp_path,
        "buckets CFG",
        listed=("have-it", "missing-one"),
        config=TWO_BUCKETS,
    )
    assert done.returncode == 0, done.stderr
    assert not any("create" in c for c in calls)


def test_a_jurisdictional_binding_is_refused_not_guessed(tmp_path):
    cfg = TWO_BUCKETS + 'jurisdiction = "eu"\n'
    done, calls = _run(tmp_path, "buckets CFG", config=cfg)
    assert done.returncode == 1
    assert "jurisdiction" in done.stderr
    assert not any("create" in c for c in calls)


def test_a_drifted_install_is_refused(tmp_path):
    done, _ = _run(tmp_path, "lockfile %s" % tmp_path, npm_ls_rc=1)
    assert done.returncode == 1
    assert "does not match its package-lock.json" in done.stderr


LINKED = {"resolved": "file:../../packages/shared", "dependencies": {"zod": {"missing": True}}}


def test_a_linked_package_missing_its_dependencies_is_not_this_install_drifting(tmp_path):
    tree = {"problems": ["missing: zod"], "dependencies": {"@rediacc/shared": LINKED}}
    done, _ = _run(tmp_path, "lockfile %s" % tmp_path, npm_ls_rc=1, npm_ls_out=json.dumps(tree))
    assert done.returncode == 0, done.stderr


def test_a_missing_dependency_beside_a_linked_package_is_still_refused(tmp_path):
    own = {"@rediacc/shared": LINKED, "hono": {"dependencies": {"left": {"invalid": True}}}}
    tree = {"problems": ["missing: zod", "invalid: left"], "dependencies": own}
    done, _ = _run(tmp_path, "lockfile %s" % tmp_path, npm_ls_rc=1, npm_ls_out=json.dumps(tree))
    assert done.returncode == 1
    assert "does not match its package-lock.json" in done.stderr


def test_a_mark_on_the_link_itself_is_refused(tmp_path):
    tree = {
        "problems": ["invalid: shared"],
        "dependencies": {"@rediacc/shared": dict(LINKED, invalid=True)},
    }
    done, _ = _run(tmp_path, "lockfile %s" % tmp_path, npm_ls_rc=1, npm_ls_out=json.dumps(tree))
    assert done.returncode == 1


def test_a_listed_problem_no_linked_mark_explains_is_refused(tmp_path):
    tree = {
        "problems": ["missing: zod", "something else"],
        "dependencies": {"@rediacc/shared": LINKED},
    }
    done, _ = _run(tmp_path, "lockfile %s" % tmp_path, npm_ls_rc=1, npm_ls_out=json.dumps(tree))
    assert done.returncode == 1


def test_a_problem_no_mark_names_is_refused_even_when_a_linked_mark_could_stand_for_it(tmp_path):
    """One problem, one mark inside a linked directory, so the two counts agree; but the problem names `left`, which is not the marked package."""
    tree = {"problems": ["missing: left"], "dependencies": {"@rediacc/shared": LINKED}}
    done, _ = _run(tmp_path, "lockfile %s" % tmp_path, npm_ls_rc=1, npm_ls_out=json.dumps(tree))
    assert done.returncode == 1
    assert "does not match its package-lock.json" in done.stderr


def test_a_scoped_package_problem_is_matched_to_its_mark(tmp_path):
    linked = {
        "resolved": "file:../../packages/shared",
        "dependencies": {"@rediacc/shared": {"missing": True}},
    }
    tree = {
        "problems": ["missing: @rediacc/shared@^1.0.0, required by x@1.0.0"],
        "dependencies": {"x": linked},
    }
    done, _ = _run(tmp_path, "lockfile %s" % tmp_path, npm_ls_rc=1, npm_ls_out=json.dumps(tree))
    assert done.returncode == 0, done.stderr


def test_a_file_tarball_is_not_a_link(tmp_path):
    packed = {"resolved": "file:vendor/x-1.0.0.tgz", "dependencies": {"zod": {"missing": True}}}
    tree = {"problems": ["missing: zod"], "dependencies": {"x": packed}}
    done, _ = _run(tmp_path, "lockfile %s" % tmp_path, npm_ls_rc=1, npm_ls_out=json.dumps(tree))
    assert done.returncode == 1


def test_control_a_clean_install_passes(tmp_path):
    done, _ = _run(tmp_path, "lockfile %s" % tmp_path, npm_ls_rc=0)
    assert done.returncode == 0, done.stderr


def test_deploy_bench_runs_both_preflights_before_the_first_migration():
    text = paths.from_root(".ci", "rediacc_ci", "ops", "deploy_bench.py").read_text(
        encoding="utf-8"
    )
    migrate = text.index('"migrations", "apply"')
    assert -1 < text.index("bench_preflight.lockfile(") < migrate
    assert -1 < text.index("bench_preflight.buckets(") < migrate
