"""Port of `scripts/ops/lib/cf-auth.sh` (229 lines): Cloudflare authentication for the bench and backup operator scripts.

WHO USES IT: `backup_d1`, `reset_bench` and `deploy_bench` in this package. The bash library was sourced by exactly those three scripts, and `resolve_aws_auth` / the `--aws` half of `self_destruct_credentials` had no caller at all, so they are ported (the operator may still export the AWS admin pair) but nothing passes `delete_aws` today.

WHAT IT DOES. `resolve()` picks a Cloudflare credential: a ready scoped token in `CF_MANAGEMENT_TOKEN`, or the Global API Key pair `CF_GLOBAL_API_KEY` + `CF_EMAIL` from which it mints a scoped management token, or an interactive prompt for either. `self_destruct()` deletes that token at the end of a run so a deploy leaves no stale tokens in the account.

THE CURL CALLS ARE KEPT AS `curl -s -X <METHOD> <url> -H ...` SUBPROCESSES, with the argv the bash built, so the differential compares the recorded call sequence of both sides against one fake `curl`. The Global API Key therefore appears on curl's argv exactly as it did.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH, each one pinned by a test that fails on the bash behaviour (`tests/test_ops_cf_auth.py`).

  1. A FAILED TOKEN MINT NOW SAYS WHY, AND SAYS IT AT ALL. `CF_MANAGEMENT_TOKEN=$(_create_management_token)` under `set -e` ends the script on the substitution's own status, so when the user lookup returned nothing (a wrong key, a revoked email) the `log_error "Failed to create management token"` below it was unreachable and the operator got a silent exit 1. Here every failing step raises `CfAuthError` carrying Cloudflare's own `errors[].message`.
  2. AN EMPTY TOKEN IS REFUSED. Choosing option 2 and pressing Enter left `CF_AUTH_HEADERS=(-H "Authorization: Bearer ")` non-empty, so the "credentials are required" check passed and the first API call failed later with an authentication error naming nothing.
  3. SELF-DESTRUCT REPORTS THE DELETE'S OUTCOME. The bash sent the DELETE to /dev/null and logged "deleted (self-destruct)" whatever Cloudflare answered, and its callers wrapped the whole function in `2>/dev/null || true` so even the warnings vanished. A management token that stays alive after a run is exactly what the operator needs to hear about. The result is checked (`success` in the body) and any failure is a warning on stderr; it still never changes the exit status of the run.
  4. SELF-DESTRUCT RUNS ONCE. The bash trap was installed for EXIT, INT and TERM, so an interrupt ran the handler and then the EXIT trap ran it again, the second pass failing on a token that no longer existed. `Auth.destroyed` makes the second call a no-op.
  7. THE MINTED TOKEN CARRIES R2 STORAGE WRITE. The bash policy had no R2 group, so a bench deploy that minted its own token died at the bucket preflight (`wrangler r2 bucket list` -> Cloudflare API error, run live 2026-10-01), and the same token could not list or create the bucket `deploy-bench` is meant to guarantee.
  6. A MINTED TOKEN IS AWAITED BEFORE ITS FIRST USE (`await_propagation`). `deploy-bench.sh` carried a hand-written `sleep 5` for this; `reset-bench.sh` had none and failed every real run with `Authentication error` on its first D1 query (2026-10-01, twice, then reproduced in isolation: refused at 0 s, accepted at 6 s). One shared wait now serves both, only when the token was minted here.
  5. MORE THAN FIFTY ZONES ARE NOT SILENTLY DROPPED. `zones?per_page=50` read the first page only, so a token minted for an account with fifty-one zones lacked Workers Routes Write on the last one. The first request is byte-identical to the bash; further pages are fetched only when `result_info.total_pages` says there are some.
"""

from __future__ import annotations

import dataclasses
import getpass
import json
import os
import subprocess
import time

from rediacc_ci import log
from rediacc_ci.well_known import CF_API_BASE as WK_CF_API_BASE

CF_API_BASE = WK_CF_API_BASE
DEFAULT_ACCOUNT_ID = "fa51e4a18d553c30e1633288e9733d04"
# A new token answers `Authentication error` for a few seconds. Measured 2026-10-01 against the bench D1 query endpoint: refused at 0 s, accepted at 6 s.
PROPAGATION_SECONDS = 8
MINTED_NAME = "auto-rotation-management"

# Account-scoped permission groups: Account API Tokens Read + Write, Turnstile Sites Write, Workers Scripts Read + Write, D1 Write, Workers R2 Storage Write.
ACCOUNT_PERMISSION_GROUPS = (
    "eb56a6953c034b9d97dd838155666f06",
    "5bc3f8b21c554832afc660159ab75fa4",
    "755c05aa014b4f9ab263aa80b8167bd8",
    "1a71c399035b4950a1bd1466bbe4f420",
    "e086da7e2179491d91ee5f35b3ca210a",
    "09b2857d1c31407795e75e3fed8617a1",
    # Workers R2 Storage Write: `wrangler r2 bucket list|create`, which `bench_preflight buckets` runs. The bash token lacked it.
    "bf7481a1826f439697cb59a20b22293e",
)
# Zone-scoped: Workers Routes Write, DNS Read (wrangler validates a custom domain's DNS before deploying).
ZONE_PERMISSION_GROUPS = (
    "28f4b596e7d643029c524985477ae49a",
    "82e64a83756745bbbb1c9c2701bf816b",
)
# User-scoped: API Tokens Read + Write (list permission groups, self-destruct).
USER_PERMISSION_GROUPS = (
    "0cc3a61731504c89b99ec1be78b77aa0",
    "686d18d5ac6c441c867cbf6771e58a0a",
)


