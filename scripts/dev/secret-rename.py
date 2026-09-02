#!/usr/bin/env python3
"""GitHub-side secret rename (durable plan Part 10 + the Part 12 inventory), DRY-RUN by default.

WHAT THIS IS. The Worker-side rename and the Bitwarden-side rename landed on
2026-09-02. What remains is the GitHub side: the org secrets and every
`secrets.X` read, env mapping, shell reader and doc that spells the OLD GitHub
name. The operator sequenced that AFTER the CI cutover ("CI cutover first,
rename after"), so this script exists to make the rename a five-minute, reviewable
act when that day comes, not to run it now. Without `--apply` it writes nothing.

WHAT IT KNOWS THAT A SED DOES NOT (all measured in Part 12):
  - Every prefix-adding rename leaves the old name as a substring of its own
    replacement (R2_ENDPOINT -> CLOUDFLARE_R2_ENDPOINT). Both boundaries are
    anchored, so the pass is idempotent and container tokens survive untouched:
    CONFIG_R2_*, ACCOUNT_BACKUP_S3_*, SECRET_BACKUP_S3_*, CD_APP_PRIVATE_KEY.
  - The shadow-run compares GH_<NAME> against BWS_<NAME> and lists NAME in
    SHADOW_NAMES. Renaming NAME alone would break the trio, so GH_OLD -> GH_NEW
    and BWS_OLD -> BWS_NEW are rewritten with NAME.
  - Longest-first ordering, so STRIPE_SECRET_KEY_EU is consumed before any bare
    STRIPE_SECRET_KEY could see it, and OTLP_CLIENT_CREDENTIALS_EU before the
    Worker key OTLP_CLIENT_CREDENTIALS (which is NOT renamed here; it is a
    Worker name and already moved to OBS_OTLP_CREDENTIALS).
  - Names built at runtime (`${!var}`, `key_var=`) cannot be rewritten by text
    substitution. They are LISTED, never edited.
  - The one-account Stripe collapse maps three secrets onto one name. Where a
    file carried all three, the result is three identical keys; those hits are
    listed separately so the duplicate is removed by hand.
  - Generated files are reported and skipped: regenerate them instead.

WHAT IT DOES NOT DO: touch GitHub. Creating the new org secrets (copy, do not
mint: decision 8ter) and deleting the old ones is `gh secret set` / `gh secret
delete`, run by a person, after this diff is reviewed.

Usage:
  python3 scripts/dev/secret-rename.py            # dry-run summary
  python3 scripts/dev/secret-rename.py --show FILE # unified diff for one file
  python3 scripts/dev/secret-rename.py --apply     # rewrite the tree
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (old, new). Copied from Part 10's table on 2026-09-02, not retyped from memory.
RENAMES: list[tuple[str, str]] = [
    ("R2_ACCESS_KEY_ID", "CLOUDFLARE_R2_ACCESS_KEY_ID"),
    ("R2_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_SECRET_ACCESS_KEY"),
    ("R2_ENDPOINT", "CLOUDFLARE_R2_ENDPOINT"),
    ("R2_MEDIA_ACCESS_KEY_ID", "CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID"),
    ("R2_MEDIA_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY"),
    ("R2_MEDIA_ENDPOINT", "CLOUDFLARE_R2_MEDIA_ENDPOINT"),
    ("BACKUP_S3_ACCESS_KEY_ID", "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"),
    ("BACKUP_S3_SECRET_ACCESS_KEY", "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"),
    ("BACKUP_S3_ENDPOINT", "ACCOUNT_BACKUP_S3_ENDPOINT"),
    ("TURNSTILE_SECRET_KEY", "CLOUDFLARE_TURNSTILE_SECRET_KEY"),
    ("BREAKPOINT_TUNNEL_TOKEN", "CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN"),
    ("SES_AK_ID", "AWS_IAM_ADMIN_ACCESS_KEY_ID"),
    ("SES_AK_SECRET", "AWS_IAM_ADMIN_SECRET_ACCESS_KEY"),
    ("STRIPE_SECRET_KEY_EU", "STRIPE_SECRET_KEY"),
    ("STRIPE_SECRET_KEY_US", "STRIPE_SECRET_KEY"),
    ("STRIPE_SECRET_KEY_ASIA", "STRIPE_SECRET_KEY"),
    ("OTLP_CLIENT_CREDENTIALS_EU", "OBS_OTLP_CREDENTIALS_EU"),
    ("OTLP_CLIENT_CREDENTIALS_US", "OBS_OTLP_CREDENTIALS_US"),
    ("OTLP_CLIENT_CREDENTIALS_ASIA", "OBS_OTLP_CREDENTIALS_ASIA"),
    ("APP_PRIVATE_KEY", "GITHUB_APP_PRIVATE_KEY"),
    ("AUTOPILOT_APP_ID", "GITHUB_AUTOPILOT_APP_ID"),
    ("AUTOPILOT_PRIVATE_KEY", "GITHUB_AUTOPILOT_PRIVATE_KEY"),
    ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN"),
    ("GPG_PRIVATE_KEY", "RELEASE_GPG_PRIVATE_KEY"),
    ("GPG_PASSPHRASE", "RELEASE_GPG_PASSPHRASE"),
]
COLLAPSES = {"STRIPE_SECRET_KEY_EU", "STRIPE_SECRET_KEY_US", "STRIPE_SECRET_KEY_ASIA"}

# Generated: regenerate, do not edit.
GENERATED = {
    ".ci/config/secret-reachability.json": "npm run check:ci-secret-reachability -- --refresh",
    ".ci/config/bws-secret-map.json": "scripts/dev/bws-map-refresh.py (already on the new names)",
}
# Never rewritten: history, session notes, this script, the plan that defines the table.
SKIP_PREFIXES = ("agent/", "node_modules/", ".git/", "scripts/dev/secret-rename.py")
SKIP_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp3",
    ".mp4",
    ".woff",
    ".woff2",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
)
# Same limit check_secret_reachability.py enforces on itself.
REACH_MAX_AGE_DAYS = 45

# Untracked files that are part of the surface.
EXTRA = ["private/account/.env", "private/account/.env.bench"]

# THE WALK CANNOT SEE A GITIGNORED SIBLING REPO, and that cost an outage.
# files() uses `git ls-files --recurse-submodules`, which reaches submodules but
# NOT private/growth -- its own git repository, gitignored by console. So the
# rename left private/growth/video_pipeline/{publish-solutions.sh,publish.py}
# requiring R2_MEDIA_* while .env had already become CLOUDFLARE_R2_MEDIA_*, and
# the publish pipeline died at its step-0 credential check. Loudly rather than
# silently, but broken -- and invisible to every console-side scan, the same
# blindness that once reported 9 of 10 keys in that repo as unreferenced.
NON_SUBMODULE_REPOS = ("private/growth", "private/generative")

# Runtime-constructed names: text substitution cannot see them. Listed, never edited.
# `vars.NAME`, `VARS.NAME`, `vars['NAME']` -- GitHub contexts are case
# insensitive and index-addressable. The leading class also excludes a DOT, so
# `needs.x.outputs.vars.NAME` is a property path, not a variable reference, and
# is left to the normal rename.
VARS_CTX = re.compile(r"(?<![A-Za-z0-9_.])vars\s*[.\[]\s*['\"]?$", re.IGNORECASE)

INDIRECTION = re.compile(r"\$\{!|key_var=|_VAR=\"|\bSUFFIX\b.*\$\{|\$\{[A-Z_]+_\$\{SUFFIX\}")


class Rules:
    """ONE alternation, longest-first, applied in a single pass per file. The
    first cut of this script ran 75 separate substitutions over every tracked
    file and did not finish in two minutes; one pass finishes in seconds."""

    def __init__(self) -> None:
        self.map = dict(RENAMES)
        alts = "|".join(re.escape(o) for o, _ in sorted(RENAMES, key=lambda r: -len(r[0])))
        self.pat = re.compile(rf"(?<![A-Za-z0-9_])(GH_|BWS_)?({alts})(?![A-Za-z0-9_])")
        self.stems = tuple({o.split("_")[0] for o, _ in RENAMES})

    def apply(self, text: str) -> tuple[str, Counter, list[str], list[tuple[int, str, str]]]:
        counts: Counter = Counter()
        collapsed: list[str] = []
        variables: list[tuple[int, str, str]] = []

        def sub(m: re.Match[str]) -> str:
            old = m.group(2)
            # A `vars.NAME` reference is an Actions VARIABLE, and this table is
            # GitHub org SECRETS. `gh secret set` does not touch a variable, so
            # rewriting the reference points it at a variable that was never
            # renamed and the expression silently evaluates to "". That is not
            # hypothetical: AUTOPILOT_APP_ID is in this table and is read as
            # `vars.AUTOPILOT_APP_ID` at four app-token mint sites in
            # autopilot.yml, whose own comment (:58-62) warns it is a variable
            # NOT a secret -- and this script rewrote that warning too. Every
            # autopilot token mint would have failed. Report, never rewrite.
            if VARS_CTX.search(text[max(0, m.start() - 48) : m.start()]):
                line = text.count("\n", 0, m.start()) + 1
                variables.append((line, old, self.map[old]))
                return m.group(0)
            counts[old] += 1
            if old in COLLAPSES and old not in collapsed:
                collapsed.append(old)
            return (m.group(1) or "") + self.map[old]

        return self.pat.sub(sub, text), counts, collapsed, variables


def files() -> list[Path]:
    ls = (
        subprocess.run(
            ["git", "ls-files", "-z", "--recurse-submodules"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    rels = [p for p in ls if p] + EXTRA
    # Sibling repos console's index cannot see: each has its own git, so ask IT.
    for repo in NON_SUBMODULE_REPOS:
        if not (ROOT / repo / ".git").exists():
            continue
        got = subprocess.run(
            ["git", "-C", str(ROOT / repo), "ls-files", "-z"],
            capture_output=True,
            check=False,
        )
        rels += [f"{repo}/{q}" for q in got.stdout.decode().split("\0") if q]
    out = []
    for rel in rels:
        if rel.startswith(SKIP_PREFIXES) or rel.endswith(SKIP_SUFFIXES):
            continue
        p = ROOT / rel
        # Lockfiles and bundles never carry a secret name and dominate the byte count.
        if (
            p.is_file()
            and p.stat().st_size <= 2_000_000
            and not rel.endswith(("package-lock.json", ".min.js", ".map"))
        ):
            out.append(p)
    return out


def rewrite(text: str, rs: Rules) -> tuple[str, Counter, list[str], list[tuple[int, str, str]]]:
    if not any(s in text for s in rs.stems):
        return text, Counter(), [], []
    return rs.apply(text)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--apply", action="store_true", help="rewrite files (default is a dry run)")
    ap.add_argument("--show", metavar="FILE", help="print the unified diff for one file and exit")
    args = ap.parse_args()

    rs = Rules()
    # Control: the boundaries must hold before any verdict is printed.
    probe = "R2_ENDPOINT CONFIG_R2_ENDPOINT BACKUP_S3_ENDPOINT ACCOUNT_BACKUP_S3_ENDPOINT GH_APP_PRIVATE_KEY CD_APP_PRIVATE_KEY STRIPE_SECRET_KEY_EU CLOUDFLARE_R2_ENDPOINT"
    got, _, _, _ = rewrite(probe, rs)
    want = "CLOUDFLARE_R2_ENDPOINT CONFIG_R2_ENDPOINT ACCOUNT_BACKUP_S3_ENDPOINT ACCOUNT_BACKUP_S3_ENDPOINT GH_GITHUB_APP_PRIVATE_KEY CD_APP_PRIVATE_KEY STRIPE_SECRET_KEY CLOUDFLARE_R2_ENDPOINT"
    if got != want:
        print(f"✗ instrument control failed:\n  got  {got}\n  want {want}", file=sys.stderr)
        return 1
    again, _, _, _ = rewrite(got, rs)
    if again != got:
        print(
            "✗ instrument control failed: a second pass changed the text (not idempotent)",
            file=sys.stderr,
        )
        return 1
    # Control, both directions: a `vars.` reference must survive untouched and be
    # REPORTED, while the same name used as a secret must still be rewritten. One
    # direction alone would pass on a script that rewrote nothing at all.
    vprobe = "vars.AUTOPILOT_APP_ID and secrets.AUTOPILOT_APP_ID"
    vgot, vcounts, _, vhits = rewrite(vprobe, rs)
    if vgot != "vars.AUTOPILOT_APP_ID and secrets.GITHUB_AUTOPILOT_APP_ID":
        print(f"✗ instrument control failed: vars./secrets. split\n  got  {vgot}", file=sys.stderr)
        return 1
    if len(vhits) != 1 or sum(vcounts.values()) != 1:
        print(
            f"✗ instrument control failed: expected 1 reported variable and 1 rewrite, "
            f"got {len(vhits)} and {sum(vcounts.values())}",
            file=sys.stderr,
        )
        return 1

    per_file: dict[str, Counter] = {}
    per_name: Counter = Counter()
    collapse_hits: list[str] = []
    indirection_hits: list[str] = []
    generated_hits: list[str] = []
    variable_hits: list[str] = []
    changed: dict[Path, str] = {}
    old_stems = rs.stems
    for p in files():
        rel = p.relative_to(ROOT).as_posix()
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new, counts, collapsed, variables = rewrite(text, rs)
        for line, old, target in variables:
            variable_hits.append(f"{rel}:{line}: vars.{old}  (would have become vars.{target})")
        if not counts:
            continue
        if rel in GENERATED:
            generated_hits.append(f"{rel}: {sum(counts.values())} hit(s) -> {GENERATED[rel]}")
            continue
        per_file[rel] = counts
        per_name.update(counts)
        if args.show and rel == args.show:
            sys.stdout.writelines(
                difflib.unified_diff(text.splitlines(True), new.splitlines(True), rel, rel)
            )
            return 0
        for i, line in enumerate(text.splitlines(), 1):
            if INDIRECTION.search(line) and any(s in line for s in old_stems):
                indirection_hits.append(f"{rel}:{i}: {line.strip()[:100]}")
        if collapsed:
            for i, line in enumerate(new.splitlines(), 1):
                if "STRIPE_SECRET_KEY" in line and re.search(
                    r"(?<![A-Za-z0-9_])STRIPE_SECRET_KEY(?![A-Za-z0-9_])", line
                ):
                    collapse_hits.append(f"{rel}:{i}: {line.strip()[:100]}")
        changed[p] = new

    if args.show:
        print(f"no change in {args.show}")
        return 0

    # PREFLIGHT, and it is a REFUSAL, not a warning. Every name this table renames
    # TO must already exist in the Bitwarden map, because the rename is what makes
    # the Bitwarden copy the one CI resolves. The case that made this mandatory:
    # OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA} -> OBS_OTLP_CREDENTIALS_{EU,US,ASIA},
    # where none of the three targets existed in the map and no scan on either
    # side could see it, because set-account-worker-secrets.sh:134 builds the name
    # at RUNTIME ("OBS_OTLP_CREDENTIALS_${SUFFIX}") so it never appears as a
    # literal anywhere. Applying the rename would have failed _require_nonempty
    # in all three regions -- the founding OTLP incident, reproduced by the
    # migration built to prevent it. A dry run still reports; only --apply is
    # refused, so this cannot block the measurement it is meant to inform.
    try:
        bws_map = json.loads((ROOT / ".ci" / "config" / "bws-secret-map.json").read_text())[
            "secrets"
        ]
    except (OSError, ValueError, KeyError) as exc:
        print(f"REFUSING: cannot read .ci/config/bws-secret-map.json ({exc})", file=sys.stderr)
        return 1
    # ONLY names the cutover will actually fetch from Bitwarden. A rename whose
    # SOURCE is not a GitHub org secret is a local-file rename with no store
    # counterpart -- SES_AK_ID/SES_AK_SECRET live only in private/account/.env
    # and are read by the rotation tool itself, so demanding a map entry for
    # AWS_IAM_ADMIN_* would block the rename on creating a secret nothing
    # fetches. Getting this wrong in the strict direction is still a refusal to
    # act, which is why it is re-derived rather than hand-listed.
    try:
        reach = json.loads((ROOT / ".ci" / "config" / "secret-reachability.json").read_text())[
            "repos"
        ]["console"]
    except (OSError, ValueError, KeyError) as exc:
        print(f"REFUSING: cannot read secret-reachability.json ({exc})", file=sys.stderr)
        return 1
    try:
        whole = json.loads((ROOT / ".ci" / "config" / "secret-reachability.json").read_text())
        refreshed = dt.datetime.strptime(whole["refreshed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.UTC
        )
        stale_days = (dt.datetime.now(dt.UTC) - refreshed).days
    except (OSError, ValueError, KeyError) as exc:
        print(
            f"REFUSING: secret-reachability.json has no parseable refreshed_at ({exc})",
            file=sys.stderr,
        )
        return 1
    if stale_days > REACH_MAX_AGE_DAYS:
        print(
            f"REFUSING: secret-reachability.json is {stale_days} days old (limit "
            f"{REACH_MAX_AGE_DAYS}). It decides which rename targets must already exist in "
            f"Bitwarden, so a stale copy silently EXEMPTS any org secret created since. "
            f"Refresh it first: npm run check:ci-secret-reachability -- --refresh",
            file=sys.stderr,
        )
        return 1
    org_secrets = {k for k, v in reach.items() if isinstance(v, dict) and v.get("reachable")}
    if not org_secrets:
        print("REFUSING: secret-reachability.json lists no console secret", file=sys.stderr)
        return 1
    unmapped = sorted({new for old, new in RENAMES if old in org_secrets and new not in bws_map})
    if unmapped:
        print(f"\nUNMAPPED TARGETS ({len(unmapped)}): the rename points these at a Bitwarden")
        print("secret that does not exist, so CI would resolve nothing after cutover:")
        for name in unmapped:
            src = [o for o, n in RENAMES if n == name]
            print(f"  {name}   <- {', '.join(src)}")
        print("  Create them first (./run.sh rotation rotate <slug>, which MINTS), then")
        print("  refresh the map with scripts/dev/bws-map-refresh.py.")
    if args.apply and unmapped:
        print("\nREFUSING --apply: fix the unmapped targets above first. Nothing was written.")
        return 1

    total = sum(per_name.values())
    print(
        f"{'APPLYING' if args.apply and not unmapped else 'DRY RUN'}: "
        f"{total} replacement(s) in {len(per_file)} file(s)\n"
    )
    print("per name:")
    for name, n in sorted(per_name.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  {name}")
    print("\nper file:")
    for rel, counts in sorted(per_file.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {sum(counts.values()):5d}  {rel}")
    if generated_hits:
        print("\nGENERATED (skipped; regenerate instead):")
        for h in generated_hits:
            print(f"  {h}")
    if indirection_hits:
        print(
            f"\nHAND-EDIT ({len(indirection_hits)}): names built at runtime on these lines; the rewrite cannot see them:"
        )
        for h in indirection_hits:
            print(f"  {h}")
    if variable_hits:
        print(
            f"\nVARIABLE ({len(variable_hits)}): read as `vars.NAME`, so `gh secret set` does NOT"
            " rename them and this script leaves them alone:"
        )
        for h in variable_hits:
            print(f"  {h}")
        print(
            "  These are Actions VARIABLES. Renaming one is `gh variable delete <old> && gh variable"
            " set <new>` (org- or repo-level, matching its current visibility), a separate decision"
            " from the secret rename. If you do rename a variable, hand-edit its `vars.` references"
            " -- this script will not, on purpose."
        )
    if collapse_hits:
        print(
            f"\nCOLLAPSE ({len(collapse_hits)}): STRIPE_SECRET_KEY_{{EU,US,ASIA}} became one name; remove duplicates by hand:"
        )
        for h in collapse_hits:
            print(f"  {h}")
    print(
        "\nAFTER --apply: create the new org secrets by COPY (gh secret set), run every gate that hardcodes a"
    )
    print(
        "name (check-workflows.sh, check_workflow_submodule_deps.py, check_secret_reachability.py,"
    )
    print(
        "check-autopilot-no-bypass.sh), regenerate the GENERATED files, then delete the old org secrets."
    )
    if args.apply:
        # EXTRA's files are UNTRACKED and hold live values, so git is not the
        # undo for them: `private/account/.env` rewritten wrongly is gone. Back
        # every untracked target up beside itself before the first write, and
        # refuse the whole run if a backup cannot be made -- a partial rewrite
        # of a credential file is worse than no rewrite.
        backups: list[str] = []
        for target in EXTRA:
            src = ROOT / target
            if src not in changed or not src.is_file():
                continue
            dst = src.with_name(src.name + ".pre-rename.bak")
            try:
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                dst.chmod(0o600)
            except OSError as exc:
                print(f"REFUSING: cannot back up {target} ({exc}); nothing was written")
                return 1
            backups.append(str(dst.relative_to(ROOT)))
        for p, new in changed.items():
            p.write_text(new, encoding="utf-8")
        print(f"\nwrote {len(changed)} file(s)")
        for b in backups:
            print(f"backup: {b} (untracked file, git is not its undo -- delete it once verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
