"""Refuse a `git push` whose range touches the VM trigger paths unless a VERIFIED `npm run vm:check` receipt covers the pushed tree, or the operator answered for it.

THE ORDER (operator /ask ASKED:2026-10-14T17:19Z, option (c) "Script plus a push guard"; box VC4 of agent/plans/PLAN-vm-check.md). No CI suite drives `rdc` against a VM for the repo shell, sync, SFTP, repo-key shells or VS Code, so a change there is proven on the ops VMs by `npm run vm:check` before it leaves this machine.

WHAT IS TOUCHED is never decided here. `rediacc_ci.drills.vm_check_trigger.changed_paths(root, base, "push", tip)` is the only definition of the trigger, shared with the script, and is imported through `syspath.import_from_ci` (`.ci` on sys.path only for the import). The base is `push_base` (`@{push}`, `origin/<branch>`, `@{upstream}`, then `origin/main`, merged with the pushed tip). A renet range that cannot be computed (an old gitlink commit missing from the local private/renet) is UNKNOWN, and unknown counts as touched: it is listed among the hits, never dropped. A push base that cannot be resolved is unknown in the same way.

THE RECEIPT is judged by `vm_check_receipt.admit(root, tree, inputs(root, tree))`: the pushed tree's archive, then `receipt.json`, then the newest archives. VERIFIED with the same tree or the same trigger digest, a renet build equal to the pointer and not modified, admits. A later commit outside the trigger keeps the digest, so it costs no new VM run.

THE ESCAPE is an environment assignment on the push itself, read from the shared lexer's walk (`run.env`) exactly as `TURBO_PUSH_REASON` is, so a prefix, an earlier `export` and `env NAME=value` count, and prose naming it does not:

    VM_CHECK_PUSH_REASON='<kind>: <why, 40+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push origin <branch>

    vm-unavailable  a NOT_VERIFIED receipt for these inputs exists, so the attempt was made
    not-runtime     the touched change cannot alter what runs on a VM; the why names the files
    deadline        production or CD state that cannot wait; the why names it

  Every kind needs the `ASKED:` minute, matched against an AskUserQuestion answer in the payload's `transcript_path` within 300 s by `wl_checks._asked_in_transcript`, the evidence rule of the review waiver. That proves an operator answer exists at that minute, not that it answered this question: it narrows the escape to the operator's own turn. A transcript that cannot be read proves nothing, so the escape is refused then.

THE LEDGER. Each admitted escape appends one JSON line per judged push to agent/ledgers/vm-check-push-reasons.jsonl in the console checkout (ts, branch, head, tree, renet, kind, why, asked, hits[:10], receipt), written only once every push of the command is admitted. ORDER 62 is the last pre-bash slot, so every other guard has already admitted the command when the line is written. A push a VERIFIED receipt admits writes nothing: the receipt is its record.

SCOPE, as `block_unverified_push` draws it: a command-position `git push` in this checkout. NOT judged: a `--dry-run` push; a delete push (`--delete`, `:<ref>`); a push whose source is exactly `origin/main` (the GitLab mirror push of /pr-merge step 6b, `block_unverified_push.pushes_only_origin_main`); a submodule push (the console pointer push carries the range); another repository, by `-C`, `cd` or the payload's `cwd`.

THE OPERATOR. There is no override beyond the ASKED escape: the operator's own `!` command never reaches PreToolUse.

FAILS OPEN, LOUDLY, on a broken environment (no root, the trigger or receipt module will not import, git cannot name the pushed tree): a note on stderr and the push allowed, like the sibling push guards. A verdict is never failed open.
"""

import datetime
import json
import pathlib
import re

from rediacc_hooks import commit_policy, hookio, plan_gate, shellscan, syspath
from rediacc_hooks.guards import block_unverified_push as PUSH

CHAIN = "pre-bash"
OWN_SUITE = True
# The last pre-bash slot: the ledger line is the admission record, so it is written only after every other guard has let the command through.
ORDER = 62

# The touched test, inverted: planted, every push reads as untouched and passes without a receipt.
DEFECT = ("if not hits:", "if True:")
# The two further mutants the own suite plants; each must flip at least one refusal to allowed.
MUTANTS = {
    "inputs-always-equal": (
        'return receipt.get("tree") == tree or (bool(digest) and receipt.get("inputs") == digest)',
        "return True",
    ),
    "asked-always-true": (
        "return bool(wl_checks._asked_in_transcript(reason, transcript))",
        "return True",
    ),
}

