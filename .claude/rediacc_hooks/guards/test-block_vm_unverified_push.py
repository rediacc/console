#!/usr/bin/env python3
"""Control harness for block_vm_unverified_push (OWN_SUITE: never bash, so no golden), box VC4 of agent/plans/PLAN-vm-check.md and box AV5 of agent/plans/PLAN-account-vm-check.md.

REAL REPOSITORIES, one per world, built under a `rediacc_ci.runtmp` run directory by the guard's own `world()` and `plant_receipt()` (the builders its differential `FIXTURES` use, so the suite and the differential judge one shape): a console-shaped checkout on `1008-1` with real `private/renet` and `private/account` gitlinks, `origin/main` at the seed and one unpushed commit, and schema 2 receipts written through `vm_check_receipt.write`, so a receipt shape the module would refuse can never be planted here. The one exception is the retired schema 1 receipt, written raw by `plant_schema_1` because the point of that world is that the module refuses to read it.

BOTH DIRECTIONS. Every refusal has an allow twin that differs by one planted fact: a docs-only range, a test-only renet or account range, a VERIFIED receipt, a receipt that ran the touched side's phase, a receipt carried by a docs commit, a valid escape of each kind against a transcript holding one AskUserQuestion answer. Every escape kind is refused in its invalid case (an unknown kind, a short why, no ASKED, a malformed ASKED, an ASKED matching no answer, `vm-unavailable` with no NOT_VERIFIED receipt for these inputs).

EACH SIDE ON ITS OWN. A private/account range charges the account side and a renet range the renet side: a renet-only VERIFIED receipt is refused `phase-missing` on an account range, an account-only one on a range touching both sides, and an account receipt whose checkout is not the pointer or is modified is refused. The widened renet trigger (pkg/license/x.go, go.mod) is refused without a receipt and admitted with one.

THE LEDGER. An admitted escape appends one line per push to agent/ledgers/vm-check-push-reasons.jsonl in the world; a refused command, a command whose second push is refused, and a push a VERIFIED receipt admits append nothing. All three are read back from the file.

THE MUTANTS ARE PROVEN HERE TOO. The guard's `DEFECT` and every one of its `MUTANTS` (`inputs-always-equal`, `asked-always-true`, `phases-ignored`, `account-side-dropped`) are each planted in a copy run through the same payloads, and each must flip at least one refusal to allowed; a suite whose green did not depend on that line would pass the copy too.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_vm_unverified_push"
GUARD = HERE / ("%s.py" % STEM)
LEDGER = "agent/ledgers/vm-check-push-reasons.jsonl"

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-vm-unverified-push-")

_SYSPATH = importlib.util.spec_from_file_location(
    "_rediacc_syspath", HERE.parents[1] / "rediacc_hooks" / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: .claude/rediacc_hooks/syspath.py is missing" % __file__)
syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(syspath)
syspath.on_sys_path(syspath.CLAUDE_DIR)
_SPEC = importlib.util.spec_from_file_location("vm_push_guard_under_test", GUARD)
if _SPEC is None or _SPEC.loader is None:
    raise SystemExit("cannot load %s" % GUARD)
G = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(G)


def new_dir(prefix):
    return pathlib.Path(tempfile.mkdtemp(prefix=prefix, dir=RUN_TMP)) / "repo"


def built(name):
    return G.FIXTURES[name](new_dir(name + "-"))


DOCS = built("vmc-docs-only")
CLI_NONE = built("vmc-cli-none")
CLI_VERIFIED = built("vmc-cli-verified")
CLI_NOT_VERIFIED = built("vmc-cli-not-verified")
CLI_FAILED = built("vmc-cli-failed")
SANDBOX = built("vmc-renet-sandbox")
TESTS_ONLY = built("vmc-renet-tests-only")
OTHER_POINTER = built("vmc-other-pointer")
ADVANCED = built("vmc-advanced")
MISSING_OLD = built("vmc-missing-old")
STALE_NV = built("vmc-stale-not-verified")
# A VERIFIED receipt for the pushed tree whose deployed renet is not the pointer.
MISMATCH = G.plant_receipt(G.world(new_dir("mismatch-"), cli=True), built=G.FAKE_RENET)
# Worlds the escape cases write ledger lines into, one per kind, so each count is exact.
ESC_NR = built("vmc-cli-none")
ESC_DL = built("vmc-cli-none")
ESC_NV = built("vmc-cli-not-verified")
OUTSIDE = built("vmc-docs-only")
# HEAD reverts the CLI change that `G.TIP_BRANCH` still carries: a command pushing both commits is judged on each.
REVERTED = built("vmc-reverted")
REVERTED_VERIFIED = built("vmc-reverted")
G.plant_receipt(
    REVERTED_VERIFIED,
    tree=G._git(REVERTED_VERIFIED, "rev-parse", "%s^{tree}" % G.TIP_BRANCH),
)
ESC_TIP = built("vmc-reverted")
ESC_MIRROR = built("vmc-docs-only")
# `G.TIP_BRANCH` touched but already pushed: its remote-tracking ref names its tip, so `--all` sends nothing of it.
SYNCED_TIP = built("vmc-reverted")
G._git(SYNCED_TIP, "update-ref", "refs/remotes/origin/%s" % G.TIP_BRANCH, G.TIP_BRANCH)
# ---- the account side and the widened renet trigger
ACCOUNT_SRC = built("vmc-account-src")
ACCOUNT_TESTS = built("vmc-account-tests-only")
ACCOUNT_RENET_RECEIPT = built("vmc-account-renet-receipt")
ACCOUNT_VERIFIED = built("vmc-account-verified")
ACCOUNT_MISSING_OLD = built("vmc-account-missing-old")
RENET_WIDE = built("vmc-renet-wide")
RENET_GOMOD = built("vmc-renet-gomod")
SCHEMA_1 = built("vmc-schema-1")
RENET_WIDE_VERIFIED = G.plant_receipt(built("vmc-renet-wide"))
# A renet-only VERIFIED receipt on a renet range, but the push base cannot be resolved: every side is charged, so the account phase is missing.
NO_BASE = G.plant_receipt(built("vmc-renet-wide"))
G._git(NO_BASE, "update-ref", "-d", "refs/remotes/origin/main")
# origin/main an unrelated root: no base shares a merge base with HEAD, so the base stays unresolved.
UNRELATED_BASE = G.plant_receipt(built("vmc-renet-wide"))
G._git(
    UNRELATED_BASE,
    "update-ref",
    "refs/remotes/origin/main",
    G._git(
        UNRELATED_BASE, "commit-tree", "-m", "unrelated", "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    ),
)
# A resolvable base, but the pushed `orphan` branch shares no merge base with it: every side is charged.
NO_MERGE_BASE = G.plant_receipt(built("vmc-renet-wide"))
G._git(
    NO_MERGE_BASE,
    "update-ref",
    "refs/heads/orphan",
    G._git(
        NO_MERGE_BASE, "commit-tree", "-m", "orphan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    ),
)
RENET_GOMOD_VERIFIED = G.plant_receipt(built("vmc-renet-gomod"))
# Both sides touched (the CLI remote path and the account source): one phase is not enough.
BOTH_ACCOUNT_ONLY = G.plant_receipt(
    G.world(new_dir("both-account-only-"), cli=True, account_files=(G.ACCOUNT_SRC,)),
    ran=("account",),
)
BOTH_VERIFIED = G.plant_receipt(
    G.world(new_dir("both-verified-"), cli=True, account_files=(G.ACCOUNT_SRC,)),
    ran=("renet", "account"),
)
ACCOUNT_MISMATCH = G.plant_receipt(
    G.world(new_dir("account-mismatch-"), account_files=(G.ACCOUNT_SRC,)),
    ran=("account",),
    account_checkout=G.FAKE_ACCOUNT,
)
ACCOUNT_MODIFIED = G.plant_receipt(
    G.world(new_dir("account-modified-"), account_files=(G.ACCOUNT_SRC,)),
    ran=("account",),
    account_modified=True,
)
# The account phase could not start its gateway: the NOT_VERIFIED attempt the `vm-unavailable` escape names.
ESC_GATEWAY = G.plant_receipt(
    G.world(new_dir("esc-gateway-"), account_files=(G.ACCOUNT_SRC,)),
    "NOT_VERIFIED",
    reason_class="account-gateway",
)
ACCOUNT_HIT = "private/account/%s" % G.ACCOUNT_SRC
TIP = G.TIP_BRANCH
TIP_PUSH = "git push origin %s:refs/heads/x" % TIP


def transcript(answer_ts):
    """A lead transcript holding one AskUserQuestion and its answer at `answer_ts`."""
    path = pathlib.Path(tempfile.mkdtemp(prefix="transcript-", dir=RUN_TMP)) / "lead.jsonl"
    records = [
        {
            "type": "assistant",
            "timestamp": "2026-01-01T00:00:10Z",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "AskUserQuestion", "id": "toolu_fixture_ask"}
                ]
            },
        },
        {
            "type": "user",
            "timestamp": answer_ts,
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_fixture_ask", "content": "a"}
                ]
            },
        },
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return str(path)


ANSWERED = transcript("2026-01-01T00:00:30Z")
ASK = " ASKED:2026-01-01T00:00Z"
ASK_ELSEWHERE = " ASKED:2026-01-01T00:10Z"
FILES = G._FILES
DEADLINE = G._DEADLINE
UNAVAIL = G._UNAVAIL
R = "VM_CHECK_PUSH_REASON='%s' "
PUSH = "git push origin 1008-1"
NR = (R % ("not-runtime: " + FILES + ASK)) + PUSH

CASES = [
    # (name, command, root, transcript, cwd, expect_blocked, stderr needle) ---- the trigger
    ("docs only: a bare push", PUSH, DOCS, None, None, False, ""),
    ("renet range, tests only", PUSH, TESTS_ONLY, None, None, False, ""),
    (
        "CLI touched, no receipt",
        PUSH,
        CLI_NONE,
        None,
        None,
        True,
        "packages/cli/src/remote/sftp.ts",
    ),
    (
        "CLI touched: the command named",
        PUSH,
        CLI_NONE,
        None,
        None,
        True,
        "npm run vm:check -- --changed",
    ),
    ("CLI touched: an implicit push", "git push", CLI_NONE, None, None, True, ""),
    ("CLI touched: a -C push", "git -C . push origin 1008-1", CLI_NONE, None, None, True, ""),
    (
        "CLI touched: an sh -c payload",
        "sh -c 'git push origin 1008-1'",
        CLI_NONE,
        None,
        None,
        True,
        "",
    ),
    (
        "CLI touched: the push to main",
        "git push origin 1008-1:main",
        CLI_NONE,
        None,
        None,
        True,
        "",
    ),
    (
        "renet range touching sandbox_exec.go",
        PUSH,
        SANDBOX,
        None,
        None,
        True,
        "private/renet/cmd/renet/sandbox_exec.go",
    ),
    (
        "the old renet object missing",
        PUSH,
        MISSING_OLD,
        None,
        None,
        True,
        "(unknown) private/renet %s" % G.FAKE_RENET,
    ),
    (
        "renet range touching pkg/license/x.go",
        PUSH,
        RENET_WIDE,
        None,
        None,
        True,
        "pkg/license/x.go",
    ),
    ("renet range touching go.mod", PUSH, RENET_GOMOD, None, None, True, "private/renet/go.mod"),
    ("pkg/license/x.go, VERIFIED", PUSH, RENET_WIDE_VERIFIED, None, None, False, ""),
    ("go.mod, VERIFIED", PUSH, RENET_GOMOD_VERIFIED, None, None, False, ""),
    # ---- the account side
    ("account range, tests only", PUSH, ACCOUNT_TESTS, None, None, False, ""),
    ("account src touched, no receipt", PUSH, ACCOUNT_SRC, None, None, True, ACCOUNT_HIT),
    (
        "account src touched: the side named",
        PUSH,
        ACCOUNT_SRC,
        None,
        None,
        True,
        "touches: account",
    ),
    ("account src touched: its cost named", PUSH, ACCOUNT_SRC, None, None, True, "account phase"),
    (
        "account src touched: no renet cost",
        PUSH,
        ACCOUNT_SRC,
        None,
        None,
        True,
        "!renet phase",
    ),
    (
        "the old account object missing",
        PUSH,
        ACCOUNT_MISSING_OLD,
        None,
        None,
        True,
        "(unknown) private/account %s" % G.FAKE_ACCOUNT,
    ),
    (
        "account range, a renet-only VERIFIED receipt",
        PUSH,
        ACCOUNT_RENET_RECEIPT,
        None,
        None,
        True,
        "did not run the account phase",
    ),
    ("account range, an account VERIFIED receipt", PUSH, ACCOUNT_VERIFIED, None, None, False, ""),
    (
        "no push base: a renet-only receipt is refused",
        PUSH,
        NO_BASE,
        None,
        None,
        True,
        "did not run the account phase",
    ),
    ("no push base: names the unresolved base", PUSH, NO_BASE, None, None, True, "no push base"),
    (
        "unrelated base: a renet-only receipt is refused",
        PUSH,
        UNRELATED_BASE,
        None,
        None,
        True,
        "no push base",
    ),
    (
        "no merge base: a renet-only receipt is refused",
        "git push origin orphan",
        NO_MERGE_BASE,
        None,
        None,
        True,
        "no merge base",
    ),
    (
        "refusal names its receipt code",
        PUSH,
        ACCOUNT_RENET_RECEIPT,
        None,
        None,
        True,
        "Receipt: [phase-missing]",
    ),
    (
        "an escape refusal names its code",
        PUSH,
        CLI_NONE,
        None,
        None,
        True,
        "escape-missing: no `VM_CHECK_PUSH_REASON=` on it",
    ),
    (
        "both sides, an account-only VERIFIED receipt",
        PUSH,
        BOTH_ACCOUNT_ONLY,
        None,
        None,
        True,
        "did not run the renet phase",
    ),
    ("both sides: both costs named", PUSH, BOTH_ACCOUNT_ONLY, None, None, True, "renet phase"),
    ("both sides, both phases VERIFIED", PUSH, BOTH_VERIFIED, None, None, False, ""),
    (
        "account checkout is not the pointer",
        PUSH,
        ACCOUNT_MISMATCH,
        None,
        None,
        True,
        "the account checkout",
    ),
    (
        "account checkout modified",
        PUSH,
        ACCOUNT_MODIFIED,
        None,
        None,
        True,
        "account checkout had uncommitted changes",
    ),
    (
        "a schema 1 VERIFIED receipt",
        PUSH,
        SCHEMA_1,
        None,
        None,
        True,
        "no vm:check receipt exists",
    ),
    # ---- every pushed commit, not only HEAD
    ("HEAD reverts the change: a bare push", PUSH, REVERTED, None, None, False, ""),
    (
        "two pushes, the other commit touched",
        "%s && %s" % (TIP_PUSH, PUSH),
        REVERTED,
        None,
        None,
        True,
        "pushed as `%s`" % TIP,
    ),
    (
        "two refspecs in one push",
        "git push origin 1008-1:1008-1 %s:refs/heads/x" % TIP,
        REVERTED,
        None,
        None,
        True,
        "pushed as `%s`" % TIP,
    ),
    (
        "a bare ref naming another branch",
        "git push origin %s" % TIP,
        REVERTED,
        None,
        None,
        True,
        "",
    ),
    (
        "a HEAD-relative source",
        "git push origin HEAD~1:refs/heads/x",
        REVERTED,
        None,
        None,
        True,
        "",
    ),
    (
        "two pushes, the other commit VERIFIED",
        "%s && %s" % (TIP_PUSH, PUSH),
        REVERTED_VERIFIED,
        None,
        None,
        False,
        "",
    ),
    # ---- every branch, a glob refspec, a mirror
    (
        "--all, another branch touched",
        "git push --all origin",
        REVERTED,
        None,
        None,
        True,
        "pushed as `refs/heads/%s`" % TIP,
    ),
    ("--all with no remote named", "git push --all", REVERTED, None, None, True, TIP),
    (
        "--branches, another branch touched",
        "git push --branches origin",
        REVERTED,
        None,
        None,
        True,
        TIP,
    ),
    (
        "--all, every differing tip VERIFIED",
        "git push --all origin",
        REVERTED_VERIFIED,
        None,
        None,
        False,
        "",
    ),
    (
        "--all, the touched branch already pushed",
        "git push --all origin",
        SYNCED_TIP,
        None,
        None,
        False,
        "",
    ),
    ("--all to another remote", "git push --all elsewhere", SYNCED_TIP, None, None, True, TIP),
    ("--all, docs only", "git push --all origin", DOCS, None, None, False, ""),
    (
        "--all to a URL remote",
        "git push --all https://example.invalid/c.git",
        REVERTED,
        None,
        None,
        True,
        TIP,
    ),
    (
        "a glob refspec",
        "git push origin 'refs/heads/*:refs/heads/*'",
        REVERTED,
        None,
        None,
        True,
        "pushed as `refs/heads/%s`" % TIP,
    ),
    (
        "a forced glob refspec",
        "git push origin '+refs/heads/vm-*:refs/heads/vm-*'",
        REVERTED,
        None,
        None,
        True,
        TIP,
    ),
    (
        "a glob matching only synced main",
        "git push origin 'refs/heads/ma*:refs/heads/ma*'",
        REVERTED,
        None,
        None,
        False,
        "",
    ),
    (
        "a synced mapping first, a second glob sending the same ref elsewhere",
        "git push origin 'refs/heads/vm-*:refs/heads/vm-*' 'refs/heads/vm-*:refs/heads/other-*'",
        SYNCED_TIP,
        None,
        None,
        True,
        TIP,
    ),
    (
        "a glob git cannot enumerate",
        "git push origin 'refs/heads/*/*:refs/heads/*/*'",
        DOCS,
        None,
        None,
        True,
        "(unknown) the glob refspec",
    ),
    (
        "--mirror, nothing touched",
        "git push --mirror origin",
        DOCS,
        None,
        None,
        True,
        "(mirror) every local ref",
    ),
    ("--mirror, no remote named", "git push --mirror", DOCS, None, None, True, "--mirror"),
    (
        "--mirror then --no-mirror",
        "git push --mirror --no-mirror origin 1008-1",
        DOCS,
        None,
        None,
        False,
        "",
    ),
    ("--mirror, a dry run", "git push --mirror --dry-run origin", DOCS, None, None, False, ""),
    ("--all, a dry run", "git push --all -n origin", REVERTED, None, None, False, ""),
    (
        "--mirror into a submodule",
        "git -C private/renet push --mirror origin",
        DOCS,
        None,
        None,
        False,
        "",
    ),
    # ---- the receipt
    ("VERIFIED for this tree", PUSH, CLI_VERIFIED, None, None, False, ""),
    ("VERIFIED, carried by a docs commit", PUSH, ADVANCED, None, None, False, ""),
    ("NOT_VERIFIED", PUSH, CLI_NOT_VERIFIED, None, None, True, "fleet-unavailable"),
    ("FAILED", PUSH, CLI_FAILED, None, None, True, "V1.3"),
    ("VERIFIED for another pointer", PUSH, OTHER_POINTER, None, None, True, "other trigger inputs"),
    ("VERIFIED, another renet build", PUSH, MISMATCH, None, None, True, "is not the pointer"),
    # ---- not this guard's business
    ("a dry run", "git push --dry-run origin 1008-1", CLI_NONE, None, None, False, ""),
    ("a delete push", "git push origin --delete 1007-1", CLI_NONE, None, None, False, ""),
    ("an empty-source delete", "git push origin :1007-1", CLI_NONE, None, None, False, ""),
    (
        "the mirror push of main",
        "git push gitlab origin/main:refs/heads/main --follow-tags",
        CLI_NONE,
        None,
        None,
        False,
        "",
    ),
    (
        "a submodule push",
        "git -C private/renet push origin 1008-1",
        CLI_NONE,
        None,
        None,
        False,
        "",
    ),
    ("cd into the submodule", "cd private/renet && git push", CLI_NONE, None, None, False, ""),
    ("cwd inside the submodule", PUSH, CLI_NONE, None, "private/renet", False, ""),
    ("prose naming a push", "echo 'git push origin 1008-1'", CLI_NONE, None, None, False, ""),
    ("a heredoc body", "cat > n.md <<'EOF'\ngit push\nEOF", CLI_NONE, None, None, False, ""),
    (
        "a repository outside",
        "git -C %s push origin 1008-1" % OUTSIDE,
        CLI_NONE,
        None,
        None,
        False,
        "",
    ),
    ("an empty command", "", CLI_NONE, None, None, False, ""),
    # ---- the escape, admitted
    ("not-runtime, answered", NR, ESC_NR, ANSWERED, None, False, ""),
    (
        "deadline, answered",
        (R % ("deadline: " + DEADLINE + ASK)) + PUSH,
        ESC_DL,
        ANSWERED,
        None,
        False,
        "",
    ),
    (
        "vm-unavailable over its NOT_VERIFIED receipt",
        (R % ("vm-unavailable: " + UNAVAIL + ASK)) + PUSH,
        ESC_NV,
        ANSWERED,
        None,
        False,
        "",
    ),
    (
        "an exported reason",
        "export VM_CHECK_PUSH_REASON='not-runtime: %s%s'; %s" % (FILES, ASK, PUSH),
        ESC_NR,
        ANSWERED,
        None,
        False,
        "",
    ),
    (
        "env NAME=value",
        "env VM_CHECK_PUSH_REASON='not-runtime: %s%s' %s" % (FILES, ASK, PUSH),
        ESC_NR,
        ANSWERED,
        None,
        False,
        "",
    ),
    (
        "vm-unavailable over an account-gateway NOT_VERIFIED",
        (R % ("vm-unavailable: " + UNAVAIL + ASK)) + PUSH,
        ESC_GATEWAY,
        ANSWERED,
        None,
        False,
        "",
    ),
    (
        "not-runtime for the other commit",
        (R % ("not-runtime: " + FILES + ASK)) + TIP_PUSH,
        ESC_TIP,
        ANSWERED,
        None,
        False,
        "",
    ),
    (
        "--mirror, deadline answered",
        (R % ("deadline: " + DEADLINE + ASK)) + "git push --mirror origin",
        ESC_MIRROR,
        ANSWERED,
        None,
        False,
        "",
    ),
    # ---- the escape, refused
    (
        "--mirror, vm-unavailable answered",
        (R % ("vm-unavailable: " + UNAVAIL + ASK)) + "git push --mirror origin",
        DOCS,
        ANSWERED,
        None,
        True,
        "escape-blind: `vm-unavailable` names a NOT_VERIFIED attempt for one tree",
    ),
    (
        "--mirror, an ASKED matching no answer",
        (R % ("deadline: " + DEADLINE + ASK_ELSEWHERE)) + "git push --mirror origin",
        DOCS,
        ANSWERED,
        None,
        True,
        "escape-unproven: its ASKED: minute matches no AskUserQuestion answer",
    ),
    (
        "vm-unavailable with no receipt at all",
        (R % ("vm-unavailable: " + UNAVAIL + ASK)) + PUSH,
        CLI_NONE,
        ANSWERED,
        None,
        True,
        "escape-no-attempt: `vm-unavailable`, but no NOT_VERIFIED receipt exists for these inputs",
    ),
    (
        "vm-unavailable over another tree's NOT_VERIFIED",
        (R % ("vm-unavailable: " + UNAVAIL + ASK)) + PUSH,
        STALE_NV,
        ANSWERED,
        None,
        True,
        "escape-no-attempt: `vm-unavailable`, but no NOT_VERIFIED receipt exists for these inputs",
    ),
    (
        "an unknown kind",
        (R % ("because: " + FILES + ASK)) + PUSH,
        CLI_NONE,
        ANSWERED,
        None,
        True,
        "escape-kind: `VM_CHECK_PUSH_REASON=",
    ),
    (
        "a short why",
        (R % ("deadline: soon" + ASK)) + PUSH,
        CLI_NONE,
        ANSWERED,
        None,
        True,
        "escape-why: `deadline: soon",
    ),
    (
        "no ASKED",
        (R % ("not-runtime: " + FILES)) + PUSH,
        CLI_NONE,
        ANSWERED,
        None,
        True,
        "escape-asked: `",
    ),
    (
        "a malformed ASKED",
        (R % ("not-runtime: " + FILES + " ASKED:today")) + PUSH,
        CLI_NONE,
        ANSWERED,
        None,
        True,
        "escape-asked: `",
    ),
    (
        "an ASKED matching no answer",
        (R % ("not-runtime: " + FILES + ASK_ELSEWHERE)) + PUSH,
        CLI_NONE,
        ANSWERED,
        None,
        True,
        "escape-unproven: its ASKED: minute matches no AskUserQuestion answer",
    ),
    (
        "an ASKED with no transcript",
        NR,
        CLI_NONE,
        None,
        None,
        True,
        "escape-unproven: its ASKED: minute matches no AskUserQuestion",
    ),
    (
        "the reason in prose only",
        "echo \"VM_CHECK_PUSH_REASON='not-runtime: %s%s'\"; %s" % (FILES, ASK, PUSH),
        CLI_NONE,
        ANSWERED,
        None,
        True,
        "no `VM_CHECK_PUSH_REASON=` on it",
    ),
    (
        "a second push with no reason",
        "%s; git push origin HEAD:1008-1" % NR,
        CLI_NONE,
        ANSWERED,
        None,
        True,
        "no `VM_CHECK_PUSH_REASON=` on it",
    ),
    (
        "the same push twice, the second with no reason",
        "%s; %s" % (NR, PUSH),
        CLI_NONE,
        ANSWERED,
        None,
        True,
        "no `VM_CHECK_PUSH_REASON=` on it",
    ),
]

BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "import ast\n"
    "cut = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id in ('DEFECT', 'MUTANTS') for t in n.targets)]\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut))\n"
    "assert outside.count(old) == 1, 'the mutant must name exactly one line outside its declaration'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def ledger_lines(root):
    path = pathlib.Path(root) / LEDGER
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def run(command, root, transcript_path, cwd, broken=None):
    """(blocked, stderr) of one payload through the dispatcher, or through a copy of the guard with `broken` (an (old, new) mutant) planted."""
    env = dict(
        os.environ,
        CLAUDE_PROJECT_DIR=str(root),
        TMPDIR=tempfile.mkdtemp(prefix="tmp-", dir=RUN_TMP),
    )
    env.pop("VM_CHECK_PUSH_REASON", None)
    doc = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(pathlib.Path(root) / cwd) if cwd else str(root),
    }
    if transcript_path:
        doc["transcript_path"] = transcript_path
    if broken:
        argv = [
            sys.executable,
            "-c",
            BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), broken, str(GUARD)),
        ]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=json.dumps(doc), capture_output=True, text=True, check=False, env=env
    )
    if proc.returncode not in (0, 2):
        raise SystemExit(
            "%s runner crashed (rc %d): %s"
            % ("broken" if broken else "guard", proc.returncode, proc.stderr[-800:])
        )
    return proc.returncode == 2, proc.stderr


fails = 0
blocked = 0
for name, command, root, tr, cwd, want, needle in CASES:
    before = len(ledger_lines(root))
    got, err = run(command, root, tr, cwd)
    grew = len(ledger_lines(root)) - before
    blocked += got
    if needle and needle.startswith("!"):
        ok = got == want and needle[1:] not in err
    else:
        ok = got == want and (not needle or needle in err)
    escaped = "VM_CHECK_PUSH_REASON='" in command and not command.startswith("echo")
    if got and grew:
        ok = False
        print("    a refused command wrote %d ledger line(s)" % grew)
    if not got and escaped and grew != 1:
        ok = False
        print("    an admitted escape wrote %d ledger line(s), want 1" % grew)
    if not got and not escaped and grew:
        ok = False
        print("    a push admitted without an escape wrote %d ledger line(s)" % grew)
    fails += not ok
    print(
        "%-52s want=%-8s got=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok:
        print("    needle %r; stderr: %s" % (needle, err.strip().splitlines()[:8]))

# The shape of the ledger lines, read back.
want_keys = {
    "ts",
    "branch",
    "head",
    "tree",
    "renet",
    "account",
    "sides",
    "kind",
    "why",
    "asked",
    "hits",
    "receipt",
}
checks = (
    (ESC_NR, "not-runtime", None, [G.CLI_FILE], ["renet"]),
    (ESC_DL, "deadline", None, [G.CLI_FILE], ["renet"]),
    (
        ESC_NV,
        "vm-unavailable",
        {"status": "NOT_VERIFIED", "class": "fleet-unavailable"},
        [G.CLI_FILE],
        ["renet"],
    ),
    (
        ESC_GATEWAY,
        "vm-unavailable",
        {"status": "NOT_VERIFIED", "class": "account-gateway"},
        [ACCOUNT_HIT],
        ["account"],
    ),
)
for root, kind, receipt, hits, sides in checks:
    rows = [json.loads(line) for line in ledger_lines(root)]
    if not rows:
        print("*** FAIL *** no ledger line was written for kind %s" % kind)
        fails += 1
        continue
    last = rows[-1]
    bad = [
        what
        for what, cond in (
            ("keys", set(last) == want_keys),
            ("kind", last.get("kind") == kind),
            ("branch", last.get("branch") == "1008-1"),
            ("head", len(last.get("head", "")) == 40),
            ("tree", len(last.get("tree", "")) == 40),
            ("renet", len(last.get("renet", "")) == 40),
            ("account", len(last.get("account", "")) == 40),
            ("sides", last.get("sides") == sides),
            ("asked", last.get("asked") == "2026-01-01T00:00Z"),
            ("hits", last.get("hits") == hits),
            ("receipt", last.get("receipt") == receipt),
            ("why", "ASKED" not in last.get("why", "") and len(last.get("why", "")) >= G.MIN_WHY),
        )
        if not cond
    ]
    if bad:
        print("*** FAIL *** ledger line %r is wrong in: %s" % (last, ", ".join(bad)))
        fails += 1
    else:
        print("ledger: %d line(s) for kind %s, receipt %r" % (len(rows), kind, last["receipt"]))
# The ledger names the commit pushed, not the checkout's HEAD.
tip_rows = [json.loads(line) for line in ledger_lines(ESC_TIP)]
tip_sha = G._git(ESC_TIP, "rev-parse", TIP)
if [r.get("head") for r in tip_rows] != [tip_sha]:
    print(
        "*** FAIL *** the escape for %s recorded head %r, want [%r] (HEAD is %s)"
        % (TIP, [r.get("head") for r in tip_rows], tip_sha, G._git(ESC_TIP, "rev-parse", "HEAD"))
    )
    fails += 1
else:
    print("ledger: the escape for %s names the pushed commit %s" % (TIP, tip_sha[:12]))
# A mirror escape records the push it admitted, with no single commit or tree to name.
mirror_rows = [json.loads(line) for line in ledger_lines(ESC_MIRROR)]
if [(r.get("head"), r.get("tree"), r.get("kind"), r.get("hits")) for r in mirror_rows] != [
    ("", "", "deadline", G.MIRROR_HITS)
]:
    print("*** FAIL *** the --mirror escape recorded %r" % mirror_rows)
    fails += 1
else:
    print("ledger: the --mirror escape is recorded with no head and its mirror hit")
for quiet in (
    CLI_NONE,
    CLI_VERIFIED,
    ADVANCED,
    STALE_NV,
    DOCS,
    REVERTED,
    REVERTED_VERIFIED,
    ACCOUNT_SRC,
    ACCOUNT_VERIFIED,
    ACCOUNT_RENET_RECEIPT,
    SCHEMA_1,
):
    if ledger_lines(quiet):
        print("*** FAIL *** a world with no admitted escape wrote %r" % ledger_lines(quiet))
        fails += 1

print()
CONTROLS = [("DEFECT", G.DEFECT), *sorted(G.MUTANTS.items())]
# The cases each named mutant must flip, so a control cannot pass on some unrelated refusal.
MUST_FLIP = {
    "inputs-always-equal": "vm-unavailable over another tree's NOT_VERIFIED",
    "asked-always-true": "an ASKED matching no answer",
    # Only the empty-sides call admits it: with the account side dropped, the renet phase is still missing.
    "phases-ignored": "both sides, an account-only VERIFIED receipt",
    "account-side-dropped": "account range, a renet-only VERIFIED receipt",
}
for label, mutant in CONTROLS:
    flipped = [
        n for n, c, r, tr, cwd, w, _ in CASES if w and not run(c, r, tr, cwd, broken=mutant)[0]
    ]
    must = MUST_FLIP.get(label)
    if flipped and (must is None or must in flipped):
        print(
            "%s control: planted %r; %d refusal(s) flipped to allowed, e.g. %r"
            % (label, mutant[1], len(flipped), must or flipped[0])
        )
    else:
        print(
            "*** FAIL *** %s control: with %r planted, %s"
            % (
                label,
                mutant,
                "every refusal still refused" if not flipped else "%r did not flip" % must,
            )
        )
        fails += 1

if blocked in (0, len(CASES)):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
