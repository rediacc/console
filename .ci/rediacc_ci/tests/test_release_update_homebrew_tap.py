"""Differential: `rediacc_ci.release.update_homebrew_tap` against its twin `.ci/scripts/release/update-homebrew-tap.sh`.

NEITHER SIDE EVER SEES THE REAL TREE, and that is not a convenience here. The twin resolves its root through `get_repo_root` (common.sh:205-210), which takes no override, so run from this checkout it would `sed` the live `private/homebrew-tap/Formula/rediacc-cli.rb`, `git commit` inside that submodule and `git push origin HEAD:main`. Every case therefore copies BOTH subjects into a
throwaway fixture tree at their real relative depths, one tree per side, and puts recording fakes for `git`, `curl` and `gh` on a PATH that contains no real copy of any of the three. `_assert_no_real_tool` proves the shadowing rather than assuming it.

`gh` IS STUBBED EVEN THOUGH THIS SCRIPT NEVER CALLS IT, deliberately. The fake exits 91 and records, and `test_gh_is_never_invoked` asserts the call log holds no `gh` line. A future edit that reaches for `gh pr create` instead of `git push` would otherwise reach the real, authenticated `gh` on this machine on its first run.

THE CALL LOG IS COMPARED, NOT JUST THE STREAMS, for the reason the sibling port records: the observable effect is a set of mutations, and two implementations can print identical text while committing to different repositories. THE FORMULA FILE IS COMPARED TOO, byte for byte, because the whole point of the awk state machine is putting the right checksum in the right platform block
and nothing on stdout would show it going wrong.

FOUR DISTINCT FAKE CHECKSUMS, one per platform, so a slot mix-up is visible at a glance instead of needing a diff. `test_planted_slot_swap_is_caught` plants exactly that mix-up and drives it red.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.release import update_homebrew_tap as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "release" / "update-homebrew-tap.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "release" / "update_homebrew_tap.py"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
TOOLCHAIN_ENV = ROOT / ".devcontainer" / "toolchain.env"
BASH = shutil.which("bash") or "/bin/bash"

# The four fake checksums, one per platform, chosen so a slot mix-up is readable without a diff.
SHA_MAC_ARM = "1" * 64
SHA_MAC_X64 = "2" * 64
SHA_LINUX_ARM = "3" * 64
SHA_LINUX_X64 = "4" * 64
DOWNLOAD_SHAS = {
    "rdc-mac-arm64.sha256": SHA_MAC_ARM,
    "rdc-mac-x64.sha256": SHA_MAC_X64,
    "rdc-linux-arm64.sha256": SHA_LINUX_ARM,
    "rdc-linux-x64.sha256": SHA_LINUX_X64,
}

ORIGIN_SHA = "c" * 40

# The formula fixture, carrying the real file's shape: two `on_*` blocks, two `if Hardware::CPU.arm?` / `else` pairs, four `sha256` lines and a `version` line. `test_the_fixture_matches_the_real_formulas_shape` keeps it honest.
FORMULA = """class RediaccCli < Formula
  desc "Rediacc CLI - automation and scripting tool"
  homepage "https://www.rediacc.com"
  version "1.0.0"
  license "MIT"

  on_macos do
    if Hardware::CPU.arm?
      url "https://releases.rediacc.com/cli/v#{version}/rdc-mac-arm64"
      sha256 "aaaaaaaa"

      def install
        bin.install "rdc-mac-arm64" => "rdc"
      end
    else
      url "https://releases.rediacc.com/cli/v#{version}/rdc-mac-x64"
      sha256 "bbbbbbbb"

      def install
        bin.install "rdc-mac-x64" => "rdc"
      end
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://releases.rediacc.com/cli/v#{version}/rdc-linux-arm64"
      sha256 "cccccccc"

      def install
        bin.install "rdc-linux-arm64" => "rdc"
      end
    else
      url "https://releases.rediacc.com/cli/v#{version}/rdc-linux-x64"
      sha256 "dddddddd"

      def install
        bin.install "rdc-linux-x64" => "rdc"
      end
    end
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/rdc --version")
  end
end
"""

FAKE_GIT = (
    """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("git\\t" + "\\t".join(argv) + "\\n")

rest = list(argv)
if rest[:1] == ["-C"]:
    rest = rest[2:]
while rest[:1] == ["-c"]:
    rest = rest[2:]
verb = rest[0] if rest else ""


def rc(name, default="0"):
    return int(os.environ.get(name, default))


if verb == "config":
    sys.exit(0)
if verb == "status":
    sys.stdout.write(os.environ.get("FAKE_GIT_STATUS_OUT", ""))
    sys.exit(rc("FAKE_GIT_STATUS_RC"))
if verb == "fetch":
    sys.exit(rc("FAKE_GIT_FETCH_RC"))
if verb == "rev-parse":
    if rc("FAKE_GIT_REVPARSE_RC"):
        sys.stderr.write("fatal: ambiguous argument 'origin/main': unknown revision\\n")
        sys.exit(rc("FAKE_GIT_REVPARSE_RC"))
    sys.stdout.write(os.environ.get("FAKE_GIT_ORIGIN_SHA", "%s") + "\\n")
    sys.exit(0)
