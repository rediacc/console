"""Differential: `.ci/rediacc_ci/build/build_pkg_repo.py` against its twin `.ci/scripts/build/build-pkg-repo.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new code is correct", it is "the new code says what the old code said". Only running BOTH, on the same fixture, in the same run, can support that. This script's product is a published package repository, so "what it said" includes the FILES.

WHAT IS COMPARED, per case:

  1. the exit code -- and it is not always 0 or 1 here: three of the twin's
     failure modes exit 2, inherited from `tar` and from `gpg`;
  2. stdout and stderr, SEPARATELY. stdout carries exactly two things in this
     script (`--help`'s usage line and `::add-mask::`), and a port that put a
     log line there would be invisible to a merged comparison;
  3. every output FILE, by path AND by bytes. A port that logged identically and
     wrote a different `Release` would pass 1 and 2 and ship a repository apt
     rejects;
  4. the CALL LOG: every invocation of gpg, dpkg-scanpackages, createrepo_c and
     docker, with full argv, in order.

TWO NORMALISATIONS, AND WHY EACH IS NOT A LOOPHOLE.

  `Packages.gz` IS NOT BYTE-STABLE ACROSS TWO RUNS OF THE SAME PROGRAM. `gzip
  -9c FILE` embeds FILE's mtime in the member header, and the two sides write
  their `Packages` seconds apart, so the header bytes differ for a reason that
  has nothing to do with the port -- and the md5/sha256 rows in `Release` that
  cover it differ with them. `_artifacts` therefore compares `*.gz` by its
  DECOMPRESSED content and masks the digest of `.gz` rows in `Release` and
  `InRelease`. The `Packages` files themselves, the `.gz` SIZES, and every
  digest of a non-`.gz` file are still compared byte for byte, so the
  normalisation cannot hide a wrong index.

  `SOURCE_DATE_EPOCH` IS SET IN EVERY BUILDING CASE, so `Date:` in `Release` is
  pinned rather than masked. One case deliberately omits it and masks the line,
  which is what proves the fallback path (`date -Ru`) is reached at all.

THE DESTRUCTIVE TOOLS ARE FAKES, AND THE PATH IS REPLACED, NEVER PREPENDED.
`gpg`, `dpkg-scanpackages`, `createrepo_c` and `docker` are recording stubs. `_binder` builds the ENTIRE PATH from a named list, then ASSERTS that the real `gpg` and the real `docker` are NOT reachable through it: a prepended PATH that silently fell through to the real docker would try to pull `alpine:latest`, and a case built to prove "docker is absent" would prove nothing.

THE FIXTURE HOLDS COPIES OF BOTH SUBJECTS, because each derives the console root
from its own location (`BASH_SOURCE`/`__file__`, three directories up). Driving
the TRACKED files would point them at the real repository's `.ci/keys/`.
"""

import gzip
import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.build import build_pkg_repo

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "build" / "build-pkg-repo.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
TOOLCHAIN = ROOT / ".devcontainer" / "toolchain.env"
PORT = ROOT / ".ci" / "rediacc_ci" / "build" / "build_pkg_repo.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/build/build-pkg-repo.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/build/build_pkg_repo.py")

# A fixed epoch so `Date:` in Release is a constant rather than a mask.
EPOCH = "1700000000"
EPOCH_DATE = "Tue, 14 Nov 2023 22:13:20 +0000"

# Everything both subjects need once PATH is rebuilt from scratch. NAMED, not derived: a PATH built by copying "everything except X" is a PATH nobody can state, and the first tool it forgot would look like a divergence in the subject rather than a hole in the harness. `find` and `grep` are listed explicitly because an interactive shell in this environment shadows both with
# FUNCTIONS, so `command -v` from a login shell is not what a subprocess sees.
NEEDED = (
    "bash",
    "sh",
    "python3",
    "env",
    "uname",
    "dirname",
    "basename",
    "cat",
    "mkdir",
    "rm",
    "cp",
    "find",
    "grep",
    "awk",
    "sed",
    "sort",
    "head",
    "cut",
    "wc",
    "tar",
    "gzip",
    "date",
    "md5sum",
    "sha256sum",
    "mktemp",
    "tr",
)

# The tools that must NEVER resolve to the real binary inside a fixture run. Asserted, not assumed: this is the control on the control.
FAKED = ("gpg", "dpkg-scanpackages", "createrepo_c", "docker")

# `<path>: line <n>: ` -- the prefix bash puts on its own diagnostics, and the shape the port reproduces with its own path. Masked ONLY in the tests that are about that divergence.
LINE_PREFIX = re.compile(r"^[^\n]*: line \d+: ", re.MULTILINE)

# A `mktemp -d` / `tempfile.mkdtemp(prefix="tmp.")` path. Observable in exactly
# one message, the vacuity refusal, which interpolates the APT pool directory.
TEMP_PATH = re.compile(r"/[^ \n]*/tmp\.[A-Za-z0-9_]+")

# A digest row in Release covering a `.gz`, whose bytes carry gzip's mtime.
GZ_DIGEST_ROW = re.compile(r"^ [0-9a-f]{32,64} (\d+) (\S+\.gz)$", re.MULTILINE)

