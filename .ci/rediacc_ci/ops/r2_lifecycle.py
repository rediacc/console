"""R2 lifecycle backstops for the release bucket, as code (PLAN-cloudflare-spend-guard T3).

The application decides first: `housekeeping/cleanup_versions.py` Phase 8 deletes `<fmt>/dryrun-*` past 7 days and `<fmt>/pr-N` past 3 days. These rules sit beyond it and catch only what it missed: `<fmt>/pr-` at 14 days, `<fmt>/dryrun-` at 21 days for the six `R2_FORMAT_DIRS`, plus one all-prefix rule aborting incomplete multipart uploads after 1 day (the platform default is 7).

Modes: `apply` (default; idempotent, a rule whose name and values already match is skipped, a drifted one is removed and re-added), `list` (print the rules), `check` / `--check` (exit 1 on a missing or drifted rule, or on a planted rule on a protected bucket).

Safety: only buckets in `ALLOWED_BUCKETS` are ever written. A name matching `PROTECTED_PATTERNS` (backups, configs) is refused before any call, because the account Worker's chunk GC is authoritative there and a lifecycle expiry would delete a chunk the index still references. `list` and `check` read the rules of every protected bucket (read-only) and report anything beyond the platform default as PLANTED.

Auth is `cf_auth.resolve` (a ready `CF_MANAGEMENT_TOKEN`, or the Global API Key pair, from which a token carrying Workers R2 Storage Write is minted and self-destructed). The token reaches wrangler only through its environment, never argv.
"""

from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import re
import subprocess
import sys
import typing

from rediacc_ci import log, paths
from rediacc_ci.ops import cf_auth

RELEASES_BUCKET = "rediacc-releases"
STAGING_BUCKET = "rediacc-staging"
# Written only when the live listing shows them.
ALLOWED_BUCKETS = (RELEASES_BUCKET, STAGING_BUCKET)
PROTECTED_PATTERNS = ("rediacc-backups*", "*-backups-*", "rediacc-configs*", "*-configs-*")
# Mirrors `R2_FORMAT_DIRS` in housekeeping/cleanup_versions.py.
FORMAT_DIRS = ("cli", "npm", "apt", "rpm", "apk", "archlinux")
PR_EXPIRE_DAYS = 14
DRYRUN_EXPIRE_DAYS = 21
MULTIPART_ABORT_DAYS = 1
MULTIPART_RULE = "spend-guard-multipart"
PLATFORM_DEFAULT_RULE = "Default Multipart Abort Rule"


class RefusedBucket(Exception):
    """A bucket outside the allowlist, or a protected one."""


@dataclasses.dataclass(frozen=True)
class Rule:
    name: str
    prefix: str = ""
    expire_days: int | None = None
    abort_days: int | None = None


def desired_rules() -> list[Rule]:
    rules = [Rule("spend-guard-pr-%s" % f, "%s/pr-" % f, expire_days=PR_EXPIRE_DAYS) for f in FORMAT_DIRS]
    rules += [
        Rule("spend-guard-dryrun-%s" % f, "%s/dryrun-" % f, expire_days=DRYRUN_EXPIRE_DAYS)
        for f in FORMAT_DIRS
    ]
    rules.append(Rule(MULTIPART_RULE, "", abort_days=MULTIPART_ABORT_DAYS))
    return rules


def is_protected(bucket: str) -> bool:
    return any(fnmatch.fnmatchcase(bucket, p) for p in PROTECTED_PATTERNS)


def require_writable(bucket: str) -> None:
    """Raise `RefusedBucket` unless `bucket` may be written; called before every mutation."""
    if is_protected(bucket):
        raise RefusedBucket(
            "refusing %s: backup and config buckets never get lifecycle rules (the chunk GC is authoritative there)"
            % bucket
        )
    if bucket not in ALLOWED_BUCKETS:
        raise RefusedBucket("refusing %s: not in the allowlist %s" % (bucket, ", ".join(ALLOWED_BUCKETS)))


