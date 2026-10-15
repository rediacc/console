r"""check:ci-backup-credential-isolation -- each environment's account Workers hold only their own bucket-scoped backup key, and nothing account-wide stands in for it.

WHY. Until 2026-10-15 `deploy_bench` filled every empty `ACCOUNT_BACKUP_S3_*` value from the account-wide R2 token, and the deploy-bench profile supplied only that token, so the public bench Worker held a key that reaches every bucket in the account; every other Worker shared one hand-minted pair. agent/plans/PLAN-backup-credential-isolation.md splits the credential into three bucket-scoped tokens (stable, edge, bench), each limited to object read and write on its own environment's backup buckets. This gate pins the split in the tree, so a later edit cannot quietly re-widen it. It reads NAMES only: configuration files, workflow files and one Python module's string constants. No value is read from anywhere, and none could be printed.

THE RULES, each with a plant in the controls that must turn it red:

  bench-no-fallback   `.ci/rediacc_ci/ops/deploy_bench.py` holds no string constant
                      containing `CLOUDFLARE_R2_` (the AST, so a docstring, an
                      f-string piece or a message counts; a comment does not).
  profile-source      no profile in `.ci/config/secret-supply.json` binds a
                      `CLOUDFLARE_*` store entry (the R2 trio, the API token) to an
                      `ACCOUNT_BACKUP_S3_*` name.
  profile-pair        a profile binding `ACCOUNT_BACKUP_S3_ACCESS_KEY_ID` or
                      `..._SECRET_ACCESS_KEY` takes both halves from ONE environment
                      suffix (`_STABLE`, `_EDGE`, `_BENCH`), never the unsuffixed
                      store entry and never two environments. Census: deploy-bench
                      binds bench, backup-push-<env> binds <env>.
  workflow-pair       no workflow or action requests the unsuffixed pair or the
                      `_BENCH` pair; a `_STABLE` request sits in a bws-secrets step whose
                      `if:` is exactly `inputs.target == 'stable'`, an `_EDGE` request in
                      one whose `if:` is exactly `inputs.target != 'stable'`. Census: at
                      least one of each is seen.
  workflow-source     no workflow env value or bws-secrets spec feeds an
                      `ACCOUNT_BACKUP_S3_*` name from `CLOUDFLARE_R2_*` or
                      `CLOUDFLARE_API_TOKEN` (as `env.BWS_...`, `secrets....` or a
                      `run:` assignment).
  rotation-scopes     `private/account/scripts/rotation/r2-backup-tokens.json`: the three
                      slugs exist, their BWS names are pairwise disjoint and carry their
                      own suffix, their bucket sets equal regions.json `backupR2`
                      (stable), `edgeBackupR2` (edge) and wrangler.bench.toml's
                      BACKUP_BUCKET (bench) with matching jurisdictions, and no entry
                      carries an account or zone permission.

`ACCOUNT_BACKUP_S3_ENDPOINT` IS SHARED BY DESIGN. It is not a credential (one host per account; `set_account_worker_secrets.apply_jurisdiction` adds the `.eu.` label), so every rule above lets every profile and workflow bind it, and the disjointness rule ignores it.

SKIP IS NOT PASS. The rotation-scopes file lives in the private/account submodule. When the submodule is not checked out, or the file does not exist yet, the rule prints `SKIP` with the reason on every run and the summary line names it; the other five rules still decide the verdict. Every other way of seeing nothing is a refusal (exit 2): no workflow file, no profile, deploy_bench.py missing or not naming the backup values.

Exit 0 when every rule that ran is clean, 1 on any finding, 2 on a failed control or a corpus the gate cannot read.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
import tomllib
from dataclasses import dataclass, field

from rediacc_ci import log, paths, workflows
from rediacc_ci.controls import Checker, controls_first, plant
from rediacc_ci.core import bws_env

DEPLOY_BENCH_REL = ".ci/rediacc_ci/ops/deploy_bench.py"
SUPPLY_REL = ".ci/config/secret-supply.json"
REGIONS_REL = "regions.json"
BENCH_TOML_REL = "workers/account/wrangler.bench.toml"
SCOPES_REL = "private/account/scripts/rotation/r2-backup-tokens.json"
SUBMODULE_REL = "private/account"

ENVS = ("STABLE", "EDGE", "BENCH")
SLUGS = {
    "STABLE": "cf-r2-backup-stable",
    "EDGE": "cf-r2-backup-edge",
    "BENCH": "cf-r2-backup-bench",
}
PAIR = ("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY")
SHARED = "ACCOUNT_BACKUP_S3_ENDPOINT"
PAIR_RE = re.compile(
    r"^(ACCOUNT_BACKUP_S3_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY))(?:_(STABLE|EDGE|BENCH))?$"
)
WIDE_STORE_RE = re.compile(r"^CLOUDFLARE_")
# A value expression that reaches an account-wide Cloudflare credential, in any of the spellings a workflow uses.
WIDE_REF_RE = re.compile(
    r"(?:BWS_CLOUDFLARE_R2_|secrets\.CLOUDFLARE_R2_|env\.CLOUDFLARE_R2_|\$\{?CLOUDFLARE_R2_|"
    r"BWS_CLOUDFLARE_API_TOKEN|secrets\.CLOUDFLARE_API_TOKEN|env\.CLOUDFLARE_API_TOKEN|\$\{?CLOUDFLARE_API_TOKEN)"
)
RUN_ASSIGN_RE = re.compile(r"\bACCOUNT_BACKUP_S3_[A-Z_]*=([^\s;&|]*)")
BWS_ACTION = "./.github/actions/bws-secrets"
STABLE_IF = "inputs.target == 'stable'"
EDGE_IF = "inputs.target != 'stable'"
BUCKET_PERMS = frozenset(
    {"Workers R2 Storage Bucket Item Read", "Workers R2 Storage Bucket Item Write"}
)
PROFILE_CENSUS = {
    "deploy-bench": "BENCH",
    "backup-push-stable": "STABLE",
    "backup-push-edge": "EDGE",
    "backup-push-bench": "BENCH",
}
RULES = (
    "bench-no-fallback",
    "profile-source",
    "profile-pair",
    "workflow-pair",
    "workflow-source",
    "rotation-scopes",
)


class CannotRunError(Exception):
    """The gate cannot see its corpus; a verdict would mean nothing."""


@dataclass(frozen=True)
class Finding:
    rule: str
    where: str
    what: str

    def line(self) -> str:
        return "%s  %s: %s" % (self.rule, self.where, self.what)


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    skips: list[str] = field(default_factory=list)
    shape: dict[str, int] = field(default_factory=dict)


# --------------------------------------------------------------------------- rule: bench-no-fallback


def bench_fallback(source: str, where: str = DEPLOY_BENCH_REL) -> list[Finding]:
    """Every string constant in deploy_bench's source naming `CLOUDFLARE_R2_`. CannotRunError when the module does not parse or does not name the backup values at all (the gate would be reading the wrong file)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CannotRunError("%s does not parse (%s)" % (where, exc.msg)) from None
    constants = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    if not any(PAIR[0] in str(node.value) for node in constants):
        raise CannotRunError(
            "%s names no %s; the gate is not reading the bench deploy" % (where, PAIR[0])
        )
    return [
        Finding(
            "bench-no-fallback",
            "%s:%d" % (where, node.lineno),
            "a string naming CLOUDFLARE_R2_ is back in the bench deploy. The account-wide R2 "
            "token must never fill ACCOUNT_BACKUP_S3_*: bind the bench-scoped pair in the "
            "deploy-bench profile and read only ACCOUNT_BACKUP_S3_*",
        )
        for node in constants
        if "CLOUDFLARE_R2_" in str(node.value)
    ]


