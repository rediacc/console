"""Refuse a `git push` whose range touches the backup paths (the CLI backup commands and services, renet's chunk store and backup commands, the account backup routes and services) unless a VERIFIED backup receipt covers the pushed tree and both its gitlinks, or the operator answered for it.

THE ORDER. Box J4 of agent/plans/PLAN-backup-program.md: "a backup receipt: backup_check_trigger.py plus block_backup_unverified_push.py, cloned from the vm-check pair ... REASON_ENV with ASKED: is the only escape". The backup path has no CI job that drives it end to end on every change (suite 26 is box J6), so a change to it is proven by the RustFS drill (legs a-l) and its on-premise variant (box I7) before it leaves this machine.

WHAT IS TOUCHED is never decided here. `rediacc_ci.drills.backup_check_trigger.changed_paths(root, base, "push", tip)` is the only definition, imported through `syspath.import_from_ci`; its git arithmetic and `push_base` are the vm-check trigger's own. A private/renet or private/account gitlink move is diffed inside that submodule, and a range that cannot be computed is UNKNOWN, listed as `(unknown) <submodule> <sha>: <why>`, and counts as touched. A push base that cannot be resolved is unknown the same way.

WHAT IS PUSHED is `block_vm_unverified_push`'s reading, called rather than copied (`VM._tips`): every refspec source resolved to a commit and judged on its own, `--all` and glob refspecs enumerated, `--mirror` and an unenumerable ref set judged blind (refused unless escaped as `not-runtime` or `deadline`).

THE RECEIPT is judged by `backup_check_trigger.admit(root, tree, inputs_of_tree(root, tree), pointers_of_tree(root, tree))`: VERIFIED, both gitlinks equal to the pushed tree's (`stale-gitlink`), the same tree or the same console trigger digest (`other-inputs`), each submodule checkout equal to its pointer and unmodified. A receipt short of legs a-l or the on-premise variant is never VERIFIED (the module refuses to write one).

THE ESCAPE is an environment assignment on the push itself, read from the shared lexer's walk (`run.env`) exactly as `VM_CHECK_PUSH_REASON` is:

    BACKUP_CHECK_PUSH_REASON='<kind>: <why, 40+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push origin <branch>

    drill-unavailable  a NOT_VERIFIED backup receipt for these inputs exists, so the attempt was made
    not-runtime        the touched change cannot alter what the drill exercises; the why names the files
    deadline           production or CD state that cannot wait; the why names it

  Every kind needs the `ASKED:` minute, matched against an AskUserQuestion answer in the payload's `transcript_path` within 300 s by `wl_checks._asked_in_transcript`. A transcript that cannot be read proves nothing, so the escape is refused then.

THE LEDGER. Each admitted escape appends one JSON line per judged push to agent/ledgers/backup-check-push-reasons.jsonl (ts, branch, head, tree, renet, account, kind, why, asked, hits[:10], receipt), written only once every push of the command is admitted. ORDER 63 is the last pre-bash slot, so every other guard, `block_vm_unverified_push` at 62 included, has already admitted the command when the line is written. A push a VERIFIED receipt admits writes nothing.

SCOPE is `block_vm_unverified_push`'s: a command-position `git push` in this checkout; not a `--dry-run`, a delete, the GitLab mirror push of `origin/main`, a submodule push or another repository. The git-level `pre-push` hook (box J10) backs this up for pushes that never pass through the Bash tool.

FAILS OPEN, LOUDLY, on a broken environment (no root, the trigger module will not import, git cannot name the pushed tree): a note on stderr and the push allowed, like the sibling push guards. A verdict is never failed open.
"""

import datetime
import json
import pathlib

from rediacc_hooks import commit_policy, hookio, plan_gate, syspath
from rediacc_hooks.guards import block_unverified_push as PUSH
from rediacc_hooks.guards import block_vm_unverified_push as VM

CHAIN = "pre-bash"
OWN_SUITE = True
# The last pre-bash slot: the ledger line is the admission record, so it is written only after every other guard has let the command through.
ORDER = 63

# The touched test, inverted: planted, every push reads as untouched and passes without a receipt.
DEFECT = ("if not hits:", "if True:")
# The further mutants the own suite plants; each must flip at least one refusal to allowed.
MUTANTS = {
    # The judge stops requiring the pushed tree's gitlinks, so a receipt taken at another renet admits.
    "gitlinks-ignored": (
        "verdict = trigger.admit(root_path, tree, digest, pointers)",
        "verdict = trigger.admit(root_path, tree, digest, {})",
    ),
    "inputs-always-equal": (
        'return receipt.get("tree") == tree or (bool(digest) and receipt.get("inputs") == digest)',
        "return True",
    ),
    "asked-always-true": (
        "return bool(wl_checks._asked_in_transcript(reason, transcript))",
        "return True",
    ),
}