if verb == "checkout":
    sys.exit(rc("FAKE_GIT_CHECKOUT_RC"))
if verb == "diff":
    if "--cached" in rest:
        sys.exit(rc("FAKE_GIT_DIFF_CACHED_RC", "1"))
    sys.exit(rc("FAKE_GIT_DIFF_RC", "1"))
if verb == "add":
    sys.exit(rc("FAKE_GIT_ADD_RC"))
if verb == "commit":
    sys.stdout.write("[main 0000000] fake commit\\n")
    sys.exit(rc("FAKE_GIT_COMMIT_RC"))
if verb == "push":
    sys.stdout.write("fake push stdout\\n")
    sys.stderr.write("fake push stderr\\n")
    sys.exit(rc("FAKE_GIT_PUSH_RC"))

sys.stderr.write("fake git: unrouted call: %%s\\n" %% " ".join(argv))
sys.exit(90)
"""
    % ORIGIN_SHA
)

FAKE_CURL = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("curl\\t" + "\\t".join(argv) + "\\n")

SHAS = %r

url = argv[1]
out = argv[3]
if int(os.environ.get("FAKE_CURL_RC", "0")):
    sys.stderr.write("curl: (22) The requested URL returned error: 404\\n")
    sys.exit(int(os.environ["FAKE_CURL_RC"]))
name = url.rsplit("/", 1)[-1]
with open(out, "w") as fh:
    fh.write("%%s  %%s\\n" %% (SHAS[name], name[: -len(".sha256")]))
sys.exit(0)
""" % (DOWNLOAD_SHAS,)

