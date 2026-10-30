"""Refuse a `git push` whose outgoing range changes renet Go code unless a passing renet test receipt covers the pushed renet tree, or the operator answered for it.

THE ORDER. Operator ruling ASKED:2026-10-30 ("Path map, receipt at push"), box M3 of agent/plans/PLAN-renet-change-test-triggers.md. A change in pkg/license or pkg/functions used to leave this machine with no `go test` at all; the first full run was CI's test-renet-go after the push.

TWO PUSH FORMS ARE JUDGED, because a renet change leaves by either:

    console   `git push` in this checkout: each pushed console commit whose private/renet gitlink differs from the gitlink at its merge-base with the push base. The renet range is old gitlink..new gitlink, the tree is the new gitlink's tree.
    renet     `git -C private/renet push`, `cd private/renet && git push`, or a payload `cwd` inside private/renet: each pushed renet commit against its merge-base with the renet push base. The tree is that commit's tree.

WHAT IS PUSHED is `block_vm_unverified_push`'s reading (`VM._tips`), called with the repository the push runs in: every refspec source resolved and judged on its own, `--all` and glob refspecs enumerated, `--mirror` and an unenumerable ref set judged blind. The push base is `rediacc_ci.proof.surfaces.push_base` (`@{push}`, `origin/<branch>`, `@{upstream}`, `origin/main`) run in that repository.

WHAT A RANGE REQUIRES is never decided here. `wl_renettests.required_for` reads `.ci/config/renet-test-map.json` exactly as `scripts/gates/check-renet-test-map.ts` does (a parity test holds the two together): the packages the changed paths reach, their dependents and the `always` set; every package for go.mod, go.sum or a Go path no glob claims; nothing for docs. A range git cannot compute (a commit missing from the checkout, no push base) is UNKNOWN and requires every package: it is never dropped.

THE RECEIPT is `wl_renettests.read_receipt(<renet tree>)`, written by a passing `npm run check:ci-renet-test-map` (ci:quick runs it). It admits when it ran every required package (`all` admits anything). A receipt for another tree admits nothing: the tree is the key.

THE ESCAPE is the repo's operator-ASKED convention (`VM_CHECK_PUSH_REASON`'s shape, read from the shared lexer's `run.env`), with no kind that a receipt could have answered:

    RENET_TEST_PUSH_REASON='<kind>: <why, 40+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push ...

    environment  the selected tests fail here for a reason the why names (root, a kernel feature) and CI's test-renet-go runs them
    deadline     production or CD state that cannot wait; the why names it

  The `ASKED:` minute must match an AskUserQuestion answer in the payload's transcript within 300 s (`wl_checks._asked_in_transcript`). Each admitted escape appends one line per judged commit to agent/ledgers/renet-test-push-reasons.jsonl, written only once every push of the command is admitted.

SCOPE: a command-position `git push` in this checkout or in its private/renet. NOT judged: a `--dry-run` push, a delete push, the GitLab mirror push of `origin/main` (console form), another repository.

FAILS OPEN, LOUDLY, on a broken environment (no root, the map or a helper module will not load): a note on stderr and the push allowed, like the sibling push guards. A verdict is never failed open.
"""

import datetime
import json
import pathlib

from rediacc_hooks import commit_policy, hookio, plan_gate, syspath
from rediacc_hooks.guards import block_unverified_push as PUSH
from rediacc_hooks.guards import block_vm_unverified_push as VM

CHAIN = "pre-bash"
OWN_SUITE = True
# After every other refusing push guard, so its ledger line is written only for a command the rest admitted. The vm-check (63) and backup (64) ledgers are written before this slot; see the report that added it for the renumbering that would put this guard ahead of them.
ORDER = 66

# The touched test, inverted: planted, every range reads as selecting nothing and passes without a receipt.
DEFECT = ('if not required["packages"]:', "if True:")
# The further mutants the own suite plants; each must flip at least one refusal to allowed.
MUTANTS = {
    # Any receipt for the tree admits, whatever packages it ran.
    "partial-receipt-admits": (
        "missing = WR.uncovered(receipt, required)",
        "missing = [] if receipt else None",
    ),
    # The renet form is dropped: a push from inside private/renet is never judged.
    "renet-form-ignored": (
        "if top == renet_root:",
        "if False:",
    ),
    "asked-always-true": (
        "return bool(wl_checks._asked_in_transcript(reason, transcript))",
        "return True",
    ),
}

REASON_ENV = "RENET_TEST_PUSH_REASON"
KINDS = ("environment", "deadline")
MIN_WHY = 40
LEDGER_REL = "agent/ledgers/renet-test-push-reasons.jsonl"
SHOWN = 10
SURFACES_MOD = "rediacc_ci.proof.surfaces"
RENET = "private/renet"
COMMAND = "npm run check:ci-renet-test-map"

