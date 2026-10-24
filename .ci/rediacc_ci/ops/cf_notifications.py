"""Cloudflare usage-billing notifications as code (agent/plans/PLAN-cloudflare-spend-guard.md T1).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_notifications [--dry-run] [--config <path>]

WHAT IT DOES. Reads `.ci/config/cf-spend-guard.json` `notifications.products` and makes the account's `billing_usage_alert` policies match it, one per product, named `spend-guard:<product>`, with `filters.product` and `filters.limit` from the JSON and an email mechanism to `WK_OPERATOR_EMAIL`. Upsert by name: `GET .../alerting/v3/policies`, then `POST` for a missing name, `PUT .../policies/<id>` for a drifted one, nothing for a matching one; a `spend-guard:` policy the JSON no longer names is deleted, so the JSON stays the one source. A second run against an unchanged JSON writes nothing and says `0 change(s)`. After writing, the policy list is read again and every configured name must be on it.

AVAILABILITY. `available_alerts` returns `billing_usage_alert` with `AvailableValues: null` for both filters (read 2026-10-23), so a product name is only judged by the policy write itself: Cloudflare answers `17106 Invalid product selection.` That configured product prints `UNAVAILABLE <product>` and the run exits 1, never a silent skip. Products already known to be refused sit under `notifications.unavailable` with their evidence and dashboard fallback; they print `UNAVAILABLE <name> (recorded ...)` on every run and do not fail it.

AUTH. `cf_auth.resolve_scoped("cf-notifications")`: a supplied `CF_MANAGEMENT_TOKEN`, or a token minted from the Global API Key with Notifications Write only, awaited on the policies listing and self-destructed at the end. Credentials reach curl on its stdin (`rediacc_ci.core.curl_stdin`), never argv, and no token is printed. Run it under the Bitwarden profile that carries the Global API Key:

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile rotation -- \\
        env PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_notifications

`--dry-run` lists the changes and writes nothing (it still mints and destroys the read token).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import typing

from rediacc_ci import paths
from rediacc_ci.ops import cf_auth
from rediacc_ci.well_known import OPERATOR_EMAIL

CONFIG_REL = ".ci/config/cf-spend-guard.json"
ALERT_TYPE = "billing_usage_alert"
INVALID_PRODUCT = 17106
WRITE_ATTEMPTS = 3
RETRY_SLEEP_S = 1.0


class NotificationError(Exception):
    """A step failed; the message goes to stderr and the exit status is 1."""


class UnavailableError(Exception):
    """Cloudflare refused the policy's product (17106)."""


def load_config(path: pathlib.Path) -> dict:
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise NotificationError("cannot read %s: %s" % (path, exc)) from None
    section = cfg.get("notifications")
    if not isinstance(section, dict) or not isinstance(section.get("products"), dict):
        raise NotificationError("%s has no notifications.products map" % path)
    if not section["products"]:
        raise NotificationError("%s configures zero products" % path)
    for product, spec in section["products"].items():
        limit = spec.get("limit") if isinstance(spec, dict) else None
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise NotificationError("%s: %s needs an integer limit >= 1" % (path, product))
    return section


def desired_policies(section: dict, email: str = OPERATOR_EMAIL) -> dict[str, dict]:
    """Policy name -> the body this run writes for it."""
    prefix = section.get("policy_prefix", "spend-guard:")
    out = {}
    for product, spec in sorted(section["products"].items()):
        name = prefix + product
        out[name] = {
            "name": name,
            "alert_type": ALERT_TYPE,
            "enabled": True,
            "description": "Spend guard: %s at %s %s per billing cycle (%s)"
            % (product, spec["limit"], spec.get("unit", "units"), CONFIG_REL),
            "mechanisms": {"email": [{"id": email}]},
            "filters": {"product": [product], "limit": [str(spec["limit"])]},
        }
    return out


