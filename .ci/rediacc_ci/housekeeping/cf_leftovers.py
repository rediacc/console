"""Report-only listing of Cloudflare leftovers that no PR cleanup owns.

PLAN-cloudflare-spend-guard T7, widened for PLAN-product-domain-rename L11. Every listing is a GET, nothing is deleted or changed:

  script     a Workers script named by no `workers/*/wrangler*.toml` (nor `private/account/wrangler.toml`) and not a PR preview (`pr-<n>`, which the PR-close cleanup owns)
  d1         a D1 database matching `edge-*`, `*-bench` or the jurisdictional `*-bench-j` that no config binds as `database_name`
  route      a Workers route in any zone whose script is absent from the account, or that names no script
  domain     a Workers custom domain whose service is absent from the account
  bucket     an R2 bucket, in the default jurisdiction or in `eu`, whose name no wrangler config or regions.json carries
  queue      a Queue whose name no wrangler config carries
  container  a container application whose Durable Object namespace belongs to no configured Worker, or to no Worker at all
  do         a Durable Object namespace whose Worker no wrangler config names
  pages      a Pages project whose name no wrangler config or regions.json carries

Each row carries the object's id, `referenced:` (the tracked config files that still name it: `workers/**/wrangler*.toml`, regions.json and `.ci/config/**`, the retired-terms record excepted, since naming a retired name is its job) and `bound:` (the custom domains, routes, service, D1, R2 and queue bindings of other Workers, and the queue producers and consumers that still point at it). A referenced or bound leftover is not safe to delete as it stands; `rediacc_ci.housekeeping.cf_retire` is the path that deletes, and it refuses both.

Masking (agent/plans/PLAN-enterprise-isolation.md, N2): the housekeeping log is public, and an Enterprise company's Workers, routes and hosts carry its name and are named by no tracked config, so every one of them would print here as a leftover. Each printed line goes through `rediacc_ci.quality.enterprise_leak.Masker`, which turns a company label into `<company-N>` and leaves every public name as it is; a company-shaped leftover says so in its line, since the control database, not a wrangler config, accounts for it. `--unmasked` prints real names for a local run and is refused under `GITHUB_ACTIONS`; a masker that cannot be built is exit 1, the same as an unreadable listing.

Exit status: 0 whatever was found (a finding is a report line, never a failure). 1 when a listing could not be read or the environment is incomplete: an unreadable listing printed as "nothing found" is the vacuity this report must not have.

Usage: PYTHONPATH=.ci python3 -m rediacc_ci.housekeeping.cf_leftovers
Environment: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID. The token is sent in a header only and never printed.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.parse

from rediacc_ci import paths
from rediacc_ci.core import https
from rediacc_ci.quality import enterprise_leak as leak
from rediacc_ci.well_known import CF_API_BASE

PR_SCRIPT_RE = re.compile(r"^pr-[0-9]+$")
# `*-bench-j` and `*-bench-*-j` are the bench databases created under a jurisdiction (`account-bench-j`, `control-bench-eu-j`).
D1_PATTERNS = ("edge-*", "*-bench", "*-bench-j", "*-bench-*-j")
CONFIG_GLOBS = ("workers/*/wrangler*.toml", "private/account/wrangler*.toml")
# The tracked files whose naming an object counts as a reference: the deploy configs, templates included (a template naming an object still deploys it), regions.json and .ci/config. The retired-terms record names retired objects by design, so it is no reference.
REF_GLOBS = ("workers/*/wrangler*.toml", "private/account/wrangler*.toml", "regions.json")
REF_DIR = ".ci/config"
REF_EXCLUDE = frozenset({".ci/config/retired-terms.json"})
REF_MAX_BYTES = 4 << 20
R2_JURISDICTIONS = ("default", "eu")
R2_JURISDICTION_HEADER = "cf-r2-jurisdiction"
PAGE = 100


class CfError(Exception):
    """A Cloudflare read that failed; the message names the path and Cloudflare's own errors."""


