"""The production `Exporter` and `Teardown` of enterprise.lifecycle, over wrangler, the R2 S3 endpoint, the Cloudflare API and the enterprise bws project.

WHAT EACH CALL REACHES. `CloudflareExporter.dump_d1` runs `wrangler d1 export account-<company> --remote` (argv from `core.wrangler.ARGV`, the one spelling of a wrangler call) into a temporary file and returns its text; `bucket_keys` and `get_object` read the bucket over R2's S3 API, because the Cloudflare REST API serves no object listing (measured 2026-10-01, `ops/reset_bench.py` RULE T 1). `secrets.json` is written by `lifecycle.export` itself, at mode 0600, from the `Store` in the `Context` (the enterprise `BwsStore`), so the exporter holds no secret. `CloudflareTeardown` deletes the two Workers (`proxy-<company>` first, since it binds `account-<company>`) and the D1 database `account-<company>` through the Cloudflare API, the lookup entry through `ops.enterprise_lookup.delete` (the namespace's one writer; the KV key is the HMAC of the domain, so neither the domain nor the pepper reaches argv), the token `enterprise-<id>-backups` the `CloudflareMinter` created, each bucket (emptied over S3, then deleted through the API), and each store entry through `bws secret delete <id>`.

EVERY STEP RESUMES. Each step first reads whether its target still exists and skips it when it is gone, so a rerun of `enterprise remove` after a failure repeats nothing destructive and continues at the failed step. The teardown keeps a journal (`done`), and a failing step raises a `LifecycleError` naming the step, the opaque company id, the steps completed this run and that a rerun resumes. `lifecycle.remove` runs the steps in order and stops at the first raise, so nothing after the failed step runs and the company is not marked removed.

NO VALUE IN ARGV, A LOG LINE OR AN EXCEPTION. R2 credentials ride curl's stdin; Cloudflare auth headers ride curl's stdin through `cf_auth.curl_json`; the lookup pepper stays in the environment. No message carries a response body, a URL path, wrangler or curl output, or the company label: messages name the step, the opaque id, an HTTP status, a Cloudflare error code or an exception TYPE. Every translated exception is raised after its except block has closed, so it carries neither `__cause__` nor `__context__` (the secrets.py discipline).

EVERY EXTERNAL CALL IS A SEAM. `wrangler(argv) -> rc`, `s3(method, path) -> (status, body)`, `http(method, path, body=None, extra_headers=()) -> dict` and the bws `list_rows`/`delete` callables are constructor arguments; `live_wrangler`, `r2_s3_from_env`, `cloudflare_http` and `BwsDeleter.from_env` build the live ones. `tests/test_enterprise_lifecycle_adapters.py` drives all of it with fakes.
"""

from __future__ import annotations

import html
import os
import re
import subprocess
import tempfile
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from rediacc_ci.core import bws_env
from rediacc_ci.core import wrangler as wrangler_mod
from rediacc_ci.enterprise import secrets
from rediacc_ci.enterprise.lifecycle import LifecycleError, Target
from rediacc_ci.ops import cf_auth, enterprise_lookup

Wrangler = Callable[[list[str]], int]
S3 = Callable[[str, str], tuple[int, bytes]]
Http = Callable[..., dict]
LookupDomains = Callable[[Target], Sequence[str]]

GONE = "gone"
XML_KEY = re.compile(r"<Key>([^<]*)</Key>")
XML_NEXT_TOKEN = re.compile(r"<NextContinuationToken>([^<]*)</NextContinuationToken>")
S3_DELETED = (200, 204, 404)
# The environment variable NAMES of the operator's R2 S3 pair: (key id, its private half).
R2_ENV_NAMES = ("CLOUDFLARE_R2_ACCESS_KEY_ID", "CLOUDFLARE_R2_SECRET_ACCESS_KEY")
JURISDICTION_HEADER = "cf-r2-jurisdiction"


def d1_name(company: Target) -> str:
    return "account-%s" % company.name


