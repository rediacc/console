"""Preflights for rediacc_ci.ops.deploy_bench, run BEFORE its first remote write.

WHY THIS EXISTS. On 2026-09-24 a bench deploy applied 21 D1 migrations and THEN failed: wrangler.bench.toml binds R2 bucket rediacc-backups-bench, which nothing had created, so bench was left serving its old worker on a newer schema. The retry bundled from a drifted node_modules (packages/shared and workers/account resolving zod 3.25.76 against a lockfile pinning 4.x) and Cloudflare refused the worker at startup ("uuid is not a function"). Both are knowable before anything remote changes.

Python rather than a sourced bash library: Ruling 7 (2026-09-06) bans new bash under scripts/ops.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_preflight lockfile <dir>...
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_preflight buckets <wrangler-config>
"""

import dataclasses
import json
import re
import subprocess
import sys
import tomllib

from rediacc_ci import paths
from rediacc_ci.core import wrangler

BENCH_CONFIG_REL = ("workers", "account", "wrangler.bench.toml")
LISTED_NAME = re.compile(r"^name:\s+(\S+)", re.MULTILINE)


@dataclasses.dataclass(frozen=True)
class BenchNames:
    """The names and jurisdictions wrangler.bench.toml declares: the one place every bench tool reads them from, so a repoint (PLAN-d1-eu-jurisdiction) is a toml change."""

    database_name: str
    database_id: str
    config_bucket: str
    config_jurisdiction: str
    backup_bucket: str
    backup_jurisdiction: str


def bench_names(config=None) -> BenchNames:
    """BenchNames from CONFIG (default workers/account/wrangler.bench.toml). A missing DB binding is a ValueError, never a silent default; a missing bucket binding reads as "" and each caller that needs the bucket refuses it by name."""
    path = paths.repo_root().joinpath(*BENCH_CONFIG_REL) if config is None else config
    with open(path, "rb") as fh:
        doc = tomllib.load(fh)
    dbs = {b.get("binding"): b for b in doc.get("d1_databases") or []}
    buckets = {b.get("binding"): b for b in doc.get("r2_buckets") or []}
    db = dbs.get("DB") or {}
    config_b, backup_b = buckets.get("CONFIG_BUCKET") or {}, buckets.get("BACKUP_BUCKET") or {}
    names = BenchNames(
        db.get("database_name") or "",
        db.get("database_id") or "",
        config_b.get("bucket_name") or "",
        config_b.get("jurisdiction") or "",
        backup_b.get("bucket_name") or "",
        backup_b.get("jurisdiction") or "",
    )
    if not names.database_name:
        raise ValueError("%s binds no DB database with a database_name" % path)
    return names


MARKS = ("missing", "invalid", "extraneous")
ARCHIVES = (".tgz", ".tar.gz", ".tar")


def _is_link(node):
    """Whether NODE is a `file:` dependency on a directory, which npm links; a `file:` tarball is installed like any other."""
    resolved = str(node.get("resolved", ""))
    return resolved.startswith("file:") and not resolved.endswith(ARCHIVES)


def _marks(node, linked=False, name=None):
    """(own, inside): the missing, invalid and extraneous marks `npm ls --json` puts on NODE and below. OWN counts those that belong to this install; INSIDE lists the dependency names marked strictly inside a linked directory.

    A linked package (private/account links packages/shared) is installed by the tree it lives in, the console root, which is checked as a directory of its own. Seen from the linking package its dependencies are all `missing`, whatever the state of either install. A mark on the link itself is this install's.
    """
    here = sum(1 for flag in MARKS if node.get(flag))
    own, inside = (0, [name] * here) if linked else (here, [])
    below = linked or _is_link(node)
    for child_name, child in (node.get("dependencies") or {}).items():
        child_own, child_inside = _marks(child, below, child_name)
        own += child_own
        inside += child_inside
    return own, inside


PROBLEM_NAME = re.compile(r"^\w+:\s+((?:@[^/\s@,]+/)?[^@\s,]+)")


