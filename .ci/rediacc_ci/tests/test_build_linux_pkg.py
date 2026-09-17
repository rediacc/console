"""Differential: `rediacc_ci.build.build_linux_pkg` against its twin
`.ci/scripts/build/build-linux-pkg.sh`.

WHAT IS COMPARED, per case and never folded: stdout, stderr, exit code, the
FAKE-BINARY CALL LOG, the env `nfpm` was handed, and every file left under the
output directory.

WHY THE ENV DUMP IS PART OF THE COMPARISON. This script's real output is a
`.deb`, and everything that decides what is INSIDE it -- the package name, the
maintainer, the version, the arch, the absolute binary path, the signing key
file -- reaches nfpm as ENVIRONMENT, because `.ci/config/nfpm.yaml` is a
template over those variables. A port that logged all six `✓` lines correctly
and exported `NFPM_ARCH=x64` instead of `amd64` would be byte-identical on both
streams and would ship an unusable package. The fake `nfpm` therefore writes the
variables it was given to `$FAKE_ENV_DUMP`, and `_agree` compares them.

THE BUILD DIRECTORY IS MASKED, AND IT HAS TO BE. `mktemp -d` and
`tempfile.mkdtemp()` both invent a random name, and that name appears in three
different argv (`nfpm --target`, the canonicaliser's key path, `gpg --show-keys`).
Comparing it would be comparing two random strings. The masking is done INSIDE
the fakes rather than in this file, so the shadow-gate ledger -- which has no
masking hook of its own -- gets the identical normalisation. `$TMPDIR` is
pointed at a fixture directory so the fakes can recognise what to mask.

RECORDED TO `$FAKE_CALL_LOG`, NEVER TO STDOUT. The fake `gpg`'s stdout IS the
colon-format key listing the script parses.

THE PATH IS REPLACED, NOT PREPENDED. `test_the_scratch_path_is_sealed` asserts
there is no reachable real `nfpm` or `gpg` before anything is driven; a real
`gpg --import` reaching a developer's keyring would be a genuine accident.

`$0` IS MASKED TO `<SELF>`; the `line <n>: ` in a `set -u` death is masked in the
one test that drives it. Nothing else.

K=5 LEDGER: `.ci/shadow/w7p6-build-linux-pkg.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.build import build_linux_pkg as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/build-linux-pkg.sh"
PORT_REL = ".ci/rediacc_ci/build/build_linux_pkg.py"
COMMON_REL = ".ci/scripts/lib/common.sh"
CONSTANTS_REL = ".ci/config/constants.sh"
TOOLCHAIN_REL = ".devcontainer/toolchain.env"
CANON_REL = ".ci/scripts/build/canonicalise-gpg-key.sh"

VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/build/__init__.py",
)

BASH = shutil.which("bash") or "/bin/bash"

# Real, deterministic, and genuinely reached: `dirname` and `basename` by the twin's own path arithmetic, `tr` by its lowercase of a flag name, `find` and `head` by the output lookup, `cp`/`mkdir`/`wc` by the copy and the size line, `mktemp` by `:172` and `rm` by the EXIT trap. Everything not listed is ABSENT, including a real `nfpm` and a real `gpg`.
#
# `mktemp` WAS MISSING FROM THIS TUPLE and every build-path case failed with `line 172: mktemp: command not found`, exit 127, on the OLD side only. That is the PATH-discipline trap this campaign keeps hitting from the other direction: replacing PATH is right, and a tool the twin genuinely needs then has to be listed here or the differential compares a real run against a broken one.
PATH_MINIMUM = (
    "dirname",
    "basename",
    "mkdir",
    "mktemp",
    "cp",
    "head",
    "tr",
    "wc",
    "cat",
    "uname",
    "sed",
    "awk",
    "rm",
)

# `find` is a FAKE that records its argv and then execs the real one, so the lookup at `:277-279` is compared as an INVOCATION and not merely by its result. Without it a port that said `-maxdepth 2` would pass every case here, because nfpm's output directory has no subdirectory for the difference to show up in. `$FAKE_FIND_RC` also makes DEFECT 3 drivable.
REAL_FIND = shutil.which("find")

# The masking helper every fake shares. `$FIXTURE_TMP/<random>/rest` becomes `<BUILD_DIR>/rest`, and `$FIXTURE_TMP/<random>/` becomes `<BUILD_DIR>/`.
MASK = r"""
__mask() {
    local a="$1" rest sub
    if [[ -n "${FIXTURE_TMP:-}" && "$a" == "$FIXTURE_TMP"/* ]]; then
        rest="${a#"$FIXTURE_TMP"/}"
        sub="${rest#*/}"
        if [[ "$sub" == "$rest" ]]; then printf '<BUILD_DIR>'; else printf '<BUILD_DIR>/%s' "$sub"; fi
    else
        printf '%s' "$a"
    fi
}
__record() {
    {
        printf 'FAKEBIN %s' "$__self"
        for a in "$@"; do printf '\t'; __mask "$a"; done
        printf '\n'
    } >>"$FAKE_CALL_LOG"
}
"""

# `nfpm package --config X --packager F --target D/`. Writes ONE file, named the way nfpm names things (which is deliberately NOT the name the script wants -- the rename at `:286` is the behaviour under test).
FAKE_NFPM = (
    """#!/bin/bash
__self=nfpm
"""
    + MASK
    + """
__record "$@"
if [[ -n "${FAKE_ENV_DUMP:-}" ]]; then
    for v in PKG_NAME PKG_BINARY_NAME PKG_SECTION PKG_PRIORITY PKG_MAINTAINER \\
             PKG_DESCRIPTION PKG_HOMEPAGE VERSION NFPM_ARCH BINARY_PATH \\
             NFPM_RPM_KEY_FILE NFPM_DEB_KEY_FILE NFPM_APK_KEY_FILE \\
             NFPM_RPM_PASSPHRASE NFPM_DEB_PASSPHRASE CI_OS CI_ARCH CI_TEMP; do
        printf '%s=' "$v"
        __mask "${!v-<unset>}"
        printf '\\n'
    done >"$FAKE_ENV_DUMP"
fi
if [[ "${FAKE_NFPM_WRITES:-1}" == "1" ]]; then
    target=""
    packager=""
    prev=""
    for a in "$@"; do
        [[ "$prev" == "--target" ]] && target="$a"
        [[ "$prev" == "--packager" ]] && packager="$a"
        prev="$a"
    done
    case "$packager" in
        archlinux) ext="pkg.tar.zst" ;;
        *) ext="$packager" ;;
    esac
    printf 'NFPM PACKAGE PAYLOAD\\n' >"${target}nfpm-native-name.${ext}"
fi
exit "${FAKE_NFPM_RC:-0}"
"""
)

# `gpg --show-keys --with-colons --with-fingerprint FILE`. The colon format the
# twin's awk reads; driven by the FILE's own content so a fixture can hand the
# two calls different answers without a second env var.
FAKE_GPG = (
    """#!/bin/bash