# --------------------------------------------------------------------------- rules: profile-source, profile-pair


def profile_findings(consumers: dict) -> tuple[list[Finding], int]:
    """(findings, number of profiles binding a backup pair). CannotRunError on an empty consumer table."""
    if not consumers:
        raise CannotRunError("%s lists no consumer profile" % SUPPLY_REL)
    out: list[Finding] = []
    binding = 0
    for profile, body in consumers.items():
        where = "%s consumers.%s" % (SUPPLY_REL, profile)
        specs = bws_env.parse_specs([*(body.get("required") or []), *(body.get("optional") or [])])
        envs: dict[str, set[str]] = {}
        for store, local in specs:
            if local.startswith("ACCOUNT_BACKUP_S3_") and WIDE_STORE_RE.match(store):
                out.append(
                    Finding(
                        "profile-source",
                        where,
                        "%s > %s feeds a backup name from an account-wide Cloudflare credential; "
                        "bind the environment's bucket-scoped pair instead" % (store, local),
                    )
                )
            match = PAIR_RE.match(store)
            if not match:
                continue
            half, env = match.groups()
            if env is None:
                out.append(
                    Finding(
                        "profile-pair",
                        where,
                        "%s > %s binds the unsuffixed store entry, the shared pair the split "
                        "retires; bind %s_<STABLE|EDGE|BENCH> > %s" % (store, local, half, half),
                    )
                )
                continue
            if local in PAIR and local != half:
                out.append(
                    Finding(
                        "profile-pair",
                        where,
                        "%s > %s crosses the key id and the secret" % (store, local),
                    )
                )
            # Bound under any local name, a suffixed store entry puts that environment's key in the profile.
            envs.setdefault(env, set()).add(half)
        if envs:
            binding += 1
        if len(envs) > 1:
            out.append(
                Finding(
                    "profile-pair",
                    where,
                    "binds the backup pair of %s; one profile serves ONE environment"
                    % " and ".join(sorted(envs)),
                )
            )
        for env, halves in envs.items():
            if halves != set(PAIR):
                out.append(
                    Finding(
                        "profile-pair",
                        where,
                        "binds only %s of the %s pair; a profile binds both halves of one token"
                        % (", ".join(sorted(halves)), env),
                    )
                )
        want = PROFILE_CENSUS.get(profile)
        if want and set(envs) != {want}:
            out.append(
                Finding(
                    "profile-pair",
                    where,
                    "must bind the %s pair (ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_%s and "
                    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_%s) and no other; it binds %s"
                    % (want, want, want, ", ".join(sorted(envs)) or "none"),
                )
            )
    out.extend(
        Finding(
            "profile-pair",
            SUPPLY_REL,
            "profile %s is missing; the backup pair of %s has no binding the gate can check"
            % (profile, env),
        )
        for profile, env in PROFILE_CENSUS.items()
        if profile not in consumers
    )
    return out, binding