def request(method: str, path: str, token: str, jurisdiction: str | None = None) -> dict:
    """One API call, returning the decoded body and raising CfError on any failure. The only network call here; `cf_retire` sends its DELETEs through it. `jurisdiction` sets the `cf-r2-jurisdiction` header an R2 call needs to see an `eu` bucket."""
    headers = {"Authorization": "Bearer " + token}
    if jurisdiction is not None:
        headers[R2_JURISDICTION_HEADER] = jurisdiction
    try:
        req = https.build_request(CF_API_BASE + path, headers=headers, method=method)
        with https.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
        except OSError as read_exc:
            raise CfError(
                "%s %s: HTTP %s, body unreadable: %s" % (method, path, exc.code, read_exc)
            ) from None
        finally:
            exc.close()
    except OSError as exc:
        # URLError, a timeout and a connection reset while reading the body are all OSErrors.
        raise CfError("%s %s: %s" % (method, path, exc)) from None
    try:
        body = json.loads(raw)
    except ValueError:
        raise CfError("%s %s: non-JSON answer" % (method, path)) from None
    if not isinstance(body, dict) or body.get("success") is not True:
        errors = body.get("errors") if isinstance(body, dict) else None
        raise CfError("%s %s: %s" % (method, path, json.dumps(errors)))
    return body


def fetch(path: str, token: str, jurisdiction: str | None = None) -> dict:
    """GET one API path (see `request`)."""
    return request("GET", path, token, jurisdiction)


def _get(get, path: str, token: str, jurisdiction: str | None = None) -> dict:
    """Call a `get` that may be a two-argument fake: the jurisdiction is passed only when one is set."""
    if jurisdiction is None:
        return get(path, token)
    return get(path, token, jurisdiction=jurisdiction)


def listing(path: str, token: str, get=fetch) -> list:
    """Every `result` item of a paginated path (`per_page` and `page` appended)."""
    sep = "&" if "?" in path else "?"
    items: list = []
    page = 1
    while True:
        body = get("%s%sper_page=%d&page=%d" % (path, sep, PAGE, page), token)
        chunk = body.get("result") or []
        items.extend(chunk)
        info = body.get("result_info") or {}
        total_pages = info.get("total_pages")
        if total_pages is not None:
            if page >= total_pages:
                break
        elif len(chunk) < PAGE:
            break
        page += 1
    return items


def _dbs(node, dbs: set) -> None:
    if isinstance(node, dict):
        db = node.get("database_name")
        if isinstance(db, str):
            dbs.add(db)
        for value in node.values():
            _dbs(value, dbs)
    elif isinstance(node, list):
        for value in node:
            _dbs(value, dbs)


def configured(root) -> tuple[set, set]:
    """(Worker names, D1 database names) the repo's wrangler configs declare, `[env.*]` blocks included."""
    scripts: set = set()
    dbs: set = set()
    # A template carries bare @@ placeholders and is not TOML until rendered, so it is not a config: a tree holding only templates is as empty as one holding nothing.
    files = sorted({p for g in CONFIG_GLOBS for p in root.glob(g) if ".template." not in p.name})
    if not files:
        raise CfError("no wrangler config found under %s" % root)
    for path in files:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            raise CfError("%s cannot be read: %s" % (path, exc)) from None
        top = data.get("name")
        if isinstance(top, str):
            scripts.add(top)
        for env in (data.get("env") or {}).values():
            if isinstance(env, dict) and isinstance(env.get("name"), str):
                scripts.add(env["name"])
        _dbs(data, dbs)
    return scripts, dbs


def _strings(node, out: set) -> None:
    if isinstance(node, str):
        out.add(node)
    elif isinstance(node, dict):
        for value in node.values():
            _strings(value, out)
    elif isinstance(node, list):
        for value in node:
            _strings(value, out)


def declared(root) -> set:
    """Every string a deploy config carries: each non-template wrangler config's values and regions.json's. An object whose name is among them is one the repo deploys."""
    out: set = set()
    files = sorted({p for g in CONFIG_GLOBS for p in root.glob(g) if ".template." not in p.name})
    for path in files:
        try:
            _strings(tomllib.loads(path.read_text(encoding="utf-8")), out)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            raise CfError("%s cannot be read: %s" % (path, exc)) from None
    regions = root / "regions.json"
    if regions.is_file():
        try:
            _strings(json.loads(regions.read_text(encoding="utf-8")), out)
        except (ValueError, OSError) as exc:
            raise CfError("%s cannot be read: %s" % (regions, exc)) from None
    return out


