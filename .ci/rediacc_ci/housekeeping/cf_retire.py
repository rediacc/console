"""Retire the Cloudflare objects the product rename left behind (agent/plans/PLAN-product-domain-rename.md, L11): the one path that deletes them.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- \\
      python3 -m rediacc_ci.housekeeping.cf_retire plan    [--only NAME ...]
      python3 -m rediacc_ci.housekeeping.cf_retire archive NAME (--dir DIR | --to-bucket BUCKET)
      python3 -m rediacc_ci.housekeeping.cf_retire delete  [--only NAME ...] [--write] [--no-archive ASKED:<YYYY-MM-DDTHH:MM>Z]

THE RETIRED SET has one source, the rename plan and the retired-terms record, and no hand-kept list beside them. A name is retired when it is (1) a "Before" name of the plan's Names table, with `<r>` read as eu, us or asia, `<n>` as a number, and a bare `-bench` cell continuing the name before it; (2) a full match of a `.ci/config/retired-terms.json` pattern; (3) a pre-rename prefix form, `rediacc-<x>` or `edge-rediacc-<x>`, of a name `<x>` a tracked wrangler config or regions.json carries (the old queues `rediacc-backup-replicate-eu` and kin); or (4) the Pages project the L11 box names. Durable Object namespaces and container applications follow their Worker: a namespace whose Worker is retired, and a container application whose namespace belongs to a retired Worker or whose name is `<retired Worker>-<class>` (the orphaned `*-executorcontainer` apps). A custom domain or route goes when its Worker does.

KEPT whatever the set says: every name the Names table lists as "Unchanged", `rediacc-public-data` (operator ruling ASKED:2026-11-13T10:07Z), and every `*-proof-loss-*` drill object. An Enterprise company's objects (`account-<c>`, `proxy-<c>`, ...) carry no pre-rename name and fall outside the set by construction.

ORDER. unbind (custom domains, routes) -> Workers, with their Durable Object namespaces (`?force=true`) -> container applications by id -> queues -> D1 -> R2 (emptied, then deleted, through the bucket's jurisdiction) -> Pages.

REFUSALS. `delete --write` changes nothing when any planned object (1) is still named by a tracked config (`cf_leftovers.reference_texts`: the wrangler configs, regions.json, `.ci/config/**` less the retired-terms record), (2) is still bound by a Worker outside the retired set (a service, D1, R2 or queue binding, a producer or consumer), or (3) holds data (a D1 with tables, an R2 bucket with objects) and has no verified archive record under `.ci/state/cf-retire/archive/`, unless the run carries `--no-archive ASKED:<minute>Z` naming the operator's answer that waives the archive. `--only` naming a name outside the retired set is refused, and every mutating call re-checks the name against the set before it is sent.

DRY RUN IS THE DEFAULT. `plan` and `delete` without `--write` send GETs only. `delete --write` prints each action before it runs and appends it, with its outcome, to `.ci/state/cf-retire/<UTC stamp>-delete.jsonl`. `archive` writes `.ci/state/cf-retire/archive/<kind>-<name>.json`: a D1 through `rediacc_ci.ops.backup_d1`'s wrangler export (verified: a non-empty file holding CREATE TABLE, its sha256 recorded); an R2 bucket either to a local directory (each key downloaded with `r2_bucket_copy.fetch_object`, its size and single-part ETag checked, its sha256 recorded and re-read from disk) or to another bucket (`r2_bucket_copy.copy`, then a per-key sha256 comparison of both sides).

Exit status: `plan` 0 when the account was read; `delete` 0 when nothing is refused and every action succeeded, 1 on a refusal or a failed call, 2 on bad usage. Environment: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID (sent in a header only and never printed); `archive` of R2 uses the aws-cli credentials `r2_bucket_copy` reads, and of D1 the `cf_auth` credentials `backup_d1` reads.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.parse

from rediacc_ci import paths
from rediacc_ci.deploy import r2_promote
from rediacc_ci.housekeeping import cf_leftovers as cfl
from rediacc_ci.ops import backup_d1, cf_auth
from rediacc_ci.ops import r2_bucket_copy as rbc

PLAN_NAME = "PLAN-product-domain-rename.md"
TERMS_PATH = ".ci/config/retired-terms.json"
RECORD_DIR = ".ci/state/cf-retire"
REGIONS = ("eu", "us", "asia")
OLD_PREFIXES = ("edge-rediacc-", "rediacc-")
# Operator ruling ASKED:2026-11-13T10:07Z: the public data bucket stays.
KEEP_NAMES = frozenset({"rediacc-public-data"})
KEEP_RE = re.compile(r"(?:^|-)proof-loss(?:-|$)")
ASKED_RE = re.compile(r"ASKED:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z")
STEPS = ("unbind", "worker", "container", "queue", "d1", "r2", "pages")
EMPTY_WORKERS = 16


class RetireError(Exception):
    """A setup or input problem that stops the run before anything is sent."""


# --- the retired set ------------------------------------------------------------------------------


def _template_regex(template: str) -> re.Pattern:
    body = re.escape(template).replace("<r>", "(?:%s)" % "|".join(REGIONS))
    return re.compile(body.replace("<n>", "[0-9]+"))


def plan_text(root) -> str:
    """The rename plan wherever it now lives under agent/plans (it moves to `_done/` at close and leaves a stub, so the copy holding the Names table is the one read)."""
    for path in sorted((root / "agent" / "plans").rglob(PLAN_NAME)):
        text = path.read_text(encoding="utf-8")
        if "\n## Names" in text:
            return text
    raise RetireError("no %s with a ## Names table under agent/plans" % PLAN_NAME)


def names_section(text: str) -> str:
    start = text.index("\n## Names")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def before_names(text: str) -> list[str]:
    """The Names table's "Before" cells as templates, a bare `-x` cell continuing the name before it (`rediacc-configs-<r>`, `-bench` -> `rediacc-configs-bench`)."""
    out: list[str] = []
    for line in names_section(text).splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 3 or cols[0] in ("Thing", "") or set(cols[0]) <= {"-"}:
            continue
        prev = ""
        for cell in re.findall(r"`([^`]+)`", cols[1]):
            name = re.sub(r"-<r>$", "", prev) + cell if cell.startswith("-") and prev else cell
            out.append(name)
            prev = name
    return out


