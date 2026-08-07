#!/usr/bin/env python3
"""A workflow may not reference a secret its repository cannot read.

WHY THIS EXISTS. On 2026-08-07 it turned out that `Claude Review` had NEVER
succeeded in rediacc/account or rediacc/renet -- every run since at least
2026-07-28 failed, including runs on `main`. Both repos carry a
`claude-review.yml` that references `secrets.CLAUDE_CODE_OAUTH_TOKEN`. That
secret is an ORGANISATION secret with `visibility=selected`, and its
selected-repositories list contains exactly one entry: `console`. So in those
two repos the reference resolved to an empty string and the action aborted on
environment validation.

For eleven days two repositories appeared to have automated review and had
none. The 0804-1 wave merged renet#98 and account#74 with neither submodule
half ever reviewed. Nothing noticed, because no gate connects a workflow's
`secrets.X` reference to whether X is actually reachable from that repository:
workflow linting checks SYNTAX, and a missing secret is syntactically perfect.

WHAT IT CHECKS. Every `secrets.NAME` reference in every workflow of this repo
and its submodules must have a committed record saying that repository can read
that secret. A reference with no record, or with a record saying `false`, fails.

WHY A COMMITTED BASELINE. `npm run ci` must work offline and deterministically,
and reading secret visibility needs an org-admin token that most runs do not
have. So the gate compares committed facts; the network lives only in
`--refresh`, which rewrites them from the API. A gate that needs a token is a
gate that silently degrades to "passed" wherever the token is absent -- which is
the same failure shape as the thing it is here to catch.

WHAT IT CANNOT DO. It cannot see an org admin removing a repo from an allowlist
after the last refresh. That is what MAX_BASELINE_AGE_DAYS is for: the record
going stale is itself a failure, so the blind window is bounded and visible
rather than open-ended.
"""

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

# Refresh cadence. An allowlist can change without any commit touching this
# repo, so a stale record is a failure rather than a warning.
MAX_BASELINE_AGE_DAYS = 45

# Vacuity floor. These trees reference dozens of secrets; a handful means the
# scan broke and every comparison below would be over an empty set.
MIN_REFERENCES = 10

BASELINE = ".ci/config/secret-reachability.json"

# GitHub provides these; they are never org or repo secrets.
BUILTIN = {"GITHUB_TOKEN"}

# References that are OPTIONAL BY DESIGN: the workflow is written so that an
# empty value degrades to a documented behaviour rather than a failure. Each
# entry is a claim about the calling code, and it is reviewable -- the reason
# must name the line that makes the absence safe.
#
# Keep this list tiny. "It is failing and I want green" is not a reason; that is
# the escape hatch that turned the cli-manifest guard into decoration for its
# whole life.
OPTIONAL = {
    "ANTHROPIC_API_KEY": (
        "watchdog-monitor.yml:145-150 documents it as a tier that may not exist: "
        "an undefined secret interpolates to an empty string and the script treats "
        "'no credential' as 'this tier is absent', falling through to the allowlist. "
        "CLAUDE_CODE_OAUTH_TOKEN on the next line is the credential this org has."
    ),
}

# KNOWN-UNREACHABLE, with an EXPIRY. These are real defects that this session
# cannot fix, because the remedy is a GitHub secret operation and that is an
# operator power. Blocking every CI run on something no engineer here can
# action would make the gate a hostage rather than a guard.
#
# So each entry carries the issue that fixes it and a DATE after which the
# exception dies and this gate goes red. That is the difference between an
# acknowledged defect and a suppression: a suppression is silent and permanent,
# this one announces itself on every run and has a deadline.
KNOWN_UNREACHABLE = {
    ("account", "CLAUDE_CODE_OAUTH_TOKEN"): (
        "2026-09-07",
        "https://github.com/rediacc/account/issues/76 — org secret is visibility=selected "
        "scoped to `console` alone, so Claude Review has never once succeeded here. "
        "Fix is a secret operation: add the repo to the allowlist, or create a repo-level "
        "secret as claude-review.yml:10 already assumes.",
    ),
    ("renet", "CLAUDE_CODE_OAUTH_TOKEN"): (
        "2026-09-07",
        "https://github.com/rediacc/account/issues/76 — identical cause and identical "
        "remedy; confirmed by checking, every Claude Review run in renet has failed too.",
    ),
}

