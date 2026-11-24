"""Refuse a push whose tree no local gate run has judged.

WHY. A CI round costs ~15 minutes. Measured on PR #579, three of the five reds this wave were `check:format` (1.72s), `check:ci-python-lint` (0.59s) and `check:ci-parity` (1.29s) -- 3.6 seconds of gate time between them, and they cost roughly 45 minutes of CI. The gates were there, the runner was there, and nothing made anyone run them.

PROSE ALREADY TRIED. docs/agent-reference/ci-gates.md says "Run it before pushing to catch issues early" and CLAUDE.md points at it. Five rounds happened anyway. wl_git.py's own header states the principle this guard follows: prose is not a safety mechanism, and the recorded incidents show it failing.

WHY A RECEIPT AND NOT A RUN. This hook sits in the PreToolUse chain, which fires on EVERY Bash call, so it must cost microseconds -- one `git rev-parse` and one file read. The expensive half (the whole quick lane) happens in an ordinary Bash call the session makes itself, where the runner's untruncated failure block is readable. Splitting them is the only shape that is both enforceable and cheap.

KEYED ON `HEAD^{tree}`. CI checks out the pushed commit, so the tree object is
exactly what CI will judge. It is also invariant to the dozens of dirty paths this repo's tree normally carries from OTHER live sessions -- keying on the worktree would invalidate the receipt on someone else's keystroke and make it unobtainable, which is how a guard becomes a wall and then gets bypassed.

A TOUCHED SLOW GATE THE LANE DROPPED IS REFUSED until it has passed (agent/plans/PLAN-gate-drop-receipt-verify.md). On 2026-10-03 ci:quick dropped `check:ci-plan-record`, a gate the diff touched, because it wrote the tree; the drop was printed and then lost, this guard allowed the push, and CI run 37129843955 went red on exactly that gate. The runner now records each such gate in the receipt's `droppedTouched`, and a `run.ts --only <id>` run of it merges its result into `droppedVerified`. Every `droppedTouched` id needs a `droppedVerified` entry at the pushed tree with exit code 0, and a receipt with no `droppedTouched` list at all refuses, failing closed exactly as a missing `whole` does.

A RECORD-ONLY COMMIT ADVANCES THE RECEIPT INSTEAD OF VOIDING IT (agent/plans/PLAN-prepush-full-cpu.md part 5). `worklist.py --review-commit` commits agent/reviews/<branch>/ after every reviewed commit, and on 2026-10-05 nine receipts died that way with no code changed. A receipt for tree T now admits a pushed tree reachable from T through the receipt's `advances`: each step's
diff is recomputed here with `git diff --no-renames`, never read from the step's own `paths`, must lie inside the record globs of .ci/policy/record-paths.json as committed in the pushed tree, and every reader gate of the touched globs must appear in the step's `gates` at exit 0, or red and listed in `failed` so the carry rule judges it. A path outside the set still voids the
receipt. The extra git calls run only on the branch that refused before, so the common push stays one `rev-parse` and one file read.

A COMMIT THAT ONLY SHRINKS .ci/config/carried-reds.json ADVANCES TOO (agent/plans/PLAN-ciquick-green-then-batch.md G3). Every tick that changes a carried key set edits that file, and each edit voided the receipt and forced a whole run. The file is a record path with derived readers, but a step touching it is admitted only by `carried_shrink_refusal`: the step touches that file alone, both blobs are read from git and parse, the carry at the new tree excuses nothing the old one did not (an entry added, keys added, or a switch between `"*"` and keys all refuse), and no dropped excuse still covers a red in the receipt. Removing an excuse can only make the push verdict stricter, so a shrink needs no new lane, only its readers; the rule is in this guard, not the policy, so no policy edit turns the carry file into a plain record.

A LIVE BRANCH BEHIND origin/main IS REFUSED TOO (operator finding 2026-10-03). PR #592's first CI run went red only on Quality / Branch because main had moved three commits after 1003-1 was cut, and the push clone's origin/main was stale. Once the receipt allows, `behind_base_refusal` fetches origin/main itself (a stale ref would pass the ancestry test vacuously) and refuses an MMDD-N push to origin that does not contain it, printing the REBASE LOCALLY recipe CI prints. A fetch that fails or times out cannot judge, says so and allows. The refusal says whether the missing base commits are behind or ABSORBED, copies of this branch's own commits left by a rebase-merged parent (`base_split`, the split RB1's lease reader draws).

A LEASE'S PUSH IS JUDGED AGAINST THE LEASE'S BASE (PLAN-two-track-merge-dev RB3). A push typed in a lease tree, which `block_lease_boundary` and the git-level `pre-push` refuse first, is still judged here for every branch it names, of any name, against RB1's base (`lease_base`: the branch the lease record says it was cut from while origin carries it, else main), so a lease that trails its live branch is refused as behind it rather than read against main.

EACH TREE IS JUDGED BY ITS OWN RECEIPT (PLAN-two-track-merge-dev LT6). A push typed in a linked tree of this repository, such as the landing tree that holds the PR branch beside this checkout, reads that tree's HEAD, branch and `.ci/cache/prepush-receipt.json` (`push_tree`); it used to return ALLOW because its toplevel was not CLAUDE_PROJECT_DIR. A push in another repository (another git common directory: a submodule, a scratch repository) is still not this guard's.

=============================================================================
PORT NOTES
=============================================================================

`command -v jq` IS KEPT, AND IT NOW GUARDS NOTHING THIS FILE DOES. The bash reads the receipt with six `jq -r` calls, so it fails open when jq is missing: "FAIL OPEN ON A BROKEN ENVIRONMENT, never on a broken verdict". This port reads the receipt with `json.loads` and needs no jq at all, so the probe is now a pure environment test with no consumer. It is reproduced anyway, because the port is judged by AGREEMENT with its twin and a machine without jq is a case the differential can be handed. Deleting it is a BEHAVIOUR CHANGE and therefore P6's call, made when the last bash guard goes and the chain head's jq check retires with it. Recorded here so that decision is a decision rather than an omission.

THE `jq` FILTERS, spelled out because their defaults are load-bearing: `.headTree // ""`, `.whole // false`, `.exitCode // 1`, `(.failed // []) | join(", ")`, `.dirtyDigest // ""`, `(.blocked // []) | join(", ")`. `//` is falsy-tested, not null-tested, so a `whole` of `false` and a `whole` that is absent produce the same string, which is what makes the narrowed-run refusal fail CLOSED on a receipt shape the runner has not written yet.

WHAT THIS GUARD USED TO INHERIT FROM `shellscan.target_root`: the TAB-after-`-C` defect, reproduced deliberately until Rule T (PLAN-retire-bash-oracles A4) fixed it at its source. See `block_untagged_commit`'s port notes.
"""

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any

from rediacc_hooks import commit_policy, hookio, shellscan, syspath
from rediacc_hooks.guards import _backup_push, _push_receipts, tables
from rediacc_hooks.wellknown import GH_REPO

__getattr__ = tables(
    "block_unverified_push",
    "EDGE_CASES",
    "ENVS",
    "FIXTURES",
    "DROPPED_PLAN_RECORD",
    "FIXTURE_LOCK",
    "V2_FX",
    "V2_FX_INPUTS",
    "V2_FX_SCRIPT",
    "V2_LOCK",
    "V2_PKG",
    "_env",
    "_gate_entry",
    "_repo_v2_carried",
    "_repo_with_forged_advance",
    "_repo_with_receipt",
    "_v2_body",
    "_write_fixture_lock",
)

CHAIN = "pre-bash"
# Re-keyed from 39 to 40 on 2026-09-22 to make room for block_push_to_protected_branch.py at 39: "this branch may not be pushed to at all" is checked before "is this tree gate-verified".
ORDER = 39
# This guard's row of the push-receipt table (`_push_receipts`, box CR6): the receipt files, the admit line and the readers, `read_receipt` and ORIGIN_READERS below, are declared there.
ROW = _push_receipts.row("ci:quick")

# The confinement check is what keeps an advance from being a second way past the tree comparison: without it a step claiming "records only" over a code commit authorises that commit, which is a receipt for a tree no gate judged. The tree comparison itself is pinned by the frozen golden's push-wrong-tree rows.
DEFECT = ("confined = not outside", "confined = True")
# The further mutants the own suite plants (test-block_unverified_push.py), each against the case it names there.
MUTANTS = {
    # LT6: a linked tree of this repository is waved through again, as before the per-tree judgement.
    "sibling-tree-waved": (
        'return target if store and commit_policy.common_dir(target) == store else ""',
        'return ""',
    ),
    # LT6: a linked tree's push is judged against CLAUDE_PROJECT_DIR's receipt and HEAD instead of its own.
    "sibling-judged-as-project": (
        'return target if store and commit_policy.common_dir(target) == store else ""',
        'return project if store and commit_policy.common_dir(target) == store else ""',
    ),
    # LT7: every base commit the branch lacks reads behind, so a rebase-merged parent is no longer read absorbed.
    "absorbed-read-behind": ("    return plus, minus\n", "    return plus + minus, 0\n"),
    # RB3: a push typed in a lease tree is judged as a live-branch push again, so a lease behind the branch it was cut from is admitted.
    "lease-branch-dropped": ("    if lease is not None:\n", "    if False:\n"),
    # R4: the verification arm of a CI-receipt origin is off, so an origin whose bytes no attestation covers, or one signed by another workflow, is admitted. A MUTANTS entry rather than DEFECT: DEFECT is this guard's single slot and holds the confinement plant test_guards_differential depends on.
    "ci-verification-off": ("        why = attested(data, sha, memo)\n", '        why = ""\n'),
}

PUSH_AT_COMMAND_POS = hookio.rx(
    r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+(=[^ ;&|]*|[{S}]+[^ ;&|]+)?)*[{S}]+push([{S}]|$)"
)