def unchanged_names(text: str) -> set[str]:
    for line in names_section(text).splitlines():
        if "Unchanged:" in line:
            return set(re.findall(r"`([^`]+)`", line.split("Unchanged:", 1)[1]))
    raise RetireError("the Names section of %s has no Unchanged: line" % PLAN_NAME)


def l11_pages(text: str) -> list[str]:
    for line in text.splitlines():
        if re.match(r"- \[[ x]\] L11 ", line):
            return re.findall(r"Pages project `([^`]+)`", line)
    raise RetireError("%s has no L11 box" % PLAN_NAME)


@dataclasses.dataclass
class RetiredSet:
    patterns: list[tuple[str, re.Pattern]]
    keep: frozenset
    declared: frozenset

    @classmethod
    def load(cls, root) -> RetiredSet:
        text = plan_text(root)
        pats = [("Names table %s" % t, _template_regex(t)) for t in before_names(text)]
        pats += [("L11 Pages project", re.compile(re.escape(n))) for n in l11_pages(text)]
        try:
            terms = json.loads((root / TERMS_PATH).read_text(encoding="utf-8"))["terms"]
        except (OSError, ValueError, KeyError) as exc:
            raise RetireError("%s cannot be read: %s" % (TERMS_PATH, exc)) from None
        for term in terms:
            flags = 0 if term.get("case_sensitive") else re.IGNORECASE
            pats.append(("retired term %s" % term["id"], re.compile(term["pattern"], flags)))
        keep = frozenset(unchanged_names(text) | KEEP_NAMES)
        return cls(pats, keep, frozenset(cfl.declared(root)))

    def kept(self, name: str) -> str | None:
        if name in self.keep:
            return "kept by name"
        if KEEP_RE.search(name):
            return "a proof-loss drill object"
        return None

    def matched(self, name: str) -> str | None:
        """Why `name` is in the set, ignoring the keep list."""
        for label, pat in self.patterns:
            if pat.fullmatch(name):
                return label
        for prefix in OLD_PREFIXES:
            rest = name[len(prefix) :]
            if name.startswith(prefix) and rest in self.declared:
                return "pre-rename form of %s" % rest
        return None

    def why(self, name: str) -> str | None:
        return None if self.kept(name) else self.matched(name)


# --- the plan -------------------------------------------------------------------------------------


