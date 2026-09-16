#!/usr/bin/env python3
"""Port of `.ci/scripts/build/prepare-cli-assets.sh` (228 lines).

Stages everything the CLI's SEA build embeds: the renet binaries the target
platform needs, a `renet-metadata.json` describing them, the third-party credits
inventory, a generated `THIRD_PARTY_LICENSES`, and a platform-specific
`sea-config.generated.json` listing all of it.

WHICH BINARIES, and why. Every platform embeds BOTH Linux binaries, because the
CLI provisions remote Linux machines from wherever it runs. macOS additionally
embeds its own `darwin-<arch>` for local renet execution, and Windows its own
`windows-<arch>`. The Windows binary is `renet-windows-<arch>.exe` ON DISK and
`renet-windows-<arch>` as a SEA asset key, so the copy renames it.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT:

  * `date -u +%Y-%m-%dT%H:%M:%SZ` (`:171`) -- the metadata timestamp. Kept as a
    real `date` call rather than `datetime.now(UTC)` for one concrete reason:
    it is the only non-deterministic byte in the artifact, and a differential
    that cannot freeze it on BOTH sides identically cannot compare the file at
    all. A fake `date` on the scratch PATH pins both.
  * `jq -r '.version' packages/cli/package.json` (`:135`) -- the version
    fallback. jq's answer for a package.json with no `.version` is the string
    `null`, and that string reaches the metadata; a Python read would have to
    decide to reproduce that, so jq decides it instead.
  * `sha256sum` / `shasum -a 256` (`:146-155`) -- including the `command -v`
    probe that chooses between them, and the refusal when neither exists.
  * `npx tsx scripts/gen/generate-third-party-licenses.ts` (`:190-192`).

NOT SHELLED OUT: `jq -Rn` for WRITING the two JSON files. Both are built from
values this process already holds, and `json.dumps(obj, indent=2) + "\\n"` is
byte-identical to jq's default pretty-printer for these shapes; the differential
asserts that equality on the real artifacts rather than assuming it. Building
the objects as tab-separated text so a second program can parse them back is a
bash limitation, not behaviour. `stat -c%s` is `os.path.getsize`; `cp`,
`mkdir -p` and `wc -l` are likewise in-process.

-----------------------------------------------------------------------------
DEFECTS CARRIED, NOT FIXED
-----------------------------------------------------------------------------
DEFECT 1, `--arch` IS VALIDATED AND THE VERDICT IS THROWN AWAY. `map_arch`
(`:64-73`) ends its unknown-arch arm with `log_error` and `exit 1`. That `exit`
runs inside `$(map_arch "$arch")`, which runs inside `$(get_required_binaries
...)`, and **bash does not inherit errexit into a command-substitution
subshell**. Driven on bash 5.3.9 to be sure it is the nesting and not the
assignment:

    set -euo pipefail
    f(){ echo E >&2; exit 1; }
    g(){ local a; a=$(f); echo g-continued >&2; echo out; }
    g                       # dies, rc=1
    R=$( a=$(f); echo sub-continued >&2; echo out )   # SURVIVES, rc=0

So the script prints its refusal and carries straight on with an EMPTY
`renet_arch`:

    $ bash .ci/scripts/build/prepare-cli-assets.sh --platform linux --arch bogus
    -> Preparing CLI embedded assets for linux-bogus...
    x  Unknown arch: bogus
    ...
    ok CLI assets prepared successfully
    ; echo $? -> 0

For `--platform linux` the empty value is never used, so a typo'd arch produces
a complete, valid, silently-mislabelled build. For `--platform mac` it becomes
the asset name `renet-darwin-`, which is missing, so that path dies at `:128`
with the wrong diagnostic. Reproduced exactly: the error is logged, the value is
empty, execution continues.

DEFECT 2, `--platform` IS NEVER VALIDATED AT ALL. The usage says
`linux|mac|win`; the code tests only `== "mac"` and `== "win"` (`:87`, `:91`).
`--platform banana --arch x64` builds the Linux-only asset set and exits 0.

DEFECT 3, THE ASSET COUNT IS OFF BY ONE, ALWAYS. `:211` is
`printf '%b' "$ASSET_LINES" | wc -l`, and `ASSET_LINES` has no trailing newline,
so `wc -l` counts SEPARATORS rather than entries. Note that `:213` -- the line
that feeds the same string to jq -- uses `printf '%b\\n'` WITH the newline, so
the file is right and only the report is wrong. Driven: `--platform linux`
writes five assets and prints `Generated sea-config with 4 assets`.

DEFECT 4, `Generated THIRD_PARTY_LICENSES` IS A CLAIM ABOUT AN EXIT CODE, NOT
ABOUT A FILE. `:190` branches on the generator's status alone. A generator that
exits 0 without writing anything leaves `sea-config.generated.json` pointing at
`dist/assets/THIRD_PARTY_LICENSES`, which does not exist, and the log says it
was generated. Driven with a stub `npx` that only exits 0: the success line
prints and the file is absent from `dist/assets/`.

-----------------------------------------------------------------------------
ENVIRONMENT IS READ AT THE CALL SITE
-----------------------------------------------------------------------------
`RENET_VERSION` is read once, with a literal
`os.environ.get("RENET_VERSION", "")`, where it is used. No alias and no loop:
`check:ci-python-env-registry` reads the AST and records a non-literal key as
the expression rather than the name.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `:64-73`. CI's arch spelling to renet's.
ARCH_MAP = {"x64": "amd64", "arm64": "arm64"}

# `:204-206`. The three non-binary assets, in the twin's order.
FIXED_ASSETS = (
    "renet-metadata.json",
    "third-party-credits.json",
    "THIRD_PARTY_LICENSES",
)

# `:190-192`.
GENERATOR_REL = "scripts/gen/generate-third-party-licenses.ts"

# `:196`.
LICENSES_PLACEHOLDER = (
    "THIRD_PARTY_LICENSES generation failed at build time. Regenerate with: "
    "npx tsx scripts/gen/generate-third-party-licenses.ts\n"
)

# The lines bash names in a `set -u` death when an option's value is missing:
# `SEA_PLATFORM="$2"` is `:32`, `SEA_ARCH="$2"` is `:36`. These are the lines of
# the ASSIGNMENT, not of the `case` label above it, and the differential drove
# the twin to establish which.
UNBOUND_LINES = {"--platform": 32, "--arch": 36}


def console_root() -> pathlib.Path:
    """The repository root, from this file's own location.

    Same reasoning as `build/build_cli_musl.py`: `get_repo_root`
    (common.sh:205-210) has no environment override, so `paths.repo_root()` --
    which honours `$REDIACC_CI_ROOT` -- would make one side of a differential
    follow a variable the other cannot see.
    """
    # This file: <root>/.ci/rediacc_ci/build/prepare_cli_assets.py
    return pathlib.Path(__file__).resolve().parents[3]


def map_arch(arch: str) -> tuple[str, str | None]:
    """`map_arch` (`:64-73`). Returns `(renet_arch, error_message)`.

    DEFECT 1 IS IN THE SIGNATURE. The twin's `exit 1` cannot escape its nested
    command substitution, so an unknown arch yields the error line AND an empty
    string AND continued execution. Returning both is how that is said in Python
    without pretending the refusal works.
    """
    mapped = ARCH_MAP.get(arch)
    if mapped is None:
        return "", "Unknown arch: %s" % arch
    return mapped, None


def required_binaries(platform: str, arch: str) -> tuple[list[str], str | None]:
    """`get_required_binaries` (`:78-94`). Returns `(names, error_message)`.

    Both Linux binaries always, plus the host's own on mac and win. `map_arch`
    is called UNCONDITIONALLY, before either test, so a bad `--arch` is reported
    even for `--platform linux` where its value is never used. That ordering is
    observable in the output and is kept.
    """
    renet_arch, error = map_arch(arch)
    names = ["linux-amd64", "linux-arm64"]
    if platform == "mac":
        names.append("darwin-%s" % renet_arch)
    # DEFECT 2: no `else`, and no rejection of anything that is neither.
    if platform == "win":
        names.append("windows-%s" % renet_arch)
    return names, error


def binary_to_meta_key(name: str) -> str:
    """`binary_to_meta_key` (`:99-105`). `linux-amd64` -> `amd64`; anything else
    keeps its full name, so `darwin-arm64` stays `darwin-arm64`."""
    if name.startswith("linux-"):
        return name[len("linux-") :]
    return name


def disk_name(name: str) -> str:
    """`:118-122`. Windows binaries carry `.exe` ON DISK and never as an asset
    key, so the source path and the destination name differ for exactly them."""
    if name.startswith("windows-"):
        return "renet-%s.exe" % name
    return "renet-%s" % name


def sea_config(asset_pairs: list[tuple[str, str]]) -> str:
    """`:213-224`. The generated sea-config, as bytes on disk.

    `json.dumps(..., indent=2)` reproduces jq's default pretty-printer exactly
    for this shape, including the trailing newline added here; the differential
    compares the two real files rather than trusting the claim.
    """
    return (
        json.dumps(
            {
                "main": "dist/cli-bundle.cjs",
                "output": "dist/sea-prep.blob",
                "disableExperimentalSEAWarning": True,
                "useSnapshot": False,
                "useCodeCache": False,
                "assets": dict(asset_pairs),
            },
            indent=2,
        )
        + "\n"
    )


def asset_count(asset_pairs: list[tuple[str, str]]) -> int:
    """`:211`, DEFECT 3 preserved. `printf '%b'` writes no trailing newline, so
    `wc -l` counts the separators between the entries, one fewer than there are.
    """
    return max(len(asset_pairs) - 1, 0)


def parse_args(argv: list[str]) -> tuple[str, str, int | None, str]:
    """`:29-48`. Returns `(platform, arch, exit_code, message)`.

    `exit_code` is `None` on success. `-h/--help` prints on STDOUT and exits 0;
    everything else is stderr. `--platform` or `--arch` as the final argument
    dies the way bash's `set -u` does, naming the script and the line of the
    `"$2"` it could not expand, before any `shift` happens.
    """
    platform = ""
    arch = ""
    i = 0
    while i < len(argv):
        opt = argv[i]
        if opt in ("--platform", "--arch"):
            if i + 1 >= len(argv):
                return (
                    platform,
                    arch,
                    1,
                    "%s: line %d: $2: unbound variable" % (sys.argv[0], UNBOUND_LINES[opt]),
                )
            if opt == "--platform":
                platform = argv[i + 1]
            else:
                arch = argv[i + 1]
            i += 2
        elif opt in ("-h", "--help"):
            return (
                platform,
                arch,
                0,
                "Usage: %s --platform <linux|mac|win> --arch <x64|arm64>" % sys.argv[0],
            )
        else:
            return (platform, arch, 1, "Unknown option: %s" % opt)
    return (platform, arch, None, "")


def _capture(command: list[str], **kw) -> tuple[int, str]:
    """A child whose STDOUT this process consumes and whose stderr it inherits,
    which is what `$(cmd)` does. Trailing newlines are stripped, as there."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        proc = subprocess.run(command, check=False, stdout=subprocess.PIPE, text=True, **kw)
    except PermissionError:
        return 126, ""
    except OSError:
        return 127, ""
    return proc.returncode, proc.stdout.rstrip("\n")


