"""`rediacc_ci.ops.build_server`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `scripts/ops/build-server.sh` and the port over the same throwaway root, one after the other, and compared exit code, stdout, stderr, the fake-command call log and the staged tree. The K=5 ledger `.ci/shadow/w9p3-build-server.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every case
compares against `goldens/build-server/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

STDOUT IS THE LEAST INFORMATIVE HALF HERE, and a comparison of the two streams alone would have been close to worthless. This script prints four progress lines and then invokes `npm`, `npx`, `cp`, `sort` and `docker buildx` with arguments that decide what lands in the image. So each golden carries two further sections:

    `--- calls ---`   the fakes' argv log, which is the staging CONTRACT. A port
                      that printed the same four sentences and handed docker a
                      different `--build-arg` would pass a stream comparison and
                      produce a different image.
    `--- staged ---`  every file under `binaries/`, `www-assets/`,
                      `account-web-assets/` and `cli-npm/` with its first line,
                      which is the staging RESULT. `sort -V` picking
                      `rediacc-cli-0.8.10.tgz` over `rediacc-cli-0.8.9.tgz` is
                      invisible in every other section and visible here.

THE PATH IS REPLACED, NEVER PREPENDED. `docker buildx build --load` in this checkout is a real multi-gigabyte image build and `npm run build` is a real site build, so the fixture hands both sides a directory holding nothing but the fakes and symlinks to the coreutils each subject genuinely needs. `test_the_scratch_path_cannot_reach_a_real_docker` asserts the replacement holds in
both directions.

THREE THINGS ARE NORMALIZED, and only three.

    `$0`, which a bash child and a Python child never agreed on: the twin prints
    the path it was invoked by, the port prints `sys.argv[0]`, and the usage line
    is the one place either appears. `test_both_sides_printed_a_real_usage_line`
    is the control.

    The bash LOCATION PREFIX, `<SELF>: line 104: `, which bash puts in front of
    its own diagnostics for a failed `cd` and an absent command. A port must not
    forge a line number: a hard-coded one goes stale the first time the twin
    gains a comment, on the `test_infra_ci_start_elite.py` precedent. The
    SENTENCE after the prefix is reproduced exactly and compared exactly, and
    `the-raw-twin-location-prefix` is a golden holding the twin's UNMASKED bytes
    for one such case, so the mask can be shown to be hiding a prefix that was
    really there rather than nothing at all.

    The fixture root, which a recording compared against a tree built minutes or
    months later cannot share. `frozen.mask_root` carries it.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

SLUG = "build-server"

TWIN_REL = "scripts/ops/build-server.sh"
PORT_REL = ".ci/rediacc_ci/ops/build_server.py"

# Everything the port imports, transitively. It imports nothing from `rediacc_ci` itself, so only the package markers travel; they are still needed for the module to be addressable in the copied tree.
VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/ops/__init__.py",
)

# `sed` and `tr` read the account key on the bash side, `cp`, `mkdir`, `rm`, `sort` and `tail` do the staging, and `cd`/`pwd` are builtins. Anything not listed is ABSENT from both sides.
PATH_MINIMUM = ("sed", "tr", "mkdir", "cp", "rm", "sort", "tail", "dirname")

FAKE = """#!/bin/bash
printf 'CALL %(name)s' >>"$FAKE_CALL_LOG"
for a in "$@"; do printf '\\t%%s' "$a" >>"$FAKE_CALL_LOG"; done
printf '\\n' >>"$FAKE_CALL_LOG"
for f in ${FAKE_%(upper)s_MAKE_FILES:-}; do
    mkdir -p "$(dirname "$f")"
    basename "$f" >"$f"
