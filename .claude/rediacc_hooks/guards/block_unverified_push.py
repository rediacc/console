"""Refuse a push whose tree no local gate run has judged.

WHY. A CI round costs ~15 minutes. Measured on PR #579, three of the five
reds this wave were `check:format` (1.72s), `check:ci-python-lint` (0.59s) and
`check:ci-parity` (1.29s) -- 3.6 seconds of gate time between them, and they
cost roughly 45 minutes of CI. The gates were there, the runner was there, and
nothing made anyone run them.

PROSE ALREADY TRIED. docs/agent-reference/ci-gates.md says "Run it before
pushing to catch issues early" and CLAUDE.md points at it. Five rounds
happened anyway. wl_git.py's own header states the principle this guard
follows: prose is not a safety mechanism, and the recorded incidents show it
failing.

WHY A RECEIPT AND NOT A RUN. This hook sits in the PreToolUse chain, which
fires on EVERY Bash call, so it must cost microseconds -- one `git rev-parse`
and one file read. The expensive half (33 seconds, 254 gates) happens in an
ordinary Bash call the session makes itself, where the runner's untruncated
failure block is readable. Splitting them is the only shape that is both
enforceable and cheap.

KEYED ON `HEAD^{tree}`. CI checks out the pushed commit, so the tree object is
exactly what CI will judge. It is also invariant to the dozens of dirty paths
this repo's tree normally carries from OTHER live sessions -- keying on the
worktree would invalidate the receipt on someone else's keystroke and make it
unobtainable, which is how a guard becomes a wall and then gets bypassed.

=============================================================================
PORT NOTES
=============================================================================

`command -v jq` IS KEPT, AND IT NOW GUARDS NOTHING THIS FILE DOES. The bash
reads the receipt with six `jq -r` calls, so it fails open when jq is missing:
"FAIL OPEN ON A BROKEN ENVIRONMENT, never on a broken verdict". This port reads
the receipt with `json.loads` and needs no jq at all, so the probe is now a pure
environment test with no consumer. It is reproduced anyway, because the port is
judged by AGREEMENT with its twin and a machine without jq is a case the
differential can be handed. Deleting it is a BEHAVIOUR CHANGE and therefore
P6's call, made when the last bash guard goes and `require-jq.sh` retires with
it. Recorded here so that decision is a decision rather than an omission.

THE `jq` FILTERS, spelled out because their defaults are load-bearing:
`.headTree // ""`, `.whole // false`, `.exitCode // 1`, `(.failed // []) |
join(", ")`, `.dirtyDigest // ""`, `(.blocked // []) | join(", ")`. `//` is
falsy-tested, not null-tested, so a `whole` of `false` and a `whole` that is
absent produce the same string, which is what makes the narrowed-run refusal
fail CLOSED on a receipt shape the runner has not written yet.

WHAT THIS GUARD INHERITS FROM `shellscan.target_root`: the TAB-after-`-C`
defect, reproduced deliberately. See `block_untagged_commit`'s port notes.
"""

import hashlib
import json
import os
import pathlib
import subprocess

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-unverified-push.sh"
ORDER = 39

# The tree comparison is the whole guard. Without it any receipt at all
# authorises any push, which is the state that let five CI rounds happen on
# PR #579.
DEFECT = ("if r_tree != tree:", "if False:")

PUSH_AT_COMMAND_POS = (
    r"(^|[;&|(]|\$\(|`)["
    + hookio.SPACE
    + r"]*git(["
    + hookio.SPACE
    + r"]+-[A-Za-z-]+(["
    + hookio.SPACE
    + r"]+[^ ;&|]+)?)*["
    + hookio.SPACE
    + r"]+push(["
    + hookio.SPACE
    + r"]|$)"
)

DRY_RUN = r"git push[^|;&]*--dry-run"

