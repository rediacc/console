#!/usr/bin/env python3
"""Port of `.ci/scripts/build/extract-renet-from-image.sh` (243 lines).

THE CACHED FAST PATH for renet. When CI decides a renet image already exists
(`renet_exists=true`) it does not rebuild renet from source; it creates a
throwaway container from `<registry>/renet:<tag>` and copies the artifacts out:

  1. `renet-linux-amd64` and `renet-linux-arm64` into `private/bin/`.
  2. Every third-party asset the embed lockfile declares, into the PER-ARCH,
     PER-CLASS layout `pkg/embed/assets/<arch>/<class>/`, zstd-compressed.
  3. The proxy compose, staged through `private/renet/build.sh embed_proxy`.
  4. Cross-compiled `darwin` and `windows` renet binaries, built from the tree
     with the assets from step 2 embedded.
  5. `checksums.sha256` over everything in the output directory.

THE LOCKFILE IS THE SOURCE OF TRUTH for step 2, and the twin's own comments say why: this script used to carry its own REQUIRED/OPTIONAL split that disagreed
with `build.sh`'s, which is how the CSI sidecars ended up mandatory in one place
and optional in the other. The component list, its per-arch coverage, the image directory each lives in and its base/cluster class all come out of `private/renet/embed-assets.lock.json`. That reasoning is the twin's; it is not restated here beyond naming it.

WHY THE PER-ARCH LAYOUT MATTERS, also the twin's: a FLAT `assets/` directory is what silently shipped assetless darwin/windows binaries, because the per-arch `go:embed` directives found nothing and `ops up` failed with "embedded assets missing".

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT, all of them the twin's contract with the machine:

  * `docker create` / `docker cp` / `docker rm` (`:57`, `:68`, `:71`, `:164`,
    `:61`).
  * `jq`, twice per shape: once for the whole component matrix as TSV (`:182`)
    and once per asset for the declared version (`:122`). Kept as jq rather than
    `json.load` so the ROW ORDER, the `keys[]` sort and the `// ""` default stay
    in one place. The matrix filter is also the exact text `build.sh` reads, and
    a second spelling of it would be a second source of truth.
  * `zstd -19 -T0 -q --rm -f` (`:178`).
  * `strings -a` (`:135-136`).
  * `private/renet/build.sh embed_proxy` (`:211`) -- the single owner of that
    step. The twin deliberately does NOT delegate the ASSET staging to
    `build.sh embed_assets`, because its strictness would fail this path on a
    legitimately older cached image; only the proxy step is delegated.
  * `go build` (`:218-222`, `:230-234`), four times, with `CGO_ENABLED=0` and
    per-target `GOOS`/`GOARCH`.
  * `ls -la` (`:205`, `:242`) and `sha256sum` (`:239`). Their stdout IS the
    script's output, so they are run rather than reimplemented.

NOT SHELLED OUT: `grep -oE` / `grep -xE` / `sed` / `sort -u` inside the version check, which are `re` and `sorted(set(...))`; `mkdir -p`, `rm -f`, the glob expansions and the `-f` tests. The grep divergence is real and named: on a machine with no `grep` the twin's pipeline collapses to an empty result and the check degrades to a warning (see DEFECT 1, which reaches the same end by
a different door), while this port still answers. The scratch PATH the differential runs on carries a real `grep`, so both sides agree there.

-----------------------------------------------------------------------------
DEFECTS CARRIED, NOT FIXED
-----------------------------------------------------------------------------
DEFECT 1, THE VERSION CHECK IS DISARMED BY A MISSING `strings`, SILENTLY. `:94-95` require `jq` and `zstd`. Nothing requires `strings`, and `:135-136` redirect its stderr to `/dev/null`, which also swallows bash's own `strings: command not found`. With `strings` absent the collected set is empty, `:147-150` reports `no version string found; cannot verify` as a WARNING and returns
0, and the run completes. Driven, with a container whose criu really is the stale 3.17.1 the lockfile forbids:

    (strings present)  x criu-linux-amd64 declares version(s) [3.17.1] but the
                         lockfile requires 4.2.1                        rc=1
    (strings absent)   ! criu-linux-amd64: no version string found;
                         cannot verify against lockfile (4.2.1)         rc=0

That is UNKNOWN folded into FINE, on the one component the twin's own comment says actually drifted: "arm64 criu shipped 3.17.1 for months while every inventory declared 4.2.x". The warning is honest; the exit code is not. Carried unchanged.

DEFECT 2, THERE IS NO `-h` / `--help` ARM. `:34-37` sends anything unrecognised to `log_error "Unknown option: $1"; exit 1`, so `--help` is an error here while both sibling build scripts print a usage and exit 0. Driven:
`extract-renet-from-image.sh --help` -> `x Unknown option: --help`, rc=1.

DEFECT 3, `docker` IS NEVER `require_cmd`ed. `jq` and `zstd` are; `docker`, which the script cannot do anything without, is not, so a machine without it dies at `:57` with bash's `command not found` (rc 127) instead of the house refusal.

DEFECT 4, A FAILED `docker cp` MEANS "the image does not carry this asset" AND NOTHING ELSE. `:164` suppresses stderr and reads only the status, so a daemon that died mid-run reports every remaining asset as MISSING FROM THE IMAGE and tells the operator to rebuild it. The verdict is at least a failure rather than a pass, which is why it is listed last.

-----------------------------------------------------------------------------
ENVIRONMENT
-----------------------------------------------------------------------------
This script reads NO environment variables of its own. `CGO_ENABLED`, `GOOS` and `GOARCH` are SET for the `go build` children (`:218`, `:230`) and never read, so they are passed in the child's env dict and are deliberately not `os.environ.get` call sites.
"""