class Wrangler:
    """`wrangler r2 ...` through a subprocess whose environment carries the token."""

    def __init__(self, env: dict[str, str]):
        self.env = env
        local = paths.repo_root() / "workers" / "www"
        binary = local / "node_modules" / ".bin" / "wrangler"
        self.argv = [str(binary)] if binary.exists() else ["npx", "wrangler"]
        self.cwd = str(local)

    def __call__(self, *args: str) -> tuple[int, str]:
        proc = subprocess.run(
            [*self.argv, "r2", *args],
            env=self.env,
            cwd=self.cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout + (("\n" + proc.stderr) if proc.returncode else "")


Runner = typing.Callable[..., tuple[int, str]]


def parse_buckets(text: str) -> list[str]:
    return re.findall(r"^name:\s+(\S+)\s*$", text, flags=re.MULTILINE)


def parse_rules(text: str) -> list[Rule]:
    """Parse `wrangler r2 bucket lifecycle list` blocks (name / enabled / prefix / action lines)."""
    rules: list[Rule] = []
    for block in re.split(r"\n\s*\n", text):
        name = re.search(r"^name:\s+(.+?)\s*$", block, flags=re.MULTILINE)
        if not name:
            continue
        prefix_m = re.search(r"^prefix:\s+(.*?)\s*$", block, flags=re.MULTILINE)
        prefix = prefix_m.group(1) if prefix_m else ""
        if prefix.startswith("("):
            prefix = ""
        expire = abort = None
        action = block.split("action:", 1)[1] if "action:" in block else ""
        for line in action.splitlines():
            days = re.search(r"after (\d+) days?", line)
            if not days:
                continue
            if "abort" in line.lower():
                abort = int(days.group(1))
            elif re.search(r"delet|expir", line, flags=re.IGNORECASE):
                expire = int(days.group(1))
        rules.append(Rule(name.group(1), prefix, expire, abort))
    return rules


def list_rules(run: Runner, bucket: str) -> list[Rule]:
    rc, out = run("bucket", "lifecycle", "list", bucket)
    if rc != 0:
        raise RuntimeError("lifecycle list %s failed (exit %d): %s" % (bucket, rc, out.strip()[-300:]))
    return parse_rules(out)


def _add(run: Runner, bucket: str, rule: Rule) -> None:
    require_writable(bucket)
    args = ["bucket", "lifecycle", "add", bucket, rule.name, rule.prefix]
    if rule.expire_days is not None:
        args += ["--expire-days", str(rule.expire_days)]
    if rule.abort_days is not None:
        args += ["--abort-multipart-days", str(rule.abort_days)]
    rc, out = run(*args, "-y")
    if rc != 0:
        raise RuntimeError("lifecycle add %s on %s failed (exit %d): %s" % (rule.name, bucket, rc, out.strip()[-300:]))


def _remove(run: Runner, bucket: str, name: str) -> None:
    require_writable(bucket)
    rc, out = run("bucket", "lifecycle", "remove", bucket, "--name", name)
    if rc != 0:
        raise RuntimeError("lifecycle remove %s on %s failed (exit %d): %s" % (name, bucket, rc, out.strip()[-300:]))


def diff(existing: list[Rule], wanted: list[Rule]) -> tuple[list[Rule], list[Rule]]:
    """(missing, drifted) among `wanted` given `existing`, matched by name."""
    by_name = {r.name: r for r in existing}
    missing = [r for r in wanted if r.name not in by_name]
    drifted = [r for r in wanted if r.name in by_name and by_name[r.name] != r]
    return missing, drifted


def target_buckets(run: Runner) -> tuple[list[str], list[str]]:
    """(writable targets present in the live listing, protected buckets present)."""
    rc, out = run("bucket", "list")
    if rc != 0:
        raise RuntimeError("bucket list failed (exit %d): %s" % (rc, out.strip()[-300:]))
    live = parse_buckets(out)
    targets = [b for b in ALLOWED_BUCKETS if b in live]
    for b in targets:
        require_writable(b)
    return targets, [b for b in live if is_protected(b)]


def planted(run: Runner, protected: list[str]) -> list[tuple[str, Rule]]:
    """Rules on protected buckets beyond the platform default. Read-only."""
    found = []
    for b in protected:
        for rule in list_rules(run, b):
            if rule.name != PLATFORM_DEFAULT_RULE:
                found.append((b, rule))
    return found


def run_mode(run: Runner, mode: str, bucket: str | None = None, dry_run: bool = False) -> int:
    """Return the exit status for `mode` in apply|list|check."""
    if bucket is not None:
        try:
            require_writable(bucket)
        except RefusedBucket as exc:
            log.error(str(exc))
            return 2
    targets, protected = target_buckets(run)
    if bucket is not None:
        targets = [b for b in targets if b == bucket]
    if not targets:
        log.error("no allowed bucket (%s) in the live listing" % ", ".join(ALLOWED_BUCKETS))
        return 2
    wanted = desired_rules()
    status = 0
    for b in targets:
        existing = list_rules(run, b)
        if mode == "list":
            for r in existing:
                print("%s: %s prefix=%r expire=%s abort=%s" % (b, r.name, r.prefix, r.expire_days, r.abort_days))
            continue
        missing, drifted = diff(existing, wanted)
        for r in missing:
            print("MISSING %s: %s" % (b, r.name))
        for r in drifted:
            print("DRIFTED %s: %s" % (b, r.name))
        if mode == "check":
            if missing or drifted:
                status = 1
            continue
        for r in drifted:
            if not dry_run:
                _remove(run, b, r.name)
        for r in [*missing, *drifted]:
            if dry_run:
                print("WOULD ADD %s: %s" % (b, r.name))
            else:
                _add(run, b, r)
                print("ADDED %s: %s" % (b, r.name))
        print("%s: %d added, %d updated, %d unchanged" % (b, len(missing), len(drifted), len(wanted) - len(missing) - len(drifted)))
    if mode in ("list", "check"):
        for b, r in planted(run, protected):
            print("PLANTED %s: %s prefix=%r expire=%s abort=%s" % (b, r.name, r.prefix, r.expire_days, r.abort_days))
            status = 1
        print("protected buckets read, not written: %s" % (", ".join(protected) or "none"))
    return status


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="r2_lifecycle", description=__doc__.split("\n", 1)[0])
    parser.add_argument("mode", nargs="?", default="apply", choices=("apply", "list", "check"))
    parser.add_argument("--check", action="store_true", help="same as the check mode")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--bucket", help="restrict to one allowed bucket; a protected or unlisted name exits 2")
    args = parser.parse_args(argv)
    mode = "check" if args.check else args.mode
    if args.bucket:
        try:
            require_writable(args.bucket)
        except RefusedBucket as exc:
            log.error(str(exc))
            return 2
    try:
        auth = cf_auth.resolve(cf_auth.DEFAULT_ACCOUNT_ID)
    except cf_auth.CfAuthError as exc:
        log.error(str(exc))
        return 1
    try:
        cf_auth.await_propagation(auth)
        env = cf_auth.wrangler_env(auth, cf_auth.DEFAULT_ACCOUNT_ID, scrub_global_key=True)
        return run_mode(Wrangler(env), mode, args.bucket, args.dry_run)
    except (cf_auth.CfAuthError, RuntimeError) as exc:
        log.error(str(exc))
        return 1
    finally:
        if auth.created:
            cf_auth.self_destruct(auth)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
