"""Company name validation for `enterprise add`.

A company gets `<company>.<product domain>` and `<company>-proxy.<product domain>`, so its name is one DNS label that must not collide with a region host, a service host or any other company's `-proxy` host. The reserved set is derived, not typed: region ids and every host label come from regions.json and the well-known registry, so a region added there is reserved here without an edit. Only the service words that name no region (the Worker and bucket families, channels, mail and web labels) are listed.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from urllib.parse import urlparse

from rediacc_ci import paths, well_known

MIN_LENGTH = 3
MAX_LENGTH = 30  # the `-proxy` host must still fit a 63-character label with room to spare

# Words that name a service or a channel rather than a region.
SERVICE_LABELS = frozenset(
    {
        "account", "accounts", "admin", "api", "app", "asia", "auth", "backups", "bench", "cdn", "configs",
        "console", "control", "dashboard", "dev", "docs", "edge", "enterprise", "executor", "ftp", "git",
        "help", "imap", "login", "mail", "media", "mta-sts", "notify", "ns", "ops", "ops-health", "portal", "proxy",
        "registry", "releases", "signer", "smtp", "stable", "static", "status", "support", "test", "www",
    }
)  # fmt: skip

_LABEL = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PROXY_SUFFIX = "-proxy"


class CompanyNameError(ValueError):
    """The company name is not usable; the message names the rule."""


def _host_label(value: str) -> str | None:
    host = urlparse(value if "://" in value else "//" + value).hostname or ""
    return host.split(".")[0] if "." in host else None


@lru_cache(maxsize=1)
def reserved() -> frozenset[str]:
    """Every label a company may not take: region ids, host labels from regions.json and well-known, and the service words."""
    names: set[str] = set(SERVICE_LABELS)
    data = json.loads((paths.repo_root() / "regions.json").read_text())
    for region in data["regions"]:
        names.add(str(region["id"]))
        for value in region.values():
            if isinstance(value, str):
                label = _host_label(value)
                if label:
                    names.add(label)
    for key, value in vars(well_known).items():
        if key.isupper() and isinstance(value, str):
            label = _host_label(value)
            if label:
                names.add(label)
    expanded: set[str] = set()
    for name in names:
        expanded.add(name)
        for prefix in ("edge-", "stable-"):
            if name.startswith(prefix):
                expanded.add(name[len(prefix) :])
        if name.endswith(PROXY_SUFFIX):
            expanded.add(name[: -len(PROXY_SUFFIX)])
    return frozenset(expanded)


def check(name: str) -> str:
    """The name when valid; raises CompanyNameError naming the first rule it breaks."""
    if not isinstance(name, str) or not _LABEL.fullmatch(name):
        raise CompanyNameError(
            "%r is not a lowercase DNS label (a-z, 0-9, single inner hyphens)" % (name,)
        )
    if name in reserved():
        raise CompanyNameError("%r is a reserved region or service name" % name)
    if not MIN_LENGTH <= len(name) <= MAX_LENGTH:
        raise CompanyNameError("%r must be %d to %d characters" % (name, MIN_LENGTH, MAX_LENGTH))
    if name.startswith("xn--"):
        raise CompanyNameError("%r uses the reserved xn-- prefix" % name)
    if name.endswith(PROXY_SUFFIX):
        raise CompanyNameError(
            "%r ends in %s, the proxy host suffix of another name" % (name, PROXY_SUFFIX)
        )
    if re.fullmatch(r"c[0-9a-f]{8,}", name):
        raise CompanyNameError("%r has the shape of an opaque store id" % name)
    return name


def hosts(name: str, domain: str) -> tuple[str, str]:
    """(account host, proxy host) for a valid name under the product domain the caller names (well_known.PRODUCT_DOMAIN once the rename lands)."""
    check(name)
    return "%s.%s" % (name, domain), "%s%s.%s" % (name, PROXY_SUFFIX, domain)
