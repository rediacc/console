"""Refuse a `git push` whose range touches the VM trigger paths (the CLI remote paths, the deployed renet binary's inputs in private/renet, the served code in private/account) unless a VERIFIED `npm run vm:check` receipt covers the pushed tree and every side it touches, or the operator answered for it.

THE ORDER (operator /ask ASKED:2026-10-14T17:19Z, option (c) "Script plus a push guard"; box VC4 of agent/plans/PLAN-vm-check.md). No CI suite drives `rdc` against a VM for the repo shell, sync, SFTP, repo-key shells or VS Code, so a change there is proven on the ops VMs by `npm run vm:check` before it leaves this machine. The account side was added by operator /ask #c5305ed9 ("Account drills via one runner"; box AV5 of agent/plans/PLAN-account-vm-check.md): a private/account change is proven against a live dev gateway and the ops VMs by the same runner and the same receipt.

WHAT IS TOUCHED is never decided here. `rediacc_ci.drills.vm_check_trigger.changed_paths(root, base, "push", tip)` is the only definition of the trigger, shared with the script, and is imported through `syspath.import_from_ci` (`.ci` on sys.path only for the import). The base is `push_base` (`@{push}`, `origin/<branch>`, `@{upstream}`, then `origin/main`, merged with the pushed tip). Both submodules are diffed: a private/renet or private/account gitlink move is diffed inside that submodule, and each side counts on its own. `Changed.sides` names the sides the hits reach (renet, account, or both), and the receipt must have run the phase of every one. A submodule range that cannot be computed (an old gitlink commit missing from the local checkout) is UNKNOWN, listed as `(unknown) <submodule> <sha>: <why>`, adds that submodule's side and counts as touched: it is never dropped. A push base that cannot be resolved is unknown in the same way and charges both sides.

EVERY PUSHED COMMIT IS JUDGED ON ITS OWN. A command can send several commits: two pushes with different sources, or one push naming several refspecs. Each refspec's source (a bare ref is its own source, `+` dropped, no refspec at all reads as HEAD) is resolved to a commit, and each distinct commit gets its own range, tree and receipt. Judging only HEAD would admit a pushed commit carrying a trigger change that HEAD reverts. A source git cannot resolve is named on stderr and skipped, since git refuses to push it as well.

`--all` (`--branches`) AND GLOB REFSPECS send every matching local ref, so the refs are enumerated with one `git for-each-ref` (`_enumerated`): every branch for `--all`, every ref a glob source matches for a glob (one `*`, which crosses `/` as it does in git; an unqualified glob is also tried under `refs/` and `refs/heads/`, a superset of git's match). A ref whose tip equals its remote-tracking counterpart (`refs/remotes/<remote>/<branch>` for a `refs/heads/` destination, the remote being the push's own, else `branch.<b>.pushRemote`, `remote.pushDefault`, `branch.<b>.remote`, `origin`) sends nothing and is not judged; a ref with no counterpart (a URL remote, a tag, another namespace) is judged. Each judged tip takes the per-commit path above. A ref set that cannot be enumerated (`for-each-ref` failing, a glob git would call invalid, a tip that is no commit) is UNKNOWN and counts as touched: it is refused like a range with no receipt, never skipped.

`--mirror` IS REFUSED OUTRIGHT, touched or not. It sends every ref, deletes each remote ref missing here and forces each diverged one, so no receipt for one tree can speak for it. Only the escape admits it, and only as `not-runtime` or `deadline`: `vm-unavailable` names a NOT_VERIFIED attempt for one tree, which a push of every ref has none of. An unenumerable ref set is judged the same way.

THE RECEIPT is judged by `vm_check_receipt.admit(root, tree, inputs(root, tree), sides)`: the pushed tree's archive, then `receipt.json`, then the newest archives. VERIFIED with the same tree or the same trigger digest, a renet build equal to the pointer and not modified, and the phase of every touched side run (`phase-missing` otherwise: a renet-only receipt does not admit an account range), admits. On the account side the receipt's account checkout must equal the pointer (`account-mismatch`) and be unmodified (`modified-account`). The digest (version 2) covers both submodule pointers. A later commit outside the trigger keeps the digest, so it costs no new VM run. Schema 1 receipts are a clean break: the receipt module does not read them, so one admits nothing and backs no escape (`no-receipt`).

THE ESCAPE is an environment assignment on the push itself, read from the shared lexer's walk (`run.env`) exactly as `TURBO_PUSH_REASON` is, so a prefix, an earlier `export` and `env NAME=value` count, and prose naming it does not:

    VM_CHECK_PUSH_REASON='<kind>: <why, 40+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push origin <branch>

    vm-unavailable  a NOT_VERIFIED receipt for these inputs exists (such as `account-gateway`), so the attempt was made
    not-runtime     the touched change cannot alter what runs on a VM or the gateway; the why names the account or renet files
    deadline        production or CD state that cannot wait; the why names it

  Every kind needs the `ASKED:` minute, matched against an AskUserQuestion answer in the payload's `transcript_path` within 300 s by `wl_checks._asked_in_transcript`, the evidence rule of the review waiver. That proves an operator answer exists at that minute, not that it answered this question: it narrows the escape to the operator's own turn. A transcript that cannot be read proves nothing, so the escape is refused then.

THE LEDGER. Each admitted escape appends one JSON line per judged push to agent/ledgers/vm-check-push-reasons.jsonl in the console checkout (ts, branch, head (the pushed commit, not the checkout's HEAD), tree, renet, account (the two gitlinks of that tree), sides, kind, why, asked, hits[:10], receipt), written only once every push of the command is admitted. ORDER 63 puts it behind every refusing guard but `block_backup_unverified_push` at 64, `block_unasked_release` at 62 included, so those have already admitted the command when the line is written. A push a VERIFIED receipt admits writes nothing: the receipt is its record.

SCOPE, as `block_unverified_push` draws it: a command-position `git push` in this checkout. NOT judged: a `--dry-run` push (a `--mirror` or `--all` one too, since it publishes nothing); a delete push (`--delete`, `:<ref>`); a push whose source is exactly `origin/main` (the GitLab mirror push of /pr-merge step 6b, `block_unverified_push.pushes_only_origin_main`), which a `--mirror` push never is; a submodule push (the console pointer push carries the range); another repository, by `-C`, `cd` or the payload's `cwd`.

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
# The second-last pre-bash slot: the ledger line is the admission record, so it is written only after every other guard but block_backup_unverified_push (64) has let the command through.
ORDER = 63

# The touched test, inverted: planted, every push reads as untouched and passes without a receipt.
DEFECT = ("if not hits:", "if True:")
# The further mutants the own suite plants; each must flip at least one refusal to allowed.
MUTANTS = {
    # The judge stops passing the touched sides, so a receipt that skipped a phase admits.
    "phases-ignored": (
        "verdict = receipt_mod.admit(root_path, tree, digest, sides)",
        "verdict = receipt_mod.admit(root_path, tree, digest, ())",
    ),
    # `_hits` loses the account side, so a renet-only receipt admits an account range.
    "account-side-dropped": (
        "return via, found, frozenset(changed.sides)",
        "return via, found, frozenset(changed.sides) - {'account'}",
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
ACCOUNT = "private/account"
CLI_FILE = "packages/cli/src/remote/sftp.ts"
FAKE_RENET = "0123456789abcdef0123456789abcdef01234567"
FAKE_ACCOUNT = "89abcdef0123456789abcdef0123456789abcdef"
ACCOUNT_SRC = "src/routes/licenses.ts"
ACCOUNT_TEST = "tests/routes/licenses.test.ts"


def _submodule(sub, files):
    sub.mkdir(parents=True)
    _git(sub, "init", "-q", "--initial-branch=main")
    for rel, text in files:
        _put(sub, rel, text)
    _commit(sub, "%s A" % sub.name)


def _gitlink(root, sub, missing, fake):
    if missing:
        _git(root, "update-index", "--add", "--cacheinfo", "160000,%s,%s" % (fake, sub))
    else:
        _git(root, "add", sub)


def world(
    path,
    renet_files=(),
    cli=False,
    docs=True,
    missing_old=False,
    account_files=(),
    account_missing_old=False,
):
    """A console-shaped repository on `1008-1` with real `private/renet` and `private/account` gitlinks.

    The seed (`origin/main`) holds a renet commit A and an account commit A as the gitlinks, or a commit absent from the local submodule when `missing_old` (renet) or `account_missing_old` (account). The branch adds one commit: a docs file when `docs`, `CLI_FILE` when `cli`, a renet commit B touching `renet_files` (relative to private/renet) and an account commit B touching `account_files` (relative to private/account), each gitlink moved to its B when files are named. Returns the console path.
    """
    root = pathlib.Path(path)
    renet = root / RENET
    account = root / ACCOUNT
    _submodule(
        renet,
        (
            ("README.md", "renet\n"),
            ("cmd/renet/sandbox_exec.go", "package main\n"),
            ("pkg/sandbox/sandbox_test.go", "package sandbox\n"),
        ),
    )
    _submodule(
        account,
        (
            ("README.md", "account\n"),
            (ACCOUNT_SRC, "export const licenses = 1;\n"),
            (ACCOUNT_TEST, "test('licenses', () => {});\n"),
        ),
    )
    _git(root, "init", "-q", "--initial-branch=main")
    _git(root, "remote", "add", "origin", "https://github.com/fixture/console.git")
    _put(root, ".gitignore", ".ci/cache/\nagent/ledgers/\n")
    _put(root, "docs/guide.md", "guide\n")
    _put(root, CLI_FILE, "export const sftp = 1;\n")
    _git(root, "add", ".gitignore", "docs", "packages")
    _gitlink(root, RENET, missing_old, FAKE_RENET)
    _gitlink(root, ACCOUNT, account_missing_old, FAKE_ACCOUNT)
    _git(root, "commit", "-q", "-m", "seed")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(root, "checkout", "-q", "-b", "1008-1")
    for sub, files in ((renet, renet_files), (account, account_files)):
        if files:
            for rel in files:
                _put(sub, rel, "// changed\n")
            _commit(sub, "%s B" % sub.name)
    if docs:
        _put(root, "docs/guide.md", "guide, edited\n")
    if cli:
        _put(root, CLI_FILE, "export const sftp = 2;\n")
    _git(root, "add", "docs", "packages", RENET, ACCOUNT)
    _git(root, "commit", "-q", "--allow-empty", "-m", "work")
    return root


def plant_receipt(
    root,
    status="VERIFIED",
    tree=None,
    inputs=None,
    pointer=None,
    built=None,
    ran=("renet",),
    reason_class=None,
    account_checkout=None,
    account_modified=False,
):
    """Write a schema 2 receipt into `root`'s cache through the receipt module's own `write`, keyed on `tree` (HEAD's by default) with the trigger digest the guard will compute for it unless `inputs` overrides it.

    `ran` names the phases a VERIFIED receipt ran (each also required); a FAILED or NOT_VERIFIED one ran none and required both. `reason_class` overrides the NOT_VERIFIED or FAILED class, `account_checkout` the account checkout (the pointer by default) and `account_modified` its modified flag.
    """
    trigger = syspath.import_from_ci(TRIGGER_MOD)
    receipt_mod = syspath.import_from_ci(RECEIPT_MOD)
    root = pathlib.Path(root)
    tree = tree or _git(root, "rev-parse", "HEAD^{tree}")
    head = _git(root, "rev-parse", "HEAD")
    if not head:
        raise RuntimeError("fixture has no HEAD commit to key the receipt on")
    if pointer is None:
        pointer = _git(root, "rev-parse", "%s:%s" % (tree, RENET))
    account_pointer = _git(root, "rev-parse", "%s:%s" % (tree, ACCOUNT))
    if not account_pointer:
        raise RuntimeError("fixture has no account pointer to key the receipt on")
    reason = None
    steps = [{"id": "V1.1", "desc": "deploy renet", "rc": 0, "verdict": "PASS", "ms": 1}]
    if status == "NOT_VERIFIED":
        reason = {
            "class": reason_class or "fleet-unavailable",
            "detail": "ops up --basic exited 1",
        }
        steps = []
    elif status == "FAILED":
        reason = {"class": reason_class or "step-failed", "detail": "V1.3 sftp put"}
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
    verified = status == "VERIFIED"
    phases = {
        side: {"required": side in ran if verified else True, "ran": verified and side in ran}
        for side in receipt_mod.SIDES
    }
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
        "trigger": {
            "base": "origin/main",
            "via": "origin/main",
            "hits": [],
            "sides": sorted(side for side, phase in phases.items() if phase["required"]),
        },
        "fleet": {"mode": "reused", "os": "ubuntu-24.04", "ips": [], "landlock": {}},
        "phases": phases,
        "account": {
            "pointer": account_pointer,
            "checkout": account_pointer if account_checkout is None else account_checkout,
            "modified": account_modified,
            "gateway": {"mode": "reused", "port": 8787, "started": 1767225600},
        },
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


def plant_schema_1(root):
    """A VERIFIED receipt in the retired schema 1 shape for HEAD's tree, written raw (the receipt module's `write` refuses it): the guard must read it as no receipt at all."""
    trigger = syspath.import_from_ci(TRIGGER_MOD)
    receipt_mod = syspath.import_from_ci(RECEIPT_MOD)
    root = pathlib.Path(root)
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    pointer = _git(root, "rev-parse", "%s:%s" % (tree, RENET))
    receipt = {
        "schema": 1,
        "status": "VERIFIED",
        "reason": None,
        "tree": tree,
        "head": _git(root, "rev-parse", "HEAD"),
        "inputs": trigger.inputs(root, tree),
        "renet": {
            "pointer": pointer,
            "checkout": pointer,
            "built": pointer,
            "modified": False,
            "deployed": True,
        },
        "trigger": {"base": "origin/main", "via": "origin/main", "hits": []},
        "fleet": {"mode": "reused", "os": "ubuntu-24.04", "ips": [], "landlock": {}},
        "forks": [],
        "steps": [{"id": "V1.1", "desc": "deploy renet", "rc": 0, "verdict": "PASS", "ms": 1}],
        "teardown": {"ok": True, "leftovers": []},
        "runId": "fixture-run-schema-1",
        "startedAt": "2026-01-01T00:00:00Z",
        "finishedAt": "2026-01-01T00:01:00Z",
        "wallMs": 60000,
    }
    folder = receipt_mod.receipt_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    data = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    for name in ("%s.json" % tree, receipt_mod.LATEST):
        (folder / name).write_text(data, encoding="utf-8")
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
    if not seed_tree:
        raise RuntimeError("fixture has no origin/main tree to seed the receipt from")
    return plant_receipt(root, tree=seed_tree)


def _stale_not_verified(path):
    """The CLI touched; the only NOT_VERIFIED receipt is for the seed's tree and inputs."""
    root = world(path, cli=True)
    seed_tree = _git(root, "rev-parse", "origin/main^{tree}")
    if not seed_tree:
        raise RuntimeError("fixture has no origin/main tree to seed the receipt from")
    return plant_receipt(root, "NOT_VERIFIED", tree=seed_tree)


