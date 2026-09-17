#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/verify-stable-endpoints.sh`.

Post-deploy verification for the stable environment. Same shape as `verify_edge_endpoints`, one channel over, with two structural differences the twin's header states and this port carries:

  * NO RETRY LOOP. Every assertion samples the surface exactly ONCE. The edge
    twin grew `fetch_retry` on 2026-08-08 after a single unlucky sample failed
    a healthy release; this one never did.
  * REGION HEALTH ONLY WARNS. Stable promotion has already happened by the time
    this runs, so a slow region emits `::warning::` and the script still exits
    0. The edge twin's identical-looking loop emits `::error::` and sets a
    failure flag.

WHY `curl` AND `jq` ARE SHELLED OUT TO rather than replaced by `urllib` and `json`: the full argument is in `verify_edge_endpoints`'s docstring and applies verbatim. In one line, every URL here is a hard-coded production hostname with no override knob, so a fake `curl` on `PATH` is the ONLY way either implementation can be driven off-production, and a port using `urllib` could
never be compared against the twin at all.

THE ONE PLACE `set -e` IS OBSERVABLE, and it is a real defect rather than a
port decision. `INSTALL_SH=$(curl -fsSL https://www.rediacc.com/install.sh)` is
a TOP-LEVEL assignment under `set -e`, so a transport failure kills the script
with curl's own exit code and NO `::error::` annotation at all. Driven:
`bash -c 'set -eu; S=$(curl -sI -o /dev/null -w "%{http_code}"
http://127.0.0.1:19999/x 2>/dev/null); echo "[$S]"'` exits 7 and prints nothing. The edge twin cannot do this because the identical code sits inside a `fetch_retry` predicate, where `set -e` is suspended. Reproduced here, not fixed: see FINDING 4 in the differential.

Exit: 0 verification complete, 1 any assertion failed, or curl's own exit code on a transport failure (see above).
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.core import common
from rediacc_ci.deploy import verify_edge_endpoints as edge

WWW = "https://www.rediacc.com"
RELEASES = "https://releases.rediacc.com"

# Reused rather than re-spelled: these are the SAME two `grep -qi` patterns the edge twin uses, character for character, on the same header block.
HSTS = edge.HSTS
NOSNIFF = edge.NOSNIFF