FAKE_GH = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("gh\\t" + "\\t".join(sys.argv[1:]) + "\\n")
sys.stderr.write("fake gh: this script must never call gh\\n")
sys.exit(91)
"""

# Everything either subject needs on PATH, and nothing else. `git`, `curl` and `gh` are deliberately absent from this list: they arrive as fakes.
PATH_MINIMUM = (
    "dirname",
    "uname",
    "tr",
    "mktemp",
    "rm",
    "mv",
    "cat",
    "sed",
    "awk",
    "find",
    "head",
    "sha256sum",
)
FAKES = {"git": FAKE_GIT, "curl": FAKE_CURL, "gh": FAKE_GH}


def _stub_path(tmp_path: pathlib.Path, side: str) -> str:
    stub = tmp_path / ("%s-bin" % side)
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    for name, body in FAKES.items():
        fake = stub / name
        fake.write_text(body, encoding="utf-8")
        fake.chmod(0o755)
    return str(stub)


def _assert_no_real_tool(path: str) -> None:
    """The control on the control: prove the fakes SHADOW, never merely exist."""
    for name in FAKES:
        found = shutil.which(name, path=path)
        assert found is not None, "%s vanished from the stub PATH" % name
        assert found.startswith(path.split(":", 1)[0]), (
            "%s resolved to %s, which is not the stub" % (name, found)
        )


def _fixture(tmp_path: pathlib.Path, side: str, *, with_pins: bool = True) -> pathlib.Path:
    """One throwaway console tree holding both subjects at their real depths."""
    root = tmp_path / ("tree-%s" % side)
    (root / ".ci" / "scripts" / "release").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "rediacc_ci" / "release").mkdir(parents=True, exist_ok=True)
    (root / ".devcontainer").mkdir(parents=True, exist_ok=True)
    (root / "private" / "homebrew-tap" / "Formula").mkdir(parents=True, exist_ok=True)

    shutil.copy2(TWIN, root / ".ci" / "scripts" / "release" / TWIN.name)
    shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "release" / PORT.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(CONSTANTS, root / ".ci" / "config" / "constants.sh")
    if with_pins:
        shutil.copy2(TOOLCHAIN_ENV, root / ".devcontainer" / "toolchain.env")
    (root / "private" / "homebrew-tap" / "Formula" / "rediacc-cli.rb").write_text(
        FORMULA, encoding="utf-8"
    )
    return root


def _subject(root: pathlib.Path, side: str) -> pathlib.Path:
    if side == "old":
        return root / ".ci" / "scripts" / "release" / TWIN.name
    return root / ".ci" / "rediacc_ci" / "release" / PORT.name


def _run(
    tmp_path: pathlib.Path,
    side: str,
    args: list[str],
    *,
    with_pins: bool = True,
    local_binaries: tuple[str, ...] = (),
    **extra: str,
):
    root = _fixture(tmp_path, side, with_pins=with_pins)
    call_log = tmp_path / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    stub = _stub_path(tmp_path, side)
    _assert_no_real_tool(stub)

    if local_binaries:
        binaries = root / "dist"
        binaries.mkdir(parents=True, exist_ok=True)
        for name in local_binaries:
            (binaries / name).write_bytes(name.encode("utf-8"))

    env = {
        "PATH": stub,
        # A SCRATCH HOME, so the no-persistence test can prove nothing wrote a gitconfig, and so the real one is never in reach even of a fake.
        "HOME": str(tmp_path / ("%s-home" % side)),
        "TMPDIR": str(tmp_path / ("%s-tmp" % side)),
        "LC_ALL": "C",
        "LANG": "C",
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(call_log),
    }
    os.makedirs(env["HOME"], exist_ok=True)
    os.makedirs(env["TMPDIR"], exist_ok=True)
    env.update(extra)

    subject = _subject(root, side)
    runner = [BASH] if side == "old" else [sys.executable]
    resolved = [a.replace("@ROOT@", str(root)) for a in args]
    proc = subprocess.run(
        [*runner, str(subject), *resolved],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    formula = (root / "private" / "homebrew-tap" / "Formula" / "rediacc-cli.rb").read_text(
        encoding="utf-8"
    )
    return proc, calls, formula, root, env["TMPDIR"]


def run_both(tmp_path: pathlib.Path, args: list[str], **kw):
    old = _run(tmp_path, "old", args, **kw)
    new = _run(tmp_path, "new", args, **kw)
    return old, new


def _norm(text: str, root: pathlib.Path, tmpdir: str) -> str:
    """Mask what CANNOT agree, and nothing else.

    Two things: the per-side fixture root, and the random component `mktemp -d` (twin) or `tempfile.mkdtemp` (port) invents inside the per-side TMPDIR. The mask is anchored to that TMPDIR rather than to `/tmp`, so a real absolute path leaking from anywhere else is still compared.
    """
    masked = text.replace(str(root), "<tree>")
    return re.sub(re.escape(tmpdir) + r"/[^/\t\n \"']+", "<scratch>", masked)


def assert_agree(old, new, label: str) -> None:
    o_proc, o_calls, o_formula, o_root, o_tmp = old
    n_proc, n_calls, n_formula, n_root, n_tmp = new
    assert n_proc.returncode == o_proc.returncode, (
        "%s: exit diverged: %r vs %r\nold stderr: %r\nnew stderr: %r"
        % (label, o_proc.returncode, n_proc.returncode, o_proc.stderr, n_proc.stderr)
    )
    assert _norm(n_proc.stdout, n_root, n_tmp) == _norm(o_proc.stdout, o_root, o_tmp), (
        "%s: stdout diverged:\nold: %r\nnew: %r" % (label, o_proc.stdout, n_proc.stdout)
    )
    assert _norm(n_proc.stderr, n_root, n_tmp) == _norm(o_proc.stderr, o_root, o_tmp), (
        "%s: stderr diverged:\nold: %r\nnew: %r" % (label, o_proc.stderr, n_proc.stderr)
    )
    o_masked = [_norm(c, o_root, o_tmp) for c in o_calls]
    n_masked = [_norm(c, n_root, n_tmp) for c in n_calls]
    assert n_masked == o_masked, "%s: call sequence diverged:\nold: %s\nnew: %s" % (
        label,
        o_masked,
        n_masked,
    )
    assert n_formula == o_formula, "%s: the formula file diverged" % label


# --------------------------------------------------------------------------- Refusals, before anything is touched ---------------------------------------------------------------------------


def test_no_version_is_refused_and_nothing_is_called(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, [])
    assert old[0].returncode == 1
    assert old[0].stderr == "✗ --version is required\n"
    assert old[1] == [], "a tool ran before the version was validated"
    assert_agree(old, new, "no-version")


def test_an_unknown_option_is_refused(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--bogus"])
    assert old[0].returncode == 1
    assert old[0].stderr == "✗ Unknown option: --bogus\n"
    assert_agree(old, new, "unknown-option")


def test_a_missing_formula_is_refused_after_the_step_line(tmp_path: pathlib.Path) -> None:
    """`require_file` runs AFTER `log_step`, so the operator sees the intent and then the refusal. Order matters: a port that checked first would print one fewer line on the only path where a human is reading."""
    old2 = _rerun_without_formula(tmp_path, "old")
    new2 = _rerun_without_formula(tmp_path, "new")
    assert old2[0].returncode == 1
    assert "→ Updating Homebrew tap for version 9.9.9..." in old2[0].stderr
    assert "Required file" in old2[0].stderr
    assert old2[1] == [], "git ran before the formula was found"
    assert_agree(old2, new2, "missing-formula")


def _rerun_without_formula(tmp_path: pathlib.Path, side: str):
    """A fresh tree with the formula deleted, run for real."""
    root = _fixture(tmp_path, "nf-%s" % side)
    (root / "private" / "homebrew-tap" / "Formula" / "rediacc-cli.rb").unlink()
    call_log = tmp_path / ("nf-%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    stub = _stub_path(tmp_path, "nf-%s" % side)
    env = {
        "PATH": stub,
        "HOME": str(tmp_path / ("nf-%s-home" % side)),
        "TMPDIR": str(tmp_path / ("nf-%s-tmp" % side)),
        "LC_ALL": "C",
        "LANG": "C",
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(call_log),
    }
    os.makedirs(env["HOME"], exist_ok=True)
    os.makedirs(env["TMPDIR"], exist_ok=True)
    subject = _subject(root, "old" if side == "old" else "new")
    runner = [BASH] if side == "old" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), "--version", "9.9.9"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls, "", root, env["TMPDIR"]


def test_a_missing_toolchain_env_refuses_before_any_argument_is_read(
    tmp_path: pathlib.Path,
) -> None:
    """`source constants.sh` (:26) precedes the argument loop (:34), so a checkout without `.devcontainer/toolchain.env` cannot even print --help."""
    old, new = run_both(tmp_path, ["--help"], with_pins=False)
    assert old[0].returncode == 1
    assert "constants.sh: gate toolchain pins missing:" in old[0].stderr
    assert old[0].stdout == "", "the usage text printed despite the refusal"
    assert_agree(old, new, "no-toolchain-env")


# --------------------------------------------------------------------------- Two deliberate divergences, asserted in both directions ---------------------------------------------------------------------------


def test_divergence_help_and_unbound_operand_name_their_own_script(
    tmp_path: pathlib.Path,
) -> None:
    """`$0` AND bash's `set -u` DIAGNOSTIC BOTH NAME THE RUNNING PROGRAM, so the two subjects cannot agree byte for byte and must not pretend to. Everything
    except the script path agrees, the exit codes agree, and both halves are
    asserted so nobody later "fixes" one of them."""
    old_help = _run(tmp_path, "old", ["-h"])
    new_help = _run(tmp_path, "new", ["-h"])
    assert old_help[0].returncode == new_help[0].returncode == 0
    assert old_help[0].stdout.endswith(
        " --version X.Y.Z [--push | --stage-only] [--local-checksums <dir>] [--dry-run]\n"
    )
    assert new_help[0].stdout.endswith(
        " --version X.Y.Z [--push | --stage-only] [--local-checksums <dir>] [--dry-run]\n"
    )
    assert old_help[0].stdout.startswith("Usage: ")
    assert old_help[0].stdout != new_help[0].stdout
    assert "update-homebrew-tap.sh" in old_help[0].stdout
    assert "update_homebrew_tap.py" in new_help[0].stdout

    old_u = _run(tmp_path, "old", ["--version"])
    new_u = _run(tmp_path, "new", ["--version"])
    assert old_u[0].returncode == new_u[0].returncode == 1
    shape = re.compile(r"^\S+: line \d+: \$2: unbound variable\n$")
    assert shape.match(old_u[0].stderr), old_u[0].stderr
    assert shape.match(new_u[0].stderr), new_u[0].stderr
    assert old_u[0].stderr != new_u[0].stderr


# --------------------------------------------------------------------------- The download path ---------------------------------------------------------------------------


def test_the_download_path_writes_each_checksum_into_its_own_platform_block(
    tmp_path: pathlib.Path,
) -> None:
    """THE STEP A PORT WOULD SILENTLY GET WRONG. Four `sha256` lines, one file, and the only thing telling them apart is the awk state machine. Four distinct fake checksums make a mix-up readable; the assertions below name which one belongs where."""
    old, new = run_both(tmp_path, ["--version", "2.5.0"])
    assert old[0].returncode == 0, old[0].stderr
    formula = old[2]
    assert 'version "2.5.0"' in formula
    blocks = formula.split("on_linux do")
    assert SHA_MAC_ARM in blocks[0]
    assert SHA_MAC_X64 in blocks[0]
    assert SHA_LINUX_ARM in blocks[1]
    assert SHA_LINUX_X64 in blocks[1]
    arm_first = formula.index(SHA_MAC_ARM) < formula.index(SHA_MAC_X64)
    assert arm_first, "the mac arm64 checksum did not land in the arm branch"
    assert formula.index(SHA_LINUX_ARM) < formula.index(SHA_LINUX_X64)
    assert_agree(old, new, "download-path")


def test_the_download_urls_are_exact(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--version", "2.5.0"])
    urls = [c.split("\t")[2] for c in old[1] if c.startswith("curl\t")]
    assert urls == [
        "https://releases.rediacc.com/cli/v2.5.0/rdc-mac-arm64.sha256",
        "https://releases.rediacc.com/cli/v2.5.0/rdc-mac-x64.sha256",
        "https://releases.rediacc.com/cli/v2.5.0/rdc-linux-arm64.sha256",
        "https://releases.rediacc.com/cli/v2.5.0/rdc-linux-x64.sha256",
    ]
    assert_agree(old, new, "download-urls")


def test_releases_base_url_is_overridable_from_the_environment(
    tmp_path: pathlib.Path,
) -> None:
    """`.ci/config/constants.sh:200` uses `:-`, so a caller can point the download at a staging bucket. A port that hardcoded the default would look identical on every CI run and be wrong on every staging one."""
    old, new = run_both(
        tmp_path, ["--version", "2.5.0"], RELEASES_BASE_URL="https://staging.example"
    )
    urls = [c.split("\t")[2] for c in old[1] if c.startswith("curl\t")]
    assert urls[0] == "https://staging.example/cli/v2.5.0/rdc-mac-arm64.sha256"
    assert_agree(old, new, "base-url-override")


def test_a_failed_download_names_the_file_and_stops(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--version", "2.5.0"], FAKE_CURL_RC="22")
    assert old[0].returncode == 1
    assert "✗ Failed to download checksum: rdc-mac-arm64.sha256\n" in old[0].stderr
    assert len([c for c in old[1] if c.startswith("curl\t")]) == 1, (
        "the run continued after the first download failed"
    )
    assert 'version "1.0.0"' in old[2], "the formula was rewritten from a failed download"
    assert_agree(old, new, "download-fails")


def test_dry_run_downloads_nothing_and_writes_nothing(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--version", "2.5.0", "--dry-run"])
    assert old[0].returncode == 0
    assert [c for c in old[1] if c.startswith("curl\t")] == []
    assert old[2] == FORMULA, "dry-run touched the formula"
    assert "[DRY-RUN] Would download checksums for v2.5.0" in old[0].stderr
    assert "[DRY-RUN] Would update formula to version 2.5.0" in old[0].stderr
    assert_agree(old, new, "dry-run")


def test_dry_run_still_runs_fetch_and_rev_parse_and_still_says_synced(
    tmp_path: pathlib.Path,
) -> None:
    """A QUIRK WORTH PINNING RATHER THAN TIDYING. `sync_to_origin_main` skips only the `checkout` under --dry-run: the `fetch` and the `rev-parse` still run and the "Synced" line still prints, so the message overstates what happened."""
    old, new = run_both(tmp_path, ["--version", "2.5.0", "--dry-run"])
    verbs = [c.split("\t")[1:] for c in old[1] if c.startswith("git\t")]
    flat = [" ".join(v) for v in verbs]
    assert any("fetch origin main" in f for f in flat)
    assert any("rev-parse origin/main" in f for f in flat)
    assert not any("checkout" in f for f in flat)
    assert "Synced" in old[0].stderr
    assert_agree(old, new, "dry-run-sync")


def test_an_unresolvable_origin_main_ends_the_run_with_gits_own_status(
    tmp_path: pathlib.Path,
) -> None:
    """The `rev-parse` is a bare assignment, so `set -e` kills the script with git's status and git's stderr, before the "Synced" line."""
    old, new = run_both(tmp_path, ["--version", "2.5.0"], FAKE_GIT_REVPARSE_RC="128")
    assert old[0].returncode == 128
    assert "fatal: ambiguous argument 'origin/main'" in old[0].stderr
    assert "Synced" not in old[0].stderr
    assert_agree(old, new, "rev-parse-fails")


# --------------------------------------------------------------------------- The local-checksum path ---------------------------------------------------------------------------


def test_local_checksums_are_computed_and_reported(tmp_path: pathlib.Path) -> None:
    old, new = run_both(
        tmp_path,
        ["--version", "3.0.0", "--local-checksums", "@ROOT@/dist"],
        local_binaries=port.BINARY_NAMES,
    )
    assert old[0].returncode == 0, old[0].stderr
    assert "Computed all checksums from local binaries" in old[0].stderr
    assert [c for c in old[1] if c.startswith("curl\t")] == [], "R2 was contacted anyway"
    for name in port.BINARY_NAMES:
        assert re.search(r"%s: [0-9a-f]{64}" % re.escape(name), old[0].stderr), name
    assert_agree(old, new, "local-checksums")


def test_one_missing_local_binary_is_fatal_even_when_three_are_present(
    tmp_path: pathlib.Path,
) -> None:
    """The twin's own comment (:125-127) says the floor is PER ARTIFACT, and it is the stricter reading: three of four present still exits 1, and it stops at the missing one rather than reporting an aggregate."""
    present = tuple(n for n in port.BINARY_NAMES if n != "rdc-linux-x64")
    args = ["--version", "3.0.0", "--local-checksums", "@ROOT@/dist"]
    old, new = run_both(tmp_path, args, local_binaries=present)
    assert old[0].returncode == 1
    assert "✗ Missing local binary matching rdc-linux-x64* in " in old[0].stderr
    assert "Computed all checksums" not in old[0].stderr
    assert old[2] == FORMULA, "the formula was rewritten from an incomplete set"
    assert_agree(old, new, "missing-local-binary")