TIP_BRANCH = "vm-tip"


def _reverted(path):
    """`TIP_BRANCH` holds the CLI commit; HEAD reverts the CLI file on top, so HEAD's range touches nothing while the branch's does."""
    root = world(path, cli=True)
    _git(root, "branch", TIP_BRANCH)
    _put(root, CLI_FILE, "export const sftp = 1;\n")
    _commit(root, "revert the CLI change")
    return root


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
    "vmc-reverted": _reverted,
    "vmc-account-src": lambda p: world(p, account_files=(ACCOUNT_SRC,)),
    "vmc-account-tests-only": lambda p: world(p, account_files=(ACCOUNT_TEST,)),
    "vmc-account-renet-receipt": lambda p: plant_receipt(world(p, account_files=(ACCOUNT_SRC,))),
    "vmc-account-verified": lambda p: plant_receipt(
        world(p, account_files=(ACCOUNT_SRC,)), ran=("account",)
    ),
    "vmc-account-missing-old": lambda p: world(p, account_missing_old=True),
    "vmc-renet-wide": lambda p: world(p, renet_files=("pkg/license/x.go",)),
    "vmc-renet-gomod": lambda p: world(p, renet_files=("go.mod",)),
    "vmc-schema-1": lambda p: plant_schema_1(world(p, cli=True)),
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
    ("two pushes of two commits", "git push origin %s:refs/heads/x && %s" % (TIP_BRANCH, _PUSH)),
    ("two refspecs in one push", "git push origin 1008-1:1008-1 %s:refs/heads/x" % TIP_BRANCH),
    ("every branch", "git push --all origin"),
    ("a glob refspec", "git push origin 'refs/heads/*:refs/heads/*'"),
    ("a mirror push", "git push --mirror origin"),
    (
        "a mirror push, escaped",
        "%s='deadline: %s%s' git push --mirror origin" % (REASON_ENV, _DEADLINE, _ASK),
    ),
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
    """[(canonical push line, reason-or-None, args)] for every judged push of this checkout in `cmd`, in order."""
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
        # Before the origin/main exemption: a mirror push is never the GitLab copy of main.
        if not _mirrors(args) and PUSH.pushes_only_origin_main(root, [line]):
            continue
        out.append((line, run.env.get(REASON_ENV), args))
    return out