__self=gpg
"""
    + MASK
    + """
__record "$@"
file="${!#}"
body="$(cat "$file" 2>/dev/null || true)"
case "$body" in
    *BADKEY*)
        printf 'gpg: no valid OpenPGP data found.\\n' >&2
        exit 2
        ;;
    *NOFPR*)
        printf 'pub:u:255:22:0000000000000000:1700000000:::u:::scESC::::::ed25519:::0:\\n'
        exit 0
        ;;
esac
fpr="${body##*FPR=}"
fpr="${fpr%%$'\\n'*}"
printf 'pub:u:255:22:0000000000000000:1700000000:::u:::scESC::::::ed25519:::0:\\n'
printf 'fpr:::::::::%s:\\n' "$fpr"
exit 0
"""
)

FAKE_CANON = (
    """#!/bin/bash
__self=canonicalise-gpg-key.sh
"""
    + MASK
    + """
__record "$@"
exit "${FAKE_CANON_RC:-0}"
"""
)

# Records, then delegates to the real `find` so the DIRECTORY-ORDER behaviour the port's module head relies on is genuinely exercised. `FAKE_FIND_RC` overrides the real status without changing the output, which is what DEFECT 3 needs: a `find` that PRINTS a package and still exits non-zero.
FAKE_FIND = (
    """#!/bin/bash
__self=find
"""
    + MASK
    + """