done
exit "${FAKE_%(upper)s_RC:-0}"
"""

FAKES = ("npm", "npx", "docker")

STAGED_DIRS = ("binaries", "www-assets", "account-web-assets", "cli-npm")

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))

# bash's own location prefix on a diagnostic it raises itself, stripped AFTER `SELF_RE` has already replaced the path with `<SELF>`.
LOCATION_RE = re.compile(r"^<SELF>: line \d+: ", re.MULTILINE)

CALLS_MARKER = "--- calls ---\n"
STAGED_MARKER = "--- staged ---\n"


def fixture(
    tmp_path: pathlib.Path,
    *,
    port_source: str | None = None,
    renet: tuple[str, ...] = ("amd64", "arm64"),
    www_dist: bool = True,
    www_package: bool = True,
    account_dist: bool = True,
    dotenv: str | None = None,
) -> pathlib.Path:
    """A throwaway console root holding the port and whatever the case needs staged."""
    root = tmp_path / "repo"
    for rel in (PORT_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in VENDORED:
        shutil.copy2(ROOT / rel, root / rel)
    if port_source is None:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")

    (root / "Dockerfile").write_text("# fixture\n", encoding="utf-8")
    (root / "packages" / "cli").mkdir(parents=True, exist_ok=True)
    bindir = root / "private" / "renet" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    for arch in renet:
        (bindir / ("renet-linux-%s" % arch)).write_text("renet-%s\n" % arch, encoding="utf-8")
    # The package directories always exist; only `dist/` is conditional. A tree missing `packages/www` entirely is a different case, `no-packages-www-to-cd-into`, and the twin dies in the subshell rather than in npm.
    for rel, package, present, head in (
        ("packages/www/dist", www_package, www_dist, "www-index"),
        ("private/account/web/dist", True, account_dist, "portal-index"),
    ):
        base = root / rel
        if not package:
            continue
        (base if present else base.parent).mkdir(parents=True, exist_ok=True)
        if present:
            (base / "index.html").write_text("%s\n" % head, encoding="utf-8")
    if dotenv is not None:
        (root / "private" / "account").mkdir(parents=True, exist_ok=True)
        (root / "private" / "account" / ".env").write_text(dotenv, encoding="utf-8")
    return root


def scratch_bin(root: pathlib.Path, *, drop: tuple[str, ...] = ()) -> str:
    """The ONLY directory on PATH for either side."""
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for name in (*PATH_MINIMUM, "basename"):
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    for name in FAKES:
        fake = stub / name
        if name in drop:
            if fake.exists():
                fake.unlink()
            continue
        fake.write_text(FAKE % {"name": name, "upper": name.upper()}, encoding="utf-8")
        fake.chmod(0o755)
    return str(stub)


def staged(root: pathlib.Path) -> str:
    """Every staged file with its first line, which is what the staging produced."""
    lines = []
    for name in STAGED_DIRS:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            head = path.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
            lines.append("%s\t%s\n" % (path.relative_to(root), head))
    return "".join(lines)


def drive(
    root: pathlib.Path,
    argv: list[str],
    *,
    drop: tuple[str, ...] = (),
    tag: str = "new",
    **extra: str,
) -> tuple[int, str, str, str, str]:
    """One side, once, under a replaced PATH and a fresh call log."""
    call_log = root / ("%s-calls.log" % tag)
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
    proc = subprocess.run(
        argv,
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return (
        proc.returncode,
        proc.stdout,
        proc.stderr,
        call_log.read_text(encoding="utf-8"),
        staged(root),
    )


CASES = (
    "no-argument",
    "an-unknown-variant",
    "no-renet-binaries-at-all",
    "only-the-amd64-binary",
    "a-complete-staging-run",
    "an-absent-www-dist-builds-it",
    "an-absent-account-dist-builds-it",
    "npm-pack-produced-nothing",
    "docker-buildx-refuses",
    "the-account-key-comes-from-dotenv",
    "a-dotenv-naming-the-key-twice",
    "two-tarballs-version-sort",
    "npm-run-build-fails",
    "docker-is-absent-entirely",
    "no-packages-www-to-cd-into",
)

# The twin's UNMASKED bytes for one location-prefixed diagnostic. Asserted, never compared against the port: it is the control proving `LOCATION_RE` masks a prefix that was really there.
RAW_CASE = "the-raw-twin-location-prefix"

EXPECTED_EXIT = {
    "no-argument": 2,
    "an-unknown-variant": 2,
    "no-renet-binaries-at-all": 1,
    "only-the-amd64-binary": 1,
    "a-complete-staging-run": 0,
    "an-absent-www-dist-builds-it": 0,
    "an-absent-account-dist-builds-it": 0,
    "npm-pack-produced-nothing": 1,
    "docker-buildx-refuses": 125,
    "the-account-key-comes-from-dotenv": 0,
    "a-dotenv-naming-the-key-twice": 0,
    "two-tarballs-version-sort": 0,
    "npm-run-build-fails": 7,
    "docker-is-absent-entirely": 127,
    "no-packages-www-to-cd-into": 1,
}

ONE_TARBALL = "cli-npm/rediacc-cli-0.8.9.tgz"
OLDER_TARBALL = "cli-npm/rediacc-cli-0.8.9.tgz"
NEWER_TARBALL = "cli-npm/rediacc-cli-0.8.10.tgz"


def build(tmp_path: pathlib.Path, name: str, *, port_source: str | None = None):
    """The fixture tree, the argv tail and the run keywords for one recorded case.

    THE FAKES MAKE THE OUTPUTS THE REAL TOOLS WOULD. `npm pack` is a fake, so the tarball it "produces" is a path in `FAKE_NPM_MAKE_FILES` that the fake creates on every npm call; `rm -rf cli-npm` runs BEFORE the pack, so a tarball staged by the fixture up front would be wiped and the fake is the only way to put one there.
    """
    kw: dict[str, object] = {}
    fx: dict[str, object] = {}
    args = ["onprem"]
    npm_makes = [ONE_TARBALL]
    npx_makes: list[str] = []

    if name == "no-argument":
        args = []
    elif name == "an-unknown-variant":
        args = ["cloud"]
    elif name == "no-renet-binaries-at-all":
        fx["renet"] = ()
    elif name == "only-the-amd64-binary":
        fx["renet"] = ("amd64",)
    elif name == "an-absent-www-dist-builds-it":
        fx["www_dist"] = False
        npm_makes.append("packages/www/dist/index.html")
    elif name == "an-absent-account-dist-builds-it":
        fx["account_dist"] = False
        npx_makes.append("private/account/web/dist/index.html")
    elif name == "the-account-key-comes-from-dotenv":
        fx["dotenv"] = "OTHER=1\nACCOUNT_ED25519_PUBLIC_KEY=from-dotenv\n"
    elif name == "a-dotenv-naming-the-key-twice":
        fx["dotenv"] = "ACCOUNT_ED25519_PUBLIC_KEY=first\nACCOUNT_ED25519_PUBLIC_KEY=second\r\n"
    elif name == "two-tarballs-version-sort":
        npm_makes = [OLDER_TARBALL, NEWER_TARBALL]
    elif name == "npm-pack-produced-nothing":
        npm_makes = []
    elif name == "docker-buildx-refuses":
        kw["FAKE_DOCKER_RC"] = "125"
    elif name == "npm-run-build-fails":
        fx["www_dist"] = False
        kw["FAKE_NPM_RC"] = "7"
        npm_makes = []
    elif name == "docker-is-absent-entirely":
        kw["drop"] = ("docker",)
    elif name == "no-packages-www-to-cd-into":
        fx["www_dist"] = False
        fx["www_package"] = False
        npm_makes = []

    root = fixture(tmp_path, port_source=port_source, **fx)  # type: ignore[arg-type]
    if npm_makes:
        kw["FAKE_NPM_MAKE_FILES"] = " ".join(str(root / p) for p in npm_makes)
    if npx_makes:
        kw["FAKE_NPX_MAKE_FILES"] = " ".join(str(root / p) for p in npx_makes)
    return root, args, kw


def mask(text: str, root: pathlib.Path) -> str:
    """`$0`, bash's location prefix, and the fixture root. Nothing else."""
    return frozen.mask_root(LOCATION_RE.sub("", SELF_RE.sub("<SELF>", text)), root)