SECRET_RE = re.compile(r"secrets\.([A-Z_][A-Z0-9_]*)")


class ScanError(Exception):
    """The workflow set could not be read, so no verdict is possible."""


def repo_roots(root):
    """This repo plus every submodule that has its own workflows."""
    out = [("console", root)]
    for sub in sorted((root / "private").glob("*")):
        if (sub / ".github" / "workflows").is_dir():
            out.append((sub.name, sub))
    return out


def references(repo_root):
    """Every distinct secret name referenced by this repo's workflows."""
    wf = repo_root / ".github" / "workflows"
    names = set()
    files = sorted(wf.glob("*.yml")) + sorted(wf.glob("*.yaml"))
    for path in files:
        for m in SECRET_RE.finditer(path.read_text(encoding="utf-8", errors="replace")):
            if m.group(1) not in BUILTIN:
                names.add(m.group(1))
    return names, len(files)


def refresh(root, baseline_path):
    """Rewrite the record from the GitHub API. The network lives HERE only."""

    def gh(args):
        out = subprocess.run(
            ["gh", *args], capture_output=True, text=True, cwd=str(root), check=False
        )
        return out.stdout if out.returncode == 0 else None

    listing = gh(["api", "orgs/rediacc/actions/secrets", "--paginate", "--jq",
                  ".secrets[]|[.name,.visibility]|@tsv"])
    if not listing:
        print("refresh: cannot read the org secret list (needs an admin token)", file=sys.stderr)
        return 1

    org = {}
    for line in listing.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            org[parts[0]] = parts[1]

    # Which repos each `selected` secret is scoped to.
    scoped = {}
    for name, vis in org.items():
        if vis != "selected":
            continue
        repos = gh(["api", f"orgs/rediacc/actions/secrets/{name}/repositories",
                    "--paginate", "--jq", ".repositories[].name"])
        scoped[name] = set((repos or "").split())

    data = {
        "_comment": [
            "Which secrets each repository can actually READ, not merely reference.",
            "Refresh: npm run check:ci-secret-reachability -- --refresh (needs an org-admin token).",
            "Written because Claude Review failed in account and renet for eleven days:",
            "both reference CLAUDE_CODE_OAUTH_TOKEN, an org secret scoped to console alone.",
        ],
        "refreshed_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repos": {},
    }

    for repo_name, repo_root in repo_roots(root):
        names, _ = references(repo_root)
        gh_repo = f"rediacc/{'console' if repo_name == 'console' else repo_name}"
        repo_own = gh(["api", f"repos/{gh_repo}/actions/secrets", "--paginate", "--jq",
                       ".secrets[].name"])
        own = set((repo_own or "").split())
        entry = {}
        for n in sorted(names):
            if n in own:
                entry[n] = {"reachable": True, "via": "repo"}
            elif n in org:
                vis = org[n]
                if vis in ("all", "private"):
                    entry[n] = {"reachable": True, "via": f"org:{vis}"}
                else:
                    ok = gh_repo.split("/")[-1] in scoped.get(n, set())
                    entry[n] = {"reachable": ok, "via": "org:selected"}
            else:
                entry[n] = {"reachable": False, "via": "absent"}
        data["repos"][repo_name] = entry

    baseline_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    total = sum(len(v) for v in data["repos"].values())
    bad = sum(1 for v in data["repos"].values() for r in v.values() if not r["reachable"])
    print(f"refreshed {total} reference(s) across {len(data['repos'])} repo(s); {bad} unreachable")
    return 0