from __future__ import annotations

import glob as globmod
import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `:17`.
DEFAULT_REGISTRY = "ghcr.io/rediacc"

# `:68`, `:71`. The two binaries that come straight out of `/opt/renet/`.
RENET_LINUX_BINARIES = ("renet-linux-amd64", "renet-linux-arm64")

# `:182-190`, verbatim. One filter, shared with `build.sh`, emitting `<assetBase>\t<imageDir>\t<arch>\t<class>` per row.
MATRIX_FILTER = """
    .components
    | to_entries[]
    | .value as $c
    | $c.arches
    | keys[]
    | [$c.assetBase, $c.imageDir, ., $c.class]
    | @tsv
"""

# `:122`.
VERSION_FILTER = '.components[$b].version // ""'

# `:135-136`. The amd64 build carries the build path `/build/criu-<version>`;
# the arm64 cross-build carries a bare `<version>` string. BOTH are collected, because a pattern matching only one would leave the other unverified, and the other is the arch that drifted.
CRIU_BUILD_PATH_RE = re.compile(r"/build/criu-[0-9][0-9.]*")
CRIU_BARE_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+(\.[0-9]+)?$")

# `:120-145`. criu is the only component whose version is reliably greppable out of the binary; for the rest the digest-pinned fetch in the Dockerfile is the guarantee, and the twin returns success rather than pretending to check.
CHECKABLE_COMPONENTS = ("criu",)

# `:216-234`. The two cross-compile families, in the twin's order, with the suffix each target's output carries.
CROSS_TARGETS = (
    ("Darwin", "darwin", ""),
    ("Windows", "windows", ".exe"),
)
CROSS_ARCHES = ("amd64", "arm64")

# The lines bash names in a `set -u` death when an option's value is missing.
# These are the lines of the ASSIGNMENTS -- `TAG="$2"` (`:23`),
# `OUTPUT_DIR="$2"` (`:27`), `REGISTRY="$2"` (`:31`) -- not of the `case` labels
# above them, and the three gaps are not uniform because the `--tag` arm has no blank line before it. Each is established by DRIVING the twin in the differential, not by counting lines in a reading.
UNBOUND_LINES = {"--tag": 23, "--output": 27, "--registry": 31}


def console_root() -> pathlib.Path:
    """The repository root, from this file's own location.

    `get_repo_root` (common.sh:205-210) has no environment override, so `paths.repo_root()` is deliberately not used here; see the same note in `build/build_cli_musl.py`.
    """
    # This file: <root>/.ci/rediacc_ci/build/extract_renet_from_image.py
    return pathlib.Path(__file__).resolve().parents[3]


