"""Differential: `rediacc_ci.build.build_pages` against its twin `.ci/scripts/build/build-pages.sh`.

THE FIXTURE SHAPE follows `test_build_build_www.py` and `test_build_build_json.py`:
neither side takes a root override, so both are copied into a throwaway root;
PATH is REPLACED rather than prepended; `rediacc_ci` is vendored so no absolute path outside the fixture appears in any command; `$0` is masked to `<SELF>` and nothing else is.

WHAT THIS FILE ADDS is that the subject's whole output surface is FILESYSTEM, not text. `build-pages.sh` prints eleven chatter lines on a successful run and says nothing about what it copied, so a port that assembled a different package would agree on every byte of stderr. Every case therefore compares the RESULTING TREE as well: `_state` walks the fixture and hashes every file the
run produced, and `_agree` fails when the two trees differ even by one path.

THE THREE FILESYSTEM TOOLS ARE RECORDED, NOT REPLACED. `rm`, `mkdir` and `cp` are wrappers that append their own argv to a log and then `exec` the real binary, so the copies really happen AND the argv each side built is comparable. `dirname` and `uname` are plain symlinks and deliberately NOT recorded: the twin spawns them from `get_repo_root` and from sourcing `common.sh`, which
is shell plumbing rather than ported logic, and recording them would manufacture a divergence out of the fact that Python resolves its own path in-process.

K=5 LEDGER: `.ci/shadow/w7p6-build-pages.observations.jsonl`.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.build import build_pages as port

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/build-pages.sh"
PORT_REL = ".ci/rediacc_ci/build/build_pages.py"
COMMON_REL = ".ci/scripts/lib/common.sh"

# Everything the port imports, transitively.
VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/build/__init__.py",
)

BASH = shutil.which("bash") or "/bin/bash"

# Plain symlinks. `dirname` for `get_repo_root` (common.sh:207) and for the twin's own `SCRIPT_DIR` (:16); `uname` because sourcing common.sh runs `detect_os`/`detect_arch`; `tr` because `parse_args` folds each flag name through `to_upper` (common.sh:302). Anything not listed here or below is ABSENT.
PLAIN = ("dirname", "uname", "tr")

# Recorded wrappers around the real binaries. These three ARE the ported logic.
RECORDED = ("rm", "mkdir", "cp")

RECORDER = """#!/bin/bash
printf 'CALL {name}' >>"$FAKE_CALL_LOG"
for a in "$@"; do printf '\\t%s' "$a" >>"$FAKE_CALL_LOG"; done
printf '\\n' >>"$FAKE_CALL_LOG"
exec {real} "$@"
"""

# Directories either side may create or destroy, reset between the two runs.
MUTABLE = ("packages", "workers", "dist", "out", "true", "pages")

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))


# --------------------------------------------------------------------------- Fixture ---------------------------------------------------------------------------


def fixture(
    tmp_path: pathlib.Path,
    *,
    port_source: str | None = None,
    www: dict[str, str] | None = None,
    json_dist: dict[str, str] | None = None,
    manifest: str | None = None,
    worker_dir: bool = True,
) -> pathlib.Path:
    """A throwaway repo root holding both sides and a build to assemble.

    `www=None` / `json_dist=None` means the dist directory is not created at all;
    an empty dict means it is created and left EMPTY, which is a different case (defect 4) and the one the twin reports as `cp: cannot stat`.
    """
    root = tmp_path / "repo"
    for rel in (TWIN_REL, PORT_REL, COMMON_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in (TWIN_REL, COMMON_REL, *VENDORED):
        shutil.copy2(ROOT / rel, root / rel)
    if port_source is None:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")

    if www is not None:
        (root / port.WWW_DIST).mkdir(parents=True, exist_ok=True)
        for name, body in www.items():
            target = root / port.WWW_DIST / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
    if json_dist is not None:
        (root / port.JSON_DIST).mkdir(parents=True, exist_ok=True)
        for name, body in json_dist.items():
            target = root / port.JSON_DIST / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
    if manifest is not None:
        (root / port.CLI_MANIFEST).parent.mkdir(parents=True, exist_ok=True)
        (root / port.CLI_MANIFEST).write_text(manifest, encoding="utf-8")
    if worker_dir:
        root.joinpath(*port.WORKER_SUBDIR).mkdir(parents=True, exist_ok=True)

    _pristine(root)
    return root


def default_fixture(tmp_path: pathlib.Path, **kw) -> pathlib.Path:
    """The ordinary case: a two-file www build and a one-file json build."""
    kw.setdefault("www", {"index.html": "<html>www</html>", "assets/app.js": "//js"})
    kw.setdefault("json_dist", {"catalog.json": "{}"})
    return fixture(tmp_path, **kw)


def _pristine(root: pathlib.Path) -> None:
    """Save the mutable subtrees so the second side starts where the first did."""
    keep = root / ".pristine"
    if keep.exists():
        shutil.rmtree(keep)
    keep.mkdir()
    for name in MUTABLE:
        src = root / name
        if src.exists():
            shutil.copytree(src, keep / name, symlinks=True)


def _restore(root: pathlib.Path) -> None:
    keep = root / ".pristine"
    for name in MUTABLE:
        target = root / name
        if target.exists():
            shutil.rmtree(target)
        if (keep / name).exists():
            shutil.copytree(keep / name, target, symlinks=True)


def scratch_bin(root: pathlib.Path, *, drop: tuple[str, ...] = ()) -> str:
    """The ONLY directory on PATH for either side."""
    stub = root / "fixture-bin"
    if stub.exists():
        shutil.rmtree(stub)
    stub.mkdir(parents=True)
    for name in PLAIN:
        if name in drop:
            continue
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        (stub / name).symlink_to(real)
    for name in RECORDED:
        if name in drop:
            continue
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        wrapper = stub / name
        wrapper.write_text(RECORDER.format(name=name, real=real), encoding="utf-8")
        wrapper.chmod(0o755)
    return str(stub)


# --------------------------------------------------------------------------- Driving ---------------------------------------------------------------------------


def _state(root: pathlib.Path) -> dict[str, str]:
    """Every file the run produced, hashed. The subject's real output surface."""
    out: dict[str, str] = {}
    for name in MUTABLE:
        base = root / name
        if not base.exists():
            continue
        if base.is_file():
            out[name] = "file:" + hashlib.sha256(base.read_bytes()).hexdigest()[:16]
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            here = os.path.relpath(dirpath, root)
            for d in sorted(dirnames):
                out[os.path.join(here, d)] = "dir"
            for f in sorted(filenames):
                full = pathlib.Path(dirpath) / f
                digest = hashlib.sha256(full.read_bytes()).hexdigest()[:16]
                out[os.path.relpath(full, root)] = "file:" + digest
    return out


