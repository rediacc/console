"""The live `rediacc-console` Turnstile widget must hold the site key and the secret that Bitwarden is about to deploy.

WHY. On 2026-09-24, after the empty-site-key portal was rebuilt (that half is `check:ci-portal-sitekey-guard`), every production login still failed with "Captcha verification failed". Bitwarden's `CLOUDFLARE_TURNSTILE_SECRET_KEY` had silently stopped matching the secret of the live widget, and a routine secret push deployed the stale value to every account worker. Nothing compared the two; `./run.sh rotation rotate turnstile` repaired it by hand.

WHAT IT CHECKS. With `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `TURNSTILE_SITE_KEY` and `CLOUDFLARE_TURNSTILE_SECRET_KEY` in the environment, it lists `/accounts/{id}/challenges/widgets` (every page), picks the ONE widget named `rediacc-console`, reads `/accounts/{id}/challenges/widgets/{sitekey}`, and asserts
  1. the widget's sitekey equals TURNSTILE_SITE_KEY, and
  2. the widget's secret equals CLOUDFLARE_TURNSTILE_SECRET_KEY.

WHY A DIRECT COMPARISON AND NOT SITEVERIFY. `rotation check` probes `challenges.cloudflare.com/turnstile/v0/siteverify`, which takes no sitekey: it accepts any live secret of any widget, so it cannot tell a stale-but-valid secret of the wrong widget from the right one. Only the widget GET says which secret THIS widget holds. The GET is also stricter during the 2-hour grace window after a rotation, where siteverify still accepts the previous secret and this check does not, which is the right answer for a deploy that is about to push it everywhere.

EXIT CODES. 0 both match; 1 drift (either mismatch), with the fix named; 2 no verdict: a missing variable, a credential or API failure, a widget that is absent or ambiguous, a GET without `secret` (token scope), or a failed control. Unknown is never folded into fine.

NO VALUE IS EVER PRINTED, not the secret and not the site key: every message names variables and the widget, and the selftest asserts that no planted value reaches either stream.

`--selftest` runs the controls only, through an injected fake fetch; it needs no network and no credential and is what `check:ci-turnstile-drift` runs in CI. Without it the controls run first and then the live check, which is the deploy preflight in `.github/workflows/cd-deploy-account.yml`.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from rediacc_ci.controls import controls_first

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

API_BASE = "https://api.cloudflare.com/client/v4"
WIDGET_NAME = "rediacc-console"
FIX = "./run.sh rotation rotate turnstile"
# Rotation re-syncs the SECRET only (private/account/scripts/rotation/lib/config.ts `turnstile.bitwardenSecretName`); nothing in it writes the site key, so a site-key mismatch names a different fix.
FIX_SITEKEY = (
    "set Bitwarden TURNSTILE_SITE_KEY to the sitekey the %r widget lists "
    "(Cloudflare dashboard, Turnstile); `%s` does not touch the site key"
)
REQUIRED = (
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "TURNSTILE_SITE_KEY",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY",
)
PER_PAGE = 50
MAX_PAGES = 40
SCOPE_HINT = (
    "the API token can list widgets but the widget GET returned no `secret`: the token lacks "
    "'Turnstile Sites Write'. Add it to the token's account permissions (cf-cd declares it in "
    "private/account/scripts/rotation/commands/rotate.ts CF_TOKEN_PERMISSIONS) and re-mint it"
)


class ApiError(Exception):
    """The Cloudflare API gave no usable answer. Carries names and CF error text, never a value."""


def label(path: str) -> str:
    """The path with its values replaced by their names, so an error can say where it failed."""
    path = re.sub(r"/accounts/[^/?]+", "/accounts/{account_id}", path.split("?", maxsplit=1)[0])
    return re.sub(r"/widgets/[^/?]+", "/widgets/{sitekey}", path)


def http_fetch(path: str, token: str) -> tuple[object, dict]:
    """The `result` and `result_info` of a successful Cloudflare v4 envelope; ApiError otherwise."""
    req = urllib.request.Request(  # noqa: S310 -- constant https API_BASE
        API_BASE + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "rediacc-ci-turnstile-drift",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 -- constant https API_BASE
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise ApiError("HTTP %d on %s%s" % (e.code, label(path), _cf_errors(e.read()))) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ApiError("transport failure on %s: %s" % (label(path), e)) from None
    try:
        body = json.loads(raw)
    except ValueError:
        raise ApiError("non-JSON body on %s" % label(path)) from None
    if not isinstance(body, dict) or body.get("success") is not True:
        raise ApiError("success is not true on %s%s" % (label(path), _cf_errors(raw)))
    return body.get("result"), body.get("result_info") or {}


def _cf_errors(raw: bytes) -> str:
    """Cloudflare's own error codes and messages. They describe the failure, never a credential."""
    try:
        errs = json.loads(raw).get("errors") or []
        return (
            ": " + "; ".join("%s %s" % (e.get("code"), e.get("message")) for e in errs)
            if errs
            else ""
        )
    except (ValueError, AttributeError):
        return ""