def test_a_local_checksum_directory_that_does_not_exist_is_fatal_on_the_first_name(
    tmp_path: pathlib.Path,
) -> None:
    """`find` on a missing directory writes its own diagnostic to the INHERITED stderr and the empty result is what the script acts on."""
    args = ["--version", "3.0.0", "--local-checksums", "@ROOT@/nope"]
    old, new = run_both(tmp_path, args)
    assert old[0].returncode == 1
    assert "✗ Missing local binary matching rdc-mac-arm64* in " in old[0].stderr
    assert_agree(old, new, "missing-local-dir")


# --------------------------------------------------------------------------- The commit / push / pointer paths ---------------------------------------------------------------------------


def test_push_commits_in_the_tap_then_commits_and_pushes_the_pointer(
    tmp_path: pathlib.Path,
) -> None:
    old, new = run_both(
        tmp_path,
        ["--version", "2.5.0", "--push"],
        GIT_BOT_NAME="Rediacc Bot",
        GIT_BOT_EMAIL="bot@rediacc.com",
        FAKE_GIT_DIFF_RC="1",
        FAKE_GIT_DIFF_CACHED_RC="1",
    )
    assert old[0].returncode == 0, old[0].stderr
    flat = "\n".join(old[1])
    assert "chore(release): bump rediacc-cli to 2.5.0 [skip ci]" in flat
    assert "chore(release): update homebrew-tap submodule pointer [skip ci]" in flat
    assert "user.name=Rediacc Bot" in flat
    assert flat.count("push\torigin\tHEAD:main") == 2
    assert "✓ Pushed to homebrew-tap" in old[0].stderr
    assert "✓ Committed and pushed homebrew-tap submodule pointer update" in old[0].stderr
    assert_agree(old, new, "push")


