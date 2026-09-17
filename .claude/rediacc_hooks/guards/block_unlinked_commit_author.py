"""Refuse a `git commit` whose author email GitHub does not link to an account.

WHAT IT COST WHEN NOTHING CHECKED. On 2026-09-03, 30 of 42 commits on branch 0903-1 carried `muhammed@rediacc.com` -- same DISPLAY NAME as the good ones, so `git log` looked uniform, while GitHub rendered them with a bare name, no avatar, no profile link and no contribution credit. The submodules had it too (7 of 9, 2 of 2, 1 of 1). Fixing it took a history rewrite across four
repositories and a force push.

THE CONFIG WAS NOT THE CAUSE, and that decides the whole design. Measured in that checkout: no local user.email at all, and `git config --show-origin --get-all user.email` named exactly one source, the global file, with the CORRECT address.
So those 30 came from an override at commit time -- `-c user.email=`, `--author=`,
GIT_AUTHOR_EMAIL, or a different HOME. A guard that only read `git config` would have watched all 30 go past.

WHY THIS DOES NOT PATTERN-MATCH THE COMMAND TEXT. The author identity is not IN
the command; it comes from git's ident resolution. That is why this guard cannot
repeat the failure recorded in block-commit-meta.sh's header, where a phrase check fired on prose and even on `grep -rn 'co-authored-by' docs/` -- its own audit. A command that merely MENTIONS an address is not a commit and is never scanned here.

`git var GIT_AUTHOR_IDENT` implements git's entire precedence chain except
`--author=`, so this does not reimplement it. Verified:
    git var GIT_AUTHOR_IDENT                          -> the global address
    git -c user.email=x@y.z var GIT_AUTHOR_IDENT      -> x@y.z
    GIT_AUTHOR_EMAIL=e@e.e git var GIT_AUTHOR_IDENT   -> e@e.e

The allowed set is .ci/config/commit-identity.json, GENERATED from GitHub by `.ci/scripts/quality/check-commit-identity.sh --refresh` and never hand-authored. It cannot be used to smuggle a bad address past CI: the CI gate never consults it to PASS a commit -- its verdict is GitHub's own `.author`.

=============================================================================
PORT NOTES
=============================================================================

A NAME COLLISION WORTH STATING. The bash calls its captured environment overrides `ENVS`. In this package `ENVS` is the differential harness's key for the environments a port is judged in, so the local variable is spelled `env_overrides` here. Same value, different name, and the rename is the only thing that changed.

`set -uo pipefail` HAS NO PORT. It makes an unset variable fatal and a pipeline inherit its first failure, both of which are properties of the shell rather than of this guard, and neither has a Python analogue that would change any answer. Recorded rather than dropped, because its absence in a port is the kind of detail a later reader reasonably wonders about.

THE TWO SEDS ARE ONE EXPRESSION LIST APPLIED IN ORDER, which matters for
`OVERRIDE`: `sed -nE 's/A/\\1/p; s/B/\\1/p'` runs A over the line, prints if it
substituted, and then runs B over WHAT A LEFT. `head -1` after it takes the first line either printed. Written out here rather than collapsed into one regex, because collapsing them would be a different program that happens to agree on today's inputs.
"""

import json
import os
import pathlib
import re
import subprocess

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-unlinked-commit-author.sh"
ORDER = 5

# The `--author=` arm is the one whose two corrections this file's header
# records: read from the scan it was invisible, read from the raw command whole it refused its own introducing commit. Dropping it means the override that produced the 2026-09-03 rewrite is not looked at.
DEFECT = ("if override:", "if False:")

COMMIT_AT_COMMAND_POS = hookio.rx(
    r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+commit([{S}]|$)"
)

C_FLAG = hookio.rx(r'\-c[{S}]+"?user\.email=[^"{S}]+')
ENV_FLAG = hookio.rx(r"(GIT_AUTHOR_EMAIL|GIT_COMMITTER_EMAIL|EMAIL)=[^{S}]+")
AUTHOR_FLAG = (
    r"\-\-author[= ]+(\"[^\"]*<[^>]+>\"|'[^']*<[^>]+>'|[^"
    + hookio.SPACE
    + r"]+@[^"
    + hookio.SPACE
    + r"]+)"
)
IDENT_EMAIL = re.compile(r".*<([^>]+)>.*")

