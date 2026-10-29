"""Does each account portal render the Turnstile widget its Worker enforces.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.portal_captcha [host ...]

WHY IT EXISTS. On 2026-10-28 stable eu, us and asia served a login page with no Turnstile widget while the Worker enforced captcha, so every login answered 400 "Captcha verification required". The portal had been built for bench (no captcha, no site key) and a production deploy uploaded that dist. Nothing that watched the hosts could see it: the page, its assets and the health route were all 200 (`portal_health` stayed green).

THE CHECK, per host, read-only except one refused login:

  1. GET `https://<host>/account/login` and find the `/account/assets/index-*.js` bundle it loads.
  2. GET the bundle. When it carries a Turnstile site key (the exact one when the caller knows it, else the `0x4AAAAAA...` shape every Turnstile key has), the widget renders: OK, and nothing is posted.
  3. Only when the bundle has no key: POST `/account/api/v1/auth/login` with a dummy JSON body. The Worker's captcha middleware runs before any credential lookup (private/account/src/middleware/turnstile.ts), so an enforcing Worker answers "Captcha verification required" without touching an account. That answer beside a keyless bundle is BROKEN. Any other answer means captcha is not enforced, and a keyless portal is consistent with it: OK.

UNKNOWN IS RED. A host that cannot be reached, a login page without an index bundle, or a bundle that does not answer 200 is a verdict nobody could check, never folded into OK.

HOSTS default to every stable and edge host in regions.json (`portal_health.hosts`), so a new region is probed without editing this file. Exit 0 when every host is OK, 1 when any is BROKEN or UNKNOWN (each red line names the host and the fix command), 2 on a usage error. Output never carries a response body or the site key itself.

`rediacc_ci.deploy.deploy_account` runs the same check after each deploy (`portal_smoke`), with the key it deployed and a short retry for propagation.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
import time
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass

from rediacc_ci.core import https
from rediacc_ci.ops import portal_health

LOGIN_PATH = portal_health.LOGIN_PATH
LOGIN_API = "/account/api/v1/auth/login"
# The entry bundle vite emits for the portal; the login page and its Turnstile widget live in it (private/account/web/src/pages/Login.tsx reads import.meta.env.VITE_TURNSTILE_SITE_KEY).
INDEX_RE = re.compile(r"(/account/assets/index-[^\"'\s<>?#]+\.js)")
# Every Turnstile site key starts 0x4AAAAAA; a hex constant in bundled crypto code does not match.
SITEKEY_RE = re.compile(r"0x4AAAAAA[0-9A-Za-z_-]{8,}")
CAPTCHA_REQUIRED = "Captcha verification required"
# Not an account: the captcha middleware refuses before the body is read for credentials.
DUMMY_LOGIN = {"email": "portal-captcha-probe@rediacc.invalid", "password": "portal-captcha-probe"}
TIMEOUT_S = 20.0
USER_AGENT = portal_health.USER_AGENT.replace("portal-health", "portal-captcha")

OK, BROKEN, UNKNOWN = "ok", "BROKEN", "UNKNOWN"


@dataclass(frozen=True)
class Reply:
    """`status` is 0 when no HTTP answer arrived; `error` then names the exception class."""

    status: int
    body: str = ""
    error: str = ""


# (method, url, json body or None) -> Reply. Injected by the tests; `http` is the real one.
Http = Callable[[str, str, "dict | None"], Reply]


def http(method: str, url: str, body: dict | None = None) -> Reply:
    """One request through `rediacc_ci.core.https` (https only). An HTTP error status is an answer, not an exception."""
    headers = {"User-Agent": USER_AGENT}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = https.build_request(url, data=data, headers=headers, method=method)
    try:
        with https.urlopen(request, timeout=TIMEOUT_S) as resp:
            return Reply(resp.status, resp.read(4_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read(65_536).decode("utf-8", "replace")
        except OSError:
            text = ""
        exc.close()
        return Reply(exc.code, text)
    except (OSError, ValueError) as exc:
        return Reply(0, error=type(exc).__name__)


@dataclass(frozen=True)
class Verdict:
    host: str
    state: str
    why: str


def check(host: str, fetch: Http, sitekey: str | None = None) -> Verdict:
    """One host's verdict. `sitekey`, when given, must appear verbatim in the bundle; otherwise any Turnstile-shaped key counts."""
    base = "https://%s" % host
    page = fetch("GET", base + LOGIN_PATH, None)
    if page.status != 200:
        return Verdict(
            host, UNKNOWN, "GET %s answered %s" % (LOGIN_PATH, page.status or page.error)
        )
    bundles = list(dict.fromkeys(m.group(1) for m in INDEX_RE.finditer(page.body)))
    if not bundles:
        return Verdict(host, UNKNOWN, "the login page loads no /account/assets/index-*.js bundle")
    keyed = False
    other_key = False
    for path in bundles:
        got = fetch("GET", base + path, None)
        if got.status != 200:
            return Verdict(host, UNKNOWN, "GET %s answered %s" % (path, got.status or got.error))
        if (sitekey in got.body) if sitekey else bool(SITEKEY_RE.search(got.body)):
            keyed = True
        elif sitekey and SITEKEY_RE.search(got.body):
            other_key = True
    if keyed:
        return Verdict(host, OK, "the portal bundle carries the Turnstile site key")
    login = fetch("POST", base + LOGIN_API, DUMMY_LOGIN)
    if login.status == 0:
        return Verdict(host, UNKNOWN, "POST %s got no answer (%s)" % (LOGIN_API, login.error))
    if CAPTCHA_REQUIRED in login.body:
        # A bundle carrying some other key renders a widget whose token the Worker's secret cannot verify; saying "no key" there would send the operator looking for the wrong fault (review 760ca2d1.2).
        if other_key:
            return Verdict(
                host,
                BROKEN,
                "the Worker answers %r and the portal bundle carries a different Turnstile site key than the one deployed, so its widget's tokens fail verification"
                % CAPTCHA_REQUIRED,
            )
        return Verdict(
            host,
            BROKEN,
            "the Worker answers %r but the portal bundle carries no Turnstile site key, so no widget renders and every login fails"
            % CAPTCHA_REQUIRED,
        )
    return Verdict(host, OK, "captcha is not enforced, and the portal carries no site key")