REASON_ENV = "VM_CHECK_PUSH_REASON"
KINDS = ("vm-unavailable", "not-runtime", "deadline")
MIN_WHY = 40
LEDGER_REL = "agent/ledgers/vm-check-push-reasons.jsonl"
HITS_SHOWN = 10
REASON_RE = re.compile(r"^\s*([A-Za-z-]+)\s*:\s*(.*?)\s*$", re.DOTALL)
ASKED_TOKEN_RE = re.compile(r"\s*\bASKED:\S*")
# The minute the escape must spell; `wl_checks.ASKED_RE` is the same shape, and matching it here lets a malformed token be named before the transcript is read.
ASKED_STRICT_RE = re.compile(r"\bASKED:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z")
TRIGGER_MOD = "rediacc_ci.drills.vm_check_trigger"
RECEIPT_MOD = "rediacc_ci.drills.vm_check_receipt"

UNEXAMINED = "block-vm-unverified-push: %s; this push passed UNEXAMINED."


def _git(path, *argv):
    # Fixture builders only; the imports stay inside the function that builds them.
    import os
    import subprocess

    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_AUTHOR_DATE="2026-01-01T00:00:00+00:00",
        GIT_COMMITTER_DATE="2026-01-01T00:00:00+00:00",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )
    out = subprocess.run(
        ["git", *argv], cwd=str(path), check=True, capture_output=True, text=True, env=env
    )
    return out.stdout.strip()


def _put(root, rel, text):
    path = pathlib.Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(root, message):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


# --------------------------------------------------------------------------- fixture worlds


RENET = "private/renet"
CLI_FILE = "packages/cli/src/remote/sftp.ts"
FAKE_RENET = "0123456789abcdef0123456789abcdef01234567"


def world(path, renet_files=(), cli=False, docs=True, missing_old=False):
    """A console-shaped repository on `1008-1` with a real `private/renet` gitlink.

    The seed (`origin/main`) holds a renet commit A as the gitlink, or a commit absent from the local renet when `missing_old`. The branch adds one commit: a docs file when `docs`, `CLI_FILE` when `cli`, and a renet commit B touching `renet_files` (paths relative to private/renet) with the gitlink moved to it when any are named. Returns the console path.
    """
    root = pathlib.Path(path)
    sub = root / RENET
    sub.mkdir(parents=True)
    _git(sub, "init", "-q", "--initial-branch=main")
    _put(sub, "README.md", "renet\n")
    _put(sub, "cmd/renet/sandbox_exec.go", "package main\n")
    _put(sub, "pkg/sandbox/sandbox_test.go", "package sandbox\n")
    _commit(sub, "renet A")
    _git(root, "init", "-q", "--initial-branch=main")
    _git(root, "remote", "add", "origin", "https://github.com/fixture/console.git")
    _put(root, ".gitignore", ".ci/cache/\nagent/ledgers/\n")
    _put(root, "docs/guide.md", "guide\n")
    _put(root, CLI_FILE, "export const sftp = 1;\n")
    _git(root, "add", ".gitignore", "docs", "packages")
    if missing_old:
        _git(root, "update-index", "--add", "--cacheinfo", "160000,%s,%s" % (FAKE_RENET, RENET))
    else:
        _git(root, "add", RENET)
    _git(root, "commit", "-q", "-m", "seed")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(root, "checkout", "-q", "-b", "1008-1")
    if renet_files:
        for rel in renet_files:
            _put(sub, rel, "// changed\n")
        _commit(sub, "renet B")
    if docs:
        _put(root, "docs/guide.md", "guide, edited\n")
    if cli:
        _put(root, CLI_FILE, "export const sftp = 2;\n")
    _git(root, "add", "docs", "packages", RENET)
    _git(root, "commit", "-q", "--allow-empty", "-m", "work")
    return root