def reference_texts(root) -> dict[str, str]:
    """The text of every file whose naming an object is a reference (REF_GLOBS and REF_DIR), keyed by repo-relative path."""
    files = {p for g in REF_GLOBS for p in root.glob(g)}
    ref_dir = root / REF_DIR
    if ref_dir.is_dir():
        files |= {p for p in ref_dir.rglob("*") if p.is_file()}
    texts: dict[str, str] = {}
    for path in sorted(files):
        rel = path.relative_to(root).as_posix()
        if rel in REF_EXCLUDE:
            continue
        try:
            if path.stat().st_size > REF_MAX_BYTES:
                raise CfError("%s is over %d bytes and cannot be searched" % (rel, REF_MAX_BYTES))
            texts[rel] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            raise CfError("%s cannot be read: %s" % (rel, exc)) from None
    return texts


def referenced_by(name: str, texts: dict[str, str], kind: str = "") -> list[str]:
    """The files of `texts` that name `name` as a whole token (a longer name that contains it does not count). A Pages project's name is often a plain word (`rediacc`), so for `pages` only the shapes that name a project count: `<name>.pages.dev`, `pages/projects/<name>` and `--project-name <name>`."""
    esc = re.escape(name)
    if kind == "pages":
        pat = re.compile(
            r"(?<![A-Za-z0-9_-])%s\.pages\.dev|pages/projects/%s(?![A-Za-z0-9_-])"
            r"|--project-name[= ]%s(?![A-Za-z0-9_-])" % (esc, esc, esc)
        )
    else:
        pat = re.compile(r"(?<![A-Za-z0-9_-])%s(?![A-Za-z0-9_-])" % esc)
    return [rel for rel, text in texts.items() if pat.search(text)]


def listing_by_page(path: str, token: str, get=fetch) -> list:
    """Every `result` item of a path that pages by `page` alone (Pages projects refuse `per_page`)."""
    sep = "&" if "?" in path else "?"
    items: list = []
    page = 1
    while True:
        body = get("%s%spage=%d" % (path, sep, page), token)
        items.extend(body.get("result") or [])
        total = (body.get("result_info") or {}).get("total_pages") or 1
        if page >= total:
            return items
        page += 1


def r2_buckets(account: str, token: str, get=fetch) -> list[dict]:
    """Every R2 bucket as {name, jurisdiction}, across R2_JURISDICTIONS: one listing per jurisdiction, since a listing without the header never shows an `eu` bucket."""
    out: list[dict] = []
    for jur in R2_JURISDICTIONS:
        header = None if jur == "default" else jur
        cursor, seen = "", set()
        while True:
            path = "/accounts/%s/r2/buckets?per_page=1000" % account
            if cursor:
                path += "&cursor=" + urllib.parse.quote(cursor, safe="")
            body = _get(get, path, token, header)
            result = body.get("result") or {}
            out.extend(
                {"name": b["name"], "jurisdiction": jur}
                for b in result.get("buckets") or []
                if isinstance(b, dict) and isinstance(b.get("name"), str)
            )
            cursor = (body.get("result_info") or {}).get("cursor") or ""
            if not cursor or cursor in seen:
                break
            seen.add(cursor)
    return out