REFUSAL_TAIL = """
The pre-push lane is 254 gates in ~33 seconds, and it exists because three of
the five CI reds on PR #579 were sub-2-second gates that cost ~45 minutes of CI
between them. Run it, fix what it names, then push:

  npm run ci:quick

It is a PARTIAL run and says so: 58 slower gates are deferred to CI, and it
names any it had to defer because a prerequisite was slow. `npm run ci` is
still the whole set.

If a gate it names is not yours -- another session's uncommitted file often
reddens this shared tree -- do not work around it and do not fix their file.
Ask them, and keep working while they answer:

  .claude/hooks/stop/worklist.py --list --open        # who else is live here
  .claude/hooks/stop/worklist.py --ask <you> <them> '<gate>: <what you saw>'

If a gate cannot RUN here (a toolchain this machine lacks), that is not a red
you can fix by pushing: the gate's own message names the install line.
"""


def _env():
    return dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )


def _repo_with_receipt(path, receipt, carried=None):
    """A checkout whose `.ci/cache/prepush-receipt.json` says what we want.

    The receipt's `headTree` is filled in AFTER the commit, because the whole
    point of the key is that it names the tree object git actually produced.
    A hand-written hash would make every fixture take the "judged a different
    tree" branch and the other four would be unreachable.
    """
    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", "-q"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=_env(),
    )
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True, env=_env())
    subprocess.run(
        ["git", "commit", "-q", "-m", "seed"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=_env(),
    )
    if receipt is not None:
        tree = (
            subprocess.run(
                ["git", "rev-parse", "HEAD^{tree}"],
                cwd=str(path),
                check=True,
                capture_output=True,
                env=_env(),
            )
            .stdout.decode()
            .strip()
        )
        body = dict(receipt)
        body.setdefault("headTree", tree)
        cache = path / ".ci" / "cache"
        cache.mkdir(parents=True)
        (cache / "prepush-receipt.json").write_text(json.dumps(body), encoding="utf-8")
    if carried is not None:
        config = path / ".ci" / "config"
        config.mkdir(parents=True, exist_ok=True)
        (config / "carried-reds.json").write_text(json.dumps(carried), encoding="utf-8")
    return path


# The five receipt worlds this guard distinguishes. Without them the corpus
# sees whatever receipt this shared worktree happens to hold at the moment the
# test runs, which is BOTH undiscriminating and a race: another session running
# `ci:quick` between the bash pass and the Python pass would rewrite the file
# and the difference would be reported as a port defect.
FIXTURES = {
    "push-no-receipt": lambda p: _repo_with_receipt(p, None),
    "push-green": lambda p: _repo_with_receipt(p, {"whole": True, "exitCode": 0}),
    "push-narrowed": lambda p: _repo_with_receipt(p, {"whole": False, "exitCode": 0}),
    "push-wrong-tree": lambda p: _repo_with_receipt(
        p, {"headTree": "0" * 40, "whole": True, "exitCode": 0}
    ),
    "push-red-unnamed": lambda p: _repo_with_receipt(
        p, {"whole": True, "exitCode": 1, "failed": ["check:format", "check:ci-parity"]}
    ),
    "push-red-carried": lambda p: _repo_with_receipt(
        p,
        {"whole": True, "exitCode": 1, "failed": ["check:format"], "blocked": ["check:ci-go-vet"]},
        carried={
            "carried": [
                {
                    "gate": "check:format",
                    "reason": (
                        "A reason of at least eighty characters, because the bar this "
                        "guard applies is the one the dead-bash allowlist uses and a bare "
                        "'known issue' excuses nothing at all here."
                    ),
                }
            ]
        },
    ),
    "push-red-stale": lambda p: _repo_with_receipt(
        p,
        {"whole": True, "exitCode": 1, "failed": ["check:ci-parity"]},
        carried={
            "carried": [
                {
                    "gate": "check:format",
                    "reason": (
                        "A reason of at least eighty characters, kept deliberately long so "
                        "that this entry passes the substantive-reason bar and reaches the "
                        "stale-entry arm instead of being filtered out first."
                    ),
                }
            ]
        },
    ),
}

ENVS = [(name, {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in sorted(FIXTURES)] + [
    ("this-worktree", {}, {})
]

EDGE_CASES = [
    ("a plain push", "git push origin 0831-1"),
    # A dry run publishes nothing and buys no CI round.
    ("a dry run", "git push --dry-run origin 0831-1"),
    ("prose about pushing", "echo 'remember to git push once green'"),
    ("git pull is not git push", "git pull --rebase"),
    # SUBMODULE PUSHES ARE OUT OF SCOPE, deliberately.
    ("cd into a submodule", "cd private/account && git push origin 0831-1"),
    ("git -C into a submodule", "git -C private/renet push"),
    # The tab defect inherited from shellscan.target_root, pinned here so a
    # later change to that module is a visible divergence rather than a quiet one.
    ("git -C with a TAB resolves to the empty root", "git -C\t/tmp push"),
    ("a push in another tree", "cd /tmp && git push"),
]


def _jq_join(value, sep=", "):
    """`(.x // []) | join(", ")` -- a jq join, over a list that may be absent.

    jq stringifies a non-string element rather than refusing, which is why this
    does not assume the list holds strings.
    """
    if not isinstance(value, list):
        return ""
    out = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
        elif item is None:
            out.append("")
        elif isinstance(item, bool):
            out.append("true" if item else "false")
        else:
            out.append(json.dumps(item, separators=(",", ":")))
    return sep.join(out)


def _alt(doc, key, fallback):
    """`.key // <fallback>`: FALSY, not null. `false` and `0` take the fallback."""
    if not isinstance(doc, dict):
        return fallback
    value = doc.get(key)
    if value is None or value is False:
        return fallback
    return value


def _refuse(ev, reason):
    ev.warn_raw("BLOCKED: %s\n%s" % (reason, REFUSAL_TAIL))
    return hookio.DENY


def _read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Every read in the bash is `jq ... 2>/dev/null`, so an unreadable or
        # malformed file behaves exactly like an absent key: the `//` default.
        return None


def run(ev):
    state = shellscan.hook_init(ev.payload)
    if state is None:
        return hookio.ALLOW
    cmd, scan = state

    # Command position, so prose about pushing is not a push. Same anchor as
    # block-untagged-commit.sh; see lib/command-scan.sh for why the raw string is
    # never matched directly.
    if not hookio.grep_q(PUSH_AT_COMMAND_POS, scan):
        return hookio.ALLOW

    # A dry run publishes nothing and buys no CI round.
    if hookio.grep_q(DRY_RUN, cmd):
        return hookio.ALLOW

    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    if root == "":
        return hookio.ALLOW

    # ANOTHER REPO'S PUSH IS NOT THIS TREE'S BUSINESS, and it was being refused as though it
    # were. Reproduced 2026-09-01: `git -C <scratch-repo> push origin main` exited 2 here,
    # because the gate-run stamp compared below belongs to CONSOLE and the scratch tree can
    # never match it. The message then reads as "your gates are stale" about a repo the gates
    # were never run against. Same class as block-untagged-commit.sh:52-69; the resolution now
    # lives in lib/command-scan.sh rather than being written a third time.
    if shellscan.target_root(scan, root) != "":
        return hookio.ALLOW

    # SUBMODULE PUSHES ARE OUT OF SCOPE, deliberately. They advance no console
    # branch and trigger no console CI; cancel-old-ci.sh draws the same line for the
    # same reason. The pointer-bump commit that DOES advance console is covered by
    # the ordinary path.
    if hookio.case_glob(
        cmd,
        "*-C %s/private/*" % root,
        "*cd %s/private/*" % root,
        "*git -C private/*",
        "*cd private/*",
    ):
        return hookio.ALLOW

    receipt_path = "%s/.ci/cache/prepush-receipt.json" % root
    tree = hookio.git_out(["-C", root, "rev-parse", "HEAD^{tree}"], want_rc=True)
    if tree is None or tree == "":
        return hookio.ALLOW

    # FAIL OPEN ON A BROKEN ENVIRONMENT, never on a broken verdict. No jq, no git,
    # no repo: allow, exactly as warn-remote-drift.sh does -- "a drift CHECK must
    # never become a push outage". A MISSING or STALE receipt is a different thing
    # and is refused below, because that is the condition this guard exists for.
    if not hookio.have("jq"):
        return hookio.ALLOW

    if not pathlib.Path(receipt_path).is_file():
        return _refuse(ev, "no local gate run has judged this tree.")

    receipt = _read_json(receipt_path)
    r_tree = _alt(receipt, "headTree", "")
    r_whole = _alt(receipt, "whole", False)
    r_exit = _alt(receipt, "exitCode", 1)
    r_failed = _jq_join(receipt.get("failed") if isinstance(receipt, dict) else None)
    r_dirty = _alt(receipt, "dirtyDigest", "")
    r_blocked = _jq_join(receipt.get("blocked") if isinstance(receipt, dict) else None)
    # `R_TREE=$(jq -r ...)` is a STRING in the bash, whatever the JSON type, so
    # a numeric or boolean field is compared as jq would have printed it.
    r_tree = r_tree if isinstance(r_tree, str) else json.dumps(r_tree, separators=(",", ":"))
    r_whole = (
        "true"
        if r_whole is True
        else (r_whole if isinstance(r_whole, str) else json.dumps(r_whole, separators=(",", ":")))
    )
    r_exit = r_exit if isinstance(r_exit, str) else json.dumps(r_exit, separators=(",", ":"))

    if r_tree != tree:
        return _refuse(
            ev,
            "the gate run judged a different tree (%s), not this one (%s)." % (r_tree, tree),
        )

    # A NARROWED RUN PROVES ALMOST NOTHING. `--quick --only <one-gate>` produces a
    # receipt that is otherwise indistinguishable from all 254, so the runner
    # records whether the lane ran WHOLE and this reads the flag rather than
    # parsing the selection prose -- a guard that parses English fails open on a
    # rewording.
    if r_whole != "true":
        return _refuse(
            ev, "that receipt came from a NARROWED run (--only/--skip), not the whole lane."
        )

    if r_exit != "0":
        # A RED RECEIPT MAY STILL AUTHORISE A PUSH, but only when every failure is
        # named and justified in .ci/config/carried-reds.json. All-or-nothing is the
        # shape that gets a guard routed around; naming the exception keeps the
        # refusal informative and leaves the excuse in git where it can be reviewed.
        carried_file = "%s/.ci/config/carried-reds.json" % root
        carried = []
        if pathlib.Path(carried_file).is_file():
            # Only entries whose reason is SUBSTANTIVE count. The bar is the one
            # .dead-bash-allowlist uses and gate-test:dead-bash pins with a
            # low-effort-BLOCKER case: a bare "known issue" excuses nothing.
            doc = _read_json(carried_file)
            entries = doc.get("carried") if isinstance(doc, dict) else None
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, dict):
                    continue
                reason = entry.get("reason")
                reason = reason if isinstance(reason, str) else ""
                if len(reason) >= 80:
                    carried.append(entry.get("gate"))
            carried = [g for g in carried if isinstance(g, str)]

        failed = receipt.get("failed") if isinstance(receipt, dict) else None
        failed = [g for g in failed if isinstance(g, str)] if isinstance(failed, list) else []
        # `for g in $(jq -r '(.failed // [])[]')` is UNQUOTED, so the shell word-
        # splits each name. Every gate name here is one word, so the two agree;
        # a name with a space would split in the bash and not here, and that is
        # a difference in the ORIGINAL rather than in the port.
        unnamed = "".join(" %s" % g for g in failed if g not in carried)

        # STALE ENTRIES REFUSE. An excuse that outlives its failure is exactly how an
        # allowlist rots into a permanent hole -- the npm side of this repo once
        # carried 101 dead entries for that reason. If a carried gate is no longer
        # failing, the entry must go before the next push.
        stale = "".join(" %s" % g for g in carried if g not in failed)

        if unnamed:
            return _refuse(
                ev,
                "the gate run went RED and these failures are neither fixed nor carried:%s.\n"
                "  To carry one deliberately, add it to .ci/config/carried-reds.json with a reason\n"
                "  that says WHY it cannot be fixed now. CI still runs it and still fails on it --\n"
                "  carrying only records the decision instead of routing around it." % unnamed,
            )

        if stale:
            return _refuse(
                ev,
                "these gates are carried in .ci/config/carried-reds.json but are NOT failing"
                " any more:%s.\n"
                "  Remove the entries. A carried red that has gone green is a standing excuse for\n"
                "  a problem that no longer exists, which is how an allowlist becomes permanent."
                % stale,
            )

        ev.warn("NOTE: pushing with CARRIED reds, each named in .ci/config/carried-reds.json:")
        ev.warn("  %s" % r_failed)
        ev.warn("  CI runs these for real and will fail on them. Carrying is a record of a")
        ev.warn("  deliberate decision, not a way to make CI green.")

    # A GATE THAT COULD NOT RUN WARNS, IT DOES NOT REFUSE (operator decision,
    # 2026-08-27). Measured that day: twelve reds on a normal developer tree, ten of
    # them ambient, several purely "this machine has no ruff / no workers-types". A
    # missing toolchain is not evidence about the code, and refusing on it would
    # make the receipt unobtainable -- an unobtainable receipt is a guard people
    # route around, which costs more than the rounds it saves.
    #
    # Never silent, though. "A linter that cannot run is a gate that cannot fail"
    # stays true; this makes that state loud instead of forgiving it, and CI still
    # runs those gates for real.
    if r_blocked:
        ev.warn("NOTE: these gates could NOT RUN locally, so nothing here judged what they cover:")
        ev.warn("  %s" % r_blocked)
        ev.warn("  They are not a verdict on your code and they do not block this push --")
        ev.warn("  but CI runs them for real, so a finding in them lands there instead.")
        ev.warn("  Each names its own install line; `.ci/scripts/lib/toolchain.sh --report`")
        ev.warn("  lists what this machine is missing against the pinned versions.")

    # THE HONEST RESIDUAL, stated rather than hidden: the gates ran against the
    # WORKING TREE, not against `HEAD^{tree}`. If the dirty set has moved since,
    # something the gates read has changed. That is a warning and not a refusal --
    # this tree carries dozens of dirty paths from other sessions at any moment, so
    # refusing on it would make the receipt unobtainable, and an unobtainable
    # receipt is a guard nobody keeps.
    now_dirty = _dirty_digest(root)
    r_dirty = r_dirty if isinstance(r_dirty, str) else ""
    if now_dirty and r_dirty and now_dirty != r_dirty:
        ev.warn("NOTE: the working tree has changed since the gates ran (they judged the")
        ev.warn("  worktree, this push carries HEAD^{tree}). The receipt still matches the")
        ev.warn("  committed tree, so this is allowed -- but if you changed something a gate")
        ev.warn("  reads, re-run: npm run ci:quick")
    return hookio.ALLOW


def _dirty_digest(root):
    """`git status --porcelain=v1 -z | sha256sum | cut -c1-16`.

    `sha256sum` prints `<hex>  -`, and `cut -c1-16` takes the first sixteen
    characters of the hex, never of the filename field. A pipeline, so a git
    failure yields an empty digest rather than an error, and the caller treats
    an empty digest as "no comparison to make".
    """
    try:
        proc = subprocess.run(
            ["git", "-C", root, "status", "--porcelain=v1", "-z"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return ""
    if proc.returncode != 0:
        # The bash pipeline still runs sha256sum over whatever git wrote, which
        # for a failure is nothing at all: sha256sum of the empty input.
        return hashlib.sha256(b"").hexdigest()[:16]
    return hashlib.sha256(proc.stdout).hexdigest()[:16]