def list_widgets(account: str, token: str, fetch: Callable) -> list[dict]:
    out: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        result, info = fetch(
            "/accounts/%s/challenges/widgets?page=%d&per_page=%d" % (account, page, PER_PAGE), token
        )
        if not isinstance(result, list):
            raise ApiError("the widget list is not a list")
        out.extend(w for w in result if isinstance(w, dict))
        total = info.get("total_count")
        if not result or (isinstance(total, int) and len(out) >= total):
            return out
    raise ApiError("the widget list did not end within %d pages" % MAX_PAGES)


def check(env: Mapping[str, str], fetch: Callable) -> tuple[int, list[str]]:
    """(exit code, lines). Every line names things; none carries a value."""
    missing = [n for n in REQUIRED if not (env.get(n) or "").strip()]
    if missing:
        return 2, ["unset or empty: %s; no verdict is possible" % ", ".join(missing)]
    token = env["CLOUDFLARE_API_TOKEN"].strip()
    account = env["CLOUDFLARE_ACCOUNT_ID"].strip()
    want_key = env["TURNSTILE_SITE_KEY"].strip()
    want_secret = env["CLOUDFLARE_TURNSTILE_SECRET_KEY"].strip()
    try:
        widgets = list_widgets(account, token, fetch)
        if not widgets:
            return 2, [
                "the account lists ZERO Turnstile widgets: wrong account or token, no verdict"
            ]
        named = [w for w in widgets if w.get("name") == WIDGET_NAME]
        if len(named) != 1:
            return 2, [
                "%d widget(s) named %r among %d listed; expected exactly one, no verdict"
                % (len(named), WIDGET_NAME, len(widgets))
            ]
        live_key = str(named[0].get("sitekey") or "")
        if not live_key:
            return 2, ["the listed %r widget carries no sitekey, no verdict" % WIDGET_NAME]
        full, _ = fetch("/accounts/%s/challenges/widgets/%s" % (account, live_key), token)
    except ApiError as e:
        return 2, ["Cloudflare API: %s; failing closed, no verdict" % e]
    if not isinstance(full, dict) or not str(full.get("secret") or ""):
        return 2, [SCOPE_HINT]
    live_secret = str(full["secret"])
    lines: list[str] = []
    fixes: list[str] = []
    if not hmac.compare_digest(live_key.encode(), want_key.encode()):
        lines.append(
            "TURNSTILE_SITE_KEY does not equal the sitekey of the live %r widget: the portal "
            "would render a widget whose tokens this secret cannot verify" % WIDGET_NAME
        )
        fixes.append("fix: " + FIX_SITEKEY % (WIDGET_NAME, FIX))
    if not hmac.compare_digest(live_secret.encode(), want_secret.encode()):
        lines.append(
            "CLOUDFLARE_TURNSTILE_SECRET_KEY does not equal the secret of the live %r widget: "
            "deploying it makes every login fail with 'Captcha verification failed'" % WIDGET_NAME
        )
        fixes.append("fix: %s (re-syncs the widget secret into Bitwarden)" % FIX)
    if lines:
        return 1, [*lines, *fixes, "then re-run this deploy"]
    return 0, [
        "the live %r widget (1 of %d listed) holds TURNSTILE_SITE_KEY and "
        "CLOUDFLARE_TURNSTILE_SECRET_KEY" % (WIDGET_NAME, len(widgets))
    ]