def render(returncode: int, stdout: str, stderr: str, calls: str, tree: str) -> str:
    return "%s%s%s%s%s" % (
        frozen.render(returncode, stdout, stderr),
        CALLS_MARKER,
        calls,
        STAGED_MARKER,
        tree,
    )


def split_golden(text: str) -> tuple[int, str, str, str, str]:
    """A recorded twin render, back into its five parts."""
    exit_line, rest = text.split("\n", 1)
    body, tail = rest.split(CALLS_MARKER, 1)
    calls, tree = tail.split(STAGED_MARKER, 1)
    stdout, stderr = body.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls, tree


def run_port(root: pathlib.Path, args: list[str], **kw) -> tuple[int, str, str, str, str]:
    return drive(root, [sys.executable, str(root / PORT_REL), *args], **kw)


def compare(root: pathlib.Path, name: str, args: list[str], **kw):
    want = split_golden(frozen.read(SLUG, name))
    returncode, stdout, stderr, calls, tree = run_port(root, args, **kw)
    assert returncode == want[0], "%s: the twin exited %d, the port %d\n%s" % (
        name,
        want[0],
        returncode,
        stderr,
    )
    assert mask(stdout, root) == want[1], "%s: stdout diverged from the recorded bytes" % name
    assert mask(stderr, root) == want[2], "%s: stderr diverged from the recorded bytes" % name
    assert mask(calls, root) == want[3], "%s: the call log diverged" % name
    assert mask(tree, root) == want[4], "%s: the staged tree diverged" % name
    return returncode, stdout, stderr, calls, tree