UNEXAMINED = "block-renet-untested-push: %s; this push passed UNEXAMINED."


# --------------------------------------------------------------------------- fixture worlds

CONSOLE_READ = "packages/shared/src/subscription/schema.generated.json"
FIXTURE_MAP = {
    "schema": 1,
    "module": "github.com/rediacc/renet",
    "whole": [{"glob": "go.mod", "why": "the module graph reaches every package"}],
    "always": [],
    "entries": [
        {"glob": "cmd/renet/**", "packages": ["cmd/renet"], "dependents": []},
        {
            "glob": "pkg/license/**",
            "packages": ["pkg/license"],
            "dependents": ["cmd/renet"],
        },
        {
            "glob": "pkg/sandbox/**",
            "packages": ["pkg/sandbox"],
            "dependents": ["cmd/renet"],
        },
    ],
    "console": [
        {"glob": CONSOLE_READ, "packages": ["pkg/license"], "why": "a renet test reads it"}
    ],
}
LICENSE_FILE = "pkg/license/store.go"
UNMAPPED_FILE = "pkg/brandnew/x.go"
RECEIPTS_REL = ".ci/cache/renet-receipts"


def world(path, renet_files=(), missing_old=False):
    """`block_vm_unverified_push.world` (a console checkout on `1008-1`, renet commit A at origin/main's gitlink and B on the branch when `renet_files` are named) plus this guard's map and a renet `origin/main` at A, so the renet push form has a base. Returns the console path."""
    root = VM.world(path, renet_files=renet_files, missing_old=missing_old)
    renet = root / RENET
    VM._put(root, ".ci/config/renet-test-map.json", json.dumps(FIXTURE_MAP, indent=2) + "\n")
    VM._git(root, "add", ".ci/config/renet-test-map.json")
    VM._git(root, "commit", "-q", "-m", "map")
    VM._git(renet, "remote", "add", "origin", "https://github.com/fixture/renet.git")
    first = VM._git(renet, "rev-list", "--max-parents=0", "HEAD")
    VM._git(renet, "update-ref", "refs/remotes/origin/main", first)
    return root


def plant_receipt(root, packages, every=False, commit="HEAD"):
    """A passing receipt for the renet tree of `commit` (in private/renet) under `<root>/RECEIPTS_REL`, the shape the gate writes."""
    renet = pathlib.Path(root) / RENET
    tree = VM._git(renet, "rev-parse", "%s^{tree}" % commit)
    receipts = pathlib.Path(root) / RECEIPTS_REL
    receipts.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": 1,
        "renetTree": tree,
        "renetHead": VM._git(renet, "rev-parse", commit),
        "dirty": False,
        "all": every,
        "packages": sorted(packages),
        "consoleTrees": [],
        "base": "",
        "passed": 3,
        "finishedAt": "2026-01-01T00:00:00Z",
    }
    (receipts / ("%s.json" % tree)).write_text(json.dumps(doc) + "\n", encoding="utf-8")
    return root


def _new_missing(path):
    """The branch moves the renet gitlink to a commit this checkout does not hold, so no local run can have tested it."""
    root = world(path)
    VM._git(root, "update-index", "--cacheinfo", "160000,%s,%s" % (MISSING_NEW, RENET))
    VM._git(root, "commit", "-q", "-m", "gitlink to a commit not fetched")
    return root


def _console_read(path, receipt=False):
    """The renet pointer does not move, but the branch changes a console file a renet test reads, so the renet packages that read it need a receipt."""
    root = world(path)
    VM._put(root, CONSOLE_READ, "{}\n")
    VM._git(root, "add", CONSOLE_READ)
    VM._git(root, "commit", "-q", "-m", "console read")
    return plant_receipt(root, ["pkg/license"]) if receipt else root


MISSING_NEW = "fedcba9876543210fedcba9876543210fedcba98"

