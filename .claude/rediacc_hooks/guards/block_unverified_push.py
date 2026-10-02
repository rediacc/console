"""Refuse a push whose tree no local gate run has judged.

WHY. A CI round costs ~15 minutes. Measured on PR #579, three of the five reds this wave were `check:format` (1.72s), `check:ci-python-lint` (0.59s) and `check:ci-parity` (1.29s) -- 3.6 seconds of gate time between them, and they cost roughly 45 minutes of CI. The gates were there, the runner was there, and nothing made anyone run them.

PROSE ALREADY TRIED. docs/agent-reference/ci-gates.md says "Run it before pushing to catch issues early" and CLAUDE.md points at it. Five rounds happened anyway. wl_git.py's own header states the principle this guard follows: prose is not a safety mechanism, and the recorded incidents show it failing.

WHY A RECEIPT AND NOT A RUN. This hook sits in the PreToolUse chain, which fires on EVERY Bash call, so it must cost microseconds -- one `git rev-parse` and one file read. The expensive half (33 seconds, 254 gates) happens in an ordinary Bash call the session makes itself, where the runner's untruncated failure block is readable. Splitting them is the only shape that is both
enforceable and cheap.

KEYED ON `HEAD^{tree}`. CI checks out the pushed commit, so the tree object is
exactly what CI will judge. It is also invariant to the dozens of dirty paths this repo's tree normally carries from OTHER live sessions -- keying on the worktree would invalidate the receipt on someone else's keystroke and make it unobtainable, which is how a guard becomes a wall and then gets bypassed.

=============================================================================
PORT NOTES
=============================================================================

`command -v jq` IS KEPT, AND IT NOW GUARDS NOTHING THIS FILE DOES. The bash reads the receipt with six `jq -r` calls, so it fails open when jq is missing: "FAIL OPEN ON A BROKEN ENVIRONMENT, never on a broken verdict". This port reads the receipt with `json.loads` and needs no jq at all, so the probe is now a pure environment test with no consumer. It is reproduced anyway, because
the port is judged by AGREEMENT with its twin and a machine without jq is a case the differential can be handed. Deleting it is a BEHAVIOUR CHANGE and therefore P6's call, made when the last bash guard goes and the chain head's jq check retires with it. Recorded here so that decision is a decision rather than an omission.

THE `jq` FILTERS, spelled out because their defaults are load-bearing: `.headTree // ""`, `.whole // false`, `.exitCode // 1`, `(.failed // []) | join(", ")`, `.dirtyDigest // ""`, `(.blocked // []) | join(", ")`. `//` is falsy-tested, not null-tested, so a `whole` of `false` and a `whole` that is absent produce the same string, which is what makes the narrowed-run refusal fail
CLOSED on a receipt shape the runner has not written yet.

WHAT THIS GUARD USED TO INHERIT FROM `shellscan.target_root`: the TAB-after-`-C` defect, reproduced deliberately until Rule T (PLAN-retire-bash-oracles A4) fixed it at its source. See `block_untagged_commit`'s port notes.
"""

import hashlib
import json
import os
import pathlib
import re
import subprocess

from rediacc_hooks import commit_policy, hookio, shellscan

CHAIN = "pre-bash"
# Re-keyed from 39 to 40 on 2026-09-22 to make room for block_push_to_protected_branch.py at
# 39: "this branch may not be pushed to at all" is checked before "is this tree gate-verified".
ORDER = 39

# The tree comparison is the whole guard. Without it any receipt at all authorises any push, which is the state that let five CI rounds happen on PR #579.
DEFECT = ("if r_tree != tree:", "if False:")

PUSH_AT_COMMAND_POS = hookio.rx(
    r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+push([{S}]|$)"
)


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
Ask the operator, or leave a [?] worklist item naming the conflict, and
keep working meanwhile:

  .claude/hooks/stop/worklist.py --list --open        # who else is live here

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

    The receipt's `headTree` is filled in AFTER the commit, because the whole point of the key is that it names the tree object git actually produced. A hand-written hash would make every fixture take the "judged a different tree" branch and the other four would be unreachable.
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
    # carried-reds.json is COMMITTED, because the guard reads it from HEAD. Committed and on disk are then the same bytes, so the bash oracle (which reads the worktree) and this port still see one file and the differential compares like with like.
    if carried is not None:
        config = path / ".ci" / "config"
        config.mkdir(parents=True, exist_ok=True)
        (config / "carried-reds.json").write_text(json.dumps(carried), encoding="utf-8")
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
    return path


