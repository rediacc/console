"""Refuse a `git push` whose range touches the VM trigger paths (the CLI remote paths, the deployed renet binary's inputs in private/renet, the served code in private/account) unless a VERIFIED `npm run vm:check` receipt covers the pushed tree and every side it touches, or the operator answered for it.

THE ORDER (operator /ask ASKED:2026-10-14T17:19Z, option (c) "Script plus a push guard"; box VC4 of agent/plans/PLAN-vm-check.md). No CI suite drives `rdc` against a VM for the repo shell, sync, SFTP, repo-key shells or VS Code, so a change there is proven on the ops VMs by `npm run vm:check` before it leaves this machine. The account side was added by operator /ask #c5305ed9 ("Account drills via one runner"; box AV5 of agent/plans/PLAN-account-vm-check.md): a private/account change is proven against a live dev gateway and the ops VMs by the same runner and the same receipt.

WHAT IS TOUCHED is never decided here. `rediacc_ci.proof.surfaces.changed_paths(root, base, "push", tip)` is the only definition of the trigger, shared with the script, and is imported through `syspath.import_from_ci` (`.ci` on sys.path only for the import). The base is `push_base` (`@{push}`, `origin/<branch>`, `@{upstream}`, then `origin/main`, merged with the pushed tip). Both submodules are diffed: a private/renet or private/account gitlink move is diffed inside that submodule, and each side counts on its own. `Changed.sides` names the sides the hits reach (renet, account, or both), and the receipt must have run the phase of every one. A submodule range that cannot be computed (an old gitlink commit missing from the local checkout) is UNKNOWN, listed as `(unknown) <submodule> <sha>: <why>`, adds that submodule's side and counts as touched: it is never dropped. A push base that cannot be resolved is unknown in the same way and charges both sides.

EVERY PUSHED COMMIT IS JUDGED ON ITS OWN. A command can send several commits: two pushes with different sources, or one push naming several refspecs. Each refspec's source (a bare ref is its own source, `+` dropped, no refspec at all reads as HEAD) is resolved to a commit, and each distinct commit gets its own range, tree and receipt. Judging only HEAD would admit a pushed commit carrying a trigger change that HEAD reverts. A source git cannot resolve is named on stderr and skipped, since git refuses to push it as well.

`--all` (`--branches`) AND GLOB REFSPECS send every matching local ref, so the refs are enumerated with one `git for-each-ref` (`_enumerated`): every branch for `--all`, every ref a glob source matches for a glob (one `*`, which crosses `/` as it does in git; an unqualified glob is also tried under `refs/` and `refs/heads/`, a superset of git's match). A ref whose tip equals its remote-tracking counterpart (`refs/remotes/<remote>/<branch>` for a `refs/heads/` destination, the remote being the push's own, else `branch.<b>.pushRemote`, `remote.pushDefault`, `branch.<b>.remote`, `origin`) sends nothing and is not judged; a ref with no counterpart (a URL remote, a tag, another namespace) is judged. Each judged tip takes the per-commit path above. A ref set that cannot be enumerated (`for-each-ref` failing, a glob git would call invalid, a tip that is no commit) is UNKNOWN and counts as touched: it is refused like a range with no receipt, never skipped.

`--mirror` IS REFUSED OUTRIGHT, touched or not. It sends every ref, deletes each remote ref missing here and forces each diverged one, so no receipt for one tree can speak for it. Only the escape admits it, and only as `not-runtime` or `deadline`: `vm-unavailable` names a NOT_VERIFIED attempt for one tree, which a push of every ref has none of. An unenumerable ref set is judged the same way.

THE RECEIPT is judged by `rediacc_ci.proof.vm_tier.admit(root, tree, inputs(root, tree), sides, chain_for(root, commit))`: the pushed tree's archive, then `receipt.json`, then the newest archives. VERIFIED with the same tree or the same trigger digest, a renet build equal to the pointer and not modified, and the phase of every touched side run (`phase-missing` otherwise: a renet-only receipt does not admit an account range), admits. `receipt.identity_refusal` then judges the surfaces of the touched sides: a clean console tree (`dirty-tree`), each needed submodule checked out at its pointer (`checkout-mismatch`) and unmodified (`modified-checkout`). The digest (version 3) covers the pointer of each submodule a VM surface lives in. A later commit outside the trigger keeps the digest, so it costs no new VM run. Receipts of an earlier schema are a clean break: the receipt module reads only schema 3, so one admits nothing and backs no escape (`no-receipt`).

TWO WAYS A RECEIPT IS BUILT UP, both in agent/plans/PLAN-vmcheck-incremental.md, and neither widens what admits. A FAILED receipt repaired by `vm:check --only` runs of its failed steps is a VERIFIED receipt like any other once vm_check has re-judged the merged ledger; `vm_tier.validate` holds each `merged` entry to that receipt's tree, inputs, submodules and renet build, so a receipt whose merge does not fit reads as no receipt at all. A `--changed` run that diffed against an earlier VERIFIED commit records it as `trigger.verifiedBase` and may not have run a side the push touches: that side admits only when it is unchanged from that commit to the pushed one (`changed_paths` in push mode, recomputed here, never read from the receipt) and the base tree's own receipt admits it, link by link (`chain-touched`, `chain-broken`, `chain-loop`, `chain-too-long` otherwise).

THE ESCAPE is an environment assignment on the push itself, read from the shared lexer's walk (`run.env`) exactly as `TURBO_PUSH_REASON` is, so a prefix, an earlier `export` and `env NAME=value` count, and prose naming it does not:

    VM_CHECK_PUSH_REASON='<kind>: <why, 40+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push origin <branch>

    vm-unavailable  a NOT_VERIFIED receipt for these inputs exists (such as `account-gateway`), so the attempt was made
    not-runtime     the touched change cannot alter what runs on a VM or the gateway; the why names the account or renet files
    deadline        production or CD state that cannot wait; the why names it

  Every kind needs the `ASKED:` minute, matched against an AskUserQuestion answer in the payload's `transcript_path` within 300 s by `wl_checks._asked_in_transcript`, the evidence rule of the review waiver. That proves an operator answer exists at that minute, not that it answered this question: it narrows the escape to the operator's own turn. A transcript that cannot be read proves nothing, so the escape is refused then.

THE LEDGER. Each admitted escape appends one JSON line per judged push to agent/ledgers/vm-check-push-reasons.jsonl in the tree the push was typed in (ts, branch, head (the pushed commit, not the checkout's HEAD), tree, renet, account (the two gitlinks of that tree), sides, kind, why, asked, hits[:10], receipt), written only once every push of the command is admitted. ORDER 63 puts it behind every refusing guard but `block_backup_unverified_push` at 64, `block_unasked_release` at 62 included, so those have already admitted the command when the line is written. A push a VERIFIED receipt admits writes nothing: the receipt is its record.

SCOPE, as `block_unverified_push` draws it: a command-position `git push` in this checkout or in another linked tree of its repository, such as the landing tree beside it that holds the PR branch; each push is judged in its own tree, against that tree's HEAD, range and receipts (`_push_tree`, PLAN-two-track-merge-dev LT6). NOT judged: a `--dry-run` push (a `--mirror` or `--all` one too, since it publishes nothing); a delete push (`--delete`, `:<ref>`); a push whose source is exactly `origin/main` (the GitLab mirror push of /pr-merge step 6b, `block_unverified_push.pushes_only_origin_main`), which a `--mirror` push never is; a submodule push (the console pointer push carries the range); another repository, by `-C`, `cd` or the payload's `cwd`.

THE OPERATOR. There is no override beyond the ASKED escape: the operator's own `!` command never reaches PreToolUse.

FAILS OPEN, LOUDLY, on a broken environment (no root, the trigger or receipt module will not import, git cannot name the pushed tree): a note on stderr and the push allowed, like the sibling push guards. A verdict is never failed open.
"""