def test_stage_only_commits_in_the_tap_and_only_stages_the_pointer(
    tmp_path: pathlib.Path,
) -> None:
    old, new = run_both(
        tmp_path,
        ["--version", "2.5.0", "--stage-only"],
        GIT_BOT_NAME="Rediacc Bot",
        GIT_BOT_EMAIL="bot@rediacc.com",
    )
    assert old[0].returncode == 0, old[0].stderr
    flat = "\n".join(old[1])
    assert "chore(release): bump rediacc-cli to 2.5.0 [skip ci]" in flat
    assert "submodule pointer [skip ci]" not in flat
    assert flat.count("push\torigin\tHEAD:main") == 1, "the parent repo was pushed"
    assert "Staged private/homebrew-tap submodule pointer in parent repo" in old[0].stderr
    assert_agree(old, new, "stage-only")


def test_stage_only_wins_over_push_when_both_are_given(tmp_path: pathlib.Path) -> None:
    """Not refused, silently resolved (:303-309). Reproduced, not repaired."""
    old, new = run_both(
        tmp_path,
        ["--version", "2.5.0", "--push", "--stage-only"],
        GIT_BOT_NAME="B",
        GIT_BOT_EMAIL="b@e",
    )
    assert old[0].returncode == 0
    assert "Staged private/homebrew-tap submodule pointer" in old[0].stderr
    assert "Committed and pushed homebrew-tap submodule pointer" not in old[0].stderr
    assert_agree(old, new, "both-flags")