EDGE_CASES = [
    ("a plain commit", 'git commit -m "feat(x): a change"'),
    # The three override shapes the 2026-09-03 finding names, none of which a `git config` read would have seen.
    ("a -c user.email override", 'git -c user.email=nobody@example.invalid commit -m "x"'),
    ("a GIT_AUTHOR_EMAIL override", 'GIT_AUTHOR_EMAIL=nobody@example.invalid git commit -m "x"'),
    ("an --author override", 'git commit --author="Nobody <nobody@example.invalid>" -m "x"'),
    (
        "an --author override, single quoted",
        "git commit --author='Nobody <nobody@example.invalid>' -m 'x'",
    ),
    # The false positive that this guard's own first commit produced: the
    # message EXPLAINING --author= must not be read as one.
    ("--author named inside the message", 'git commit -m "explain --author=a@b.c in prose"'),
    ("--author named inside a single-quoted message", "git commit -m 'explain --author=a@b.c'"),
    ("a -F message file hides its body", "git commit -F msg.txt"),
    # Not a commit at all.
    ("prose about an address", "echo 'muhammed@rediacc.com is the wrong one'"),
    ("git tag is deliberately out of scope", 'git tag -m "x" v1'),
    ("gh pr create is deliberately out of scope", "gh pr create --draft --fill"),
    # A submodule of this tree IS judged; an independent checkout is not.
    ("a commit in a submodule", 'cd private/renet && git commit -m "x"'),
    ("a commit in an independent checkout", 'cd /tmp && git commit -m "x"'),
]


def _sed_ident(text):
    """`sed -nE 's/.*<([^>]+)>.*/\\1/p'` -- print only the lines that matched."""
    out = []
    records, _ = hookio._records(text)
    for record in records:
        m = IDENT_EMAIL.fullmatch(record)
        if m:
            out.append(m.group(1))
    return hookio._command_substitution(hookio._grep_out(out))


def _resolve(which, target, cflags, env_overrides):
    """`env <overrides> git -C <target> <-c flags> var <which>`, then the sed.

    A command substitution, so a git failure is an empty answer rather than an error: the caller's next test is `[ -z "$AUTHOR_EMAIL" ]`, which is the "git cannot resolve an author identity" refusal.
    """
    env = dict(os.environ)
    for pair in env_overrides:
        key, _, value = pair.partition("=")
        env[key] = value
    argv = ["git", "-C", target]
    for kv in cflags:
        argv.extend(["-c", kv])
    argv.extend(["var", which])
    try:
        proc = subprocess.run(argv, capture_output=True, check=False, env=env)
    except OSError:
        return ""
    return _sed_ident(proc.stdout.decode("utf-8", "surrogateescape"))


def _allowed(email, identity):
    """The jq filter, spelled out.

    `[ .identities[] | .emails[], "\\(.id)+\\(.login)@users.noreply.github.com",
       "\\(.login)@users.noreply.github.com" ] | index($e) != null`

    The two synthesised addresses are GitHub's noreply forms, which attribute correctly and are therefore allowed without appearing in `emails`.
    """
    pool = []
    identities = identity.get("identities") if isinstance(identity, dict) else None
    for entry in identities if isinstance(identities, list) else []:
        if not isinstance(entry, dict):
            continue
        emails = entry.get("emails")
        if isinstance(emails, list):
            pool.extend(emails)
        pool.append("%s+%s@users.noreply.github.com" % (entry.get("id"), entry.get("login")))
        pool.append("%s@users.noreply.github.com" % entry.get("login"))
    return email in pool