def parse_args(argv: list[str]) -> tuple[str, str, str, int | None, str]:
    """`:20-39`. Returns `(tag, output_dir, registry, exit_code, message)`.

    There is no `-h`/`--help` arm; see DEFECT 2. A missing option VALUE dies the way bash's `set -u` does, naming the script and the line of the `"$2"` it could not expand.
    """
    tag = ""
    output_dir = ""
    registry = DEFAULT_REGISTRY
    i = 0
    while i < len(argv):
        opt = argv[i]
        if opt in UNBOUND_LINES:
            if i + 1 >= len(argv):
                return (
                    tag,
                    output_dir,
                    registry,
                    1,
                    "%s: line %d: $2: unbound variable" % (sys.argv[0], UNBOUND_LINES[opt]),
                )
            value = argv[i + 1]
            if opt == "--tag":
                tag = value
            elif opt == "--output":
                output_dir = value
            else:
                registry = value
            i += 2
        else:
            return (tag, output_dir, registry, 1, "Unknown option: %s" % opt)
    return (tag, output_dir, registry, None, "")


def bash_glob(pattern: str, cwd: pathlib.Path) -> list[str]:
    """A bash glob, producing the exact STRINGS bash would hand the command.

    Two properties, both observable in this script's output:

      * With no `nullglob`, a pattern that matches nothing is passed through
        LITERALLY. That is why `:205` needs `2>/dev/null || true`: `ls` is asked
        about a file whose name contains `*`.
      * An ABSOLUTE pattern expands to absolute paths and a RELATIVE one to
        paths relative to the cwd, so `ls -la "$EMBED_DIR"/*/*/*.zst` prints full
        paths while `ls -la renet-*` after `cd "$OUTPUT_DIR"` prints bare names.
        `glob.glob(..., root_dir=)` has exactly that behaviour.

    Results are sorted, which under `LC_ALL=C` is byte order.
    """
    matches = sorted(globmod.glob(pattern, root_dir=str(cwd)))
    return matches or [pattern]


def _capture(command: list[str], **kw) -> tuple[int, str]:
    """`$(cmd)`: stdout consumed, stderr inherited, trailing newlines stripped."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        proc = subprocess.run(command, check=False, stdout=subprocess.PIPE, text=True, **kw)
    except PermissionError:
        return 126, ""
    except OSError:
        return 127, ""
    return proc.returncode, proc.stdout.rstrip("\n")


def _run(command: list[str], **kw) -> int:
    """A child whose streams the caller inherits unless told otherwise."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(command, check=False, **kw).returncode
    except PermissionError:
        return 126
    except OSError:
        return 127


