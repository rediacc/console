"""check:ci-region-consistency --live: the seven targets against Cloudflare, names and ids only.

WHAT IT READS, all GET, nothing written:
  workers   /accounts/<id>/workers/scripts                     every account and proxy Worker exists;
  secrets   /accounts/<id>/workers/scripts/<w>/secrets         each account Worker holds every Worker key the pusher sends (set_account_worker_secrets.KEYS; bench's deploy_bench payload is held to the same set offline) and nothing else, where `__ARCHIVE_*` recovery copies (prune_worker_secrets --archive) and the CD-owned console switch EXECUTOR_MODE (console_executor) are not extras; each proxy Worker holds no secret at all (it reads none; its executor token is minted over ISSUER);
  r2        /accounts/<id>/r2/buckets, default and `cf-r2-jurisdiction: eu`   each bound bucket exists in the jurisdiction its toml declares;
  d1        /accounts/<id>/d1/database                         each DB exists under its name with the toml's database_id.

The secrets list endpoint returns names and types, never a value, and this module prints names only.

THE CONSOLE SWITCH IS REPORTED, NOT JUDGED. EXECUTOR_MODE present means the target's console executor is open; CD sets it after the proxy smoke and its rollback deletes it, so stable and edge legitimately differ while a rollout is in flight. One line per target names the state so the asymmetry is never silent.

CREDENTIAL. CLOUDFLARE_API_TOKEN (Bearer), or CF_GLOBAL_API_KEY with CF_EMAIL, plus CLOUDFLARE_ACCOUNT_ID (cf_auth.DEFAULT_ACCOUNT_ID when unset, said out loud). The token must carry Workers Scripts Read, D1 Read and Workers R2 Storage Read. A refused or failed listing is UNCHECKED for its class, never "no drift": the caller exits 2.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
from typing import TYPE_CHECKING

from rediacc_ci.core import https
from rediacc_ci.deploy import console_executor
from rediacc_ci.deploy import set_account_worker_secrets as pusher
from rediacc_ci.ops import cf_auth
from rediacc_ci.ops.prune_worker_secrets import ARCHIVE_PREFIX, TEXT_BINDING
from rediacc_ci.quality.region_consistency_offline import Finding, Inputs, Target, blocks
from rediacc_ci.well_known import CF_API_BASE

if TYPE_CHECKING:
    from collections.abc import Callable

    # (path, extra headers) -> the envelope's (result, result_info); raises LiveError.
    Get = Callable[[str, dict[str, str]], tuple[object, dict]]
    # (class, target id or None for every target, why).
    Unchecked = tuple[str, str | None, str]

LIVE_CLASSES = ("workers", "secrets", "r2", "d1")
CD_OWNED = frozenset({console_executor.MODE_KEY})
JURISDICTION_HEADER = "cf-r2-jurisdiction"
MAX_PAGES = 50


class LiveError(Exception):
    """A listing gave no usable answer. Carries Cloudflare's error codes, never a credential."""


def credential_headers(env: dict[str, str]) -> tuple[dict[str, str], str, list[str]]:
    """(auth headers, account id, notes). Raises LiveError when no credential is present."""
    notes: list[str] = []
    token = env.get("CLOUDFLARE_API_TOKEN", "")
    if token:
        headers = {"Authorization": "Bearer " + token}
    elif env.get("CF_GLOBAL_API_KEY") and env.get("CF_EMAIL"):
        headers = {"X-Auth-Key": env["CF_GLOBAL_API_KEY"], "X-Auth-Email": env["CF_EMAIL"]}
        notes.append("authenticated with the Global API key pair (CF_GLOBAL_API_KEY)")
    else:
        raise LiveError(
            "no Cloudflare credential: set CLOUDFLARE_API_TOKEN (Workers Scripts Read, D1 Read, Workers R2 "
            "Storage Read), e.g. `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile bench-access -- ...`"
        )
    account = env.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not account:
        account = cf_auth.DEFAULT_ACCOUNT_ID
        notes.append("CLOUDFLARE_ACCOUNT_ID unset; using cf_auth.DEFAULT_ACCOUNT_ID")
    return headers, account, notes