def _emails(policy: dict) -> list[str]:
    mech = policy.get("mechanisms") or {}
    return sorted(str(m.get("id")) for m in mech.get("email") or [] if isinstance(m, dict))


def drift(existing: dict, want: dict) -> list[str]:
    """The fields where `existing` differs from `want`, empty when it matches."""
    diffs = [
        "%s %r -> %r" % (key, existing.get(key), want[key])
        for key in ("alert_type", "enabled", "description")
        if existing.get(key) != want[key]
    ]
    have_filters = existing.get("filters") or {}
    diffs.extend(
        "%s %s -> %s" % (key, have_filters.get(key), want["filters"][key])
        for key in ("product", "limit")
        if [str(v) for v in have_filters.get(key) or []] != want["filters"][key]
    )
    if _emails(existing) != _emails(want):
        diffs.append("email %s -> %s" % (_emails(existing), _emails(want)))
    return diffs


class Api:
    """The alerting/v3 policy calls, authenticated with one scoped token."""

    def __init__(
        self,
        auth: cf_auth.Auth,
        account_id: str,
        sleep: typing.Callable[[float], None] = time.sleep,
    ):
        self.auth = auth
        self.base = "%s/accounts/%s/alerting/v3/policies" % (cf_auth.CF_API_BASE, account_id)
        self.sleep = sleep

    def list(self) -> list[dict]:
        body = cf_auth.curl_json("GET", self.base, self.auth.headers, content_type=False)
        result = body.get("result")
        if body.get("success") is not True or not isinstance(result, list):
            raise NotificationError(
                "listing notification policies failed: %s" % cf_auth._errors(body)
            )
        return [p for p in result if isinstance(p, dict)]

    def write(
        self,
        method: str,
        url: str,
        payload: dict | None,
        stored: typing.Callable[[], dict | None] | None = None,
    ) -> dict:
        """Send one write, retrying a refusal that is not a product refusal (measured 2026-10-23: back-to-back DELETEs were refused, then accepted a second later).

        `stored` is for a non-idempotent write (a POST): before each retry it answers with the result when an earlier attempt was in fact recorded although Cloudflare reported an error, so the retry cannot create a second policy of the same name.
        """
        data = json.dumps(payload) if payload is not None else None
        body: dict = {}
        for attempt in range(WRITE_ATTEMPTS):
            if attempt and stored is not None:
                recorded = stored()
                if recorded is not None:
                    return {"success": True, "result": recorded}
            body = cf_auth.curl_json(method, url, self.auth.headers, data)
            if body.get("success") is True:
                return body
            codes = cf_auth._error_codes(body)
            if INVALID_PRODUCT in codes:
                raise UnavailableError(cf_auth._errors(body))
            if attempt + 1 < WRITE_ATTEMPTS:
                self.sleep(RETRY_SLEEP_S)
        raise NotificationError(
            "%s %s failed: %s" % (method, url.rsplit("/", 1)[-1], cf_auth._errors(body))
        )

    def create(self, want: dict) -> str:

        def stored() -> dict | None:
            same = [p for p in self.list() if p.get("name") == want.get("name")]
            return {"id": same[0].get("id")} if same else None

        body = self.write("POST", self.base, want, stored)
        result = body.get("result")
        return str(result.get("id")) if isinstance(result, dict) else "?"

    def update(self, policy_id: str, want: dict) -> None:
        self.write("PUT", "%s/%s" % (self.base, policy_id), want)

    def delete(self, policy_id: str) -> None:
        self.write("DELETE", "%s/%s" % (self.base, policy_id), None)