def check_with_retry(
    host: str,
    fetch: Http,
    sitekey: str | None = None,
    *,
    attempts: int = 6,
    delay_s: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Verdict:
    """`check` until OK or `attempts` run out: a fresh deploy can take a few seconds to reach every edge."""
    verdict = check(host, fetch, sitekey)
    for _ in range(attempts - 1):
        if verdict.state == OK:
            break
        sleep(delay_s)
        verdict = check(host, fetch, sitekey)
    return verdict


def target_of(host: str, regions: list[dict] | None = None) -> tuple[str, str] | None:
    """(`stable`|`edge`, region id) for a regions.json host, else None."""
    for region in portal_health.load_regions() if regions is None else regions:
        if region.get("domain") == host:
            return "stable", region["id"]
        if region.get("edgeDomain") == host:
            return "edge", region["id"]
    return None


REBUILD = (
    '(cd private/account/web && VITE_TURNSTILE_SITE_KEY="$TURNSTILE_SITE_KEY" VITE_CI_MODE=false '
    "npx vite build --outDir ../../../workers/account/dist/account)"
)


def fix_command(host: str, regions: list[dict] | None = None) -> str:
    """The command that rebuilds the portal with the key and redeploys this host, and the rollback."""
    where = target_of(host, regions)
    if where is None:
        return (
            "rebuild the portal with VITE_TURNSTILE_SITE_KEY bound from TURNSTILE_SITE_KEY and redeploy %s"
            % host
        )
    target, region = where
    config = "wrangler.%s.toml" % (region if target == "stable" else "edge-" + region)
    rollback = (
        "or roll back: cd workers/account && npx wrangler deployments list --config %s, then "
        "npx wrangler rollback <last good version id> --config %s -y (deploy-workers profile)"
        % (config, config)
    )
    if target == "edge":
        return "npm run release:local -- --channel edge --workers-only --regions %s; %s" % (
            region,
            rollback,
        )
    # The inner script is quoted once, for the outer shell (`shlex.quote`): inside its single quotes REBUILD's double quotes reach `sh -c` as quotes, so the key is bound bare. Escaping them as `\"` there handed the inner shell literal quote characters, and the rebuilt portal carried a key wrapped in them (review 760ca2d1.1).
    inner = "%s && PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_account --region %s" % (
        REBUILD,
        region,
    )
    return (
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile account-secrets-%s-stable -- "
        "sh -c %s; %s" % (region, shlex.quote(inner), rollback)
    )


def default_hosts() -> list[str]:
    return [h for target in ("stable", "edge") for h in portal_health.hosts(target, None)]


def run(hosts: list[str], fetch: Http = http, out=None) -> int:
    out = sys.stdout if out is None else out
    if not hosts:
        print("portal captcha: RED, no host to probe; the verdict would mean nothing", file=out)
        return 1
    red = 0
    for host in hosts:
        verdict = check_with_retry(host, fetch, attempts=2)
        print("  %-7s %s  %s" % (verdict.state, host, verdict.why), file=out, flush=True)
        if verdict.state != OK:
            red += 1
            print("          fix: %s" % fix_command(host), file=out, flush=True)
    print(
        "portal captcha: %s, %d host(s), %d red" % ("GREEN" if not red else "RED", len(hosts), red),
        file=out,
        flush=True,
    )
    return 1 if red else 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in ("-h", "--help"):
        sys.stdout.write((__doc__ or "") + "\n")
        return 0
    if any(a.startswith("-") for a in args):
        print(
            "usage: PYTHONPATH=.ci python3 -m rediacc_ci.ops.portal_captcha [host ...]",
            file=sys.stderr,
        )
        return 2
    return run(args or default_hosts())


if __name__ == "__main__":
    raise SystemExit(main())