@dataclasses.dataclass
class Action:
    step: str
    name: str
    oid: str
    reason: str
    parent: str = ""  # the retired Worker a domain, route or container follows
    jurisdiction: str | None = None
    zone: str = ""
    size: int = 0
    count: int = 0
    holds_data: bool = False
    refs: list = dataclasses.field(default_factory=list)
    bound: list = dataclasses.field(default_factory=list)
    namespaces: list = dataclasses.field(default_factory=list)
    refusals: list = dataclasses.field(default_factory=list)

    def header(self) -> str | None:
        """The jurisdiction header an R2 call on this bucket needs."""
        return None if self.jurisdiction in (None, "default") else self.jurisdiction

    def line(self) -> str:
        extra = []
        if self.jurisdiction:
            extra.append("jurisdiction %s" % self.jurisdiction)
        if self.step == "d1":
            extra.append("%d table(s), %d bytes" % (self.count, self.size))
        if self.step == "r2":
            extra.append("%d object(s), %d bytes" % (self.count, self.size))
        if self.namespaces:
            extra.append("with DO namespace(s) %s" % ", ".join(self.namespaces))
        tail = "".join("; " + e for e in extra)
        return "%-9s %s  (id %s; %s%s)" % (self.step, self.name, self.oid, self.reason, tail)


class Client:
    """The Cloudflare calls: GETs through `cf_leftovers.fetch`, DELETEs through `cf_leftovers.request`."""

    def __init__(self, token: str):
        self._token = token

    def get(self, path: str, jurisdiction: str | None = None) -> dict:
        return cfl.fetch(path, self._token, jurisdiction)

    def delete(self, path: str, jurisdiction: str | None = None) -> dict:
        return cfl.request("DELETE", path, self._token, jurisdiction)


def _getter(client):
    def get(path, _token, jurisdiction=None):
        return client.get(path, jurisdiction)

    return get


def _foreign(bound: set | None, retired_scripts: set) -> list[str]:
    """The bindings held by a Worker outside the retired set (a host binder is unbound in step 1)."""
    return sorted(text for who, text in (bound or ()) if who and who not in retired_scripts)


def r2_objects(client, account: str, bucket: str, jur: str | None, limit: int = 1000) -> list[str]:
    path = "/accounts/%s/r2/buckets/%s/objects?per_page=%d" % (account, bucket, limit)
    body = client.get(path, jur)
    return [o["key"] for o in body.get("result") or [] if isinstance(o, dict) and "key" in o]