def _mirrors(args):
    return shellscan.git_push_args(args).on("mirror")


def _remote(root, parsed):
    """The configured remote name a push sends to, "" when it is a URL or no remote this checkout knows (then no ref has a remote-tracking counterpart)."""
    name = parsed.operands[0] if parsed.operands else parsed.last("repo")
    if not name:
        branch = commit_policy.current_branch(root)
        keys = ["remote.pushDefault"]
        if branch:
            keys = ["branch.%s.pushRemote" % branch, *keys, "branch.%s.remote" % branch]
        for key in keys:
            name = commit_policy.git(["config", "--get", key], cwd=root)
            if name:
                break
        name = name or "origin"
    if commit_policy.git(["config", "--get", "remote.%s.url" % name], cwd=root):
        return name
    return ""


def _glob_match(pattern, refname):
    """The part of `refname` the one `*` of `pattern` stands for, None when it does not match."""
    head, _star, tail = pattern.partition("*")
    if len(refname) < len(head) + len(tail):
        return None
    if not (refname.startswith(head) and refname.endswith(tail)):
        return None
    return refname[len(head) : len(refname) - len(tail)]


def _enumerated(root, parsed, globs):
    """[(label, commit-or-None, why-unknown)] for every ref `--all` or the glob refspecs `globs` send whose tip differs from its remote-tracking counterpart.

    A tip that is not a commit, an invalid glob and a `for-each-ref` that fails each come back as one entry with no commit and the reason, so the caller counts it as touched.
    """
    listing = commit_policy.git(
        ["for-each-ref", "--format=%(refname)%09%(objectname)%09%(*objectname)"], cwd=root
    )
    if listing is None:
        return [("(the refs this push sends)", None, "git for-each-ref could not list the refs")]
    refs: dict[str, str] = {}
    for row in listing.split("\n"):
        name, _, rest = row.partition("\t")
        obj, _, peeled = rest.partition("\t")
        if name:
            refs[name] = peeled or obj
    remote = _remote(root, parsed)
    # (src pattern, dst pattern); `--all` is the glob refs/heads/* onto itself.
    pairs = [("refs/heads/*", "refs/heads/*")] if parsed.on("all") or parsed.on("branches") else []
    out: list[tuple[str, str | None, str]] = []
    for spec in globs:
        src, colon, dst = spec.lstrip("+").partition(":")
        dst = dst if colon else src
        if src.count("*") != 1 or dst.count("*") != 1:
            out.append((spec, None, "the glob refspec `%s` cannot be enumerated" % spec))
            continue
        pairs.append((src, dst))
        if not src.startswith("refs/"):
            pairs.extend(("%s%s" % (p, src), dst) for p in ("refs/", "refs/heads/"))
    seen: set[str] = set()
    for src, dst in pairs:
        for name, tip in refs.items():
            matched = _glob_match(src, name)
            if matched is None or name in seen:
                continue
            target = dst.replace("*", matched)
            branch = target.removeprefix("refs/heads/") if target.startswith("refs/heads/") else ""
            if remote and branch and refs.get("refs/remotes/%s/%s" % (remote, branch)) == tip:
                # Synced under THIS mapping only: a later glob may send the same ref to another destination, so it is not marked seen.
                continue
            seen.add(name)
            commit = commit_policy.git(
                ["rev-parse", "-q", "--verify", "%s^{commit}" % tip], cwd=root
            )
            if not commit:
                out.append((name, None, "the tip of `%s` is no commit" % name))
                continue
            out.append((name, commit, ""))
    return out