FIXTURES = {
    "rnt-docs": world,
    "rnt-new-missing": _new_missing,
    "rnt-renet-docs": lambda p: world(p, renet_files=("README.md",)),
    "rnt-license": lambda p: world(p, renet_files=(LICENSE_FILE,)),
    "rnt-license-receipt": lambda p: plant_receipt(
        world(p, renet_files=(LICENSE_FILE,)), ["cmd/renet", "pkg/license"]
    ),
    "rnt-license-partial": lambda p: plant_receipt(
        world(p, renet_files=(LICENSE_FILE,)), ["pkg/license"]
    ),
    "rnt-license-seed-receipt": lambda p: plant_receipt(
        world(p, renet_files=(LICENSE_FILE,)), ["cmd/renet", "pkg/license"], commit="HEAD~1"
    ),
    "rnt-unmapped-partial": lambda p: plant_receipt(
        world(p, renet_files=(UNMAPPED_FILE,)), ["cmd/renet", "pkg/license", "pkg/sandbox"]
    ),
    "rnt-unmapped-all": lambda p: plant_receipt(
        world(p, renet_files=(UNMAPPED_FILE,)), [], every=True
    ),
    "rnt-missing-old": lambda p: world(p, renet_files=(LICENSE_FILE,), missing_old=True),
    "rnt-console-read": _console_read,
    "rnt-console-read-receipt": lambda p: _console_read(p, receipt=True),
}

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (
        name[len("rnt-") :],
        {
            "CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name,
            "RENET_TEST_RECEIPT_DIR": "{FIXTURE:%s}/%s" % (name, RECEIPTS_REL),
        },
        {},
    )
    for name in FIXTURES
]

_ASK = " ASKED:2026-01-01T00:00Z"
_ENVIRONMENT = "pkg/daemon netns tests need root here; CI test-renet-go runs them under sudo"
_DEADLINE = "the 03:00Z CD promote carries the broken stable licence check otherwise"
EDGE_CASES = [
    ("a console push", "git push origin 1008-1"),
    ("an implicit console push", "git push"),
    ("a renet push by -C", "git -C private/renet push origin main"),
    ("a renet push after cd", "cd private/renet && git push origin main"),
    (
        "environment",
        "%s='environment: %s%s' git push origin 1008-1" % (REASON_ENV, _ENVIRONMENT, _ASK),
    ),
    ("deadline", "%s='deadline: %s%s' git push origin 1008-1" % (REASON_ENV, _DEADLINE, _ASK)),
    (
        "an unknown kind",
        "%s='because: %s%s' git push origin 1008-1" % (REASON_ENV, _DEADLINE, _ASK),
    ),
    ("no ASKED", "%s='deadline: %s' git push origin 1008-1" % (REASON_ENV, _DEADLINE)),
    ("a dry run", "git push --dry-run origin 1008-1"),
    ("a renet dry run", "git -C private/renet push --dry-run origin main"),
    ("a delete push", "git push origin --delete 1007-1"),
    ("prose naming a push", "echo 'git -C private/renet push origin main'"),
    ("a mirror push", "git push --mirror origin"),
]


# --------------------------------------------------------------------------- what the command pushes


def _pushes(cmd, root, base):
    """({"console": [...], "renet": [...]}) of (canonical push line, reason-or-None, args) for every judged push of this checkout or its private/renet in `cmd`."""
    created = commit_policy.created_dirs(cmd, base)
    root_path = pathlib.Path(root).resolve()
    renet_root = (root_path / RENET).resolve()
    out: dict[str, list[tuple[str, str | None, list[str]]]] = {"console": [], "renet": []}
    for run in commit_policy.git_runs(cmd, "push"):
        _, _, args = commit_policy.git_split(run.argv)
        if VM._skipped(args):
            continue
        repo = commit_policy.scoped_repo(run, base, root, created) or root
        top = pathlib.Path(repo).resolve()
        line = " ".join(["git", "push", *args])
        if top == renet_root:
            out["renet"].append((line, run.env.get(REASON_ENV), args))
        elif top == root_path:
            if not VM._mirrors(args) and PUSH.pushes_only_origin_main(root, [line]):
                continue
            out["console"].append((line, run.env.get(REASON_ENV), args))
    return out


def _base(surfaces, repo, tip):
    """(merge-base of `tip` with the push base of `repo`, label) or (None, why)."""
    git = surfaces.make_git(pathlib.Path(repo))
    resolved = surfaces.push_base(git, commit_policy.current_branch(str(repo)) or None)
    if not resolved.ref:
        return None, "no push base: tried %s" % ", ".join(resolved.tried)
    merge_base = git(["merge-base", tip, resolved.ref])
    if not merge_base:
        return None, "no merge base of %s and %s" % (tip[:12], resolved.ref)
    return merge_base, "%s via %s" % (merge_base[:12], resolved.via or resolved.ref)


def _console_changed(root, merge_base, commit):
    """The console paths a pushed console commit changes since its merge-base, for the map's `console` rows (renet tests that read console files). Empty when the base is unknown."""
    if not merge_base:
        return []
    out = (
        commit_policy.git(["diff", "--no-renames", "--name-only", merge_base, commit], cwd=root)
        or ""
    )
    return [
        line
        for line in out.splitlines()
        if line and not line.startswith(RENET + "/") and line != RENET
    ]


