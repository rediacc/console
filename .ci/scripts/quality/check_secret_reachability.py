#!/usr/bin/env python3
"""A workflow may not reference a secret its repository cannot read.

WHY THIS EXISTS. On 2026-08-07 it turned out that `Claude Review` had NEVER
succeeded in rediacc/account or rediacc/renet -- every run since at least
2026-07-28 failed, including runs on `main`. Both repos carry a
`claude-review.yml` that references `secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`. That
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

---- gate ----
step: Secret reachability
needs: python-yaml
selftest: true
lane: quality-security
---- end gate ----
"""

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

import yaml

# Refresh cadence. An allowlist can change without any commit touching this repo, so a stale record is a failure rather than a warning.
MAX_BASELINE_AGE_DAYS = 45

# Vacuity floor. These trees reference dozens of secrets; a handful means the
# scan broke and every comparison below would be over an empty set. 1 since 2026-09-09, down from 5, down from 10. The corpus shrinks because references are RETIRED, not because the scan breaks -- and it has now reached its floor in the literal sense: ONE is the TERMINAL STATE of this migration, because `BWS_ACCESS_TOKEN` is the bootstrap credential every other secret is fetched
# WITH, so it can never itself be fetched. Everything else is in Bitwarden.
#
# ANY FLOOR ABOVE 1 REDS AT THE FINISH LINE, which is the trap this repository keeps paying for: a threshold calibrated mid-migration becomes a false failure at the moment the migration succeeds. On 2026-09-09 the operator deleted every non-BWS repo secret on all three repositories, deliberately, to force the stragglers into the open -- so the count was always going to arrive here.
#
# ONE STILL DISTINGUISHES "clean" FROM "did not run", which is the only job a floor has: 21 workflows reference BWS_ACCESS_TOKEN, so a scan that stopped seeing the tree yields 0 and reds, while any healthy tree yields at least 1.
#
# The single remaining non-BWS reference is `BREAKPOINT_TUNNEL_TOKEN` in breakpoint.yml, and it is UNREACHABLE as of that deletion. It is not an oversight and it must NOT be "migrated": that job's later steps include `Start debug shell`, and bws-secrets exports through GITHUB_ENV into every later step, so fetching there would hand a human on the runner the credential that reads all
# 58 secrets. A step-scoped repo secret is the correct shape for it -- see the reasoning at breakpoint.yml:196-214.
MIN_REFERENCES = 1

BASELINE = ".ci/config/secret-reachability.json"

# GitHub provides these; they are never org or repo secrets.
BUILTIN = {"GITHUB_TOKEN"}

# References that are OPTIONAL BY DESIGN: the workflow is written so that an empty value degrades to a documented behaviour rather than a failure. Each entry is a claim about the calling code, and it is reviewable -- the reason must name the line that makes the absence safe.
#
# Keep this list tiny. "It is failing and I want green" is not a reason; that is
# the escape hatch that turned the cli-manifest guard into decoration for its whole life. EMPTY, and that is the healthy state. It held one entry, ANTHROPIC_API_KEY, excusing a reference to a credential that did not exist. On 2026-09-02 the operator ruled out pay-as-you-go API billing, so the key will never exist and the REFERENCE was deleted rather than excused -- which is the
# right end for every entry here: a suppression outlives its reason silently, a deleted reference cannot.
OPTIONAL = {}

# KNOWN-UNREACHABLE, with an EXPIRY. These are real defects that this session cannot fix, because the remedy is a GitHub secret operation and that is an operator power. Blocking every CI run on something no engineer here can action would make the gate a hostage rather than a guard.
#
# So each entry carries the issue that fixes it and a DATE after which the exception dies and this gate goes red. That is the difference between an acknowledged defect and a suppression: a suppression is silent and permanent, this one announces itself on every run and has a deadline.
KNOWN_UNREACHABLE: dict[tuple[str, str], tuple[str, str]] = {
    # Empty as of 2026-09-02. The two entries that lived here -- account and renet unable to read ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN, waived until 2026-09-07 -- were closed by their own stated remedy: the org secret's visibility was `selected` and scoped to console alone, and both repos were added to its allowlist (gh api PUT orgs/rediacc/actions/secrets/.../repositories/<id>).
    # Claude Review had never once succeeded in either repo before that. Keep the mechanism: a waiver here announces itself every run and carries a deadline, which is what separates it from a suppression.
}