def build_plan(root, account: str, client, rs: RetiredSet) -> tuple[list[Action], list[str]]:
    """The ordered actions and the KEEP lines (objects the set matches that the keep list holds back). GETs only."""
    inv = cfl.read_inventory(account, "", _getter(client))
    texts = cfl.reference_texts(root)
    bound = inv.bound()
    kept: list[str] = []

    def judge(kind: str, name: str) -> str | None:
        why = rs.why(name)
        if why is None and rs.matched(name):
            kept.append("KEEP %-9s %s  (%s)" % (kind, name, rs.kept(name)))
        return why

    retired = {s for s in inv.scripts if judge("worker", s)}
    acts: list[Action] = []
    for dom in inv.domains:
        svc = dom.get("service")
        if svc in retired:
            why = "custom domain of %s" % svc
            acts.append(
                Action("unbind", dom.get("hostname", "?"), dom.get("id", "?"), why, parent=svc)
            )
    for zid, zname, route in inv.routes:
        script = route.get("script")
        if script in retired:
            why = "route of %s in zone %s" % (script, zname)
            acts.append(
                Action(
                    "unbind",
                    route.get("pattern", "?"),
                    route.get("id", "?"),
                    why,
                    parent=script,
                    zone=zid,
                )
            )
    ns_script = {n.get("id"): n.get("script") for n in inv.namespaces}
    for script in sorted(retired):
        a = Action("worker", script, script, rs.why(script) or "")
        a.namespaces = sorted(
            n.get("name", "?") for n in inv.namespaces if n.get("script") == script
        )
        a.bound = _foreign(bound.get(("service", script)), retired)
        acts.append(a)
    for app in inv.containers:
        name = app.get("name", "")
        script = ns_script.get((app.get("durable_objects") or {}).get("namespace_id"))
        parent = script if script in retired else ""
        if not parent:
            stem = re.sub(r"-[a-z]+$", "", name)
            parent = stem if stem != name and rs.why(stem) else ""
        if parent and not rs.kept(name):
            why = "container application of %s" % parent
            acts.append(Action("container", name, app.get("id", "?"), why, parent=parent))
    for q in inv.queues:
        name = q.get("queue_name", "")
        why = judge("queue", name)
        if why:
            foreign = _foreign(bound.get(("queue", name)), retired)
            acts.append(Action("queue", name, q.get("queue_id", "?"), why, bound=foreign))
    for db in inv.d1:
        name = db.get("name", "")
        why = judge("d1", name)
        if why:
            path = "/accounts/%s/d1/database/%s" % (account, db["uuid"])
            detail = client.get(path).get("result") or {}
            tables = int(detail.get("num_tables") or 0)
            a = Action("d1", name, db["uuid"], why, count=tables, holds_data=tables > 0)
            a.size = int(detail.get("file_size") or 0)
            a.bound = _foreign(bound.get(("d1", db["uuid"])), retired)
            acts.append(a)
    for b in inv.buckets:
        name = b["name"]
        why = judge("r2", name)
        if why:
            a = Action("r2", name, name, why, jurisdiction=b["jurisdiction"])
            path = "/accounts/%s/r2/buckets/%s/usage" % (account, name)
            usage = client.get(path, a.header()).get("result") or {}
            a.count = int(usage.get("objectCount") or 0)
            a.size = int(usage.get("payloadSize") or 0)
            # The usage figure lags writes, so one listed object also counts as data.
            a.holds_data = a.count > 0 or bool(r2_objects(client, account, name, a.header(), 1))
            a.bound = _foreign(bound.get(("r2", name)), retired)
            acts.append(a)
    for proj in inv.pages:
        name = proj.get("name", "")
        why = judge("pages", name)
        if why:
            acts.append(Action("pages", name, proj.get("id", "?"), why))
    for a in acts:
        if a.step not in ("unbind", "container"):
            a.refs = cfl.referenced_by(a.name, texts, "pages" if a.step == "pages" else "")
    acts.sort(key=lambda a: STEPS.index(a.step))
    return acts, kept


def archive_path(root, step: str, name: str) -> pathlib.Path:
    return root / RECORD_DIR / "archive" / ("%s-%s.json" % (step, name))


