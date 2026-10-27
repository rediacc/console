"""Preflights for rediacc_ci.ops.deploy_bench, run BEFORE its first remote write.

WHY THIS EXISTS. On 2026-09-24 a bench deploy applied 21 D1 migrations and THEN failed: wrangler.bench.toml binds R2 bucket rediacc-backups-bench, which nothing had created, so bench was left serving its old worker on a newer schema. The retry bundled from a drifted node_modules (packages/shared and workers/account resolving zod 3.25.76 against a lockfile pinning 4.x) and Cloudflare refused the worker at startup ("uuid is not a function"). Both are knowable before anything remote changes.

Python rather than a sourced bash library: Ruling 7 (2026-09-06) bans new bash under scripts/ops.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_preflight lockfile <dir>...
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_preflight buckets <wrangler-config>
"""

import json
import re
import subprocess
import sys

from rediacc_ci.core import wrangler

BUCKET_NAME = re.compile(r'^\s*bucket_name\s*=\s*"([^"]+)"', re.MULTILINE)
JURISDICTION = re.compile(r"^\s*jurisdiction\s*=", re.MULTILINE)
LISTED_NAME = re.compile(r"^name:\s+(\S+)", re.MULTILINE)


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


def buckets(config):
    """Create every R2 bucket the config binds that does not exist yet.

    A binding that names a jurisdiction is refused rather than guessed: creating it in the default jurisdiction would put the data somewhere the config did not ask for.
    """
    with open(config, encoding="utf-8") as fh:
        text = fh.read()
    if JURISDICTION.search(text):
        print(
            "✗ %s binds a jurisdictional R2 bucket; create it by hand with --jurisdiction, "
            "then rerun" % config,
            file=sys.stderr,
        )
        return 1
    listing = subprocess.run(
        [*wrangler.ARGV, "r2", "bucket", "list"], capture_output=True, text=True, check=False
    )
    if listing.returncode != 0:
        print("✗ could not list R2 buckets: %s" % listing.stderr.strip()[:300], file=sys.stderr)
        return 1
    existing = set(LISTED_NAME.findall(listing.stdout))
    for bucket in BUCKET_NAME.findall(text):
        if bucket in existing:
            continue
        print("→ creating R2 bucket %s (bound in %s, absent)" % (bucket, config))
        made = subprocess.run(
            [*wrangler.ARGV, "r2", "bucket", "create", bucket],
            capture_output=True,
            text=True,
            check=False,
        )
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