# The receipt worlds this guard distinguishes. Without them the corpus sees whatever receipt this shared worktree happens to hold at the moment the test runs, which is BOTH undiscriminating and a race: another session running `ci:quick` between the bash pass and the Python pass would rewrite the file and the difference would be reported as a port defect.
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
    # A whole-gate carry: `"*"` over a gate whose receipt entry is null (it emits no `::finding::` lines), with a reason past the stricter 160-character bar.
    "push-red-carried": lambda p: _repo_with_receipt(
        p,
        {
            "whole": True,
            "exitCode": 1,
            "failed": ["check:format"],
            "findings": {"check:format": None},
            "blocked": ["check:ci-go-vet"],
        },
        carried={
            "version": 2,
            "carried": [
                {
                    "gate": "check:format",
                    "findings": "*",
                    "reason": (
                        "A reason of at least one hundred and sixty characters, because a whole-gate "
                        "carry is only for a gate that emits no finding keys yet, and the bar for "
                        "carrying everything it will ever report is higher than for carrying one key."
                    ),
                }
            ],
        },
    ),
    "push-red-stale": lambda p: _repo_with_receipt(
        p,
        {"whole": True, "exitCode": 1, "failed": ["check:ci-parity"]},
        carried={
            "version": 2,
            "carried": [
                {
                    "gate": "check:format",
                    "findings": ["fmt:packages/a.ts"],
                    "reason": (
                        "A reason of at least eighty characters, kept deliberately long so "
                        "that this entry passes the substantive-reason bar and reaches the "
                        "stale-entry arm instead of being filtered out first."
                    ),
                }
            ],
        },
    ),
    # FINDING LEVEL (PLAN-carried-red-finding-keys): the carried gate is failing and named, but it emitted a key the entry does not carry, so the push refuses naming it; the sibling world carries exactly the emitted keys and is allowed.
    "push-red-finding-new": lambda p: _repo_with_receipt(
        p,
        {
            "whole": True,
            "exitCode": 1,
            "failed": ["check:ci-plan-implementation"],
            "findings": {
                "check:ci-plan-implementation": [
                    "P-A2:no-row:agent/plans/PLAN-a.md#0a1b2c3d",
                    "P-A2:no-row:agent/plans/PLAN-b.md#4e5f6a7b",
                ]
            },
        },
        carried={
            "version": 2,
            "carried": [
                {
                    "gate": "check:ci-plan-implementation",
                    "findings": ["P-A2:no-row:agent/plans/PLAN-a.md#0a1b2c3d"],
                    "reason": (
                        "A reason of at least eighty characters, so the entry clears the "
                        "substance bar and the verdict turns on the finding keys alone."
                    ),
                }
            ],
        },
    ),
    "push-red-finding-carried": lambda p: _repo_with_receipt(
        p,
        {
            "whole": True,
            "exitCode": 1,
            "failed": ["check:ci-plan-implementation"],
            "findings": {
                "check:ci-plan-implementation": [
                    "P-A2:no-row:agent/plans/PLAN-a.md#0a1b2c3d",
                    "P-A2:no-row:agent/plans/PLAN-b.md#4e5f6a7b",
                ]
            },
        },
        carried={
            "version": 2,
            "carried": [
                {
                    "gate": "check:ci-plan-implementation",
                    "findings": [
                        "P-A2:no-row:agent/plans/PLAN-a.md#0a1b2c3d",
                        "P-A2:no-row:agent/plans/PLAN-b.md#4e5f6a7b",
                    ],
                    "reason": (
                        "A reason of at least eighty characters, so the entry clears the "
                        "substance bar and the verdict turns on the finding keys alone."
                    ),
                }
            ],
        },
    ),
}