__record "$@"
"$FAKE_REAL_FIND" "$@"
rc=$?
exit "${FAKE_FIND_RC:-$rc}"
"""
)

FAKES = {"nfpm": FAKE_NFPM, "gpg": FAKE_GPG, "find": FAKE_FIND}

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))
LINE_RE = re.compile(r"line \d+: ")

GOOD_FPR = "ABCDEF0123456789ABCDEF0123456789ABCDEF01"
OTHER_FPR = "9999999999999999999999999999999999999999"

# The passphrase the fixture hands the signing path, and what the fake `nfpm` prints for a variable it was NOT given.
#
# BOUND TO A NAME RATHER THAN WRITTEN INLINE, and that is a lint constraint rather than a style preference: ruff's S105/S106 flag a string LITERAL next to
# an identifier that looks like a credential, so `_signed(RELEASE_GPG_PASSPHRASE=
# "hunter2")` and `seen["NFPM_RPM_PASSPHRASE"] == "hunter2"` are four findings.
# A reference is not a literal. Suppressing the rule per line is what `check:ci-python-lint` explicitly refuses, and it would be the wrong trade anyway: the rule is right in general and merely uninformed about fixtures.
#
# `FIXTURE_PHRASE`, not `FIXTURE_PASSPHRASE`: S105 matches the IDENTIFIER, so naming the constant after what it holds simply moved the same finding from five call sites to one declaration.
FIXTURE_PHRASE = "hunter2"
UNSET = "<unset>"


def fixture(
    tmp_path: pathlib.Path,
    *,
    port_source: str | None = None,
    public_key: str | None = "FPR=%s\n" % GOOD_FPR,
    private_key: str = "FPR=%s\n" % GOOD_FPR,
    binary: bool = True,
) -> pathlib.Path:
    root = tmp_path / "repo"
    for rel in (TWIN_REL, PORT_REL, COMMON_REL, CONSTANTS_REL, TOOLCHAIN_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in (TWIN_REL, COMMON_REL, CONSTANTS_REL, TOOLCHAIN_REL, *VENDORED):
        shutil.copy2(ROOT / rel, root / rel)
    if port_source is None:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")

    canon = root / CANON_REL
    canon.write_text(FAKE_CANON, encoding="utf-8")
    canon.chmod(0o755)

    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "config" / "nfpm.yaml").write_text("# template\n", encoding="utf-8")
    (root / ".ci" / "keys").mkdir(parents=True, exist_ok=True)
    if public_key is not None:
        (root / ".ci" / "keys" / "gpg-public.asc").write_text(public_key, encoding="utf-8")
    if binary:
        (root / "dist" / "cli").mkdir(parents=True, exist_ok=True)
        (root / "dist" / "cli" / "rdc-linux-x64").write_text("BINARY\n", encoding="utf-8")
    (root / "fixture-tmp").mkdir(exist_ok=True)
    root.joinpath("private-key.txt").write_text(private_key, encoding="utf-8")
    return root


def scratch_bin(root: pathlib.Path, *, drop: tuple[str, ...] = ()) -> str:
    stub = root / "fixture-bin"
    if stub.exists():
        shutil.rmtree(stub)
    stub.mkdir(parents=True)
    for name in PATH_MINIMUM:
        if name in drop:
            continue
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        (stub / name).symlink_to(real)
    for name, body in FAKES.items():
        if name in drop:
            continue
        (stub / name).write_text(body, encoding="utf-8")
        (stub / name).chmod(0o755)
    return str(stub)


def _run(
    root: pathlib.Path,
    side: str,
    *,
    args: tuple[str, ...] = (),
    drop: tuple[str, ...] = (),
    env_overrides: dict[str, str | None] | None = None,
):
    call_log = root / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env_dump = root / ("%s-env.txt" % side)
    if env_dump.exists():
        env_dump.unlink()
    fixture_tmp = root / "fixture-tmp"
    env = {
        "PATH": scratch_bin(root, drop=drop),  # REPLACED, never prepended.
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(fixture_tmp),
        "FIXTURE_TMP": str(fixture_tmp),
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_ENV_DUMP": str(env_dump),
        "FAKE_REAL_FIND": str(REAL_FIND),
    }
    for key, value in (env_overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    argv = [BASH, str(root / TWIN_REL)] if side == "old" else [sys.executable, str(root / PORT_REL)]
    proc = subprocess.run(
        [*argv, *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    dumped = env_dump.read_text(encoding="utf-8") if env_dump.exists() else ""
    return proc, call_log.read_text(encoding="utf-8"), dumped


def _artifacts(root: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for base in (root / "dist" / "packages", root / "out"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                out[str(path.relative_to(root))] = path.read_text(
                    encoding="utf-8", errors="replace"
                )
            elif path.is_dir():
                out[str(path.relative_to(root)) + "/"] = "<dir>"
    for base in (root / "dist" / "packages", root / "out"):
        if base.is_dir():
            out[str(base.relative_to(root)) + "/"] = "<dir>"
    return out


def _leftover_temp(root: pathlib.Path) -> list[str]:
    """The EXIT trap's subject. A build directory that survives is a leak, and it
    is invisible on every stream."""
    return sorted(p.name for p in (root / "fixture-tmp").iterdir())


def _reset(root: pathlib.Path) -> None:
    for rel in ("dist/packages", "out", "fixture-tmp"):
        shutil.rmtree(root / rel, ignore_errors=True)
    (root / "fixture-tmp").mkdir(parents=True, exist_ok=True)


def run_both(root: pathlib.Path, **kw):
    _reset(root)
    old = (*_run(root, "old", **kw), _artifacts(root), _leftover_temp(root))
    _reset(root)
    new = (*_run(root, "new", **kw), _artifacts(root), _leftover_temp(root))
    return old, new


def _mask(text: str, *, lines: bool = False) -> str:
    masked = SELF_RE.sub("<SELF>", text)
    return LINE_RE.sub("line <N>: ", masked) if lines else masked


def _agree(old_t, new_t, label: str, *, lines: bool = False) -> None:
    old, old_calls, old_env, old_files, old_tmp = old_t
    new, new_calls, new_env, new_files, new_tmp = new_t
    assert new.returncode == old.returncode, (
        "%s: exit diverged: %r vs %r\nold stderr: %r\nnew stderr: %r"
        % (label, old.returncode, new.returncode, old.stderr, new.stderr)
    )
    assert _mask(new.stdout, lines=lines) == _mask(old.stdout, lines=lines), (
        "%s: stdout diverged:\n%r\n%r" % (label, old.stdout, new.stdout)
    )
    assert _mask(new.stderr, lines=lines) == _mask(old.stderr, lines=lines), (
        "%s: stderr diverged:\n%r\n%r" % (label, old.stderr, new.stderr)
    )
    assert new_calls == old_calls, "%s: call log diverged:\n%s---\n%s" % (
        label,
        old_calls,
        new_calls,
    )
    assert new_env == old_env, "%s: nfpm environment diverged:\n%s---\n%s" % (
        label,
        old_env,
        new_env,
    )
    assert new_files == old_files, "%s: artifacts diverged:\n%r\n%r" % (
        label,
        old_files,
        new_files,
    )
    assert new_tmp == old_tmp == [], "%s: a build directory leaked: %r / %r" % (
        label,
        old_tmp,
        new_tmp,
    )


DEB = ("--binary", "dist/cli/rdc-linux-x64", "--version", "1.2.3", "--arch", "amd64")


# --------------------------------------------------------------------------- The control on the control ---------------------------------------------------------------------------


def test_the_scratch_path_is_sealed(tmp_path) -> None:
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    for faked in ("nfpm", "gpg", "find"):
        assert shutil.which(faked, path=sealed) == str(root / "fixture-bin" / faked), faked
    for absent in ("dpkg-deb", "rpmbuild", "createrepo_c", "docker", "gpg2", "git"):
        assert shutil.which(absent, path=sealed) is None, absent
    assert shutil.which("nfpm", path=scratch_bin(root, drop=("nfpm",))) is None
    assert REAL_FIND is not None, "the fake find has nothing to delegate to"


def test_the_absent_tools_are_absent_in_the_env_that_is_actually_driven(tmp_path) -> None:
    """The control ON the control, and it is not the same claim as the one above.

    `shutil.which(path=...)` asks about a STRING. This asks the child process,
    through the very `env=` dict `_run` builds, whether it can reach a real
    `nfpm`, `gpg` or `docker` -- which is the thing that would quietly turn a
    signing test into a real `gpg --import` against a developer's keyring. It
    also proves PATH was REPLACED rather than prepended, by asserting the
    machine's own PATH entries are gone.
    """
    root = fixture(tmp_path)
    proc, _, _ = _run(root, "old", args=("--help",))
    assert proc.returncode == 0

    env = {
        "PATH": scratch_bin(root),
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    assert "/usr/bin" not in env["PATH"].split(os.pathsep), "PATH must be REPLACED"
    for tool in ("docker", "gpg2", "dpkg-deb", "rpmbuild", "bash", "python3"):
        probe = subprocess.run(
            [shutil.which("sh") or "/bin/sh", "-c", "command -v %s" % tool],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert probe.returncode != 0, "%s is REACHABLE in the fixture env: %r" % (
            tool,
            probe.stdout,
        )
    reachable = subprocess.run(
        [shutil.which("sh") or "/bin/sh", "-c", "command -v nfpm"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert reachable.stdout.strip() == str(root / "fixture-bin" / "nfpm"), (
        "the fake must be the only nfpm the child can see"
    )


def test_the_restated_constants_match_constants_sh() -> None:
    """The staleness alarm the module head promises. `constants.sh` is the source
    of truth for what a package is CALLED; a drift here is a mislabelled
    artifact, and nothing else in the tree would notice."""
    text = (ROOT / CONSTANTS_REL).read_text(encoding="utf-8")
    for name, value in (
        ("PKG_NAME", port.PKG_NAME),
        ("PKG_BINARY_NAME", port.PKG_BINARY_NAME),
        ("PKG_MAINTAINER", port.PKG_MAINTAINER),
        ("PKG_DESCRIPTION", port.PKG_DESCRIPTION),
        ("PKG_HOMEPAGE", port.PKG_HOMEPAGE),
        ("PKG_SECTION", port.PKG_SECTION),
        ("PKG_PRIORITY", port.PKG_PRIORITY),
    ):
        expected = 'readonly %s="%s"' % (name, value)
        assert expected in text, "constants.sh no longer says %s; the port is stale" % expected


# --------------------------------------------------------------------------- Argument parsing and validation ---------------------------------------------------------------------------


def test_help_prints_usage_on_stdout_and_exits_zero(tmp_path) -> None:
    root = fixture(tmp_path)
    for flag in ("-h", "--help"):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 0
        assert old_t[0].stderr == ""
        assert old_t[0].stdout.endswith(
            " --binary PATH --version VER --arch ARCH --format FORMAT [--output DIR] [--dry-run]\n"
        )
        _agree(old_t, new_t, flag)


def test_an_unknown_option_refuses_and_names_it(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--nope",))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "\u2717 Unknown option: --nope\n"
    _agree(old_t, new_t, "unknown-option")


def test_every_flag_with_no_value_dies_the_way_set_u_does(tmp_path) -> None:
    root = fixture(tmp_path)
    for flag, line in (
        ("--binary", 40),
        ("--version", 44),
        ("--arch", 48),
        ("--format", 52),
        ("--output", 56),
    ):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 1
        assert old_t[0].stderr == "%s: line %d: $2: unbound variable\n" % (
            str(root / TWIN_REL),
            line,
        )
        _agree(old_t, new_t, flag)


def test_each_missing_required_argument_names_itself_lowercased(tmp_path) -> None:
    """`tr '[:upper:]' '[:lower:]'` on the loop variable, and the FIRST missing
    one wins: the loop exits rather than collecting all four."""
    root = fixture(tmp_path)
    for args, missing in (
        ((), "binary"),
        (("--binary", "x"), "version"),
        (("--binary", "x", "--version", "1"), "arch"),
        (("--binary", "x", "--version", "1", "--arch", "amd64"), "format"),
    ):
        old_t, new_t = run_both(root, args=args)
        assert old_t[0].returncode == 1
        assert old_t[0].stderr == "\u2717 Missing required argument: --%s\n" % missing
        _agree(old_t, new_t, "missing-%s" % missing)


def test_an_invalid_format_refuses_before_the_arch_is_looked_at(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "snap"))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == (
        "\u2717 Invalid format 'snap'. Must be one of: deb, rpm, apk, archlinux\n"
    )
    _agree(old_t, new_t, "bad-format")


def test_an_invalid_arch_refuses(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=(
            "--binary",
            "dist/cli/rdc-linux-x64",
            "--version",
            "1.2.3",
            "--arch",
            "riscv64",
            "--format",
            "deb",
        ),
    )
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == (
        "\u2717 Invalid architecture 'riscv64'. Must be one of: amd64, arm64, x86_64, aarch64\n"
    )
    _agree(old_t, new_t, "bad-arch")


# --------------------------------------------------------------------------- Naming: four conventions, four arch spellings ---------------------------------------------------------------------------


def test_every_format_and_arch_spelling_produces_the_documented_filename(tmp_path) -> None:
    """Eight of the sixteen combinations, through the real script in dry-run, so
    the names are read off the twin rather than off a table this file wrote."""
    root = fixture(tmp_path)
    expected = {
        ("deb", "amd64"): "rediacc-cli_1.2.3_amd64.deb",
        ("deb", "aarch64"): "rediacc-cli_1.2.3_arm64.deb",
        ("rpm", "x86_64"): "rediacc-cli-1.2.3-1.x86_64.rpm",
        ("rpm", "arm64"): "rediacc-cli-1.2.3-1.aarch64.rpm",
        ("apk", "amd64"): "rediacc-cli-1.2.3-r1-amd64.apk",
        ("apk", "aarch64"): "rediacc-cli-1.2.3-r1-arm64.apk",
        ("archlinux", "x86_64"): "rediacc-cli-1.2.3-1-x86_64.pkg.tar.zst",
        ("archlinux", "arm64"): "rediacc-cli-1.2.3-1-aarch64.pkg.tar.zst",
    }
    for (fmt, arch), name in expected.items():
        old_t, new_t = run_both(
            root,
            args=(
                "--binary",
                "dist/cli/rdc-linux-x64",
                "--version",
                "1.2.3",
                "--arch",
                arch,
                "--format",
                fmt,
                "--dry-run",
            ),
        )
        assert old_t[0].returncode == 0, old_t[0].stderr
        assert "\u2192 Building .%s package: %s\n" % (fmt, name) in old_t[0].stderr
        assert "\u2713 [DRY-RUN] Would build %s\n" % name in old_t[0].stderr
        _agree(old_t, new_t, "%s-%s" % (fmt, arch))
        assert port.package_filename(fmt, "1.2.3", port.ARCH_MAP[arch]) == name


def test_a_dry_run_creates_the_output_directory_and_validates_nothing(tmp_path) -> None:
    """DEFECT 5. The binary does not exist and `nfpm` is not installed, and the
    preview reports success anyway -- because both checks are BELOW it."""
    root = fixture(tmp_path, binary=False)
    old_t, new_t = run_both(
        root,
        args=(
            "--binary",
            "no/such/binary",
            "--version",
            "9.9.9",
            "--arch",
            "amd64",
            "--format",
            "deb",
            "--dry-run",
        ),
        drop=("nfpm",),
    )
    assert old_t[0].returncode == 0
    assert "\u2713 [DRY-RUN] Would build rediacc-cli_9.9.9_amd64.deb\n" in old_t[0].stderr
    assert "dist/packages/" in old_t[3], "the output directory is still created"
    assert old_t[1] == "", "no nfpm, no gpg, nothing"
    _agree(old_t, new_t, "dry-run")


def test_output_directory_is_honoured_relative_and_absolute(tmp_path) -> None:
    """`--output` was parsed by both sides and driven by NEITHER. The flag decides
    where the artifact lands, so a port that dropped it would have been green."""
    root = fixture(tmp_path)
    for spelling in ("out", str(root / "out")):
        old_t, new_t = run_both(root, args=(*DEB, "--format", "deb", "--output", spelling))
        assert old_t[0].returncode == 0, old_t[0].stderr
        assert "✓   Output: %s/rediacc-cli_1.2.3_amd64.deb\n" % spelling in old_t[0].stderr
        assert old_t[3] == {
            "out/": "<dir>",
            "out/rediacc-cli_1.2.3_amd64.deb": "NFPM PACKAGE PAYLOAD\n",
        }, old_t[3]
        assert "dist/packages/" not in old_t[3], "the default must NOT also be created"
        _agree(old_t, new_t, "output-%s" % spelling)


def test_an_output_directory_blocked_by_a_file_fails_the_way_mkdir_does(tmp_path) -> None:
    """`mkdir -p` under `set -e`, at BOTH of its call sites.

    The twin runs the real `mkdir`; a port using `Path.mkdir` exits 1 as well but
    prints a PYTHON TRACEBACK where the twin prints one `mkdir:` line, which is
    the difference between a diagnosable release failure and a scary one. Driven
    on the dry-run site (`:148`) too, because that one runs BEFORE any validation
    and would otherwise never be reached in this file.
    """
    root = fixture(tmp_path)
    for extra in ((), ("--dry-run",)):
        _reset(root)
        (root / "out").write_text("in the way\n", encoding="utf-8")
        old_t, new_t = run_both(root, args=(*DEB, "--format", "deb", "--output", "out", *extra))
        assert old_t[0].returncode == 1, old_t[0].stderr
        assert "mkdir:" in old_t[0].stderr, old_t[0].stderr
        assert "Traceback" not in new_t[0].stderr, new_t[0].stderr
        _agree(old_t, new_t, "mkdir-blocked%s" % ("-dry" if extra else ""))
    (root / "out").unlink()


def test_a_binary_with_no_directory_part_still_becomes_absolute(tmp_path) -> None:
    """`$(dirname "rdc")` is `.`, not the empty string, and `$(cd . && pwd)` is
    the CWD. `os.path.dirname` returns `""` there, which `os.path.abspath` would
    also resolve to the CWD -- but only because the port spells the `or "."`
    out. Untested, this is a one-character difference from a path of `/rdc`."""
    root = fixture(tmp_path)
    (root / "rdc").write_text("BINARY\n", encoding="utf-8")
    old_t, new_t = run_both(
        root,
        args=("--binary", "rdc", "--version", "1.2.3", "--arch", "amd64", "--format", "deb"),
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    seen = dict(line.split("=", 1) for line in old_t[2].splitlines())
    assert seen["BINARY_PATH"] == str(root / "rdc")
    _agree(old_t, new_t, "bare-binary-name")


# --------------------------------------------------------------------------- The unsigned happy path ---------------------------------------------------------------------------


def test_an_unsigned_deb_builds_renames_and_warns(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert old_t[1].splitlines() == [
        "FAKEBIN nfpm\tpackage\t--config\t%s\t--packager\tdeb\t--target\t<BUILD_DIR>/"
        % (root / ".ci/config/nfpm.yaml"),
        (
            "FAKEBIN find\t<BUILD_DIR>\t-maxdepth\t1\t-type\tf\t(\t-name\t*.deb\t-o\t"
            "-name\t*.rpm\t-o\t-name\t*.apk\t-o\t-name\t*.pkg.tar.zst\t)"
        ),
    ]
    assert old_t[3] == {
        "dist/packages/": "<dir>",
        "dist/packages/rediacc-cli_1.2.3_amd64.deb": "NFPM PACKAGE PAYLOAD\n",
    }, "nfpm's own name must be renamed to the convention"
    assert "\u2713 Package built: rediacc-cli_1.2.3_amd64.deb (0KB)\n" in old_t[0].stderr
    assert "\u26a0 RELEASE_GPG_PRIVATE_KEY not set, skipping deb signing\n" in old_t[0].stderr
    _agree(old_t, new_t, "unsigned-deb")


def test_the_environment_nfpm_receives_is_the_whole_package_definition(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "rpm", "--arch", "aarch64"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    seen = dict(line.split("=", 1) for line in old_t[2].splitlines())
    assert seen["PKG_NAME"] == "rediacc-cli"
    assert seen["PKG_BINARY_NAME"] == "rdc"
    assert seen["PKG_MAINTAINER"] == "Rediacc <info@rediacc.com>"
    assert seen["PKG_DESCRIPTION"] == "Rediacc CLI - automation and scripting tool"
    assert seen["PKG_HOMEPAGE"] == "https://www.rediacc.com"
    assert seen["PKG_SECTION"] == "utils"
    assert seen["PKG_PRIORITY"] == "optional"
    assert seen["VERSION"] == "1.2.3"
    assert seen["NFPM_ARCH"] == "arm64", "GOARCH, not the rpm spelling"
    assert seen["BINARY_PATH"] == str(root / "dist/cli/rdc-linux-x64"), "must be ABSOLUTE"
    assert seen["NFPM_RPM_KEY_FILE"] == "<unset>"
    assert seen["CI_OS"] in ("linux", "macos", "windows", "unknown")
    _agree(old_t, new_t, "nfpm-env")


def test_a_relative_binary_becomes_an_absolute_binary_path(tmp_path) -> None:
    """`$(cd "$(dirname "$BINARY")" && pwd)/$(basename "$BINARY")` -- a command
    substitution nested two levels deep, whose `cd` failing would be a silent
    death. It cannot fail here, and the ABSOLUTE result is what nfpm needs."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "apk"))
    seen = dict(line.split("=", 1) for line in old_t[2].splitlines())
    assert seen["BINARY_PATH"].startswith("/")
    assert seen["BINARY_PATH"] == str(root / "dist/cli/rdc-linux-x64")
    _agree(old_t, new_t, "abs-binary-path")


