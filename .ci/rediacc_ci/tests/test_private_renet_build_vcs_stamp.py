"""`private/renet/build.sh` stamps a renet binary with RENET's commit when renet is a console submodule.

THE DEFECT. Go records `vcs.revision`/`vcs.modified` from the repository it finds by walking up from the module for a `.git` DIRECTORY (cmd/go/internal/vcs, vcsGit RootNames `{".git", isDir: true}`). A submodule's `.git` is a gitlink FILE, so a plain `go build` in `private/renet` stamped the CONSOLE's HEAD and dirt: on 2026-10-14 bin/renet read `vcs.revision=2ea3c2780` (a console commit) and `vcs.modified=true` over a clean renet tree at e27b334, and `npm run vm:check`'s P1 refused it as `renet-build-mismatch` on every run, its one rebuild included.

THE FIX UNDER TEST. Every `go build` in build.sh goes through `_go_build`, which cds to renet's root in a subshell and, when `.git` is a gitlink file, points `GIT_DIR` at the gitdir it names and `GIT_WORK_TREE` at renet's root.

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
) -> subprocess.CompletedProcess[str]:
    # build.sh's last line, `[[ BASH_SOURCE == $0 ]] && "$@"`, is false when sourced and
    # so is the `source` itself; `declare -F` prints the name once the helper really loaded.
    # Every path is a positional argument, never interpolated into the script text.
    script = (
        'source "$1" || true; declare -F _go_build >/dev/null && declare -F _go_build && '
        'CGO_ENABLED=0 _go_build -o "$2" ./cmd/renet'
    )
    return subprocess.run(
        ["bash", "-c", script, "build-vcs", str(sub / "build.sh"), str(out)],
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
) -> None:
    res = _build_sh_run(sub, out, env, cwd)
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


def test_a_broken_gitlink_fails_naming_the_missing_gitdir(tmp_path: pathlib.Path) -> None:
    """Failing on an unreadable gitlink is not a regression: a plain go build fails the same way."""
    sub, _sub_head, _outer, env = _fixture(tmp_path)
    (sub / ".git").write_text("gitdir: ../missing-gitdir\n", encoding="utf-8")
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
    missing = f"{sub}/../missing-gitdir"
    assert f"build.sh: {sub}/.git names gitdir {missing}, which is not a directory" in (
        res.stderr
    ), res.stderr


def test_a_foreign_cwd_still_builds_renet_with_renets_stamp(tmp_path: pathlib.Path) -> None:
    """The helper cds to renet's root, so the caller's cwd neither breaks the build nor its stamp."""
    sub, sub_head, _outer, env = _fixture(tmp_path)
    other = tmp_path / "other"
    (other / "cmd" / "renet").mkdir(parents=True)
    (other / "go.mod").write_text("module example.com/other\n\ngo 1.22\n", encoding="utf-8")
    (other / "cmd" / "renet" / "main.go").write_text(
        "package main\n\nfunc main() {}\n", encoding="utf-8"
    )
    _run(["git", "init", "-q", str(other)], tmp_path, env)
    other_head = _commit(other, env, "go.mod", "cmd/renet/main.go")
    out = tmp_path / "foreign.bin"
    _build_sh_go_build(sub, out, env, cwd=other)
    assert _stamp(out, env) == (sub_head, "false")
    assert other_head != sub_head


def _bypassing_go_builds(text: str) -> list[str]:
    """Shell lines of `text` outside `_go_build` that run `go build` (any spelling of `go`)."""
    body = re.search(r"^_go_build\(\) [{(]\n.*?^[})]$", text, re.MULTILINE | re.DOTALL)
    outside = text[: body.start()] + text[body.end() :] if body else text
    # Bash does not continue a comment line, so comments go before continuations are joined.
    code = "\n".join(ln for ln in outside.splitlines() if not ln.lstrip().startswith("#"))
    joined = re.sub(r"\\\n\s*", " ", code)
    # `go`, `/usr/local/go/bin/go`, `"go"`, `'go'`, `$(go ...)`, `` `go ...` ``, then `build`.
    go_build = re.compile(r"""(?:^|[\s;&|(`])["']?(?:[^\s;&|()`"']*/)?go["']?\s+["']?build\b""")
    return [ln for ln in joined.splitlines() if go_build.search(ln)]


@pytest.mark.parametrize(
    "line",
    [
        "go build ./cmd/renet",
        "CGO_ENABLED=0 go build -o x ./cmd/renet",
        "/usr/local/go/bin/go build ./cmd/renet",
        '"go" build ./cmd/renet',
        "'go' build ./cmd/renet",
        '"$(go build ./cmd/renet)"',
        "x=`go build ./cmd/renet`",
        "go \\\n    build ./cmd/renet",
        "# a comment ending in a backslash \\\ngo build ./cmd/renet",
        "true && go\tbuild ./cmd/renet",
    ],
)
def test_the_bypass_scan_catches_every_spelling(line: str) -> None:
    assert _bypassing_go_builds(line + "\n"), line


@pytest.mark.parametrize(
    "line",
    [
        "_go_build -o x ./cmd/renet",
        "# go build ./cmd/renet",
        "go generate ./pkg/ebpf/...",
        "go version -m bin/renet",
        '_go_build() (\n    go build "$@"\n)',
    ],
)
def test_the_bypass_scan_passes_the_helper_and_other_go_verbs(line: str) -> None:
    assert _bypassing_go_builds(line + "\n") == [], line


def test_every_go_build_in_build_sh_goes_through_the_helper() -> None:
    """A new `go build` site that bypasses `_go_build` brings the console stamp back."""
    text = BUILD_SH.read_text(encoding="utf-8")
    assert re.search(r"^_go_build\(\) [{(]$", text, re.MULTILINE), "build.sh defines _go_build"
    assert _bypassing_go_builds(text) == []
    assert re.search(r"^\s+(?:\S+=\S+ )*_go_build\s", text, re.MULTILINE), (
        "build.sh calls _go_build"
    )