def test_an_unchanged_formula_is_not_committed(tmp_path: pathlib.Path) -> None:
    old, new = run_both(
        tmp_path,
        ["--version", "2.5.0", "--push"],
        GIT_BOT_NAME="B",
        GIT_BOT_EMAIL="b@e",
        FAKE_GIT_DIFF_RC="0",
    )
    assert old[0].returncode == 0
    assert "✓ Formula already at version 2.5.0" in old[0].stderr
    flat = "\n".join(old[1])
    assert "bump rediacc-cli to 2.5.0" not in flat, "an unchanged formula was committed"
    # AND THE POINTER STILL MOVES. `commit_and_push` returning early does not stop `update_submodule_pointer`, so the parent repo is still committed and pushed when its index says the gitlink changed. Reproduced, not repaired.
    assert "update homebrew-tap submodule pointer [skip ci]" in flat
    assert_agree(old, new, "already-current")


def test_no_pointer_change_is_reported_and_nothing_is_pushed(
    tmp_path: pathlib.Path,
) -> None:
    old, new = run_both(
        tmp_path,
        ["--version", "2.5.0", "--push"],
        GIT_BOT_NAME="B",
        GIT_BOT_EMAIL="b@e",
        FAKE_GIT_DIFF_CACHED_RC="0",
    )
    assert old[0].returncode == 0
    assert "✓ No submodule pointer changes" in old[0].stderr
    assert "\n".join(old[1]).count("push\torigin\tHEAD:main") == 1
    assert_agree(old, new, "no-pointer-change")


def test_neither_push_nor_stage_only_writes_the_formula_and_stops(
    tmp_path: pathlib.Path,
) -> None:
    old, new = run_both(tmp_path, ["--version", "2.5.0"])
    assert old[0].returncode == 0
    assert SHA_MAC_ARM in old[2]
    assert not any("\tcommit\t" in c for c in old[1])
    assert not any("\tpush\t" in c for c in old[1])
    assert old[0].stderr.endswith("✓ Homebrew tap update complete\n")
    assert_agree(old, new, "no-commit-flags")


def test_a_missing_git_bot_name_kills_the_run_after_the_formula_was_written(
    tmp_path: pathlib.Path,
) -> None:
    """A REAL LATENT DEFECT, REPRODUCED RATHER THAN REPAIRED.
    `.ci/config/constants.sh:164-166` deliberately does NOT declare GIT_BOT_NAME / GIT_BOT_EMAIL, and `set -u` makes reading an undeclared one fatal. So `--push` on a machine without the org variables rewrites the formula, stages it, and then dies -- leaving the submodule dirty with an uncommitted change and no message explaining why."""
    old = _run(tmp_path, "old", ["--version", "2.5.0", "--push"])
    new = _run(tmp_path, "new", ["--version", "2.5.0", "--push"])
    assert old[0].returncode == new[0].returncode == 1
    shape = re.compile(r"\S+: line \d+: GIT_BOT_NAME: unbound variable\n$")
    assert shape.search(old[0].stderr), old[0].stderr
    assert shape.search(new[0].stderr), new[0].stderr
    assert SHA_MAC_ARM in old[2], "the formula was NOT written before the crash"
    assert old[2] == new[2], "the two left the formula in different states"
    assert any("\tadd\t" in c for c in old[1]), "the change was not even staged"
    assert not any("\tcommit\t" in c for c in old[1])