def plant_receipt(root, status="VERIFIED", tree=None, inputs=None, pointer=None, built=None):
    """Write a schema-valid receipt into `root`'s cache through the receipt module's own `write`, keyed on `tree` (HEAD's by default) with the trigger digest the guard will compute for it unless `inputs` overrides it."""
    trigger = syspath.import_from_ci(TRIGGER_MOD)
    receipt_mod = syspath.import_from_ci(RECEIPT_MOD)
    root = pathlib.Path(root)
    tree = tree or _git(root, "rev-parse", "HEAD^{tree}")
    head = _git(root, "rev-parse", "HEAD")
    if pointer is None:
        pointer = _git(root, "rev-parse", "%s:%s" % (tree, RENET))
    reason = None
    steps = [{"id": "V1.1", "desc": "deploy renet", "rc": 0, "verdict": "PASS", "ms": 1}]
    if status == "NOT_VERIFIED":
        reason = {"class": "fleet-unavailable", "detail": "ops up --basic exited 1"}
        steps = []
    elif status == "FAILED":
        reason = {"class": "step-failed", "detail": "V1.3 sftp put"}
        steps.append(
            {
                "id": "V1.3",
                "desc": "sftp put into the repo",
                "rc": 1,
                "verdict": "FAIL",
                "ms": 1,
                "evidence": "permission denied",
            }
        )
    receipt = {
        "schema": receipt_mod.SCHEMA,
        "status": status,
        "reason": reason,
        "tree": tree,
        "head": head,
        "inputs": inputs if inputs is not None else trigger.inputs(root, tree),
        "renet": {
            "pointer": pointer,
            "checkout": pointer,
            "built": pointer if built is None else built,
            "modified": False,
            "deployed": True,
        },
        "trigger": {"base": "origin/main", "via": "origin/main", "hits": []},
        "fleet": {"mode": "reused", "os": "ubuntu-24.04", "ips": [], "landlock": {}},
        "forks": [],
        "steps": steps,
        "teardown": {"ok": True, "leftovers": []},
        "runId": "fixture-run",
        "startedAt": "2026-01-01T00:00:00Z",
        "finishedAt": "2026-01-01T00:01:00Z",
        "wallMs": 60000,
    }
    receipt_mod.write(root, receipt)
    return root


def _with_receipt(path, status, **kw):
    root = world(path, cli=True)
    return plant_receipt(root, status, **kw)


def _advanced(path):
    """VERIFIED at the CLI commit, then one more docs-only commit: the digest carries over."""
    root = world(path, cli=True)
    plant_receipt(root)
    _put(root, "docs/later.md", "later\n")
    _commit(root, "docs after the run")
    return root


def _other_pointer(path):
    """A VERIFIED receipt taken at renet A, while the pushed tree points at renet B."""
    root = world(path, renet_files=("cmd/renet/sandbox_exec.go",))
    seed_tree = _git(root, "rev-parse", "origin/main^{tree}")
    return plant_receipt(root, tree=seed_tree)


def _stale_not_verified(path):
    """The CLI touched; the only NOT_VERIFIED receipt is for the seed's tree and inputs."""
    root = world(path, cli=True)
    seed_tree = _git(root, "rev-parse", "origin/main^{tree}")
    return plant_receipt(root, "NOT_VERIFIED", tree=seed_tree)