# --------------------------------------------------------------------------- rules: workflow-pair, workflow-source


def _norm_if(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2]
    return " ".join(text.replace('"', "'").split())


def _steps(doc: dict) -> list[tuple[str, dict]]:
    """(job id or `runs`, raw step) for every step of a workflow or a composite action."""
    out: list[tuple[str, dict]] = []
    for job_id, job in (doc.get("jobs") or {}).items():
        out.extend((str(job_id), s) for s in (job or {}).get("steps") or [] if isinstance(s, dict))
    runs = doc.get("runs")
    if isinstance(runs, dict):
        out.extend(("runs", s) for s in runs.get("steps") or [] if isinstance(s, dict))
    return out


def _env_maps(doc: dict) -> list[tuple[str, dict]]:
    maps: list[tuple[str, dict]] = [("env", doc.get("env") or {})]
    for job_id, job in (doc.get("jobs") or {}).items():
        maps.append(("%s.env" % job_id, (job or {}).get("env") or {}))
    for job_id, step in _steps(doc):
        maps.append(
            (
                "%s/%s.env" % (job_id, step.get("name") or step.get("uses") or "step"),
                step.get("env") or {},
            )
        )
    return [(label, m) for label, m in maps if isinstance(m, dict)]


def workflow_findings(rel: str, text: str) -> tuple[list[Finding], dict[str, int]]:
    """Findings for one workflow-shaped file, and the census: how many stable and edge pair fetches it holds."""
    out: list[Finding] = []
    census = {"STABLE": 0, "EDGE": 0}
    try:
        doc = workflows.parse(text) or {}
    except ValueError as exc:
        raise CannotRunError("%s does not parse (%s)" % (rel, exc)) from None
    if not isinstance(doc, dict):
        return out, census
    for job_id, step in _steps(doc):
        where = "%s %s/%s" % (rel, job_id, step.get("name") or step.get("uses") or "step")
        uses = str(step.get("uses") or "")
        if uses == BWS_ACTION:
            specs = bws_env.parse_specs(
                str((step.get("with") or {}).get("secrets") or "").splitlines()
            )
            condition = _norm_if(step.get("if"))
            fetched: set[str] = set()
            for store, local in specs:
                if WIDE_STORE_RE.match(store) and "ACCOUNT_BACKUP_S3_" in local:
                    out.append(
                        Finding(
                            "workflow-source",
                            where,
                            "%s > %s fetches an account-wide Cloudflare credential into a backup name"
                            % (store, local),
                        )
                    )
                match = PAIR_RE.match(store)
                if not match:
                    continue
                env = match.group(2)
                if env is None:
                    out.append(
                        Finding(
                            "workflow-pair",
                            where,
                            "requests the unsuffixed %s, the shared pair the split retires; fetch "
                            "%s_STABLE under `if: %s` or %s_EDGE under `if: %s`"
                            % (store, store, STABLE_IF, store, EDGE_IF),
                        )
                    )
                elif env == "BENCH":
                    out.append(
                        Finding(
                            "workflow-pair",
                            where,
                            "requests %s; the bench pair is for the operator's deploy-bench profile "
                            "only, and no workflow may hold it" % store,
                        )
                    )
                else:
                    want = STABLE_IF if env == "STABLE" else EDGE_IF
                    if condition != want:
                        out.append(
                            Finding(
                                "workflow-pair",
                                where,
                                "requests %s under `if: %s`; it must be fetched only under "
                                "`if: %s`, so the other channel's run never holds it"
                                % (store, condition or "(none)", want),
                            )
                        )
                    else:
                        fetched.add(env)
            for env in fetched:
                census[env] += 1
        run = str(step.get("run") or "")
        out.extend(
            Finding(
                "workflow-source",
                where,
                "a run: line assigns a backup name from an account-wide Cloudflare credential",
            )
            for match in RUN_ASSIGN_RE.finditer(run)
            if WIDE_REF_RE.search(match.group(1))
        )
    for label, mapping in _env_maps(doc):
        for key, value in mapping.items():
            name = str(key)
            if "ACCOUNT_BACKUP_S3_" in name and WIDE_REF_RE.search(str(value)):
                out.append(
                    Finding(
                        "workflow-source",
                        "%s %s" % (rel, label),
                        "%s is fed from an account-wide Cloudflare credential" % name,
                    )
                )
    return out, census


# --------------------------------------------------------------------------- rule: rotation-scopes