def _status_or_die(url: str) -> str:
    """`S=$(curl -sI -o /dev/null -w '%{http_code}' <url>)` under `set -e`.

    RAISES `_TransportError` when curl itself fails, because at top level under `set -e` that is a script-killing event in the twin and NOT a route to the `::error::` branch below. See the module docstring.
    """
    proc = subprocess.run(
        ["curl", "-sI", "-o", "/dev/null", "-w", "%{http_code}", url],
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise _TransportError(proc.returncode)
    return proc.stdout.rstrip("\n")


def _body_or_die(url: str) -> str:
    """`X=$(curl -fsSL <url>)` under `set -e`. No `2>/dev/null` on this twin."""
    proc = subprocess.run(
        ["curl", "-fsSL", url],
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise _TransportError(proc.returncode)
    return proc.stdout.rstrip("\n")


class _TransportError(Exception):
    """`set -e` firing on a failed command substitution. Carries curl's status."""

    def __init__(self, code: int) -> None:
        super().__init__("curl exited %d" % code)
        self.code = code


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments and no environment input

    try:
        common.require_cmd("curl")
        common.require_cmd("jq")
    except common.RefusalError as refusal:
        refusal.report()
        return refusal.code

    os.chdir(paths.repo_root())

    print("Verifying stable deployment...", flush=True)

    try:
        return _verify()
    except _TransportError as failure:
        # `set -e` on a top-level `VAR=$(curl ...)`: bash exits with curl's own
        # status, silently. Nothing is printed here for the same reason.
        return failure.code


def _verify() -> int:
    install_sh = _body_or_die("%s/install.sh" % WWW)
    if "REDIACC_CHANNEL:-stable" not in install_sh:
        print("::error::www.rediacc.com/install.sh is not baked to channel=stable", flush=True)
        edge.grep_e(install_sh, "REDIACC_CHANNEL")
        return 1
    print("  marketing (install.sh): OK (channel=stable)", flush=True)

    install_ps1 = _body_or_die("%s/install.ps1" % WWW)
    if '} else { "stable" }' not in install_ps1:
        print("::error::www.rediacc.com/install.ps1 is not baked to channel=stable", flush=True)
        edge.grep_f(install_ps1, "$Channel")
        return 1
    print("  marketing (install.ps1): OK (channel=stable)", flush=True)

    # Worker fingerprints. `$RANDOM$RANDOM` cache-busters; see the edge port's docstring for why this is `secrets` and not `random`.
    rnda = "%d%d" % (secrets.randbelow(32768), secrets.randbelow(32768))
    rndb = "%d%d" % (secrets.randbelow(32768), secrets.randbelow(32768))
    rndc = "%d%d" % (secrets.randbelow(32768), secrets.randbelow(32768))

    status = _status_or_die("%s/about?cb=%s" % (WWW, rnda))
    if status != "410":
        # THE EM DASH IS AN ESCAPE ON PURPOSE. The twin's line 77 carries a literal U+2014 and this port must emit the same byte, but a literal em dash in authored source is banned house-wide.
        print(
            "::error::www /about expected 410 (curated redirect table), got %s "
            "\u2014 old worker bundle likely live" % status,
            flush=True,
        )
        return 1
    print("  worker fingerprint (redirect table): OK (/about=410)", flush=True)

    status = _status_or_die("%s/en?cb=%s" % (WWW, rndb))
    if status != "200":
        print(
            "::error::www /en expected 200 (html_handling=drop-trailing-slash), got %s" % status,
            flush=True,
        )
        return 1
    print("  worker fingerprint (html_handling): OK (/en=200, no 307)", flush=True)

    status = _status_or_die("%s/fonts/inter/Inter-Regular.woff2?cb=%s" % (WWW, rndc))
    if status != "200":
        print(
            "::error::www mixed-case font expected 200 (asset-path guard), got %s" % status,
            flush=True,
        )
        return 1
    print("  worker fingerprint (asset-path guard): OK (Inter-Regular.woff2=200)", flush=True)

    r2_sh = _body_or_die("%s/cli/stable/install.sh" % RELEASES)
    if "REDIACC_CHANNEL:-stable" not in r2_sh:
        print(
            "::error::releases.rediacc.com/cli/stable/install.sh not baked to channel=stable",
            flush=True,
        )
        edge.grep_e(r2_sh, "REDIACC_CHANNEL")
        return 1
    print("  R2 cli/stable/install.sh: OK (channel=stable)", flush=True)

    r2_ps1 = _body_or_die("%s/cli/stable/install.ps1" % RELEASES)
    if '} else { "stable" }' not in r2_ps1:
        print(
            "::error::releases.rediacc.com/cli/stable/install.ps1 not baked to channel=stable",
            flush=True,
        )
        return 1
    print("  R2 cli/stable/install.ps1: OK (channel=stable)", flush=True)

    _region_health()

    print("Stable verification complete", flush=True)
    return 0


def _region_domains() -> list[str]:
    """`done < <(jq -r '.regions[] | .domain' regions.json)`.

    `.domain`, NOT `.edgeDomain`: that one field is the entire difference between this loop and the edge twin's. A failing jq yields zero domains and no error, exactly as in the edge port; see FINDING 1 in the differential.
    """
    _rc, out = edge.jq_run(["-r", ".regions[] | .domain", "regions.json"])
    return [line.strip(" \t") for line in out.split("\n")[:-1]]


def _region_health() -> None:
    """The WARN-ONLY loop. Nothing here can change the exit code."""
    for domain in _region_domains():
        info_url = "https://%s/account/api/v1/.well-known/server-info" % domain
        proc = subprocess.run(
            ["curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}", info_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        # `$(curl ... || echo "000")`: BOTH outputs land in the substitution, so a real 404 becomes the string "404000". Carried; see FINDING 2.
        http_code = (proc.stdout + "000\n" if proc.returncode != 0 else proc.stdout).rstrip("\n")
        if http_code != "200":
            print("::warning::%s health check returned HTTP %s" % (domain, http_code), flush=True)
            continue
        header_lines = edge.lines(edge.headers(info_url))
        if any(HSTS.search(line) for line in header_lines):
            if not any(NOSNIFF.search(line) for line in header_lines):
                print(
                    "::warning::%s has HSTS but missing X-Content-Type-Options" % domain,
                    flush=True,
                )
                continue
            print("  %s health: OK (security headers verified)" % domain, flush=True)
        else:
            print("  %s health: OK (security headers not yet enabled)" % domain, flush=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