def archived(root, step: str, name: str) -> bool:
    try:
        record = json.loads(archive_path(root, step, name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(record, dict) and record.get("verified") is True


def judge_refusals(root, acts: list[Action], no_archive: str | None) -> int:
    """Fill each action's refusals; return how many actions are refused."""
    for a in acts:
        a.refusals = []
        if a.refs:
            a.refusals.append("still named by tracked config: %s" % ", ".join(a.refs))
        if a.bound:
            a.refusals.append("still bound outside the retired set: %s" % ", ".join(a.bound))
        if a.holds_data and not no_archive and not archived(root, a.step, a.name):
            a.refusals.append(
                "holds data and has no verified archive record "
                "(archive it, or pass --no-archive ASKED:<minute>Z)"
            )
    return sum(1 for a in acts if a.refusals)


def narrow(acts: list[Action], only: list[str], rs: RetiredSet) -> list[Action]:
    if not only:
        return acts
    for name in only:
        if not rs.why(name):
            raise RetireError("%s is outside the retired set; refusing" % name)
    known = {a.name for a in acts}
    missing = [n for n in only if n not in known]
    if missing:
        raise RetireError("%s: in the retired set but no such live object" % ", ".join(missing))
    return [a for a in acts if a.name in only or a.parent in only]


def print_actions(acts: list[Action]) -> None:
    for a in acts:
        print(("REFUSED " if a.refusals else "ACTION  ") + a.line())
        for r in a.refusals:
            print("          refused: %s" % r)


# --- the deletes ----------------------------------------------------------------------------------


def _empty_bucket(client, account: str, a: Action) -> int:
    removed = 0
    with concurrent.futures.ThreadPoolExecutor(EMPTY_WORKERS) as pool:
        while True:
            keys = r2_objects(client, account, a.name, a.header())
            if not keys:
                return removed
            base = "/accounts/%s/r2/buckets/%s/objects/" % (account, a.name)
            urls = [base + urllib.parse.quote(k, safe="") for k in keys]
            list(pool.map(lambda u: client.delete(u, a.header()), urls))
            removed += len(keys)
            print("cf_retire:   %s: %d object(s) removed" % (a.name, removed))


def run_action(client, account: str, a: Action) -> None:
    acct = "/accounts/%s" % account
    if a.step == "unbind" and a.zone:
        client.delete("/zones/%s/workers/routes/%s" % (a.zone, a.oid))
    elif a.step == "unbind":
        client.delete("%s/workers/domains/%s" % (acct, a.oid))
    elif a.step == "worker":
        client.delete("%s/workers/scripts/%s?force=true" % (acct, a.name))
    elif a.step == "container":
        client.delete("%s/containers/applications/%s" % (acct, a.oid))
    elif a.step == "queue":
        client.delete("%s/queues/%s" % (acct, a.oid))
    elif a.step == "d1":
        client.delete("%s/d1/database/%s" % (acct, a.oid))
    elif a.step == "r2":
        _empty_bucket(client, account, a)
        client.delete("%s/r2/buckets/%s" % (acct, a.name), a.header())
    elif a.step == "pages":
        client.delete("%s/pages/projects/%s" % (acct, a.name))
    else:
        raise RetireError("unknown step %s" % a.step)


def execute(
    root,
    account: str,
    client,
    rs: RetiredSet,
    acts: list[Action],
    write: bool,
    no_archive: str | None,
) -> int:
    """Print each action; send it only under `write`, recording each. Refusals stop the run before the first call."""
    refused = judge_refusals(root, acts, no_archive)
    print_actions(acts)
    if refused:
        verb = "deleted" if write else "would be deleted"
        print("cf_retire: %d action(s) refused; nothing %s" % (refused, verb), file=sys.stderr)
        return 1
    if not write:
        print("cf_retire: dry run, %d action(s), nothing deleted; --write deletes" % len(acts))
        return 0
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    record = root / RECORD_DIR / ("%s-delete.jsonl" % stamp)
    record.parent.mkdir(parents=True, exist_ok=True)

    def note(a: Action, status: str, detail: str = "") -> None:
        row = {
            "at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            "step": a.step,
            "name": a.name,
            "id": a.oid,
            "jurisdiction": a.jurisdiction,
            "status": status,
            "detail": detail,
            "no_archive": no_archive,
        }
        with record.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    for a in acts:
        guard = a.parent or a.name
        if not rs.why(guard):
            note(a, "refused", "outside the retired set")
            print("cf_retire: %s is outside the retired set; stopping" % guard, file=sys.stderr)
            return 1
        print("cf_retire: running %s" % a.line())
        note(a, "started")
        try:
            run_action(client, account, a)
        except cfl.CfError as exc:
            note(a, "failed", str(exc))
            print("cf_retire: %s %s failed: %s" % (a.step, a.name, exc), file=sys.stderr)
            return 1
        note(a, "done")
    print("cf_retire: %d action(s) done; record %s" % (len(acts), record.relative_to(root)))
    return 0


# --- archive --------------------------------------------------------------------------------------


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_d1(name: str, out_dir: pathlib.Path) -> dict:
    auth = cf_auth.resolve(backup_d1.ACCOUNT_ID)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir / ("%s-%s.sql" % (name, stamp))
    try:
        env = cf_auth.wrangler_env(auth, backup_d1.ACCOUNT_ID)
        out_dir.mkdir(parents=True, exist_ok=True)
        rc = backup_d1._export(env, name, str(out))
    finally:
        if auth.created:
            cf_auth.self_destruct(auth)
    data = out.read_bytes() if out.is_file() else b""
    return {
        "path": str(out),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "verified": rc == 0 and b"CREATE TABLE" in data,
    }


def archive_r2_dir(name: str, jur: str | None, out_dir: pathlib.Path) -> dict:
    endpoint = rbc.endpoint_for(rbc.default_endpoint(), jur)
    objs = r2_promote.Transfers(rbc.SELF, endpoint, rbc.RETRY_DELAY_S, bucket=name).list_tree("")
    keys: dict[str, str] = {}
    bad: list[str] = []
    for o in objs:
        dest = out_dir / name / o.rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        rbc.fetch_object(endpoint, name, o.rel, str(dest))
        data = dest.read_bytes()
        single = o.etag and "-" not in o.etag
        if len(data) != o.size or (
            single and hashlib.md5(data, usedforsecurity=False).hexdigest() != o.etag
        ):
            bad.append(o.rel)
        keys[o.rel] = hashlib.sha256(data).hexdigest()
    bad += [k for k, h in keys.items() if _sha256(out_dir / name / k) != h]
    return {
        "path": str(out_dir / name),
        "objects": len(objs),
        "keys": keys,
        "mismatches": bad,
        "verified": bool(objs) and not bad,
    }


def archive_r2_bucket(name: str, jur: str | None, dst: str) -> dict:
    endpoint = rbc.endpoint_for(rbc.default_endpoint(), jur)
    rc = rbc.copy(endpoint, name, dst)
    reader = r2_promote.Transfers(rbc.SELF, endpoint, rbc.RETRY_DELAY_S, bucket=name)
    keys = [o.rel for o in reader.list_tree("")]
    diffs = (
        rbc.deep_differences(endpoint, name, endpoint, dst, keys)
        if rc == 0
        else ["copy exited %d" % rc]
    )
    return {
        "to_bucket": dst,
        "objects": len(keys),
        "mismatches": diffs,
        "verified": rc == 0 and not diffs,
    }


def archive(root, acts: list[Action], args) -> int:
    match = [x for x in acts if x.name == args.name and x.step in ("d1", "r2")]
    if not match:
        raise RetireError("%s is no retired D1 database or R2 bucket of this account" % args.name)
    x = match[0]
    if x.step == "d1":
        result = archive_d1(
            x.name, pathlib.Path(args.dir) if args.dir else root / RECORD_DIR / "archive" / "d1"
        )
    elif args.dir:
        result = archive_r2_dir(x.name, x.header(), pathlib.Path(args.dir))
    else:
        result = archive_r2_bucket(x.name, x.header(), args.to_bucket)
    rec = archive_path(root, x.step, x.name)
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(
        json.dumps({"kind": x.step, "name": x.name, **result}, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "cf_retire: archive of %s %s: verified=%s; record %s"
        % (x.step, x.name, result["verified"], rec.relative_to(root))
    )
    return 0 if result["verified"] else 1


# --- main -----------------------------------------------------------------------------------------


def summary(acts: list[Action], kept: list[str]) -> None:
    for line in kept:
        print(line)
    counts = ", ".join("%d %s" % (sum(1 for a in acts if a.step == s), s) for s in STEPS)
    print("cf_retire: %s" % counts)
    holders = [a for a in acts if a.holds_data]
    print("cf_retire: %d data holder(s)" % len(holders))
    for a in holders:
        print("  %s %s: %d item(s), %d bytes" % (a.step, a.name, a.count, a.size))
    print(
        "cf_retire: %d refused, %d kept by the keep list"
        % (sum(1 for a in acts if a.refusals), len(kept))
    )


def parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="cf_retire")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--only", action="append", default=[])
    a = sub.add_parser("archive")
    a.add_argument("name")
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--dir")
    g.add_argument("--to-bucket")
    d = sub.add_parser("delete")
    d.add_argument("--only", action="append", default=[])
    d.add_argument("--write", action="store_true")
    d.add_argument("--no-archive", dest="no_archive", default=None)
    return ap.parse_args(argv)


def main(argv: list[str], client=None, root=None) -> int:
    try:
        args = parse(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    no_archive = getattr(args, "no_archive", None)
    if no_archive is not None and not ASKED_RE.fullmatch(no_archive):
        print(
            "cf_retire: --no-archive takes ASKED:<YYYY-MM-DDTHH:MM>Z naming the operator's answer",
            file=sys.stderr,
        )
        return 2
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if client is None:
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        if not token or not account:
            print(
                "cf_retire: CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are required",
                file=sys.stderr,
            )
            return 1
        client = Client(token)
    root = root or paths.repo_root()
    try:
        rs = RetiredSet.load(root)
        acts, kept = build_plan(root, account, client, rs)
        if args.cmd == "archive":
            return archive(root, acts, args)
        acts = narrow(acts, args.only, rs)
        if args.cmd == "plan":
            judge_refusals(root, acts, None)
            print_actions(acts)
            summary(acts, kept)
            print("cf_retire: plan only; nothing deleted")
            return 0
        rc = execute(root, account, client, rs, acts, args.write, no_archive)
        summary(acts, kept)
        return rc
    except (RetireError, cfl.CfError) as exc:
        print("cf_retire: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