REASON_ENV = "BACKUP_CHECK_PUSH_REASON"
KINDS = ("drill-unavailable", "not-runtime", "deadline")
MIN_WHY = 40
LEDGER_REL = "agent/ledgers/backup-check-push-reasons.jsonl"
HITS_SHOWN = 10
TRIGGER_MOD = "rediacc_ci.drills.backup_check_trigger"

UNEXAMINED = "block-backup-unverified-push: %s; this push passed UNEXAMINED."


# --------------------------------------------------------------------------- fixture worlds

RENET = VM.RENET
ACCOUNT = VM.ACCOUNT
CONSOLE_FILE = "packages/cli/src/services/backup/backup-schedule.ts"
RENET_FILE = "pkg/chunkstore/store.go"
RENET_TEST = "pkg/chunkstore/store_test.go"
RENET_OTHER = "pkg/license/x.go"
ACCOUNT_FILE = "src/services/backup-gc.service.ts"


def world(path, console=False, renet_files=(), account_files=(), missing_old=False):
    """`block_vm_unverified_push.world` (a console-shaped checkout on `1008-1` with real `private/renet` and `private/account` gitlinks, one unpushed commit), plus a second commit editing `CONSOLE_FILE` when `console`. Returns the console path."""
    root = VM.world(
        path, renet_files=renet_files, account_files=account_files, missing_old=missing_old
    )
    if console:
        VM._put(root, CONSOLE_FILE, "export const schedule = 2;\n")
        VM._commit(root, "backup schedule")
    return root


def plant_receipt(
    root,
    status="VERIFIED",
    tree=None,
    legs=None,
    onprem=True,
    reason_class=None,
    checkout=None,
    modified=False,
):
    """Write a schema 1 backup receipt into `root`'s cache through the trigger module's own `write`, keyed on `tree` (HEAD's by default) with that tree's digest and gitlinks. `checkout` overrides the renet checkout, `modified` both modified flags."""
    trigger = syspath.import_from_ci(TRIGGER_MOD)
    root = pathlib.Path(root)
    tree = tree or VM._git(root, "rev-parse", "HEAD^{tree}")
    pointers = trigger.pointers_of_tree(root, tree)
    reason = None
    if status != "VERIFIED":
        reason = {"class": reason_class or "store-unavailable", "detail": "RustFS :9100 refused"}
    receipt = {
        "schema": trigger.SCHEMA,
        "status": status,
        "reason": reason,
        "tree": tree,
        "head": VM._git(root, "rev-parse", "HEAD"),
        "inputs": trigger.inputs_of_tree(root, tree),
        "renet": {
            "pointer": pointers[RENET],
            "checkout": pointers[RENET] if checkout is None else checkout,
            "modified": modified,
        },
        "account": {
            "pointer": pointers[ACCOUNT],
            "checkout": pointers[ACCOUNT],
            "modified": modified,
        },
        "legs": list(trigger.REQUIRED_LEGS if legs is None else legs),
        "onprem": onprem,
        "runId": "fixture-backup-run",
        "startedAt": "2026-01-01T00:00:00Z",
        "finishedAt": "2026-01-01T00:05:00Z",
    }
    trigger.write(root, receipt)
    return root


def _seed_tree(root):
    tree = VM._git(root, "rev-parse", "origin/main^{tree}")
    if not tree:
        raise RuntimeError("fixture has no origin/main tree to seed the receipt from")
    return tree


def _stale_gitlink(path):
    """A renet chunk-store range; the only VERIFIED receipt was taken at the seed, whose console inputs match but whose renet gitlink is the old one."""
    root = world(path, renet_files=(RENET_FILE,))
    return plant_receipt(root, tree=_seed_tree(root))


def _stale_not_verified(path):
    """The console backup file touched; the only NOT_VERIFIED receipt is for the seed's tree, whose console inputs differ."""
    root = world(path, console=True)
    return plant_receipt(root, "NOT_VERIFIED", tree=_seed_tree(root))


