"""`private/renet/build.sh` stamps a renet binary with RENET's commit when renet is a console submodule.

THE DEFECT. Go records `vcs.revision`/`vcs.modified` from the repository it finds by walking up from the module for a `.git` DIRECTORY (cmd/go/internal/vcs, vcsGit RootNames `{".git", isDir: true}`). A submodule's `.git` is a gitlink FILE, so a plain `go build` in `private/renet` stamped the CONSOLE's HEAD and dirt: on 2026-10-14 bin/renet read `vcs.revision=2ea3c2780` (a console commit) and `vcs.modified=true` over a clean renet tree at e27b334, and `npm run vm:check`'s P1 refused it as `renet-build-mismatch` on every run, its one rebuild included.

THE FIX UNDER TEST. Every `go build` in build.sh goes through `_go_build`, which points `GIT_DIR`/`GIT_WORK_TREE` at renet's own repository when `.git` is a file.

REAL GIT, REAL GO. The fixture is an outer repository holding an inner one as a real submodule, the inner carrying a copy of the real build.sh and a one-file `./cmd/renet`. A fake `go` would prove only that the env vars are set, not that Go then stamps the right commit, so the module skips where `go` is absent, as `test_proxies_go_unit.py` does. `test_the_fixture_reproduces_the_defect` is the control: a plain `go build` in the same submodule must stamp the OUTER commit, or the fixture cannot tell the fix from its absence.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

BUILD_SH = paths.repo_root() / "private" / "renet" / "build.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("go") is None, reason="go absent; no binary to read a VCS stamp from"
)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _env(tmp_path: pathlib.Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_ENV)
    # A caller's GOFLAGS=-buildvcs=false or a go.work would hide the stamp under test.
    env["GOFLAGS"] = ""
    env["GOWORK"] = "off"
    env["GOCACHE"] = os.environ.get("GOCACHE") or str(tmp_path / "gocache")
    return env


def _run(argv: list[str], cwd: pathlib.Path, env: dict[str, str]) -> str:
    res = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    assert res.returncode == 0, "%s rc=%d\nstdout:%s\nstderr:%s" % (
        argv,
        res.returncode,
        res.stdout,
        res.stderr,
    )
    return res.stdout


def _commit(repo: pathlib.Path, env: dict[str, str], *names: str) -> str:
    _run(["git", "add", "--", *names], repo, env)
    _run(["git", "commit", "-q", "-m", "c"], repo, env)
    return _run(["git", "rev-parse", "HEAD"], repo, env).strip()


def _fixture(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str, str, dict[str, str]]:
    """(submodule dir, submodule HEAD, outer HEAD, env)."""
    env = _env(tmp_path)
    inner = tmp_path / "inner"
    (inner / "cmd" / "renet").mkdir(parents=True)
    _run(["git", "init", "-q", str(inner)], tmp_path, env)
    (inner / "go.mod").write_text("module example.com/renet\n\ngo 1.22\n", encoding="utf-8")
    (inner / "cmd" / "renet" / "main.go").write_text(
        "package main\n\nfunc main() {}\n", encoding="utf-8"
    )
    shutil.copy2(BUILD_SH, inner / "build.sh")
    _commit(inner, env, "go.mod", "cmd/renet/main.go", "build.sh")

    outer = tmp_path / "outer"
    outer.mkdir()
    _run(["git", "init", "-q", str(outer)], tmp_path, env)
    (outer / "README").write_text("outer\n", encoding="utf-8")
    _commit(outer, env, "README")
    _run(
        ["git", "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "renet"],
        outer,
        env,
    )
    outer_head = _commit(outer, env, ".gitmodules", "renet")
    sub = outer / "renet"
    assert (sub / ".git").is_file(), "the fixture must check renet out as a gitlink FILE"
    # Dirty the OUTER tree, as untracked agent/ files dirty the console: a stamp
    # read from the outer repository would then say modified=true.
    (outer / "untracked.txt").write_text("x\n", encoding="utf-8")
    sub_head = _run(["git", "rev-parse", "HEAD"], sub, env).strip()
    return sub, sub_head, outer_head, env


def _stamp(binary: pathlib.Path, env: dict[str, str]) -> tuple[str, str]:
    out = _run(["go", "version", "-m", str(binary)], binary.parent, env)
    rev = re.search(r"\bvcs\.revision=(\S+)", out)
    mod = re.search(r"\bvcs\.modified=(\S+)", out)
    return (rev.group(1) if rev else "", mod.group(1) if mod else "")


def _build_sh_run(
    sub: pathlib.Path,
    out: pathlib.Path,
    env: dict[str, str],
    cwd: pathlib.Path | None = None,
    args: tuple[str, ...] = ("./cmd/renet",),
    dash_c: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    # build.sh's last line, `[[ BASH_SOURCE == $0 ]] && "$@"`, is false when sourced and
    # so is the `source` itself; `declare -F` prints the name once the helper really loaded.
    # Every path is a positional argument, never interpolated into the script text.
    script = (
        'source "$2" || true; declare -F _go_build >/dev/null && declare -F _go_build && '
        'CGO_ENABLED=0 _go_build "${@:3}"'
    )
    return subprocess.run(
        [
            "bash",
            "-c",
            script,
            "build-vcs",
            str(out),
            str(sub / "build.sh"),
            *dash_c,  # go requires -C to be the first flag
            "-o",
            str(out),
            *args,
        ],
        cwd=cwd or sub,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _build_sh_go_build(
    sub: pathlib.Path,
    out: pathlib.Path,
    env: dict[str, str],
    cwd: pathlib.Path | None = None,
    args: tuple[str, ...] = ("./cmd/renet",),
    dash_c: tuple[str, ...] = (),
) -> None:
    res = _build_sh_run(sub, out, env, cwd, args, dash_c)
    assert res.returncode == 0, "rc=%d\nstdout:%s\nstderr:%s" % (
        res.returncode,
        res.stdout,
        res.stderr,
    )


def test_the_fixture_reproduces_the_defect(tmp_path: pathlib.Path) -> None:
    sub, sub_head, outer_head, env = _fixture(tmp_path)
    out = tmp_path / "plain.bin"
    _run(["go", "build", "-o", str(out), "./cmd/renet"], sub, {**env, "CGO_ENABLED": "0"})
    assert _stamp(out, env) == (outer_head, "true"), (
        "CONTROL: a plain go build stamps the outer repo"
    )
    assert sub_head != outer_head


def test_build_sh_stamps_the_submodule_commit_clean(tmp_path: pathlib.Path) -> None:
    sub, sub_head, _outer, env = _fixture(tmp_path)
    out = tmp_path / "renet.bin"
    _build_sh_go_build(sub, out, env)
    assert _stamp(out, env) == (sub_head, "false")


def test_build_sh_stamps_a_dirty_submodule_as_modified(tmp_path: pathlib.Path) -> None:
    sub, sub_head, _outer, env = _fixture(tmp_path)
    (sub / "cmd" / "renet" / "main.go").write_text(
        "package main\n\nfunc main() { println() }\n", encoding="utf-8"
    )
    out = tmp_path / "dirty.bin"
    _build_sh_go_build(sub, out, env)
    assert _stamp(out, env) == (sub_head, "true")


def test_a_broken_gitlink_fails_with_or_without_the_helper(tmp_path: pathlib.Path) -> None:
    """Failing on an unreadable gitlink is not a regression: a plain go build fails the same way."""
    sub, _sub_head, _outer, env = _fixture(tmp_path)
    (sub / ".git").write_text("gitdir: /nonexistent/gitdir\n", encoding="utf-8")
    plain = subprocess.run(
        ["go", "build", "-o", str(tmp_path / "p.bin"), "./cmd/renet"],
        cwd=sub,
        env={**env, "CGO_ENABLED": "0"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert plain.returncode != 0, "CONTROL: Go itself refuses a broken gitlink"
    res = _build_sh_run(sub, tmp_path / "h.bin", env)
    assert "_go_build" in res.stdout, "the helper must have loaded and been called"
    assert res.returncode != 0
    assert "nonexistent" in res.stderr or "not a git repository" in res.stderr, res.stderr


def test_cwd_outside_renet_is_not_stamped_with_renets_commit(tmp_path: pathlib.Path) -> None:
    """build.sh does not cd, so a build of another tree must not carry renet's stamp."""
    sub, sub_head, _outer, env = _fixture(tmp_path)
    other = tmp_path / "other"
    (other / "cmd" / "renet").mkdir(parents=True)
    (other / "go.mod").write_text("module example.com/other\n\ngo 1.22\n", encoding="utf-8")
    (other / "cmd" / "renet" / "main.go").write_text(
        "package main\n\nfunc main() {}\n", encoding="utf-8"
    )
    _run(["git", "init", "-q", str(other)], tmp_path, env)
    other_head = _commit(other, env, "go.mod", "cmd/renet/main.go")
    # Run build.sh's helper from renet's path while the cwd is the other tree.
    out = tmp_path / "other.bin"
    _build_sh_go_build(sub, out, env, cwd=other)
    assert _stamp(out, env) == (other_head, "false")
    assert other_head != sub_head