SECRET_RE = re.compile(r"secrets\.([A-Z_][A-Z0-9_]*)")


class ScanError(Exception):
    """The workflow set could not be read, so no verdict is possible."""


def repo_roots(root):
    """This repo plus every submodule that has its own workflows."""
    out = [("console", root)]
    out.extend(
        (sub.name, sub)
        for sub in sorted((root / "private").glob("*"))
        if (sub / ".github" / "workflows").is_dir()
    )
    return out


def declared_secrets(text):
    """Names a reusable workflow DECLARES under on.workflow_call.secrets.

    WHY PyYAML AND NOT A REGEX, carried here from the workflow step that used to
    install it (ci-quality.yml, quality-security) before that step was generated
    from this gate's own header. A generated step keeps the command and drops the
    prose, so reasoning left there dies at the cutover.

    This gate must know which secret reads are a reusable's own DECLARED INPUTS
    rather than org secrets, and that lives in NESTED `on.workflow_call.secrets`.
    Hand-rolling a parser for nested YAML is a correctness risk a gate cannot
    afford, and a yaml-if-available-else-regex fallback would make the gate mean
    different things in CI and locally.

    A TRAP PAID FOR ALREADY: naming the read form literally in that workflow
    comment made CHECK 2 of check-workflow-gates.sh match its own prose and report
    the file as reading an undeclared secret. A detector matching a comment about
    itself is a documented trap in TRAPS.md, and it is why the phrasing here
    describes the shape rather than spelling it.

    Inside a reusable, `secrets.X` reads the DECLARED INPUT, not an org secret
    of that name -- the caller supplies it, under whatever name the caller has.
    Once the two name-spaces diverge (the org keeps `R2_ACCESS_KEY_ID` while the
    workflow layer says `CLOUDFLARE_R2_ACCESS_KEY_ID`) that distinction stops
    being academic: 18 declared inputs read as unreachable org secrets, which is
    a false red on the callee for something only the CALLER can get wrong -- and
    the caller's passthrough is still scanned, so nothing is lost by excluding
    these.

    Parsed, not regexed. `on` is the YAML boolean True after safe_load, which is
    the one gotcha; both spellings are tried.
    """
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        # A file this cannot parse is left ENTIRELY to the caller: returning an empty set here means every read in it is judged as an org secret, which is the conservative direction (noisy, never silent).
        return set()
    if not isinstance(doc, dict):
        return set()
    on = doc.get(True, doc.get("on"))
    if not isinstance(on, dict):
        return set()
    call = on.get("workflow_call")
    if not isinstance(call, dict):
        return set()
    sec = call.get("secrets")
    return set(sec) if isinstance(sec, dict) else set()


def references(repo_root):
    """Every distinct ORG secret name referenced by this repo's workflows."""
    wf = repo_root / ".github" / "workflows"
    names = set()
    files = sorted(wf.glob("*.yml")) + sorted(wf.glob("*.yaml"))
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        declared = declared_secrets(text)
        # A `#` COMMENT IS NOT A REFERENCE. Scanning raw text made the two the same thing, so a comment RECORDING that some `secrets.X` was removed reported as a live read of it -- the removal tripping the gate the removal satisfied. Measured 2026-09-09 on watchdog-monitor.yml: every real reference was repointed at Bitwarden and the gate still named CLAUDE_CODE_OAUTH_TOKEN, from
        # the comment explaining why.
        #
        # The pressure that creates is the harm: the cheapest way to green is to delete the explanation, and then nobody knows why the credential went. Its sibling `scripts/gates/check-secret-scope.ts` carries the identical filter, added the same day
        # for the identical reason; so do check:ci-env-file-adoption and
        # block_host_toolchain_run. YAML has one comment form, so a `#` opening a line is
        # the whole rule -- a trailing `#` can sit inside a `${{ }}` string and
        # over-scanning is the safe direction.
        code = "\n".join(ln for ln in text.split("\n") if not ln.lstrip().startswith("#"))
        for m in SECRET_RE.finditer(code):
            if m.group(1) not in BUILTIN and m.group(1) not in declared:
                names.add(m.group(1))
    return names, len(files)