class CfAuthError(Exception):
    """A credential could not be resolved; the message is what the operator sees."""


@dataclasses.dataclass
class Auth:
    """The resolved Cloudflare credential. `token` is always a scoped bearer token once `resolve` returns."""

    token: str
    created: bool = False
    destroyed: bool = False

    @property
    def headers(self) -> list[str]:
        """The curl arguments that authenticate a request."""
        return ["-H", "Authorization: Bearer %s" % self.token]


def curl_json(
    method: str,
    url: str,
    headers: list[str],
    body: str | None = None,
    flags: str = "-s",
    content_type: bool = True,
) -> dict:
    """Run `curl <flags> -X <method>` and return the decoded JSON object; raise CfAuthError on a non-JSON answer."""
    argv = ["curl", flags, "-X", method, url, *headers]
    if content_type:
        argv += ["-H", "Content-Type: application/json"]
    if body is not None:
        argv += ["-d", body]
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    try:
        decoded = json.loads(proc.stdout)
    except ValueError:
        raise CfAuthError(
            "%s %s did not return JSON (curl exit %d)" % (method, url, proc.returncode)
        ) from None
    if not isinstance(decoded, dict):
        raise CfAuthError("%s %s returned a non-object JSON body" % (method, url))
    return decoded


def _errors(body: dict) -> str:
    """Cloudflare's own error text from a response body, or a placeholder when it sent none."""
    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        return "; ".join(
            str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in errors
        )
    return "no error detail in the response"


def _global_headers(global_key: str, email: str) -> list[str]:
    return ["-H", "X-Auth-Key: %s" % global_key, "-H", "X-Auth-Email: %s" % email]


def _zone_ids(headers: list[str], account_id: str) -> list[str]:
    ids: list[str] = []
    page = 1
    while True:
        url = "%s/zones?account.id=%s&per_page=50" % (CF_API_BASE, account_id)
        if page > 1:
            url += "&page=%d" % page
        body = curl_json("GET", url, headers)
        result = body.get("result")
        if not isinstance(result, list):
            raise CfAuthError("listing zones failed: %s" % _errors(body))
        ids += [z["id"] for z in result if isinstance(z, dict) and "id" in z]
        info = body.get("result_info")
        total = info.get("total_pages", 1) if isinstance(info, dict) else 1
        if not isinstance(total, int) or page >= total:
            return ids
        page += 1


def token_policies(account_id: str, user_id: str, zone_ids: list[str]) -> list[dict]:
    """The policy list for the management token: account, then (when any zone exists) zones, then user.

    Cloudflare rejects a policy with an empty `resources` map (400 invalid_request), so the zone policy is omitted outright for an account with no zones.
    """
    policies: list[dict] = [
        {
            "effect": "allow",
            "resources": {"com.cloudflare.api.account.%s" % account_id: "*"},
            "permission_groups": [{"id": g} for g in ACCOUNT_PERMISSION_GROUPS],
        }
    ]
    if zone_ids:
        policies.append(
            {
                "effect": "allow",
                "resources": {"com.cloudflare.api.account.zone.%s" % z: "*" for z in zone_ids},
                "permission_groups": [{"id": g} for g in ZONE_PERMISSION_GROUPS],
            }
        )
    policies.append(
        {
            "effect": "allow",
            "resources": {"com.cloudflare.api.user.%s" % user_id: "*"},
            "permission_groups": [{"id": g} for g in USER_PERMISSION_GROUPS],
        }
    )
    return policies


def create_management_token(
    global_key: str, email: str, account_id: str = DEFAULT_ACCOUNT_ID
) -> str:
    """Mint a scoped management token from the Global API Key; raise CfAuthError naming the failing step."""
    headers = _global_headers(global_key, email)
    user = curl_json("GET", "%s/user" % CF_API_BASE, headers)
    result = user.get("result")
    user_id = result.get("id") if isinstance(result, dict) else None
    if not user_id:
        raise CfAuthError(
            "Cloudflare did not accept the Global API Key for %s: %s" % (email, _errors(user))
        )
    zone_ids = _zone_ids(headers, account_id)
    payload = {"name": MINTED_NAME, "policies": token_policies(account_id, user_id, zone_ids)}
    created = curl_json("POST", "%s/user/tokens" % CF_API_BASE, headers, json.dumps(payload))
    result = created.get("result")
    value = result.get("value") if isinstance(result, dict) else None
    if not value:
        raise CfAuthError("creating the management token failed: %s" % _errors(created))
    return str(value)