def _sources(root, args):
    """[(label, commit-or-None, why-unknown)] for every source one push sends, in order.

    A refspec's left side is its source (a bare ref is its own, a leading `+` dropped), HEAD when no refspec is named, and a `:dst` delete inside a mixed push sends nothing; each is resolved here, and one git cannot resolve comes back with no commit and no reason. `--all` and glob refspecs are enumerated by `_enumerated`.
    """
    parsed = shellscan.git_push_args(args)
    specs = parsed.operands[1:]
    every = parsed.on("all") or parsed.on("branches")
    globs = [s for s in specs if "*" in s]
    out = _enumerated(root, parsed, globs) if every or globs else []
    named = []
    for spec in specs:
        src = spec.lstrip("+").split(":", 1)[0]
        if "*" in spec or (not src and ":" in spec):
            continue
        named.append(src or "HEAD")
    if not named and not every and not globs:
        named = ["HEAD"]
    for src in named:
        commit = commit_policy.git(["rev-parse", "-q", "--verify", "%s^{commit}" % src], cwd=root)
        out.append((src, commit or None, ""))
    return out


MIRROR_HITS = [
    (
        "(mirror) every local ref is sent, each remote ref missing here is deleted and each "
        "diverged one forced, so no receipt for one tree covers it"
    )
]