def test_apk_and_archlinux_each_say_why_they_are_unsigned(tmp_path) -> None:
    """Silence is what let two of four formats ship unsigned unnoticed."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "apk"))
    assert "APK_RSA_PRIVATE_KEY not set, skipping APK signing" in old_t[0].stderr
    assert "declared-unsigned" in old_t[0].stderr
    _agree(old_t, new_t, "apk-unsigned")
    old_t, new_t = run_both(root, args=(*DEB, "--format", "archlinux"))
    assert "archlinux packages are UNSIGNED: nfpm cannot sign them" in old_t[0].stderr
    assert "would break pacman -U" in old_t[0].stderr
    _agree(old_t, new_t, "archlinux-unsigned")


def test_release_signing_required_turns_an_empty_secret_into_a_refusal(tmp_path) -> None:
    """The 2026-09-05 incident: a deleted org secret resolved to "", which was
    indistinguishable from "no signing wanted", and the build shipped unsigned
    and green."""
    root = fixture(tmp_path)
    # NOT `..._amd64.%s`: rpm's convention is `-1.x86_64.rpm`, and writing the deb spelling for both formats is how this assertion previously came to
    # carry an `or fmt == "rpm"` escape hatch -- which made it ALWAYS TRUE for
    # rpm and therefore checked nothing on the arm that needed it most.
    built = {
        "deb": "dist/packages/rediacc-cli_1.2.3_amd64.deb",
        "rpm": "dist/packages/rediacc-cli-1.2.3-1.x86_64.rpm",
    }
    for fmt in ("deb", "rpm"):
        old_t, new_t = run_both(
            root,
            args=(*DEB, "--format", fmt),
            env_overrides={"RELEASE_SIGNING_REQUIRED": "1", "RELEASE_GPG_PRIVATE_KEY": ""},
        )
        assert old_t[0].returncode == 1
        assert (
            "\u2717 RELEASE_SIGNING_REQUIRED=1 but RELEASE_GPG_PRIVATE_KEY is empty or "
            "unset -- refusing to ship an UNSIGNED %s." % fmt in old_t[0].stderr
        )
        assert old_t[3] == {
            "dist/packages/": "<dir>",
            built[fmt]: "NFPM PACKAGE PAYLOAD\n",
        }, (
            "the refusal is the LAST thing the script does, so the unsigned "
            "package is already on disk when it fires: %r" % old_t[3]
        )
        _agree(old_t, new_t, "required-%s" % fmt)


def test_release_signing_required_does_not_touch_apk_or_archlinux(tmp_path) -> None:
    """It blocked a real release once (run 34003316362) for a credential nobody
    has. Both formats stay warnings under the same flag."""
    root = fixture(tmp_path)
    for fmt in ("apk", "archlinux"):
        old_t, new_t = run_both(
            root,
            args=(*DEB, "--format", fmt),
            env_overrides={"RELEASE_SIGNING_REQUIRED": "1"},
        )
        assert old_t[0].returncode == 0, old_t[0].stderr
        assert "refusing to ship an UNSIGNED" not in old_t[0].stderr
        _agree(old_t, new_t, "required-noop-%s" % fmt)


# --------------------------------------------------------------------------- Failure paths around nfpm ---------------------------------------------------------------------------


def test_a_missing_nfpm_is_declared_not_a_stack_trace(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"), drop=("nfpm",))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith("\u2717 Required command 'nfpm' is not available\n")
    _agree(old_t, new_t, "no-nfpm")


def test_a_missing_binary_is_declared(tmp_path) -> None:
    root = fixture(tmp_path, binary=False)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith(
        "\u2717 Required file 'dist/cli/rdc-linux-x64' does not exist\n"
    )
    _agree(old_t, new_t, "no-binary")


def test_nfpm_producing_nothing_is_a_refusal_not_an_empty_package(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=(*DEB, "--format", "deb"), env_overrides={"FAKE_NFPM_WRITES": "0"}
    )
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith("\u2717 nfpm produced no output file\n")
    assert old_t[3] == {"dist/packages/": "<dir>"}
    _agree(old_t, new_t, "nfpm-silent")


def test_a_failing_nfpm_propagates_its_own_status(tmp_path) -> None:
    root = fixture(tmp_path)
    for code in ("1", "5"):
        old_t, new_t = run_both(
            root,
            args=(*DEB, "--format", "deb"),
            env_overrides={"FAKE_NFPM_RC": code, "FAKE_NFPM_WRITES": "0"},
        )
        assert old_t[0].returncode == int(code)
        _agree(old_t, new_t, "nfpm-rc-%s" % code)


def test_defect_3_a_failing_find_dies_silently(tmp_path) -> None:
    """`BUILT_PKG=$(find ... | head -1)` at `:277-279`, the same
    assignment-of-a-pipeline shape as DEFECT 2 and just as live.

    `find` exits 1 whenever it cannot read something it was told to walk, `head`
    exits 0, so `pipefail` hands the assignment find's 1 and `set -e` ends the
    build. Nothing is printed: not `log_error`, not "nfpm produced no output
    file". The package nfpm just wrote is left in a temp directory the EXIT trap
    then deletes, and the release engineer gets a bare exit 1.
    """
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=(*DEB, "--format", "deb"), env_overrides={"FAKE_FIND_RC": "1"}
    )
    assert old_t[0].returncode == 1
    assert old_t[0].stdout == ""
    assert old_t[0].stderr.endswith(
        "✓   Output: %s/dist/packages/rediacc-cli_1.2.3_amd64.deb\n" % root
    ), "the last thing said is routine progress: %r" % old_t[0].stderr
    assert "nfpm produced no output file" not in old_t[0].stderr
    assert "Package built" not in old_t[0].stderr
    assert old_t[3] == {"dist/packages/": "<dir>"}, "nothing was copied out"
    _agree(old_t, new_t, "defect-3")


def test_find_reporting_success_with_no_output_is_the_other_branch(tmp_path) -> None:
    """The refusal DEFECT 3 hides. Same missing package, `find` exits 0, and this
    time the script says so -- which is what makes the silent arm worth naming."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=(*DEB, "--format", "deb"),
        env_overrides={"FAKE_NFPM_WRITES": "0", "FAKE_FIND_RC": "0"},
    )
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith("✗ nfpm produced no output file\n")
    _agree(old_t, new_t, "find-empty-but-ok")