# ---- controls -----------------------------------------------------------------------

_SITEKEY = "0xPLANTSITEKEY0000000001"
_PLANT_WIDGET_VALUE = "0xPLANTSECRET000000000000000001"
_ENV = {
    "CLOUDFLARE_API_TOKEN": "plant-token-value",
    "CLOUDFLARE_ACCOUNT_ID": "plantaccount",
    "TURNSTILE_SITE_KEY": _SITEKEY,
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": _PLANT_WIDGET_VALUE,
}


def fake_fetch(
    widgets: list[dict], secrets: dict[str, str | None], fail: str = "", page_size: int = PER_PAGE
) -> Callable:
    """A fake Cloudflare: `widgets` paged at `page_size`, `secrets` by sitekey (None drops the field)."""

    def fetch(path: str, token: str) -> tuple[object, dict]:
        if token != _ENV["CLOUDFLARE_API_TOKEN"]:
            raise ApiError("HTTP 403 on %s: 10000 Authentication error" % label(path))
        if fail and fail in path:
            raise ApiError("HTTP 500 on %s: 10001 planted" % label(path))
        base = "/accounts/%s/challenges/widgets" % _ENV["CLOUDFLARE_ACCOUNT_ID"]
        if path.startswith(base + "?"):
            page = int(path.split("page=")[1].split("&", maxsplit=1)[0])
            chunk = widgets[(page - 1) * page_size : page * page_size]
            return [dict(w) for w in chunk], {"total_count": len(widgets)}
        if path.startswith(base + "/"):
            key = path[len(base) + 1 :]
            match = [w for w in widgets if w.get("sitekey") == key]
            if not match:
                raise ApiError("HTTP 404 on %s" % label(path))
            full = dict(match[0])
            if secrets.get(key) is not None:
                full["secret"] = secrets[key]
            return full, {}
        raise ApiError("unexpected path %s" % label(path))

    return fetch


def _live(sitekey: str = _SITEKEY) -> list[dict]:
    return [
        {"name": "rediacc-console-bench", "sitekey": "0xBENCHKEY"},
        {"name": WIDGET_NAME, "sitekey": sitekey},
    ]


def controls() -> list[tuple[str, int, dict, Callable]]:
    """(description, expected exit code, env, fetch). Both directions: one must pass, the rest must not."""
    ok = fake_fetch(_live(), {_SITEKEY: _PLANT_WIDGET_VALUE, "0xBENCHKEY": "bench-secret"})
    return [
        ("a matching widget passes", 0, _ENV, ok),
        (
            "the widget found on page 2 of the listing still passes",
            0,
            _ENV,
            fake_fetch(_live(), {_SITEKEY: _PLANT_WIDGET_VALUE}, page_size=1),
        ),
        (
            "a planted SECRET mismatch fails (the 2026-09-24 incident)",
            1,
            _ENV,
            fake_fetch(_live(), {_SITEKEY: "0xROTATEDELSEWHERE00000000000"}),
        ),
        (
            "a planted SITEKEY mismatch fails",
            1,
            {**_ENV, "TURNSTILE_SITE_KEY": "0xSTALESITEKEY0000000000"},
            ok,
        ),
        (
            "an API error on the widget GET fails closed",
            2,
            _ENV,
            fake_fetch(_live(), {_SITEKEY: _PLANT_WIDGET_VALUE}, fail="/widgets/"),
        ),
        (
            "an API error on the listing fails closed",
            2,
            _ENV,
            fake_fetch(_live(), {_SITEKEY: _PLANT_WIDGET_VALUE}, fail="widgets?"),
        ),
        ("a rejected token fails closed", 2, {**_ENV, "CLOUDFLARE_API_TOKEN": "wrong"}, ok),
        ("a missing variable fails closed", 2, {**_ENV, "CLOUDFLARE_TURNSTILE_SECRET_KEY": ""}, ok),
        (
            "a widget GET without `secret` (token scope) fails closed",
            2,
            _ENV,
            fake_fetch(_live(), {_SITEKEY: None}),
        ),
        (
            "no widget named rediacc-console fails closed",
            2,
            _ENV,
            fake_fetch(_live()[:1], {"0xBENCHKEY": "bench-secret"}),
        ),
        ("zero widgets listed fails closed", 2, _ENV, fake_fetch([], {})),
        (
            "two widgets named rediacc-console fail closed",
            2,
            _ENV,
            fake_fetch(
                [*_live(), {"name": WIDGET_NAME, "sitekey": "0xDUP"}],
                {_SITEKEY: _PLANT_WIDGET_VALUE},
            ),
        ),
    ]