FIXTURES = {
    "vmc-docs-only": world,
    "vmc-cli-none": lambda p: world(p, cli=True),
    "vmc-cli-verified": lambda p: _with_receipt(p, "VERIFIED"),
    "vmc-cli-not-verified": lambda p: _with_receipt(p, "NOT_VERIFIED"),
    "vmc-cli-failed": lambda p: _with_receipt(p, "FAILED"),
    "vmc-renet-sandbox": lambda p: world(p, renet_files=("cmd/renet/sandbox_exec.go",)),
    "vmc-renet-tests-only": lambda p: world(p, renet_files=("pkg/sandbox/sandbox_test.go",)),
    "vmc-other-pointer": _other_pointer,
    "vmc-advanced": _advanced,
    "vmc-missing-old": lambda p: world(p, missing_old=True),
    "vmc-stale-not-verified": _stale_not_verified,
}

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (name[len("vmc-") :], {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in FIXTURES
]

_ASK = " ASKED:2026-01-01T00:00Z"
_FILES = "only packages/cli/src/remote/sftp.ts comments changed, no runtime code"
_DEADLINE = "the 03:00Z CD promote carries the broken stable SFTP path otherwise"
_UNAVAIL = "the ops fleet is down, ops up --basic exits 1 on vm11 and vm12"
_PUSH = "git push origin 1008-1"
EDGE_CASES = [
    ("a bare push", "git push -u origin 1008-1"),
    ("an implicit push", "git push"),
    ("a -C push", "git -C . push origin 1008-1"),
    ("vm-unavailable", "%s='vm-unavailable: %s%s' %s" % (REASON_ENV, _UNAVAIL, _ASK, _PUSH)),
    ("not-runtime", "%s='not-runtime: %s%s' %s" % (REASON_ENV, _FILES, _ASK, _PUSH)),
    ("deadline", "%s='deadline: %s%s' %s" % (REASON_ENV, _DEADLINE, _ASK, _PUSH)),
    (
        "an exported reason",
        "export %s='not-runtime: %s%s'; %s" % (REASON_ENV, _FILES, _ASK, _PUSH),
    ),
    ("an unknown kind", "%s='because: %s%s' %s" % (REASON_ENV, _FILES, _ASK, _PUSH)),
    ("a short why", "%s='deadline: soon%s' %s" % (REASON_ENV, _ASK, _PUSH)),
    ("no ASKED", "%s='not-runtime: %s' %s" % (REASON_ENV, _FILES, _PUSH)),
    ("a malformed ASKED", "%s='not-runtime: %s ASKED:today' %s" % (REASON_ENV, _FILES, _PUSH)),
    ("a dry run", "git push --dry-run origin 1008-1"),
    ("a delete push", "git push origin --delete 1007-1"),
    ("the mirror push of main", "git push gitlab origin/main:refs/heads/main --follow-tags"),
    ("a submodule push", "git -C private/renet push origin 1008-1"),
    ("prose naming a push", "echo 'git push origin 1008-1'"),
    ("a scratch repo", "git -C /tmp push origin x"),
]


# --------------------------------------------------------------------------- what the command pushes


def _skipped(args):
    """Why one push is not this guard's business, "" when it is judged."""
    parsed = shellscan.git_push_args(args)
    if parsed.on("dry-run"):
        return "dry-run"
    specs = parsed.operands[1:]
    if parsed.on("delete") or (specs and all(s.startswith(":") and len(s) > 1 for s in specs)):
        return "delete"
    return ""


def _pushes(cmd, root, base):
    """[(canonical push line, reason-or-None)] for every judged push of this checkout in `cmd`, in order."""
    created = commit_policy.created_dirs(cmd, base)
    out = []
    for run in commit_policy.git_runs(cmd, "push"):
        _, _, args = commit_policy.git_split(run.argv)
        if _skipped(args):
            continue
        repo = commit_policy.scoped_repo(run, base, root, created) or root
        if pathlib.Path(repo).resolve() != pathlib.Path(root).resolve():
            # A submodule (its pointer push carries the range) or another repository.
            continue
        line = " ".join(["git", "push", *args])
        if PUSH.pushes_only_origin_main(root, [line]):
            continue
        out.append((line, run.env.get(REASON_ENV)))
    return out


def _tip(lines):
    """The commit the push sends: the one explicit source every line names, else HEAD (`block_unverified_push.pushed_tree`'s rule)."""
    sources = {PUSH.push_source(line) for line in lines}
    if len(sources) == 1 and "" not in sources:
        return sources.pop()
    return "HEAD"


def _hits(trigger, root, tip):
    """The touched trigger paths plus every unknown range, each spelled so the refusal can name it."""
    git = trigger.make_git(root)
    branch = commit_policy.current_branch(str(root))
    resolved = trigger.push_base(git, branch or None)
    if not resolved.ref:
        return "", ["(unknown) no push base: tried %s" % ", ".join(resolved.tried)]
    base = resolved.merge_base if tip == "HEAD" else git(["merge-base", tip, resolved.ref])
    if not base:
        return resolved.ref, ["(unknown) no merge base of %s and %s" % (tip, resolved.ref)]
    changed = trigger.changed_paths(root, base, "push", tip)
    found = list(changed.hits) + ["(unknown) renet range %s" % u for u in changed.unknown]
    return "%s via %s" % (base[:12], resolved.via or resolved.ref), found


# --------------------------------------------------------------------------- the escape


def _for_these_inputs(receipt, tree, digest):
    return receipt.get("tree") == tree or (bool(digest) and receipt.get("inputs") == digest)


def _not_verified_attempt(receipt_mod, root, tree, digest):
    """The NOT_VERIFIED receipt taken for these inputs, or None."""
    for receipt in (receipt_mod.read_archive(root, tree), receipt_mod.read_latest(root)):
        if receipt is None or receipt.get("status") != receipt_mod.NOT_VERIFIED:
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
            "block-vm-unverified-push: wl_checks could not import (%s), so no ASKED: "
            "minute can be proven." % exc
        )
        return False
    return bool(wl_checks._asked_in_transcript(reason, transcript))