import pathlib

from rediacc_hooks import commit_policy, hookio, plan_gate, shellscan, syspath
from rediacc_hooks.guards import _backup_push, _push_receipts, tables
from rediacc_hooks.guards import block_unverified_push as PUSH

__getattr__ = tables(
    "block_vm_unverified_push",
    "EDGE_CASES",
    "ENVS",
    "FIXTURES",
    "TIP_BRANCH",
    "_ASK",
    "_DEADLINE",
    "_FILES",
    "_PUSH",
    "_UNAVAIL",
    "_advanced",
    "_chained",
    "_other_pointer",
    "_reverted",
    "_stale_not_verified",
    "_with_receipt",
    "plant_receipt",
    "plant_retired",
)

CHAIN = "pre-bash"
OWN_SUITE = True
# The second-last pre-bash slot: the ledger line is the admission record, so it is written only after every other guard but block_backup_unverified_push (63) has let the command through.
ORDER = 62

# The touched test, inverted: planted, every push reads as untouched and passes without a receipt.
DEFECT = ("if not hits:", "if True:")
# The further mutants the own suite plants; each must flip at least one refusal to allowed.
MUTANTS = {
    # LT6: a push typed in a linked tree is judged in this checkout again, against its HEAD and receipts.
    "sibling-tree-unjudged": (
        "if top and store and commit_policy.common_dir(top) == store:",
        "if False:",
    ),
    # The judge stops passing the touched sides, so a receipt that skipped a phase admits.
    "phases-ignored": (
        "verdict = receipt_mod.admit(root_path, tree, digest, sides, chain)",
        "verdict = receipt_mod.admit(root_path, tree, digest, (), chain)",
    ),
    # The chain stops asking what changed since a receipt's VERIFIED base, so a side changed after that base and never run rides the base anyway.
    "chain-touched-ignored": (
        "chain = receipt_mod.chain_for(root_path, commit)",
        "chain = receipt_mod.Chain(commit, lambda old, new: (), lambda t: trigger.inputs(root_path, t))",
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

# This guard's row of the push-receipt table (`_push_receipts`, box CR6): the escape, its kinds and the ledger are declared there and read back here.
ROW = _push_receipts.row("vm:check")
REASON_ENV = ROW.escape
KINDS = ROW.kinds
MIN_WHY = _push_receipts.MIN_WHY
LEDGER_REL = ROW.ledger
HITS_SHOWN = 10
REASON_RE = _push_receipts.REASON_RE
ASKED_TOKEN_RE = _push_receipts.ASKED_TOKEN_RE
ASKED_STRICT_RE = _push_receipts.ASKED_STRICT_RE
TRIGGER_MOD = "rediacc_ci.proof.surfaces"
RECEIPT_MOD = "rediacc_ci.proof.vm_tier"

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
    _git(root, "remote", "add", "origin", _backup_push.OTHER_ORIGIN)
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
    """{tree: [(canonical push line, reason-or-None, args)]} for every judged push in `cmd`, in order, keyed by the tree each is judged in: this checkout, or another linked tree of its repository (`_push_tree`)."""
    created = commit_policy.created_dirs(cmd, base)
    out: dict[str, list[tuple[str, str | None, list[str]]]] = {}
    for run in commit_policy.git_runs(cmd, "push"):
        _, _, args = commit_policy.git_split(run.argv)
        if _skipped(args):
            continue
        tree = _push_tree(run, base, root, created, cmd)
        if not tree:
            continue
        line = " ".join(["git", "push", *args])
        # Before the origin/main exemption: a mirror push is never the GitLab copy of main.
        if not _mirrors(args) and PUSH.pushes_only_origin_main(tree, [line]):
            continue
        out.setdefault(tree, []).append((line, run.env.get(REASON_ENV), args))
    return out


def _push_tree(run, base, root, created, cmd):
    """The tree the walked push `run` is judged in, "" when it is a submodule's or another repository's.

    EACH TREE IS JUDGED BY ITS OWN RECEIPT (PLAN-two-track-merge-dev LT6). A push whose directory sits in a linked tree of this repository (one git common directory: the landing tree beside this checkout, which holds the PR branch) is judged there, against that tree's HEAD, range and `.ci/cache` receipts. `scoped_repo` alone answered this checkout for it, since the landing tree lies outside `root` and pushes to this repository's origin, so the landing tree's push was judged by the development checkout's receipt and HEAD. A git variable or global option that moves git (`git_run_scope_doubt`) keeps the `scoped_repo` answer, which judges this checkout.
    """
    if not shellscan.git_run_scope_doubt(run):
        top = commit_policy.toplevel(commit_policy.run_dir(run, base))
        store = commit_policy.common_dir(root)
        if top and store and commit_policy.common_dir(top) == store:
            return root if pathlib.Path(top).resolve() == pathlib.Path(root).resolve() else top
    # The bound trees are passed (box LT11), as commit_policy._creation_repo does: without them a push in a submodule of the landing tree resolved to this checkout and was judged against this checkout's receipt (2026-11-21, `git -C <landing>/private/renet push origin 1104-1` refused while the landing tree's own receipt was VERIFIED for the pushed tree).
    repo = (
        commit_policy.scoped_repo(
            run, base, root, created, cmd, trees=commit_policy.bound_trees(root)
        )
        or root
    )
    if pathlib.Path(repo).resolve() != pathlib.Path(root).resolve():
        # A submodule (its pointer push carries the range) or another repository.
        return ""
    return root


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


def _not_verified_attempt(root, tree, digest):
    """The NOT_VERIFIED receipt taken for these inputs, or None (the table's reader, judged by `_for_these_inputs`)."""
    return _push_receipts.not_verified_attempt(ROW.id, root, tree, digest, _for_these_inputs)


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


def _judge_reason(ev, reason, root, tree, digest):
    """(kind, why, receipt-or-None) when the escape is admitted, else (None, the refusal line, None). The checks every escape shares are the table's (`_push_receipts.judge_escape`); the NOT_VERIFIED attempt is this row's own."""
    kind, why = _push_receipts.judge_escape(ev, ROW.id, reason, _operator_answered)
    if kind is None:
        return None, why, None
    attempt = None
    if kind == "vm-unavailable" and tree is None:
        blind = (
            "escape-blind: `vm-unavailable` names a NOT_VERIFIED attempt for one tree, and this push sends "
            "refs no single tree describes; only `not-runtime` or `deadline` admits it"
        )
        return None, blind, None
    if kind == "vm-unavailable":
        attempt = _not_verified_attempt(root, tree, digest)
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
    receipt = None
    if attempt is not None:
        receipt = {
            "status": attempt.get("status"),
            "class": (attempt.get("reason") or {}).get("class"),
        }
    return {
        "ts": _push_receipts.now_stamp(),
        "branch": commit_policy.current_branch(root),
        "head": commit,
        "tree": tree,
        "renet": _pointer(root, tree, RENET),
        "account": _pointer(root, tree, ACCOUNT),
        "sides": sorted(sides),
        "kind": kind,
        "why": why,
        "asked": _push_receipts.asked_minute(reason),
        "hits": hits[:HITS_SHOWN],
        "receipt": receipt,
    }


def _record(ev, root, rows):
    _push_receipts.record(ev, ROW.id, root, rows)


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
    # A push of nothing but `refs/backup/**` to its repository's pin is the git-level pre-push hook's to judge (box G5 of PLAN-local-first-delivery, `_backup_push`).
    if _backup_push.admitted(ev, cmd):
        return hookio.ALLOW
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    if not root:
        return hookio.ALLOW
    base = ev.field("cwd") or root
    groups = _pushes(cmd, root, base)
    if not groups:
        return hookio.ALLOW
    try:
        trigger = syspath.import_from_ci(TRIGGER_MOD)
        receipt_mod = syspath.import_from_ci(RECEIPT_MOD)
    except ImportError as exc:
        ev.warn(UNEXAMINED % ("the vm-check trigger or receipt module could not import (%s)" % exc))
        return hookio.ALLOW
    blocks: list[str] = []
    admitted = []
    for tree_root, pushes in groups.items():
        rows = _judge_tree(ev, tree_root, pushes, trigger, receipt_mod, blocks)
        if rows:
            admitted.append((tree_root, rows))
    if blocks:
        ev.warn_raw("\n".join(blocks))
        return hookio.DENY
    for tree_root, rows in admitted:
        _record(ev, tree_root, rows)
    return hookio.ALLOW


def _judge_tree(ev, root, pushes, trigger, receipt_mod, blocks):
    """The ledger rows of the escapes admitted for `pushes`, all typed in the tree `root`; each refusal is appended to `blocks`."""
    root_path = pathlib.Path(root)
    tips, unresolved, blind = _tips(root, pushes)
    for src in unresolved:
        ev.warn(UNEXAMINED % ("git could not name the pushed commit of `%s`" % src))

    rows = []
    for label, hits, sending in blind:
        refusals = []
        for index in sending:
            line, reason, _args = pushes[index]
            kind, why, _attempt = _judge_reason(ev, reason, root_path, None, "")
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
        chain = receipt_mod.chain_for(root_path, commit)
        verdict = receipt_mod.admit(root_path, tree, digest, sides, chain)
        if verdict.ok:
            continue
        refusals = []
        for index in sending:
            line, reason, _args = pushes[index]
            kind, why, attempt = _judge_reason(ev, reason, root_path, tree, digest)
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
    return rows