# ---------------------------------------------------------------------------
# The control on the control
# ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_docker(tmp_path: pathlib.Path) -> None:
    """`docker buildx build --load` in this checkout builds a real image and `npm run build` builds the real site. A PREPENDED PATH would still resolve both, so the fixture REPLACES it and this asserts the replacement holds in both directions."""
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    for name in FAKES:
        assert shutil.which(name, path=sealed) == str(root / "fixture-bin" / name)
    dropped = scratch_bin(root, drop=FAKES)
    for name in FAKES:
        assert shutil.which(name, path=dropped) is None, "a real %s is reachable" % name
    assert shutil.which("node", path=dropped) is None
    assert shutil.which("git", path=dropped) is None


# ---------------------------------------------------------------------------
# Every recorded case
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    root, args, kw = build(tmp_path, name)
    returncode = compare(root, name, args, **kw)[0]
    assert returncode == EXPECTED_EXIT[name], "the recorded verdict moved"


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {*CASES, RAW_CASE})


def test_the_green_case_is_not_vacuously_equal() -> None:
    """Two implementations that both print nothing agree about nothing, so the recorded green case must carry a whole staging run: the progress lines, the call log and the staged tree."""
    _, stdout, _, calls, tree = split_golden(frozen.read(SLUG, "a-complete-staging-run"))
    assert "==> Staging build context...\n" in stdout
    assert "==> Packing CLI tarball...\n" in stdout
    assert "Built: rediacc-server-onprem:dev\n" in stdout
    assert "CALL npm\tpack\t--pack-destination\t<root>/cli-npm\n" in calls
    assert "CALL docker\tbuildx\tbuild" in calls
    assert "binaries/renet-linux-amd64\trenet-amd64\n" in tree
    assert "www-assets/index.html\twww-index\n" in tree
    assert "account-web-assets/index.html\tportal-index\n" in tree


def test_the_docker_arguments_are_recorded_in_full() -> None:
    """The staging contract is the argv, not the prose. A port that changed a `--build-arg` would print the same four sentences and produce a different image."""
    calls = split_golden(frozen.read(SLUG, "the-account-key-comes-from-dotenv"))[3]
    line = next(c for c in calls.splitlines() if c.startswith("CALL docker"))
    assert line.split("\t")[1:] == [
        "buildx",
        "build",
        "--file",
        "Dockerfile",
        "--target",
        "onprem",
        "--build-arg",
        "ACCOUNT_ENTRY=on-premise",
        "--build-arg",
        "ACCOUNT_ED25519_PUBLIC_KEY=from-dotenv",
        "--build-arg",
        "VITE_APP_VERSION=dev",
        "--tag",
        "rediacc-server-onprem:dev",
        "--load",
        ".",
    ]


def test_both_sides_printed_a_real_usage_line() -> None:
    """CONTROL for the `$0` mask: the one masked token must actually sit inside a usage line the twin really printed, or the mask would be hiding its absence."""
    assert split_golden(frozen.read(SLUG, "no-argument"))[2] == "usage: <SELF> <onprem>\n"


def test_a_duplicate_key_line_is_joined_rather_than_dropped() -> None:
    """`sed -n 's/^X=//p'` prints EVERY matching line. A `.env` naming the key twice is malformed, and the twin has a defined answer for it that a port reaching for `next(...)` would not reproduce."""
    calls = split_golden(frozen.read(SLUG, "a-dotenv-naming-the-key-twice"))[3]
    line = next(c for c in calls.splitlines() if "ACCOUNT_ED25519_PUBLIC_KEY=" in c)
    assert line.endswith("ACCOUNT_ED25519_PUBLIC_KEY=first")