@pytest.mark.parametrize("flag", ["split", "equals"])
def test_dash_c_into_renet_from_a_foreign_cwd_is_stamped_with_renets_commit(
    tmp_path: pathlib.Path, flag: str
) -> None:
    """Go picks the module from `-C`, not the cwd: a build of renet from elsewhere is renet's."""
    sub, sub_head, _outer, env = _fixture(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    dash_c = ("-C", str(sub)) if flag == "split" else (f"-C={sub}",)
    out = tmp_path / "c.bin"
    _build_sh_go_build(sub, out, env, cwd=other, dash_c=dash_c)
    assert _stamp(out, env) == (sub_head, "false")


def test_dash_c_away_from_renet_with_renet_cwd_is_not_stamped_with_renets_commit(
    tmp_path: pathlib.Path,
) -> None:
    sub, sub_head, _outer, env = _fixture(tmp_path)
    other = tmp_path / "other"
    (other / "cmd" / "renet").mkdir(parents=True)
    (other / "go.mod").write_text("module example.com/other\n\ngo 1.22\n", encoding="utf-8")
    (other / "cmd" / "renet" / "main.go").write_text(
        "package main\n\nfunc main() {}\n", encoding="utf-8"
    )
    _run(["git", "init", "-q", str(other)], tmp_path, env)
    other_head = _commit(other, env, "go.mod", "cmd/renet/main.go")
    out = tmp_path / "away.bin"
    _build_sh_go_build(sub, out, env, cwd=sub, dash_c=("-C", str(other)))
    assert _stamp(out, env) == (other_head, "false")
    assert other_head != sub_head


def test_every_go_build_in_build_sh_goes_through_the_helper() -> None:
    """A new `go build` site that bypasses `_go_build` brings the console stamp back."""
    text = BUILD_SH.read_text(encoding="utf-8")
    body = re.search(r"^_go_build\(\) \{\n(.*?)^\}", text, re.MULTILINE | re.DOTALL)
    assert body, "build.sh defines _go_build"
    outside = text[: body.start()] + text[body.end() :]
    # Join backslash continuations first, so `go \` + newline + `build` is one line.
    joined = re.sub(r"\\\n\s*", " ", outside)
    code = [ln for ln in joined.splitlines() if not ln.lstrip().startswith("#")]
    raw = [ln for ln in code if re.search(r"(^|[\s;&|(])go\s+build\b", ln)]
    assert raw == [], "go build outside _go_build: %s" % raw
    assert any(re.search(r"\b_go_build\s", ln) for ln in code), "build.sh calls _go_build"