# The RFC-2822 `Date:` line, masked only in the case that omits SOURCE_DATE_EPOCH.
DATE_LINE = re.compile(r"^Date: .*$", re.MULTILINE)

FAKE_GPG = """#!/usr/bin/env bash
echo "call: gpg $*" >>"$CALLLOG"
if [[ " $* " == *" --import "* ]]; then cat >/dev/null; exit ${GPG_IMPORT_RC:-0}; fi
if [[ " $* " == *" --show-keys "* ]]; then
  [[ -n "${GPG_SHOW_KEYS_RC:-}" ]] && exit "$GPG_SHOW_KEYS_RC"
  echo "fpr:::::::::${WANT_FPR:-AAAABBBBCCCCDDDD}:"; exit 0
fi
if [[ " $* " == *" --list-keys "* ]]; then
  if [[ " $* " == *" --with-fingerprint "* ]]; then
    echo "fpr:::::::::${HAVE_FPR:-AAAABBBBCCCCDDDD}:"
  else
    [[ -n "${GPG_NO_KEYS:-}" ]] && exit 0
    echo "pub:u:255:22:DEADBEEF:1:::u:::scESC::::::23::0:"
  fi
  exit 0
fi
if [[ " $* " == *" --detach-sign "* || " $* " == *" --clearsign "* ]]; then
  out=""; prev=""
  for a in "$@"; do [[ "$prev" == "--output" ]] && out="$a"; prev="$a"; done
  [[ -n "$out" ]] && echo "SIGNATURE" >"$out"
  exit 0
fi
if [[ " $* " == *" --export "* ]]; then echo "EXPORTED-PUBKEY"; exit 0; fi
exit 0
"""

FAKE_SCANPACKAGES = """#!/usr/bin/env bash
echo "call: dpkg-scanpackages $*" >>"$CALLLOG"
echo "cwd-is-pool: $([[ -d pool ]] && echo yes || echo no)" >>"$CALLLOG"
echo "Package: rediacc-cli"
echo "Architecture: ${2:-any}"
echo ""
"""

FAKE_CREATEREPO = """#!/usr/bin/env bash
echo "call: createrepo_c $*" >>"$CALLLOG"
mkdir -p "$1/repodata"
echo "<repomd/>" >"$1/repodata/repomd.xml"
"""

# The two docker images, faked to write what the real ones write. The apk arm emits a real gzipped tar so the twin's `tar xzf ... -O APKINDEX` succeeds; that is what makes the docker-ABSENT case (DEFECT 1) a contrast rather than the only behaviour the harness can produce.
FAKE_DOCKER = """#!/usr/bin/env bash
echo "call: docker $*" >>"$CALLLOG"
outdir=""; repodir=""; arch_image=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -v) m="$2"; h="${m%%:*}"; rest="${m#*:}"; c="${rest%%:*}"
        [[ "$c" == "/out" ]] && outdir="$h"
        [[ "$c" == "/repo" ]] && repodir="$h"
        shift 2 ;;
    alpine:latest) shift; break ;;
    archlinux:latest) arch_image=1; shift; break ;;
    *) shift ;;
  esac
done
[[ -z "$outdir" ]] && exit 0
if [[ -n "$arch_image" ]]; then
  cp "$repodir"/*.pkg.tar.zst "$outdir"/ 2>/dev/null || true
  echo "pacman-db" >"$outdir/rediacc.db.tar.gz"
else
  work=$(mktemp -d)
  printf 'C:Q1x\\nP:rediacc-cli\\nV:1.2.3-r1\\nA:x86_64\\n' >"$work/APKINDEX"
  # DETERMINISTIC ON PURPOSE. A plain `tar czf` embeds the member's mtime in the
  # tar header AND the source mtime in the gzip header, so the two sides -- which
  # run seconds apart -- would produce different bytes for a reason that is not
  # the port, and the artifact comparison would fail on the harness rather than
  # on the subject. `--mtime=@0 --owner=0 --group=0` pins the tar, `gzip -n` drops
  # the gzip header's name and timestamp.
  tar --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$work" APKINDEX \\
    | gzip -n -9 >"$outdir/APKINDEX.tar.gz"
  rm -rf "$work"
fi
"""

FAKES = {
    "gpg": FAKE_GPG,
    "dpkg-scanpackages": FAKE_SCANPACKAGES,
    "createrepo_c": FAKE_CREATEREPO,
    "docker": FAKE_DOCKER,
}

# The package sets a case can ask for. Keys are what `--local-pkgs` holds.
PKG_SETS = {
    "full": (
        "rediacc-cli_1.2.3_amd64.deb",
        "rediacc-cli_1.2.3_arm64.deb",
        "rediacc-cli-1.2.3-1.x86_64.rpm",
        "rediacc-cli-1.2.3-1.aarch64.rpm",
        "rediacc-cli-1.2.3-r1-amd64.apk",
        "rediacc-cli-1.2.3-r1-arm64.apk",
        "rediacc-cli-1.2.3-1-x86_64.pkg.tar.zst",
        "rediacc-cli-1.2.3-1-aarch64.pkg.tar.zst",
    ),
    "deb-only": ("rediacc-cli_1.2.3_amd64.deb",),
    "empty": (),
    "two-apks-one-arch": (
        "rediacc-cli_1.2.3_amd64.deb",
        "rediacc-cli-1.2.3-r1-amd64.apk",
        "rediacc-cli-1.2.4-r1-amd64.apk",
    ),
    "amd64-only": (
        "rediacc-cli_1.2.3_amd64.deb",
        "rediacc-cli-1.2.3-1.x86_64.rpm",
        "rediacc-cli-1.2.3-r1-amd64.apk",
        "rediacc-cli-1.2.3-1-x86_64.pkg.tar.zst",
    ),
}