def test_the_build_directory_never_survives_any_path(tmp_path) -> None:
    """`trap cleanup EXIT`. A leaked temp directory is invisible on every stream,
    so `_agree` asserts the fixture temp root is empty after BOTH sides on every
    case; this one drives the refusal paths explicitly."""
    root = fixture(tmp_path)
    for overrides in (
        {"FAKE_NFPM_RC": "5", "FAKE_NFPM_WRITES": "0"},
        {"FAKE_NFPM_WRITES": "0"},
        {"RELEASE_GPG_PRIVATE_KEY": "FPR=%s" % OTHER_FPR},
    ):
        old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"), env_overrides=overrides)
        assert old_t[4] == [], old_t[4]
        assert new_t[4] == [], new_t[4]


# --------------------------------------------------------------------------- Signing ---------------------------------------------------------------------------


def _signed(fpr: str = GOOD_FPR, **extra) -> dict[str, str | None]:
    env: dict[str, str | None] = {"RELEASE_GPG_PRIVATE_KEY": "FPR=%s" % fpr}
    env.update(extra)
    return env


def test_a_matching_key_signs_and_says_which_fingerprint_matched(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"), env_overrides=_signed())
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "\u2713 Setting up GPG signing for deb...\n" in old_t[0].stderr
    assert "\u2713 Signing key armor was already canonical\n" in old_t[0].stderr
    assert (
        "\u2713 Signing key matches the published public key (%s)\n" % GOOD_FPR in old_t[0].stderr
    )
    assert "\u2713 Package signed with DEB key\n" in old_t[0].stderr
    calls = old_t[1].splitlines()
    assert calls[0] == "FAKEBIN canonicalise-gpg-key.sh\t<BUILD_DIR>/signing-key.gpg\t"
    assert calls[1].startswith("FAKEBIN gpg\t--show-keys\t--with-colons\t--with-fingerprint\t")
    assert calls[1].endswith(str(root / ".ci/keys/gpg-public.asc"))
    assert calls[2].endswith("<BUILD_DIR>/signing-key.gpg")
    seen = dict(line.split("=", 1) for line in old_t[2].splitlines())
    assert seen["NFPM_DEB_KEY_FILE"] == "<BUILD_DIR>/signing-key.gpg"
    assert seen["NFPM_RPM_KEY_FILE"] == "<unset>"
    _agree(old_t, new_t, "signed-deb")


def test_rpm_gets_the_rpm_key_variable_and_deb_gets_the_deb_one(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "rpm"), env_overrides=_signed())
    seen = dict(line.split("=", 1) for line in old_t[2].splitlines())
    assert seen["NFPM_RPM_KEY_FILE"] == "<BUILD_DIR>/signing-key.gpg"
    assert seen["NFPM_DEB_KEY_FILE"] == "<unset>"
    assert "\u2713 Package signed with RPM key\n" in old_t[0].stderr
    _agree(old_t, new_t, "signed-rpm")