def http_get(auth: dict[str, str]) -> Get:
    def get(path: str, extra: dict[str, str]) -> tuple[object, dict]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "rediacc-ci-region-consistency",
            **auth,
            **extra,
        }
        req = https.build_request(CF_API_BASE + path, data=None, headers=headers, method="GET")
        label = (
            path.split("?", maxsplit=1)[0].rsplit("/accounts/", maxsplit=1)[-1].split("/", 1)[-1]
        )
        try:
            with https.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise LiveError("HTTP %d on %s%s" % (exc.code, label, _errors(exc.read()))) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LiveError("transport failure on %s: %s" % (label, exc)) from None
        try:
            env = json.loads(raw)
        except ValueError:
            raise LiveError("non-JSON body on %s" % label) from None
        if not isinstance(env, dict) or env.get("success") is not True:
            raise LiveError("success is not true on %s%s" % (label, _errors(raw)))
        return env.get("result"), env.get("result_info") or {}

    return get


def _errors(raw: bytes) -> str:
    try:
        errs = json.loads(raw).get("errors") or []
        return ": " + "; ".join("%s %s" % (e.get("code"), e.get("message")) for e in errs)
    except (ValueError, AttributeError):
        return ""


def worker_names(get: Get, account: str) -> set[str]:
    result, _ = get("/accounts/%s/workers/scripts" % account, {})
    if not isinstance(result, list) or not result:
        raise LiveError(
            "the Workers listing is empty or not a list; an account with no Workers is not a verdict"
        )
    return {str(w.get("id")) for w in result if isinstance(w, dict)}


def secret_names(get: Get, account: str, worker: str) -> set[str]:
    path = "/accounts/%s/workers/scripts/%s/secrets" % (
        account,
        urllib.parse.quote(worker, safe=""),
    )
    result, _ = get(path, {})
    if not isinstance(result, list):
        raise LiveError("the secrets listing of %s is not a list" % worker)
    return {
        str(s.get("name"))
        for s in result
        if isinstance(s, dict) and s.get("type", TEXT_BINDING) == TEXT_BINDING
    }


def bucket_names(get: Get, account: str, jurisdiction: str | None) -> set[str]:
    extra = {JURISDICTION_HEADER: jurisdiction} if jurisdiction else {}
    names: set[str] = set()
    cursor = ""
    for _ in range(MAX_PAGES):
        query = "per_page=1000" + ("&cursor=" + urllib.parse.quote(cursor) if cursor else "")
        result, info = get("/accounts/%s/r2/buckets?%s" % (account, query), extra)
        buckets = result.get("buckets") if isinstance(result, dict) else None
        if not isinstance(buckets, list):
            raise LiveError(
                "the R2 listing (jurisdiction %s) carries no buckets list"
                % (jurisdiction or "default")
            )
        names |= {str(b.get("name")) for b in buckets if isinstance(b, dict)}
        cursor = str(info.get("cursor") or "")
        if not cursor:
            return names
    raise LiveError("the R2 listing did not end within %d pages" % MAX_PAGES)