def run(api: Api, section: dict, dry_run: bool, out: typing.TextIO | None = None) -> int:
    """Make the account's spend-guard policies match `section`; return the exit status."""
    out = sys.stdout if out is None else out
    prefix = section.get("policy_prefix", "spend-guard:")
    want = desired_policies(section)
    existing = api.list()
    by_name: dict[str, list[dict]] = {}
    for policy in existing:
        by_name.setdefault(str(policy.get("name")), []).append(policy)
    changes = 0
    unavailable: list[str] = []
    for name, body in want.items():
        have = by_name.get(name, [])
        if len(have) > 1:
            raise NotificationError(
                "%d policies are named %s (%s); delete the extras in the dashboard"
                % (len(have), name, ", ".join(str(p.get("id")) for p in have))
            )
        product = body["filters"]["product"][0]
        try:
            if not have:
                if dry_run:
                    changes += 1
                    print(
                        "CREATE %s limit=%s (dry run)" % (name, body["filters"]["limit"][0]),
                        file=out,
                    )
                    continue
                pid = api.create(body)
                changes += 1
                print(
                    "CREATE %s id=%s limit=%s" % (name, pid, body["filters"]["limit"][0]), file=out
                )
                continue
            current = have[0]
            diffs = drift(current, body)
            if not diffs:
                print("UNCHANGED %s id=%s" % (name, current.get("id")), file=out)
                continue
            if dry_run:
                changes += 1
                print(
                    "UPDATE %s id=%s: %s (dry run)" % (name, current.get("id"), "; ".join(diffs)),
                    file=out,
                )
                continue
            api.update(str(current.get("id")), body)
            changes += 1
            print("UPDATE %s id=%s: %s" % (name, current.get("id"), "; ".join(diffs)), file=out)
        except UnavailableError as exc:
            unavailable.append(product)
            print("UNAVAILABLE %s (Cloudflare: %s)" % (product, exc), file=out)
    for name, policies in sorted(by_name.items()):
        if not name.startswith(prefix) or name in want:
            continue
        for policy in policies:
            if dry_run:
                changes += 1
                print("DELETE %s id=%s (dry run)" % (name, policy.get("id")), file=out)
                continue
            api.delete(str(policy.get("id")))
            changes += 1
            print(
                "DELETE %s id=%s (no longer in %s)" % (name, policy.get("id"), CONFIG_REL), file=out
            )
    for name, spec in sorted((section.get("unavailable") or {}).items()):
        print(
            "UNAVAILABLE %s (recorded in %s; fallback: %s)"
            % (name, CONFIG_REL, spec.get("fallback", "none named")),
            file=out,
        )
    for policy in existing:
        if policy.get("alert_type") == "billing_budget_alert":
            print(
                "BUDGET %s id=%s total_spend_dollars=%s (not managed here)"
                % (
                    policy.get("name"),
                    policy.get("id"),
                    (policy.get("filters") or {}).get("total_spend_dollars"),
                ),
                file=out,
            )
    if not dry_run and changes:
        listed = {str(p.get("name")) for p in api.list()}
        missing = [n for n in want if n not in listed and n[len(prefix) :] not in unavailable]
        if missing:
            raise NotificationError("written but not listed afterwards: %s" % ", ".join(missing))
    print("%d change(s)%s" % (changes, " planned (dry run)" if dry_run else ""), file=out)
    return 1 if unavailable else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cf_notifications", description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="list the changes, write nothing")
    parser.add_argument(
        "--config", type=pathlib.Path, default=None, help="default: %s" % CONFIG_REL
    )
    parser.add_argument("--account-id", default=cf_auth.DEFAULT_ACCOUNT_ID)
    args = parser.parse_args(argv)
    config = args.config or paths.from_root(*CONFIG_REL.split("/"))
    auth: cf_auth.Auth | None = None
    try:
        section = load_config(config)
        auth = cf_auth.resolve_scoped("cf-notifications", args.account_id)
        cf_auth.await_propagation(auth)
        return run(Api(auth, args.account_id), section, args.dry_run)
    except (NotificationError, cf_auth.CfAuthError) as exc:
        print("cf_notifications: %s" % exc, file=sys.stderr)
        return 1
    finally:
        if auth is not None and auth.created:
            cf_auth.self_destruct(auth)


if __name__ == "__main__":
    sys.exit(main())