def test_a_mismatched_key_refuses_and_names_both_fingerprints(tmp_path) -> None:
    """dnf verifies every rpm against the gpg.key the repository publishes, so a
    package signed with any other key installs nowhere."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=(*DEB, "--format", "deb"), env_overrides=_signed(fpr=OTHER_FPR)
    )
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith(
        "\u2717 signing key %s is not the published public key %s (%s); a deb signed "
        "with it would fail verification on every client\n"
        % (OTHER_FPR, GOOD_FPR, root / ".ci/keys/gpg-public.asc")
    )
    assert old_t[3] == {}, "nothing may be written after the refusal"
    _agree(old_t, new_t, "key-mismatch")


def test_a_key_with_no_fingerprint_row_refuses_as_unreadable(tmp_path) -> None:
    """The ONE way `<unreadable>` can actually print: gpg exits 0 and emits no
    `fpr` row. When gpg exits NON-zero the script dies before reaching it -- see
    the next test."""
    root = fixture(tmp_path, public_key="NOFPR\n")
    old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"), env_overrides=_signed())
    assert old_t[0].returncode == 1
    assert "signing key %s is not the published public key <unreadable>" % GOOD_FPR in (
        old_t[0].stderr
    )
    _agree(old_t, new_t, "no-fpr-row")


def test_defect_2_an_unreadable_published_key_dies_silently(tmp_path) -> None:
    """`want_fpr=$(gpg ... | awk ...)` under `pipefail`: gpg's exit 2 becomes the
    assignment's status and `set -e` ends the script with NOTHING on either
    stream. The `<unreadable>` fallback written for exactly this case is
    unreachable, and a release engineer sees a bare exit 2."""
    root = fixture(tmp_path, public_key="BADKEY\n")
    old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"), env_overrides=_signed())
    assert old_t[0].returncode == 2, "gpg's own status, not a flattened 1"
    assert old_t[0].stdout == ""
    assert old_t[0].stderr.endswith("\u2713 Signing key armor was already canonical\n"), (
        "the last thing said is a TICK; the refusal never prints"
    )
    assert "<unreadable>" not in old_t[0].stderr
    assert "is not the published public key" not in old_t[0].stderr
    _agree(old_t, new_t, "defect-2")


def test_defect_2_also_fires_on_an_unreadable_private_key(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=(*DEB, "--format", "deb"),
        env_overrides=_signed(fpr="") | {"RELEASE_GPG_PRIVATE_KEY": "BADKEY"},
    )
    assert old_t[0].returncode == 2
    assert "is not the published public key" not in old_t[0].stderr
    _agree(old_t, new_t, "defect-2-private")


def test_defect_1_no_published_key_file_means_no_check_at_all(tmp_path) -> None:
    """`if [[ -f "$PUBLIC_KEY_FILE" ]]` with no `else`. The build signs with an
    unverified key, exits 0, and never mentions that the comparison did not
    happen."""
    root = fixture(tmp_path, public_key=None)
    old_t, new_t = run_both(
        root, args=(*DEB, "--format", "deb"), env_overrides=_signed(fpr=OTHER_FPR)
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "Signing key matches the published public key" not in old_t[0].stderr
    assert "is not the published public key" not in old_t[0].stderr
    assert "\u2713 Package signed with DEB key\n" in old_t[0].stderr
    assert old_t[1].count("FAKEBIN gpg") == 0, "gpg is never even asked"
    _agree(old_t, new_t, "defect-1")


def test_the_public_key_file_can_be_overridden(tmp_path) -> None:
    root = fixture(tmp_path)
    other = root / "throwaway.asc"
    other.write_text("FPR=%s\n" % OTHER_FPR, encoding="utf-8")
    old_t, new_t = run_both(
        root,
        args=(*DEB, "--format", "deb"),
        env_overrides=_signed(fpr=OTHER_FPR) | {"RELEASE_GPG_PUBLIC_KEY_FILE": str(other)},
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert (
        "\u2713 Signing key matches the published public key (%s)\n" % OTHER_FPR in old_t[0].stderr
    )
    _agree(old_t, new_t, "public-key-override")


def test_a_repaired_key_is_loud_and_a_failed_canonicalise_is_a_warning(tmp_path) -> None:
    """Exit 10 is a SIGNAL, not a failure: a bare call under `set -e` aborted
    every build whose key needed repairing, which is the production case."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=(*DEB, "--format", "deb"), env_overrides=_signed(FAKE_CANON_RC="10")
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "\u26a0 SIGNING KEY WAS REPAIRED:" in old_t[0].stderr
    assert "re-join the two Bitwarden halves WITH a newline" in old_t[0].stderr
    _agree(old_t, new_t, "canon-repaired")

    old_t, new_t = run_both(
        root, args=(*DEB, "--format", "deb"), env_overrides=_signed(FAKE_CANON_RC="3")
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert (
        "\u26a0 could not canonicalise the signing key; handing nfpm the key as stored\n"
        in old_t[0].stderr
    )
    _agree(old_t, new_t, "canon-failed")


def test_a_passphrase_is_masked_on_stdout_and_exported_to_both_packagers(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=(*DEB, "--format", "deb"),
        env_overrides=_signed() | {"RELEASE_GPG_PASSPHRASE": FIXTURE_PHRASE},
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert old_t[0].stdout == "::add-mask::%s\n" % FIXTURE_PHRASE
    seen = dict(line.split("=", 1) for line in old_t[2].splitlines())
    assert seen["NFPM_RPM_PASSPHRASE"] == FIXTURE_PHRASE
    assert seen["NFPM_DEB_PASSPHRASE"] == FIXTURE_PHRASE
    assert old_t[1].splitlines()[0].endswith("\t%s" % FIXTURE_PHRASE), (
        "the passphrase is passed to the canonicaliser as argv"
    )
    _agree(old_t, new_t, "passphrase")


def test_no_passphrase_means_no_mask_line_and_no_passphrase_variables(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"), env_overrides=_signed())
    assert old_t[0].stdout == ""
    seen = dict(line.split("=", 1) for line in old_t[2].splitlines())
    assert seen["NFPM_RPM_PASSPHRASE"] == UNSET
    _agree(old_t, new_t, "no-passphrase")


def test_an_apk_rsa_key_is_the_other_signing_arm(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=(*DEB, "--format", "apk"),
        env_overrides={"APK_RSA_PRIVATE_KEY": "-----BEGIN RSA PRIVATE KEY-----"},
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "\u2713 Setting up RSA signing for APK...\n" in old_t[0].stderr
    seen = dict(line.split("=", 1) for line in old_t[2].splitlines())
    assert seen["NFPM_APK_KEY_FILE"] == "<BUILD_DIR>/apk-signing-key.rsa"
    assert "\u2713 Package signed with APK key\n" in old_t[0].stderr, (
        "DEFECT 6: an RSA key reported as an 'APK key', and no signature was checked"
    )
    assert old_t[1].count("FAKEBIN gpg") == 0
    _agree(old_t, new_t, "apk-rsa")


def test_a_gpg_key_is_ignored_for_apk_and_an_rsa_key_for_deb(tmp_path) -> None:
    """The `elif` chain, both directions. A GPG key present while building apk
    takes NEITHER arm, so apk still reports itself unsigned."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*DEB, "--format", "apk"), env_overrides=_signed())
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "APK_RSA_PRIVATE_KEY not set, skipping APK signing" in old_t[0].stderr
    _agree(old_t, new_t, "gpg-key-for-apk")

    old_t, new_t = run_both(
        root,
        args=(*DEB, "--format", "deb"),
        env_overrides={"APK_RSA_PRIVATE_KEY": "rsa"},
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "RELEASE_GPG_PRIVATE_KEY not set, skipping deb signing" in old_t[0].stderr
    _agree(old_t, new_t, "rsa-key-for-deb")


def test_a_key_that_is_exactly_dash_n_writes_a_zero_byte_key_file(tmp_path) -> None:
    """`echo "$RELEASE_GPG_PRIVATE_KEY" >"$GPG_KEY_FILE"` at `:187`.

    bash's BUILTIN `echo` parses a leading `-n`/`-e`/`-E` as OPTIONS, so a secret
    whose entire value is `-n` writes an EMPTY key file and the build then walks
    into the unreadable-key path with no hint of why. Driven: `v=-n; echo "$v"
    >f` leaves `wc -c` = 0 on bash 5.3.9.

    Real armor is NOT affected -- `-----BEGIN PGP PRIVATE KEY BLOCK-----` is not
    an option string, so the leading dashes are harmless -- and the other half of
    this test pins that, because "a key starts with dashes" is exactly the wrong
    lesson to draw from the first half.
    """
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=(*DEB, "--format", "deb"),
        env_overrides=_signed() | {"RELEASE_GPG_PRIVATE_KEY": "-n"},
    )
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith(
        "✗ signing key <unreadable> is not the published public key %s (%s); a deb "
        "signed with it would fail verification on every client\n"
        % (GOOD_FPR, root / ".ci/keys/gpg-public.asc")
    ), old_t[0].stderr
    _agree(old_t, new_t, "key-is-dash-n")

    # And the case that looks like it should behave the same and does not.
    old_t, new_t = run_both(
        root,
        args=(*DEB, "--format", "deb"),
        env_overrides=_signed() | {"RELEASE_GPG_PRIVATE_KEY": "-----BEGIN\nFPR=%s" % GOOD_FPR},
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "✓ Signing key matches the published public key (%s)\n" % GOOD_FPR in (old_t[0].stderr)
    _agree(old_t, new_t, "key-starts-with-dashes")


def test_the_logger_escape_divergence_is_pinned_not_accidental(tmp_path) -> None:
    """THE ONE PLACE THE TWO SIDES DELIBERATELY DISAGREE, asserted as a
    DISAGREEMENT so nobody later reads a green suite as proof they match.

    `common.sh:35` logs with `echo -e`, which INTERPRETS backslash escapes in the
    message: `--binary 'a\\tb'` makes the twin print a real tab. `rediacc_ci.log`
    formats the message as data, and `log.py`'s own docstring records that as a
    bug being dropped rather than a decision being made, pinned by
    `test_log.py`. Changing it here would mean forking the one logger the whole
    campaign shares, so it is DOCUMENTED instead -- and documented means
    executed, not commented.

    Unreachable in production: this script's only caller passes a fixed binary
    path and a version read off a git tag. That is why it is a note and not a
    defect.
    """
    root = fixture(tmp_path)
    args = (
        "--binary",
        "a\\tb",
        "--version",
        "1.2.3",
        "--arch",
        "amd64",
        "--format",
        "deb",
        "--dry-run",
    )
    old_t, new_t = run_both(root, args=args)
    assert old_t[0].returncode == new_t[0].returncode == 0
    assert "  Binary: a\tb\n" in old_t[0].stderr, "the twin interprets \\t"
    assert "  Binary: a\\tb\n" in new_t[0].stderr, "the port does not"
    assert old_t[0].stderr != new_t[0].stderr

    # Everything OTHER than that line still has to match, or this test would be excusing far more divergence than it names.
    def without_binary_line(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if "Binary:" not in ln]

    assert without_binary_line(new_t[0].stderr) == without_binary_line(old_t[0].stderr)
    assert new_t[0].stdout == old_t[0].stdout
    assert new_t[3] == old_t[3]


def test_a_missing_gpg_is_declared_before_the_check_that_needs_it(tmp_path) -> None:
    """`require_cmd gpg` exists precisely because the check below runs gpg inside
    a command substitution, where a missing binary would exit 127 with no
    message and the signing check would silently not happen."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=(*DEB, "--format", "deb"), env_overrides=_signed(), drop=("gpg",)
    )
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith("\u2717 Required command 'gpg' is not available\n")
    _agree(old_t, new_t, "no-gpg")


# --------------------------------------------------------------------------- The proof the differential can fail ---------------------------------------------------------------------------


def test_a_planted_defect_is_caught(tmp_path) -> None:
    """Three plants, three different assertions."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")

    # 1. The arch translation reversed: identical streams, wrong package.
    root = fixture(
        tmp_path / "a",
        port_source=source.replace(
            '"amd64": ("amd64", "x86_64", "x86_64", "amd64"),',
            '"amd64": ("x86_64", "x86_64", "x86_64", "amd64"),',
        ),
    )
    old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"))
    assert old_t[0].returncode == new_t[0].returncode == 0
    assert old_t[0].stdout == new_t[0].stdout
    assert new_t[2] != old_t[2], "the nfpm environment must catch it"

    # 2. DEFECT 2 "fixed": the port refuses politely where the twin dies bare.
    root = fixture(
        tmp_path / "b",
        port_source=source.replace(
            "        raise Refusal(proc.returncode)",
            '        raise Refusal(1, "\u2717 could not read the key")',
        ),
        public_key="BADKEY\n",
    )
    old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"), env_overrides=_signed())
    assert old_t[0].returncode == 2
    assert new_t[0].returncode == 1, "the plant must change the verdict"

    # 3. The EXIT trap dropped: no stream difference at all, a leaked directory.
    root = fixture(
        tmp_path / "c",
        port_source=source.replace(
            "        shutil.rmtree(build_dir, ignore_errors=True)", "        pass"
        ),
    )
    old_t, new_t = run_both(root, args=(*DEB, "--format", "deb"))
    assert old_t[0].stderr == new_t[0].stderr
    assert old_t[4] == []
    assert new_t[4] != [], "the leak must be visible"


# --------------------------------------------------------------------------- Unit-level ---------------------------------------------------------------------------


def test_package_filename_covers_all_four_conventions() -> None:
    amd = port.ARCH_MAP["amd64"]
    assert port.package_filename("deb", "1.0", amd) == "rediacc-cli_1.0_amd64.deb"
    assert port.package_filename("rpm", "1.0", amd) == "rediacc-cli-1.0-1.x86_64.rpm"
    assert port.package_filename("apk", "1.0", amd) == "rediacc-cli-1.0-r1-amd64.apk"
    assert port.package_filename("archlinux", "1.0", amd) == "rediacc-cli-1.0-1-x86_64.pkg.tar.zst"


def test_the_arch_map_accepts_every_spelling_the_twin_does() -> None:
    assert set(port.ARCH_MAP) == {"amd64", "x86_64", "arm64", "aarch64"}
    assert port.ARCH_MAP["amd64"] == port.ARCH_MAP["x86_64"]
    assert port.ARCH_MAP["arm64"] == port.ARCH_MAP["aarch64"]


def test_the_find_predicates_are_the_twins_four_patterns() -> None:
    assert port._name_predicates() == [
        "-name",
        "*.deb",
        "-o",
        "-name",
        "*.rpm",
        "-o",
        "-name",
        "*.apk",
        "-o",
        "-name",
        "*.pkg.tar.zst",
    ]


def test_console_root_is_this_checkout() -> None:
    assert port.console_root() == ROOT
    assert port.script_dir(ROOT) == ROOT / ".ci" / "scripts" / "build"


def test_the_module_reads_env_at_the_call_site() -> None:
    """The env-registry alias trap, confirmed in waves 15, 18, 45 and 46."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    for name in (
        "RELEASE_GPG_PRIVATE_KEY",
        "RELEASE_GPG_PASSPHRASE",
        "RELEASE_GPG_PUBLIC_KEY_FILE",
        "APK_RSA_PRIVATE_KEY",
        "RELEASE_SIGNING_REQUIRED",
    ):
        assert 'os.environ.get("%s"' % name in source, name
    assert "dict(os.environ)" not in source
    assert "environ.copy()" not in source