def _judge_reason(ev, reason, receipt_mod, root, tree, digest):
    """(kind, why, receipt-or-None) when the escape is admitted, else (None, the refusal line, None)."""
    if reason is None:
        return None, "no `%s=` on it" % REASON_ENV, None
    m = REASON_RE.match(reason)
    kind, rest = (m.group(1).lower(), m.group(2)) if m else ("", reason)
    if kind not in KINDS:
        return (
            None,
            "`%s=%r`: the kind must be one of %s" % (REASON_ENV, reason, ", ".join(KINDS)),
            None,
        )
    why = ASKED_TOKEN_RE.sub("", rest).strip()
    if len(why) < MIN_WHY:
        return (
            None,
            "`%s`: the why is %d characters; at least %d name the files or the deadline"
            % (reason, len(why), MIN_WHY),
            None,
        )
    if not ASKED_STRICT_RE.search(reason):
        return None, "`%s` carries no ASKED:<YYYY-MM-DDTHH:MM>Z" % reason, None
    if not _operator_answered(ev, reason):
        unproven = (
            "its ASKED: minute matches no AskUserQuestion answer in this session's transcript "
            "(within 300 s)"
        )
        return None, unproven, None
    attempt = None
    if kind == "vm-unavailable":
        attempt = _not_verified_attempt(receipt_mod, root, tree, digest)
        if attempt is None:
            missing = (
                "`vm-unavailable`, but no NOT_VERIFIED receipt exists for these inputs; "
                "run `npm run vm:check -- --changed` so the attempt is on record"
            )
            return None, missing, None
    return kind, why, attempt


# --------------------------------------------------------------------------- the ledger


def _row(root, tree, kind, why, reason, hits, attempt):
    asked = ASKED_STRICT_RE.search(reason or "")
    receipt = None
    if attempt is not None:
        receipt = {
            "status": attempt.get("status"),
            "class": (attempt.get("reason") or {}).get("class"),
        }
    return {
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": commit_policy.current_branch(root),
        "head": commit_policy.git(["rev-parse", "HEAD"], cwd=root) or "",
        "tree": tree,
        "renet": commit_policy.git(["rev-parse", "%s:%s" % (tree, RENET)], cwd=root) or "",
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
            "block-vm-unverified-push: the admission was NOT recorded in %s (%s)."
            % (LEDGER_REL, exc)
        )


REFUSAL = """BLOCKED: this push touches the VM trigger paths and no VERIFIED vm:check receipt covers tree %(tree)s.

Receipt: %(verdict)s
Touched (%(n)d, base %(base)s):
%(hits)s
Prove it on the ops VMs (about 1 min on a warm fleet, about 2.5 min cold):

    npm run vm:check -- --changed

%(lines)sWhen the VMs cannot answer, the operator decides, and the escape names the minute of
that answer (an AskUserQuestion in this session, matched within 300 s):

    %(env)s='<kind>: <why, %(min)d+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push ...

    vm-unavailable  a NOT_VERIFIED receipt for these inputs exists (the attempt was made)
    not-runtime     the change cannot alter what runs on a VM; name the files
    deadline        production or CD state that cannot wait; name it

Each admitted escape is appended to %(ledger)s.
The operator's own `!` command does not pass through this guard.
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
        receipt_mod = syspath.import_from_ci(RECEIPT_MOD)
    except ImportError as exc:
        ev.warn(UNEXAMINED % ("the vm-check trigger or receipt module could not import (%s)" % exc))
        return hookio.ALLOW
    lines = [line for line, _reason in pushes]
    tip = _tip(lines)
    root_path = pathlib.Path(root)
    tree = PUSH.pushed_tree(root, lines)
    if not tree:
        ev.warn(UNEXAMINED % ("git could not name the pushed tree of %s" % tip))
        return hookio.ALLOW
    base_name, hits = _hits(trigger, root_path, tip)
    if not hits:
        return hookio.ALLOW
    digest = trigger.inputs(root_path, tree)
    verdict = receipt_mod.admit(root_path, tree, digest)
    if verdict.ok:
        return hookio.ALLOW

    rows = []
    refusals = []
    for line, reason in pushes:
        kind, why, attempt = _judge_reason(ev, reason, receipt_mod, root_path, tree, digest)
        if kind is None:
            refusals.append("  %s\n    escape refused: %s\n" % (line, why))
            continue
        rows.append(_row(root, tree, kind, why, reason, hits, attempt))
    if refusals:
        shown = "".join("  %s\n" % h for h in hits[:HITS_SHOWN])
        if len(hits) > HITS_SHOWN:
            shown += "  ... and %d more\n" % (len(hits) - HITS_SHOWN)
        ev.warn_raw(
            REFUSAL
            % {
                "tree": tree[:12],
                "verdict": verdict.message,
                "n": len(hits),
                "base": base_name or "unresolved",
                "hits": shown,
                "lines": "".join(refusals) + "\n",
                "env": REASON_ENV,
                "min": MIN_WHY,
                "ledger": LEDGER_REL,
            }
        )
        return hookio.DENY
    _record(ev, root, rows)
    return hookio.ALLOW