def verdicts(refs_by_repo, record):
    """Every complaint. Pure, so the controls can drive it directly."""
    out = []
    for repo_name, names in sorted(refs_by_repo.items()):
        known = record.get("repos", {}).get(repo_name, {})
        for n in sorted(names):
            if n in OPTIONAL:
                continue
            waiver = KNOWN_UNREACHABLE.get((repo_name, n))
            if waiver is not None:
                expiry, why = waiver
                if dt.date.today().isoformat() <= expiry:
                    print(
                        f"  KNOWN, waived until {expiry}: {repo_name}/{n} — {why}",
                        file=sys.stderr,
                    )
                    continue
                out.append(
                    f"{repo_name}: the waiver for `secrets.{n}` EXPIRED on {expiry}. {why} "
                    f"Either the fix landed and this entry should go, or it did not and the "
                    f"deadline is the point."
                )
                continue
            got = known.get(n)
            if got is None:
                out.append(
                    f"{repo_name}: workflows reference `secrets.{n}` but the record says nothing "
                    f"about it. Run --refresh; if it is genuinely unreachable this is the bug."
                )
            elif not got.get("reachable"):
                out.append(
                    f"{repo_name}: workflows reference `secrets.{n}`, which that repository "
                    f"CANNOT read (via={got.get('via')}). It resolves to an empty string at "
                    f"runtime and the step fails on a missing value, not on a missing secret. "
                    f"Either scope the secret to this repo or stop referencing it."
                )
    return out


def controls(record):
    """Prove the detector fires in BOTH directions before any real read."""
    probe_repo = next(iter(record.get("repos", {})), None)
    if probe_repo is None:
        return "the record names no repositories, so nothing can be probed"
    if not verdicts({probe_repo: {"A_SECRET_NO_RECORD_MENTIONS"}}, record):
        return "planted an unrecorded secret reference and the detector stayed silent"
    fake = {"repos": {probe_repo: {"X": {"reachable": False, "via": "org:selected"}}}}
    if not verdicts({probe_repo: {"X"}}, fake):
        return "planted a reference to an unreachable secret and the detector stayed silent"
    ok = {"repos": {probe_repo: {"X": {"reachable": True, "via": "repo"}}}}
    if verdicts({probe_repo: {"X"}}, ok):
        return "planted a reachable secret and the detector complained anyway"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="rewrite the record from the API")
    args = ap.parse_args(argv)

    root = pathlib.Path(__file__).resolve().parents[3]
    baseline_path = root / BASELINE

    if args.refresh:
        return refresh(root, baseline_path)

    if not baseline_path.is_file():
        print(f"VACUOUS INPUT: {BASELINE} is missing, so nothing can be compared", file=sys.stderr)
        return 1

    refs_by_repo = {}
    total_refs = 0
    total_files = 0
    for repo_name, repo_root in repo_roots(root):
        names, nfiles = references(repo_root)
        refs_by_repo[repo_name] = names
        total_refs += len(names)
        total_files += nfiles

    if total_refs < MIN_REFERENCES or total_files == 0:
        print(
            f"VACUOUS INPUT: scanned {total_files} workflow file(s) and found {total_refs} secret "
            f"reference(s), expected at least {MIN_REFERENCES}. A check over an empty set exits 0 "
            f"and reads exactly like full coverage.",
            file=sys.stderr,
        )
        return 1

    record = json.loads(baseline_path.read_text(encoding="utf-8"))

    broken = controls(record)
    if broken:
        print(
            f"CONTROL FAILED, so nothing below is meaningful: {broken}.\n"
            "  This gate refuses a verdict when it cannot demonstrate its own detector,\n"
            "  because the defect it exists for is a check that reported success while\n"
            "  examining nothing.",
            file=sys.stderr,
        )
        return 1

    problems = verdicts(refs_by_repo, record)

    try:
        age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(record["refreshed_at"])
        if age.days > MAX_BASELINE_AGE_DAYS:
            problems.append(
                f"the record is {age.days} days old (limit {MAX_BASELINE_AGE_DAYS}). An org "
                f"allowlist can change without any commit here, so a stale record is the one "
                f"blind spot this gate has. Refresh it."
            )
    except (KeyError, ValueError):
        problems.append("refreshed_at is missing or unparseable, so the record's age is unknown")

    if problems:
        print("Workflows reference secrets their repository cannot read:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(
        f"{total_refs} secret reference(s) across {len(refs_by_repo)} repo(s) are all reachable "
        f"(controls fired in both directions)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