def _range(wr, surfaces, root, form, commit):
    """(renet commit, renet tree or None, changed paths or None, base label, console changed) for one pushed commit; changed is None when the range is unknown. A console push whose renet pointer did not move still reports its console paths, since renet tests read some console files."""
    renet = pathlib.Path(root) / RENET
    if form == "renet":
        merge_base, label = _base(surfaces, renet, commit)
        tree = commit_policy.git(["rev-parse", "%s^{tree}" % commit], cwd=str(renet))
        if merge_base is None:
            return commit, tree, None, label, []
        return commit, tree, wr.changed_between(renet, merge_base, commit), label, []
    new = commit_policy.git(["rev-parse", "%s:%s" % (commit, RENET)], cwd=root)
    if not new:
        return None, None, [], "", []
    merge_base, label = _base(surfaces, root, commit)
    console = _console_changed(root, merge_base, commit)
    old = (
        commit_policy.git(["rev-parse", "%s:%s" % (merge_base, RENET)], cwd=root)
        if merge_base
        else None
    )
    tree = commit_policy.git(["rev-parse", "%s^{tree}" % new], cwd=str(renet))
    if old == new:
        return new, tree, [], label, console
    if not old:
        return new, tree, None, label if merge_base is None else "%s pins no renet" % label, console
    return (
        new,
        tree,
        wr.changed_between(renet, old, new),
        "renet %s..%s (%s)" % (old[:12], new[:12], label),
        console,
    )


# --------------------------------------------------------------------------- the escape


def _operator_answered(ev, reason):
    transcript = ev.field("transcript_path")
    if not transcript:
        return False
    syspath.on_sys_path(plan_gate.STOP_DIR)
    try:
        import wl_checks
    except ImportError as exc:
        ev.warn(
            "block-renet-untested-push: wl_checks could not import (%s), so no ASKED: minute can be proven."
            % exc
        )
        return False
    return bool(wl_checks._asked_in_transcript(reason, transcript))


def _judge_reason(ev, reason):
    """(kind, why) when the escape is admitted, else (None, the refusal line)."""
    if reason is None:
        return None, "escape-missing: no `%s=` on it" % REASON_ENV
    m = VM.REASON_RE.match(reason)
    kind, rest = (m.group(1).lower(), m.group(2)) if m else ("", reason)
    if kind not in KINDS:
        return None, "escape-kind: `%s=%r`: the kind must be one of %s" % (
            REASON_ENV,
            reason,
            ", ".join(KINDS),
        )
    why = VM.ASKED_TOKEN_RE.sub("", rest).strip()
    if len(why) < MIN_WHY:
        return (
            None,
            "escape-why: `%s`: the why is %d characters; at least %d name the tests or the deadline"
            % (
                reason,
                len(why),
                MIN_WHY,
            ),
        )
    if not VM.ASKED_STRICT_RE.search(reason):
        return None, "escape-asked: `%s` carries no ASKED:<YYYY-MM-DDTHH:MM>Z" % reason
    if not _operator_answered(ev, reason):
        return (
            None,
            "escape-unproven: its ASKED: minute matches no AskUserQuestion answer in this session's transcript (within 300 s)",
        )
    return kind, why


def _row(root, form, commit, tree, kind, why, reason, packages):
    asked = VM.ASKED_STRICT_RE.search(reason or "")
    return {
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": commit_policy.current_branch(root),
        "form": form,
        "head": commit,
        "renetTree": tree,
        "kind": kind,
        "why": why,
        "asked": asked.group(0)[len("ASKED:") :] if asked else "",
        "packages": packages[:SHOWN],
    }


def _record(ev, root, rows):
    path = pathlib.Path(root) / LEDGER_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    except OSError as exc:
        ev.warn(
            "block-renet-untested-push: the admission was NOT recorded in %s (%s)."
            % (LEDGER_REL, exc)
        )


REFUSAL = """BLOCKED: this push changes renet Go code and no passing renet test receipt covers renet tree %(tree)s (%(form)s push, commit %(commit)s, sent as `%(src)s`).

Receipt: %(verdict)s
Selected (%(scope)s, range %(base)s):
%(packages)s
Run the mapped Go tests on exactly that tree: private/renet checked out at %(renet)s with no
uncommitted changes in it (the receipt is keyed on the tree the run tested), then push again:

    %(command)s

%(lines)sWhen the tests cannot pass here, the operator decides, and the escape names the minute of
that answer (an AskUserQuestion in this session, matched within 300 s):

    %(env)s='<environment|deadline>: <why, %(min)d+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push ...

Each admitted escape is appended to %(ledger)s.
The operator's own `!` command does not pass through this guard.
"""