@dataclasses.dataclass
class Inventory:
    """One read of every Cloudflare object class the leftover report and `cf_retire` judge."""

    scripts: list[str]
    bindings: dict[str, list[dict]]
    d1: list[dict]
    routes: list[tuple[str, str, dict]]
    domains: list[dict]
    buckets: list[dict]
    queues: list[dict]
    containers: list[dict]
    namespaces: list[dict]
    pages: list[dict]

    def bound(self) -> dict[tuple[str, str], set[tuple[str, str]]]:
        """(kind, target) -> {(binder, description)}: `service`, `d1` (uuid), `r2` (bucket), `queue` (name) from Worker bindings, `queue` from producers and consumers, `script` from custom domains and routes. The binder is the Worker that holds the binding, or the empty string for a host."""
        out: dict[tuple[str, str], set[tuple[str, str]]] = {}

        def add(key: tuple[str, str], text: str, who: str = "") -> None:
            out.setdefault(key, set()).add((who, text))

        for script, items in self.bindings.items():
            for b in items:
                kind = b.get("type")
                if kind == "service" and b.get("service"):
                    add(("service", b["service"]), "service binding of %s" % script, script)
                elif kind == "d1" and b.get("id"):
                    add(("d1", b["id"]), "d1 binding of %s" % script, script)
                elif kind == "r2_bucket" and b.get("bucket_name"):
                    add(("r2", b["bucket_name"]), "r2 binding of %s" % script, script)
                elif kind == "queue" and b.get("queue_name"):
                    add(("queue", b["queue_name"]), "queue binding of %s" % script, script)
        for q in self.queues:
            for role in ("producers", "consumers"):
                for p in q.get(role) or []:
                    who = p.get("script") or p.get("service") if isinstance(p, dict) else None
                    if who:
                        add(("queue", q.get("queue_name", "")), "%s %s" % (role[:-1], who), who)
        for dom in self.domains:
            if dom.get("service"):
                add(("script", dom["service"]), "custom domain %s" % dom.get("hostname", "?"))
        for _zid, zname, route in self.routes:
            if route.get("script"):
                add(
                    ("script", route["script"]),
                    "route %s (zone %s)" % (route.get("pattern"), zname),
                )
        return out


def read_inventory(account: str, token: str, get=fetch, with_bindings: bool = True) -> Inventory:
    """Read every object class. Raises CfError when any listing cannot be read."""
    scripts = sorted(
        {
            s["id"]
            for s in listing("/accounts/%s/workers/scripts" % account, token, get)
            if isinstance(s, dict) and isinstance(s.get("id"), str)
        }
    )
    bindings: dict[str, list[dict]] = {}
    if with_bindings:
        for name in scripts:
            body = get("/accounts/%s/workers/scripts/%s/settings" % (account, name), token)
            items = (body.get("result") or {}).get("bindings") or []
            bindings[name] = [b for b in items if isinstance(b, dict)]
    routes: list[tuple[str, str, dict]] = []
    # Only this account's zones: a route in another account's zone may name a script that lives here and is not a leftover of this account.
    for zone in listing("/zones?account.id=%s" % account, token, get):
        owner = (zone.get("account") or {}).get("id")
        if owner is not None and owner != account:
            continue
        zid, zname = zone.get("id"), zone.get("name", "?")
        routes.extend(
            (zid, zname, r) for r in listing("/zones/%s/workers/routes" % zid, token, get)
        )
    containers = get("/accounts/%s/containers/applications" % account, token).get("result") or []
    return Inventory(
        scripts=scripts,
        bindings=bindings,
        d1=[
            d
            for d in listing("/accounts/%s/d1/database" % account, token, get)
            if isinstance(d, dict)
        ],
        routes=routes,
        domains=listing("/accounts/%s/workers/domains" % account, token, get),
        buckets=r2_buckets(account, token, get),
        queues=listing("/accounts/%s/queues" % account, token, get),
        containers=[c for c in containers if isinstance(c, dict)],
        namespaces=listing("/accounts/%s/workers/durable_objects/namespaces" % account, token, get),
        pages=listing_by_page("/accounts/%s/pages/projects" % account, token, get),
    )


def _row_detail(base: str, oid, name: str, texts: dict[str, str], bound, kind: str = "") -> str:
    refs = referenced_by(name, texts, kind)
    return "%s; id %s; referenced: %s; bound: %s" % (
        base,
        oid or "?",
        ", ".join(refs) if refs else "no",
        ", ".join(sorted(text for _who, text in bound)) if bound else "no",
    )