def worker_names(company: Target) -> tuple[tuple[str, str], ...]:
    """(journal label, Worker name), the proxy first because it binds the account Worker."""
    return (
        ("proxy worker", "proxy-%s" % company.name),
        ("account worker", "account-%s" % company.name),
    )


def backup_token_name(company: Target) -> str:
    """The name `secrets.r2_token_name` gives the bucket-scoped backup token."""
    return "enterprise-%s-backups" % company.id


def _codes(answer: Mapping[str, Any]) -> str:
    errors = answer.get("errors")
    if not isinstance(errors, list):
        return "none"
    return ",".join(str(e.get("code")) for e in errors if isinstance(e, dict)) or "none"


def _ok(answer: object, what: str) -> Mapping[str, Any]:
    """The answer when Cloudflare reports success; otherwise a refusal naming its error codes, never its text."""
    if not isinstance(answer, Mapping):
        raise LifecycleError("Cloudflare answered %s with a non-object" % what)
    if answer.get("success") is not True:
        raise LifecycleError("Cloudflare refused %s (error codes %s)" % (what, _codes(answer)))
    return answer


def _rows(answer: Mapping[str, Any], what: str) -> list:
    rows = answer.get("result")
    if not isinstance(rows, list):
        raise LifecycleError("%s answered an unexpected shape" % what)
    return rows


def list_keys(s3: S3, bucket: str) -> list[str] | None:
    """Every key of `bucket` (ListObjectsV2, following continuation tokens), or None when the bucket does not exist. Any other non-200 page raises without naming the bucket."""
    keys: list[str] = []
    token = ""
    while True:
        query = "list-type=2&max-keys=1000"
        if token:
            query += "&continuation-token=%s" % urllib.parse.quote(token, safe="")
        status, raw = s3("GET", "%s?%s" % (bucket, query))
        if status == 404 and not token:
            return None
        if status != 200:
            raise LifecycleError("listing a company bucket answered HTTP %d" % status)
        body = raw.decode("utf-8", errors="replace")
        if "<ListBucketResult" not in body:
            raise LifecycleError("listing a company bucket answered no ListBucketResult")
        keys += [html.unescape(k) for k in XML_KEY.findall(body)]
        found = XML_NEXT_TOKEN.search(body)
        token = html.unescape(found.group(1)) if found else ""
        if "<IsTruncated>true</IsTruncated>" not in body or not token:
            return keys


def _object_path(bucket: str, key: str) -> str:
    return "%s/%s" % (bucket, urllib.parse.quote(key, safe="/"))


# --- Exporter --------------------------------------------------------------------------


class CloudflareExporter:
    """`lifecycle.Exporter` over wrangler (the D1 dump) and the R2 S3 endpoint (the bucket objects)."""

    def __init__(self, *, wrangler: Wrangler, s3: S3) -> None:
        self._wrangler = wrangler
        self._s3 = s3

    def dump_d1(self, company: Target) -> str:
        with tempfile.TemporaryDirectory(prefix="enterprise-export-") as tmp:
            out = Path(tmp) / "d1.sql"
            argv = [*wrangler_mod.ARGV, "d1", "export", d1_name(company), "--remote"]
            rc = self._wrangler([*argv, "--output=%s" % out])
            if rc != 0:
                raise LifecycleError(
                    "the d1 export of company %s exited %d; wrangler's output is withheld because it names the database"
                    % (company.id, rc)
                )
            if not out.is_file():
                raise LifecycleError(
                    "the d1 export of company %s reported success but wrote no dump" % company.id
                )
            return out.read_text(encoding="utf-8")

    def bucket_keys(self, bucket: str) -> list[str]:
        keys = list_keys(self._s3, bucket)
        if keys is None:
            raise LifecycleError(
                "listing a company bucket answered HTTP 404; the bucket is missing"
            )
        return keys

    def get_object(self, bucket: str, key: str) -> bytes:
        status, body = self._s3("GET", _object_path(bucket, key))
        if status != 200:
            raise LifecycleError("reading a company object answered HTTP %d" % status)
        return body


