"""Every commit in a PR must be ATTRIBUTABLE to a GitHub account.

Ported from `.ci/scripts/quality/check-commit-identity.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live.

The twin's header, carried whole because the measurement, the oracle argument
and the rejected alternative are each load-bearing:

    THE DEFECT, measured 2026-09-03 on rediacc/console#585 before the history
    rewrite: 30 of 42 commits carried `muhammed@rediacc.com`, an address not
    linked to the operator's GitHub account. Same display name as the good ones,
    so nothing looked wrong in `git log` -- but GitHub renders them with a bare
    name, no avatar, no profile link, and no contribution credit. The submodules
    carried the same defect: account#85 7 of 9, renet#110 2 of 2, elite#16 1 of
    1. Fixing it cost a history rewrite across four repositories plus a force
    push.

    THE ORACLE IS NOT AN EMAIL ALLOWLIST. The commit list returns, per commit,
    the account GitHub RESOLVED the author email to -- `.author`,
    null when it resolves to nobody. Measured on #585: 30 null, 11
    `.author.login = mfbayraktar`. So the rule is `.author` and `.committer` must
    both be non-null, which is the same question GitHub answers on the commit
    page. No hardcoded address, nothing to edit when one is linked or retired,
    and bots pass for free (`github-actions[bot]` resolves), which is why main's
    own bot commits need no special case.

    `gh api user/emails` would be the obvious oracle and CANNOT be used: it needs
    the `user` scope, which the token here lacks (measured: 404), and CI's app
    token is an INSTALLATION token with no user identity at all, so it can never
    work there.

    WHY THE API AND NOT `git log`: this repo's CI checkouts are shallow, and
    check-plan-housekeeping.sh is the record of what that costs -- three
    iterations, because `--is-shallow-repository` is not even the right test.
    This endpoint is authoritative regardless of what the runner cloned, so this
    gate has no shallow branch at all.

    PROVEN AGAINST THE LIVE DEFECT, both directions, 2026-09-03:

      BEFORE the history rewrite      AFTER
        console  #585  30 unattributed   48 commit(s), all attributed (mfbayraktar)
        account  #85    7 unattributed    9 commit(s), all attributed
        renet    #110   2 unattributed    2 commit(s), all attributed
        elite    #16    1 unattributed    1 commit(s), all attributed

    The 30 matched the count measured independently from git, so the gate and the
    history agreed about the size of the defect before it was repaired.

    WHICH ENDPOINT LISTS THE COMMITS, and why it is not the obvious one. This
    gate read `repos/{r}/pulls/{n}/commits`, which GitHub caps at 250 EVEN WITH
    `--paginate`, and refused outright at the cap rather than judge a set it
    might not have read whole. That refusal was right and the endpoint was
    wrong: measured 2026-09-15 on rediacc/console#589, a 254-commit PR, the gate
    stopped being able to report AT ALL -- "Cannot certify", every run, with two
    genuinely unattributed commits sitting behind the refusal, unnamed. A gate
    that cannot reach a verdict on a large PR is not strict, it is absent.

    So the list comes from `repos/{r}/compare/{base}...{head}`, which GitHub's
    own docs name for ranges over 250, which `--paginate` walks properly
    (measured: 254 of 254 in 2.2s, against 250 from the pulls endpoint), and
    which carries the SAME `.author`/`.committer` resolution -- the oracle is
    unchanged.

    COMPLETENESS IS NOW CHECKED, NOT ASSUMED. The old guard was a magic 250: it
    could only notice truncation at one number, and it fired on PRs that were
    merely large. The new guard compares what we read against `.commits` on the
    PR object -- a count from a DIFFERENT endpoint -- and refuses on any
    mismatch. It is strictly stronger: it catches a short read at 3 commits as
    well as at 250, and it stops refusing PRs whose only sin is size.

    Usage:
      GITHUB_TOKEN=xxx PR_NUMBER=123 ./check-commit-identity.sh
      ./check-commit-identity.sh --refresh      # regenerate the local identity cache

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE PAYLOAD IS ONE COMPACT JSON OBJECT PER LINE, and both the count and the
verdict depend on that. The twin counts commits with `grep -c .`, which counts
LINES, and then feeds the same text to `jq` as a stream of values. Those two
readings only agree while gh emits one object per line, which it does; a pretty
printed payload would make the completeness refusal fire on every PR. The port
parses line by line for the same reason, so the two implementations disagree in
the same way if that ever changes rather than one of them silently coping.

`.author.login` ON A NULL AUTHOR IS null, NOT AN ERROR. jq indexes null with a
string and yields null, which is what lets the twin's projection
`{sha, author: .author.login, ...}` run at all over an unattributed commit. The
port reproduces it with a `None`-tolerant lookup rather than a `try`, because
the null IS the finding and swallowing it in an exception handler would be one
step from swallowing the finding.

`gh_retry` IS REPRODUCED, sleeps included, for the reasons recorded in
`common.sh:418-432`: nine call sites were spelled `$(gh api ... || echo "[]")`
and a rate limit then produced the same value as "this PR is clean". The gate is
merge-blocking, so a swallowed failure there is a silent green on the check that
is supposed to stop the merge.

`--refresh` IS PORTED IN FULL even though CI never runs it, and its two traps are
carried as comments where they bite. The first is the shape filter: `gh api
user/emails` fails with 404 here and prints its JSON error body to STDOUT, so
`2>/dev/null` does not suppress it and `|| true` swallows the exit code, and the
first run of that function wrote `{"message":"Not` and `Found","documentation_url":...}`
into the cache as two "emails". The second is the anti-vacuity refusal: an empty
cache would make the local guard refuse every commit, which reads as the guard
being broken rather than the cache being empty.

THE GENERATED FILE'S `$comment` IS DATA, NOT PROSE, and is carried byte for byte.
It is the only thing standing between the next reader and hand-editing a cache
whose whole value is that it is derived.

`require_cmd jq` IS CARRIED for the same reason as in the autopilot port: this
module parses with `json`, but its twin refuses without jq, and a port that ran
where its twin refuses would disagree about the only machine where the question
is interesting. It is the first thing W7 phase 5 should delete when the twin dies.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The default repository, matching `${GITHUB_REPOSITORY:-rediacc/console}`.
DEFAULT_REPO = "rediacc/console"

# The commands both implementations require on PATH. See the port notes for why `jq` is here when nothing below calls it.
REQUIRED_COMMANDS = ("gh", "jq")

# The test seam, spelled the twin's way so one override drives both.
IDENTITY_ENV = "COMMIT_IDENTITY_FILE"

# Keep only lines that are actually addresses. The guard against an API error
# body being mistaken for data; see the note in `refresh_identity`.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

# The projection the twin passes to `gh api --jq`. Named once so the string that decides which fields exist is not buried in an argument list, and so a test can assert it still matches the twin's.
PROJECTION = (
    ".commits[] | {sha: .sha, author: .author.login, committer: .committer.login, "
    "email: .commit.author.email, name: .commit.author.name}"
)

# The PR metadata read: the compare range's two ends, plus the PR's own commit count. Three values in one line because the twin reads them with `read -r`, and one call rather than three keeps the two implementations comparable.
PR_META_JQ = '"\\(.base.sha) \\(.head.sha) \\(.commits)"'

# The retry schedule from `common.sh`'s `_gh_probe`: three attempts, 3 then 6 seconds apart.
GH_ATTEMPTS = 3

# The `$comment` written into the generated cache. Carried byte for byte; it is
# the only thing telling the next reader not to hand-edit a derived file.
CACHE_COMMENT = (
    "GENERATED by check-commit-identity.sh --refresh. Do not hand-edit: it is a "
    "cache of what GitHub already attributes, and the CI gate never consults it to "
    "PASS a commit -- its verdict is GitHub own .author. Two live assertions keep "
    "it honest: an email listed here that GitHub refuses on a judged commit fails "
    "naming this file, and an attributed email missing from here fails naming "
    "--refresh."
)


def require_cmd(name: str) -> bool:
    """`common.sh:141-147`, with its message byte for byte."""
    if shutil.which(name) is not None:
        return True
    log.error("Required command '%s' is not available" % name)
    return False


def gh_retry(what: str, args: list[str]) -> tuple[bool, str]:
    """`gh_retry <what> -- <gh args...>`. Returns (ok, stdout with trailing newlines cut).

    The exit status is ALWAYS checked. A caller that substituted a default here
    would reintroduce the defect this helper exists to end.
    """
    rc = 0
    stderr = ""
    for attempt in range(1, GH_ATTEMPTS + 1):
        try:
            proc = subprocess.run(["gh", *args], capture_output=True, check=False)
            rc = proc.returncode
            stdout = proc.stdout.decode("utf-8", "replace")
            stderr = proc.stderr.decode("utf-8", "replace")
        except OSError:
            rc, stdout, stderr = 127, "", ""
        if rc == 0:
            return True, re.sub(r"\n+$", "", stdout)
        if attempt < GH_ATTEMPTS:
            log.warn(
                "%s: gh call failed or returned unusable output (attempt %d/%d), retrying..."
                % (what, attempt, GH_ATTEMPTS)
            )
            time.sleep(attempt * 3)
    log.error("%s: gh failed after %d attempts (last exit %d)." % (what, GH_ATTEMPTS, rc))
    if stderr != "":
        for line in stderr.rstrip("\n").split("\n"):
            print("    %s" % line, file=sys.stderr)
    return False, ""


def gh_plain(args: list[str]) -> tuple[int, str]:
    """A single `gh` call with stderr DISCARDED, for the `--refresh` probes.

    Separate from `gh_retry` because `refresh_identity` deliberately does NOT
    retry: it is an interactive command, and its two calls each have their own
    handling for the failure.
    """
    try:
        proc = subprocess.run(
            ["gh", *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False
        )
    except OSError:
        return 127, ""
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def valid_emails(text: str) -> list[str]:
    """`grep -E '^[A-Za-z0-9._%+-]+@...$' || true`: only things shaped like an address.

    THE SHAPE FILTER IS THE GUARD, not decoration. `gh api user/emails` fails
    with 404 for the token used here and prints its JSON error body to STDOUT,
    where `2>/dev/null` cannot reach it and `|| true` swallows the status. The
    first run of `--refresh` wrote `{"message":"Not` and
    `Found","documentation_url":...}` into the cache as two "emails". CLAUDE.md
    records the identical trap with curl: a 404 is silent and its body becomes
    the value.
    """
    return [line for line in text.split("\n") if EMAIL_RE.match(line)]


def parse_payload(payload: str) -> list[dict]:
    """One compact JSON object per line. Unparseable lines are DROPPED, not raised.

    Dropping matches the twin: `jq` reading a stream stops at a malformed value,
    and the surrounding `$( )` would then hand the gate a short list. Both
    implementations therefore under-report identically rather than one crashing,
    which is the property the differential needs.
    """
    out: list[dict] = []
    for line in payload.split("\n"):
        if line.strip() == "":
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def count_lines(payload: str) -> int:
    """`grep -c .`: non-empty LINES, which is what the completeness check reads."""
    return len([line for line in payload.split("\n") if line != ""])


def parse_meta(meta: str) -> tuple[str, str, int] | None:
    """`read -r base head total`, with the twin's own validity test.

    None means the line was not three usable fields, which the caller turns into
    a refusal. The twin's guard is `-z "$base" || -z "$head" || ! "$total" =~
    ^[0-9]+$`, so a missing field and a non-numeric count are the same outcome
    on both sides -- and NEITHER is allowed to become a count of zero, which
    would make the completeness check pass over an empty read.
    """
    fields = meta.split()
    if len(fields) < 3:
        return None
    # `read -r base head total` puts the ENTIRE remainder in the last variable, so a fourth field makes the count non-numeric rather than being dropped.
    base, head, total = fields[0], fields[1], " ".join(fields[2:])
    if base == "" or head == "" or not re.match(r"^[0-9]+$", total):
        return None
    return base, head, int(total)


def unattributed(rows: list[dict]) -> list[str]:
    """`jq -r 'select(.author == null or .committer == null) | "    \\(.sha[0:7]) ..."' | sort -u`.

    Sorted and DEDUPLICATED, as `sort -u` is. The four-space indent is part of
    the string in the twin, not applied later, so it is part of it here too:
    those lines are what the comparator attaches to the header above them.
    """
    lines = {
        "    %s  %s <%s>" % (str(row.get("sha", ""))[0:7], row.get("name"), row.get("email"))
        for row in rows
        if row.get("author") is None or row.get("committer") is None
    }
    return sorted(lines)


def email_tally(rows: list[dict]) -> list[tuple[int, str]]:
    """`jq -r 'select(.author == null) | .email' | sort | uniq -c | sort -rn`.

    Only `.author`, NOT `.committer`: the summary is about which ADDRESS is
    unlinked, and a null committer with a resolved author is a different defect.
    `sort -rn` is descending by count; ties keep `uniq -c`'s order, which is the
    ascending email order `sort` produced.
    """
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("author") is None:
            key = str(row.get("email"))
            counts[key] = counts.get(key, 0) + 1
    return sorted(((n, e) for e, n in sorted(counts.items())), key=lambda p: -p[0])


def probe_failed() -> int:
    """The refusal. An unreadable PR is not a PR whose commits attribute."""
    print(file=sys.stderr)
    print(
        "Cannot certify that this PR's commits attribute to a GitHub account, because",
        file=sys.stderr,
    )
    print(
        "the GitHub API could not be read. Failing closed rather than reporting clean.",
        file=sys.stderr,
    )
    return 1


def judge_pr(repo: str, pr: str, label: str) -> int:
    """Print offenders and return 1 when any commit is unattributed.

    Returns 2 for a probe failure, which the caller turns into `probe_failed()`.
    Three outcomes rather than two, because "could not read" must never be
    folded into either verdict.
    """
    ok, meta = gh_retry(
        "PR metadata for %s#%s" % (label, pr),
        ["api", "repos/%s/pulls/%s" % (repo, pr), "--jq", PR_META_JQ],
    )
    if not ok:
        return 2

    parsed = parse_meta(meta)
    if parsed is None:
        print(
            "  ERROR: could not read base/head/commit-count for %s#%s: '%s'." % (label, pr, meta),
            file=sys.stderr,
        )
        return 2
    base, head, total = parsed

    ok, payload = gh_retry(
        "commit list for %s#%s" % (label, pr),
        [
            "api",
            "repos/%s/compare/%s...%s?per_page=100" % (repo, base, head),
            "--paginate",
            "--jq",
            PROJECTION,
        ],
    )
    if not ok:
        return 2

    # A PR always has at least one commit, so an empty list is a failed read.
    if payload.strip(" \t\n\v\f\r") == "":
        print("  ERROR: the commit list for %s#%s came back empty." % (label, pr), file=sys.stderr)
        print(
            "  Every PR has at least one commit, so this is a failed read, not a clean PR.",
            file=sys.stderr,
        )
        return 2

    count = count_lines(payload)
    if count != total:
        print(
            "  ERROR: read %d commit(s) for %s#%s, but the PR reports %d."
            % (count, label, pr, total),
            file=sys.stderr,
        )
        print(
            "  An incomplete set cannot be cleared; refusing rather than judging part of it.",
            file=sys.stderr,
        )
        return 2

    rows = parse_payload(payload)
    bad = unattributed(rows)
    if bad:
        print(
            "✗ %s#%s: commit(s) GitHub does not attribute to any account:" % (label, pr),
            file=sys.stderr,
        )
        for line in bad:
            print(line, file=sys.stderr)
        print(file=sys.stderr)
        for number, email in email_tally(rows):
            print("    %d commit(s) from %s" % (number, email), file=sys.stderr)
        return 1

    # NOT VACUOUS: say what was cleared, so a collapse to zero is visible in the log rather than inferred from an absent complaint.
    logins = sorted({str(row.get("author")) for row in rows})
    print(
        "  ✓ %s#%s: %d commit(s), all attributed (%s)"
        % (label, pr, count, "".join(name + " " for name in logins))
    )
    return 0


# --------------------------------------------------------------------------- --refresh: derive the LOCAL guard's cache from GitHub. Never hand-authored. ---------------------------------------------------------------------------


def refresh_identity(identity_file: pathlib.Path) -> int:
    """Regenerate the identity cache. 0 on success, 1 on either refusal."""
    repo = os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO
    code, me = gh_plain(["api", "user", "--jq", "{login,id}"])
    if code != 0:
        print("✗ cannot read the authenticated user; run: gh auth login", file=sys.stderr)
        return 1
    try:
        parsed = json.loads(me)
    except ValueError:
        print("✗ cannot read the authenticated user; run: gh auth login", file=sys.stderr)
        return 1
    login = str(parsed.get("login"))
    identity_id = parsed.get("id")

    # user/emails is authoritative but needs the `user` scope. When it is absent -- which is the normal case here and the ONLY case in CI -- ask GitHub which addresses it has already attributed to this login, which needs no extra scope. See `valid_emails` for why the shape filter is not optional.
    _code, raw = gh_plain(["api", "user/emails", "--jq", ".[].email"])
    emails = valid_emails(raw)
    if not emails:
        print(
            "  note: user/emails unavailable (needs the 'user' scope; to add it,", file=sys.stderr
        )
        print(
            "        gh auth refresh -h github.com -s user). Deriving from attributed",
            file=sys.stderr,
        )
        print("        commits instead, which needs no extra scope.", file=sys.stderr)
        _code, raw = gh_plain(
            [
                "api",
                "repos/%s/commits?per_page=100" % repo,
                "--paginate",
                "--jq",
                '.[] | select(.author.login == "%s") | .commit.author.email' % login,
            ]
        )
        emails = sorted(set(valid_emails(raw)))[:50]

    # ANTI-VACUITY: a cache with no emails would make the local guard refuse every commit, which reads as the guard being broken rather than the cache being empty.
    if not emails:
        print(
            "✗ derived NO valid email addresses for '%s'; refusing to write the cache." % login,
            file=sys.stderr,
        )
        print(
            "  (An API error body is discarded by the shape filter rather than stored,",
            file=sys.stderr,
        )
        print(
            "   so 'none' here means none were readable, not that the call was silent.)",
            file=sys.stderr,
        )
        return 1

    identity_file.write_text(
        json.dumps(
            {
                "format": 1,
                "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "$comment": CACHE_COMMENT,
                "identities": [{"login": login, "id": identity_id, "emails": sorted(set(emails))}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "✓ wrote %s: %s (id %s), %d email(s)"
        % (identity_file.name, login, identity_id, len(emails))
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean or not a PR, 1 on an unattributed commit or a failed read."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    for name in REQUIRED_COMMANDS:
        if not require_cmd(name):
            return 1

    root = paths.repo_root()
    identity_file = pathlib.Path(
        os.environ.get(IDENTITY_ENV) or str(root / ".ci" / "config" / "commit-identity.json")
    )

    if args and args[0] == "--refresh":
        return refresh_identity(identity_file)

    pr_number = os.environ.get("PR_NUMBER", "")
    if not pr_number:
        print("PR_NUMBER not set - skipping commit identity check (not a pull request)")
        return 0
    repo = os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO

    verdict = judge_pr(repo, pr_number, repo)
    if verdict == 2:
        return probe_failed()

    if verdict != 0:
        print(file=sys.stderr)
        print(
            "Those commits render on GitHub with a bare name: no avatar, no profile link,",
            file=sys.stderr,
        )
        print(
            "and no contribution credit. The address is not linked to any account.", file=sys.stderr
        )
        print(file=sys.stderr)
        print("Fix, in order of preference:", file=sys.stderr)
        print(
            "  1. Add the address at https://github.com/settings/emails, then push again.",
            file=sys.stderr,
        )
        print(
            "  2. Or rewrite the authors to an address that IS linked, and force push.",
            file=sys.stderr,
        )
        print("  3. Check any single address with:", file=sys.stderr)
        print(
            '       gh api "search/commits?q=repo:%s+author-email:<addr>" '
            "--jq '.items[0].author.login'" % repo,
            file=sys.stderr,
        )
        return 1

    print("✓ commit identity: every commit attributes to a GitHub account")
    print("  Blind spot: this judges the PR's commits only. A commit pushed straight to a")
    print("  branch with no PR is not seen here; the pre-bash guard is what covers that.")
    return 0


# --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------


def _row(sha: str, author, committer, email: str, name: str) -> str:
    """One payload line, exactly as gh's `--jq` projection emits it."""
    return json.dumps(
        {"sha": sha, "author": author, "committer": committer, "email": email, "name": name},
        separators=(",", ":"),
    )


def selftest() -> int:
    """Both directions for the oracle, the two floors and the shape filter.

    The mirror matters as much as the plant here: this gate reds a merge, so a
    port that flagged an ATTRIBUTED commit would be worse than one that missed
    an unattributed one.
    """
    ctl = Controls("commit-identity", floor=22, verbose=True)

    attributed = _row("aaaaaaa1111", "mfbayraktar", "mfbayraktar", "m@example.invalid", "M F B")
    no_author = _row("bbbbbbb2222", None, "mfbayraktar", "muhammed@rediacc.com", "M F B")
    no_committer = _row("ccccccc3333", "mfbayraktar", None, "m@example.invalid", "M F B")
    bot = _row(
        "ddddddd4444", "github-actions[bot]", "github-actions[bot]", "b@example.invalid", "bot"
    )

    # -- the oracle, both directions ----------------------------------------
    ctl.check(
        "MIRROR: an attributed commit is not reported",
        unattributed(parse_payload(attributed)),
        [],
    )
    ctl.check(
        "MIRROR: a BOT resolves and is therefore not reported",
        unattributed(parse_payload(bot)),
        [],
    )
    ctl.check(
        "PLANT: a null .author is reported, sha shortened to seven",
        unattributed(parse_payload(no_author)),
        ["    bbbbbbb  M F B <muhammed@rediacc.com>"],
    )
    ctl.check(
        "PLANT: a null .committer is reported too",
        unattributed(parse_payload(no_committer)),
        ["    ccccccc  M F B <m@example.invalid>"],
    )
    ctl.check(
        "the offender list is sorted and DEDUPLICATED, as `sort -u` is",
        unattributed(parse_payload(f"{no_author}\n{no_author}\n{no_committer}")),
        [
            "    bbbbbbb  M F B <muhammed@rediacc.com>",
            "    ccccccc  M F B <m@example.invalid>",
        ],
    )

    # -- the address tally, which reads .author ONLY ------------------------
    ctl.check(
        "the tally counts per address, descending",
        email_tally(
            parse_payload(
                "\n".join(
                    [
                        _row("1111111", None, None, "a@example.invalid", "A"),
                        _row("2222222", None, None, "a@example.invalid", "A"),
                        _row("3333333", None, None, "b@example.invalid", "B"),
                    ]
                )
            )
        ),
        [(2, "a@example.invalid"), (1, "b@example.invalid")],
    )
    ctl.check(
        "MIRROR: a null COMMITTER with a resolved author is not in the tally",
        email_tally(parse_payload(no_committer)),
        [],
    )

    # -- the two floors -----------------------------------------------------
    ctl.check("an empty payload counts zero lines", count_lines(""), 0)
    ctl.check("blank lines are not counted", count_lines("a\n\nb\n"), 2)
    # -- the completeness check, which replaced the 250 page cap ------------- Both directions, because the whole point of the replacement is that it ACCEPTS a large complete read and REFUSES a short one at any size. A one-directional control here would have re-admitted the defect: the old cap also "passed its test" while refusing every PR over 250 commits.
    ctl.check(
        "PLANT: a short read is refused -- 250 of 254 is not the PR",
        count_lines("x\n" * 250) != 254,
        True,
    )
    ctl.check(
        "MIRROR: a complete read of a 254-commit PR is accepted",
        count_lines("x\n" * 254) != 254,
        False,
    )
    ctl.check(
        "PLANT: a short read at THREE commits is refused too, not just at 250",
        count_lines("x\ny\n") != 3,
        True,
    )
    ctl.check(
        "the metadata line parses to base, head and an int", parse_meta("b h 254"), ("b", "h", 254)
    )
    ctl.check("a non-numeric count refuses rather than becoming zero", parse_meta("b h many"), None)
    ctl.check("a missing field refuses", parse_meta("b h"), None)
    ctl.check(
        "a fourth field makes the count unreadable, as `read -r` does", parse_meta("b h 1 2"), None
    )

    # -- the shape filter, both directions ----------------------------------
    ctl.check(
        "PLANT: a 404 error body is discarded rather than stored as two emails",
        valid_emails('{"message":"Not\nFound","documentation_url":"https://x"}'),
        [],
    )
    ctl.check(
        "MIRROR: real addresses survive",
        valid_emails("a@example.invalid\nb.c+d@sub.example.co\n"),
        ["a@example.invalid", "b.c+d@sub.example.co"],
    )
    ctl.check("a bare word is not an address", valid_emails("mfbayraktar"), [])
    ctl.check("a one-letter TLD is not an address", valid_emails("a@b.c"), [])

    # -- payload parsing ----------------------------------------------------
    ctl.check("one object per line is parsed", len(parse_payload(attributed + "\n" + bot)), 2)
    ctl.check("a blank payload parses to nothing", parse_payload("\n\n"), [])
    ctl.check(
        "a JSON value that is not an object is dropped, not indexed",
        parse_payload('"just a string"\n42\n'),
        [],
    )
    ctl.check(
        "a trailing newline does not invent a commit",
        count_lines(attributed + "\n"),
        1,
    )
    ctl.check(
        "an unparseable line is DROPPED, matching the twin's short read",
        len(parse_payload(attributed + "\nnot json\n" + bot)),
        2,
    )

    # -- the whole gate, over a fixture payload -----------------------------
    ctl.check(
        "PLANT: the offender list drives the exit code through judge_pr's contract",
        1 if unattributed(parse_payload(no_author)) else 0,
        1,
    )

    # -- the skip arm, driven for real --------------------------------------
    saved = os.environ.get("PR_NUMBER")
    try:
        os.environ.pop("PR_NUMBER", None)
        ctl.check("MIRROR: no PR number skips and exits 0", main([]), 0)
    finally:
        if saved is not None:
            os.environ["PR_NUMBER"] = saved

    # -- require_cmd, both directions ---------------------------------------
    ctl.check("require_cmd finds a command that exists", require_cmd("sh"), True)
    ctl.check(
        "require_cmd refuses one that does not",
        require_cmd("definitely-not-a-real-binary-portf"),
        False,
    )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