BLIND_REFUSAL = """BLOCKED: this push sends refs that no renet test receipt can describe (`%(src)s`).

Why:
%(hits)s
Push the branches one by one, so each pushed commit is judged against its own receipt, or have
the operator decide, naming the minute of that answer:

%(lines)s    %(env)s='deadline: <why, %(min)d+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z' git push ...
"""


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    if not root:
        return hookio.ALLOW
    base = ev.field("cwd") or root
    by_form = _pushes(cmd, root, base)
    if not by_form["console"] and not by_form["renet"]:
        return hookio.ALLOW
    syspath.on_sys_path(plan_gate.STOP_DIR)
    try:
        import wl_renettests as WR

        surfaces = syspath.import_from_ci(SURFACES_MOD)
    except ImportError as exc:
        ev.warn(UNEXAMINED % ("a helper module could not import (%s)" % exc))
        return hookio.ALLOW
    test_map = WR.load_map(root)
    if test_map is None:
        ev.warn(UNEXAMINED % ("%s could not be read" % WR.MAP_REL))
        return hookio.ALLOW

    rows = []
    blocks = []
    for form, pushes in (("console", by_form["console"]), ("renet", by_form["renet"])):
        if not pushes:
            continue
        repo = root if form == "console" else str(pathlib.Path(root) / RENET)
        tips, unresolved, blind = VM._tips(repo, pushes)
        for src in unresolved:
            ev.warn(UNEXAMINED % ("git could not name the pushed commit of `%s`" % src))
        for label, hits, sending in blind:
            refusals = []
            for index in sending:
                line, reason, _args = pushes[index]
                kind, why = _judge_reason(ev, reason)
                if kind != "deadline":
                    refusals.append(
                        "  %s\n    escape refused: %s\n"
                        % (line, why if kind is None else "only `deadline` admits a blind push")
                    )
                    continue
                rows.append(_row(root, form, "", "", kind, why, reason, []))
            if refusals:
                blocks.append(
                    BLIND_REFUSAL
                    % {
                        "src": label,
                        "hits": "".join("  %s\n" % h for h in hits),
                        "lines": "".join(refusals) + "\n",
                        "env": REASON_ENV,
                        "min": MIN_WHY,
                    }
                )
        for commit, (src, sending) in tips.items():
            renet_commit, tree, changed, base_label, console_changed = _range(
                WR, surfaces, root, form, commit
            )
            if changed is None:
                required = {
                    "all": True,
                    "packages": WR.all_packages(test_map),
                    "all_why": [
                        "the renet range is unknown: %s"
                        % (base_label or "a commit is missing from the checkout")
                    ],
                    "mapped": 0,
                }
            else:
                required = WR.required_for(test_map, changed, console_changed=console_changed)
            if not required["packages"]:
                continue
            receipt = WR.read_receipt(tree)
            missing = WR.uncovered(receipt, required)
            if missing == []:
                continue
            if not tree:
                verdict = (
                    "[no-tree] renet commit %s is not in this checkout, so no run here can have tested it"
                    % (renet_commit or commit)[:12]
                )
            elif missing is None:
                verdict = "[no-receipt] none for renet tree %s in %s" % (
                    tree[:12],
                    WR.receipt_dir(),
                )
            else:
                verdict = "[partial] the receipt for this tree did not run: %s" % ", ".join(
                    missing[:SHOWN]
                )
            refusals = []
            for index in sending:
                line, reason, _args = pushes[index]
                kind, why = _judge_reason(ev, reason)
                if kind is None:
                    refusals.append("  %s\n    escape refused: %s\n" % (line, why))
                    continue
                rows.append(
                    _row(root, form, commit, tree or "", kind, why, reason, required["packages"])
                )
            if not refusals:
                continue
            shown = "".join("  %s\n" % p for p in required["packages"][:SHOWN])
            if len(required["packages"]) > SHOWN:
                shown += "  ... and %d more\n" % (len(required["packages"]) - SHOWN)
            if required["all"]:
                shown += "".join("  every package: %s\n" % w for w in required["all_why"][:3])
            blocks.append(
                REFUSAL
                % {
                    "tree": (tree or "?")[:12],
                    "form": form,
                    "commit": commit[:12],
                    "renet": (renet_commit or commit)[:12],
                    "src": src,
                    "verdict": verdict,
                    "scope": "every package"
                    if required["all"]
                    else "%d package(s)" % len(required["packages"]),
                    "base": base_label or "unresolved",
                    "packages": shown,
                    "command": COMMAND,
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