# --- secrets deletion ------------------------------------------------------------------


class BwsDeleter:
    """Deletes enterprise store entries by name. `list_rows` returns `bws secret list` rows; `delete(id) -> rc` is `bws secret delete <id>`, whose only argument is the entry's uuid."""

    def __init__(
        self,
        project_id: str,
        *,
        list_rows: Callable[[], list[dict]],
        delete: Callable[[str], int],
    ) -> None:
        if not project_id:
            raise LifecycleError(
                "no enterprise bws project id; company secrets are never deleted from the shared project"
            )
        self.project_id = project_id
        self._list = list_rows
        self._delete = delete
        self._rows: list[dict] | None = None

    def delete(self, name: str) -> bool:
        """Delete every row named `name` in the enterprise project; False when none was left."""
        if not secrets.STORE_NAME.fullmatch(name):
            raise LifecycleError("refusing a non-opaque store name")
        if self._rows is None:
            self._rows = list(self._list())
        ids = [
            str(r.get("id"))
            for r in self._rows
            if r.get("key") == name and r.get("projectId") == self.project_id and r.get("id")
        ]
        for secret_id in ids:
            rc = self._delete(secret_id)
            if rc != 0:
                raise LifecycleError("deleting store entry %s failed: bws exited %d" % (name, rc))
            self._rows = [r for r in self._rows if str(r.get("id")) != secret_id]
        return bool(ids)

    @classmethod
    def from_env(cls, project_id: str, env: dict | None = None) -> BwsDeleter:
        """The live deleter: `bws secret list` for the ids and `bws secret delete <id>`, output captured and dropped."""
        try:
            environ = bws_env.with_token(env)
        except bws_env.RefusalError:
            environ = None
        if environ is None:
            raise LifecycleError("no bws access token")
        binary = bws_env.binary(environ)
        if not binary:
            raise LifecycleError("no bws binary")

        def list_rows() -> list[dict]:
            try:
                return bws_env.listing(binary, environ)
            except bws_env.RefusalError:
                pass
            raise LifecycleError("bws secret list failed")

        def delete(secret_id: str) -> int:
            proc = subprocess.run(
                [binary, "secret", "delete", secret_id],
                env=environ,
                capture_output=True,
                check=False,
            )
            return int(proc.returncode)

        return cls(project_id, list_rows=list_rows, delete=delete)


# --- Teardown --------------------------------------------------------------------------