def _tips(root, pushes):
    """({commit: (the source as spelled, [indexes into `pushes` sending it])}, [sources git cannot resolve], [(label, hits, [indexes])] judged blind), every distinct pushed commit once, in order.

    The blind entries are the pushes no tree describes: a `--mirror` push, and a ref set that cannot be enumerated. Each is refused unless its push carries an admitted escape.
    """
    tips: dict[str, tuple[str, list[int]]] = {}
    unresolved: list[str] = []
    blind: list[tuple[str, list[str], list[int]]] = []
    for index, (_line, _reason, args) in enumerate(pushes):
        if _mirrors(args):
            blind.append(("--mirror", MIRROR_HITS, [index]))
            continue
        for src, commit, unknown in _sources(root, args):
            if unknown:
                blind.append((src, ["(unknown) %s" % unknown], [index]))
                continue
            if not commit:
                unresolved.append(src)
                continue
            _label, sending = tips.setdefault(commit, (src, []))
            if index not in sending:
                sending.append(index)
    return tips, unresolved, blind


def _hits(trigger, root, tip):
    """(base, hits, sides): the touched trigger paths plus every unknown range, each spelled so the refusal can name it (an unknown submodule range as `(unknown) <submodule> <sha>: <why>`), and the sides they reach. A base that cannot be resolved charges every side."""
    git = trigger.make_git(root)
    branch = commit_policy.current_branch(str(root))
    resolved = trigger.push_base(git, branch or None)
    every = frozenset(trigger.SIDES)
    if not resolved.ref:
        return "", ["(unknown) no push base: tried %s" % ", ".join(resolved.tried)], every
    base = git(["merge-base", tip, resolved.ref])
    if not base:
        unknown = "(unknown) no merge base of %s and %s" % (tip, resolved.ref)
        return resolved.ref, [unknown], every
    changed = trigger.changed_paths(root, base, "push", tip)
    found = list(changed.hits) + ["(unknown) %s" % u for u in changed.unknown]
    via = "%s via %s" % (base[:12], resolved.via or resolved.ref)
    return via, found, frozenset(changed.sides)


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
        return None, "escape-missing: no `%s=` on it" % REASON_ENV, None
    m = REASON_RE.match(reason)
    kind, rest = (m.group(1).lower(), m.group(2)) if m else ("", reason)
    if kind not in KINDS:
        return (
            None,
            "escape-kind: `%s=%r`: the kind must be one of %s"
            % (REASON_ENV, reason, ", ".join(KINDS)),
            None,
        )
    why = ASKED_TOKEN_RE.sub("", rest).strip()
    if len(why) < MIN_WHY:
        return (
            None,
            "escape-why: `%s`: the why is %d characters; at least %d name the files or the deadline"
            % (reason, len(why), MIN_WHY),
            None,
        )
    if not ASKED_STRICT_RE.search(reason):
        return None, "escape-asked: `%s` carries no ASKED:<YYYY-MM-DDTHH:MM>Z" % reason, None
    if not _operator_answered(ev, reason):
        unproven = (
            "escape-unproven: its ASKED: minute matches no AskUserQuestion answer in this session's transcript "
            "(within 300 s)"
        )
        return None, unproven, None
    attempt = None
    if kind == "vm-unavailable" and tree is None:
        blind = (
            "escape-blind: `vm-unavailable` names a NOT_VERIFIED attempt for one tree, and this push sends "
            "refs no single tree describes; only `not-runtime` or `deadline` admits it"
        )
        return None, blind, None
    if kind == "vm-unavailable":
        attempt = _not_verified_attempt(receipt_mod, root, tree, digest)
        if attempt is None:
            missing = (
                "escape-no-attempt: `vm-unavailable`, but no NOT_VERIFIED receipt exists for these inputs; "
                "run `npm run vm:check -- --changed` so the attempt is on record"
            )
            return None, missing, None
    return kind, why, attempt