REFUSAL_TAIL = """
The pre-push lane exists because three of the five CI reds on PR #579 were
sub-2-second gates that cost ~45 minutes of CI between them. Run it, fix what
it names, then push:

  npm run ci:quick

It is a PARTIAL run and says so: slower gates the change did not touch are
deferred to CI, and it names any it had to defer because a prerequisite was
slow. Every slow gate the change touches runs in the same pass; one it DROPS
(a tree writer outside a disposable clone) is named with the `run.ts --only
<id>` command that clears it, and the push waits for that run. After a commit
confined to .ci/policy/record-paths.json it re-runs only those records'
readers. `npm run ci` is still the whole set.

If a gate it names is not yours -- another session's uncommitted file often
reddens this shared tree -- do not work around it and do not fix their file.
Ask the operator, or leave a [?] worklist item naming the conflict, and
keep working meanwhile:

  .claude/hooks/stop/worklist.py --list --open        # who else is live here

If a gate cannot RUN here (a toolchain this machine lacks), that is not a red
you can fix by pushing: the gate's own message names the install line.
"""


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
    """carried-reds.json as committed at HEAD in `root`, parsed; None when HEAD has no such file.

    A file that does not parse returns `{UNPARSEABLE: <error>}`, never None: None means "nothing carried", and a corrupt carry file read that way stopped carrying what its author thinks it carries without a word (found by the stop hook's carry reader, #e3fca920). `parse_carried` turns the marker into a schema error, which refuses.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", root, "show", "HEAD:%s" % CARRIED_REL],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    # UnicodeDecodeError is a ValueError, so a non-UTF-8 blob is the corrupt-file case below.
    try:
        return json.loads(proc.stdout.decode("utf-8"))
    except ValueError as exc:
        return {UNPARSEABLE: str(exc)[:120]}


#: The key `_carried_at_head` returns a corrupt carry file under; not a key the schema allows, so it can never collide with a real document.
UNPARSEABLE = "__unparseable__"


def _read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Every read in the bash is `jq ... 2>/dev/null`, so an unreadable or malformed file behaves exactly like an absent key: the `//` default.
        return None


#: The substance bar for a keyed entry: the one .dead-bash-allowlist uses and test_gate_dead_bash.py pins with a low-effort-BLOCKER case. A bare "known issue" excuses nothing.
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
    if isinstance(doc, dict) and UNPARSEABLE in doc:
        return {}, "carried-reds.json at HEAD does not parse as JSON: %s" % doc[UNPARSEABLE]
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


def push_source(push_line):
    """The source of the one `<src>:<dst>` refspec in a canonical push line, or "" when it pushes HEAD, a bare ref, or several refspecs. A leading `+` is dropped; a delete (`:dst`) has no source."""
    words = push_line.split()
    try:
        after = words[words.index("push") + 1 :]
    except ValueError:
        return ""
    # The refspecs are the operands after the remote, read by `shellscan.git_push_args` (#e8be3092): a valued option's value (`-o a:b`) is no refspec.
    specs = [w for w in shellscan.git_push_args(after).operands[1:] if ":" in w and "://" not in w]
    if len(specs) != 1:
        return ""
    src = specs[0].split(":", 1)[0].lstrip("+")
    return "" if src in ("", "HEAD") or src.startswith("HEAD") else src


def pushes_only_origin_main(root, pushes):
    """True when every push in the command names an explicit source that resolves to exactly the commit `origin/main` names."""
    if not pushes:
        return False
    sources = {push_source(line) for line in pushes}
    if "" in sources:
        return False
    want = hookio.git_out(
        ["-C", root, "rev-parse", "-q", "--verify", "origin/main^{commit}"], want_rc=True
    )
    if not want:
        return False
    for src in sources:
        got = hookio.git_out(
            ["-C", root, "rev-parse", "-q", "--verify", "%s^{commit}" % src], want_rc=True
        )
        if got != want:
            return False
    return True


def pushed_tree(root, pushes):
    """The tree the push sends, which is the tree the receipt must have judged.

    HEAD's tree unless every push names one and the same explicit source: `git push origin origin/<branch>:main`, the fast-forward fallback, sends the branch's pushed tip whatever the checkout's HEAD is. Measured 2026-10-03 on #591: with an unpushed local commit on top, the receipt for the pushed tip b47559569 was refused as "a different tree" because HEAD's was compared.
    """
    sources = {push_source(line) for line in pushes} if pushes else {""}
    if len(sources) == 1 and "" not in sources:
        got = hookio.git_out(["-C", root, "rev-parse", "%s^{tree}" % sources.pop()], want_rc=True)
        if got:
            return got
    return hookio.git_out(["-C", root, "rev-parse", "HEAD^{tree}"], want_rc=True)


#: The base every live branch is judged against, and the remote it is fetched from.
BASE = "main"
BASE_REMOTE = "origin"
#: Seconds the base fetch may take before the check reports that it cannot judge.
FETCH_TIMEOUT = 20


def rebase_recipe(base, head):
    """The REBASE LOCALLY block `rediacc_ci.quality.branch.recipe(base, head)` prints, line for line.

    REPRODUCED, NOT IMPORTED: a hook cannot import the rediacc_ci package. test-block_unverified_push.py pins this text equal to that function's in a child process, so the two cannot drift apart unnoticed.
    """
    suffix = " (branch: %s)" % head if head else ""
    return [
        "",
        "==============================================",
        "REBASE LOCALLY%s" % suffix,
        "==============================================",
        "",
        "  /branch-rebase %s" % base,
        "",
        "    Rebases the console repo AND every submodule carrying a branch of the",
        "    same name, resolving the gitlink conflicts that a plain 'git rebase'",
        "    gets wrong. It rebases and verifies only; it lands nothing.",
        "",
        "  If the rebase halts on a conflict:",
        "",
        "    .claude/hooks/stop/worklist.py --git rebase-resolve",
        "        reports where it stopped and stages the paths it can decide",
        "        (gitlinks by ancestry, registry unions). All-or-nothing: if any",
        "        path needs you, nothing is written.",
        "    .claude/hooks/stop/worklist.py --git rebase-continue --execute",
        "        continues the rebase once every conflicted path is staged.",
        "",
        "  Prove no commit was lost across the rebase:",
        "",
        "    .claude/hooks/stop/worklist.py --git snapshot > /tmp/pre.snap   # BEFORE",
        "    .claude/hooks/stop/worklist.py --git verify-rebase /tmp/pre.snap origin/%s" % base,
        "",
        "==============================================",
    ]


def _push_remote(args):
    """The remote a `git push <args>` names (its first operand), "" when it names none. Read by `shellscan.git_push_args` (#d5d33bee), so a valued option in any spelling (`--push-o x`, `-ox`, `--repo=x`) never stands in for the remote."""
    operands = shellscan.git_push_args(args).operands
    return operands[0] if operands else ""


def live_pushes(cmd, root, any_branch=False):
    """`[(sha, branch)]` for every push in `cmd` that publishes an MMDD-N branch to origin, or with `any_branch` every branch of any name (a lease's push, `behind_base_refusal`).

    A push naming no refspec (`git push`, `git push origin`) and a `HEAD` destination send the checked-out branch. A source that does not resolve is skipped: git itself refuses that push, so there is no commit to judge. The remote must be spelled `origin` (or left out); a mirror or a URL is another guard's business.
    """
    current = hookio.git_out(["-C", root, "branch", "--show-current"], want_rc=True) or ""
    # Detached prints nothing here, never the literal "HEAD" `rev-parse --abbrev-ref` would; a "HEAD" from any other path is no branch either, so it judges nothing.
    if current == "HEAD":
        current = ""
    out = []
    for run in commit_policy.git_runs(cmd, "push"):
        _, _, args = commit_policy.git_split(run.argv)
        if _push_remote(args) not in ("", BASE_REMOTE):
            continue
        dests = commit_policy.push_destinations(args)
        parsed = shellscan.git_push_args(args)
        if not dests and not any(parsed.on(f) for f in ("delete", "all", "mirror", "tags")):
            dests = [("HEAD", current)]
        for src, named in dests:
            dst = current if named == "HEAD" else named
            if not (dst if any_branch else commit_policy.BRANCH_SHAPE.match(dst or "")):
                continue
            sha = hookio.git_out(
                ["-C", root, "rev-parse", "-q", "--verify", "%s^{commit}" % (src or "HEAD")],
                want_rc=True,
            )
            if sha:
                out.append((sha, dst))
    return out


#: The lease verb's record directory under the main checkout's git dir, one `<id>.json` per lease (.ci/rediacc_ci/dev/worktree_lease.py RECORD_DIR, read the same way by .claude/hooks/stop/wl_worktrees.py `read_records`).
LEASE_RECORD_DIR = "rediacc-worktrees"


def lease_of(root):
    """`(lease id, record)` when `root` sits in a lease tree (`commit_policy.lease_root`), `record` None when no readable record names that tree; None when `root` is no lease."""
    lease = commit_policy.lease_root(root)
    if not lease:
        return None
    main = lease.partition(commit_policy.LEASE_HOLDER)[0]
    for path in sorted(pathlib.Path(main, ".git", LEASE_RECORD_DIR).glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if isinstance(record, dict) and os.path.realpath(str(record.get("path") or "")) == lease:
            return str(record.get("id") or path.stem), record
    return lease.rsplit("/", 1)[-1], None


def _rb1_base_branch():
    """`wl_rebase.base_branch`, RB1's base rule, through a scoped insert of the stop-hook directory (the shape `_policy_rel` uses), so the rule is written down once."""
    inserted = syspath.on_sys_path(syspath.STOP_DIR)
    try:
        import wl_rebase
    finally:
        if inserted and str(syspath.STOP_DIR) in sys.path:
            sys.path.remove(str(syspath.STOP_DIR))
    return wl_rebase.base_branch


def _remote_has(root, branch):
    """True when origin carries `branch`, False when it does not, or the reason git could not say."""
    try:
        got = subprocess.run(
            ["git", "-C", root, "ls-remote", "--heads", BASE_REMOTE, "refs/heads/%s" % branch],
            capture_output=True,
            text=True,
            timeout=FETCH_TIMEOUT,
            check=False,
            env=dict(os.environ, GIT_TERMINAL_PROMPT="0"),
        )
    except subprocess.TimeoutExpired:
        return "ls-remote timed out after %ds" % FETCH_TIMEOUT
    except OSError as exc:
        return str(exc)
    if got.returncode != 0:
        return got.stderr.strip() or "ls-remote exit %d" % got.returncode
    return bool(got.stdout.strip())


def lease_base(root, record):
    """`(base branch, "")` for a lease push, or `("", why)` when origin cannot be read (PLAN-two-track-merge-dev RB3).

    THE BASE IS RB1's (.claude/hooks/stop/wl_rebase.py `base_branch`): the branch the lease was cut from (its record's `cut_from`) while origin still carries it, so the PR branch while its PR is open and the development branch a dev lease trails; `main` when the record names none. A `cut_from` origin no longer carries (the PR branch deleted by its rebase-merge) judges against `main`, where its commits now live.
    """
    cut = str((record or {}).get("cut_from") or "")
    has = _remote_has(root, cut) if cut else False
    if not isinstance(has, bool):
        return "", has
    base = _rb1_base_branch()(has, cut, record)
    if base == cut and not has:
        base = BASE
    return base, ""


def _fetch_base(root, branch):
    """ "" when origin's `branch` was fetched into its remote-tracking ref, else why not."""
    try:
        fetched = subprocess.run(
            [
                "git",
                "-C",
                root,
                "fetch",
                BASE_REMOTE,
                "+refs/heads/%s:refs/remotes/%s/%s" % (branch, BASE_REMOTE, branch),
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=FETCH_TIMEOUT,
            check=False,
            env=dict(os.environ, GIT_TERMINAL_PROMPT="0"),
        )
    except subprocess.TimeoutExpired:
        return "timed out after %ds" % FETCH_TIMEOUT
    except OSError as exc:
        return str(exc)
    return (
        ""
        if fetched.returncode == 0
        else (fetched.stderr.strip() or "exit %d" % fetched.returncode)
    )


def behind_base_refusal(ev, root, cmd):
    """A refusal when a pushed live branch does not contain origin/main, else None.

    WHY. PR #592's first CI run (run 37110619739) went red only on Quality / Branch, "Check whether the branch is behind its base": main had moved three commits after 1003-1 was cut, and the local ci:quick ran in a push clone whose origin/main was stale. The CI gate (.ci/rediacc_ci/quality/branch.py) fetches the base itself before judging, so this does too: a stale `refs/remotes/origin/main` would make the ancestry test pass vacuously.

    A FAILED OR TIMED-OUT FETCH CANNOT JUDGE, and says so and allows: a base check must never become a push outage, the same fail-open-on-a-broken-environment line the receipt arm draws.

    BOTH TREES, ONE BASE (PLAN-two-track-merge-dev LT7, serving RB3). `root` is the tree the push was typed in (`push_tree`), so the PR branch pushed from the landing tree and the development branch pushed from this checkout are each read from their own HEAD; both are MMDD-N, so both are judged against origin/main. Once the PR branch is rebase-merged, the development branch still holds the PR's original commits while main holds their copies: `base_split` reads that ABSORBED rather than behind, and the refusal names which kind it is above CI's recipe and RB4's proof.

    LEASE BRANCHES (PLAN-two-track-merge-dev RB3). A push typed in a lease tree (`lease_of`) judges every branch it names, MMDD-N or not, against the lease's base as RB1 reads it (`lease_base`), never against main alone: a lease cut from the live branch is behind when that branch moved on origin after the cut, however current it is with main. A stacked development branch is no lease and keeps the origin/main judgement, which its stacked PR-branch commits pass by containing main. Origin unable to say whether it still carries the lease's `cut_from` cannot judge, says so and allows, like a failed fetch.
    """
    if hookio.git_out(["-C", root, "remote", "get-url", BASE_REMOTE], want_rc=True) is None:
        return None
    judged = [(sha, branch, BASE) for sha, branch in live_pushes(cmd, root)]
    lease = lease_of(root)
    if lease is not None:
        lease_pushed = live_pushes(cmd, root, any_branch=True)
        base, why = lease_base(root, lease[1]) if lease_pushed else (BASE, "")
        if why:
            ev.warn(
                "NOTE: cannot judge whether lease %s's push is behind its base: origin could not"
                " say whether it still carries `%s`" % (lease[0], (lease[1] or {}).get("cut_from"))
            )
            ev.warn("  (%s)." % why.splitlines()[-1])
            ev.warn(
                "  Allowed. The lease's landing still replays its commits onto the live branch."
            )
            return None
        judged = [(sha, "%s (lease %s)" % (branch, lease[0]), base) for sha, branch in lease_pushed]
    if not judged:
        return None
    fetched = {}
    for base in sorted({b for _sha, _branch, b in judged}):
        failure = _fetch_base(root, base)
        if failure:
            ev.warn(
                "NOTE: cannot judge whether this push is behind %s/%s: fetching it failed"
                % (BASE_REMOTE, base)
            )
            ev.warn("  (%s)." % failure.splitlines()[-1])
            ev.warn(
                "  Allowed. CI's Quality / Branch step still checks it, and a red there costs a round."
            )
            return None
        fetched[base] = "%s/%s" % (BASE_REMOTE, base)
    for sha, branch, base in judged:
        base_ref = fetched[base]
        if (
            hookio.git_out(["-C", root, "merge-base", "--is-ancestor", base_ref, sha], want_rc=True)
            is not None
        ):
            continue
        missing = hookio.git_out(["-C", root, "rev-list", "--count", "%s..%s" % (sha, base_ref)])
        recent = hookio.git_out(["-C", root, "log", "--oneline", "-5", "%s..%s" % (sha, base_ref)])
        split = base_split(root, sha, base_ref)
        if split is None:
            head = "%s (%s) is %s commit(s) behind %s, freshly fetched.\n" % (
                branch,
                sha[:12],
                missing or "?",
                base_ref,
            )
        elif split[0] == 0:
            head = (
                "%s (%s) does not contain %s, freshly fetched, and every one of the %d commit(s)\n"
                "  it lacks is a patch-equivalent copy of a commit on this branch: a rebase-merged\n"
                "  parent, read ABSORBED, not behind. The rebase drops the copies and replays only\n"
                "  this branch's own commits.\n" % (branch, sha[:12], base_ref, split[1])
            )
        else:
            head = "%s (%s) is %d commit(s) behind %s, freshly fetched%s.\n" % (
                branch,
                sha[:12],
                split[0],
                base_ref,
                (
                    ", and %d more absorbed (patch-equivalent copies of this branch's commits)"
                    % split[1]
                )
                if split[1]
                else "",
            )
        # A lease push is labelled "<branch> (lease <id>)": the label is for the message, the bare ref name is for the recipe.
        bare = branch.split(" (lease ", 1)[0]
        ci_line = (
            "  The landing would replay the lease's commits onto %s, so this is judged against it (CI's Quality / Branch step judges only origin/%s).\n"
            % (base, BASE)
            if bare != branch
            else "  CI's Quality / Branch step refuses exactly this, after a ~15-minute round.\n"
        )
        return "%s%s  Recent commits on %s not in this branch:\n%s\n%s\n%s" % (
            head,
            ci_line,
            base,
            "\n".join("    %s" % line for line in recent.splitlines()),
            "\n".join(rebase_recipe(base, bare)),
            "\n".join(line.replace("origin/%s" % BASE, base_ref) for line in REBASE_PROOF),
        )
    return None


#: The post-rebase proof RB4 added (`worklist.py --git rebase-proof`, .claude/hooks/stop/wl_rebase.py `rebase_proof`), printed under CI's recipe: it names every commit whose patch moved in a resolved conflict and every review record the rebase owes. The same commands as the lease block `wl_rebase.REBASE_RECIPE` (RB2) prints; test-block_unverified_push.py pins each command line here to that text.
REBASE_PROOF = [
    "  Then, from the snapshot taken BEFORE the rebase, the commits whose patch moved and the review",
    "  records the rewritten commits owe (PLAN-two-track-merge-dev RB4):",
    "",
    "    .claude/hooks/stop/worklist.py --git rebase-proof <that snapshot> origin/%s" % BASE,
    "    python3 .claude/hooks/stop/wl_review.py --check",
    "",
]


def base_split(root, sha, base_ref):
    """`(behind, absorbed)` for the commits of `base_ref` that `sha` lacks, None when git cannot say.

    The split RB1's lease reader draws (.claude/hooks/stop/wl_rebase.py `behind_base`), read the same way: `git cherry <sha> <base_ref>` marks a base commit `-` when this branch holds a patch-equivalent commit (absorbed: a rebase-merged parent, whose copies on main carry new shas) and `+` when it holds none (behind). REPRODUCED, NOT CALLED: `behind_base` fetches with its own 60-second budget and no prompt guard, and this guard already fetched under FETCH_TIMEOUT with GIT_TERMINAL_PROMPT=0. test-block_unverified_push.py pins the two verdicts equal on the same repositories. Both kinds still refuse: CI's Quality / Branch step judges ancestry alone, so an absorbed-only branch is red there too; the split only says which rebase it is.
    """
    out = hookio.git_out(["-C", root, "cherry", sha, base_ref], want_rc=True)
    if out is None:
        return None
    lines = out.splitlines()
    plus = sum(1 for line in lines if line.startswith("+"))
    minus = sum(1 for line in lines if line.startswith("-"))
    return plus, minus


#: The record set: globs a commit may touch without voiding a receipt, each with the gates that read it. Read from the PUSHED tree, never the worktree, for the reason carried-reds.json is read from HEAD.
def _policy_rel(name):
    """`.ci/policy/<name>` through rediacc_ci.policy_paths, so the policy directory is written down once (check:ci-policy-inventory). A scoped, removed sys.path insert, the shape block_host_toolchain_run._ci_seams uses: a hook cannot import rediacc_ci at module level, and a permanent `.ci` entry would leak into every later guard the dispatcher runs."""
    cipath = str(hookio.repo_root() / ".ci")
    inserted = syspath.on_sys_path(cipath)
    try:
        from rediacc_ci.policy_paths import policy_rel
    finally:
        if inserted and cipath in sys.path:
            sys.path.remove(cipath)
    return policy_rel(name)


RECORD_POLICY_REL = _policy_rel("record-paths.json")
RECORD_POLICY_VERSION = 1
#: A tree object name, SHA-1 or SHA-256. Anything else in an advance is refused before git sees it, so an option-shaped value cannot become an argument to `git diff`.
TREE_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def record_glob_re(glob):
    """`glob` as an anchored regex over a repo-relative path: `**` spans directories, `*` and `?` do not.

    The same three rules .ci/scripts/quality/check_record_paths.py applies (`glob_re` there); .ci/rediacc_ci/tests/gates/test_gate_record_paths.py pins the two equal on one corpus, because a hook cannot import the rediacc_ci package and a gate should not import a hook.
    """
    out = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("^%s$" % "".join(out))


def record_of(path, records):
    """The record entry whose glob covers `path` and none of whose `except` globs does, else None."""
    for rec in records:
        if not record_glob_re(rec["glob"]).match(path):
            continue
        if any(record_glob_re(x).match(path) for x in rec["except"]):
            continue
        return rec
    return None


def parse_record_policy(doc):
    """record-paths.json -> ([{glob, except, readers}], schema_error or None). A malformed policy judges nothing, so it is an error, never an empty set.

    The shape the runner's `parseRecordPolicy` (scripts/ci-runner/run.ts) reads too: `{"version": 1, "records": [{"glob", "except": [globs], "readers": [{"id", "evidence"}]}]}`. Other keys (`probes`, `notReaders`) are check:ci-record-paths' own.
    """
    if not isinstance(doc, dict) or doc.get("version") != RECORD_POLICY_VERSION:
        return [], '%s is not `"version": %d`' % (RECORD_POLICY_REL, RECORD_POLICY_VERSION)
    raw = doc.get("records")
    if not isinstance(raw, list) or not raw:
        return [], "%s has no `records` list" % RECORD_POLICY_REL
    records = []
    for i, rec in enumerate(raw):
        glob = rec.get("glob") if isinstance(rec, dict) else None
        excepted = rec.get("except", []) if isinstance(rec, dict) else None
        readers = rec.get("readers") if isinstance(rec, dict) else None
        if (
            not isinstance(glob, str)
            or not glob
            or not isinstance(excepted, list)
            or not all(isinstance(x, str) and x for x in excepted)
            or not isinstance(readers, list)
            or not all(
                isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"] for r in readers
            )
        ):
            return (
                [],
                "%s record %d needs a `glob`, an `except` list and a `readers` list of {id}"
                % (
                    RECORD_POLICY_REL,
                    i,
                ),
            )
        records.append(
            {"glob": glob, "except": excepted, "readers": sorted(r["id"] for r in readers)}
        )
    return records, None


def _record_policy_at(root, tree):
    """(records, error) for the record policy as committed in `tree`."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "show", "%s:%s" % (tree, RECORD_POLICY_REL)],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return [], "git could not read %s (%s)" % (RECORD_POLICY_REL, exc)
    if proc.returncode != 0:
        return [], "the pushed tree has no %s" % RECORD_POLICY_REL
    try:
        doc = json.loads(proc.stdout.decode("utf-8"))
    except ValueError:
        return [], "%s in the pushed tree does not parse" % RECORD_POLICY_REL
    return parse_record_policy(doc)


def _diff_names(root, frm, to):
    """Every path that differs between two trees, renames split into delete plus add (else a code file renamed into a record directory would list only its record-side name), or None when git cannot diff them."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "diff", "--name-only", "--no-renames", "-z", frm, to],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


#: The exit code the runner records for a reader that could not run (a missing toolchain), as opposed to one that ran and failed.
COULD_NOT_RUN = 77


def keyed_carry_vouches(reader, step, judged):
    """True when a red `reader` at an advance step is exactly the receipt's carried-by-key red: the step recorded findings for it, they equal (as a set) the receipt's findings for that gate, and carried-reds.json at HEAD carries every key. PURE. DEFECT-style plants in test-block_unverified_push.py force this to True."""
    recorded = step.get("findings")
    recorded = recorded.get(reader) if isinstance(recorded, dict) else None
    receipt_keys = judged["findings"].get(reader)
    carried = judged["carried"].get(reader)
    if not (isinstance(recorded, list) and isinstance(receipt_keys, list) and recorded):
        return False
    if not all(isinstance(k, str) for k in recorded + receipt_keys):
        return False
    if set(recorded) != set(receipt_keys):
        return False
    return isinstance(carried, set) and set(recorded) <= carried


def carried_widening(old, new):
    """Every way the carry map `new` excuses more than `old` (both `parse_carried` maps), one phrase each; [] when `new` carries nothing `old` did not. PURE. A test plant forces it to [] to show the addition world's refusal is this check at work.

    Judged on the EFFECTIVE carry, after the reason bar, so an entry whose reason is lengthened past REASON_MIN counts as added, and a reworded reason that changes nothing carried counts as nothing. A switch between `"*"` and keys is refused in both directions: it is a rewrite of what the gate is excused for, and a rewrite is when a full run should judge it.
    """
    out = []
    for gate in sorted(new):
        was, now = old.get(gate), new[gate]
        if was is None:
            out.append("adds a carry for %s" % gate)
        elif (was == "*") != (now == "*"):
            out.append('switches %s between "*" and keys' % gate)
        elif isinstance(now, set) and isinstance(was, set) and now - was:
            out.append("adds key(s) to %s: %s" % (gate, ", ".join(sorted(now - was))))
    return out


def removed_still_red(old, new, judged):
    """Every excuse `old` holds and `new` drops that still covers a red in the receipt, one phrase each. PURE.

    A whole-gate removal is still red when the receipt lists the gate in `failed`. A key removal is still red when the gate is in `failed` and the receipt's findings for it hold the key, or hold no parsable list at all, which cannot show the key gone.
    """
    out = []
    for gate in sorted(old):
        was, now = old[gate], new.get(gate)
        if gate not in judged["failed"]:
            continue
        if was == "*":
            if now is None:
                out.append("%s (its whole-gate carry)" % gate)
            continue
        dropped = was - now if isinstance(now, set) else set(was) if now is None else set()
        if not dropped:
            continue
        emitted = judged["findings"].get(gate)
        if not isinstance(emitted, list):
            out.append(
                "%s (the receipt records no finding keys to show %s gone)"
                % (gate, ", ".join(sorted(dropped)))
            )
            continue
        hit = sorted(dropped & {k for k in emitted if isinstance(k, str)})
        if hit:
            out.append("%s: %s" % (gate, ", ".join(hit)))
    return out


def _carried_at_tree(root, tree):
    """(`parse_carried` map, None) for carried-reds.json as committed in `tree`, or (None, why). An absent or broken file is a why, never an empty map: a step that creates or corrupts the carry file is not a shrink."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "show", "%s:%s" % (tree, CARRIED_REL)],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return None, "git could not read %s at %s (%s)" % (CARRIED_REL, tree[:12], exc)
    if proc.returncode != 0:
        return None, "tree %s has no %s" % (tree[:12], CARRIED_REL)
    # Bytes, decoded here: a blob that is not valid UTF-8 is a why naming it, never a UnicodeDecodeError out of the guard.
    try:
        text = proc.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, "%s at tree %s is not valid UTF-8 (%s)" % (CARRIED_REL, tree[:12], exc)
    try:
        doc = json.loads(text)
    except ValueError as exc:
        doc = {UNPARSEABLE: str(exc)}
    carried, error = parse_carried(doc)
    if error is not None:
        return None, "at tree %s: %s" % (tree[:12], error)
    return carried, None


def carried_shrink_refusal(root, frm, to, paths, judged):
    """Why a step touching carried-reds.json is not a SHRINK of it, else None (G3, agent/plans/PLAN-ciquick-green-then-batch.md).

    The file is a record (.ci/policy/record-paths.json) only for a commit that can make the push verdict stricter and never laxer: the step touches that file and nothing else, both trees carry a well-formed file, read here from git rather than from any claim in the step, `new` excuses nothing `old` did not (`carried_widening`), and no excuse it drops still covers a red in the receipt (`removed_still_red`; carried_verdict would refuse that push anyway, and here it is named at the step). This rule holds whatever the record policy says, so a policy edit cannot turn the carry file into a plain record.
    """
    others = sorted(p for p in paths if p != CARRIED_REL)
    if others:
        return (
            "it edits %s together with %d other path(s) (%s); a carry-file step must touch that file alone.\n"
            "  Commit the shrink of the carry file on its own, or re-run npm run ci:quick."
            % (CARRIED_REL, len(others), ", ".join(others[:5]))
        )
    old, why = _carried_at_tree(root, frm)
    if why is None:
        new, why = _carried_at_tree(root, to)
    if why is not None:
        return "it edits %s, and the edit cannot be judged a shrink: %s." % (CARRIED_REL, why)
    widened = carried_widening(old, new)
    if widened:
        return (
            "it WIDENS %s: %s.\n"
            "  A step may only remove carries; an added or widened excuse needs a new gate run."
            % (CARRIED_REL, "; ".join(widened))
        )
    red = removed_still_red(old, new, judged)
    if red:
        return (
            "it removes excuses from %s that still cover reds in the receipt: %s.\n"
            "  Fix the finding first, or keep its carry." % (CARRIED_REL, "; ".join(red))
        )
    return None


def step_refusal(root, step, records, judged):
    """Why one advance does not carry the receipt from its `from` to its `to`, else None.

    The step's `paths` is never read: the diff is recomputed, so a runner (or a hand) that wrote "records only" over a code commit is caught here.

    A READER THAT IS NOT GREEN AT THE STEP. An advance never touches the receipt's `failed`, `findings` or `blocked`, which still describe `headTree`; it records each reader's exit code in `gates` and the finding keys the reader printed in `findings` (scripts/ci-runner/run.ts `runAdvance`). A red reader is admitted when it was already red at `headTree` (`judged["failed"]`) AND either carried-reds.json at HEAD carries it whole (`"*"`), or the step recorded its findings, they equal as a set the receipt's own findings for that gate, and carried-reds.json at HEAD carries every one of those keys (`keyed_carry_vouches`). A reader red with a key the receipt never had, or one whose findings the step did not record (an older runner), is refused. A reader that could not run (exit 77) is admitted only when the receipt already lists it as `blocked`, the state the 2026-08-27 ruling warns on rather than refuses.
    """
    frm, to = step["from"], step["to"]
    paths = _diff_names(root, frm, to)
    if paths is None:
        return "git cannot diff %s..%s here" % (frm[:12], to[:12])
    matched = {p: record_of(p, records) for p in paths}
    outside = sorted(p for p, rec in matched.items() if rec is None)
    # THE CONFINEMENT CHECK. DEFECT plants `True` here, and the code-commit cases of test-block_unverified_push.py must then go green-for-the-wrong-reason and red the suite.
    confined = not outside
    if not confined:
        return (
            "its diff touches %d path(s) outside the record set (%s): %s%s.\n"
            "  An advance covers record-only commits; anything else needs a new gate run."
            % (
                len(outside),
                RECORD_POLICY_REL,
                ", ".join(outside[:5]),
                " and %d more" % (len(outside) - 5) if len(outside) > 5 else "",
            )
        )
    if CARRIED_REL in paths:
        why = carried_shrink_refusal(root, frm, to, paths, judged)
        if why is not None:
            return why
    readers = sorted({r for rec in matched.values() if rec is not None for r in rec["readers"]})
    gates = step.get("gates")
    gates = gates if isinstance(gates, dict) else {}
    missing = []
    unjudged = []
    for reader in readers:
        code = gates.get(reader)
        if not isinstance(code, int) or isinstance(code, bool):
            missing.append(reader)
            continue
        passed = code == 0
        blocked_already = code == COULD_NOT_RUN and reader in judged["blocked"]
        red_at_receipt = reader in judged["failed"]
        carried_whole = red_at_receipt and reader in judged["star"]
        carried_keys = red_at_receipt and keyed_carry_vouches(reader, step, judged)
        if not (passed or blocked_already or carried_whole or carried_keys):
            unjudged.append("%s (exit %d)" % (reader, code))
    if missing:
        return (
            "the readers of the records it touched were not re-run at that tree: %s.\n"
            "  A record's readers are the gates whose verdict depends on it (%s)."
            % (", ".join(missing), RECORD_POLICY_REL)
        )
    if unjudged:
        return (
            "these readers did not pass at that tree: %s.\n"
            "  An advance admits a red reader only when it was already red at the receipt's tree\n"
            '  and .ci/config/carried-reds.json carries it whole ("*"), or carries by key exactly the\n'
            "  findings the step recorded for it, which must equal the receipt's own. A reader that\n"
            "  could not run is admitted only when the receipt lists it as blocked.\n"
            "  Fix it, or re-run npm run ci:quick." % ", ".join(unjudged)
        )
    return None


def advance_chain(root, receipt, start, end):
    """(trees from `start` to `end` along verified advances, None) when the receipt's `advances` reach `end`; (None, refusal) when they do not; (None, None) when the receipt holds no advance at all, so the caller keeps its own unchanged refusal.

    Steps are read in order and a step counts only when its `from` is a tree an earlier verified step (or the receipt itself) reached, which admits both a chain (T0 to T1 to T2) and repeated advances from the receipt tree (T0 to T1, T0 to T2).
    """
    steps = receipt.get("advances") if isinstance(receipt, dict) else None
    if not isinstance(steps, list) or not steps:
        return None, None
    head = (
        "the gate run judged tree %s; this push sends %s, and the receipt's advances do not reach it"
        % (
            start,
            end,
        )
    )
    records, error = _record_policy_at(root, end)
    if error is not None:
        return None, "%s: %s." % (head, error)
    judged: dict[str, Any] = {}
    for key in ("failed", "blocked"):
        listed = receipt.get(key)
        judged[key] = (
            {g for g in listed if isinstance(g, str)} if isinstance(listed, list) else set()
        )
    carried, _schema_error = parse_carried(_carried_at_head(root))
    judged["star"] = {g for g, keys in carried.items() if keys == "*"}
    judged["carried"] = {g: keys for g, keys in carried.items() if isinstance(keys, set)}
    rf = receipt.get("findings")
    judged["findings"] = rf if isinstance(rf, dict) else {}
    parent: dict[str, str | None] = {start: None}
    problems = []
    for i, step in enumerate(steps):
        frm = step.get("from") if isinstance(step, dict) else None
        to = step.get("to") if isinstance(step, dict) else None
        if not (
            isinstance(frm, str)
            and isinstance(to, str)
            and TREE_RE.match(frm)
            and TREE_RE.match(to)
        ):
            problems.append("advance %d does not name two tree hashes" % i)
            continue
        if frm not in parent:
            problems.append(
                "advance %d starts at %s, which no verified step reached" % (i, frm[:12])
            )
            continue
        why = step_refusal(root, step, records, judged)
        if why is not None:
            problems.append("advance %d (%s..%s): %s" % (i, frm[:12], to[:12], why))
            continue
        parent.setdefault(to, frm)
        if to == end:
            break
    if end not in parent:
        return None, "%s:\n%s\n  Run npm run ci:quick at this HEAD." % (
            head,
            "\n".join("    %s" % p for p in problems) or "    no advance ends at the pushed tree",
        )
    trees = []
    node = end
    while node is not None:
        trees.append(node)
        node = parent[node]
    return list(reversed(trees)), None


WHOLE_LANE = "ci:quick will run the whole lane."
RECORD_ONLY = "ci:quick will advance (record-only)."


def no_advance_hint(root, receipt, r_tree, tree):
    """Why a receipt with no `advances` does not reach `tree`, and which run `npm run ci:quick` will do about it: indented lines ending in WHOLE_LANE or RECORD_ONLY (PLAN-stop-hook-retro-20261123 R20261123.5, D5; a wrong guess cost 27 minutes on 43201205).

    The run is the runner's own decision (scripts/ci-runner/run.ts planAdvance), restated here in its order: a receipt that is not whole, or red with no usable `failed` list, runs the lane; so does a pushed tree whose record policy does not read, a diff git cannot list, a path outside the record set, or a failed gate that reads a touched record. A carried-reds.json change that widens an excuse is named too: this guard's step rule refuses an advance over it (`carried_shrink_refusal`), so the push needs a whole-lane receipt. Everything else advances.

    THE RECORD SET IS READ, NEVER RESTATED: .ci/policy/record-paths.json as the pushed tree commits it (`_record_policy_at`, the copy the advance check and the runner read), so a glob added there (agent/*/STATE.md, R20261123.4) changes this answer with no edit here.
    """

    def whole(*lines):
        return "".join("  %s\n" % line for line in lines) + "  %s" % WHOLE_LANE

    if not isinstance(receipt, dict) or receipt.get("whole") is not True:
        return whole("The receipt is not a whole-lane run, so there is nothing to advance.")
    failed = receipt.get("failed")
    if failed is not None and not (
        isinstance(failed, list) and all(isinstance(g, str) for g in failed)
    ):
        return whole("The receipt's `failed` is not a list of gate ids.")
    failed = failed or []
    if receipt.get("exitCode") != 0 and not failed:
        return whole("The receipt is red and lists no failed gate to judge the records against.")
    records, error = _record_policy_at(root, tree)
    if error is not None:
        return whole("The record set cannot be read: %s." % error)
    paths = _diff_names(root, r_tree, tree) if TREE_RE.match(r_tree or "") else None
    if not paths:
        return whole("git cannot list what changed between %s and %s here." % (r_tree, tree))
    matched = {p: record_of(p, records) for p in paths}
    outside = sorted(p for p, rec in matched.items() if rec is None)
    if outside:
        return whole(
            "Changed since the receipt, outside the record set (%s): %s%s."
            % (
                RECORD_POLICY_REL,
                ", ".join(outside[:10]),
                " and %d more" % (len(outside) - 10) if len(outside) > 10 else "",
            )
        )
    readers = {r for rec in matched.values() if rec is not None for r in rec["readers"]}
    red = sorted(readers & set(failed))
    if red:
        return whole(
            "The receipt is red on %s, which read(s) the changed record path(s)." % ", ".join(red)
        )
    if CARRIED_REL in paths:
        old, why = _carried_at_tree(root, r_tree)
        if why is None:
            new, why = _carried_at_tree(root, tree)
        if why is not None:
            return whole("carried-reds.json cannot be judged a shrink: %s." % why)
        widened = carried_widening(old, new)
        if widened:
            return whole("carried-reds.json widened: %s." % "; ".join(widened))
    return "  Every path changed since the receipt is a record (%s): %d path(s).\n  %s" % (
        RECORD_POLICY_REL,
        len(paths),
        RECORD_ONLY,
    )


def dropped_verdict(receipt, tree, trees=None):
    """A refusal naming every touched-but-dropped gate with no passing run at `tree`, else None. PURE, like `carried_verdict`.

    `droppedTouched` is the runner's list of slow gates the change set touched and the quick lane did not run; `droppedVerified[id]` is a `run.ts --only <id>` run merged into the same receipt. An id counts as proven only when that entry names `tree` and exit code 0. A failed re-run is also in `failed`, which `carried_verdict` judges. A receipt with no `droppedTouched` list (a runner older than the field) refuses: a guard that read absence as "nothing dropped" would fail open on exactly the receipts that cannot say.

    `trees` is the verified advance chain ending at `tree` (`advance_chain`), when the push rides one. A run at any tree on it counts: every step is confined to the record set, so a gate that reads no record judged the same inputs, and a gate that does read one was re-run at that step or the chain would not exist.
    """
    judged_at = set(trees) if trees else {tree}
    dropped = receipt.get("droppedTouched") if isinstance(receipt, dict) else None
    if not isinstance(dropped, list):
        return (
            "that receipt has no `droppedTouched` list, so it cannot say whether the lane\n"
            "  dropped a slow gate the change touched. It predates the field; re-run npm run ci:quick."
        )
    verified = receipt.get("droppedVerified")
    verified = verified if isinstance(verified, dict) else {}
    outstanding = []
    for entry in dropped:
        gate = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(gate, str) or not gate:
            outstanding.append(
                "    %s (malformed entry)" % json.dumps(entry, separators=(",", ":"))
            )
            continue
        run_ = verified.get(gate)
        code = run_.get("exitCode") if isinstance(run_, dict) else None
        ran_here = (
            isinstance(run_, dict)
            and run_.get("headTree") in judged_at
            and isinstance(code, int)
            and not isinstance(code, bool)
        )
        if ran_here and code == 0:
            continue
        # A RED RE-RUN AT THIS TREE IS A KNOWN FAILURE, NOT AN UNKNOWN ONE, once the merge has also listed it in `failed`: from there `carried_verdict` judges it like any whole-lane failure, so it refuses unless carried-reds.json carries it with a reason. Without this a gate whose host cannot run every case (check:ci-pytest's WSL-only and live-container skips, 2026-10-04) had no path to a push at all.
        if ran_here and gate in (receipt.get("failed") or []):
            continue
        # A RE-RUN THAT COULD NOT RUN HERE (exit 77, the host lacks what the gate needs, such as a native-Linux docker for check:ci-proxy-wrangler-dev-e2e) is merged into `blocked`, and from there it is judged like a blocked gate of the whole lane: warned on, never counted green.
        if ran_here and code == COULD_NOT_RUN and gate in (receipt.get("blocked") or []):
            continue
        reason = entry.get("reason") if isinstance(entry.get("reason"), str) else "(no reason)"
        command = (
            entry.get("run")
            if isinstance(entry.get("run"), str)
            else "npx tsx scripts/ci-runner/run.ts --only %s" % gate
        )
        outstanding.append("    %s: %s\n      %s" % (gate, reason, command))
    if not outstanding:
        return None
    return (
        "the gate run DROPPED %d slow gate(s) the change touched that have not passed here since:\n"
        "%s\n"
        "  CI runs them for real. Run each command above; a pass merges into this receipt\n"
        "  (droppedVerified) and clears it. On 2026-10-03 exactly such a drop went red in CI."
        % (len(outstanding), "\n".join(outstanding))
    )


# The receipt verdicts (scripts/ci-runner/run.ts `ReceiptGate.verdict`) of a gate that did not run in the lane: deferred by the selection, CI-only, or blocked (it could not run here, or a prerequisite failed). Whether a blocked gate may ride the push at all is `unjudged_blocked`'s question, not this one's.
NOT_RUN_VERDICTS = ("deferred", "ciOnly", "blocked")


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
    # NOT FAILING IS NOT THE SAME AS NOT RUN. The quick lane defers a slow gate whose inputs the push does not touch and records it as `deferred` (a `ciOnly` or `blocked` gate likewise never ran here); such a gate has not gone green, so its carry is not stale. Without this a push whose diff touched nothing check:ci-pytest reads was refused for carrying that gate's host-only skips (2026-10-13). A carried gate the receipt does not list at all stays stale.
    gates = receipt.get("gates") if isinstance(receipt, dict) else None
    gates = gates if isinstance(gates, dict) else {}
    not_run = {
        g
        for g, entry in gates.items()
        if isinstance(entry, dict) and entry.get("verdict") in NOT_RUN_VERDICTS
    }
    stale = "".join(" %s" % g for g in sorted(carried) if g not in failed and g not in not_run)
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


# --- receipt v2 (PLAN-fast-loop Part 1, F3) ---------------------------------------------
# A v2 receipt records, per gate, a verdict and (for a gate the runner CARRIED instead of re-running) the hashes of what the gate reads. The functions below implement the plan's frozen "Hash contract" byte for byte; scripts/ci-runner/input-hash.ts implements the same text, and the parity test compares the two on one corpus. v2_verdict recomputes a carried gate's hashes at the PUSHED tree, so a carry the runner mis-judged, or a hand-edited receipt, is refused here rather than judged by CI.
RECEIPT_SCHEMA = 2
LOCK_REL = "scripts/ci-runner/gates.lock.json"
CARRY_EXEMPT_REL = _policy_rel("carry-exempt.json")
V2_VERDICTS = ("ok", "fail", "blocked")
V2_REGEN = ROW.admit[0]


def v2_canon(x):
    """JSON with keys sorted at every depth, no spaces, non-ASCII kept as UTF-8."""
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def v2_sha(s):
    """Lowercase hex sha256 of the UTF-8 bytes."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def v2_def_hash(entry, scripts):
    """The gate's lock entry plus the npm script texts it runs: a changed gate re-runs."""
    return v2_sha("def\n" + v2_canon(entry) + "\n" + v2_canon(scripts))


_GLOB_RES: dict[str, re.Pattern[str]] = {}


def v2_match_glob(glob, path):
    """`**` matches any run of characters including `/`, `*` any run without `/`, every other character (`?` included) is literal."""
    rx = _GLOB_RES.get(glob)
    if rx is None:
        out = []
        i = 0
        while i < len(glob):
            if glob.startswith("**", i):
                out.append(".*")
                i += 2
            elif glob[i] == "*":
                out.append("[^/]*")
                i += 1
            else:
                out.append(re.escape(glob[i]))
                i += 1
        rx = _GLOB_RES[glob] = re.compile("".join(out), re.DOTALL)
    return rx.fullmatch(path) is not None


def v2_ls_tree(root, tree):
    """`git ls-tree -r --full-tree` of one tree as (mode, type, oid, path); a gitlink is `160000 commit <oid>`. Empty when git cannot answer."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "ls-tree", "-r", "-z", "--full-tree", tree],
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    out = []
    for rec in proc.stdout.decode("utf-8", "surrogateescape").split("\0"):
        meta, sep, path = rec.partition("\t")
        parts = meta.split(" ")
        if sep and len(parts) == 3:
            out.append((parts[0], parts[1], parts[2], path))
    return out


def _entry_matches(globs, e):
    """A glob matches the path, or (input-hash.ts `entryMatches`) names a gitlink directory bare or as `<gitlink>/**`, which reaches the gitlink entry itself."""
    if any(v2_match_glob(gl, e[3]) for gl in globs):
        return True
    return e[0] == "160000" and any(gl == e[3] or gl == e[3] + "/**" for gl in globs)


def v2_input_lines(entries, globs, files):
    """`<mode> <oid>\\t<path>` (no newline) for every entry a glob matches or `files` names, sorted by path bytes."""
    named = set(files)
    picked = [e for e in entries if e[3] in named or _entry_matches(globs, e)]
    picked.sort(key=lambda e: e[3].encode("utf-8", "surrogateescape"))
    return ["%s %s\t%s" % (e[0], e[2], e[3]) for e in picked]


def v2_list_lines(entries, dirs):
    """`list\\t<dir>\\t<child>\\t<kind>` per immediate tracked child of each listed directory ('' is the root): kind is the blob mode, `tree` for a subdirectory, `commit` for a gitlink. input-hash.ts `listLines`."""
    out = []
    for d in dict.fromkeys(dirs):
        prefix = "" if d == "" else d + "/"
        seen = set()
        for e in entries:
            p = e[3]
            if not p.startswith(prefix) or len(p) == len(prefix):
                continue
            rest = p[len(prefix) :]
            child, slash, _ = rest.partition("/")
            if child in seen:
                continue
            seen.add(child)
            kind = "tree" if slash else ("commit" if e[0] == "160000" else e[0])
            out.append("list\t%s\t%s\t%s" % (d, child, kind))
    return out


def v2_name_lines(entries, globs):
    """`name\\t<mode>\\t<path>` for every tracked entry a `names` glob matches. input-hash.ts `nameLines`."""
    globs = list(dict.fromkeys(globs))
    if not globs:
        return []
    return [
        "name\t%s\t%s" % (e[0], e[3]) for e in entries if any(v2_match_glob(g, e[3]) for g in globs)
    ]


def v2_resolve_ref(root, ref):
    """The commit `ref` resolves to in `root`, or None. input-hash.ts `gitResolveRef`."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "rev-parse", "--verify", "--quiet", ref + "^{commit}"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    out = proc.stdout.decode("utf-8", "replace").strip()
    return out if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", out) else None


def v2_extra_lines(entries, lists=(), names=(), refs=(), root=".", resolve=None):
    """The name-shaped lines of PLAN-ciquick-cpu W2.4 (`list`, `name`, `ref`) and the first ref that resolves to nothing, or None. input-hash.ts builds the same lines in `computeGateHashes`; a ref that does not resolve is an unknown input there (`ref-unresolved:<name>`) and a refusal here."""
    resolve = resolve or (lambda r: v2_resolve_ref(root, r))
    extras = v2_list_lines(entries, lists) + v2_name_lines(entries, names)
    unresolved = None
    for r in refs:
        at = resolve(r)
        if at is None:
            unresolved = unresolved or r
            continue
        extras.append("ref\t%s\t%s" % (r, at))
    return extras, unresolved


def _line_path(line):
    return line.partition("\t")[2].encode("utf-8", "surrogateescape")


def v2_files_hash(lines, extras=()):
    """sha of `files\\n` and the path lines sorted by path bytes; with name-shaped `extras`, those deduplicated, sorted by whole bytes, after `extra\\n`. No extras is the pre-W2.4 preimage exactly. input-hash.ts `filesHash`."""
    base = "files\n" + "".join(line + "\n" for line in sorted(lines, key=_line_path))
    if not extras:
        return v2_sha(base)
    tail = sorted(set(extras), key=lambda x: x.encode("utf-8", "surrogateescape"))
    return v2_sha(base + "extra\n" + "".join(x + "\n" for x in tail))


def _show_at(root, tree, rel):
    """`git show <tree>:<rel>` as text, or None when the tree has no such file."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "show", "%s:%s" % (tree, rel)], capture_output=True, check=False
        )
    except OSError:
        return None
    return proc.stdout.decode("utf-8") if proc.returncode == 0 else None


#: Why an exempt gate's verdict moves with no tracked input moving; the twin of EXEMPT_KINDS in scripts/ci-runner/input-hash.ts.
EXEMPT_KINDS = ("clock", "history", "network", "cache")


def _exempt_ids(doc):
    """Ids named by .ci/policy/carry-exempt.json, `{"schema": 1, "exempt": [{"id", "reason", "kind"?}]}`. Any other shape is an error (ValueError), never an empty set, and so is a `kind` outside EXEMPT_KINDS: input-hash.ts `exemptRowsOf` refuses the same rows, so the runner and this guard never disagree about which file is well-formed."""
    items = doc.get("exempt") if isinstance(doc, dict) else None
    if (
        not isinstance(doc, dict)
        or doc.get("schema") != 1
        or not isinstance(items, list)
        or not all(isinstance(i, dict) and isinstance(i.get("id"), str) and i["id"] for i in items)
    ):
        raise ValueError("carry-exempt.json is not {schema: 1, exempt: [{id, reason}]}")
    for i in items:
        if "kind" in i and i["kind"] not in EXEMPT_KINDS:
            raise ValueError(
                "carry-exempt.json: %s has kind %r; a kind is one of %s"
                % (i["id"], i["kind"], "|".join(EXEMPT_KINDS))
            )
    return {i["id"] for i in items}


# --- attested receipts: the verifier seam (PLAN-two-track-merge-dev D6, R4) ---------------------
# A gate carried from a SIGNED CI RECEIPT names its origin `ci-<tree>` (scripts/ci-runner/ci-receipt.ts writes that prior as .ci/cache/receipts/ci-<tree>.json beside the local archive). The prior is a convenience for the runner and is never believed here: the origin check reads the content-addressed receipt bytes the prior points at, re-verifies their attestation, and compares the carried entry against the attested gate. So a receipt edited after the fetch, one signed by another workflow, or a prior that names a gate no receipt holds is refused at the push, field named. Verification is memoized per sha256 of the bytes, so several hundred gates carried from one receipt cost one `gh` call.
# THE SEAM. `attested(data, source_digest, memo, spec)` answers '' or why, through ATTESTATION_VERIFIER (a module attribute, so a suite stands a stub in). ORIGIN_READERS maps an origin kind to the reader that returns the comparable origin entry, and it is the ci:quick row's `origins` in the push-receipt table (`_push_receipts`, PLAN-tooling-code-reduction CR6): `_push_receipts.readers("ci:quick")` returns it beside the row's tree reader under one interface, so a new receipt kind is one more entry here (and a row there when it needs its own admit line), reusing `attested` unchanged.

#: Who may have signed a CI receipt. scripts/ci-runner/ci-receipt.ts `ATTESTATION_SPEC` holds the same two strings, and test-block_unverified_push.py pins them equal.
CI_ATTESTATION_SPEC = {
    "repo": GH_REPO,
    "signer_workflow": GH_REPO + "/.github/workflows/ci-quality.yml",
}
CI_ORIGIN_RE = re.compile(r"^ci-((?:[0-9a-f]{40}|[0-9a-f]{64}))$")
CI_RAW_RE = re.compile(r"^\.ci/cache/ci-receipts/([0-9a-f]{64})\.json$")
CI_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _gh_retry():
    """`rediacc_ci.core.gh_retry`, so the attestation read retries a transient 5xx and fails a 4xx at once. A scoped, removed sys.path insert, the shape `_policy_rel` uses: a hook cannot import rediacc_ci at module level."""
    cipath = str(hookio.repo_root() / ".ci")
    inserted = syspath.on_sys_path(cipath)
    try:
        from rediacc_ci.core import gh_retry
    finally:
        if inserted and cipath in sys.path:
            sys.path.remove(cipath)
    return gh_retry


def gh_attestation_verifier(data, source_digest, spec):
    """'' when `gh attestation verify` accepts `data` as built from `source_digest` by `spec`'s signer workflow, else why. The bytes are written to a private file first, so what is verified is exactly what was read. A missing gh, a timeout or a network failure is a refusal, never a pass: an unchecked origin is not a verified one."""
    if not CI_SHA_RE.match(source_digest or ""):
        return "the receipt's sha is not a 40-hex commit"
    with tempfile.TemporaryDirectory(prefix="ci-receipt-verify-") as tmp:
        path = os.path.join(tmp, "receipt.json")
        pathlib.Path(path).write_bytes(data)
        argv = ["gh", "attestation", "verify", path, "--repo", spec["repo"]]
        argv += ["--signer-workflow", spec["signer_workflow"], "--source-digest", source_digest]
        try:
            gh_retry = _gh_retry()
            proc = gh_retry.retry_transient(
                lambda: subprocess.run(
                    [*argv, "--format", "json"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                ),
                lambda r: (r.stderr or "") if r.returncode != 0 else None,
            )
        except ImportError as exc:
            return "gh_retry could not be imported, so the receipt is not verified: %s" % exc
        except FileNotFoundError:
            return "gh is not installed (https://cli.github.com, then gh auth login)"
        except subprocess.TimeoutExpired:
            return "gh attestation verify did not answer within 120 s"
        except OSError as exc:
            return "gh attestation verify could not start: %s" % exc
    if proc.returncode != 0:
        tail = " | ".join((proc.stderr or "").strip().splitlines()[-3:])
        return "gh attestation verify exited %d: %s" % (proc.returncode, tail)
    return ""


#: The verifier `attested` calls: (data, source_digest, spec) -> '' or why.
ATTESTATION_VERIFIER = gh_attestation_verifier


def attested(data, source_digest, memo, spec=None):
    """'' when `data` carries an attestation from `spec` (CI_ATTESTATION_SPEC by default) for `source_digest`, else why. Memoized per sha256 of the bytes, digest and signer."""
    spec = CI_ATTESTATION_SPEC if spec is None else spec
    key = ("attested", hashlib.sha256(data).hexdigest(), source_digest, spec["signer_workflow"])
    if key not in memo:
        memo[key] = ATTESTATION_VERIFIER(data, source_digest, spec)
    return memo[key]


def _ci_raw(root, rel, memo):
    key = ("ci-raw", rel)
    if key not in memo:
        try:
            memo[key] = pathlib.Path(root, rel).read_bytes()
        except OSError:
            memo[key] = None
    return memo[key]


def ci_origin_gate(root, tree, gid, memo):
    """(origin entry, '') for `gid` carried from the CI prior `ci-<tree>`, or (None, why naming the field). The entry is built from the ATTESTED receipt, never from the prior: `{inputHash, verdict: 'ok', findings: []}`, since only a pass is receipted and a pass is what the runner carries as ok."""
    prior_key = ("ci-prior", tree)
    if prior_key not in memo:
        memo[prior_key] = _read_json("%s/%s/ci-%s.json" % (root, RECEIPT_ARCHIVE_REL, tree))
    prior = memo[prior_key]
    refs = prior.get("ciReceipts") if isinstance(prior, dict) else None
    if not isinstance(refs, list) or not refs:
        return None, "the CI prior ci-%s is missing or names no receipt (field ciReceipts)" % tree
    for ref in refs:
        rel = ref.get("path") if isinstance(ref, dict) else None
        named = CI_RAW_RE.match(rel) if isinstance(rel, str) else None
        if named is None:
            return (
                None,
                "the CI prior ci-%s names %r, not a receipt under .ci/cache/ci-receipts/<sha256>.json (field ciReceipts.path)"
                % (tree, rel),
            )
        data = _ci_raw(root, rel, memo)
        if data is None:
            return None, "the CI receipt %s is missing (field ciReceipts.path)" % rel
        if hashlib.sha256(data).hexdigest() != named.group(1):
            return (
                None,
                "the CI receipt %s does not hash to its own name, so its bytes changed after the fetch (field sha256)"
                % rel,
            )
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            doc = None
        if not isinstance(doc, dict):
            return None, "the CI receipt %s is not a JSON object (field json)" % rel
        if doc.get("repo") != CI_ATTESTATION_SPEC["repo"]:
            return None, "the CI receipt %s names repo %r (field repo)" % (rel, doc.get("repo"))
        if doc.get("tree") != tree:
            return None, "the CI receipt %s judged tree %r, not %s (field tree)" % (
                rel,
                doc.get("tree"),
                tree,
            )
        gates = doc.get("gates")
        gate = gates.get(gid) if isinstance(gates, dict) else None
        if not isinstance(gate, dict):
            continue
        sha = doc.get("sha") if isinstance(doc.get("sha"), str) else ""
        why = attested(data, sha, memo)
        if why:
            return None, "the CI receipt %s is not verified: %s (field attestation)" % (rel, why)
        if gate.get("verdict") != "pass":
            return (
                None,
                "the CI receipt %s judged it %r, and only a pass carries (field verdict)"
                % (rel, gate.get("verdict")),
            )
        return {"inputHash": gate.get("inputHash"), "verdict": "ok", "findings": []}, ""
    return None, "no CI receipt of the prior ci-%s holds it (field gates)" % tree


#: Origin kind -> reader `(root, tree, gid, memo) -> (origin entry or None, why)`. A local origin (a bare tree hash) is read from the archive inline in `_carried_refusal`.
ORIGIN_READERS = {"ci": ci_origin_gate}


def _carried_refusal(root, tree, gid, entry, lock_entry, entries, exempt, memo=None):
    """Why one carried entry is not honoured, or ''. Names the gate and the field.

    `memo` holds what every carried gate of one push reads alike: package.json, the hash of one input set, and each origin receipt. A gate that declares no `paths` records the whole tree as its input (`**`, scripts/ci-runner/input-hash.ts), and several hundred of them carry at once, so re-reading these per gate made the push wait on the same bytes hundreds of times. Every comparison below still runs per gate.
    """
    memo = {} if memo is None else memo
    carried = entry.get("carriedFrom")
    inputs = entry.get("inputs")
    if not isinstance(inputs, dict) or not isinstance(carried, dict):
        return "%s is carried but records no inputs/carriedFrom (field inputs)" % gid
    if gid in exempt:
        return "%s is listed in %s and may never be carried (field carriedFrom)" % (
            gid,
            CARRY_EXEMPT_REL,
        )
    names = inputs.get("scripts") or []
    if "scripts" not in memo:
        pkg = _show_at(root, tree, "package.json")
        try:
            memo["scripts"] = json.loads(pkg).get("scripts", {}) if pkg else {}
        except (ValueError, AttributeError):
            memo["scripts"] = {}
    texts = memo["scripts"]
    if not isinstance(names, list) or any(n not in texts for n in names):
        return "%s: a script in inputs.scripts is absent from package.json (field defHash)" % gid
    def_hash = v2_def_hash(lock_entry, {n: texts[n] for n in names})
    if def_hash != entry.get("defHash"):
        return "%s: defHash differs at the pushed tree (the gate or its scripts changed)" % gid
    globs = inputs.get("globs") or []
    files = inputs.get("files") or []
    # The name-shaped inputs (W2.4) are recorded only by a gate that declares them; absent, the key and the hash are the pre-W2.4 ones.
    named = {f: inputs.get(f) or [] for f in ("lists", "names", "refs")}
    for f, v in named.items():
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            return "%s: inputs.%s is not a list of strings (field inputs)" % (gid, f)
    key = ("files", json.dumps([globs, files, named], sort_keys=True))
    if key not in memo:
        extras, unresolved = v2_extra_lines(
            entries, named["lists"], named["names"], named["refs"], root=root
        )
        memo[key] = (
            ("unresolved", unresolved)
            if unresolved is not None
            else v2_files_hash(v2_input_lines(entries, globs, files), extras)
        )
    if isinstance(memo[key], tuple):
        return "%s: inputs.refs names %s, which resolves to no commit here (field filesHash)" % (
            gid,
            memo[key][1],
        )
    if memo[key] != entry.get("filesHash"):
        return "%s: filesHash differs at the pushed tree (an input changed after the carry)" % gid
    origin = carried.get("headTree")
    ci = CI_ORIGIN_RE.match(origin) if isinstance(origin, str) else None
    if ci is not None:
        was, why = ORIGIN_READERS["ci"](root, ci.group(1), gid, memo)
        if why:
            return "%s: %s" % (gid, why)
    else:
        if not isinstance(origin, str) or not TREE_RE.match(origin):
            return "%s: carriedFrom.headTree is not a tree hash (field carriedFrom)" % gid
        origin_key = ("origin", origin)
        if origin_key not in memo:
            memo[origin_key] = _read_json("%s/.ci/cache/receipts/%s.json" % (root, origin))
        origin_doc = memo[origin_key]
        base = (origin_doc.get("gates") if isinstance(origin_doc, dict) else None) or {}
        was = base.get(gid) if isinstance(base, dict) else None
        if not isinstance(was, dict):
            return "%s: the archived origin receipt for %s is missing or lacks it (carriedFrom)" % (
                gid,
                origin,
            )
    for field in ("inputHash", "verdict", "findings"):
        if was.get(field) != entry.get(field):
            return "%s: %s differs from the archived origin receipt %s" % (gid, field, origin)
    return ""


def unjudged_blocked(receipt, by_id):
    """The sorted ids whose `blocked` verdict nothing in the receipt explains. PURE.

    The runner writes `blocked` for two different things (scripts/ci-runner/run.ts `receiptGates`): a gate that exited 77 (it COULD NOT RUN, and it is listed in the top-level `blocked` list, which the guard warns on), and a gate the pool SKIPPED and never launched (pool.ts `skip`). A skip has two causes: a `needs` prerequisite that did not pass, which leaves the dependent unjudgeable whatever the run's flags, and `--fail-fast` (or any stop), which leaves every unstarted gate unjudged although nothing stood in its way. Only the first is accepted behaviour (PLAN-gate-scheduling-learned, section 5 "Guard": part (b) is not taken).

    So a `blocked` entry is explained when it is in the top-level `blocked` list, or when one of its `needs` (read from the lock at the pushed tree) has verdict `fail` or is itself an explained `blocked`, transitively. Anything else is a gate the run stopped before: the receipt still says `whole: true`, so without this a `--quick --fail-fast` run whose only red was carried authorised a push over gates nothing judged (reproduced 2026-10-08, T1).
    """
    gates = receipt.get("gates") if isinstance(receipt, dict) else None
    if not isinstance(gates, dict):
        return []
    could_not_run = receipt.get("blocked")
    could_not_run = (
        {g for g in could_not_run if isinstance(g, str)}
        if isinstance(could_not_run, list)
        else set()
    )

    def verdict(gid):
        e = gates.get(gid)
        return e.get("verdict") if isinstance(e, dict) else None

    pending = {gid for gid in gates if verdict(gid) == "blocked"}
    explained = {gid for gid in pending if gid in could_not_run}
    pending -= explained
    changed = True
    while changed:
        changed = False
        for gid in sorted(pending):
            needs = (by_id.get(gid) or {}).get("needs") or []
            if any(verdict(n) == "fail" or n in explained for n in needs if isinstance(n, str)):
                explained.add(gid)
                pending.discard(gid)
                changed = True
    return sorted(pending)


def v2_verdict(root, tree, receipt):
    """The v2 acceptance of a receipt for the pushed `tree`: '' accepts, anything else is the refusal text."""
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        return (
            "that receipt is not schema %d (an older runner wrote it). `%s` writes a v2 receipt."
            % (RECEIPT_SCHEMA, V2_REGEN)
        )
    gates = receipt.get("gates")
    if not isinstance(gates, dict):
        return "the receipt has no per-gate `gates` map. `%s` writes it." % V2_REGEN
    text = _show_at(root, tree, LOCK_REL)
    try:
        lock = json.loads(text) if text else None
    except ValueError:
        lock = None
    if not isinstance(lock, list):
        return "%s is unreadable at the pushed tree, so no gate set can be required." % LOCK_REL
    by_id = {g["id"]: g for g in lock if isinstance(g, dict) and isinstance(g.get("id"), str)}
    for gid, g in sorted(by_id.items()):
        if g.get("gate") is not True or g.get("ciOnly"):
            continue
        entry = gates.get(gid)
        verdicts = V2_VERDICTS + (("deferred",) if g.get("slow") else ())
        if entry is None and g.get("slow"):
            continue
        if not isinstance(entry, dict) or entry.get("verdict") not in verdicts:
            return "the receipt has no judged verdict for %s. Re-run `%s`." % (gid, V2_REGEN)
    for gid, g in sorted(by_id.items()):
        entry = gates.get(gid)
        if g.get("ciOnly") and isinstance(entry, dict) and entry.get("verdict") != "ciOnly":
            return "%s is ciOnly, so its receipt verdict must be ciOnly (field verdict)." % gid
    # A GATE THE RUN STOPPED BEFORE IS NOT JUDGED (unjudged_blocked). After the per-gate presence check, so a receipt missing a verdict keeps its own message.
    unjudged = unjudged_blocked(receipt, by_id)
    if unjudged:
        return (
            "the run stopped before judging %d gate(s) (--fail-fast, or a stop): %s. No prerequisite"
            " failed for them and none could-not-run, so nothing judged them. Re-run `%s` without"
            " --fail-fast."
            % (
                len(unjudged),
                ", ".join(unjudged[:8]) + (" ..." if len(unjudged) > 8 else ""),
                V2_REGEN,
            )
        )
    carried = sorted(
        gid for gid, e in gates.items() if isinstance(e, dict) and e.get("carriedFrom") is not None
    )
    if carried:
        entries = v2_ls_tree(root, tree)
        exempt_text = _show_at(root, tree, CARRY_EXEMPT_REL)
        try:
            exempt = _exempt_ids(json.loads(exempt_text)) if exempt_text else set()
        except ValueError as exc:
            return "%s is unreadable at the pushed tree: %s." % (CARRY_EXEMPT_REL, exc)
        memo: dict[Any, Any] = {}
        for gid in carried:
            if gid not in by_id:
                return "%s is carried but is not in %s (field defHash)" % (gid, LOCK_REL)
            why = _carried_refusal(root, tree, gid, gates[gid], by_id[gid], entries, exempt, memo)
            if why:
                return "a carried verdict is not valid here: %s. Re-run `%s`." % (why, V2_REGEN)
    failed = receipt.get("failed")
    red = {gid for gid, e in gates.items() if isinstance(e, dict) and e.get("verdict") == "fail"}
    if not isinstance(failed, list) or red != set(failed):
        return (
            "the receipt's `failed` list (%s) is not the set of gates with verdict fail (%s)."
            % (_jq_join(failed), ", ".join(sorted(red)))
        )
    want = 1 if red else 0
    if receipt.get("exitCode") != want or isinstance(receipt.get("exitCode"), bool):
        return "the receipt's exitCode must be %d for %d failed gate(s)." % (want, len(red))
    return ""


RECEIPT_REL = ".ci/cache/prepush-receipt.json"
#: The runner's per-tree archive (`scripts/ci-runner/run.ts` archiveReceipt), one whole-lane receipt per `headTree`.
RECEIPT_ARCHIVE_REL = ".ci/cache/receipts"
NO_RECEIPT = "no local gate run has judged this tree."
#: `read_receipt`'s marker for a per-tree copy that is not admissible for the tree it is filed under.
MISFILED = "__misfiled__"


def read_receipt(root, tree):
    """The receipt that speaks for `tree`: the per-tree archive copy `.ci/cache/receipts/<tree>.json` first, then the latest `.ci/cache/prepush-receipt.json`. None when neither file exists.

    The archive copy wins because the latest file is overwritten by every whole run, so a run at another tree after the one that judged `tree` would otherwise void a receipt that is still true. A copy that EXISTS but does not parse returns `{UNPARSEABLE: <path: error>}` rather than falling through to the latest file: a corrupt receipt for this very tree is a finding, not an absence. Only `receipt_refusal`'s callers use this; `run()` keeps its own read of the latest file. THE TWO READERS DIFFER ON PURPOSE: after a whole run at another tree, this reader still finds the receipt for `tree` and `receipt_refusal` can admit it, while `run()` reads the latest file and refuses the same push as "a different tree". The release judges one exact tree, which the archive names; a push judges whatever the runner wrote last.

    THE DIVERGENCE IS SAFE BY CONSTRUCTION. A per-tree copy is admissible only when its own `headTree` equals `tree` exactly and its `whole` is `true`; the runner archives only whole receipts, under their own `headTree` (`scripts/ci-runner/run.ts` writeReceipt and archiveReceipt). A copy that fails either test is refused through `{MISFILED: <why>}`, never read past: it cannot ride an `advances` chain, and it does not fall through to the latest file. So the per-tree copy admits only a whole run that judged this exact tree, through the same verdict `run()` applies, and the release gate (`.ci/rediacc_ci/release/local_gates.py`) relies on exactly that.

    AT THE SAME TREE THE READERS CAN STILL PART, and only in one way (review 96b512e4.1). The two readers apply one verdict function to whichever receipt object they read; they are not two readings of one file. When the per-tree copy holds a whole green run at `tree` and the latest file holds a narrowed run at that same tree, this reader admits the whole run and `run()` refuses the narrowed one. The runner prevents it from arising: a narrowed run never replaces a whole latest receipt (`scripts/ci-runner/run.ts` writeReceipt via narrowedWouldReplaceWhole), and a whole run, red or green, rewrites the per-tree copy along with the latest file (archiveReceipt). So the latest file can hold a narrowed run at `tree` beside a whole copy only after the whole latest file was removed or corrupted by hand. Even then the copy is a true statement about the identical tree, and the release admits it on purpose. `test-block_unverified_push.py` pins the case (SAME-TREE DIVERGENCE).
    """
    archive = None
    if isinstance(tree, str) and TREE_RE.match(tree):
        archive = pathlib.Path(root) / RECEIPT_ARCHIVE_REL / ("%s.json" % tree)
    for path in (archive, pathlib.Path(root) / RECEIPT_REL):
        if path is None or not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {UNPARSEABLE: "%s: %s" % (path, exc)}
        if path == archive:
            named = doc.get("headTree") if isinstance(doc, dict) else None
            if named != tree:
                return {MISFILED: "%s names tree %r, not %s" % (path, named, tree)}
            if doc.get("whole") is not True:
                return {MISFILED: "%s is not a whole-lane receipt (whole is not true)" % path}
        return doc
    return None


def _receipt_front(root, tree, receipt):
    """(refusal or None, advance chain or None): the schema, tree, `whole`, per-gate (v2) and dropped-gate verdicts, in the order `run()` has always judged them. No event, no environment probe, no fetch."""
    r_tree = _alt(receipt, "headTree", "")
    r_whole = _alt(receipt, "whole", False)
    # `R_TREE=$(jq -r ...)` is a STRING in the bash, whatever the JSON type, so
    # a numeric or boolean field is compared as jq would have printed it.
    r_tree = r_tree if isinstance(r_tree, str) else json.dumps(r_tree, separators=(",", ":"))
    r_whole = (
        "true"
        if r_whole is True
        else (r_whole if isinstance(r_whole, str) else json.dumps(r_whole, separators=(",", ":")))
    )

    # A RECEIPT WITHOUT `schema: 2` IS REFUSED, with the command that writes one (clean break: there is no v1 reading path). Before the tree comparison, so an old receipt is told it is old rather than that it judged another tree.
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        return v2_verdict(root, tree, receipt), None

    chain = None
    if r_tree != tree:
        # A RECORD-ONLY COMMIT ADVANCES, it does not void (module docstring). Only this branch pays for the extra git calls, and a receipt with no `advances` keeps today's refusal byte for byte, so the frozen golden's rows do not move.
        chain, why = advance_chain(root, receipt, r_tree, tree)
        if chain is None:
            if why:
                return why, None
            # NO ADVANCE AT ALL: name what voided the receipt and the run ci:quick will do about it (PLAN-stop-hook-retro-20261123 R20261123.5), after the sentence the frozen golden's rows carry.
            return (
                "the gate run judged a different tree (%s), not this one (%s).\n%s"
                % (r_tree, tree, no_advance_hint(root, receipt, r_tree, tree))
            ), None

    # A NARROWED RUN PROVES ALMOST NOTHING. `--quick --only <one-gate>` produces a receipt that is otherwise indistinguishable from all 254, so the runner records whether the lane ran WHOLE and this reads the flag rather than parsing the selection prose -- a guard that parses English fails open on a rewording.
    if r_whole != "true":
        return "that receipt came from a NARROWED run (--only/--skip), not the whole lane.", None

    # THE PER-GATE VERDICTS, and every carried one recomputed at the pushed tree (v2_verdict). After `whole` so a narrowed receipt keeps its own message.
    v2 = v2_verdict(root, tree, receipt)
    if v2:
        return v2, None

    # A TOUCHED SLOW GATE THE LANE DROPPED is refused until a `--only` run of it passed at this tree. After `whole`, so a narrowed receipt keeps its own message; before the base fetch, so a push refused here never pays for one.
    return dropped_verdict(receipt, tree, chain), chain


def _receipt_red(receipt):
    """True when the receipt's exit code is anything but 0, read the way `R_EXIT=$(jq -r '.exitCode // 1')` printed it."""
    r_exit = _alt(receipt, "exitCode", 1)
    r_exit = r_exit if isinstance(r_exit, str) else json.dumps(r_exit, separators=(",", ":"))
    return r_exit != "0"


def receipt_refusal(root, tree, receipt):
    """Why `receipt` does not authorise publishing `tree` from `root`, or None when it does. PURE in the sense the release entry needs: no event object and none of `run()`'s environment fail-opens (a missing `jq`, a failed fetch). A missing environment here is a refusal, never an allow.

    `receipt` is the parsed document, or None when no receipt exists (`read_receipt` returns exactly that). FOR THE SAME RECEIPT OBJECT the verdict is `run()`'s, in its order, minus the behind-origin/main fetch, which belongs to a push and which a release judges on its own fresh fetch. Which receipt object each side judges is NOT shared: `read_receipt` prefers the per-tree copy and `run()` reads only the latest file, so the two can disagree about the same tree (see `read_receipt`).
    """
    if receipt is None:
        return NO_RECEIPT
    if isinstance(receipt, dict) and UNPARSEABLE in receipt:
        return "the receipt does not parse (%s). Re-run `%s`." % (receipt[UNPARSEABLE], V2_REGEN)
    if isinstance(receipt, dict) and MISFILED in receipt:
        return "the per-tree receipt is not admissible for this tree: %s. Re-run `%s`." % (
            receipt[MISFILED],
            V2_REGEN,
        )
    why, _chain = _receipt_front(root, tree, receipt)
    if why is not None:
        # v2_verdict answers a non-v2 receipt with text, so an empty string never reaches here; refuse anyway rather than read "" as consent.
        return why or "the receipt was refused with no reason; re-run `%s`." % V2_REGEN
    # A RED receipt is admitted only when carried-reds.json at HEAD names every failure; a GREEN one still meets rule 2 (a carried entry whose gate went green is stale). `run()` makes this same call on both of its branches (red and green), so one call here is its verdict, minus the warnings.
    refusal, _notes = carried_verdict(receipt, _carried_at_head(root))
    return refusal


def push_tree(ev, scan, cmd, project):
    """The working tree a push in `cmd` is judged in, or "" when it is another repository's push.

    THE SHELL'S WORKING DIRECTORY NAMES THE TREE FIRST, then a `-C`/`cd` in the command moves it (`shellscan.target_root`, resolved from that directory, so a relative hint means what bash makes of it). A plain `git push origin 0923-1` run with the tool's cwd inside private/account was once judged against the CONSOLE receipt and refused as "a different tree" (#e83d9ba9, 2026-09-25), and `git -C <scratch-repo> push origin main` was refused for a stamp that belongs to console (reproduced 2026-09-01).

    A TREE OF THIS REPOSITORY IS JUDGED, NOT WAVED THROUGH (PLAN-two-track-merge-dev LT6). The landing tree beside this checkout and this checkout are two linked trees of one repository, each on its own MMDD-N branch and each with its own `.ci/cache`, because `npm run ci:quick` keeps one clean clone per tree path (scripts/ci-runner/quick-clone.ts `cloneDirFor`) and writes the receipt into the tree it ran from. A push typed in the landing tree used to return ALLOW here because its toplevel was not CLAUDE_PROJECT_DIR, so the PR branch was pushed unjudged; it is now judged against the landing tree's own receipt. "This repository" is one git common directory: a submodule (its own store under .git/modules), a scratch repository and an independent repository under private/ each have another, and stay theirs.
    """
    here = project
    cwd = ev.raw("cwd")
    if cwd not in ("", "null"):
        top = hookio.git_out(["-C", cwd, "rev-parse", "--show-toplevel"], want_rc=True)
        if top:
            here = top
    target = shellscan.target_root(scan, here, verb="push", cmd=cmd) or here
    if os.path.realpath(target) == os.path.realpath(project):
        return project
    store = commit_policy.common_dir(project)
    return target if store and commit_policy.common_dir(target) == store else ""


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
        # git's parse of the words (`shellscan.git_push_args`, #e8be3092): measured on git 2.53.0, `-d --no-delete` pushed, `--del` deleted, and `-o <value>`'s value is no refspec.
        parsed = shellscan.git_push_args(tail)
        if parsed.on("all") or parsed.on("branches") or parsed.on("mirror") or parsed.on("tags"):
            return False
        if parsed.on("delete"):
            continue
        refspecs = parsed.operands[1:]
        if not refspecs or not all(r.startswith(":") and len(r) > 1 for r in refspecs):
            return False
    return True


def run(ev):
    state = shellscan.hook_init(ev.payload)
    if state is None:
        return hookio.ALLOW
    cmd, scan = state

    # A push of nothing but `refs/backup/**` to its repository's pin is the git-level pre-push hook's to judge (box G5 of PLAN-local-first-delivery, `_backup_push`).
    if _backup_push.admitted(ev, cmd):
        return hookio.ALLOW

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

    project = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    if project == "":
        return hookio.ALLOW

    # THE PUSH IS JUDGED IN ITS OWN TREE (PLAN-two-track-merge-dev LT6). Everything below reads `root`: its receipt, its HEAD, its branch, its committed carry file.
    root = push_tree(ev, scan, cmd, project)
    if root == "":
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
    # A PUSH OF WHAT origin/main ALREADY IS needs no local receipt: GitHub's required CI judged that exact commit before main could move to it. That is the GitLab mirror push of /pr-merge step 6b (operator ruling 2026-10-03, worklist #1cad85a1), whose shape block_push_to_protected_branch admits.
    if pushes_only_origin_main(root, pushes):
        return hookio.ALLOW
    tree = pushed_tree(root, pushes)
    if tree is None or tree == "":
        return hookio.ALLOW

    # FAIL OPEN ON A BROKEN ENVIRONMENT, never on a broken verdict. No jq, no git, no repo: allow, exactly as warn-remote-drift.sh does -- "a drift CHECK must never become a push outage". A MISSING or STALE receipt is a different thing and is refused below, because that is the condition this guard exists for.
    if not hookio.have("jq"):
        return hookio.ALLOW

    if not pathlib.Path(receipt_path).is_file():
        return _refuse(ev, "no local gate run has judged this tree.")

    receipt = _read_json(receipt_path)
    r_dirty = _alt(receipt, "dirtyDigest", "")
    r_blocked = _jq_join(receipt.get("blocked") if isinstance(receipt, dict) else None)

    # THE RECEIPT'S OWN VERDICT (schema, tree or advance chain, `whole`, per-gate, dropped), shared with `receipt_refusal`, so for the same receipt object the release entry and this guard reach the same verdict. They can still disagree about a TREE, because they read different files: `read_receipt` prefers the per-tree copy, and this guard reads only the latest file above. The behind-base fetch below sits between it and the carried check, which is why the two halves are called separately here.
    front, _chain = _receipt_front(root, tree, receipt)
    if front is not None:
        return _refuse(ev, front)

    # A LIVE BRANCH BEHIND origin/main IS REFUSED HERE, not by CI (operator finding 2026-10-03, PR #592). Judged once the receipt is whole and names the pushed tree, so a push the receipt already refuses never pays for a fetch, and the frozen goldens for refused pushes stay byte-identical. Run ci:quick after the rebase, not before it.
    behind = behind_base_refusal(ev, root, cmd)
    if behind is not None:
        ev.warn_raw("BLOCKED: %s" % behind)
        return hookio.DENY

    if _receipt_red(receipt):
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
    else:
        # A GREEN RECEIPT STILL MEETS RULE 2. carried_verdict's stale check ran only on a red receipt, so a carried gate that had gone green rode every green push unremarked: on 2026-10-02 the check:ci-external-links carry (fc84526ed) passed the push of b72969998 after its gate went green. With nothing failing, every carried entry is stale.
        refusal, _notes = carried_verdict(receipt, _carried_at_head(root))
        if refusal is not None:
            return _refuse(ev, refusal)

    # A GATE THAT COULD NOT RUN WARNS, IT DOES NOT REFUSE (operator decision, 2026-08-27). Measured that day: twelve reds on a normal developer tree, ten of them ambient, several purely "this machine has no ruff / no workers-types". A missing toolchain is not evidence about the code, and refusing on it would make the receipt unobtainable -- an unobtainable receipt is a guard people route around, which costs more than the rounds it saves.
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
    #
    # A RECEIPT FROM THE KEPT CLEAN CLONE HAS NO SUCH RESIDUAL. `npm run ci:quick` judges HEAD in another tree (scripts/ci-runner/quick-clone.ts), so `judgedRoot` names that tree, its digest describes that tree, and comparing it with this checkout's would print this note on every push while being false. A receipt with no `judgedRoot` keeps the note. This only decides a note: the tree comparison above is what admits the push.
    now_dirty = _dirty_digest(root)
    r_dirty = r_dirty if isinstance(r_dirty, str) else ""
    judged_root = receipt.get("judgedRoot") if isinstance(receipt, dict) else None
    judged_elsewhere = isinstance(judged_root, str) and os.path.realpath(
        judged_root
    ) != os.path.realpath(root)
    if now_dirty and r_dirty and now_dirty != r_dirty and not judged_elsewhere:
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