# The last variant is this checkout's SHAPE, and it closes the second half of the race the FIXTURES comment above names. Keying on `HEAD^{tree}` survives a dirty tree by design, but it does NOT survive a commit: with one interleaved between the differential's bash pass and its Python side, this guard named two different tree hashes in the same refusal, one per side. The
# world has a history and a branch and neither moves; since 2026-09-24 it is synthetic rather than a clone, so a golden frozen from it stays true. See `_synthetic_this_worktree` in test_guards_differential.py.
ENVS = [(name, {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in sorted(FIXTURES)] + [
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {})
]

EDGE_CASES = [
    ("a plain push", "git push origin 0831-1"),
    # A dry run publishes nothing and buys no CI round.
    ("a dry run", "git push --dry-run origin 0831-1"),
    # #641e2fce: one dry run does not exempt a real push beside it.
    ("a dry run beside a real push", "git push --dry-run origin x; git push origin 0831-1"),
    ("a dry run behind a global option", "git -C . push --dry-run origin 0831-1"),
    ("prose about pushing", "echo 'remember to git push once green'"),
    ("git pull is not git push", "git pull --rebase"),
    # SUBMODULE PUSHES ARE OUT OF SCOPE, deliberately.
    ("cd into a submodule", "cd private/account && git push origin 0831-1"),
    ("git -C into a submodule", "git -C private/renet push"),
    # A TAB after `-C` is a blank like any other since the Rule T fix to shellscan.target_root (A4); /tmp is not a repository, so the push is judged against this tree either way.
    ("git -C with a TAB is still a -C", "git -C\t/tmp push"),
    ("a push in another tree", "cd /tmp && git push"),
]


def _jq_join(value, sep=", "):
    """`(.x // []) | join(", ")` -- a jq join, over a list that may be absent.

    jq stringifies a non-string element rather than refusing, which is why this does not assume the list holds strings.
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
    # AN EARLIER CLAUSE MAY MOVE HEAD OR REWRITE THE RECEIPT (R20260924.22). This guard judges `HEAD^{tree}`, the receipt and carried-reds.json at HEAD as they are before the command runs, so a `git commit` or `npm run ci:quick` earlier in the same command changes all three. 2026-09-24 19:28:10: a carry-file fix committed by an earlier clause was judged at the pre-commit HEAD, and the refusal
    # never said so.
    ev.warn_raw(
        shellscan.split_refusal(
            shellscan.earlier_mutators(
                ev.field("tool_input", "command"), "git push", {"commit", "ci"}
            ),
            "git push",
            "HEAD^{tree}, the pre-push receipt and .ci/config/carried-reds.json at HEAD",
        )
    )
    ev.warn_raw("BLOCKED: %s\n%s" % (reason, REFUSAL_TAIL))
    return hookio.DENY


CARRIED_REL = ".ci/config/carried-reds.json"


def _carried_at_head(root):
    """carried-reds.json as committed at HEAD in `root`, parsed; None when HEAD has no such file or it does not parse."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "show", "HEAD:%s" % CARRIED_REL],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def _read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Every read in the bash is `jq ... 2>/dev/null`, so an unreadable or malformed file behaves exactly like an absent key: the `//` default.
        return None


#: The substance bar for a keyed entry: the one .dead-bash-allowlist uses and gate-test:dead-bash pins with a low-effort-BLOCKER case. A bare "known issue" excuses nothing.
REASON_MIN = 80
#: The stricter bar for `"findings": "*"`, a whole-gate carry. It is only for a gate that does not speak the `::finding::` protocol yet, so it must say more.
STAR_REASON_MIN = 160
CARRIED_VERSION = 2


def parse_carried(doc):
    """carried-reds.json v2 -> (`{gate: set(keys) | "*"}`, schema_error or None).

    SCHEMA ERRORS REFUSE, they are never skipped: a v1 entry (`{gate, reason}` with no `findings`), an empty `findings`, a missing `version: 2`, or `"*"` beside keyed entries for one gate. A malformed entry skipped silently is how a carry file quietly stops carrying what its author thinks it carries.

    An entry whose reason is under its bar (REASON_MIN, or STAR_REASON_MIN for `"*"`) is well-formed but carries nothing, so its gate then refuses as unnamed. Several keyed entries for one gate union their keys.
    """
    if doc is None:
        return {}, None
    if not isinstance(doc, dict) or doc.get("version") != CARRIED_VERSION:
        return {}, 'carried-reds.json at HEAD is not `"version": %d`.' % CARRIED_VERSION
    entries = doc.get("carried")
    if not isinstance(entries, list):
        return {}, "carried-reds.json at HEAD has no `carried` list."
    carried: dict[str, set[str] | str] = {}
    shapes: dict[str, str] = {}
    for i, entry in enumerate(entries):
        gate = entry.get("gate") if isinstance(entry, dict) else None
        if not isinstance(gate, str) or not gate:
            return {}, "carried-reds.json entry %d names no gate." % i
        findings = entry.get("findings")
        if findings == "*":
            shape = "*"
        elif (
            isinstance(findings, list)
            and findings
            and all(isinstance(k, str) and k for k in findings)
        ):
            shape = "keys"
        else:
            return {}, (
                "carried-reds.json entry %d (%s) has no `findings`: v2 carries a non-empty list of"
                ' finding keys, or "*" for a gate that emits none.' % (i, gate)
            )
        if shapes.setdefault(gate, shape) != shape:
            return {}, (
                '%s is carried both by "*" and by keys; carry a gate one way or the other.' % gate
            )
        reason = entry.get("reason")
        reason = reason if isinstance(reason, str) else ""
        if len(reason) < (STAR_REASON_MIN if shape == "*" else REASON_MIN):
            continue
        if shape == "*":
            carried[gate] = "*"
            continue
        keys = carried.get(gate)
        if not isinstance(keys, set):
            keys = carried[gate] = set()
        keys.update(findings)
    return carried, None


def carried_verdict(receipt, doc):
    """(refusal or None, note parts) for a RED receipt against carried-reds.json `doc` (parsed, from HEAD; None when absent). PURE: no git, no filesystem, so the tests and the push-clone proof drive exactly the function the guard runs.

    GATE LEVEL first, as before: a failed gate nothing carries refuses (unnamed), and a carried gate that is not failing refuses (stale). Then FINDING LEVEL, from `receipt["findings"]` (`{gate: [keys] | null}`, scripts/ci-runner/findings.ts): a keyed carry needs the gate's keys, and refuses on (a) a key the gate emitted that is not carried and (b) a carried key the gate no longer emits. A `"*"` carry is refused for a gate that DOES emit keys. A receipt with no `findings` field (an older runner) reads as null for every gate, so a keyed carry fails closed.
    """
    carried, schema_error = parse_carried(doc)
    if schema_error is not None:
        return schema_error + (
            '\n  Each entry is {"gate", "findings": [keys] | "*", "reason"} under'
            ' `"version": 2`; the keys are the gate\'s `::finding::` lines, recorded in the'
            " receipt's `findings`."
        ), []

    failed = receipt.get("failed") if isinstance(receipt, dict) else None
    failed = [g for g in failed if isinstance(g, str)] if isinstance(failed, list) else []
    rf = receipt.get("findings") if isinstance(receipt, dict) else None
    rf = rf if isinstance(rf, dict) else {}

    unnamed = "".join(" %s" % g for g in failed if g not in carried)
    if unnamed:
        return (
            "the gate run went RED and these failures are neither fixed nor carried:%s.\n"
            "  To carry one deliberately, add it to .ci/config/carried-reds.json with a reason\n"
            "  that says WHY it cannot be fixed now. CI still runs it and still fails on it --\n"
            "  carrying only records the decision instead of routing around it." % unnamed
        ), []

    # STALE ENTRIES REFUSE. An excuse that outlives its failure is exactly how an allowlist rots into a permanent hole -- the npm side of this repo once carried 101 dead entries for that reason. If a carried gate is no longer failing, the entry must go before the next push.
    stale = "".join(" %s" % g for g in sorted(carried) if g not in failed)
    if stale:
        return (
            "these gates are carried in .ci/config/carried-reds.json but are NOT failing"
            " any more:%s.\n"
            "  Remove the entries. A carried red that has gone green is a standing excuse for\n"
            "  a problem that no longer exists, which is how an allowlist becomes permanent."
            % stale
        ), []

    notes = []
    for g in failed:
        emitted = rf.get(g)
        emitted = [k for k in emitted if isinstance(k, str)] if isinstance(emitted, list) else None
        if carried[g] == "*":
            if emitted is not None:
                return (
                    "%s emits findings (%d in this receipt); carry them by key, not '*'. Copy the"
                    " keys from the receipt's `findings` into its entry." % (g, len(emitted))
                ), []
            notes.append("%s (*)" % g)
            continue
        if emitted is None:
            return (
                "%s reported no parsable findings (or the receipt predates finding keys); a keyed"
                " carry cannot be verified -- re-run npm run ci:quick" % g
            ), []
        new = sorted(set(emitted) - carried[g])
        if new:
            return (
                "%s has NEW findings that .ci/config/carried-reds.json does not carry:\n%s\n"
                "  A carried gate carries the findings it names, not every finding it will ever"
                " have. Fix these, or carry them with a reason."
                % (g, "".join("    %s\n" % k for k in new).rstrip("\n"))
            ), []
        gone = sorted(carried[g] - set(emitted))
        if gone:
            return (
                "%s no longer reports these carried findings -- remove them from"
                " .ci/config/carried-reds.json:\n%s"
                % (g, "".join("    %s\n" % k for k in gone).rstrip("\n"))
            ), []
        notes.append("%s (%d findings carried)" % (g, len(carried[g])))
    return None, notes


def every_push_deletes_only(scan):
    """True when every `git ... push` segment in the command only deletes remote refs.

    A segment deletes only when it carries `--delete`/`-d`, or when every refspec after the remote is `:<ref>`. Anything else in any segment -- a plain branch, `HEAD`, `--tags`, `--all`, `--mirror` -- makes the whole command a publishing push.
    """
    pushes = [seg for seg in re.split(r"[;&|\n]+", scan) if hookio.grep_q(PUSH_AT_COMMAND_POS, seg)]
    if not pushes:
        return False
    for seg in pushes:
        words = seg.split()
        tail = words[words.index("push") + 1 :] if "push" in words else []
        if any(w in ("--all", "--mirror", "--tags") for w in tail):
            return False
        if "--delete" in tail or "-d" in tail:
            continue
        refspecs = [w for w in tail if not w.startswith("-")][1:]
        if not refspecs or not all(r.startswith(":") and len(r) > 1 for r in refspecs):
            return False
    return True


def run(ev):
    state = shellscan.hook_init(ev.payload)
    if state is None:
        return hookio.ALLOW
    cmd, scan = state

    # Command position, so prose about pushing is not a push. Same anchor as block-untagged-commit.sh; see lib/command-scan.sh for why the raw string is never matched directly.
    if not hookio.grep_q(PUSH_AT_COMMAND_POS, scan):
        return hookio.ALLOW

    # A dry run publishes nothing and buys no CI round, but only when EVERY push in the command is one (#641e2fce): the text match it replaced let `git push --dry-run x; git push origin y` skip the receipt. Judged per push on the lexer's canonical spelling, so `git -C . push --dry-run` counts too.
    pushes = [line for line in commit_policy.push_texts(cmd).split("\n") if line]
    if pushes and all("--dry-run" in line.split() for line in pushes):
        return hookio.ALLOW

    # A DELETE-ONLY PUSH publishes no tree either, so there is nothing for a gate run to have judged. Found 2026-09-24 refusing `git push origin --delete <merged-branch>` during a branch cleanup, which pointed the session at `npm run ci:quick` for a push that removes a ref and carries no commits. Judged PER PUSH SEGMENT, so `git push origin --delete x && git push origin y` is still refused on the second segment.
    if every_push_deletes_only(scan):
        return hookio.ALLOW

    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    if root == "":
        return hookio.ALLOW

    # ANOTHER REPO'S PUSH IS NOT THIS TREE'S BUSINESS, and it was being refused as though it were. Reproduced 2026-09-01: `git -C <scratch-repo> push origin main` exited 2 here, because the gate-run stamp compared below belongs to CONSOLE and the scratch tree can never match it. The message then reads as "your gates are stale" about a repo the gates were never run against. Same
    # class as block-untagged-commit.sh:52-69; the resolution now lives in lib/command-scan.sh rather than being written a third time.
    if shellscan.target_root(scan, root, verb="push") != "":
        return hookio.ALLOW

    # THE SHELL'S OWN WORKING DIRECTORY NAMES THE REPO TOO, not only `-C`/`cd` in the command. A plain `git push origin 0923-1` run with the tool's cwd already inside private/account was judged against the CONSOLE receipt and refused as "a different tree" (#e83d9ba9, 2026-09-25). A payload cwd whose top level is not this root's is another repository's push.
    cwd = ev.raw("cwd")
    if cwd not in ("", "null"):
        top = hookio.git_out(["-C", cwd, "rev-parse", "--show-toplevel"], want_rc=True)
        if top and os.path.realpath(top) != os.path.realpath(root):
            return hookio.ALLOW

    # SUBMODULE PUSHES ARE OUT OF SCOPE, deliberately. They advance no console branch and trigger no console CI; cancel-old-ci.sh draws the same line for the same reason. The pointer-bump commit that DOES advance console is covered by the ordinary path.
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

    # FAIL OPEN ON A BROKEN ENVIRONMENT, never on a broken verdict. No jq, no git, no repo: allow, exactly as warn-remote-drift.sh does -- "a drift CHECK must never become a push outage". A MISSING or STALE receipt is a different thing and is refused below, because that is the condition this guard exists for.
    if not hookio.have("jq"):
        return hookio.ALLOW

    if not pathlib.Path(receipt_path).is_file():
        return _refuse(ev, "no local gate run has judged this tree.")

    receipt = _read_json(receipt_path)
    r_tree = _alt(receipt, "headTree", "")
    r_whole = _alt(receipt, "whole", False)
    r_exit = _alt(receipt, "exitCode", 1)
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

    # A NARROWED RUN PROVES ALMOST NOTHING. `--quick --only <one-gate>` produces a receipt that is otherwise indistinguishable from all 254, so the runner records whether the lane ran WHOLE and this reads the flag rather than parsing the selection prose -- a guard that parses English fails open on a rewording.
    if r_whole != "true":
        return _refuse(
            ev, "that receipt came from a NARROWED run (--only/--skip), not the whole lane."
        )

    if r_exit != "0":
        # A RED RECEIPT MAY STILL AUTHORISE A PUSH, but only when every failure is named and justified in .ci/config/carried-reds.json. All-or-nothing is the shape that gets a guard routed around; naming the exception keeps the refusal informative and leaves the excuse in git where it can be reviewed.
        #
        # READ FROM THE TREE BEING PUSHED, not the worktree. The receipt is keyed on HEAD^{tree}, so the excuses that clear it must come from the same tree. Reading the worktree let another writer's uncommitted edit to this file change the verdict on a push that does not contain that edit (2026-09-24: a working copy that dropped one entry refused a push whose HEAD still carried it). An absent file at HEAD means nothing is carried.
        refusal, notes = carried_verdict(receipt, _carried_at_head(root))
        if refusal is not None:
            return _refuse(ev, refusal)
        ev.warn("NOTE: pushing with CARRIED reds, each named in .ci/config/carried-reds.json:")
        ev.warn("  %s" % ", ".join(notes))
        ev.warn("  CI runs these for real and will fail on them. Carrying is a record of a")
        ev.warn("  deliberate decision, not a way to make CI green.")

    # A GATE THAT COULD NOT RUN WARNS, IT DOES NOT REFUSE (operator decision, 2026-08-27). Measured that day: twelve reds on a normal developer tree, ten of them ambient, several purely "this machine has no ruff / no workers-types". A missing toolchain is not evidence about the code, and refusing on it would make the receipt unobtainable -- an unobtainable receipt is a guard people
    # route around, which costs more than the rounds it saves.
    #
    # Never silent, though. "A linter that cannot run is a gate that cannot fail" stays true; this makes that state loud instead of forgiving it, and CI still runs those gates for real.
    if r_blocked:
        ev.warn("NOTE: these gates could NOT RUN locally, so nothing here judged what they cover:")
        ev.warn("  %s" % r_blocked)
        ev.warn("  They are not a verdict on your code and they do not block this push --")
        ev.warn("  but CI runs them for real, so a finding in them lands there instead.")
        ev.warn("  Each names its own install line; `.ci/scripts/lib/toolchain.sh --report`")
        ev.warn("  lists what this machine is missing against the pinned versions.")

    # THE HONEST RESIDUAL, stated rather than hidden: the gates ran against the
    # WORKING TREE, not against `HEAD^{tree}`. If the dirty set has moved since,
    # something the gates read has changed. That is a warning and not a refusal -- this tree carries dozens of dirty paths from other sessions at any moment, so refusing on it would make the receipt unobtainable, and an unobtainable receipt is a guard nobody keeps.
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

    `sha256sum` prints `<hex> -`, and `cut -c1-16` takes the first sixteen characters of the hex, never of the filename field. A pipeline, so a git failure yields an empty digest rather than an error, and the caller treats an empty digest as "no comparison to make".
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
