#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/verify-edge-endpoints.sh`.

Post-deploy smoke test for the edge environment. The twin's own header carries
the WHY for every assertion; this docstring records only what the PORT had to
decide, because everything else is a line-for-line transcription.

CURL IS SHELLED OUT TO, NOT REPLACED BY `urllib`. Its sibling `wait_for_preview_worker.py` went the other way and said so: `curl` is a generic HTTP client with no credential of its own, so faking the BINARY there would have reimplemented `urllib.request` under another name. THIS script is different in the one way that matters. Every URL in it is a hard-coded production hostname
(`edge.rediacc.com`, `releases.rediacc.com`) with no override knob anywhere, so the only way to drive either implementation without touching production is to put a fake `curl` on `PATH`. A port that used `urllib` could not be driven through that fake, which means it could not be compared against the twin at all, which means it could never be shown equivalent. The argv is therefore
byte-identical to the twin's on every one of the eleven call sites, and the differential asserts the recorded call log matches.

`jq` IS ALSO SHELLED OUT TO, for the same reason plus one more: the twin reads `jq -re '.version'`'s three distinct exit codes (0 with a value, 1 on a JSON `null`, 4 on empty input -- all three driven, not assumed), and jq's stderr is NOT redirected on that call site, so a parse error reaches the script's stderr. Reproducing that from `json.loads` would be a re-derivation of jq's
diagnostics.

PIPEFAIL IS OFF IN THE TWIN AND ITS ABSENCE IS LOAD-BEARING, which the twin's
own header explains: `HDRS=$(curl -sI ... | tr -d '\\r')` reports `tr`'s status,
so a transient curl failure falls through to the "headers not yet enabled" branch instead of aborting the smoke test. Python has no such option to get
wrong; the equivalent is simply that `headers()` below ignores curl's exit
status, and it is called out here so a later reader does not "fix" it.

THE GLOBALS ARE REAL GLOBALS IN THE TWIN, and the error paths depend on it. `_install_sh_baked` assigns `INSTALL_SH` with no `local`, so after `fetch_retry` gives up, the `echo "$INSTALL_SH" | grep -E ...` diagnostic prints the body of the LAST attempt. `S`, `FOOTER_HTML`, `EDGE_VERSION`, `R2_SH` and `R2_PS1` are the same. `_Last` below is that shared scratch space, named rather
than hidden so the coupling stays visible.

`$RANDOM$RANDOM` BECOMES `secrets.randbelow(32768)` TWICE, not `random`. The value is a cache-buster in a query string and nothing reads it back, so the
generator's quality is irrelevant; `secrets` is used only because ruff's S311
objects to `random` and this repo does not add per-line suppressions to get past a gate. The value DOMAIN is identical (0..32767 concatenated), which is the only property the twin relies on.

REWORDED ON EXACTLY ONE PATH: a missing `$VERSION`. The twin spells that
`${VERSION:?verify-edge-endpoints.sh: VERSION must be set}`, and bash prefixes
its own `<path>: line 87:` to the message. The line number is not worth reproducing and would rot on the next edit, so the port prints its own line.
Exit code (1) and the named variable agree; the bytes do not, and the
differential asserts that narrowly rather than pretending otherwise.

Exit: 0 smoke test passed, 1 any assertion failed.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.core import common

if TYPE_CHECKING:
    from collections.abc import Callable

SELF = "verify-edge-endpoints.py"

# The twin's hard-coded hosts. Named constants so a reader can see at a glance that this program has no configurable target, which is the fact that decided the fake-`curl` design above.
EDGE = "https://edge.rediacc.com"
RELEASES = "https://releases.rediacc.com"

DEVNULL = subprocess.DEVNULL


class _Last:
    """The twin's un-`local`ised predicate variables, in one place.

    Every field here is read by an ERROR path after the predicate that set it has already returned false, which is why they cannot be locals.
    """

    install_sh: str = ""
    install_ps1: str = ""
    status: str = ""
    footer_html: str = ""
    edge_version: str = ""
    r2_sh: str = ""
    r2_ps1: str = ""