def _fixture(
    where: pathlib.Path, *, packages: str = "full", public_key: bool = True
) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects."""
    root = where.resolve() / "tree"
    (root / ".ci" / "scripts" / "build").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "config").mkdir(parents=True)
    (root / ".ci" / "keys").mkdir(parents=True)
    (root / ".devcontainer").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "build").mkdir(parents=True)

    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(CONSTANTS, root / ".ci" / "config" / "constants.sh")
    shutil.copy2(TOOLCHAIN, root / ".devcontainer" / "toolchain.env")
    shutil.copy2(PORT, root / PORT_REL)

    if public_key:
        (root / ".ci" / "keys" / "gpg-public.asc").write_text(
            "-----BEGIN PGP PUBLIC KEY BLOCK-----\nfake\n-----END PGP PUBLIC KEY BLOCK-----\n",
            encoding="utf-8",
        )

    pkgs = root / "pkgs"
    pkgs.mkdir()
    for index, name in enumerate(PKG_SETS[packages]):
        # Distinct bytes per file, so a copy landing on the wrong name is a CONTENT divergence and not merely a missing path.
        (pkgs / name).write_text("payload-%d-%s\n" % (index, name), encoding="utf-8")
    return root


def _binder(where: pathlib.Path, *, with_docker: bool = True, gpg: bool = True) -> str:
    """The COMPLETE PATH for one run: real coreutils, symlinked, plus the fakes.

    Every exclusion is ASSERTED. `--docker` absent is a whole test case (DEFECT 1), and a PATH that leaked the real docker would turn that case into an attempt to pull `alpine:latest` over the network.
    """
    binder = where / "bin"
    binder.mkdir(parents=True, exist_ok=True)
    for tool in NEEDED:
        target = shutil.which(tool, path="/usr/bin:/bin:/usr/local/bin")
        if target is None:
            continue
        link = binder / tool
        if not link.exists():
            link.symlink_to(target)
    for name, body in FAKES.items():
        if name == "docker" and not with_docker:
            continue
        if name == "gpg" and not gpg:
            continue
        stub = binder / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)

    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
    assert shutil.which("find", path=str(binder)), (
        "find is missing from the restricted PATH; every count and copy in both "
        "subjects would silently see nothing"
    )
    for tool in FAKED:
        resolved = shutil.which(tool, path=str(binder))
        if tool == "docker" and not with_docker:
            assert resolved is None, (
                "docker survived exclusion; the DEFECT 1 case would run the REAL docker"
            )
            continue
        if tool == "gpg" and not gpg:
            assert resolved is None, "gpg survived exclusion"
            continue
        assert resolved == str(binder / tool), (
            "%s resolved to %r, not the fake; this run would touch the real tool" % (tool, resolved)
        )
    return str(binder)


def _normalise_release(text: str, *, mask_date: bool) -> str:
    """Mask what gzip's header makes unstable, and nothing else.

    Only the DIGEST of a `.gz` row is masked. The size stays, the path stays, and every non-`.gz` row is untouched, so a port that wrote a wrong `Packages` index, dropped an architecture or reordered the rows still fails.
    """
    text = GZ_DIGEST_ROW.sub(r" <gz-digest> \1 \2", text)
    if mask_date:
        text = DATE_LINE.sub("Date: <masked>", text)
    return text


def _artifacts(out: pathlib.Path, *, mask_date: bool) -> dict[str, object]:
    """Every output file, by relative path, with its comparable content."""
    result: dict[str, object] = {}
    if not out.is_dir():
        return result
    for path in sorted(out.rglob("*")):
        rel = str(path.relative_to(out))
        if path.is_dir():
            result[rel + "/"] = "<dir>"
            continue
        if path.name.endswith(".gz"):
            # Compared DECOMPRESSED: the gzip header embeds the source file's mtime, so two runs seconds apart differ for a reason that is not the port. `APKINDEX.tar.gz` and `rediacc.db.tar.gz` come from the fake docker and are stable, but go through the same door.
            try:
                result[rel] = gzip.decompress(path.read_bytes())
            except OSError:
                result[rel] = path.read_bytes()
            continue
        if path.name in ("Release", "InRelease"):
            result[rel] = _normalise_release(path.read_text(encoding="utf-8"), mask_date=mask_date)
            continue
        result[rel] = path.read_bytes()
    return result


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    *,
    args: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
    with_docker: bool = True,
    gpg: bool = True,
    epoch: str | None = EPOCH,
    output: str = "out",
    local_pkgs: str | None = "pkgs",
) -> dict[str, object]:
    """Drive one subject and collect all five observables."""
    tag = pathlib.Path(subject).name
    call_log = root.parent / ("calls-%s.txt" % tag)
    out_dir = root / output

    env = {
        "PATH": _binder(root.parent / ("fxbin-%s" % tag), with_docker=with_docker, gpg=gpg),
        "HOME": str(root.parent),
        "TMPDIR": "/tmp",
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        # The port imports `rediacc_ci`; the COPY under the fixture is what runs, so the package itself comes from the real checkout. This is the only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
        "CALLLOG": str(call_log),
    }
    if epoch is not None:
        env["SOURCE_DATE_EPOCH"] = epoch
    env.update(env_extra or {})

    argv = list(args)
    if local_pkgs is not None:
        argv = [*argv, "--local-pkgs", str(root / local_pkgs)]
        argv = [*argv, "--output", str(out_dir)]

    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject), *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
    )

    def scrub(text: str) -> str:
        text = text.replace(str(root / subject), "<prog>")
        text = text.replace(str(out_dir), "<out>")
        text = text.replace(str(root), "<root>")
        return TEMP_PATH.sub("<tmp>", text)

    calls: list[str] = []
    if call_log.exists():
        calls = [scrub(line) for line in call_log.read_text(encoding="utf-8").splitlines() if line]
        call_log.unlink()

    return {
        "exit": proc.returncode,
        "stdout": scrub(proc.stdout),
        "stderr": scrub(proc.stderr),
        "calls": calls,
        "artifacts": _artifacts(out_dir, mask_date=epoch is None),
        # UNSCRUBBED, and deliberately NOT in FIELDS. `scrub` replaces each subject's own path with `<prog>`, which is the right normalisation for a comparison -- the two files cannot have the same path -- but it also hides divergence 1 entirely. The two named divergence tests below assert these RAW strings differ, so the mask is proved to be hiding a path and nothing else.
        "stderr_raw": proc.stderr,
        "stdout_raw": proc.stdout,
    }


FIELDS = ("exit", "stdout", "stderr", "calls", "artifacts")

BUILD_ARGS = ("--version", "1.2.3", "--channel", "edge")

CASES = [
    pytest.param({}, {"args": BUILD_ARGS}, id="happy-path-all-four-repositories"),
    pytest.param(
        {},
        {"args": BUILD_ARGS, "env_extra": {"RELEASE_GPG_PASSPHRASE": "SEKRIT"}},
        id="passphrase-is-masked-on-stdout",
    ),
    pytest.param(
        {},
        {"args": (*BUILD_ARGS, "--dry-run"), "env_extra": {"RELEASE_GPG_PRIVATE_KEY": ""}},
        id="dry-run-writes-rediacc-repo-and-not-rediacc-conf",
    ),
    pytest.param(
        {},
        {"args": BUILD_ARGS, "with_docker": False},
        id="DEFECT-1-docker-absent-dies-after-warning",
    ),
    pytest.param(
        {"packages": "deb-only"},
        {"args": BUILD_ARGS},
        id="DEFECT-2-one-deb-publishes-three-empty-repositories",
    ),
    pytest.param(
        {"packages": "empty"},
        {"args": BUILD_ARGS},
        id="the-apt-vacuity-floor-refuses-an-empty-pool",
    ),
    pytest.param(
        {"packages": "empty"},
        {"args": BUILD_ARGS, "env_extra": {"PKG_REPO_MIN_DEBS": "8"}},
        id="a-plain-integer-floor-refuses-too",
    ),
    pytest.param(
        {"packages": "empty"},
        {"args": BUILD_ARGS, "env_extra": {"PKG_REPO_MIN_DEBS": "0"}},
        id="a-zero-floor-disables-the-refusal-legibly",
    ),
    pytest.param(
        {"packages": "two-apks-one-arch"},
        {"args": BUILD_ARGS},
        id="DEFECT-7-two-apks-collapse-into-one-file",
    ),
    pytest.param(
        {"packages": "amd64-only"},
        {"args": BUILD_ARGS},
        id="one-architecture-skips-the-other-with-a-warning",
    ),
    pytest.param(
        {},
        {"args": BUILD_ARGS, "env_extra": {"GPG_SHOW_KEYS_RC": "2"}},
        id="DEFECT-6-an-unreadable-published-key-dies-with-gpgs-status",
    ),
    pytest.param(
        {},
        {"args": BUILD_ARGS, "env_extra": {"WANT_FPR": "AAAA", "HAVE_FPR": "BBBB"}},
        id="a-signing-key-that-is-not-the-published-key-is-refused",
    ),
    pytest.param(
        {"public_key": False},
        {"args": BUILD_ARGS},
        id="no-published-key-file-exports-from-the-keyring",
    ),
    pytest.param(
        {},
        {"args": BUILD_ARGS, "env_extra": {"GPG_NO_KEYS": "1"}},
        id="an-import-that-yields-no-public-key-is-refused",
    ),
    pytest.param(
        {},
        {"args": BUILD_ARGS, "env_extra": {"GPG_IMPORT_RC": "2"}},
        id="a-failed-import-dies-with-gpgs-status-and-no-message",
    ),
    pytest.param(
        {},
        {"args": BUILD_ARGS, "env_extra": {"RELEASE_GPG_PRIVATE_KEY": ""}},
        id="an-empty-private-key-is-refused",
    ),
    pytest.param(
        {},
        {
            "args": ("--version", "1.2.3", "--channel", "pr-420"),
            "env_extra": {"RELEASES_BASE_URL": "https://example.test"},
        },
        id="releases-base-url-is-overridable-and-reaches-both-config-files",
    ),
    pytest.param(
        {},
        {"args": ("--version", "1.2.3", "--channel", "edge", "--max-versions", "20")},
        id="max-versions-with-a-value-is-ignored",
    ),
    pytest.param(
        {}, {"args": BUILD_ARGS, "epoch": None}, id="no-source-date-epoch-falls-back-to-date-Ru"
    ),
    pytest.param(
        {}, {"args": ("--help",), "local_pkgs": None}, id="help-goes-to-stdout-and-exits-zero"
    ),
    pytest.param({}, {"args": ("-h",), "local_pkgs": None}, id="short-help-is-the-same-arm"),
    pytest.param({}, {"args": ("--bogus",), "local_pkgs": None}, id="an-unknown-option-is-named"),
    pytest.param({}, {"args": (), "local_pkgs": None}, id="no-arguments-names-the-first-missing"),
    pytest.param(
        {},
        {"args": ("--version", "1.2.3"), "local_pkgs": None},
        id="version-alone-names-the-next-missing",
    ),
    pytest.param(
        {},
        {
            "args": (
                "--version",
                "1.2.3",
                "--local-pkgs",
                "/definitely/not/here",
                "--channel",
                "e",
            ),
            "local_pkgs": None,
        },
        id="a-missing-local-pkgs-directory-is-refused",
    ),
]

DEFAULT_ENV = {"RELEASE_GPG_PRIVATE_KEY": "PRIVATE-KEY-MATERIAL"}


@pytest.mark.parametrize(("fixture_kw", "run_kw"), CASES)
def test_port_and_twin_agree(tmp_path, fixture_kw, run_kw):
    run_kw = dict(run_kw)
    env_extra = dict(DEFAULT_ENV)
    env_extra.update(run_kw.pop("env_extra", {}))
    run_kw["env_extra"] = env_extra

    root_a = _fixture(tmp_path / "a", **fixture_kw)
    old = _run(TWIN_REL, root_a, **run_kw)

    root_b = _fixture(tmp_path / "b", **fixture_kw)
    new = _run(PORT_REL, root_b, **run_kw)

    _assert_agree(old, new)


def _assert_agree(old: dict[str, object], new: dict[str, object]) -> None:
    """Compare all five observables, and report the DIFFERENCE rather than both sides in full.

    A whole-dict `assert a == b` over the artifact map prints two multi-kilobyte
    repr()s of binary content, which is unreadable and therefore unactionable. This names the paths that differ and shows only those.
    """
    for field in ("exit", "stdout", "stderr", "calls"):
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )
    old_art: dict[str, object] = old["artifacts"]  # type: ignore[assignment]
    new_art: dict[str, object] = new["artifacts"]  # type: ignore[assignment]
    only_old = sorted(set(old_art) - set(new_art))
    only_new = sorted(set(new_art) - set(old_art))
    assert not only_old, "paths the twin wrote and the port did not: %r" % (only_old,)
    assert not only_new, "paths the port wrote and the twin did not: %r" % (only_new,)
    for name in sorted(old_art):
        assert new_art[name] == old_art[name], "artifact %s diverged:\n twin: %r\n port: %r" % (
            name,
            old_art[name],
            new_art[name],
        )


def test_the_fakes_are_actually_reached_and_the_repository_is_real(tmp_path):
    """ANTI-VACUITY, and it is the load-bearing test in this file.

    Every comparison above is worthless if both sides did nothing. This pins the SHAPE of a successful run: gpg imported, listed, verified the fingerprint and produced three signatures; dpkg-scanpackages ran TWICE, from the pool's own directory; createrepo_c ran once; docker ran FOUR times, two images by two architectures. Then it names the files that must exist.
    """
    root = _fixture(tmp_path / "v")
    out = _run(PORT_REL, root, args=BUILD_ARGS, env_extra=DEFAULT_ENV)
    assert out["exit"] == 0, out["stderr"]

    calls = [c for c in out["calls"] if c.startswith("call: ")]
    assert len(calls) >= 12, "the fake tools were barely reached: %r" % calls
    assert sum(c.startswith("call: dpkg-scanpackages") for c in calls) == 2, calls
    assert sum(c.startswith("call: createrepo_c") for c in calls) == 1, calls
    assert sum(c.startswith("call: docker") for c in calls) == 4, calls
    assert sum("--detach-sign" in c or "--clearsign" in c for c in calls) == 3, calls
    assert "cwd-is-pool: yes" in out["calls"], (
        "dpkg-scanpackages did not run from the directory holding pool/, so the "
        "index it produced would name nothing: %r" % out["calls"]
    )

    names = set(out["artifacts"])
    for required in (
        "apt/dists/stable/Release",
        "apt/dists/stable/Release.gpg",
        "apt/dists/stable/InRelease",
        "apt/dists/stable/main/binary-amd64/Packages",
        "apt/dists/stable/main/binary-arm64/Packages.gz",
        "apt/pool/main/r/rediacc-cli/rediacc-cli_1.2.3_amd64.deb",
        "apt/gpg.key",
        "rpm/gpg.key",
        "rpm/rediacc.repo",
        "rpm/repodata/repomd.xml.asc",
        "apk/x86_64/APKINDEX.tar.gz",
        "apk/aarch64/rediacc-cli-1.2.3-r1.apk",
        "archlinux/rediacc.conf",
        "archlinux/x86_64/rediacc.db.tar.gz",
    ):
        assert required in names, "%s is missing from a successful build: %r" % (
            required,
            sorted(names),
        )

    release = out["artifacts"]["apt/dists/stable/Release"]
    assert "Date: %s" % EPOCH_DATE in release, release
    assert release.count("main/binary-") == 8, (
        "Release should carry four md5 rows and four sha256 rows: %r" % release
    )


def test_a_docker_less_run_dies_before_it_finishes_and_both_sides_know_it(tmp_path):
    """DEFECT 1, named rather than left inside a parametrised diff.

    The twin prints "Docker not available, cannot generate APKINDEX" and then dies at `:389` with tar's status, so phase 7 never runs and the summary never prints. This asserts all three: the status, the warning, and the ABSENCE of the summary line -- because a port that warned and then carried on would produce a BETTER program and a failing differential nobody could explain.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("d1-%s" % subject.name))
        out = _run(subject, root, args=BUILD_ARGS, env_extra=DEFAULT_ENV, with_docker=False)
        assert out["exit"] == 2, "%s: expected tar's status, got %r" % (subject.name, out["exit"])
        assert "Docker not available, cannot generate APKINDEX for x86_64" in out["stderr"]
        assert "Phase 7" not in out["stderr"], (
            "%s: the run continued past the silent death, so this test is stale" % subject.name
        )
        assert "Package repository build complete" not in out["stderr"], out["stderr"]
        assert out["artifacts"].get("apk/x86_64/") == "<dir>", (
            "%s: apk/x86_64 should exist and be EMPTY" % subject.name
        )
        assert not [k for k in out["artifacts"] if k.startswith("apk/x86_64/")][1:], (
            "%s: something was copied into apk/x86_64 after all" % subject.name
        )