# --------------------------------------------------------------------------- the ledger


def _pointer(root, tree, sub):
    return (tree and commit_policy.git(["rev-parse", "%s:%s" % (tree, sub)], cwd=root)) or ""


def _row(root, commit, tree, kind, why, reason, hits, attempt, sides=()):
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
        "head": commit,
        "tree": tree,
        "renet": _pointer(root, tree, RENET),
        "account": _pointer(root, tree, ACCOUNT),
        "sides": sorted(sides),
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


# What each phase costs, as the refusal shows it (agent/plans/PLAN-account-vm-check.md *Cost*; AV7 measures it live).
PHASE_COST = {
    "renet": "about 1 min on a warm fleet, about 2.5 min cold",
    "account": (
        "about 8-11 min with a reused dev gateway, 45-90 s more when the gateway restarts "
        "(a restart rotates the dev passwords and may move its port)"
    ),
}

REFUSAL = """BLOCKED: this push touches the VM trigger paths and no VERIFIED vm:check receipt covers tree %(tree)s (commit %(commit)s, pushed as `%(src)s`) on the side(s) it touches: %(sides)s.

Receipt: [%(code)s] %(verdict)s
Touched (%(n)d, base %(base)s):
%(hits)s
Prove it on the ops VMs; `--changed` runs the phase of each touched side:

    npm run vm:check -- --changed

%(costs)s
%(lines)sWhen the VMs cannot answer, the operator decides, and the escape names the minute of
that answer (an AskUserQuestion in this session, matched within 300 s):

    %(env)s='<kind>: <why, %(min)d+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push ...

    vm-unavailable  a NOT_VERIFIED receipt for these inputs exists (the attempt was made,
                    such as `account-gateway`)
    not-runtime     the change cannot alter what runs on a VM or the gateway; name the
                    account or renet files
    deadline        production or CD state that cannot wait; name it

Each admitted escape is appended to %(ledger)s.
The operator's own `!` command does not pass through this guard.
"""