def file_sha256(path: pathlib.Path) -> tuple[str, str | None]:
    """`file_sha256` (`:146-155`). Returns `(hex, error_message)`.

    The `command -v` probe is the observable part: `sha256sum` first, `shasum -a
    256` second, and a refusal when neither exists. Unlike `map_arch`, this
    function's `exit 1` is reached from a TOP-LEVEL `$( )` (`:163`), where
    errexit does fire, so the refusal really does stop the script.
    """
    if shutil.which("sha256sum") is not None:
        argv = ["sha256sum", str(path)]
    elif shutil.which("shasum") is not None:
        argv = ["shasum", "-a", "256", str(path)]
    else:
        return "", "No sha256sum or shasum available"
    code, out = _capture(argv)
    if code != 0:
        return "", ""
    # `cut -d' ' -f1`.
    return out.split(" ", 1)[0], None


def main(argv: list[str]) -> int:
    platform, arch, code, message = parse_args(argv)
    if code is not None:
        if code == 0:
            print(message, flush=True)
        elif message.startswith("Unknown option: "):
            log.error(message)
        else:
            print(message, file=sys.stderr, flush=True)
        return code

    # `:50-53`.
    if not platform or not arch:
        log.error("Usage: %s --platform <linux|mac|win> --arch <x64|arm64>" % sys.argv[0])
        return 1

    # `:55`.
    try:
        common.require_cmd("jq")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    # `:57-60`.
    root = console_root()
    cli_dir = root / "packages" / "cli"
    assets_dir = cli_dir / "dist" / "assets"
    renet_bin_dir = root / "private" / "bin"

    # `:107`.
    log.step("Preparing CLI embedded assets for %s-%s..." % (platform, arch))

    # `:110`.
    assets_dir.mkdir(parents=True, exist_ok=True)

    # `:113`. DEFECT 1: the error is emitted and the run continues.
    names, arch_error = required_binaries(platform, arch)
    if arch_error is not None:
        log.error(arch_error)

    # `:116-131`.
    for name in names:
        source = renet_bin_dir / disk_name(name)
        if not source.is_file():
            log.error("Missing renet binary: %s" % source)
            return 1
        log.info("Copying renet-%s..." % name)
        # `cp` (`:126`) gives the new file the SOURCE's mode bits, which matters:
        # these are executables. `shutil.copyfile` would not, so `shutil.copy` is
        # the right analogue.
        shutil.copy(source, assets_dir / ("renet-%s" % name))

    # `:135`. `${RENET_VERSION:-...}`: unset and empty both fall through to jq.
    version = os.environ.get("RENET_VERSION", "")
    if not version:
        code, version = _capture(["jq", "-r", ".version", str(cli_dir / "package.json")])
        if code != 0:
            # `set -e` on a failing command substitution in an assignment.
            return code

    # `:138`.
    log.step("Generating renet metadata...")

    binaries: dict[str, dict[str, object]] = {}
    for name in names:
        local_file = assets_dir / ("renet-%s" % name)
        size = local_file.stat().st_size
        digest, sha_error = file_sha256(local_file)
        if sha_error is not None:
            log.error(sha_error)
            return 1
        binaries[binary_to_meta_key(name)] = {"size": size, "sha256": digest}
        log.info("  %s: %s bytes, sha256=%s" % (name, size, digest))

    # `:171`.
    code, generated_at = _capture(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"])
    if code != 0:
        return code

    # `:169-175`.
    metadata_path = assets_dir / "renet-metadata.json"
    metadata_path.write_text(
        json.dumps(
            {"version": version, "generatedAt": generated_at, "binaries": binaries},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # `:177-178`.
    log.info("Metadata written to %s" % metadata_path)
    log.info("  Version: %s" % version)

    # `:183-185`.
    log.step("Preparing third-party credits assets...")
    shutil.copy(
        cli_dir / "src" / "data" / "third-party-credits.json",
        assets_dir / "third-party-credits.json",
    )
    log.info("Copied third-party-credits.json")

    # `:190-198`. Best-effort and non-fatal by design: the Go-dependency section
    # needs network, so an offline build carries a marked placeholder. DEFECT 4:
    # only the status is consulted, never the file.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        status = subprocess.run(
            [
                "npx",
                "tsx",
                str(root / GENERATOR_REL),
                "--repo-root",
                str(root),
                "--output",
                str(assets_dir / "THIRD_PARTY_LICENSES"),
            ],
            check=False,
        ).returncode
    except PermissionError:
        status = 126
    except OSError:
        status = 127
    if status == 0:
        log.info("Generated THIRD_PARTY_LICENSES")
    else:
        log.warn("THIRD_PARTY_LICENSES generation failed; writing placeholder")
        (assets_dir / "THIRD_PARTY_LICENSES").write_text(LICENSES_PLACEHOLDER, encoding="utf-8")

    # `:201`.
    log.step("Generating platform-specific sea-config...")

    # `:204-209`.
    asset_pairs = [(name, "dist/assets/%s" % name) for name in FIXED_ASSETS]
    asset_pairs += [("renet-%s" % name, "dist/assets/renet-%s" % name) for name in names]

    # `:213-224`.
    (cli_dir / "sea-config.generated.json").write_text(sea_config(asset_pairs), encoding="utf-8")

    # `:226-228`. DEFECT 3 is in `asset_count`, not here.
    log.info("Generated sea-config with %d assets" % asset_count(asset_pairs))
    log.info("CLI assets prepared successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