def test_github_pat_is_passed_per_command_and_never_persisted(
    tmp_path: pathlib.Path,
) -> None:
    """The token authenticates the fetch and both pushes through `-c` credential-helper arguments that hold no secret, and nothing writes git config.

    A `git config --global` insteadOf write once left a plaintext PAT in ~/.gitconfig, which the devbox shares with the host. Reverting either side to that write turns this red on three counts: a `config` call, the token in argv, and a scratch-HOME gitconfig.
    """
    old, new = run_both(
        tmp_path,
        ["--version", "2.5.0", "--push"],
        GITHUB_PAT="ghp_secret",
        GIT_BOT_NAME="B",
        GIT_BOT_EMAIL="b@e",
    )
    assert old[0].returncode == 0, old[0].stderr
    for side in (old, new):
        calls = side[1]
        assert not any("\tconfig\t" in c for c in calls), calls
        assert not any("ghp_secret" in c for c in calls), "the token reached argv"
        helper = "credential.https://github.com.helper=" + port.CREDENTIAL_HELPER
        authed = [c for c in calls if helper in c]
        verbs = sorted(c.rsplit("\t", 3)[1] if "fetch" not in c else "fetch" for c in authed)
        assert verbs == ["fetch", "push", "push"], authed
        for c in authed:
            assert "\tcredential.https://github.com.helper=\t" in c, "the reset entry is missing"
        assert not (tmp_path / "old-home" / ".gitconfig").exists()
        assert not (tmp_path / "new-home" / ".gitconfig").exists()
    assert_agree(old, new, "github-pat")


def test_no_github_pat_means_no_credential_arguments(tmp_path: pathlib.Path) -> None:
    old, new = run_both(
        tmp_path, ["--version", "2.5.0", "--push"], GIT_BOT_NAME="B", GIT_BOT_EMAIL="b@e"
    )
    assert old[0].returncode == 0, old[0].stderr
    assert not any("credential." in c for c in old[1] + new[1])
    assert_agree(old, new, "no-pat")