def d1_databases(get: Get, account: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for page in range(1, MAX_PAGES + 1):
        result, info = get("/accounts/%s/d1/database?per_page=100&page=%d" % (account, page), {})
        if not isinstance(result, list):
            raise LiveError("the D1 listing is not a list")
        out.update({str(d.get("name")): str(d.get("uuid")) for d in result if isinstance(d, dict)})
        if page >= int(info.get("total_pages") or 1) or not result:
            break
    if not out:
        raise LiveError("the D1 listing is empty; an account with no databases is not a verdict")
    return out


def judge(
    targets: list[Target], inputs: Inputs, get: Get, account: str
) -> tuple[list[Finding], list[Unchecked], list[str]]:
    """(findings, unchecked, info lines). Every listing that fails makes its class UNCHECKED."""
    found: list[Finding] = []
    unchecked: list[Unchecked] = []
    info: list[str] = []
    pushed = {k for k, _var, _src in pusher.KEYS}
    try:
        workers = worker_names(get, account)
        found.extend(
            Finding(t.id, "workers", "Worker %s is not deployed" % w)
            for t in targets
            for w in (t.account_worker, t.proxy_worker)
            if w not in workers
        )
    except LiveError as exc:
        unchecked.append(("workers", None, str(exc)))
    for t in targets:
        try:
            live = secret_names(get, account, t.account_worker)
        except LiveError as exc:
            unchecked.append(("secrets", t.id, "%s: %s" % (t.account_worker, exc)))
            continue
        found.extend(
            Finding(
                t.id, "secrets", "%s lacks %s, which every deploy pushes" % (t.account_worker, n)
            )
            for n in sorted(pushed - live)
        )
        found.extend(
            Finding(t.id, "secrets", "%s holds %s, which no deploy pushes" % (t.account_worker, n))
            for n in sorted(live - pushed - CD_OWNED)
            if not n.startswith(ARCHIVE_PREFIX)
        )
        info.append(
            "console executor %s: %s"
            % (t.id, "open (EXECUTOR_MODE set)" if CD_OWNED & live else "closed (no EXECUTOR_MODE)")
        )
        try:
            proxy_secrets = sorted(secret_names(get, account, t.proxy_worker))
        except LiveError as exc:
            unchecked.append(("secrets", t.id, "%s: %s" % (t.proxy_worker, exc)))
            continue
        found.extend(
            Finding(
                t.id, "secrets", "%s holds %s; a proxy Worker reads no secret" % (t.proxy_worker, n)
            )
            for n in proxy_secrets
        )
    found += _r2(targets, inputs, get, account, unchecked)
    found += _d1(targets, inputs, get, account, unchecked)
    return found, unchecked, info


def _r2(
    targets: list[Target], inputs: Inputs, get: Get, account: str, unchecked: list[Unchecked]
) -> list[Finding]:
    listed: dict[str | None, set[str]] = {}
    for jur in sorted({t.jurisdiction for t in targets}, key=str):
        try:
            listed[jur] = bucket_names(get, account, jur)
        except LiveError as exc:
            unchecked.append(("r2", None, "jurisdiction %s: %s" % (jur or "default", exc)))
    if len(listed) != len({t.jurisdiction for t in targets}):
        return []
    out: list[Finding] = []
    for t in targets:
        for binding, block in sorted(blocks(inputs.account[t.id], "r2_buckets").items()):
            name, jur = block.get("bucket_name"), block.get("jurisdiction")
            if name in listed.get(jur, set()):
                continue
            elsewhere = [j or "default" for j, names in listed.items() if name in names]
            where = (
                "exists only in jurisdiction %s" % ", ".join(elsewhere)
                if elsewhere
                else "does not exist"
            )
            out.append(
                Finding(
                    t.id,
                    "r2",
                    "%s bucket %s (jurisdiction %s) %s" % (binding, name, jur or "default", where),
                )
            )
    return out


def _d1(
    targets: list[Target], inputs: Inputs, get: Get, account: str, unchecked: list[Unchecked]
) -> list[Finding]:
    try:
        dbs = d1_databases(get, account)
    except LiveError as exc:
        unchecked.append(("d1", None, str(exc)))
        return []
    out: list[Finding] = []
    for t in targets:
        db = blocks(inputs.account[t.id], "d1_databases").get("DB", {})
        name, uuid = db.get("database_name"), db.get("database_id")
        if name not in dbs:
            out.append(Finding(t.id, "d1", "D1 database %s does not exist" % name))
        elif dbs[name] != uuid:
            out.append(
                Finding(
                    t.id,
                    "d1",
                    "D1 database %s has id %s, the toml says %s" % (name, dbs[name], uuid),
                )
            )
    return out


def run(
    targets: list[Target], inputs: Inputs, env: dict[str, str] | None = None, get: Get | None = None
) -> tuple[list[Finding], list[Unchecked], tuple[str, ...]]:
    """The live layer as the gate calls it: (findings, unchecked, the classes it judged)."""
    # One explicit read per name, never a `dict(os.environ)` alias, so .ci/config/python-env-registry.json sees all four.
    source = (
        env
        if env is not None
        else {
            "CLOUDFLARE_API_TOKEN": os.environ.get("CLOUDFLARE_API_TOKEN", ""),
            "CF_GLOBAL_API_KEY": os.environ.get("CF_GLOBAL_API_KEY", ""),
            "CF_EMAIL": os.environ.get("CF_EMAIL", ""),
            "CLOUDFLARE_ACCOUNT_ID": os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
        }
    )
    try:
        auth, account, notes = credential_headers(source)
    except LiveError as exc:
        return [], [(c, None, "credential: %s" % exc) for c in LIVE_CLASSES], LIVE_CLASSES
    for note in notes:
        print("region-consistency: live: %s" % note)
    found, unchecked, info = judge(targets, inputs, get or http_get(auth), account)
    for line in info:
        print("region-consistency: %s" % line)
    return found, unchecked, LIVE_CLASSES