def selftest() -> bool:
    """True when a control FAILED."""
    failed = False
    planted = {
        _SITEKEY,
        _PLANT_WIDGET_VALUE,
        "0xROTATEDELSEWHERE00000000000",
        "0xSTALESITEKEY0000000000",
    }
    planted |= {"plant-token-value", "bench-secret"}
    for desc, want, env, fetch in controls():
        rc, lines = check(env, fetch)
        text = "\n".join(lines)
        if rc != want:
            print("✗ control: %s: exit %d, expected %d" % (desc, rc, want), file=sys.stderr)
            failed = True
        leaked = sorted(v for v in planted if v in text)
        if leaked:
            print(
                "✗ control: %s: output carries %d planted value(s)" % (desc, len(leaked)),
                file=sys.stderr,
            )
            failed = True
        if "SECRET_KEY does not equal" in text and FIX not in text:
            print("✗ control: %s: secret drift does not name %s" % (desc, FIX), file=sys.stderr)
            failed = True
        if "SITE_KEY does not equal" in text and "set Bitwarden TURNSTILE_SITE_KEY" not in text:
            print("✗ control: %s: site-key drift does not name its fix" % desc, file=sys.stderr)
            failed = True
        if want == 1 and "does not equal" not in text:
            print("✗ control: %s: exit 1 without naming what drifted" % desc, file=sys.stderr)
            failed = True
    print("  %d controls ran" % len(controls()))
    return failed


def main(
    argv: list[str], env: Mapping[str, str] | None = None, fetch: Callable = http_fetch
) -> int:
    """An unexpected exception is exit 2, never Python's default 1, which would read as drift."""
    try:
        return _main(argv, env, fetch)
    except Exception as e:  # noqa: BLE001 - any crash is "no verdict", and says which class
        print(
            "::error::\u2717 turnstile drift check crashed (%s); failing closed, no verdict"
            % type(e).__name__,
            file=sys.stderr,
        )
        return 2


def _main(argv: list[str], env: Mapping[str, str] | None, fetch: Callable) -> int:
    rc = controls_first("Turnstile widget drift", selftest)
    if rc or "--selftest" in argv:
        return rc
    # Each name is read here by its literal, so check:ci-python-env-registry can see this module's inputs; a mapping handed to `check` whole is invisible to it.
    environ = os.environ if env is None else env
    inputs = {
        "CLOUDFLARE_API_TOKEN": environ.get("CLOUDFLARE_API_TOKEN", ""),
        "CLOUDFLARE_ACCOUNT_ID": environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
        "TURNSTILE_SITE_KEY": environ.get("TURNSTILE_SITE_KEY", ""),
        "CLOUDFLARE_TURNSTILE_SECRET_KEY": environ.get("CLOUDFLARE_TURNSTILE_SECRET_KEY", ""),
    }
    rc, lines = check(inputs, fetch)
    mark = "✓" if rc == 0 else "✗"
    stream = sys.stdout if rc == 0 else sys.stderr
    for i, line in enumerate(lines):
        prefix = ("::error::" if rc else "") if i == 0 else "    "
        print("%s%s %s" % (prefix, mark, line) if i == 0 else prefix + line, file=stream)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
