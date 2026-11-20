"""PLAN-two-track-merge-dev RB5: a commit pointer written from a lease must be reachable from the live branch or origin/main, never only from the lease's own detached HEAD."""

import subprocess

import wl_planrec


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(cwd, name):
    (cwd / name).write_text(name + "\n")
    _git(cwd, "add", name)
    _git(cwd, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", name)
    return _git(cwd, "rev-parse", "HEAD")


def _repo_with_lease(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "1120-1")
    on_branch = _commit(main, "a.txt")
    lease = tmp_path / "lease"
    _git(main, "worktree", "add", "-q", "--detach", str(lease), "HEAD")
    in_lease = _commit(lease, "b.txt")
    return main, lease, on_branch, in_lease


def test_a_lease_commit_is_refused_from_inside_the_lease(tmp_path):
    _main, lease, on_branch, in_lease = _repo_with_lease(tmp_path)
    assert wl_planrec._live_ref(lease) == "refs/heads/1120-1"
    ok, why = wl_planrec.resolve(lease, "commit", in_lease)
    assert not ok, why
    assert "refs/heads/1120-1" in why
    ok, why = wl_planrec.resolve(lease, "commit", on_branch)
    assert ok, "CONTROL: a commit on the live branch resolves from the lease too: %s" % why


def test_the_main_checkout_keeps_head(tmp_path):
    main, _lease, on_branch, in_lease = _repo_with_lease(tmp_path)
    assert wl_planrec._live_ref(main) == "HEAD"
    assert wl_planrec.resolve(main, "commit", on_branch)[0]
    assert not wl_planrec.resolve(main, "commit", in_lease)[0]