def _mint(global_key: str, email: str, account_id: str) -> Auth:
    log.step("Creating scoped management token from Global API Key...")
    token = create_management_token(global_key, email, account_id)
    log.info("Management token created (will self-destruct after run)")
    return Auth(token=token, created=True)


def resolve(account_id: str = DEFAULT_ACCOUNT_ID) -> Auth:
    """Resolve Cloudflare authentication from the environment, prompting when neither credential is set."""
    token = os.environ.get("CF_MANAGEMENT_TOKEN")
    global_key = os.environ.get("CF_GLOBAL_API_KEY")
    email = os.environ.get("CF_EMAIL")
    if token:
        return Auth(token=token)
    if global_key and email:
        return _mint(global_key, email, account_id)
    print("Authentication method:")
    print("  1) Global API Key + Email (auto-creates scoped token)")
    print("  2) Scoped API Token (if you have one ready)")
    choice = input("Choose [1/2]: ")
    if choice == "1":
        email = input("Enter email: ")
        global_key = getpass.getpass("Enter Global API Key: ")
        if not email or not global_key:
            raise CfAuthError("Cloudflare authentication credentials are required")
        return _mint(global_key, email, account_id)
    token = getpass.getpass("Enter API Token: ")
    if not token:
        raise CfAuthError("Cloudflare authentication credentials are required")
    return Auth(token=token)


def await_propagation(auth: Auth) -> None:
    """Wait for a token this run minted to be accepted by Cloudflare's API; a supplied token needs no wait."""
    if auth.created:
        time.sleep(PROPAGATION_SECONDS)


def resolve_aws() -> None:
    """Export the AWS admin pair under the names the aws CLI reads."""
    key_id = os.environ.get("AWS_SES_ADMIN_KEY_ID")
    secret = os.environ.get("AWS_SES_ADMIN_SECRET")
    if not key_id or not secret:
        raise CfAuthError("AWS_SES_ADMIN_KEY_ID and AWS_SES_ADMIN_SECRET are required")
    os.environ["AWS_ACCESS_KEY_ID"] = key_id
    os.environ["AWS_SECRET_ACCESS_KEY"] = secret
    os.environ["AWS_DEFAULT_REGION"] = os.environ.get("AWS_SES_ADMIN_REGION") or "eu-central-1"


def require_self_destruct_capable(auth: Auth | None) -> None:
    """Refuse a self-destruct run that has no token to destroy."""
    if auth is None or not auth.token:
        raise CfAuthError(
            "Self-destruct requires Cloudflare authentication\n"
            "Set CF_MANAGEMENT_TOKEN or CF_GLOBAL_API_KEY + CF_EMAIL"
        )


def self_destruct(auth: Auth | None, delete_aws: bool = False) -> None:
    """Delete the credentials this run used. Never raises: a failure is a warning, the run's exit status stands."""
    if auth is not None and auth.destroyed:
        return
    log.step("=== Self-destruct: destroying credentials used for this run ===")
    aws_key = os.environ.get("AWS_SES_ADMIN_KEY_ID")
    if delete_aws and aws_key:
        log.step("Deleting AWS admin key: %s" % aws_key)
        proc = subprocess.run(
            ["aws", "iam", "delete-access-key", "--access-key-id", aws_key],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            log.warn("Failed to delete AWS admin key: %s" % aws_key)
            log.warn(
                "Manually delete it from: https://us-east-1.console.aws.amazon.com/iam/home#/security_credentials"
            )
        else:
            log.info("AWS admin key deleted")
    if auth is None or not auth.token:
        return
    auth.destroyed = True
    log.step("Deleting CF management token...")
    try:
        verify = curl_json("GET", "%s/user/tokens/verify" % CF_API_BASE, auth.headers)
        result = verify.get("result")
        token_id = result.get("id") if isinstance(result, dict) else None
        if not token_id:
            log.warn("Could not determine CF token ID for self-destruct")
            return
        deleted = curl_json("DELETE", "%s/user/tokens/%s" % (CF_API_BASE, token_id), auth.headers)
    except CfAuthError as exc:
        log.warn("CF management token was NOT deleted: %s" % exc)
        return
    if deleted.get("success") is True:
        log.info("CF management token deleted (self-destruct)")
    else:
        log.warn("CF management token was NOT deleted: %s" % _errors(deleted))


def wrangler_env(auth: Auth, account_id: str, scrub_global_key: bool = False) -> dict[str, str]:
    """The environment a wrangler child runs in: token and account id set, optionally without the Global API Key names.

    `CF_API_KEY` is wrangler's own deprecated alias for the Global API Key, so clearing it alongside `CF_GLOBAL_API_KEY` and `CF_EMAIL` stops wrangler warning about a variable the run does not use. The scrub applies to the child only; this process's environment is left alone.
    """
    env = dict(os.environ)
    env["CLOUDFLARE_API_TOKEN"] = auth.token
    env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    if scrub_global_key:
        for name in ("CF_GLOBAL_API_KEY", "CF_API_KEY", "CF_EMAIL"):
            env.pop(name, None)
    return env
