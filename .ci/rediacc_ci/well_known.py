"""The well-known values, read from `.ci/config/well-known.env`, the only place they are written.

Use it as `from rediacc_ci.well_known import RELEASES_ORIGIN`. Every name below is the registry key without its `WK_` prefix, and `check:ci-literal-sources` (rediacc_ci.quality.literal_sources, R4) holds the set of names here equal to the set of keys in the file, in both directions, so a key added there without a line here (or the reverse) is a finding rather than an `AttributeError` waiting in some rarely-run release path.

WHY THE NAMES ARE TYPED OUT AND THE VALUES ARE NOT. A module that set its globals from the file in a loop would hand mypy nothing to check, and every `from rediacc_ci.well_known import X` would be an untyped import. The names are a contract with the importers and are checked against the registry; the values are facts and are read, never restated.

THE FILE IS FOUND FROM THIS MODULE, NOT FROM `paths.repo_root()`. `$REDIACC_CI_ROOT` points a gate at a fixture tree; it must not change what production's release origin is, and it must not make the first import of this module fail because a fixture did not copy `.ci/config/`. A test that needs a different value monkeypatches the importer's name, which is what it would do for any other constant.

A MISSING FILE IS A LOUD FAILURE AT IMPORT, naming the file. A sparse checkout that leaves `.ci/config/` out gets that message instead of a `KeyError` three calls deep; the fix is to add `.ci/config/well-known.env` to the cone.
"""

from __future__ import annotations

import pathlib
import re

REGISTRY_REL = ".ci/config/well-known.env"
REGISTRY_PATH = pathlib.Path(__file__).resolve().parent.parent / "config" / "well-known.env"

_KEY = re.compile(r"^WK_[A-Z][A-Z0-9_]*$")
# toolchain.env's format: no quotes, no `$`, no whitespace, so bash, Docker, $GITHUB_ENV and this parser read the same bytes.
_VALUE = re.compile(r"^[^\s'\"$`\\]+$")


class RegistryError(RuntimeError):
    """The registry is absent or not in the one format every reader accepts."""


def parse(text: str, source: str = REGISTRY_REL) -> dict[str, str]:
    """`WK_NAME -> value` for every assignment in `text`, in file order. Raises on anything a bash `set -a; .` would read differently."""
    values: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not _KEY.match(key):
            raise RegistryError("%s:%d: not a WK_NAME=value line: %r" % (source, number, raw))
        if not _VALUE.match(value):
            raise RegistryError(
                "%s:%d: %s has a value with quotes, `$`, a backslash or whitespace; bash, Docker and "
                "$GITHUB_ENV would each read it differently: %r" % (source, number, key, value)
            )
        if key in values:
            raise RegistryError("%s:%d: %s is assigned twice" % (source, number, key))
        values[key] = value
    if not values:
        raise RegistryError(
            "%s declares nothing; every reader of it would be reading nothing" % source
        )
    return values


def load(path: pathlib.Path = REGISTRY_PATH) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RegistryError(
            "%s is missing (looked for %s). It holds every well-known origin, bucket and address; "
            "a sparse checkout must include .ci/config/well-known.env." % (REGISTRY_REL, path)
        ) from None
    return parse(text, REGISTRY_REL)


VALUES: dict[str, str] = load()


def _get(key: str) -> str:
    try:
        return VALUES[key]
    except KeyError:
        raise RegistryError(
            "%s no longer declares %s, which rediacc_ci.well_known exports" % (REGISTRY_REL, key)
        ) from None


# One line per registry key, in the registry's order. The gate refuses a mismatch in either direction.
RELEASES_ORIGIN: str = _get("WK_RELEASES_ORIGIN")
SITE_ORIGIN: str = _get("WK_SITE_ORIGIN")
EDGE_ORIGIN: str = _get("WK_EDGE_ORIGIN")
MEDIA_ORIGIN: str = _get("WK_MEDIA_ORIGIN")
BENCH_ORIGIN: str = _get("WK_BENCH_ORIGIN")
SANDBOX_ORIGIN: str = _get("WK_SANDBOX_ORIGIN")
PROFILING_ORIGIN: str = _get("WK_PROFILING_ORIGIN")
ACCOUNT_DEFAULT_ORIGIN: str = _get("WK_ACCOUNT_DEFAULT_ORIGIN")
CONSOLE_ORIGIN: str = _get("WK_CONSOLE_ORIGIN")
CLOUD_ORIGIN: str = _get("WK_CLOUD_ORIGIN")
APEX_DOMAIN: str = _get("WK_APEX_DOMAIN")
INFRA_DOMAIN: str = _get("WK_INFRA_DOMAIN")
RELEASES_BUCKET: str = _get("WK_RELEASES_BUCKET")
GH_REPO: str = _get("WK_GH_REPO")
RENET_REPO: str = _get("WK_RENET_REPO")
ACCOUNT_REPO: str = _get("WK_ACCOUNT_REPO")
ELITE_REPO: str = _get("WK_ELITE_REPO")
HOMEBREW_TAP_REPO: str = _get("WK_HOMEBREW_TAP_REPO")
HOMEBREW_TAP: str = _get("WK_HOMEBREW_TAP")
IMAGE_REGISTRY: str = _get("WK_IMAGE_REGISTRY")
WEB_IMAGE_REPO: str = _get("WK_WEB_IMAGE_REPO")
DEVBOX_UID_IMAGE_REPO: str = _get("WK_DEVBOX_UID_IMAGE_REPO")
DATASTORE_PATH: str = _get("WK_DATASTORE_PATH")
RUNTIME_DIR: str = _get("WK_RUNTIME_DIR")
ETC_DIR: str = _get("WK_ETC_DIR")
OPT_DIR: str = _get("WK_OPT_DIR")
CONTACT_EMAIL: str = _get("WK_CONTACT_EMAIL")
SUPPORT_EMAIL: str = _get("WK_SUPPORT_EMAIL")
PKG_MAINTAINER_EMAIL: str = _get("WK_PKG_MAINTAINER_EMAIL")
PKG_SIGNING_KEY_NAME: str = _get("WK_PKG_SIGNING_KEY_NAME")
ADMIN_EMAIL_DEFAULT: str = _get("WK_ADMIN_EMAIL_DEFAULT")
DEV_USER_EMAIL: str = _get("WK_DEV_USER_EMAIL")
OPERATOR_EMAIL: str = _get("WK_OPERATOR_EMAIL")
ACCOUNT_DEV_PORT: int = int(_get("WK_ACCOUNT_DEV_PORT"))
CF_API_BASE: str = _get("WK_CF_API_BASE")
GH_ORIGIN: str = _get("WK_GH_ORIGIN")
GH_API_BASE: str = _get("WK_GH_API_BASE")
GO_DL_BASE: str = _get("WK_GO_DL_BASE")
UBUNTU_ARCHIVE: str = _get("WK_UBUNTU_ARCHIVE")
UBUNTU_AZURE_MIRROR: str = _get("WK_UBUNTU_AZURE_MIRROR")
DOCKER_INSTALL_DOCS: str = _get("WK_DOCKER_INSTALL_DOCS")
CLAUDE_CODE_URL: str = _get("WK_CLAUDE_CODE_URL")
