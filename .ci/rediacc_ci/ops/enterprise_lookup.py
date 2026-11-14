"""The one writer of the www Worker's enterprise-lookup KV namespace (`ENTERPRISE_LOOKUP`).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.enterprise_lookup put <domain> <host>
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.enterprise_lookup delete <domain>
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.enterprise_lookup key <domain>

The Worker (`workers/www/src/enterprise-lookup.ts`) answers `{host}` for a company's email domain. Entries are keyed by the hex HMAC-SHA256 of the normalized domain under a server-side pepper, so the namespace holds no domain in the clear. `put` refuses a free-mail domain (`.ci/config/free-mail-domains.json`), since one address at gmail.com says nothing about a company, and a malformed domain or host.

ENVIRONMENT. `ENTERPRISE_LOOKUP_PEPPER` (required, the same value the www Worker holds as a secret), `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` for wrangler. `--namespace-id` overrides the default namespace. No value is printed except the KV key, which is not reversible without the pepper.

`normalize_domain` and `lookup_key` must stay byte-identical to `normalizeDomain` and `lookupKey` in the Worker; the tests pin the HMAC against an independent computation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable

from rediacc_ci import paths
from rediacc_ci.core import wrangler

NAMESPACE_ID = "7bbf3025c29349f5b4f833c1d47d8eb5"  # KV enterprise-lookup, created by rename L3
PEPPER_ENV = "ENTERPRISE_LOOKUP_PEPPER"
FREE_MAIL = ".ci/config/free-mail-domains.json"
_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}$")
_HOST_RE = _DOMAIN_RE
USAGE = (
    "Usage: enterprise_lookup put <domain> <host> | delete <domain> | key <domain>"
    " [--namespace-id <id>]"
)

Runner = Callable[[list[str], dict[str, str]], int]


class LookupRefusedError(Exception):
    """A refusal; the message goes to stderr and the exit status is 1."""


def normalize_domain(value: str) -> str:
    """Lowercase, drop one trailing dot, punycode a unicode name, and require a plain hostname of two or more labels."""
    d = value.strip().lower().removesuffix(".")
    try:
        d = d.encode("idna").decode("ascii")
    except UnicodeError:
        raise LookupRefusedError("not a valid domain: %r" % value) from None
    if len(d) > 253 or not _DOMAIN_RE.match(d):
        raise LookupRefusedError("not a valid domain: %r" % value)
    return d


def free_mail_domains() -> frozenset[str]:
    path = paths.repo_root() / FREE_MAIL
    data = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(data["domains"])


def refuse_free_mail(domain: str) -> None:
    labels = domain.split(".")
    free = free_mail_domains()
    # A subdomain of a free-mail domain is the same provider.
    if any(".".join(labels[i:]) in free for i in range(len(labels) - 1)):
        raise LookupRefusedError(
            "%s is a free-mail domain; a lookup entry for it is refused" % domain
        )


def lookup_key(pepper: str, domain: str) -> str:
    return hmac.new(pepper.encode(), domain.encode(), hashlib.sha256).hexdigest()


def _pepper() -> str:
    pepper = os.environ.get(PEPPER_ENV, "")
    if not pepper:
        raise LookupRefusedError("set %s (the www Worker's secret of the same name)" % PEPPER_ENV)
    return pepper


def _wrangler(argv: list[str], env: dict[str, str]) -> int:
    cwd = paths.repo_root() / "workers" / "www"
    return subprocess.run([*wrangler.ARGV, *argv], cwd=cwd, env=env, check=False).returncode


def put(domain: str, host: str, namespace_id: str, run: Runner = _wrangler) -> int:
    d = normalize_domain(domain)
    refuse_free_mail(d)
    h = host.strip().lower()
    if not _HOST_RE.match(h):
        raise LookupRefusedError("not a valid host: %r" % host)
    key = lookup_key(_pepper(), d)
    return run(
        ["kv", "key", "put", key, h, "--namespace-id", namespace_id, "--remote"], dict(os.environ)
    )


def delete(domain: str, namespace_id: str, run: Runner = _wrangler) -> int:
    d = normalize_domain(domain)
    key = lookup_key(_pepper(), d)
    return run(
        ["kv", "key", "delete", key, "--namespace-id", namespace_id, "--remote"], dict(os.environ)
    )


def main(argv: list[str], run: Runner = _wrangler) -> int:
    args = list(argv)
    namespace_id = NAMESPACE_ID
    if "--namespace-id" in args:
        i = args.index("--namespace-id")
        if i + 1 >= len(args):
            print(USAGE, file=sys.stderr)
            return 2
        namespace_id = args[i + 1]
        del args[i : i + 2]
    try:
        if len(args) == 3 and args[0] == "put":
            return put(args[1], args[2], namespace_id, run)
        if len(args) == 2 and args[0] == "delete":
            return delete(args[1], namespace_id, run)
        if len(args) == 2 and args[0] == "key":
            print(lookup_key(_pepper(), normalize_domain(args[1])))
            return 0
    except LookupRefusedError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