class CloudflareTeardown:
    """`lifecycle.Teardown` over the Cloudflare API, the R2 S3 endpoint, the lookup writer and the enterprise bws project. `done` journals each completed step; `lookup_domains(company)` names the company's lookup domains, which the control row does not hold."""

    def __init__(
        self,
        *,
        account_id: str,
        http: Http,
        s3: S3,
        secrets: BwsDeleter,
        lookup_domains: LookupDomains,
        lookup_run: enterprise_lookup.Runner | None = None,
        lookup_namespace: str = enterprise_lookup.NAMESPACE_ID,
        r2_jurisdiction: str | None = None,
    ) -> None:
        if not account_id:
            raise LifecycleError("no Cloudflare account id")
        self.account_id = account_id
        self._http = http
        self._s3 = s3
        self._secrets = secrets
        self._lookup_domains = lookup_domains
        self._lookup_run = lookup_run
        self._lookup_namespace = lookup_namespace
        self._jurisdiction = r2_jurisdiction
        self.done: list[str] = []

    def _do(self, label: str, company_id: str, fn: Callable[[], str | None]) -> None:
        """Run one step and journal it; a failure names the step, what ran before it, and that a rerun resumes. Raised outside the except block."""
        try:
            note = fn()
        except LifecycleError as exc:
            reason = str(exc)
        except secrets.SEAM_ERRORS as exc:
            reason = type(exc).__name__
        else:
            self.done.append(label + (" (already gone)" if note == GONE else ""))
            return
        raise LifecycleError(
            "%s failed for company %s (%s); completed this run: %s; rerun `enterprise remove` to resume from this step"
            % (label, company_id, reason, "; ".join(self.done) or "nothing")
        )

    def _account(self, rest: str) -> str:
        return "/accounts/%s%s" % (self.account_id, rest)

    def undeploy(self, company: Target) -> None:
        listed: list[set[str]] = []

        def present() -> set[str]:
            if not listed:
                what = "the Worker listing"
                rows = _rows(_ok(self._http("GET", self._account("/workers/scripts")), what), what)
                listed.append({str(r.get("id")) for r in rows if isinstance(r, dict)})
            return listed[0]

        def step_for(worker: str) -> Callable[[], str | None]:
            def step() -> str | None:
                if worker not in present():
                    return GONE
                path = "/workers/scripts/%s?force=true" % urllib.parse.quote(worker)
                _ok(self._http("DELETE", self._account(path)), "the Worker delete")
                return None

            return step

        for label, worker in worker_names(company):
            self._do("undeploy %s" % label, company.id, step_for(worker))

    def drop_lookup(self, company: Target) -> None:
        def step() -> None:
            domains = [d for d in self._lookup_domains(company) if d]
            if not domains:
                raise LifecycleError(
                    "the lookup domain of company %s is unknown; name it so its entry can be deleted"
                    % company.id
                )
            for domain in domains:
                rc, failed = self._lookup_delete(domain)
                if failed:
                    raise LifecycleError("the lookup entry could not be deleted (%s)" % failed)
                if rc != 0:
                    raise LifecycleError("the lookup delete exited %d" % rc)

        self._do("drop lookup", company.id, step)

    def _lookup_delete(self, domain: str) -> tuple[int, str]:
        """(wrangler rc, refusal type); a refusal's text quotes the domain, so only its type leaves."""
        try:
            if self._lookup_run is None:
                return enterprise_lookup.delete(domain, self._lookup_namespace), ""
            return enterprise_lookup.delete(domain, self._lookup_namespace, self._lookup_run), ""
        except enterprise_lookup.LookupRefusedError as exc:
            failed = type(exc).__name__
        return 1, failed

    def revoke_tokens(self, company: Target) -> None:
        name = backup_token_name(company)

        def step() -> str | None:
            stale: list[str] = []
            page, pages = 1, 1
            while page <= pages:
                what = "the token listing"
                path = "/user/tokens?page=%d&per_page=50" % page
                answer = _ok(self._http("GET", path), what)
                stale += [
                    str(r["id"])
                    for r in _rows(answer, what)
                    if isinstance(r, dict) and r.get("name") == name and r.get("id")
                ]
                info = answer.get("result_info")
                pages = int(info.get("total_pages") or 1) if isinstance(info, dict) else 1
                page += 1
            for token_id in stale:
                _ok(self._http("DELETE", "/user/tokens/%s" % token_id), "the token delete")
            return None if stale else GONE

        self._do("revoke backup token", company.id, step)

    def delete_bucket(self, company: Target, bucket: str) -> None:
        if bucket not in company.buckets:
            raise LifecycleError(
                "refusing to delete a name that is not a bucket of company %s" % company.id
            )
        kind = bucket.split("-", 1)[0]

        def step() -> str | None:
            keys = list_keys(self._s3, bucket)
            if keys is None:
                return GONE
            for index, key in enumerate(keys):
                status, _body = self._s3("DELETE", _object_path(bucket, key))
                if status not in S3_DELETED:
                    raise LifecycleError(
                        "deleting an object answered HTTP %d; %d of %d objects deleted"
                        % (status, index, len(keys))
                    )
            extra = (
                ("%s: %s" % (JURISDICTION_HEADER, self._jurisdiction),)
                if self._jurisdiction
                else ()
            )
            path = self._account("/r2/buckets/%s" % urllib.parse.quote(bucket))
            _ok(self._http("DELETE", path, None, extra), "the bucket delete")
            return None

        self._do("delete %s bucket" % kind, company.id, step)

    def delete_d1(self, company: Target) -> None:
        name = d1_name(company)

        def step() -> str | None:
            what = "the D1 listing"
            query = urllib.parse.urlencode({"name": name, "per_page": 100})
            answer = _ok(self._http("GET", self._account("/d1/database?%s" % query)), what)
            # The name filter matches substrings, so only an exact name is this company's database.
            uuids = [
                str(r["uuid"])
                for r in _rows(answer, what)
                if isinstance(r, dict) and r.get("name") == name and r.get("uuid")
            ]
            for uuid in uuids:
                _ok(self._http("DELETE", self._account("/d1/database/%s" % uuid)), "the D1 delete")
            return None if uuids else GONE

        self._do("delete d1", company.id, step)

    def delete_secret(self, name: str) -> None:
        company_id = name.split("_", 1)[0] if secrets.STORE_NAME.fullmatch(name) else "?"

        def step() -> str | None:
            return None if self._secrets.delete(name) else GONE

        self._do("delete secret %s" % name, company_id, step)