def expected_buckets(regions: list[dict], bench_toml: str) -> dict[str, set[tuple[str, str]]]:
    """{env: {(bucket, jurisdiction or "")}} from regions.json and wrangler.bench.toml."""
    bench = tomllib.loads(bench_toml)
    bench_set = {
        (b.get("bucket_name") or "", b.get("jurisdiction") or "")
        for b in bench.get("r2_buckets") or []
        if b.get("binding") == "BACKUP_BUCKET"
    }
    if not regions or not bench_set:
        raise CannotRunError(
            "regions.json lists no region or wrangler.bench.toml binds no BACKUP_BUCKET"
        )
    return {
        "STABLE": {(r["backupR2"]["name"], r.get("r2Jurisdiction") or "") for r in regions},
        "EDGE": {(r["edgeBackupR2"]["name"], r.get("r2Jurisdiction") or "") for r in regions},
        "BENCH": bench_set,
    }


def _walk(value, path: str):
    yield path, value
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(v, "%s.%s" % (path, k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _walk(v, "%s[%d]" % (path, i))


# The per-token key that lists its Bitwarden names. The file B1 writes spells it in camelCase (TypeScript reads it too); the snake_case spelling is accepted as the same field.
NAME_KEYS = ("bitwardenSecretNames", "bitwarden_secret_names")


def _permission_findings(doc: dict) -> list[Finding]:
    """Anywhere in the file (a shared top-level list or a per-token one): no account or zone permission, no permission beyond bucket item read and write, no account-level resource. Keys starting with `$` are comments."""
    out: list[Finding] = []
    for path, value in _walk(doc, "$"):
        leaf = path.rsplit(".", 1)[-1]
        if leaf.startswith("$"):
            continue
        where = "%s %s" % (SCOPES_REL, path.removeprefix("$."))
        if leaf in ("account", "zone") and value:
            out.append(
                Finding(
                    "rotation-scopes",
                    where,
                    "carries an %s-level permission; a backup token is bucket-scoped only" % leaf,
                )
            )
        if leaf == "permissions" and isinstance(value, list):
            extra = sorted(str(v) for v in value if v not in BUCKET_PERMS)
            if extra:
                out.append(
                    Finding(
                        "rotation-scopes",
                        where,
                        "permission(s) beyond bucket item read and write: %s" % ", ".join(extra),
                    )
                )
        if isinstance(value, str) and "com.cloudflare.api.account" in value:
            out.append(Finding("rotation-scopes", where, "names an account-level resource"))
    return out


def scope_findings(doc: object, expected: dict[str, set[tuple[str, str]]]) -> list[Finding]:
    """The rotation-scopes rule over the parsed file: `{"permissions": [...], "tokens": {<slug>: {environment, buckets, bitwardenSecretNames}}}`, or the token table at the top level."""
    where = SCOPES_REL
    if not isinstance(doc, dict):
        return [Finding("rotation-scopes", where, "is not a JSON object")]
    out = _permission_findings(doc)
    table = doc
    if not any(slug in table for slug in SLUGS.values()):
        # One wrapping key (`tokens`), never a guess deeper than that.
        nested = [
            v for v in doc.values() if isinstance(v, dict) and any(s in v for s in SLUGS.values())
        ]
        table = nested[0] if len(nested) == 1 else table
    owners: dict[str, list[str]] = {}
    for env, slug in SLUGS.items():
        entry = table.get(slug)
        here = "%s %s" % (where, slug)
        if not isinstance(entry, dict):
            out.append(Finding("rotation-scopes", where, "slug %s is missing" % slug))
            continue
        declared = entry.get("environment")
        if declared is not None and str(declared).upper() != env:
            out.append(
                Finding(
                    "rotation-scopes",
                    here,
                    "declares environment %r; slug %s is %s" % (declared, slug, env.lower()),
                )
            )
        raw_names = next((entry[k] for k in NAME_KEYS if k in entry), None)
        names = [str(n) for n in raw_names or []]
        if not names:
            out.append(Finding("rotation-scopes", here, "lists no Bitwarden secret name"))
        for name in names:
            if name == SHARED:
                continue
            owners.setdefault(name, []).append(slug)
            if not name.endswith("_" + env):
                out.append(
                    Finding(
                        "rotation-scopes",
                        here,
                        "BWS name %s does not carry this environment's suffix _%s" % (name, env),
                    )
                )
        got = {
            (str(b.get("name") or ""), str(b.get("jurisdiction") or ""))
            for b in entry.get("buckets") or []
            if isinstance(b, dict)
        }
        if got != expected[env]:
            out.append(
                Finding(
                    "rotation-scopes",
                    here,
                    "buckets %s, expected %s (regions.json / wrangler.bench.toml)"
                    % (_fmt(got), _fmt(expected[env])),
                )
            )
    out.extend(
        Finding(
            "rotation-scopes",
            where,
            "BWS name %s is shared by %s; each token's names are its own"
            % (name, ", ".join(slugs)),
        )
        for name, slugs in sorted(owners.items())
        if len(slugs) > 1
    )
    return out


def _fmt(pairs: set[tuple[str, str]]) -> str:
    return "{%s}" % ", ".join(
        "%s%s" % (name, ("(%s)" % j) if j else "") for name, j in sorted(pairs)
    )


# --------------------------------------------------------------------------- the run


def gather(root: pathlib.Path) -> Report:
    report = Report()
    bench_path = root / DEPLOY_BENCH_REL
    if not bench_path.is_file():
        raise CannotRunError("%s is missing" % DEPLOY_BENCH_REL)
    report.findings += bench_fallback(bench_path.read_text(encoding="utf-8"))

    supply = json.loads((root / SUPPLY_REL).read_text(encoding="utf-8"))
    consumers = supply.get("consumers") or {}
    found, binding = profile_findings(consumers)
    report.findings += found
    report.shape["profiles"] = len(consumers)
    report.shape["profiles binding a pair"] = binding

    files = workflows.call_sites(root)
    if not files:
        raise CannotRunError("no workflow file under %s/.github" % root)
    census = {"STABLE": 0, "EDGE": 0}
    for path in files:
        rel = path.relative_to(root).as_posix()
        found, seen = workflow_findings(rel, path.read_text(encoding="utf-8"))
        report.findings += found
        for env, n in seen.items():
            census[env] += n
    for env, cond in (("STABLE", STABLE_IF), ("EDGE", EDGE_IF)):
        if not census[env]:
            report.findings.append(
                Finding(
                    "workflow-pair",
                    ".github/workflows",
                    "no bws-secrets step fetches the %s pair under `if: %s`: either the account "
                    "deploy stopped fetching it or this gate is blind to it" % (env, cond),
                )
            )
    report.shape["workflow files"] = len(files)
    report.shape["stable fetches"] = census["STABLE"]
    report.shape["edge fetches"] = census["EDGE"]

    regions = json.loads((root / REGIONS_REL).read_text(encoding="utf-8"))["regions"]
    expected = expected_buckets(regions, (root / BENCH_TOML_REL).read_text(encoding="utf-8"))
    scopes = root / SCOPES_REL
    if not (root / SUBMODULE_REL / ".git").exists() and not any((root / SUBMODULE_REL).glob("*")):
        report.skips.append(
            "rotation-scopes: SKIP, %s is not checked out, so the token scopes were NOT compared"
            % SUBMODULE_REL
        )
    elif not scopes.is_file():
        report.skips.append(
            "rotation-scopes: SKIP, %s does not exist (PLAN-backup-credential-isolation B1 writes "
            "it), so the token scopes were NOT compared" % SCOPES_REL
        )
    else:
        try:
            doc = json.loads(scopes.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CannotRunError("%s is not JSON (%s)" % (SCOPES_REL, exc)) from None
        report.findings += scope_findings(doc, expected)
        report.shape["token scopes"] = len(SLUGS)
    return report


def render(report: Report) -> int:
    for skip in report.skips:
        log.warn(skip)
    for finding in report.findings:
        log.error(finding.line())
    shape = ", ".join("%d %s" % (n, k) for k, n in report.shape.items())
    skipped = (" (%d rule(s) SKIPPED, see above)" % len(report.skips)) if report.skips else ""
    if report.findings:
        log.error(
            "backup credential isolation: %d finding(s) across %s; %s%s. Fix the binding, do not "
            "widen the rule: a key that reaches another environment's buckets is the defect."
            % (
                len(report.findings),
                ", ".join(sorted({f.rule for f in report.findings})),
                shape,
                skipped,
            )
        )
        return 1
    log.success(
        "backup credential isolation: clean, %d rule(s); %s%s" % (len(RULES), shape, skipped)
    )
    return 0


def _arg(argv: list[str], flag: str) -> str | None:
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return 1 if selftest() else 0
    rc = controls_first("backup credential isolation", selftest)
    if rc:
        return rc
    root_arg = _arg(argv, "--root")
    root = pathlib.Path(root_arg).resolve() if root_arg else pathlib.Path(paths.repo_root())
    try:
        report = gather(root)
    except (CannotRunError, OSError, ValueError, KeyError) as exc:
        log.error("backup credential isolation: CANNOT RUN: %s" % exc)
        return 2
    return render(report)


# --------------------------------------------------------------------------- controls

FIX_DEPLOY = """
import os
NAMES = ("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY")
def values():
    return os.environ.get("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID") or ""
"""

FIX_SUPPLY = """{
  "deploy-bench": {"required": ["ROOT_EMAIL", "ACCOUNT_BACKUP_S3_ENDPOINT",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_BENCH > ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"], "optional": []},
  "reset-bench": {"required": ["CLOUDFLARE_R2_ACCESS_KEY_ID", "CLOUDFLARE_R2_SECRET_ACCESS_KEY"], "optional": []},
  "backup-push-stable": {"required": ["CLOUDFLARE_API_TOKEN", "ACCOUNT_BACKUP_S3_ENDPOINT",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_STABLE > ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"], "optional": []},
  "backup-push-edge": {"required": ["CLOUDFLARE_API_TOKEN", "ACCOUNT_BACKUP_S3_ENDPOINT",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_EDGE > ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"], "optional": []},
  "backup-push-bench": {"required": ["CLOUDFLARE_API_TOKEN", "ACCOUNT_BACKUP_S3_ENDPOINT",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_BENCH > ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"], "optional": []}
}"""

FIX_WORKFLOW = """name: fixture
on:
  workflow_call:
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Fetch
        uses: ./.github/actions/bws-secrets
        with:
          secrets: |
            ACCOUNT_BACKUP_S3_ENDPOINT > BWS_ACCOUNT_BACKUP_S3_ENDPOINT
            CLOUDFLARE_API_TOKEN > BWS_CLOUDFLARE_API_TOKEN
      - name: Fetch stable
        if: inputs.target == 'stable'
        uses: ./.github/actions/bws-secrets
        with:
          secrets: |
            ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE > BWS_ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE
            ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_STABLE > BWS_ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_STABLE
      - name: Fetch edge
        if: ${{ inputs.target != 'stable' }}
        uses: ./.github/actions/bws-secrets
        with:
          secrets: |
            ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE > BWS_ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE
            ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_EDGE > BWS_ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_EDGE
      - name: Set secrets
        env:
          CLOUDFLARE_API_TOKEN: ${{ env.BWS_CLOUDFLARE_API_TOKEN }}
          ACCOUNT_BACKUP_S3_ENDPOINT: ${{ env.BWS_ACCOUNT_BACKUP_S3_ENDPOINT }}
          ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE: ${{ env.BWS_ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE }}
        run: python3 -m push
"""

FIX_REGIONS: list[dict] = [
    {
        "id": "eu",
        "backupR2": {"name": "b-eu"},
        "edgeBackupR2": {"name": "edge-b-eu"},
        "r2Jurisdiction": "eu",
    },
    {
        "id": "us",
        "backupR2": {"name": "b-us"},
        "edgeBackupR2": {"name": "edge-b-us"},
        "r2Jurisdiction": None,
    },
]
FIX_BENCH_TOML = '[[r2_buckets]]\nbinding = "CONFIG_BUCKET"\nbucket_name = "c-bench"\n[[r2_buckets]]\nbinding = "BACKUP_BUCKET"\nbucket_name = "b-bench"\n'
PERMS = '["Workers R2 Storage Bucket Item Read", "Workers R2 Storage Bucket Item Write"]'
FIX_SCOPES = """{
  "$comment": "fixture: the account-level resource com.cloudflare.api.account named in a comment is not a finding",
  "permissions": %(p)s,
  "tokens": {
    "cf-r2-backup-stable": {"environment": "stable",
      "buckets": [{"name": "b-eu", "jurisdiction": "eu"}, {"name": "b-us"}],
      "bitwardenSecretNames": ["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE", "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_STABLE", "ACCOUNT_BACKUP_S3_ENDPOINT"]},
    "cf-r2-backup-edge": {"environment": "edge",
      "buckets": [{"name": "edge-b-eu", "jurisdiction": "eu"}, {"name": "edge-b-us"}],
      "bitwardenSecretNames": ["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE", "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_EDGE", "ACCOUNT_BACKUP_S3_ENDPOINT"]},
    "cf-r2-backup-bench": {"environment": "bench", "account": [],
      "buckets": [{"name": "b-bench"}],
      "bitwardenSecretNames": ["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH", "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_BENCH"]}
  }
}""" % {"p": PERMS}


def _rules(findings: list[Finding]) -> set[str]:
    return {f.rule for f in findings}


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    check = Checker()
    expected = expected_buckets(FIX_REGIONS, FIX_BENCH_TOML)

    # ---- the clean world is clean, rule by rule
    check(
        "CONTROL: a deploy that reads only ACCOUNT_BACKUP_S3_* is clean",
        bench_fallback(FIX_DEPLOY, "f") == [],
    )
    clean_profiles, binding = profile_findings(json.loads(FIX_SUPPLY))
    check("CONTROL: one environment's pair per profile is clean", clean_profiles == [])
    check("CONTROL: and the census sees the four profiles binding a pair", binding == 4)
    clean_wf, census = workflow_findings("f.yml", FIX_WORKFLOW)
    check("CONTROL: channel-conditioned fetches are clean", clean_wf == [])
    check("CONTROL: and both channel fetches are counted", census == {"STABLE": 1, "EDGE": 1})
    check(
        "CONTROL: disjoint, bucket-scoped token scopes are clean",
        scope_findings(json.loads(FIX_SCOPES), expected) == [],
    )

    # ---- bench-no-fallback
    planted = plant(FIX_DEPLOY, 'or ""', 'or os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID") or ""')
    check(
        "PLANT bench-no-fallback: a CLOUDFLARE_R2_ read in deploy_bench is a finding",
        _rules(bench_fallback(planted, "f")) == {"bench-no-fallback"},
    )
    planted = plant(
        FIX_DEPLOY, "import os\n", 'import os\n"""falls back to CLOUDFLARE_R2_ENDPOINT"""\n'
    )
    check(
        "PLANT bench-no-fallback: a docstring naming it counts too (AST constants)",
        len(bench_fallback(planted, "f")) == 1,
    )
    planted = plant(FIX_DEPLOY, "import os\n", "import os\n# CLOUDFLARE_R2_ENDPOINT in a comment\n")
    check(
        "CONTROL bench-no-fallback: a comment is not a constant", bench_fallback(planted, "f") == []
    )
    blind = plant(FIX_DEPLOY, "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", "SOMETHING_ELSE")
    try:
        bench_fallback(blind, "f")
        refused = False
    except CannotRunError:
        refused = True
    check(
        "PLANT bench-no-fallback: a module naming no backup value CANNOT RUN, it does not pass",
        refused,
    )

    # ---- profile-source
    planted = plant(
        FIX_SUPPLY,
        '"ACCOUNT_BACKUP_S3_ENDPOINT",\n    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH',
        '"CLOUDFLARE_R2_ENDPOINT > ACCOUNT_BACKUP_S3_ENDPOINT",\n    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH',
    )
    check(
        "PLANT profile-source: the R2 trio bound into a backup name is a finding",
        "profile-source" in _rules(profile_findings(json.loads(planted))[0]),
    )
    planted = plant(
        FIX_SUPPLY,
        '"ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"',
        '"CLOUDFLARE_API_TOKEN > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"',
    )
    check(
        "PLANT profile-source: the API token bound into the key id is a finding",
        "profile-source" in _rules(profile_findings(json.loads(planted))[0]),
    )

    # ---- profile-pair
    planted = plant(
        FIX_SUPPLY,
        '"ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_BENCH > ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"], "optional": []},\n  "reset-bench"',
        '"ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_EDGE > ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"], "optional": []},\n  "reset-bench"',
    )
    found = profile_findings(json.loads(planted))[0]
    check(
        "PLANT profile-pair: a profile mixing two environments' halves is a finding",
        any(f.rule == "profile-pair" and "one profile serves ONE" in f.what for f in found),
    )
    planted = plant(
        FIX_SUPPLY,
        '"ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"',
        '"ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"',
    )
    check(
        "PLANT profile-pair: the unsuffixed shared pair bound by a profile is a finding",
        any("unsuffixed" in f.what for f in profile_findings(json.loads(planted))[0]),
    )
    planted = plant(FIX_SUPPLY, '"backup-push-bench"', '"backup-push-other"')
    check(
        "PLANT profile-pair: a census profile gone missing is a finding",
        any(
            "backup-push-bench is missing" in f.what
            for f in profile_findings(json.loads(planted))[0]
        ),
    )
    planted = plant(
        FIX_SUPPLY,
        '"ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",\n    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_STABLE',
        '"ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",\n    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_EDGE',
    )
    check(
        "PLANT profile-pair: backup-push-stable binding the edge pair is a finding",
        any(
            "backup-push-stable" in f.where and "must bind the STABLE" in f.what
            for f in profile_findings(json.loads(planted))[0]
        ),
    )

    # ---- workflow-pair
    planted = plant(FIX_WORKFLOW, "if: inputs.target == 'stable'", "if: inputs.target != 'stable'")
    found, census = workflow_findings("f.yml", planted)
    check(
        "PLANT workflow-pair: the stable pair under the edge condition is a finding",
        "workflow-pair" in _rules(found),
    )
    planted = plant(FIX_WORKFLOW, "        if: inputs.target == 'stable'\n", "")
    check(
        "PLANT workflow-pair: the stable pair with no condition is a finding",
        "workflow-pair" in _rules(workflow_findings("f.yml", planted)[0]),
    )
    planted = plant(
        FIX_WORKFLOW,
        "ACCOUNT_BACKUP_S3_ENDPOINT > BWS_ACCOUNT_BACKUP_S3_ENDPOINT\n",
        "ACCOUNT_BACKUP_S3_ENDPOINT > BWS_ACCOUNT_BACKUP_S3_ENDPOINT\n            ACCOUNT_BACKUP_S3_ACCESS_KEY_ID > BWS_ACCOUNT_BACKUP_S3_ACCESS_KEY_ID\n",
    )
    check(
        "PLANT workflow-pair: a request for the unsuffixed pair is a finding",
        any("unsuffixed" in f.what for f in workflow_findings("f.yml", planted)[0]),
    )
    planted = plant(
        FIX_WORKFLOW,
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE > BWS_ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE",
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH > BWS_ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH",
    )
    check(
        "PLANT workflow-pair: a request for the bench pair is a finding",
        any("_BENCH" in f.what for f in workflow_findings("f.yml", planted)[0]),
    )
    planted = plant(
        FIX_WORKFLOW,
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE > BWS_ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE\n            ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_EDGE > BWS_ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_EDGE",
        "ROOT_EMAIL",
    )
    check(
        "PLANT workflow-pair: with the edge fetch gone, the census counts no edge fetch",
        workflow_findings("f.yml", planted)[1]["EDGE"] == 0,
    )

    # ---- workflow-source
    planted = plant(
        FIX_WORKFLOW,
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE: ${{ env.BWS_ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE }}",
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE: ${{ env.BWS_CLOUDFLARE_R2_ACCESS_KEY_ID }}",
    )
    check(
        "PLANT workflow-source: a backup env value fed from the R2 trio is a finding",
        "workflow-source" in _rules(workflow_findings("f.yml", planted)[0]),
    )
    planted = plant(
        FIX_WORKFLOW,
        "ACCOUNT_BACKUP_S3_ENDPOINT: ${{ env.BWS_ACCOUNT_BACKUP_S3_ENDPOINT }}",
        "ACCOUNT_BACKUP_S3_ENDPOINT: ${{ secrets.CLOUDFLARE_API_TOKEN }}",
    )
    check(
        "PLANT workflow-source: a backup env value fed from the API token is a finding",
        "workflow-source" in _rules(workflow_findings("f.yml", planted)[0]),
    )
    planted = plant(
        FIX_WORKFLOW,
        "CLOUDFLARE_API_TOKEN > BWS_CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY > BWS_ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY",
    )
    check(
        "PLANT workflow-source: a fetch renaming the R2 trio into a backup name is a finding",
        "workflow-source" in _rules(workflow_findings("f.yml", planted)[0]),
    )
    planted = plant(
        FIX_WORKFLOW,
        "run: python3 -m push",
        'run: ACCOUNT_BACKUP_S3_ACCESS_KEY_ID="$CLOUDFLARE_R2_ACCESS_KEY_ID" python3 -m push',
    )
    check(
        "PLANT workflow-source: a run: assignment from the R2 trio is a finding",
        "workflow-source" in _rules(workflow_findings("f.yml", planted)[0]),
    )

    # ---- rotation-scopes
    planted = plant(
        FIX_SCOPES,
        '"ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH", "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_BENCH"',
        '"ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH", "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_EDGE"',
    )
    found = scope_findings(json.loads(planted), expected)
    check(
        "PLANT rotation-scopes: a BWS name shared by two slugs is a finding",
        any("is shared by" in f.what for f in found),
    )
    planted = plant(
        FIX_SCOPES,
        '[{"name": "b-eu", "jurisdiction": "eu"}, {"name": "b-us"}]',
        '[{"name": "b-eu", "jurisdiction": "eu"}]',
    )
    check(
        "PLANT rotation-scopes: a stable token missing a regional bucket is a finding",
        "rotation-scopes" in _rules(scope_findings(json.loads(planted), expected)),
    )
    planted = plant(
        FIX_SCOPES, '[{"name": "edge-b-eu", "jurisdiction": "eu"}', '[{"name": "edge-b-eu"}'
    )
    check(
        "PLANT rotation-scopes: an EU bucket without its jurisdiction is a finding",
        "rotation-scopes" in _rules(scope_findings(json.loads(planted), expected)),
    )
    planted = plant(FIX_SCOPES, '"account": []', '"account": ["Workers R2 Storage Write"]')
    check(
        "PLANT rotation-scopes: an account-level permission is a finding",
        any("account-level" in f.what for f in scope_findings(json.loads(planted), expected)),
    )
    planted = plant(
        FIX_SCOPES,
        '"buckets": [{"name": "b-bench"}]',
        '"buckets": [{"name": "b-bench"}, {"name": "b-eu", "jurisdiction": "eu"}]',
    )
    check(
        "PLANT rotation-scopes: the bench token reaching a stable bucket is a finding",
        "rotation-scopes" in _rules(scope_findings(json.loads(planted), expected)),
    )
    planted = plant(FIX_SCOPES, '"cf-r2-backup-edge"', '"cf-r2-backup-edgy"')
    check(
        "PLANT rotation-scopes: a missing slug is a finding",
        any(
            "cf-r2-backup-edge is missing" in f.what
            for f in scope_findings(json.loads(planted), expected)
        ),
    )
    check(
        "CONTROL rotation-scopes: the clean fixture shares ACCOUNT_BACKUP_S3_ENDPOINT between two slugs, and that is allowed",
        FIX_SCOPES.count('"ACCOUNT_BACKUP_S3_ENDPOINT"') == 2,
    )
    planted = plant(
        FIX_SCOPES,
        '"Workers R2 Storage Bucket Item Write"]',
        '"Workers R2 Storage Bucket Item Write", "Workers R2 Storage Write"]',
    )
    check(
        "PLANT rotation-scopes: an account-wide permission in the shared top-level list is a finding",
        any("beyond bucket item" in f.what for f in scope_findings(json.loads(planted), expected)),
    )
    planted = plant(
        FIX_SCOPES,
        '"cf-r2-backup-bench": {"environment": "bench"',
        '"cf-r2-backup-bench": {"environment": "stable"',
    )
    check(
        "PLANT rotation-scopes: a token declaring another environment is a finding",
        any(
            "declares environment" in f.what for f in scope_findings(json.loads(planted), expected)
        ),
    )
    planted = plant(
        FIX_SCOPES,
        '"bitwardenSecretNames": ["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH"',
        '"names": ["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH"',
    )
    check(
        "PLANT rotation-scopes: a token listing no Bitwarden name under the known key is a finding",
        any("lists no Bitwarden" in f.what for f in scope_findings(json.loads(planted), expected)),
    )
    print("  %d control(s) ran" % check.count)
    return not check.ok


__all__ = [
    "Finding",
    "bench_fallback",
    "expected_buckets",
    "gather",
    "main",
    "profile_findings",
    "scope_findings",
    "selftest",
    "workflow_findings",
]