def test_one_deb_publishes_three_empty_repositories_at_exit_zero(tmp_path):
    """DEFECT 2. The APT floor is the only floor, and this is what that costs.

    Driven on BOTH sides, because the interesting claim is about the twin and the port only has to agree with it.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("d2-%s" % subject.name), packages="deb-only")
        out = _run(subject, root, args=BUILD_ARGS, env_extra=DEFAULT_ENV)
        assert out["exit"] == 0, "%s: %r" % (subject.name, out["stderr"])
        assert "metadata for 0 .rpm packages" in out["stderr"], out["stderr"]
        assert "metadata for 0 .apk packages" in out["stderr"], out["stderr"]
        assert "metadata for 0 .pkg.tar.zst packages" in out["stderr"], out["stderr"]
        # Generated AND SIGNED over nothing.
        assert "rpm/repodata/repomd.xml.asc" in out["artifacts"], sorted(out["artifacts"])
        assert not [k for k in out["artifacts"] if k.endswith(".rpm")], sorted(out["artifacts"])
        assert "archlinux/rediacc.conf" in out["artifacts"], sorted(out["artifacts"])
        assert "VACUOUS" not in out["stderr"], (
            "%s: a floor now covers the other three formats, so this test is stale" % subject.name
        )


def test_a_zero_padded_floor_disables_the_refusal(tmp_path):
    """DEFECT 3, with the one divergent prefix masked and then asserted DIFFERENT.

    `PKG_REPO_MIN_DEBS=08` is not a base-8 number, bash reports an arithmetic
    error, an erroring `[[ ]]` is FALSE, and the refusal is skipped: an EMPTY
    package directory publishes an empty APT repository at exit 0. Compared
    against `=8`, which refuses, so the test cannot pass because the floor is
    broken in general.
    """
    results = {}
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("d3-%s" % subject.name), packages="empty")
        results[subject] = _run(
            subject,
            root,
            args=BUILD_ARGS,
            env_extra={**DEFAULT_ENV, "PKG_REPO_MIN_DEBS": "08"},
        )

    for subject, out in results.items():
        assert out["exit"] == 0, "%s: the octal floor now refuses: %r" % (subject.name, out)
        assert "VACUOUS" not in out["stderr"], out["stderr"]
        assert 'value too great for base (error token is "08")' in out["stderr"], out["stderr"]
        assert "apt/dists/stable/Release" in out["artifacts"], (
            "%s: an empty repository was NOT published, so the defect is gone" % subject.name
        )

    old, new = results[TWIN_REL], results[PORT_REL]
    assert LINE_PREFIX.sub("<prog>: line N: ", new["stderr"]) == LINE_PREFIX.sub(
        "<prog>: line N: ", old["stderr"]
    ), "masked stderr diverged:\n twin: %r\n port: %r" % (old["stderr"], new["stderr"])
    assert old["stderr_raw"] != new["stderr_raw"], (
        "the two RAW diagnostics are byte-identical, so nothing is being masked and "
        "this case belongs in the parametrised set"
    )
    assert "build-pkg-repo.sh: line %d: [[:" % build_pkg_repo.FLOOR_LINE in old["stderr_raw"], (
        "the twin no longer reports the arithmetic error against line %d, so the "
        "port's copy of that line number is stale: %r"
        % (build_pkg_repo.FLOOR_LINE, old["stderr_raw"])
    )
    assert "build_pkg_repo.py: line %d: [[:" % build_pkg_repo.FLOOR_LINE in new["stderr_raw"], (
        "the port stopped naming itself: %r" % new["stderr_raw"]
    )


def test_dry_run_writes_one_config_file_and_not_the_other(tmp_path):
    """DEFECT 4, both halves, on both sides.

    `rpm/rediacc.repo` is written OUTSIDE the dry-run guard and `archlinux/rediacc.conf` INSIDE it, so a "preview" leaves one behind. The second half, found by driving: the `.rpm` PAYLOAD is copied too, because the `find -exec cp` that populates the RPM repository is also outside the guard.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("d4-%s" % subject.name))
        out = _run(subject, root, args=(*BUILD_ARGS, "--dry-run"), env_extra={})
        assert out["exit"] == 0, out["stderr"]
        names = set(out["artifacts"])
        assert "rpm/rediacc.repo" in names, (
            "%s: the dry run no longer writes rediacc.repo, so this test is stale" % subject.name
        )
        assert "archlinux/rediacc.conf" not in names, (
            "%s: the two config writers now agree, so this test is stale" % subject.name
        )
        rpms = sorted(n for n in names if n.endswith(".rpm"))
        assert rpms, (
            "%s: the dry run no longer copies the rpm payload, so the second half "
            "of DEFECT 4 is fixed and this test is stale" % subject.name
        )
        # And nothing was SIGNED, which is the part the guard does cover.
        assert not [n for n in names if n.endswith((".asc", ".gpg"))], sorted(names)