def _run(
    root: pathlib.Path,
    side: str,
    *,
    args: tuple[str, ...] = (),
    drop: tuple[str, ...] = (),
    cwd: str | None = None,
    **extra,
):
    call_log = root / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        # REPLACED, never prepended.
        "PATH": scratch_bin(root, drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(extra)
    if side == "old":
        argv = [BASH, str(root / TWIN_REL), *args]
    else:
        argv = [sys.executable, str(root / PORT_REL), *args]
    proc = subprocess.run(
        argv,
        cwd=cwd or str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8"), _state(root)


def run_both(root: pathlib.Path, **kw):
    old, old_calls, old_state = _run(root, "old", **kw)
    _restore(root)
    new, new_calls, new_state = _run(root, "new", **kw)
    return (old, old_calls, old_state), (new, new_calls, new_state)


def _mask(text: str) -> str:
    """`$0`, the one thing that cannot agree between the two sides."""
    return SELF_RE.sub("<SELF>", text)


def _agree(old_t, new_t, label: str) -> None:
    old, old_calls, old_state = old_t
    new, new_calls, new_state = new_t
    assert new.returncode == old.returncode, (
        "%s: exit diverged: %r vs %r\nold stderr: %r\nnew stderr: %r"
        % (label, old.returncode, new.returncode, old.stderr, new.stderr)
    )
    assert _mask(new.stdout) == _mask(old.stdout), "%s: stdout diverged:\n%r\n%r" % (
        label,
        old.stdout,
        new.stdout,
    )
    assert _mask(new.stderr) == _mask(old.stderr), "%s: stderr diverged:\n%r\n%r" % (
        label,
        old.stderr,
        new.stderr,
    )
    assert new_calls == old_calls, "%s: call log diverged:\n%s---\n%s" % (
        label,
        old_calls,
        new_calls,
    )
    assert new_state == old_state, "%s: the assembled tree diverged:\n%s" % (
        label,
        sorted(set(old_state.items()) ^ set(new_state.items())),
    )


# --------------------------------------------------------------------------- The control on the control ---------------------------------------------------------------------------


def test_the_scratch_path_holds_only_the_five_named_tools(tmp_path) -> None:
    """A PREPENDED PATH would let the real npm, git or node reach the checkout. This asserts the replacement holds in both directions."""
    root = default_fixture(tmp_path)
    sealed = scratch_bin(root)
    for name in (*PLAIN, *RECORDED):
        assert shutil.which(name, path=sealed) == str(root / "fixture-bin" / name)
    for absent in ("npm", "node", "git", "bash", "python3"):
        assert shutil.which(absent, path=sealed) is None, "%s is reachable" % absent
    dropped = scratch_bin(root, drop=("cp",))
    assert shutil.which("cp", path=dropped) is None


def test_the_recorder_really_runs_the_real_binary(tmp_path) -> None:
    """A wrapper that logged and did nothing would make every case pass while assembling nothing, so the wrapper itself is checked before it is trusted."""
    root = default_fixture(tmp_path)
    log = root / "probe.log"
    log.write_text("", encoding="utf-8")
    subprocess.run(
        ["mkdir", "-p", str(root / "probe-dir")],
        env={"PATH": scratch_bin(root), "FAKE_CALL_LOG": str(log)},
        check=True,
        timeout=60,
    )
    assert (root / "probe-dir").is_dir(), "the recorded mkdir did not create anything"
    assert log.read_text(encoding="utf-8").startswith("CALL mkdir\t-p\t")


# --------------------------------------------------------------------------- The success path ---------------------------------------------------------------------------


def test_a_complete_assembly_prints_eleven_lines_and_exits_zero(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--output", "out"))
    old, _old_calls, old_state = old_t
    assert old.returncode == 0, old.stderr
    assert old.stdout == ""
    worker = root.joinpath(*port.WORKER_SUBDIR)
    assert old.stderr == (
        "→ Assembling pages package...\n"
        "→ Copying www to root...\n"
        "✓ Copied www to out/\n"
        "→ Copying json to /json/...\n"
        "✓ Copied json to out/json/\n"
        "→ Copying pages to www worker static assets...\n"
        "✓ Copied pages to %s/dist/\n"
        "✓ Pages package ready at out/\n"
        "✓   - Root:     www.rediacc.com (marketing site)\n"
        "✓   - /json:    www.rediacc.com/json/ (template catalog)\n"
        "✓   - /cli:     www.rediacc.com/cli/ (CLI update manifest)\n" % worker
    ), old.stderr
    assert "out/index.html" in old_state
    assert "out/json/catalog.json" in old_state
    assert "workers/www/dist/index.html" in old_state
    _agree(old_t, new_t, "success")


def test_the_glob_is_bashs_and_the_argv_cp_receives_is_sorted(tmp_path) -> None:
    """`cp -r packages/www/dist/*` is expanded by the SHELL. The port has to build the same argv, in the same order, or `cp` sees a different command."""
    root = default_fixture(
        tmp_path,
        www={"z.html": "z", "a.html": "a", "m/inner.txt": "m"},
    )
    old_t, new_t = run_both(root, args=("--output", "out"))
    old_calls = old_t[1]
    assert (
        "CALL cp\t-r\tpackages/www/dist/a.html\tpackages/www/dist/m"
        "\tpackages/www/dist/z.html\tout/\n" in old_calls
    ), old_calls
    _agree(old_t, new_t, "glob-order")


def test_the_equals_form_of_the_flag_is_the_same_as_the_spaced_form(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--output=pages",))
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "✓ Pages package ready at pages/\n" in old_t[0].stderr
    _agree(old_t, new_t, "equals-form")


# --------------------------------------------------------------------------- The two refusals ---------------------------------------------------------------------------


def test_a_missing_www_build_refuses_with_two_lines(tmp_path) -> None:
    root = fixture(tmp_path, www=None, json_dist={"catalog.json": "{}"})
    old_t, new_t = run_both(root, args=("--output", "out"))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == (
        "→ Assembling pages package...\n"
        "✗ www build not found at packages/www/dist/\n"
        "✗ Run 'npm run build:www' first\n"
    ), old_t[0].stderr
    assert old_t[1] == "", "nothing should have been spawned"
    _agree(old_t, new_t, "no-www")


def test_a_missing_json_build_refuses_with_two_lines(tmp_path) -> None:
    root = fixture(tmp_path, www={"index.html": "x"}, json_dist=None)
    old_t, new_t = run_both(root, args=("--output", "out"))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith(
        "✗ json build not found at packages/json/dist/\n✗ Run 'npm run build:json' first\n"
    ), old_t[0].stderr
    _agree(old_t, new_t, "no-json")


# --------------------------------------------------------------------------- The defects ---------------------------------------------------------------------------


def test_defect_1_the_default_output_deletes_the_manifest_it_then_looks_for(
    tmp_path,
) -> None:
    """`rm -rf dist` at `:43` runs BEFORE the `-f dist/cli-manifest/manifest.json` test at `:58`, and the default output directory IS `dist`. So with no `--output` the CLI-manifest block can never fire, the run exits 0, and the summary still advertises `/cli`."""
    root = default_fixture(tmp_path, manifest='{"version":"1.2.3"}')
    old_t, new_t = run_both(root)
    old, _old_calls, old_state = old_t
    assert old.returncode == 0, old.stderr
    assert "Copying CLI manifest" not in old.stderr, "the block fired; defect 1 is gone"
    assert not [k for k in old_state if k.startswith("dist/cli")], sorted(old_state)
    assert "✓   - /cli:     www.rediacc.com/cli/ (CLI update manifest)\n" in old.stderr
    assert "dist/cli-manifest/manifest.json" not in old_state, "the manifest survived"
    _agree(old_t, new_t, "default-output-self-destruct")


def test_the_manifest_block_does_fire_when_the_output_is_elsewhere(tmp_path) -> None:
    """The other half of defect 1: the block is not dead code, it is code the DEFAULT can never reach. With `--output out` it runs and copies twice."""
    root = default_fixture(tmp_path, manifest='{"version":"1.2.3"}')
    old_t, new_t = run_both(root, args=("--output", "out"))
    old, old_calls, old_state = old_t
    assert old.returncode == 0, old.stderr
    assert "→ Copying CLI manifest to /cli/edge/ and /cli/stable/...\n" in old.stderr
    assert "out/cli/edge/manifest.json" in old_state
    assert "out/cli/stable/manifest.json" in old_state
    assert old_calls.count("CALL cp\tdist/cli-manifest/manifest.json\t") == 2
    _agree(old_t, new_t, "manifest-copied")


def test_defect_4_an_empty_build_is_a_raw_cp_error_not_a_named_refusal(tmp_path) -> None:
    root = default_fixture(tmp_path, www={})
    old_t, new_t = run_both(root, args=("--output", "out"))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith(
        "cp: cannot stat 'packages/www/dist/*': No such file or directory\n"
    ), old_t[0].stderr
    _agree(old_t, new_t, "empty-www")


def test_defect_4_a_dotfile_only_build_is_indistinguishable_from_an_empty_one(
    tmp_path,
) -> None:
    """`*` does not match a leading dot, and `nullglob` is not set, so a `dist/` holding only `.nojekyll` produces the SAME `cannot stat` as an empty one and the dotfile is never copied."""
    root = default_fixture(tmp_path, www={".nojekyll": ""})
    old_t, new_t = run_both(root, args=("--output", "out"))
    assert old_t[0].returncode == 1
    assert "cp: cannot stat 'packages/www/dist/*'" in old_t[0].stderr
    _agree(old_t, new_t, "dotfile-only")


def test_defect_4_a_dotfile_beside_a_real_file_is_silently_left_behind(tmp_path) -> None:
    root = default_fixture(tmp_path, www={"index.html": "x", ".nojekyll": ""})
    old_t, new_t = run_both(root, args=("--output", "out"))
    old, _calls, old_state = old_t
    assert old.returncode == 0, old.stderr
    assert "out/index.html" in old_state
    assert "out/.nojekyll" not in old_state, "the dotfile was copied; defect 4 is gone"
    _agree(old_t, new_t, "dotfile-dropped")


def test_defect_5_a_mistyped_flag_is_ignored_and_the_default_dist_is_deleted(
    tmp_path,
) -> None:
    """`parse_args` has no `*)` arm. `--outupt out` sets `ARG_OUTUPT`, nobody reads it, and `rm -rf dist` then destroys a `dist/` the caller meant to keep."""
    root = default_fixture(tmp_path, manifest='{"keep":"me"}')
    old_t, new_t = run_both(root, args=("--outupt", "out"))
    old, _calls, old_state = old_t
    assert old.returncode == 0, "a mistyped flag was accepted silently"
    assert "out" not in old_state, "the mistyped flag was honoured after all"
    assert "dist/cli-manifest/manifest.json" not in old_state, "the pre-existing dist survived"
    assert "✓ Pages package ready at dist/\n" in old.stderr
    _agree(old_t, new_t, "typo-flag")


def test_defect_5_a_dangling_output_flag_becomes_the_literal_directory_true(
    tmp_path,
) -> None:
    """`parse_args` stores the string `true` for a flag with no value, so `build-pages.sh --output` assembles the package into `./true/`."""
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--output",))
    old, _calls, old_state = old_t
    assert old.returncode == 0, old.stderr
    assert "✓ Pages package ready at true/\n" in old.stderr
    assert "true/index.html" in old_state
    _agree(old_t, new_t, "dangling-output")


def test_defect_6_a_missing_worker_directory_fails_after_the_package_is_built(
    tmp_path,
) -> None:
    root = default_fixture(tmp_path, worker_dir=False)
    old_t, new_t = run_both(root, args=("--output", "out"))
    old, _calls, old_state = old_t
    assert old.returncode == 1
    worker = root.joinpath(*port.WORKER_SUBDIR)
    assert old.stderr.endswith(
        "cp: cannot create directory '%s/dist': No such file or directory\n" % worker
    ), old.stderr
    assert "out/index.html" in old_state, "the failure arrived after the package was assembled"
    _agree(old_t, new_t, "no-worker-dir")


# --------------------------------------------------------------------------- The `cd`, and a missing tool ---------------------------------------------------------------------------


def test_both_sides_cd_to_the_repo_root_whatever_the_caller_did(tmp_path) -> None:
    """Driven from a directory holding a DECOY `packages/www/dist/index.html` and no json build: a side reading paths relative to the caller would refuse on json rather than assembling the fixture's real build."""
    root = default_fixture(tmp_path)
    decoy = tmp_path / "elsewhere"
    (decoy / "packages" / "www" / "dist").mkdir(parents=True)
    (decoy / "packages" / "www" / "dist" / "index.html").write_text("decoy", encoding="utf-8")
    old_t, new_t = run_both(root, args=("--output", "out"), cwd=str(decoy))
    old, _calls, old_state = old_t
    assert old.returncode == 0, old.stderr
    assert old_state["out/index.html"] == old_state["packages/www/dist/index.html"]
    assert (decoy / "out").exists() is False, "the package landed in the caller's cwd"
    _agree(old_t, new_t, "cd")


def test_a_missing_cp_is_bashs_own_command_not_found_at_line_48(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--output", "out"), drop=("cp",))
    old = old_t[0]
    assert old.returncode == 127, old.stderr
    assert _mask(old.stderr).endswith(
        "<SELF>: line %d: cp: command not found\n" % port.CP_WWW_LINE
    ), old.stderr
    _agree(old_t, new_t, "cp-absent")


def test_a_missing_rm_stops_before_anything_is_copied(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--output", "out"), drop=("rm",))
    old, old_calls, _state = old_t
    assert old.returncode == 127, old.stderr
    assert _mask(old.stderr).endswith(
        "<SELF>: line %d: rm: command not found\n" % port.RM_OUTPUT_LINE
    ), old.stderr
    assert old_calls == "", "something ran after the first failure"
    _agree(old_t, new_t, "rm-absent")


def test_the_port_and_the_twin_agree_about_the_repo_root_in_this_checkout() -> None:
    proc = subprocess.run(
        [BASH, "-c", 'source "$1" && get_repo_root', "bash", str(ROOT / COMMON_REL)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert proc.stdout.strip() == str(port.repo_root())
    assert proc.stdout.strip() == str(ROOT)


def test_defect_2_nothing_in_the_tree_writes_the_manifest_path_this_reads() -> None:
    """Every mention of `dist/cli-manifest/` in the repository is a CONSUMER. The producer (`generate-cli-manifest.sh`) writes `dist/cli/manifest.json`, so the block is dead under every `--output`.

    Asserted against the real tree rather than a fixture, because the claim is about the tree. If a producer is ever added this test goes red and the docstring's defect 2 has to be rewritten, which is the intent.

    The expected set is THREE files, not one. It was written as `[TWIN_REL]` and was therefore red from the commit that introduced it (`7c926bd63`): the port reproduces the twin's dead read, as the campaign requires, and this file names the path in its own `git grep` argument, so it matches itself. Counting mentions is a PROXY for "nothing writes this path"; the proxy has to know
    about the non-producers that the proxy itself created, or it only ever reports its own existence.
    """
    self_rel = str(pathlib.Path(__file__).resolve().relative_to(ROOT))
    found = subprocess.run(
        ["git", "-C", str(ROOT), "grep", "-l", "dist/cli-manifest"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert sorted(found.stdout.split()) == sorted([TWIN_REL, PORT_REL, self_rel]), found.stdout


# --------------------------------------------------------------------------- The control: this differential can actually fail ---------------------------------------------------------------------------


def test_a_planted_defect_is_caught(tmp_path) -> None:
    """A gate that has never been seen to fail is not a gate.

    The plant makes `bash_glob` fall back to `[]` instead of the literal pattern on no match, which is what `nullglob` would do and what a reader "cleaning up" the port would reach for. It is invisible on every case with a non-empty build and visible on exactly one: the empty `dist/`, where the twin hands `cp` the unexpanded pattern and fails, and the plant hands `cp` only the
    destination and fails DIFFERENTLY.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace("return matches or [pattern]", "return matches")
    assert planted != source, "the plant site moved; this control is not planting anything"
    root = default_fixture(tmp_path, port_source=planted, www={})
    old_t, new_t = run_both(root, args=("--output", "out"))
    assert old_t[0].returncode == 1
    assert "cp: cannot stat 'packages/www/dist/*'" in old_t[0].stderr
    assert "cp: cannot stat" not in new_t[0].stderr, "the plant did not diverge"
    assert _mask(new_t[0].stderr) != _mask(old_t[0].stderr)
