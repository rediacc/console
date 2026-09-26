"""Preflights for scripts/ops/deploy-bench.sh, run BEFORE its first remote write.

WHY THIS EXISTS. On 2026-09-24 a bench deploy applied 21 D1 migrations and THEN failed: wrangler.bench.toml binds R2 bucket rediacc-backups-bench, which nothing had created, so bench was left serving its old worker on a newer schema. The retry bundled from a drifted node_modules (packages/shared and workers/account resolving zod 3.25.76 against a lockfile pinning 4.x) and Cloudflare refused the worker at startup ("uuid is not a function"). Both are knowable before anything remote changes.

Python rather than a sourced bash library: Ruling 7 (2026-09-06) bans new bash under scripts/ops.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_preflight lockfile <dir>...
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_preflight buckets <wrangler-config>
"""

import re
import subprocess
import sys

BUCKET_NAME = re.compile(r'^\s*bucket_name\s*=\s*"([^"]+)"', re.MULTILINE)
JURISDICTION = re.compile(r"^\s*jurisdiction\s*=", re.MULTILINE)
LISTED_NAME = re.compile(r"^name:\s+(\S+)", re.MULTILINE)


def lockfile(dirs):
    """Refuse when `npm ls --all` reports any install out of line with its package-lock.json."""
    for directory in dirs:
        rc = subprocess.run(
            ["npm", "ls", "--all"], cwd=directory, capture_output=True, check=False
        ).returncode
        if rc != 0:
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
        ["npx", "wrangler", "r2", "bucket", "list"], capture_output=True, text=True, check=False
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
            ["npx", "wrangler", "r2", "bucket", "create", bucket],
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