def test_max_versions_without_a_value_dies_with_zero_bytes(tmp_path):
    """DEFECT 5, and the contrast that makes it a defect rather than a style.

    `--max-versions` at the end of argv fails a `shift 2` and `set -e` ends the run: exit 1, ZERO bytes on stdout, ZERO bytes on stderr. `--version` at the end of argv names the line it died on. Both spellings are driven on both sides, and the SILENT one is asserted silent, because a silent exit 1 is indistinguishable from a gate failing for a real reason.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("d5-%s" % subject.name))
        silent = _run(
            subject,
            root,
            args=(*BUILD_ARGS, "--max-versions"),
            env_extra=DEFAULT_ENV,
            local_pkgs=None,
        )
        assert silent["exit"] == 1, "%s: %r" % (subject.name, silent)
        assert silent["stdout"] == "", "%s: stdout was not empty: %r" % (
            subject.name,
            silent["stdout"],
        )
        assert silent["stderr"] == "", "%s: stderr was not empty: %r" % (
            subject.name,
            silent["stderr"],
        )


def test_a_missing_flag_value_names_the_program_that_refused(tmp_path):
    """The other half of DEFECT 5's contrast, and divergence 1.

    Every value-taking flag dies with bash's `$2: unbound variable` naming the ASSIGNMENT'S line. The port prints the same sentence against its own path, so the prefix is masked, the rest is compared byte for byte, and the two unmasked strings are asserted DIFFERENT so the mask cannot start hiding a real change.
    """
    for flag, line in (
        ("--version", 40),
        ("--local-pkgs", 44),
        ("--output", 48),
        ("--channel", 56),
    ):
        root_a = _fixture(tmp_path / ("m-a-%s" % flag.strip("-")))
        old = _run(TWIN_REL, root_a, args=(flag,), env_extra=DEFAULT_ENV, local_pkgs=None)
        root_b = _fixture(tmp_path / ("m-b-%s" % flag.strip("-")))
        new = _run(PORT_REL, root_b, args=(flag,), env_extra=DEFAULT_ENV, local_pkgs=None)

        assert old["exit"] == 1, (flag, old["exit"])
        assert new["exit"] == 1, (flag, new["exit"])
        assert "line %d: $2: unbound variable" % line in old["stderr"], (
            "the twin's parser moved; %s no longer dies on line %d: %r"
            % (flag, line, old["stderr"])
        )
        assert LINE_PREFIX.sub("<prog>: line N: ", new["stderr"]) == LINE_PREFIX.sub(
            "<prog>: line N: ", old["stderr"]
        ), "masked stderr diverged for %s:\n twin: %r\n port: %r" % (
            flag,
            old["stderr"],
            new["stderr"],
        )
        assert old["stderr_raw"] != new["stderr_raw"], (
            "the two RAW diagnostics are identical for %s, so nothing is masked" % flag
        )
        assert old["stderr_raw"].startswith(str(root_a / TWIN_REL)), old["stderr_raw"]
        assert new["stderr_raw"].startswith(str(root_b / PORT_REL)), new["stderr_raw"]


def test_two_apks_for_one_arch_collapse_into_one_published_file(tmp_path):
    """DEFECT 7, found by driving rather than by reading.

    `apk_name` is recomputed inside the per-file loop from the SAME `APKINDEX.tar.gz`, with an awk program that stops at the first `V:`. Every file therefore lands on one name. Two `.apk` files in, one out, exit 0, no warning.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("d7-%s" % subject.name), packages="two-apks-one-arch")
        out = _run(subject, root, args=BUILD_ARGS, env_extra=DEFAULT_ENV)
        assert out["exit"] == 0, out["stderr"]
        assert "APK: generating metadata for 2 packages" in out["stderr"], out["stderr"]
        published = sorted(
            n for n in out["artifacts"] if n.startswith("apk/x86_64/") and n.endswith(".apk")
        )
        assert published == ["apk/x86_64/rediacc-cli-1.2.3-r1.apk"], (
            "%s: the collision is gone, so this test is stale: %r" % (subject.name, published)
        )