BLIND_REFUSAL = """BLOCKED: this push sends refs that no vm:check receipt can describe (`%(src)s`).

Why:
%(hits)s
Push the branches one by one (`git push origin <branch>`), so each pushed commit is judged
against its own receipt, or have the operator decide, naming the minute of that answer:

%(lines)s    %(env)s='<not-runtime|deadline>: <why, %(min)d+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push ...

`vm-unavailable` does not admit it: its NOT_VERIFIED attempt covers one tree.
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
    root_path = pathlib.Path(root)
    tips, unresolved, blind = _tips(root, pushes)
    for src in unresolved:
        ev.warn(UNEXAMINED % ("git could not name the pushed commit of `%s`" % src))

    rows = []
    blocks = []
    for label, hits, sending in blind:
        refusals = []
        for index in sending:
            line, reason, _args = pushes[index]
            kind, why, _attempt = _judge_reason(ev, reason, receipt_mod, root_path, None, "")
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
        base_name, hits, sides = _hits(trigger, root_path, commit)
        if not hits:
            continue
        digest = trigger.inputs(root_path, tree)
        verdict = receipt_mod.admit(root_path, tree, digest, sides)
        if verdict.ok:
            continue
        refusals = []
        for index in sending:
            line, reason, _args = pushes[index]
            kind, why, attempt = _judge_reason(ev, reason, receipt_mod, root_path, tree, digest)
            if kind is None:
                refusals.append("  %s\n    escape refused: %s\n" % (line, why))
                continue
            rows.append(_row(root, commit, tree, kind, why, reason, hits, attempt, sides))
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
                "sides": ", ".join(sorted(sides)) or "none",
                "costs": "".join(
                    "    %-14s %s\n" % ("%s phase" % side, PHASE_COST.get(side, "unmeasured"))
                    for side in sorted(sides)
                ),
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