FIXTURES = {
    "bck-docs-only": world,
    "bck-console-none": lambda p: world(p, console=True),
    "bck-console-verified": lambda p: plant_receipt(world(p, console=True)),
    "bck-console-not-verified": lambda p: plant_receipt(world(p, console=True), "NOT_VERIFIED"),
    "bck-console-failed": lambda p: plant_receipt(world(p, console=True), "FAILED"),
    "bck-renet-chunkstore": lambda p: world(p, renet_files=(RENET_FILE,)),
    "bck-renet-tests-only": lambda p: world(p, renet_files=(RENET_TEST,)),
    "bck-renet-other": lambda p: world(p, renet_files=(RENET_OTHER,)),
    "bck-renet-verified": lambda p: plant_receipt(world(p, renet_files=(RENET_FILE,))),
    "bck-stale-gitlink": _stale_gitlink,
    "bck-account-src": lambda p: world(p, account_files=(ACCOUNT_FILE,)),
    "bck-missing-old": lambda p: world(p, missing_old=True),
    "bck-stale-not-verified": _stale_not_verified,
}

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (name[len("bck-") :], {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in FIXTURES
]

_ASK = " ASKED:2026-01-01T00:00Z"
_FILES = "only comments in packages/cli/src/services/backup changed, no runtime code"
_DEADLINE = "the 03:00Z CD promote carries the broken stable backup restore otherwise"
_UNAVAIL = "RustFS on :9100 refuses connections and run.sh account dev cannot start it"
_PUSH = "git push origin 1008-1"
EDGE_CASES = [
    ("a bare push", "git push -u origin 1008-1"),
    ("an implicit push", "git push"),
    ("a -C push", "git -C . push origin 1008-1"),
    (
        "drill-unavailable",
        "%s='drill-unavailable: %s%s' %s" % (REASON_ENV, _UNAVAIL, _ASK, _PUSH),
    ),
    ("not-runtime", "%s='not-runtime: %s%s' %s" % (REASON_ENV, _FILES, _ASK, _PUSH)),
    ("deadline", "%s='deadline: %s%s' %s" % (REASON_ENV, _DEADLINE, _ASK, _PUSH)),
    ("an unknown kind", "%s='because: %s%s' %s" % (REASON_ENV, _FILES, _ASK, _PUSH)),
    ("a short why", "%s='deadline: soon%s' %s" % (REASON_ENV, _ASK, _PUSH)),
    ("no ASKED", "%s='not-runtime: %s' %s" % (REASON_ENV, _FILES, _PUSH)),
    ("a dry run", "git push --dry-run origin 1008-1"),
    ("a delete push", "git push origin --delete 1007-1"),
    ("the mirror push of main", "git push gitlab origin/main:refs/heads/main --follow-tags"),
    ("a submodule push", "git -C private/renet push origin 1008-1"),
    ("prose naming a push", "echo 'git push origin 1008-1'"),
    ("a mirror push", "git push --mirror origin"),
]


# --------------------------------------------------------------------------- what the command pushes


def _pushes(cmd, root, base):
    """[(canonical push line, reason-or-None, args)] for every judged push of this checkout in `cmd`, in order (`block_vm_unverified_push._pushes` with this guard's escape variable)."""
    created = commit_policy.created_dirs(cmd, base)
    out = []
    for run in commit_policy.git_runs(cmd, "push"):
        _, _, args = commit_policy.git_split(run.argv)
        if VM._skipped(args):
            continue
        repo = commit_policy.scoped_repo(run, base, root, created) or root
        if pathlib.Path(repo).resolve() != pathlib.Path(root).resolve():
            continue
        line = " ".join(["git", "push", *args])
        if not VM._mirrors(args) and PUSH.pushes_only_origin_main(root, [line]):
            continue
        out.append((line, run.env.get(REASON_ENV), args))
    return out


def _hits(trigger, root, tip):
    """(base, hits): the touched backup paths plus every unknown range, each spelled so the refusal can name it."""
    git = trigger.make_git(root)
    branch = commit_policy.current_branch(str(root))
    resolved = trigger.push_base(git, branch or None)
    if not resolved.ref:
        return "", ["(unknown) no push base: tried %s" % ", ".join(resolved.tried)]
    base = git(["merge-base", tip, resolved.ref])
    if not base:
        return resolved.ref, ["(unknown) no merge base of %s and %s" % (tip, resolved.ref)]
    changed = trigger.changed_paths(root, base, "push", tip)
    found = list(changed.hits) + ["(unknown) %s" % u for u in changed.unknown]
    return "%s via %s" % (base[:12], resolved.via or resolved.ref), found


# --------------------------------------------------------------------------- the escape


def _for_these_inputs(receipt, tree, digest):
    return receipt.get("tree") == tree or (bool(digest) and receipt.get("inputs") == digest)


def _not_verified_attempt(trigger, root, tree, digest):
    """The NOT_VERIFIED receipt taken for these inputs, or None."""
    for receipt in (trigger.read_archive(root, tree), trigger.read_latest(root)):
        if receipt is None or receipt.get("status") != trigger.NOT_VERIFIED:
            continue
        if _for_these_inputs(receipt, tree, digest):
            return receipt
    return None


def _operator_answered(ev, reason):
    """True when an `ASKED:` minute in `reason` matches an AskUserQuestion answer in the payload's transcript."""
    transcript = ev.field("transcript_path")
    if not transcript:
        return False
    syspath.on_sys_path(plan_gate.STOP_DIR)
    try:
        import wl_checks
    except ImportError as exc:
        ev.warn(
            "block-backup-unverified-push: wl_checks could not import (%s), so no ASKED: "
            "minute can be proven." % exc
        )
        return False
    return bool(wl_checks._asked_in_transcript(reason, transcript))


def _judge_reason(ev, reason, trigger, root, tree, digest):
    """(kind, why, receipt-or-None) when the escape is admitted, else (None, the refusal line, None)."""
    if reason is None:
        return None, "escape-missing: no `%s=` on it" % REASON_ENV, None
    m = VM.REASON_RE.match(reason)
    kind, rest = (m.group(1).lower(), m.group(2)) if m else ("", reason)
    if kind not in KINDS:
        return (
            None,
            "escape-kind: `%s=%r`: the kind must be one of %s"
            % (REASON_ENV, reason, ", ".join(KINDS)),
            None,
        )
    why = VM.ASKED_TOKEN_RE.sub("", rest).strip()
    if len(why) < MIN_WHY:
        return (
            None,
            "escape-why: `%s`: the why is %d characters; at least %d name the files or the deadline"
            % (reason, len(why), MIN_WHY),
            None,
        )
    if not VM.ASKED_STRICT_RE.search(reason):
        return None, "escape-asked: `%s` carries no ASKED:<YYYY-MM-DDTHH:MM>Z" % reason, None
    if not _operator_answered(ev, reason):
        return (
            None,
            (
                "escape-unproven: its ASKED: minute matches no AskUserQuestion answer in this "
                "session's transcript (within 300 s)"
            ),
            None,
        )
    attempt = None
    if kind == "drill-unavailable" and tree is None:
        return (
            None,
            (
                "escape-blind: `drill-unavailable` names a NOT_VERIFIED attempt for one tree, and this "
                "push sends refs no single tree describes; only `not-runtime` or `deadline` admits it"
            ),
            None,
        )
    if kind == "drill-unavailable":
        attempt = _not_verified_attempt(trigger, root, tree, digest)
        if attempt is None:
            return (
                None,
                (
                    "escape-no-attempt: `drill-unavailable`, but no NOT_VERIFIED backup receipt exists "
                    "for these inputs; run the backup drill so the attempt is on record"
                ),
                None,
            )
    return kind, why, attempt


# --------------------------------------------------------------------------- the ledger


def _row(root, commit, tree, kind, why, reason, hits, attempt):
    asked = VM.ASKED_STRICT_RE.search(reason or "")
    receipt = None
    if attempt is not None:
        receipt = {
            "status": attempt.get("status"),
            "class": (attempt.get("reason") or {}).get("class"),
        }
    return {
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": commit_policy.current_branch(root),
        "head": commit,
        "tree": tree,
        "renet": VM._pointer(root, tree, RENET),
        "account": VM._pointer(root, tree, ACCOUNT),
        "kind": kind,
        "why": why,
        "asked": asked.group(0)[len("ASKED:") :] if asked else "",
        "hits": hits[:HITS_SHOWN],
        "receipt": receipt,
    }


def _record(ev, root, rows):
    path = pathlib.Path(root) / LEDGER_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    except OSError as exc:
        ev.warn(
            "block-backup-unverified-push: the admission was NOT recorded in %s (%s)."
            % (LEDGER_REL, exc)
        )


REFUSAL = """BLOCKED: this push touches the backup paths and no VERIFIED backup receipt covers tree %(tree)s (commit %(commit)s, pushed as `%(src)s`).

Receipt: [%(code)s] %(verdict)s
Touched (%(n)d, base %(base)s):
%(hits)s
Prove it on the committed tree with the RustFS drill (legs a-l) and the on-premise variant
(box I7); the two runs write one receipt together, .ci/cache/backup-check/receipt.json:

    ./run.sh drill backup
    ./run.sh drill backup-onprem

%(lines)sWhen the drill cannot answer, the operator decides, and the escape names the minute of
that answer (an AskUserQuestion in this session, matched within 300 s):

    %(env)s='<kind>: <why, %(min)d+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push ...

    drill-unavailable  a NOT_VERIFIED backup receipt for these inputs exists
    not-runtime        the change cannot alter what the drill exercises; name the files
    deadline           production or CD state that cannot wait; name it

Each admitted escape is appended to %(ledger)s.
The operator's own `!` command does not pass through this guard.
"""

BLIND_REFUSAL = """BLOCKED: this push sends refs that no backup receipt can describe (`%(src)s`).

Why:
%(hits)s
Push the branches one by one (`git push origin <branch>`), so each pushed commit is judged
against its own receipt, or have the operator decide, naming the minute of that answer:

%(lines)s    %(env)s='<not-runtime|deadline>: <why, %(min)d+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push ...

Each admitted escape is appended to %(ledger)s.
"""


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    if not root:
        return hookio.ALLOW
    base = ev.field("cwd") or root
    pushes = _pushes(cmd, root, base)
    if not pushes:
        return hookio.ALLOW
    try:
        trigger = syspath.import_from_ci(TRIGGER_MOD)
    except ImportError as exc:
        ev.warn(UNEXAMINED % ("the backup trigger module could not import (%s)" % exc))
        return hookio.ALLOW
    root_path = pathlib.Path(root)
    tips, unresolved, blind = VM._tips(root, pushes)
    for src in unresolved:
        ev.warn(UNEXAMINED % ("git could not name the pushed commit of `%s`" % src))

    rows = []
    blocks = []
    for label, hits, sending in blind:
        refusals = []
        for index in sending:
            line, reason, _args = pushes[index]
            kind, why, _attempt = _judge_reason(ev, reason, trigger, root_path, None, "")
            if kind is None:
                refusals.append("  %s\n    escape refused: %s\n" % (line, why))
                continue
            rows.append(_row(root, "", "", kind, why, reason, hits, None))
        if refusals:
            blocks.append(
                BLIND_REFUSAL
                % {
                    "src": label,
                    "hits": "".join("  %s\n" % h for h in hits),
                    "lines": "".join(refusals) + "\n",
                    "env": REASON_ENV,
                    "min": MIN_WHY,
                    "ledger": LEDGER_REL,
                }
            )
    for commit, (src, sending) in tips.items():
        tree = commit_policy.git(["rev-parse", "%s^{tree}" % commit], cwd=root)
        if not tree:
            ev.warn(UNEXAMINED % ("git could not name the pushed tree of %s" % src))
            continue
        base_name, hits = _hits(trigger, root_path, commit)
        if not hits:
            continue
        digest = trigger.inputs_of_tree(root_path, tree)
        pointers = trigger.pointers_of_tree(root_path, tree)
        verdict = trigger.admit(root_path, tree, digest, pointers)
        if verdict.ok:
            continue
        refusals = []
        for index in sending:
            line, reason, _args = pushes[index]
            kind, why, attempt = _judge_reason(ev, reason, trigger, root_path, tree, digest)
            if kind is None:
                refusals.append("  %s\n    escape refused: %s\n" % (line, why))
                continue
            rows.append(_row(root, commit, tree, kind, why, reason, hits, attempt))
        if not refusals:
            continue
        shown = "".join("  %s\n" % h for h in hits[:HITS_SHOWN])
        if len(hits) > HITS_SHOWN:
            shown += "  ... and %d more\n" % (len(hits) - HITS_SHOWN)
        blocks.append(
            REFUSAL
            % {
                "tree": tree[:12],
                "commit": commit[:12],
                "src": src,
                "verdict": verdict.message,
                "code": verdict.code,
                "n": len(hits),
                "base": base_name or "unresolved",
                "hits": shown,
                "lines": "".join(refusals) + "\n",
                "env": REASON_ENV,
                "min": MIN_WHY,
                "ledger": LEDGER_REL,
            }
        )
    if blocks:
        ev.warn_raw("\n".join(blocks))
        return hookio.DENY
    if rows:
        _record(ev, root, rows)
    return hookio.ALLOW