def substitute(out: str) -> str:
    """`$(...)`: command substitution strips every trailing newline."""
    return out.rstrip("\n")


def lines(text: str) -> list[str]:
    """The lines `echo "$text" | grep ...` would see.

    `echo` appends one newline, and grep does not treat the empty tail after a final newline as a line. Written once so the four diagnostic greps below cannot drift apart.
    """
    return (text + "\n").split("\n")[:-1]


def curl_run(args: list[str], *, quiet_stderr: bool) -> tuple[int, str]:
    """One `curl` invocation, argv exactly as the twin spells it.

    `quiet_stderr` is the twin's `2>/dev/null`, which is present on the `-fsSL` body fetches and the region health probe and ABSENT on the `-sI` fingerprint probes. The asymmetry is the twin's, not a choice.
    """
    proc = subprocess.run(
        ["curl", *args],
        stdout=subprocess.PIPE,
        stderr=DEVNULL if quiet_stderr else None,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout


def _fetch_body(url: str) -> tuple[int, str]:
    """`curl -fsSL <url> 2>/dev/null`, substituted."""
    rc, out = curl_run(["-fsSL", url], quiet_stderr=True)
    return rc, substitute(out)


def _status(url: str) -> str:
    """`S=$(curl -sI -o /dev/null -w '%{http_code}' <url>)`.

    NO `2>/dev/null` HERE, deliberately: the twin does not suppress curl's stderr on the three fingerprint probes, so a TLS or DNS diagnostic reaches the job log. Reproduced rather than tidied.
    """
    _rc, out = curl_run(["-sI", "-o", "/dev/null", "-w", "%{http_code}", url], quiet_stderr=False)
    return substitute(out)


def headers(url: str) -> str:
    """`HDRS=$(curl -sI <url> | tr -d '\\r')`.

    curl's exit status is DISCARDED, which under the twin's `set +o pipefail` is what the pipeline does: the status reported is `tr`'s, and `tr` succeeds on empty input. See the module docstring.
    """
    _rc, out = curl_run(["-sI", url], quiet_stderr=False)
    return substitute(out.replace("\r", ""))


def jq_run(args: list[str], *, stdin: str | None = None) -> tuple[int, str]:
    """One `jq` invocation. stderr is INHERITED, matching every twin call site."""
    proc = subprocess.run(
        ["jq", *args],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout


def fetch_retry(what: str, predicate: Callable[[], bool], retries: int, sleep_s: str) -> bool:
    """`fetch_retry` (verify-edge-endpoints.sh:70-86).

    The predicate does its own fetching AND its own matching, which is the whole point: a stale-but-200 response is a failure it can retry, and a blanket `curl --retry` cannot see one.

    `sleep_s` STAYS A STRING because the twin passes it to `sleep`, which accepts a fraction, while the give-up message computes `(retries - 1) * sleep` in bash ARITHMETIC, which does not.

    THIS PORT DELIBERATELY DIVERGES ON A FRACTIONAL `EDGE_RETRY_SLEEP`, and it is the one place a port must not be faithful. FINDING 3: in the twin, the arithmetic error inside the give-up `echo` aborts `fetch_retry` BEFORE its `return 1`, and because every call site invokes it under `||` or `if !`, bash suppresses the exit and hands the caller status 0. `fetch_retry` then reports
    SUCCESS for a check that just failed twice, the caller prints its `OK` line, and the smoke test ends with `Smoke test passed` and exit 0 having verified nothing. All six call sites are affected. Reproducing that would be transcribing a silent pass into a second language, so the port renders the number with `float` instead: byte-identical for every integer `EDGE_RETRY_SLEEP`
    (including the default 5), and correct rather than catastrophic for a fractional one.
    """
    attempt = 1
    while True:
        if predicate():
            if attempt > 1:
                print("  %s: agreed on attempt %d/%d" % (what, attempt, retries), flush=True)
            return True
        if attempt >= retries:
            waited = (retries - 1) * float(sleep_s)
            # `%d` for a whole number, so an integer EDGE_RETRY_SLEEP renders exactly as bash arithmetic renders it. See the docstring for why the fractional case is answered at all rather than reproduced.
            rendered = "%d" % waited if waited == int(waited) else "%g" % waited
            print(
                "  %s: still disagreeing after %d attempts over %ss of waiting"
                % (what, retries, rendered),
                file=sys.stderr,
                flush=True,
            )
            return False
        attempt += 1
        time.sleep(float(sleep_s))


def grep_e(text: str, pattern: str) -> None:
    """`echo "$text" | grep -E <pattern> || true`: print the matching lines."""
    matcher = re.compile(pattern)
    for line in lines(text):
        if matcher.search(line):
            print(line, flush=True)


def grep_f(text: str, needle: str) -> None:
    """`echo "$text" | grep -F <needle> || true`."""
    for line in lines(text):
        if needle in line:
            print(line, flush=True)


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments

    try:
        common.require_cmd("curl")
        common.require_cmd("jq")
    except common.RefusalError as refusal:
        refusal.report()
        return refusal.code

    # READ THROUGH `os.environ` DIRECTLY, NOT THROUGH A LOCAL ALIAS. `check:ci-python-env-registry` derives its declared-input set from the AST and only recognises `os.environ[...]` and `os.environ.get(...)` AT THE CALL SITE. Binding a local name to `os.environ` first reads identically at runtime and is INVISIBLE to that gate, so four undeclared inputs would go unregistered --
    # which is precisely the shape the gate exists to catch.
    retries = int(os.environ.get("EDGE_RETRIES") or "6")
    retry_sleep = os.environ.get("EDGE_RETRY_SLEEP") or "5"

    version = os.environ.get("VERSION") or ""
    if not version:
        # See the module docstring: this is the one reworded path.
        print("%s: VERSION must be set" % SELF, file=sys.stderr, flush=True)
        return 1
    workers_only = os.environ.get("WORKERS_ONLY", "")

    # `cd "$(get_repo_root)"`. regions.json is read by RELATIVE path below, so the chdir is load-bearing and jq's own "Could not open file regions.json" diagnostic depends on it too.
    os.chdir(paths.repo_root())

    print("Verifying edge deployment for v%s..." % version, flush=True)

    # -- Marketing worker: install.sh -------------------------------------
    def install_sh_baked() -> bool:
        rc, body = _fetch_body("%s/install.sh" % EDGE)
        _Last.install_sh = body
        if rc != 0:
            return False
        return "REDIACC_CHANNEL:-edge" in body

    if not fetch_retry("install.sh channel", install_sh_baked, retries, retry_sleep):
        print("::error::edge.rediacc.com/install.sh is not baked to channel=edge", flush=True)
        grep_e(_Last.install_sh, "REDIACC_CHANNEL")
        return 1
    print("  marketing (install.sh): OK (channel=edge)", flush=True)

    # -- Marketing worker: install.ps1 ------------------------------------
    def install_ps1_baked() -> bool:
        rc, body = _fetch_body("%s/install.ps1" % EDGE)
        _Last.install_ps1 = body
        if rc != 0:
            return False
        return '} else { "edge" }' in body

    if not fetch_retry("install.ps1 channel", install_ps1_baked, retries, retry_sleep):
        print("::error::edge.rediacc.com/install.ps1 is not baked to channel=edge", flush=True)
        grep_f(_Last.install_ps1, "$Channel")
        return 1
    print("  marketing (install.ps1): OK (channel=edge)", flush=True)

    # -- Worker fingerprints ----------------------------------------------
    rnda = "%d%d" % (secrets.randbelow(32768), secrets.randbelow(32768))
    rndb = "%d%d" % (secrets.randbelow(32768), secrets.randbelow(32768))
    rndc = "%d%d" % (secrets.randbelow(32768), secrets.randbelow(32768))

    def probe(url: str, want: str) -> Callable[[], bool]:
        def _run() -> bool:
            _Last.status = _status(url)
            return _Last.status == want

        return _run

    about = probe("%s/about?cb=%s" % (EDGE, rnda), "410")
    if not fetch_retry("about 410", about, retries, retry_sleep):
        # THE EM DASH IS AN ESCAPE ON PURPOSE. The twin's line 133 carries a literal U+2014 and this port must emit the same byte, but a literal em dash in authored source is banned house-wide. The escape keeps the OUTPUT identical without putting the character in the file.
        print(
            "::error::edge /about expected 410 (curated redirect table), got %s "
            "\u2014 old worker bundle likely live" % _Last.status,
            flush=True,
        )
        return 1
    print("  worker fingerprint (redirect table): OK (/about=410)", flush=True)

    if not fetch_retry("en 200", probe("%s/en?cb=%s" % (EDGE, rndb), "200"), retries, retry_sleep):
        print(
            "::error::edge /en expected 200 (html_handling=drop-trailing-slash), got %s"
            % _Last.status,
            flush=True,
        )
        return 1
    print("  worker fingerprint (html_handling): OK (/en=200, no 307)", flush=True)

    font_url = "%s/fonts/inter/Inter-Regular.woff2?cb=%s" % (EDGE, rndc)
    if not fetch_retry("font 200", probe(font_url, "200"), retries, retry_sleep):
        print(
            "::error::edge mixed-case font expected 200 (asset-path guard), got %s" % _Last.status,
            flush=True,
        )
        return 1
    print("  worker fingerprint (asset-path guard): OK (Inter-Regular.woff2=200)", flush=True)

    # -- Footer version ----------------------------------------------------
    # `sed 's/<!--[^>]*-->//g'` then `grep -qE "footer-version[^<]*>v${VERSION}<"`.
    # VERSION IS INTERPOLATED RAW INTO AN ERE, exactly as the twin does it, so a version containing a `.` matches any character. Escaping it here would be a behaviour change, not a fix.
    comment = re.compile(r"<!--[^>]*-->")
    footer_re = re.compile("footer-version[^<]*>v%s<" % version)
    footer_diag = re.compile("footer-version[^<]*>[^<]*<[^>]*>[^<]*<")

    if workers_only != "true":

        def footer_matches() -> bool:
            rc, body = _fetch_body("%s/en/" % EDGE)
            _Last.footer_html = body
            if rc != 0:
                return False
            return any(footer_re.search(comment.sub("", line)) for line in lines(body))

        if not fetch_retry("marketing footer", footer_matches, retries, retry_sleep):
            print("::error::edge.rediacc.com footer does not render v%s" % version, flush=True)
            # `grep -oE ... | head -3`: every non-overlapping match, first three.
            shown = 0
            for line in lines(_Last.footer_html):
                for match in footer_diag.finditer(line):
                    print(match.group(0), flush=True)
                    shown += 1
                    if shown >= 3:
                        break
                if shown >= 3:
                    break
            return 1
        print("  marketing (footer version): OK (v%s)" % version, flush=True)

    # -- R2 backstop -------------------------------------------------------
    if workers_only != "true":

        def r2_sh_baked() -> bool:
            rc, body = _fetch_body("%s/cli/edge/install.sh" % RELEASES)
            _Last.r2_sh = body
            if rc != 0:
                return False
            return "REDIACC_CHANNEL:-edge" in body

        if not fetch_retry("R2 install.sh channel", r2_sh_baked, retries, retry_sleep):
            print(
                "::error::releases.rediacc.com/cli/edge/install.sh not baked to channel=edge",
                flush=True,
            )
            grep_e(_Last.r2_sh, "REDIACC_CHANNEL")
            return 1
        print("  R2 cli/edge/install.sh: OK (channel=edge)", flush=True)

        def r2_ps1_baked() -> bool:
            rc, body = _fetch_body("%s/cli/edge/install.ps1" % RELEASES)
            _Last.r2_ps1 = body
            if rc != 0:
                return False
            return '} else { "edge" }' in body

        if not fetch_retry("R2 install.ps1 channel", r2_ps1_baked, retries, retry_sleep):
            print(
                "::error::releases.rediacc.com/cli/edge/install.ps1 not baked to channel=edge",
                flush=True,
            )
            return 1
        print("  R2 cli/edge/install.ps1: OK (channel=edge)", flush=True)
    else:
        print("  R2 backstop: skipped (workers-only deployment)", flush=True)

    # -- R2 latest.json ----------------------------------------------------
    if workers_only != "true":

        def latest_json_readable() -> bool:
            # `curl ... 2>/dev/null | jq -re '.version'` under `set +o pipefail`: the composite status is JQ'S, so a dead curl still reaches jq with empty input, and jq answers 4. Driven, not assumed.
            _rc, body = curl_run(["-fsSL", "%s/cli/edge/latest.json" % RELEASES], quiet_stderr=True)
            jq_rc, out = jq_run(["-re", ".version"], stdin=body)
            _Last.edge_version = substitute(out)
            if jq_rc != 0:
                return False
            return _Last.edge_version != ""

        if not fetch_retry("R2 latest.json", latest_json_readable, retries, retry_sleep):
            print(
                "::error::releases.rediacc.com/cli/edge/latest.json is not readable",
                flush=True,
            )
            return 1
        print("  edge latest.json: v%s" % _Last.edge_version, flush=True)

        if _Last.edge_version == version:
            print("  version match: OK", flush=True)
        else:
            print(
                "  version mismatch: edge has v%s, expected v%s (acceptable in retry mode)"
                % (_Last.edge_version, version),
                flush=True,
            )
    else:
        print("  R2 version check: skipped (workers-only)", flush=True)

    # -- Per-region account health ----------------------------------------
    return _region_health()


HSTS = re.compile(r"^strict-transport-security:", re.IGNORECASE)
NOSNIFF = re.compile(r"^x-content-type-options: *nosniff", re.IGNORECASE)


def _region_domains() -> list[str]:
    """`done < <(jq -r '.regions[] | .edgeDomain' regions.json)`.

    A FAILING jq PRODUCES ZERO DOMAINS AND NO ERROR, because a process substitution's exit status is not the loop's and `set -e` never sees it.
    Carried unchanged; see FINDING 1 in the differential, where it is
    reproduced rather than fixed.
    """
    _rc, out = jq_run(["-r", ".regions[] | .edgeDomain", "regions.json"])
    # `read -r domain` strips leading and trailing IFS whitespace.
    return [line.strip(" \t") for line in out.split("\n")[:-1]]


def _region_health() -> int:
    failed = False
    for domain in _region_domains():
        info_url = "https://%s/account/api/v1/.well-known/server-info" % domain
        rc, out = curl_run(
            ["-sf", "-o", "/dev/null", "-w", "%{http_code}", info_url], quiet_stderr=True
        )
        # `$(curl ... || echo "000")`: BOTH outputs land in the substitution, so
        # a real 404 becomes the string "404000". Carried; see FINDING 2.
        http_code = substitute(out + "000\n") if rc != 0 else substitute(out)
        if http_code != "200":
            print("::error::%s health check failed (HTTP %s)" % (domain, http_code), flush=True)
            failed = True
            continue
        header_lines = lines(headers(info_url))
        if any(HSTS.search(line) for line in header_lines):
            if not any(NOSNIFF.search(line) for line in header_lines):
                print(
                    "::error::%s has HSTS but missing X-Content-Type-Options: nosniff" % domain,
                    flush=True,
                )
                failed = True
                continue
            print("  %s health: OK (security headers verified)" % domain, flush=True)
        else:
            print("  %s health: OK (security headers not yet enabled)" % domain, flush=True)

    if failed:
        return 1
    print("Smoke test passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