def _explained(problems, inside):
    """Whether every problem line names a dependency that carries a mark inside a linked directory, one mark per problem.

    Counting alone would excuse `missing: zod` (a real defect of this install) whenever some other dependency sat marked inside a linked directory, so each problem is matched to a mark by the package name it opens with.
    """
    unspent = list(inside)
    for problem in problems:
        found = PROBLEM_NAME.match(str(problem))
        if not found or found.group(1) not in unspent:
            return False
        unspent.remove(found.group(1))
    return True


def _drifted(directory):
    """Whether DIRECTORY's install is out of line with its lockfile.

    The first run is the bash's own `npm ls --all`, and a zero exit settles it. Only a failing run is asked again as JSON, to tell a linked package's marks from this install's. It is drift unless the report is readable and every problem it lists is a mark inside a linked directory.
    """
    plain = subprocess.run(["npm", "ls", "--all"], cwd=directory, capture_output=True, check=False)
    if plain.returncode == 0:
        return False
    done = subprocess.run(
        ["npm", "ls", "--all", "--json"], cwd=directory, capture_output=True, text=True, check=False
    )
    try:
        tree = json.loads(done.stdout)
    except ValueError:
        return True
    if not isinstance(tree, dict):
        return True
    own, inside = _marks(tree)
    problems = tree.get("problems") or []
    return own > 0 or not inside or not _explained(problems, inside)


def lockfile(dirs):
    """Refuse when `npm ls --all` reports any install out of line with its package-lock.json."""
    for directory in dirs:
        if _drifted(directory):
            print(
                "✗ node_modules in %s does not match its package-lock.json (npm ls --all fails)"
                % directory,
                file=sys.stderr,
            )
            print(
                "✗ a bundle built from it can pass locally and be refused by Cloudflare; "
                "fix: npm ci && npm run install:natives",
                file=sys.stderr,
            )
            return 1
    return 0


def _list_buckets(cwd, jurisdiction):
    """The bucket names `wrangler r2 bucket list` shows in JURISDICTION ("" = default), or None when the listing failed (reported on stderr)."""
    argv = [*wrangler.ARGV, "r2", "bucket", "list"]
    if jurisdiction:
        argv += ["--jurisdiction", jurisdiction]
    listing = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if listing.returncode != 0:
        print(
            "✗ could not list R2 buckets (jurisdiction %s): %s"
            % (jurisdiction or "default", listing.stderr.strip()[:300]),
            file=sys.stderr,
        )
        return None
    return set(LISTED_NAME.findall(listing.stdout))


def buckets(config):
    """Create every R2 bucket the config binds that does not exist yet, in the jurisdiction the binding names.

    Both wrangler calls start in `workers/account`: `npx --no-install` finds only a `node_modules/.bin/wrangler` at or above its cwd, never PATH (finding e69747ea), and `--config` is not passed, so the caller's directory does not matter.

    A bucket exists per jurisdiction: a same-name bucket in the default jurisdiction does not satisfy a binding with `jurisdiction = "eu"`, so each jurisdiction is listed on its own and the create carries the binding's `--jurisdiction`.
    """
    with open(config, "rb") as fh:
        doc = tomllib.load(fh)
    wanted = [
        (b["bucket_name"], b.get("jurisdiction") or "")
        for b in doc.get("r2_buckets") or []
        if b.get("bucket_name")
    ]
    cwd = paths.repo_root() / "workers" / "account"
    existing = {}
    for jurisdiction in sorted({j for _, j in wanted}):
        names = _list_buckets(cwd, jurisdiction)
        if names is None:
            return 1
        existing[jurisdiction] = names
    for bucket, jurisdiction in wanted:
        if bucket in existing[jurisdiction]:
            continue
        print(
            "→ creating R2 bucket %s%s (bound in %s, absent)"
            % (bucket, " in jurisdiction " + jurisdiction if jurisdiction else "", config)
        )
        argv = [*wrangler.ARGV, "r2", "bucket", "create", bucket]
        if jurisdiction:
            argv += ["--jurisdiction", jurisdiction]
        made = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
        if made.returncode != 0:
            print("✗ creating %s failed: %s" % (bucket, made.stderr.strip()[:300]), file=sys.stderr)
            return 1
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "lockfile":
        return lockfile(argv[1:])
    if len(argv) == 2 and argv[0] == "buckets":
        return buckets(argv[1])
    print("\n".join(__doc__.strip().splitlines()[-2:]), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