def run(ev):
    state = shellscan.hook_init(ev.payload)
    if state is None:
        return hookio.ALLOW
    cmd, scan = state

    # Is this a commit at all? Command position, so prose about committing is not. Deliberately NOT `git tag` and NOT `gh pr create`: a tag writes a tagger and a PR body has no author email, so widening here would only invite false positives.
    if not hookio.grep_q(COMMIT_AT_COMMAND_POS, scan):
        return hookio.ALLOW

    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    if root == "":
        return hookio.ALLOW

    # WHICH REPO IS JUDGED, and this deliberately DIFFERS from block-untagged-commit.sh. That guard exits on ANY foreign root because epics are console's business alone. Three submodules carried this exact defect, so a commit into one of them IS in
    # scope here; only a repo outside this tree is somebody else's identity policy.
    target = shellscan.target_root(scan, root)
    if target != "":
        if not hookio.case_glob(target, "%s/*" % root):
            return hookio.ALLOW  # an independent checkout -- not this guard's business
    else:
        target = root

    identity_file = ev.env("COMMIT_IDENTITY_FILE") or "%s/.ci/config/commit-identity.json" % root
    if not os.access(identity_file, os.R_OK):
        ev.warn(
            "BLOCKED: cannot read %s, so this commit's author cannot be checked." % identity_file
        )
        ev.warn("")
        ev.warn("It is a tracked file; inside this tree its absence means a broken checkout.")
        ev.warn("Regenerate it from GitHub:")
        ev.warn("    .ci/scripts/quality/check-commit-identity.sh --refresh")
        return hookio.DENY

    # Collect overrides from the region BEFORE the `commit` verb. Structural, because git requires `-c` there, and it keeps a `-m` message body out of the parse.
    # `${CMD%%commit*}` is the SHORTEST prefix, so a later `commit` inside a
    # message cannot widen the region.
    pre = cmd.split("commit", 1)[0] if "commit" in cmd else cmd
    cflags = [
        hookio.sed_sub(hookio.rx(r'^-c[{S}]+"?'), "", match).rstrip("\n")
        for match in hookio.grep_o(C_FLAG, pre)
    ]
    cflags = [kv for kv in cflags if kv != ""]
    env_overrides = [kv for kv in hookio.grep_o(ENV_FLAG, pre) if kv != ""]

    author_email = _resolve("GIT_AUTHOR_IDENT", target, cflags, env_overrides)
    committer_email = _resolve("GIT_COMMITTER_IDENT", target, cflags, env_overrides)

    # --author= wins for the author field, and getting at it took two corrections.
    #
    # It must be read from the RAW command, not the scan: git's form is
    # `--author="Name <a@b>"`, and the scan strips quoted spans, so the value was gone
    # before the match ran -- leaving `--author=` with nothing after it, and the guard
    # permitting the exact override it exists to catch.
    #
    # But reading the raw command whole was ALSO wrong, and this file's own first commit
    # proved it: the message explaining `--author=` contained the string, so the guard
    # refused the commit that introduced it. That is precisely the failure recorded in block-commit-meta.sh's header, where a phrase check blocked its own audit -- and "accept the false positive, it is loud" was the wrong call. A guard that cannot be described in a commit message is a guard people route around.
    #
    # So the MESSAGE VALUE is removed first, then `--author` is looked for in what is left. git takes the message as the argument to -m/--message, so a mention inside it is prose by construction, while a real `--author` sits outside it.
    deauthored = cmd
    deauthored = hookio.sed_sub(r'(-m|--message)[= ]+"[^"]*"', r"\1 MSG", deauthored)
    deauthored = hookio.sed_sub(r"(-m|--message)[= ]+'[^']*'", r"\1 MSG", deauthored)
    deauthored = hookio.sed_sub(hookio.rx(r"(-F|--file)[= ]+[^{S}]+"), r"\1 FILE", deauthored)
    override = ""
    first = hookio.grep_o(AUTHOR_FLAG, deauthored)[:1]
    if first:
        printed = []
        for record in first:
            line = record
            m = IDENT_EMAIL.fullmatch(line)
            if m:
                printed.append(m.group(1))
                line = m.group(1)
            m2 = re.fullmatch(r".*[= ]+([^ \"'<]+@[^ \"'>]+)$", line)
            if m2:
                printed.append(m2.group(1))
        override = printed[0] if printed else ""
    if override:
        author_email = override

    if author_email == "":
        ev.warn("BLOCKED: git cannot resolve an author identity for this commit.")
        ev.warn("")
        ev.warn("It would be attributed to a guessed user@hostname, which is the same defect")
        ev.warn("in a worse costume. Set one:")
        ev.warn('    git config --global user.name  "Your Name"')
        ev.warn('    git config --global user.email "you@example.com"')
        return hookio.DENY

    try:
        identity = json.loads(pathlib.Path(identity_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # `jq -e ... >/dev/null 2>&1` on an unreadable or malformed file exits non-zero, which the bash reads as "not allowed".
        identity = None

    for field, email in (("author", author_email), ("committer", committer_email)):
        if email == "":
            continue
        # Bot addresses attribute on GitHub and are never this guard's business.
        if hookio.case_glob(email, "*[bot]@users.noreply.github.com"):
            continue
        if _allowed(email, identity if isinstance(identity, dict) else {}):
            continue

        ev.warn("BLOCKED: the %s email <%s> is not linked to a GitHub account." % (field, email))
        ev.warn("")
        ev.warn("GitHub renders such commits with a bare name: no avatar, no profile link,")
        ev.warn("no contribution credit. On 2026-09-03 this cost a history rewrite across")
        ev.warn("four repositories after 30 commits landed that way unnoticed.")
        ev.warn("")
        ev.warn("Where it came from:")
        origins = hookio.git_out(
            ["-C", target, "config", "--show-origin", "--get-all", "user.email"]
        )
        # NO ORIGINS MEANS NO LINE AT ALL, and the `else " \n"` that used to be here emitted an indented blank one. The twin is a PIPELINE -- `git ... | sed 's/^/ /'` (block-unlinked-commit-author.sh:152) -- and sed given no input writes no output, so bash prints nothing whatsoever.
        #
        # It took a CI runner to see it. `git config --get-all user.email` is empty
        # only where no identity is configured at any scope; every developer machine
        # here has a global one, so the two sides agreed locally and diverged by one blank line in run 34970782616, taking three `block_unlinked_commit_author` cases of test_guards_differential.py with it.
        if origins:
            ev.warn_raw(hookio.sed_sub(r"^", "    ", hookio._printf_line(origins)))
        if cflags:
            ev.warn("    -c on your command line: %s" % " ".join("-c %s" % kv for kv in cflags))
        if env_overrides:
            ev.warn("    environment: %s" % " ".join(env_overrides))
        if override:
            ev.warn("    --author= on your command line")
        ev.warn("")
        ev.warn("Allowed (from %s):" % identity_file)
        for entry in (identity or {}).get("identities", []) if isinstance(identity, dict) else []:
            for one in entry.get("emails", []) if isinstance(entry, dict) else []:
                ev.warn("    %s" % one)
        ev.warn("")
        ev.warn("Fix: use a linked address, or add this one at")
        ev.warn("https://github.com/settings/emails and re-run --refresh.")
        return hookio.DENY

    return hookio.ALLOW