def test_bash_arith_is_bashs_grammar_and_not_int(tmp_path):
    """The pure half, driven against BASH ITSELF rather than against a constant.

    A constant copied out of the port cannot contradict the port. Each token is compared through a real `[[ 0 -lt TOKEN ]]`, so the octal rule, the hex rule, the bare-word rule and the "an error is FALSE" rule are all checked against the interpreter whose behaviour is being reproduced.
    """
    del tmp_path
    for token in ("", "0", "1", "007", "0x10", "08", "09", "abc", " 5 ", "-3", "10"):
        expected = (
            subprocess.run(
                ["bash", "-c", 'if [[ "0" -lt "$1" ]]; then echo T; else echo F; fi', "_", token],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            == "T"
        )
        got = build_pkg_repo.bash_lt("0", token)
        assert got == expected, "bash_lt('0', %r) = %r, bash says %r" % (token, got, expected)

    # And the direction that matters for the floor: an ERROR is False, which is not the same claim as "08 is zero".
    assert build_pkg_repo.bash_arith("08") is None
    assert build_pkg_repo.bash_arith("007") == 7
    assert build_pkg_repo.bash_arith("abc") == 0


def test_the_restated_constants_match_constants_sh():
    """The two values this port copies out of `.ci/config/constants.sh`.

    A stale constant here is a repository published under the wrong package name or pointing at the wrong host, so the alarm is not optional. The two are parsed with DIFFERENT patterns on purpose: `PKG_NAME` is a bare `readonly`
    and `RELEASES_BASE_URL` is a `readonly X="${X:-default}"`, and the port
    depends on that difference -- one is a constant, the other an overridable default.
    """
    text = CONSTANTS.read_text(encoding="utf-8")

    bare = re.search(r'^readonly PKG_NAME="([^"$]+)"$', text, re.MULTILINE)
    assert bare, "PKG_NAME is no longer a bare readonly in constants.sh"
    assert bare.group(1) == build_pkg_repo.PKG_NAME, (
        "PKG_NAME drifted: constants.sh says %r, the port says %r"
        % (bare.group(1), build_pkg_repo.PKG_NAME)
    )

    overridable = re.search(
        r'^readonly RELEASES_BASE_URL="\$\{RELEASES_BASE_URL:-([^}]+)\}"$', text, re.MULTILINE
    )
    assert overridable, (
        "RELEASES_BASE_URL is no longer an overridable default in constants.sh; the "
        "port reads the environment for it and would now diverge"
    )
    assert overridable.group(1) == build_pkg_repo.RELEASES_BASE_URL_DEFAULT, (
        "RELEASES_BASE_URL default drifted: constants.sh says %r, the port says %r"
        % (overridable.group(1), build_pkg_repo.RELEASES_BASE_URL_DEFAULT)
    )


def test_source_common_exports_what_sourcing_the_library_would(monkeypatch):
    """`common.sh` runs on SOURCE, before line 28 of the twin, so every child inherits `CI_OS`, `CI_ARCH` and `CI_TEMP`. Compared against the library itself rather than against a constant, so a change to `detect_os` is caught.
    """
    monkeypatch.delenv("CI_OS", raising=False)
    monkeypatch.delenv("CI_ARCH", raising=False)
    monkeypatch.delenv("CI_TEMP", raising=False)
    build_pkg_repo.source_common()

    import os  # noqa: PLC0415 -- read back the same way the children would

    expected = subprocess.run(
        ["bash", "-c", 'source "$1"; printf "%s\\n%s\\n" "$CI_OS" "$CI_ARCH"', "_", str(COMMON)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert [os.environ["CI_OS"], os.environ["CI_ARCH"]] == expected, expected
    assert os.environ["CI_TEMP"], "CI_TEMP was not set"


def test_the_harness_refuses_a_path_that_leaks_the_real_docker(tmp_path):
    """A CONTROL ON THE CONTROL.

    `_binder(with_docker=False)` is what makes the DEFECT 1 case mean anything.
    If an exclusion silently failed, that case would run the REAL docker, try to pull `alpine:latest`, and either hang or produce a divergence nobody could attribute. The assertion inside `_binder` is exercised here by asking for the exclusion and then checking it took, and by proving the INCLUSION resolves to the fake rather than to `/usr/bin/docker`.
    """
    without = _binder(tmp_path / "no", with_docker=False)
    assert shutil.which("docker", path=without) is None
    assert shutil.which("gpg", path=without) == str(pathlib.Path(without) / "gpg")

    with_it = _binder(tmp_path / "yes", with_docker=True)
    resolved = shutil.which("docker", path=with_it)
    assert resolved == str(pathlib.Path(with_it) / "docker"), resolved
    assert resolved != "/usr/bin/docker"
