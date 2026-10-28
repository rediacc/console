"""Where each renet dev-build flavor lives: the one Python home of the flavor-to-path mapping.

`private/renet/build.sh dev` writes a `nolicense` build to `bin/` and an enforcing one to `bin/enforce/`, so a build of one flavor never overwrites the other's binaries. Every function here is pure: no `os.environ` read, so the env registry entries stay on the files that read the environment.
"""

import os
import re

FLAVORS = ("nolicense", "enforce")
SUBDIR = {"nolicense": "bin", "enforce": "bin/enforce"}
STAMP_NAME = ".renet-build-stamp"


def flavor_for(license_env: str | None, args: list[str] | tuple[str, ...] = ()) -> str:
    """build.sh's precedence: `RDC_RENET_LICENSE=1` selects enforcement, then the last `--license` or `--nolicense` wins."""
    flavor = "enforce" if license_env == "1" else "nolicense"
    for arg in args:
        if arg == "--nolicense":
            flavor = "nolicense"
        elif arg == "--license":
            flavor = "enforce"
    return flavor


def build_flag(flavor: str) -> str:
    return "--license" if flavor == "enforce" else "--nolicense"


def _dir(renet_dir: str, flavor: str) -> str:
    return os.path.join(renet_dir, *SUBDIR[flavor].split("/"))


def binary(renet_dir: str, flavor: str, exe: str = "") -> str:
    """The host binary of `flavor`; `exe` is the platform suffix (`.exe` on Windows, else empty)."""
    return os.path.join(_dir(renet_dir, flavor), "renet" + exe)


def linux_binaries(renet_dir: str, flavor: str) -> list[str]:
    return [
        os.path.join(_dir(renet_dir, flavor), "renet-linux-%s" % arch)
        for arch in ("amd64", "arm64")
    ]


def stamp_path(renet_dir: str, flavor: str) -> str:
    return os.path.join(_dir(renet_dir, flavor), STAMP_NAME)


def buildinfo_flavor(go_version_m_text: str) -> str:
    """`nolicense` or `enforce` from `go version -m <binary>` output, `""` when the text carries no build line."""
    if not re.search(r"^\s*build\s", go_version_m_text, re.MULTILINE):
        return ""
    if re.search(r"-tags=\S*nolicense", go_version_m_text):
        return "nolicense"
    return "enforce"


def flavor_refusal(want: str, info: str) -> str | None:
    """None when the `go version -m` text `info` describes a `want` build, else the reason it does not."""
    got = buildinfo_flavor(info)
    if got != want:
        return "binary is %s, expected %s" % (got or "of unknown flavor", want)
    if want == "enforce" and "ProductionPublicKey=" not in info:
        return "enforcing binary carries no baked account public key"
    return None