def _strings(path: pathlib.Path) -> str:
    """`strings -a "$file" 2>/dev/null`, once.

    The `2>/dev/null` also swallows bash's own `strings: command not found`, so an absent binary is indistinguishable from one that found nothing. That is DEFECT 1's whole mechanism, and the `except OSError: return ""` here is the faithful reproduction of it rather than a repair.
    """
    with open(os.devnull, "wb") as sink:
        try:
            proc = subprocess.run(
                ["strings", "-a", str(path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=sink,
            )
        except OSError:
            return ""
    return proc.stdout.decode("utf-8", errors="replace")


def criu_versions(path: pathlib.Path) -> list[str]:
    """`:133-138`. Every version string the binary carries, sorted and unique.

    `strings` IS RUN TWICE, ONCE PER PATTERN, and that is not an oversight to be
    optimised away. The twin's `{ ...; ...; } | sort -u` is two independent
    pipelines, each opening its own `strings -a`, and the differential compares the recording fake's CALL LOG: a single-invocation port produced one `FAKEBIN strings` line where the twin produced two, and the suite failed on exactly that. The number of times a script executes a program is behaviour.
    """
    # `strings -a "$file" | grep -oE '/build/criu-[0-9][0-9.]*' | sed 's|.*/build/criu-||'`
    found: set[str] = set()
    for match in CRIU_BUILD_PATH_RE.findall(_strings(path)):
        found.add(match.rsplit("/build/criu-", 1)[1])
    # `strings -a "$file" | grep -xE '[0-9]+\\.[0-9]+(\\.[0-9]+)?'`, a WHOLE-LINE match, which is why `v4.2.1` and `4.2.1-rc` are not versions here.
    for line in _strings(path).splitlines():
        if CRIU_BARE_VERSION_RE.match(line):
            found.add(line)
    # `sort -u`, which under `LC_ALL=C` on digit-and-dot strings is `sorted`.
    return sorted(found)


def verify_extracted_version(
    lockfile: pathlib.Path, path: pathlib.Path, base: str, arch: str
) -> tuple[bool, str | None, str | None]:
    """`_verify_extracted_version` (`:120-156`).

    Returns `(ok, warning, error)`. `ok` is False only when a version was found and it is not the one the lockfile declares; a component with no declared version, a component that is not greppable, and a binary from which nothing could be read all return True, the last of them with a warning. That last
    case is DEFECT 1.
    """
    code, want = _capture(
        ["jq", "-r", "--arg", "b", base, VERSION_FILTER, str(lockfile)],
    )
    if code != 0 or not want:
        return True, None, None
    if base not in CHECKABLE_COMPONENTS:
        return True, None, None
    found = criu_versions(path)
    if not found:
        return (
            True,
            "%s-linux-%s: no version string found; cannot verify against lockfile (%s)"
            % (base, arch, want),
            None,
        )
    if want in found:
        return True, None, None
    return (
        False,
        None,
        "%s-linux-%s declares version(s) [%s] but the lockfile requires %s"
        % (base, arch, " ".join(found), want),
    )


def main(argv: list[str]) -> int:
    tag, output_dir, registry, code, message = parse_args(argv)
    if code is not None:
        if message.startswith("Unknown option: "):
            log.error(message)
        else:
            print(message, file=sys.stderr, flush=True)
        return code

    # `:42-45`.
    if not tag:
        log.error("--tag is required")
        return 1

    # `:47-49`.
    root = console_root()
    output = pathlib.Path(output_dir) if output_dir else root / "private" / "bin"
    renet_image = "%s/renet:%s" % (registry, tag)

    # `:51`.
    log.step("Extracting renet binaries from %s" % renet_image)

    # `:53`.
    output.mkdir(parents=True, exist_ok=True)

    # `:56-57`.
    log.info("Creating temporary container...")
    code, container_id = _capture(["docker", "create", renet_image])
    if code != 0:
        # `set -e` on a failing command substitution in an assignment. DEFECT 3 means a missing docker arrives here as 127 rather than as a refusal.
        return code

    # `:59-64`. `trap cleanup EXIT`, which fires on every exit below.
    try:
        return _extract(root, output, container_id)
    finally:
        with open(os.devnull, "wb") as sink:
            _run(["docker", "rm", container_id], stdout=sink, stderr=sink)


def _extract(root: pathlib.Path, output: pathlib.Path, container_id: str) -> int:
    """Everything the twin does between `trap cleanup EXIT` (`:64`) and the end, split out only so the trap's `try/finally` reads as one statement."""
    # `:66-71`.
    for name in RENET_LINUX_BINARIES:
        log.info("Extracting %s..." % name)
        code = _run(["docker", "cp", "%s:/opt/renet/%s" % (container_id, name), "%s/" % output])
        if code != 0:
            return code

    # `:74`. `cd "$OUTPUT_DIR" && pwd` is bash's LOGICAL pwd, which normalises without resolving symlinks; `os.path.abspath` is the same operation.
    output = pathlib.Path(os.path.abspath(output))

    # `:91-95`.
    log.step("Staging embedded assets (per-arch, per-class) from container...")
    embed_dir = root / "private" / "renet" / "pkg" / "embed" / "assets"
    lockfile = root / "private" / "renet" / "embed-assets.lock.json"
    for tool in ("jq", "zstd"):
        try:
            common.require_cmd(tool)
        except common.RefusalError as exc:
            exc.report()
            return exc.code

    # `:96-99`.
    if not lockfile.is_file():
        log.error("embed lockfile not found: %s" % lockfile)
        return 1

    # `:106`. Start clean so the embedded set is EXACTLY what this image carries. The glob depth tracks the staged layout; one level too shallow matches nothing and leaves stale payloads in place.
    for stale in embed_dir.glob("*/*/*.zst"):
        stale.unlink(missing_ok=True)

    # `:182-190`.
    code, matrix = _capture(["jq", "-r", MATRIX_FILTER, str(lockfile)])
    if code != 0:
        return code

    # `:160-190`.
    missing: list[str] = []
    mismatched: list[str] = []
    for row in matrix.split("\n"):
        # `IFS=$'\t' read -r base image_dir arch class`: fields beyond the last
        # name are folded into it and absent ones read as empty, so a short row never raises here either.
        fields = [*row.split("\t"), "", "", "", ""][:4]
        base, image_dir, arch, klass = fields
        # `[[ -n "$base" ]] || continue`.
        if not base:
            continue
        asset = "%s-linux-%s" % (base, arch)
        target_dir = embed_dir / arch / klass
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / asset
        with open(os.devnull, "wb") as sink:
            code = _run(
                ["docker", "cp", "%s:%s/%s" % (container_id, image_dir, asset), str(target)],
                stderr=sink,
            )
        if code != 0:
            # DEFECT 4: every non-zero status reads as "the image lacks it".
            missing.append(asset)
            continue
        ok, warning, error = verify_extracted_version(lockfile, target, base, arch)
        if warning is not None:
            log.warn(warning)
        if error is not None:
            log.error(error)
        if not ok:
            mismatched.append(asset)
        code = _run(["zstd", "-19", "-T0", "-q", "--rm", "-f", str(target)])
        if code != 0:
            return code

    # `:192-196`.
    if missing:
        log.error(
            "Cached renet image is missing assets the lockfile declares:%s"
            % "".join(" %s" % a for a in missing)
        )
        log.error("Rebuild it with: (cd private/renet && ./build.sh docker_image)")
        return 1

    # `:198-202`.
    if mismatched:
        log.error(
            "Cached renet image carries assets at versions the lockfile does not declare:%s"
            % "".join(" %s" % a for a in mismatched)
        )
        log.error(
            "The image predates the current pins. Rebuild it with: "
            "(cd private/renet && ./build.sh docker_image --force)"
        )
        return 1

    # `:204-205`.
    log.info("Embedded assets (per-arch, per-class):")
    with open(os.devnull, "wb") as sink:
        _run(["ls", "-la", *bash_glob("%s/*/*/*.zst" % embed_dir, root)], stderr=sink)

    # `:210-211`. `embed_proxy` stages ONLY the proxy compose; the datastore README is a tracked embed file and must NOT be overwritten.
    renet_dir = root / "private" / "renet"
    log.step("Staging proxy compose for embedding...")
    code = _run(["./build.sh", "embed_proxy"], cwd=str(renet_dir))
    if code != 0:
        return code

    # `:213-235`.
    for label, goos, suffix in CROSS_TARGETS:
        log.step("Cross-compiling renet %s binaries..." % label)
        for arch in CROSS_ARCHES:
            name = "renet-%s-%s%s" % (goos, arch, suffix)
            log.info("Building renet-%s-%s..." % (goos, arch))
            child_env = dict(os.environ)
            child_env["CGO_ENABLED"] = "0"
            child_env["GOOS"] = goos
            child_env["GOARCH"] = arch
            code = _run(
                [
                    "go",
                    "build",
                    "-ldflags=-s -w",
                    "-o",
                    str(output / name),
                    "./cmd/renet",
                ],
                cwd=str(renet_dir),
                env=child_env,
            )
            if code != 0:
                return code

    # `:237-239`. `cd "$OUTPUT_DIR"` for the rest, so every path is a basename.
    log.step("Generating checksums...")
    with open(output / "checksums.sha256", "wb") as dest:
        code = _run(["sha256sum", *bash_glob("renet-*", output)], stdout=dest, cwd=str(output))
    if code != 0:
        return code

    # `:241-243`.
    log.info("Renet binaries ready:")
    _run(["ls", "-la", *bash_glob("renet-*", output)], cwd=str(output))
    sys.stdout.flush()
    sys.stdout.write((output / "checksums.sha256").read_text(encoding="utf-8", errors="replace"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