def test_the_credential_helper_answers_real_git_with_the_token(tmp_path: pathlib.Path) -> None:
    """The helper string is exercised against REAL git, not the fake: `git credential fill` must hand back the token from the environment, and the reset entry must shadow a helper inherited from the user's gitconfig."""
    real_git = shutil.which("git")
    assert real_git is not None
    home = tmp_path / "cred-home"
    home.mkdir()
    (home / ".gitconfig").write_text(
        '[credential "https://github.com"]\n\thelper = "!f() { echo username=inherited; echo password=inherited; }; f"\n',
        encoding="utf-8",
    )
    env = {
        "PATH": os.pathsep.join([os.path.dirname(real_git), "/usr/bin", "/bin"]),
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GITHUB_PAT": "ghp_probe",
    }
    proc = subprocess.run(
        [real_git, *port.auth_args(env), "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "username=x-access-token\n" in proc.stdout
    assert "password=ghp_probe\n" in proc.stdout
    assert "inherited" not in proc.stdout
    assert port.auth_args({"GITHUB_PAT": ""}) == []
    assert port.auth_args({}) == []


def test_a_dirty_tap_is_refused_before_any_fetch_or_checkout(tmp_path: pathlib.Path) -> None:
    """A forced `checkout -B main` used to run over the tap's working tree, discarding uncommitted work. A non-empty `git status --porcelain` now ends the run with exit 1 before anything is fetched, reset or rewritten, in dry-run too."""
    for args in (["--version", "2.5.0", "--push"], ["--version", "2.5.0", "--dry-run"]):
        old, new = run_both(
            tmp_path,
            args,
            GIT_BOT_NAME="B",
            GIT_BOT_EMAIL="b@e",
            FAKE_GIT_STATUS_OUT=" M Formula/rediacc-cli.rb\n",
        )
        assert old[0].returncode == 1, old[0].stderr
        assert "Refusing to reset" in old[0].stderr
        assert "uncommitted changes" in old[0].stderr
        verbs = [c.split("\t") for c in old[1]]
        assert [v[3] for v in verbs] == ["status"], old[1]
        assert old[2] == FORMULA, "the formula was rewritten despite the refusal"
        assert_agree(old, new, "dirty-%s" % args[-1])


def test_a_clean_tap_is_reset_without_force(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--version", "2.5.0"])
    checkouts = [c for c in old[1] if "\tcheckout\t" in c]
    assert len(checkouts) == 1, old[1]
    assert "--force" not in checkouts[0]
    assert old[1][0].split("\t")[3] == "status"
    assert_agree(old, new, "clean-tap")


def test_a_failing_git_status_ends_the_run_with_its_status(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--version", "2.5.0"], FAKE_GIT_STATUS_RC="128")
    assert old[0].returncode == 128
    assert not any("\tfetch\t" in c for c in old[1])
    assert_agree(old, new, "status-fails")


def test_gh_is_never_invoked(tmp_path: pathlib.Path) -> None:
    """A CONTROL ON THE STUB, not on the script. `gh` is on the PATH as a fake that records and exits 91, so if either side ever reached for it the call log would say so and the run would fail loudly rather than silently authenticating against the real account."""
    old, new = run_both(
        tmp_path, ["--version", "2.5.0", "--push"], GIT_BOT_NAME="B", GIT_BOT_EMAIL="b@e"
    )
    assert not any(c.startswith("gh\t") for c in old[1])
    assert not any(c.startswith("gh\t") for c in new[1])
    assert old[0].returncode == 0


# --------------------------------------------------------------------------- Pure helpers, constants, and the plant ---------------------------------------------------------------------------


def test_pure_helpers() -> None:
    assert port.checksum_url("https://x", "1.2.3", "a.sha256") == "https://x/cli/v1.2.3/a.sha256"
    assert port.commit_message("1.2.3") == "chore(release): bump rediacc-cli to 1.2.3 [skip ci]"
    assert port.usage("p").startswith("Usage: p --version X.Y.Z")
    assert port.releases_base_url({}) == "https://releases.rediacc.com"
    assert port.releases_base_url({"RELEASES_BASE_URL": "https://s"}) == "https://s"
    assert port.releases_base_url({"RELEASES_BASE_URL": ""}) == "https://releases.rediacc.com"
    opts = port.parse_argv(["--version", "1.0.0", "--push", "--dry-run"])
    assert (opts.version, opts.push, opts.dry_run) == ("1.0.0", True, True)
    assert not opts.stage_only
    assert port.parse_argv([]).version == ""


def test_constants_have_not_drifted() -> None:
    """The two scalars the twin gets from constants.sh, re-read from the file.

    A LIVE PARSE WOULD FOLLOW A CHANGE SILENTLY; this turns one red instead.
    """
    text = CONSTANTS.read_text(encoding="utf-8")
    assert 'readonly HOMEBREW_FORMULA_PATH="%s"' % port.HOMEBREW_FORMULA_PATH in text
    assert (
        'readonly RELEASES_BASE_URL="${RELEASES_BASE_URL:-%s}"' % port.RELEASES_BASE_URL_DEFAULT
        in text
    )


def test_the_fixture_matches_the_real_formulas_shape() -> None:
    """ANTI-VACUITY ON THE FIXTURE. The awk state machine keys on five literal markers; if the real formula stopped carrying them the differential would still pass against a fixture nobody ships."""
    real = ROOT / "private" / "homebrew-tap" / port.HOMEBREW_FORMULA_PATH
    if not real.is_file():
        return
    text = real.read_text(encoding="utf-8")
    for marker in ("on_macos do", "on_linux do", "if Hardware::CPU.arm?"):
        assert marker in text, marker
        assert marker in FORMULA, marker
    assert text.count('sha256 "') == FORMULA.count('sha256 "') == 4
    assert len(re.findall(r"^\s*else\s*$", text, re.MULTILINE)) == len(
        re.findall(r"^\s*else\s*$", FORMULA, re.MULTILINE)
    )


def test_planted_slot_swap_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted where a port would fail INVISIBLY: the two mac checksums are swapped, so every stream is byte-identical, every git call is identical, and the only evidence is the formula file. Driven red, then the source is confirmed byte-identical and green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        '    ("mac_arm64", "rdc-mac-arm64.sha256", "mac-arm64:  "),\n'
        '    ("mac_x64", "rdc-mac-x64.sha256", "mac-x64:    "),',
        '    ("mac_arm64", "rdc-mac-x64.sha256", "mac-arm64:  "),\n'
        '    ("mac_x64", "rdc-mac-arm64.sha256", "mac-x64:    "),',
    )
    assert mutated != original, "the lines this plant targets are no longer present verbatim"

    good_old, good_new = run_both(tmp_path, ["--version", "2.5.0"])
    assert_agree(good_old, good_new, "plant-baseline")

    bad_root = _fixture(tmp_path, "mutant")
    (bad_root / ".ci" / "rediacc_ci" / "release" / PORT.name).write_text(mutated, encoding="utf-8")
    call_log = tmp_path / "mutant-calls.log"
    call_log.write_text("", encoding="utf-8")
    stub = _stub_path(tmp_path, "mutant")
    env = {
        "PATH": stub,
        "HOME": str(tmp_path / "mutant-home"),
        "TMPDIR": str(tmp_path / "mutant-tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(call_log),
    }
    os.makedirs(env["HOME"], exist_ok=True)
    os.makedirs(env["TMPDIR"], exist_ok=True)
    bad = subprocess.run(
        [
            sys.executable,
            str(bad_root / ".ci" / "rediacc_ci" / "release" / PORT.name),
            "--version",
            "2.5.0",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    bad_formula = (bad_root / "private" / "homebrew-tap" / "Formula" / "rediacc-cli.rb").read_text(
        encoding="utf-8"
    )
    assert bad.returncode == good_old[0].returncode, (
        "the plant is invisible in the exit code, which is why the formula is compared"
    )
    assert bad_formula != good_old[2], "the mutant produced the correct formula"
    assert bad_formula.index(SHA_MAC_X64) < bad_formula.index(SHA_MAC_ARM), (
        "the plant did not actually swap the two mac slots"
    )
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