def find_leftovers(
    root, account: str, token: str, get=fetch, scanned: dict | None = None
) -> list[tuple[str, str, str]]:
    """Every (kind, name, detail) leftover. Raises CfError when any listing cannot be read."""
    known_scripts, known_dbs = configured(root)
    names = declared(root)
    texts = reference_texts(root)
    inv = read_inventory(account, token, get)
    bound = inv.bound()
    live_set = set(inv.scripts)
    counts = {
        "scripts": len(live_set),
        "d1": len(inv.d1),
        "routes": len(inv.routes),
        "domains": len(inv.domains),
        "buckets": len(inv.buckets),
        "queues": len(inv.queues),
        "containers": len(inv.containers),
        "do": len(inv.namespaces),
        "pages": len(inv.pages),
    }
    out: list[tuple[str, str, str]] = []

    out.extend(
        (
            "script",
            name,
            _row_detail(
                "named by no wrangler config",
                name,
                name,
                texts,
                bound.get(("script", name), set()) | bound.get(("service", name), set()),
            ),
        )
        for name in sorted(live_set)
        if name not in known_scripts and not PR_SCRIPT_RE.match(name)
    )

    for db in inv.d1:
        name = db.get("name", "")
        if any(fnmatch.fnmatchcase(name, pat) for pat in D1_PATTERNS) and name not in known_dbs:
            out.append(("d1", name, "bound by no wrangler config (uuid %s)" % db.get("uuid", "?")))

    for _zid, zname, route in inv.routes:
        script = route.get("script")
        pattern = route.get("pattern", "?")
        if not script:
            out.append(("route", pattern, "zone %s: names no script" % zname))
        elif script not in live_set:
            out.append(("route", pattern, "zone %s: script %s does not exist" % (zname, script)))

    for dom in inv.domains:
        service = dom.get("service")
        if service not in live_set:
            out.append(("domain", dom.get("hostname", "?"), "service %s does not exist" % service))

    for b in inv.buckets:
        if b["name"] not in names:
            base = "jurisdiction %s, carried by no deploy config" % b["jurisdiction"]
            out.append(
                (
                    "bucket",
                    b["name"],
                    _row_detail(base, b["name"], b["name"], texts, bound.get(("r2", b["name"]))),
                )
            )

    for q in inv.queues:
        name = q.get("queue_name", "?")
        if name not in names:
            out.append(
                (
                    "queue",
                    name,
                    _row_detail(
                        "carried by no wrangler config",
                        q.get("queue_id"),
                        name,
                        texts,
                        bound.get(("queue", name)),
                    ),
                )
            )

    ns_script = {n.get("id"): n.get("script") for n in inv.namespaces}
    for app in inv.containers:
        name = app.get("name", "?")
        ns = (app.get("durable_objects") or {}).get("namespace_id")
        script = ns_script.get(ns)
        if script is None:
            base = "its Durable Object namespace %s exists no more" % ns
        elif script not in known_scripts:
            base = "its Worker %s is named by no wrangler config" % script
        else:
            continue
        out.append(("container", name, _row_detail(base, app.get("id"), name, texts, None)))

    for n in inv.namespaces:
        script = n.get("script")
        if script not in known_scripts:
            base = "class %s of Worker %s, named by no wrangler config" % (n.get("class"), script)
            out.append(
                (
                    "do",
                    n.get("name", "?"),
                    _row_detail(base, n.get("id"), n.get("name", "?"), texts, None),
                )
            )

    for proj in inv.pages:
        name = proj.get("name", "?")
        if name not in names:
            base = "domains %s" % (", ".join(proj.get("domains") or []) or "none")
            out.append(
                ("pages", name, _row_detail(base, proj.get("id"), name, texts, None, "pages"))
            )

    if scanned is not None:
        scanned.update(counts)
    return out


def main(argv: list[str], get=fetch) -> int:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not account:
        print("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are required", file=sys.stderr)
        return 1
    try:
        masker, refusal = leak.report_masker(list(argv), os.environ, "cf_leftovers")
    except leak.LeakSetupError as exc:
        print("cf_leftovers: names cannot be masked: %s" % exc, file=sys.stderr)
        return 1
    if masker is None:
        print(refusal, file=sys.stderr)
        return 1
    try:
        scanned: dict = {}
        found = find_leftovers(paths.repo_root(), account, token, get, scanned)
    except CfError as exc:
        print("cf_leftovers: cannot read: %s" % exc, file=sys.stderr)
        return 1
    for kind, name, detail in found:
        shown = masker.mask(name)
        why = detail if shown == name else detail + "; company-shaped name, masked"
        print("LEFTOVER %-6s %s  (%s)" % (kind, shown, masker.mask(why)))
    print("cf_leftovers: scanned %s" % ", ".join("%d %s" % (v, k) for k, v in scanned.items()))
    print(
        "cf_leftovers: %d leftover(s); report only, nothing deleted; %d company label(s) masked%s"
        % (len(found), masker.masked, "" if masker.enabled else " (--unmasked: names shown)")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