# --- live transports -------------------------------------------------------------------


def live_wrangler(
    cwd: Path,
    env: Mapping[str, str],
    *,
    runner: Callable[..., Any] = subprocess.run,
    require: Callable[..., Any] = wrangler_mod.require,
) -> Wrangler:
    """A wrangler runner in `cwd` (a worker directory with the pinned install) under `env` (`cf_auth.wrangler_env`). Both streams are captured and dropped: wrangler prints the database name and a pre-signed URL."""
    require(cwd, env)

    def run(argv: list[str]) -> int:
        proc = runner(argv, cwd=cwd, env=dict(env), capture_output=True, text=True, check=False)
        return int(proc.returncode)

    return run


def r2_s3(
    endpoint: str, key_id: str, private_key: str, *, runner: Callable[..., Any] = subprocess.run
) -> S3:
    """SigV4-signed requests to R2's S3 endpoint (the `secrets.Company.backup_endpoint` shape); the credentials travel on curl's stdin, never argv."""
    base = endpoint.rstrip("/")
    config = ('user = "%s:%s"\n' % (key_id, private_key)).encode()

    def call(method: str, path: str) -> tuple[int, bytes]:
        proc = runner(
            [
                *("curl", "-sS", "-X", method, "--aws-sigv4", "aws:amz:auto:s3"),
                *("-K", "-", "-w", "\n%{http_code}", "%s/%s" % (base, path)),
            ],
            input=config,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise LifecycleError(
                "an R2 request failed (curl exit %d); its output is withheld" % proc.returncode
            )
        body, _, status = bytes(proc.stdout).rpartition(b"\n")
        return (int(status) if status.isdigit() else 0), body

    return call


def r2_s3_from_env(endpoint: str, env: Mapping[str, str] | None = None) -> S3:
    """`r2_s3` with the operator's R2 S3 pair read by name from `env`: an admin pair, since the company's own token reaches only its backups bucket."""
    source = os.environ if env is None else env
    missing = [n for n in R2_ENV_NAMES if not source.get(n)]
    if missing:
        raise LifecycleError("missing R2 S3 credentials: %s" % ", ".join(missing))
    return r2_s3(endpoint, source[R2_ENV_NAMES[0]], source[R2_ENV_NAMES[1]])


def cloudflare_http(headers: list[str]) -> Http:
    """The live API transport over `cf_auth.curl_json`, which moves the auth headers to curl's stdin. A failure names the method only, because the path carries the company label."""

    def http(
        method: str, path: str, body: str | None = None, extra_headers: Sequence[str] = ()
    ) -> dict:
        argv_headers = [*headers]
        for header in extra_headers:
            argv_headers += ["-H", header]
        try:
            return cf_auth.curl_json(method, cf_auth.CF_API_BASE + path, argv_headers, body)
        except cf_auth.CfAuthError:
            pass
        raise LifecycleError("a Cloudflare %s request failed" % method)

    return http