def refresh(root, baseline_path):
    """Rewrite the record from the GitHub API. The network lives HERE only."""

    def gh(args):
        out = subprocess.run(
            ["gh", *args], capture_output=True, text=True, cwd=str(root), check=False
        )
        return out.stdout if out.returncode == 0 else None

    listing = gh(
        [
            "api",
            "orgs/rediacc/actions/secrets",
            "--paginate",
            "--jq",
            ".secrets[]|[.name,.visibility]|@tsv",
        ]
    )
    # `is None`, NOT falsy. `gh()` returns None when the call FAILED and stdout when it succeeded -- and an org with zero Actions secrets produces EMPTY stdout, which is falsy. So `if not listing` read "the migration finished" as "you lack an admin token", and the record became permanently unrefreshable at the exact moment the thing it tracks reached its terminal state.
    #
    # Not hypothetical: the org secrets were deleted 2026-09-05, this record was last refreshed 2026-09-02, and the gate has been red ever since with an error message blaming the operator's credentials. Measured 2026-09-09 with an admin:org token in hand: `gh api orgs/rediacc/actions/secrets --jq .total_count` returns 0 and exits 0.
    if listing is None:
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
        repos = gh(
            [
                "api",
                f"orgs/rediacc/actions/secrets/{name}/repositories",
                "--paginate",
                "--jq",
                ".repositories[].name",
            ]
        )
        scoped[name] = set((repos or "").split())

    data = {
        "_comment": [
            "Which secrets each repository can actually READ, not merely reference.",
            "Refresh: npm run check:ci-secret-reachability -- --refresh (needs an org-admin token).",
            "Written because Claude Review failed in account and renet for eleven days:",
            "both reference ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN, an org secret scoped to console alone.",
        ],
        "refreshed_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repos": {},
    }

    for repo_name, repo_root in repo_roots(root):
        names, _ = references(repo_root)
        gh_repo = f"rediacc/{'console' if repo_name == 'console' else repo_name}"
        repo_own = gh(
            ["api", f"repos/{gh_repo}/actions/secrets", "--paginate", "--jq", ".secrets[].name"]
        )
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
                    ok = gh_repo.rsplit("/", 1)[-1] in scoped.get(n, set())
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
                if dt.datetime.now(dt.UTC).date().isoformat() <= expiry:
                    print(
                        f"  KNOWN, waived until {expiry}: {repo_name}/{n}: {why}",
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


def staleness_problems(record, now):
    """Why this record may not be believed, if anything. Pure, so it is controllable.

    TWO WAYS A RECORD GOES WRONG, and the second is the one that shipped.

    AGE is the obvious one: an org allowlist changes without any commit here, so a
    record nobody refreshed eventually describes a world that moved on.

    PREDATING A KNOWN CHANGE is the other, and it looks fine. On 2026-09-05, 45 org
    secrets were deleted. This record was refreshed 2026-09-02 -- three days EARLIER
    -- and the 45-day age window kept it admissible until 2026-10-17. So the gate went
    on certifying six references as reachable, two of them wrong, straight past the
    event that made them wrong, and reported it as a clean green. A record is
    inadmissible the moment it predates a change it cannot have seen, however young.
    """
    out = []
    try:
        refreshed = dt.datetime.fromisoformat(record["refreshed_at"])
    except (KeyError, ValueError):
        return ["refreshed_at is missing or unparseable, so the record's age is unknown"]

    age = now - refreshed
    if age.days > MAX_BASELINE_AGE_DAYS:
        out.append(
            f"the record is {age.days} days old (limit {MAX_BASELINE_AGE_DAYS}). An org "
            f"allowlist can change without any commit here, so a stale record is the one "
            f"blind spot this gate has. Refresh it."
        )

    changed = record.get("topology_changed_at")
    if changed:
        try:
            when = dt.datetime.fromisoformat(changed)
        except ValueError:
            out.append(f"topology_changed_at ({changed!r}) is not a timestamp")
        else:
            if refreshed < when:
                out.append(
                    f"the record was refreshed {record['refreshed_at']} but the secret "
                    f"topology changed at {changed}, AFTER it. Its age is within the limit "
                    f"and it is still describing the world before that change, which is the "
                    f"shape a stale-but-young record takes. Refresh with `--refresh` (needs "
                    f"an admin:org token) before trusting a green."
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

    # The workflow_call exclusion, both directions. It is a way for a name to LEAVE the scan, so it is the one place this gate can be quietly narrowed to nothing: a bug that returned every name would make the whole check vacuous while still printing a reassuring count.
    reusable = (
        "on:\n  workflow_call:\n    secrets:\n      DECLARED_INPUT:\n"
        "        required: true\njobs:\n  a:\n    steps:\n"
        "      - run: echo ${{ secrets.DECLARED_INPUT }} ${{ secrets.NOT_DECLARED }}\n"
    )
    got = declared_secrets(reusable)
    if got != {"DECLARED_INPUT"}:
        return f"workflow_call declarations parsed as {sorted(got)}, want ['DECLARED_INPUT']"
    if declared_secrets("on:\n  push:\njobs: {}\n"):
        return "a workflow with no workflow_call reported declarations anyway"
    if declared_secrets("this: [is not: valid: yaml"):
        return "an unparseable workflow reported declarations instead of none"

    # Staleness, both directions. The predates-a-change rule is the one that would have caught the 2026-09-05 deletion three days after this record was written, so it gets a control that plants exactly that arrangement.
    now = dt.datetime(2026, 9, 6, tzinfo=dt.UTC)
    fresh = {"refreshed_at": "2026-09-06T00:00:00Z"}
    if staleness_problems(fresh, now):
        return "a record refreshed today was reported stale"
    old_rec = {"refreshed_at": "2026-01-01T00:00:00Z"}
    if not any("days old" in p for p in staleness_problems(old_rec, now)):
        return "a record far past the age limit was not reported stale"
    predates = {
        "refreshed_at": "2026-09-02T00:00:00Z",
        "topology_changed_at": "2026-09-05T00:00:00Z",
    }
    if not any("AFTER it" in p for p in staleness_problems(predates, now)):
        return "a record predating a known topology change was accepted anyway"
    after = {"refreshed_at": "2026-09-06T00:00:00Z", "topology_changed_at": "2026-09-05T00:00:00Z"}
    if staleness_problems(after, now):
        return "a record refreshed AFTER the topology change was reported stale anyway"
    if staleness_problems({"refreshed_at": "2026-09-06T00:00:00Z", "topology_changed_at": ""}, now):
        return "an empty topology_changed_at was treated as a change"
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

    # THE SCAN MUST COVER EVERY REPO THE RECORD KNOWS ABOUT, or refuse.
    #
    # Without this the gate silently under-scans. `actions/checkout` defaults to submodules:false, so in a job that does not ask for them private/account and private/renet are empty directories with no workflows -- and this gate would scan console alone, clear its MIN_REFERENCES floor on console's 42 references, and report GREEN while never looking at the two repos where the defect
    # it exists for actually lives.
    #
    # Measured before this guard existed: hiding both submodules' .github produced "40 secret reference(s) across 1 repo(s) are all reachable", exit 0. The gate had the exact defect it was written to catch.
    recorded = set(record.get("repos", {}))
    scanned = set(refs_by_repo)
    missing = sorted(recorded - scanned)
    if missing:
        print(
            "CANNOT SEE %d repo(s) the record covers: %s\n"
            "  Their workflows are absent, which almost always means the job checked out\n"
            "  without submodules (actions/checkout defaults to submodules:false).\n"
            "  Refusing a verdict rather than reporting on a subset -- a partial scan here\n"
            "  reads exactly like a clean one." % (len(missing), ", ".join(missing)),
            file=sys.stderr,
        )
        return 1

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

    problems.extend(staleness_problems(record, dt.datetime.now(dt.UTC)))

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