def test_the_version_sort_is_not_a_lexicographic_one() -> None:
    """`sort -V` puts 0.8.10 AFTER 0.8.9; `sorted()` puts it before. The staged tree is the only section that can see which one was copied to the stable name."""
    tree = split_golden(frozen.read(SLUG, "two-tarballs-version-sort"))[4]
    assert "cli-npm/rediacc-cli-latest.tgz\trediacc-cli-0.8.10.tgz\n" in tree
    assert max(("rediacc-cli-0.8.9.tgz", "rediacc-cli-0.8.10.tgz")) == "rediacc-cli-0.8.9.tgz", (
        "the case stopped being a trap for lexicographic ordering"
    )


def test_the_failing_commands_status_is_not_flattened() -> None:
    """`set -e` ends the twin with the FAILING command's status. A port that returned 1 everywhere would be wrong on the case an operator actually hits: a docker daemon that is not running."""
    assert split_golden(frozen.read(SLUG, "docker-buildx-refuses"))[0] == 125
    assert split_golden(frozen.read(SLUG, "npm-run-build-fails"))[0] == 7


# ---------------------------------------------------------------------------
# The controls: these goldens can actually fail
# ---------------------------------------------------------------------------


def test_a_planted_build_arg_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """Swap the account entry for the variant name, which is what a reader collapsing two near-identical strings would do. It is invisible on stdout and visible in the call log alone."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    anchor = '            "ACCOUNT_ENTRY=%s" % account_entry,\n'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    planted = source.replace(anchor, '            "ACCOUNT_ENTRY=%s" % variant,\n')
    root, args, kw = build(tmp_path, "a-complete-staging-run", port_source=planted)
    with pytest.raises(AssertionError):
        compare(root, "a-complete-staging-run", args, **kw)
    clean = build(tmp_path / "clean", "a-complete-staging-run")
    compare(clean[0], "a-complete-staging-run", clean[1], **clean[2])
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == source


def test_a_planted_lexicographic_sort_is_caught(tmp_path: pathlib.Path) -> None:
    """Drop `sort -V` for Python's own ordering, which is the simplification a reader would make on sight and which every section except the staged tree is blind to."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    anchor = "    newest = sort.stdout.splitlines()[-1]\n"
    assert source.count(anchor) == 1, "the plant's anchor moved"
    planted = source.replace(anchor, "    newest = names[-1]\n")
    root, args, kw = build(tmp_path, "two-tarballs-version-sort", port_source=planted)
    with pytest.raises(AssertionError):
        compare(root, "two-tarballs-version-sort", args, **kw)
    clean = build(tmp_path / "clean", "two-tarballs-version-sort")
    compare(clean[0], "two-tarballs-version-sort", clean[1], **clean[2])
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == source


def test_the_location_prefix_mask_hides_a_prefix_that_was_really_there() -> None:
    """THE CONTROL ON `LOCATION_RE`. Every compared golden has the prefix already stripped, so on its own the mask is indistinguishable from a mask that matches nothing. This golden holds the twin's bytes for the same case with only `$0` and the root masked, and the prefix is visible in them."""
    raw = split_golden(frozen.read(SLUG, RAW_CASE))
    stripped = split_golden(frozen.read(SLUG, "docker-is-absent-entirely"))
    assert raw[2].startswith("<SELF>: line "), "the twin printed no location prefix: %r" % raw[2]
    assert raw[2].endswith("docker: command not found\n")
    assert LOCATION_RE.sub("", raw[2]) == stripped[2]
    assert raw[2] != stripped[2], "the mask matched nothing, so it is proving nothing"
    assert raw[0] == stripped[0] == 127


def test_the_recorded_bytes_are_not_a_hash_of_themselves() -> None:
    """A last anti-vacuity guard on the corpus: no two goldens may be byte-identical, which is what a recorder that wrote the same case fourteen times would produce."""
    seen: dict[str, str] = {}
    for name in (*CASES, RAW_CASE):
        digest = hashlib.sha256(frozen.read(SLUG, name).encode("utf-8")).hexdigest()
        assert digest not in seen, "%s and %s recorded identical bytes" % (name, seen[digest])
        seen[digest] = name
