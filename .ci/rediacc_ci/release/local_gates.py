"""The gates a local release must pass before it builds or publishes anything (box W2-A of agent/plans/PLAN-local-release.md).

    PYTHONPATH=.ci python3 -m rediacc_ci.release.local_gates --channel edge|stable [--version V] [--branch-release] [--commit <sha>] [--force-asked ASKED:<YYYY-MM-DDTHH:MM>Z]

Exit 0 when every gate admits, 1 with one `local-gates: <code>: <why>` line per refusal otherwise, 2 on a usage error. Every gate runs, so one run names every refusal rather than the first.

`--commit <sha>` (D1.8 of PLAN-push-decoupling) names an ancestor of the branch tip (HEAD): every gate below then judges that commit, its tree, its tag range and its release clone, in place of HEAD. A sha that is not an ancestor refuses with code `commit`.

THE GATES, each a refusal unless it holds:
  ci-quick     a whole, green ci:quick receipt judged `HEAD^{tree}`: the push guard's own `read_receipt` (the per-tree copy `.ci/cache/receipts/<tree>.json` first, then the latest file) and `receipt_refusal`, imported the way `rediacc_ci.ci.gate_model` imports that guard, never copied. A red receipt has one escape, `RELEASE_RED_WAIVER='<gate>[,<gate>] ASKED:<YYYY-MM-DDTHH:MM>Z <reason>'` (operator ruling 2026-11-16, `ci_quick_verdict`): a whole receipt whose `headTree` is HEAD's tree exactly is admitted when every red gate not in carried-reds.json is named and each is `check:ci-ops-health` or prints `UPSTREAM REACHABILITY FAILURE` when re-run now with `npm run --silent <gate>`, and the ASKED minute is proven against the transcript as `--force-asked` is. The admitted waiver is printed as one `local-gates: red-waiver admitted: <json>` line.
  vm-check     the vm:check trigger paths changed since the previous release tag (the highest-versioned `v*` tag reachable from HEAD, `git tag --merged HEAD --sort=-v:refname`) are admitted by a VERIFIED receipt, through `surfaces.changed_paths(root, <tag>, "push")` and `vm_tier.admit`. No hit is "not required", and admits.
  backup       when the backup paths moved since that tag, a VERIFIED backup receipt covers the tree: `backup_check_trigger.check(root, "HEAD", base=<tag>)`, the reader the backup push guard and the git-level pre-push hook run. Exit 1 and 2 (cannot judge) both refuse (decision 4).
  clone        a fresh clone of HEAD with its submodules at `.ci/cache/release/<tree>/` is clean, names the tree, and every submodule sits at its gitlink, unmodified (decision 1). The shared checkout always carries other sessions' ledgers, so cleanliness is judged on the clone, which is also where the release builds. Each submodule is cloned from this checkout's own copy of it (`<root>/<path>`, else `<root>/.git/modules/<name>`), never from the network; a pointer commit the local copy lacks is a refusal. HEAD equal to origin/main (below) is what makes those pointers the merged ones; under `--branch-release` they are the pushed branch head's.
  origin-main  a fresh `git fetch origin main` succeeded, and HEAD equals origin/main. A failed fetch refuses: a stale origin/main would pass vacuously. Under `--branch-release` (edge only; `release:local --channel edge --workers-only --branch-release` passes it, operator ruling ASKED:2026-11-13T05:02Z) equality is not asked: HEAD must be the tip of a branch on origin (`git ls-remote origin 'refs/heads/*'`), and origin/main after that same fetch must be an ancestor of HEAD (`git merge-base --is-ancestor`). A failed branch read or an ancestry git cannot answer refuses. Every other gate runs unchanged.
  lock         (edge) the release lock is free: the R2 sentinel `cli/v<V>/.released` of the version about to be cut is absent (`release_state_validator.sentinel_exists` through `order.live_sentinel_exists`; UNKNOWN refuses) and `check_existing_release` finds neither the tag nor the GitHub Release.
  stable       (stable) the edge version V promoted is tagged `v<V>` and sealed (sentinel present), its edge record `release-records/v<V>/edge.json` in R2 carries `smoke_rc` 0, and `check_soak_period.select` finds it soaked SOAK_DAYS from the record's `recorded_at`. `--force-asked` skips the age only when its ASKED minute is proven against an AskUserQuestion answer in the transcript (`wl_checks._asked_in_transcript`, as `block_vm_unverified_push` proves its escape); the transcript is `--transcript` or `$REDIACC_TRANSCRIPT_PATH`, and none proves nothing.

Every reader that touches the network or R2 is a keyword seam of `check`, so the tests run offline; `main` wires the live ones. The R2 reads need the R2 trio, so a live run goes through `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile r2-artifacts -- ...`; without it the sentinel reads UNKNOWN and the lock refuses.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import functools
import importlib
import itertools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_record
from rediacc_ci.drills import backup_check_trigger
from rediacc_ci.proof import surfaces, vm_tier
from rediacc_ci.release import check_soak_period, order

SELF = "rediacc_ci.release.local_gates"
CHANNELS = ("edge", "stable")
CLONE_REL = ".ci/cache/release"
# The soak promote-stable.yml (`env: SOAK_DAYS: 7`) applies; the local stable promote applies the same.
SOAK_DAYS = 7
EDGE_RECORD_KEY = "release-records/v%s/edge.json"
TRANSCRIPT_ENV = "REDIACC_TRANSCRIPT_PATH"
GIT_TIMEOUT_S = 600
FETCH_TIMEOUT_S = 120
ASKED_RE = re.compile(r"ASKED:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z")

# The seams. Each answers the question its gate asks of the world, None meaning "could not tell".
Fetch = Callable[[pathlib.Path], "tuple[str | None, str]"]
SentinelProbe = Callable[[str], "bool | None"]
ExistingProbe = Callable[[pathlib.Path, str], "tuple[bool, str]"]
NextVersion = Callable[[pathlib.Path], "str | None"]
EdgeVersion = Callable[[], "str | None"]
TagCommit = Callable[[str], "str | None"]
RecordReader = Callable[[str], "tuple[dict[str, Any] | None, str]"]
AskedProof = Callable[[str], bool]
Heads = Callable[[pathlib.Path], "tuple[dict[str, str] | None, str]"]
Ancestor = Callable[[pathlib.Path, str, str], "bool | None"]


@dataclasses.dataclass(frozen=True)
class Refusal:
    code: str
    message: str

    def line(self) -> str:
        # One line per refusal: a multi-line reason (the backup check's) is folded, never truncated.
        text = " | ".join(part.strip() for part in self.message.splitlines() if part.strip())
        return "local-gates: %s: %s" % (self.code, text)


def _git(root: pathlib.Path, *args: str, timeout: int = GIT_TIMEOUT_S) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _rev(root: pathlib.Path, spec: str) -> str | None:
    rc, out, _err = _git(root, "rev-parse", "--verify", "--quiet", spec)
    return out if rc == 0 and out else None


def previous_tag(root: pathlib.Path, tip: str = "HEAD") -> str | None:
    """The highest-versioned `v*` tag reachable from `tip` (HEAD, or the pinned commit of `--commit`), or None when there is none.

    `git tag --merged HEAD --sort=-v:refname`, the version order `resolve_version` reads, and not `git describe`: describe answers the tag nearest by commit distance, so a lower tag on a merged side branch would start the range after the real previous release.
    """
    rc, out, _err = _git(root, "tag", "--merged", tip, "--list", "v*", "--sort=-v:refname")
    first = out.splitlines()[0].strip() if rc == 0 and out else ""
    return first or None


# --------------------------------------------------------------------------- (a) ci:quick


@functools.cache
def _push_guard() -> Any:
    """The push guard `block_unverified_push`, imported once per process from this checkout's `.claude`."""
    paths.on_sys_path(paths.repo_root() / ".claude")
    return importlib.import_module("rediacc_hooks.guards.block_unverified_push")


def ci_quick_refusal(root: pathlib.Path, tree: str) -> Refusal | None:
    """The ci-quick verdict with no waiver: today's refusal, byte for byte."""
    return ci_quick_verdict(root, tree, waiver_text=None, asked_proof=transcript_proof(None))[0]


# THE RED WAIVER (operator ruling 2026-11-16 "Narrow release escape"). A production break check:ci-ops-health reports stays red until its fix is deployed, and only this release deploys it; an upstream outage blocks the same way. The waiver is the one way past a red receipt, and it is narrow on purpose: the HEAD tree (named by the receipt, or reached through record-only advances that touched nothing a waived gate reads), every red gate named, each named red gate on WAIVABLE_BY_NAME or printing UPSTREAM_MARKER when re-run now, and an ASKED minute proven against the transcript.
WAIVER_ENV = "RELEASE_RED_WAIVER"
WAIVABLE_BY_NAME = frozenset({"check:ci-ops-health"})
# `core.upstream.report_unreachable`'s wording, which `ci_diagnose`'s upstream-unreachable signature also reads. The receipt records no gate output, so a red gate is re-run at release time and its own output is what is judged.
UPSTREAM_MARKER = "UPSTREAM REACHABILITY FAILURE"
WAIVER_LINE = "local-gates: red-waiver admitted: "
RERUN_TIMEOUT_S = 900
WAIVER_RE = re.compile(r"(?P<gates>\S+) (?P<asked>ASKED:\S+) (?P<reason>\S.*)", re.DOTALL)
GATE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._-]*")
WAIVER_FORM = "%s='<gate>[,<gate>] ASKED:<YYYY-MM-DDTHH:MM>Z <reason>'" % WAIVER_ENV
GateRerun = Callable[[pathlib.Path, str], "tuple[int | None, str]"]


@dataclasses.dataclass(frozen=True)
class RedWaiver:
    gates: tuple[str, ...]
    asked: str
    reason: str


@dataclasses.dataclass(frozen=True)
class WaiverAdmission:
    """A waiver that admitted a red receipt: the red gates it covered, why each was waivable, and the warnings."""

    gates: tuple[str, ...]
    asked: str
    reason: str
    tree: str
    evidence: dict[str, str]
    warnings: tuple[str, ...]

    def record(self) -> dict[str, Any]:
        """The deploy record's `red_waiver` field."""
        return {
            "gates": list(self.gates),
            "asked": self.asked,
            "reason": self.reason,
            "tree": self.tree,
            "evidence": dict(self.evidence),
            "warnings": list(self.warnings),
        }

    def line(self) -> str:
        """One stdout line. It carries "admitted", so the entry's `gates_verdict` never reads it as a refusal."""
        return WAIVER_LINE + json.dumps(self.record(), sort_keys=True)


def waiver_from_lines(lines: list[str]) -> dict[str, Any] | None:
    """The `red_waiver` record field from the gates child's stdout lines, or None when no waiver admitted."""
    for line in lines:
        if line.startswith(WAIVER_LINE):
            doc = json.loads(line[len(WAIVER_LINE) :])
            return doc if isinstance(doc, dict) else None
    return None


def parse_red_waiver(text: str) -> tuple[RedWaiver | None, str]:
    """(waiver, "") or (None, why `text` is not `<gate>[,<gate>] ASKED:<YYYY-MM-DDTHH:MM>Z <reason>`)."""
    m = WAIVER_RE.fullmatch(text.strip())
    if m is None:
        return None, "%r is not %s" % (text, WAIVER_FORM)
    if not ASKED_RE.fullmatch(m["asked"]):
        return None, "%r is not ASKED:<YYYY-MM-DDTHH:MM>Z" % m["asked"]
    gates = tuple(m["gates"].split(","))
    bad = [g for g in gates if not GATE_ID_RE.fullmatch(g)]
    if bad:
        return None, "names no gate id in %s" % ", ".join(repr(g) for g in bad)
    if len(set(gates)) != len(gates):
        return None, "names a gate twice: %s" % m["gates"]
    return RedWaiver(gates=gates, asked=m["asked"], reason=m["reason"].strip()), ""


def live_rerun(root: pathlib.Path, gate: str) -> tuple[int | None, str]:
    """(exit code, stdout and stderr) of `npm run --silent <gate>` in `root`, or (None, why it could not run). The script is looked up in package.json first: under `--silent` a missing script exits 1 with nothing printed, which reads like a real red."""
    try:
        scripts = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts")
    except (OSError, ValueError, AttributeError) as exc:
        return None, "package.json in %s could not be read: %s" % (root, exc)
    if not isinstance(scripts, dict) or gate not in scripts:
        return None, "%s is not a script in %s/package.json" % (gate, root)
    npm = shutil.which("npm")
    if npm is None:
        return None, "npm is not on PATH"
    try:
        proc = subprocess.run(
            [npm, "run", "--silent", gate],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=RERUN_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return None, "`npm run %s` did not finish within %ds" % (gate, RERUN_TIMEOUT_S)
    except OSError as exc:
        return None, "`npm run %s` could not start: %s" % (gate, exc)
    return proc.returncode, proc.stdout + proc.stderr


def _waivable(root: pathlib.Path, gate: str, rerun: GateRerun) -> tuple[bool, str]:
    """(waivable, evidence or why not) for one red gate the waiver names."""
    if gate in WAIVABLE_BY_NAME:
        return True, "allowlisted by name"
    rc, out = rerun(root, gate)
    if rc is None:
        return False, "%s could not be re-run, so its outage is not proven: %s" % (gate, out)
    if rc == 0:
        return False, (
            "%s passed on re-run, so the receipt's red is not an outage; re-run `npm run ci:quick`"
            % gate
        )
    if UPSTREAM_MARKER in out:
        return True, "re-run exited %d printing %s" % (rc, UPSTREAM_MARKER)
    return False, (
        "%s is neither allowlisted by name (%s) nor printed %s on re-run (exit %d), so its red is a defect to fix"
        % (gate, ", ".join(sorted(WAIVABLE_BY_NAME)), UPSTREAM_MARKER, rc)
    )


def ci_quick_verdict(
    root: pathlib.Path,
    tree: str,
    *,
    waiver_text: str | None,
    asked_proof: AskedProof,
    rerun: GateRerun = live_rerun,
) -> tuple[Refusal | None, WaiverAdmission | None]:
    """(refusal, admitted waiver) for the ci:quick receipt of `tree`. With no waiver, or a green receipt, the push guard's verdict alone; a red receipt is admitted only through the waiver's rules (module docstring)."""
    guard = _push_guard()
    receipt = guard.read_receipt(str(root), tree)
    why = guard.receipt_refusal(str(root), tree, receipt)
    if why is None:
        if waiver_text:
            print(
                "local-gates: ci-quick: %s is set but the receipt is green, so it is not applied"
                % WAIVER_ENV,
                file=sys.stderr,
            )
        return None, None
    today = Refusal("ci-quick", "%s (tree %s) Run `npm run ci:quick` on HEAD." % (why, tree[:12]))
    if not waiver_text:
        return today, None

    def refuse(reason: str) -> tuple[Refusal, None]:
        return (
            Refusal(
                "ci-quick", "%s; %s does not admit it: %s" % (today.message, WAIVER_ENV, reason)
            ),
            None,
        )

    waiver, malformed = parse_red_waiver(waiver_text)
    if waiver is None:
        return refuse(malformed)
    # The receipt itself must be sound for this tree: a missing, corrupt, misfiled, narrowed or otherwise refused receipt is never waived, only its reds are.
    if not isinstance(receipt, dict) or guard.UNPARSEABLE in receipt or guard.MISFILED in receipt:
        return today, None
    # THE TREE THE REDS WERE JUDGED AT (operator ruling 2026-11-16, plans as records). The receipt names HEAD's tree exactly, or it reaches HEAD through an advance chain the push guard verifies step by step (`advance_chain` recomputes each diff and requires every reader of the touched records in the step). `failed` still describes the receipt's own tree, so a waived red is a statement about HEAD only when no step on the chain touched a record that gate reads: a step lists every reader of what it touched, so a waived gate listed in one is refused.
    judged = receipt.get("headTree")
    steps: list[dict[str, Any]] = []
    if judged != tree:
        chain = None
        if isinstance(judged, str) and judged:
            chain, _why = guard.advance_chain(str(root), receipt, judged, tree)
        if chain is None:
            return refuse(
                "the receipt judged tree %r, not HEAD's %s, and no verified advance chain carries it there"
                % (judged, tree)
            )
        edges = set(itertools.pairwise(chain))
        steps = [
            s
            for s in receipt.get("advances") or []
            if isinstance(s, dict) and (s.get("from"), s.get("to")) in edges
        ]
    front, _chain = guard._receipt_front(str(root), tree, receipt)
    if front is not None:
        return today, None
    listed: set[str] = set()
    for s in steps:
        step_gates = s.get("gates")
        if isinstance(step_gates, dict):
            listed.update(g for g in step_gates if isinstance(g, str))
    reread = sorted(listed & set(waiver.gates))
    if reread:
        return refuse(
            "the receipt reached HEAD through a record-only advance that touched what %s read(s), so the red it judged at tree %s is not a verdict on HEAD; re-run `npm run ci:quick` at HEAD"
            % (", ".join(reread), str(judged)[:12])
        )
    if not asked_proof(waiver.asked):
        return refuse(
            "%s matches no AskUserQuestion answer in the transcript ($%s)"
            % (waiver.asked, TRANSCRIPT_ENV)
        )
    listed_failed = receipt.get("failed") or []
    if not isinstance(listed_failed, list):
        return refuse("the receipt's failed field is not a list")
    odd = [g for g in listed_failed if not isinstance(g, str)]
    if odd:
        return refuse(
            "the receipt's failed list holds non-string entries (%s), which no gate name can answer"
            % ", ".join(repr(g) for g in odd)
        )
    failed = list(listed_failed)
    carried, _schema = guard.parse_carried(guard._carried_at_head(str(root)))
    carried_gates = set(carried or {})
    evidence: dict[str, str] = {}
    refusals: list[str] = []
    for gate in waiver.gates:
        if gate not in failed or gate in carried_gates:
            continue
        ok, said = _waivable(root, gate, rerun)
        if ok:
            evidence[gate] = said
        else:
            refusals.append(said)
    if refusals:
        return refuse("; ".join(refusals))
    # What is left is judged by the push guard's own carried-reds verdict, so an unnamed red, or a carried entry gone stale, still refuses.
    rest = dict(receipt)
    rest["failed"] = [g for g in failed if g not in evidence]
    findings = receipt.get("findings")
    if isinstance(findings, dict):
        rest["findings"] = {g: v for g, v in findings.items() if g not in evidence}
    left, _notes = guard.carried_verdict(rest, guard._carried_at_head(str(root)))
    if left is not None:
        return refuse(left)
    if not evidence:
        return refuse("it names none of the red gates (%s)" % ", ".join(failed))
    warnings = tuple(
        "%s is named in %s but is not red in the receipt" % (g, WAIVER_ENV)
        for g in waiver.gates
        if g not in failed
    )
    covered = tuple(g for g in waiver.gates if g in evidence)
    return None, WaiverAdmission(covered, waiver.asked, waiver.reason, tree, evidence, warnings)


# --------------------------------------------------------------------------- (b) vm:check


def vm_check_refusal(root: pathlib.Path, tree: str, base: str, tip: str = "HEAD") -> Refusal | None:
    changed = surfaces.changed_paths(root, base, "push", tip)
    if not changed.touched:
        return None
    verdict = vm_tier.admit(root, tree, surfaces.inputs(root, tree), changed.sides)
    if verdict.ok:
        return None
    shown = [*changed.hits[:5], *("(unknown) %s" % u for u in changed.unknown)]
    more = " and %d more" % (len(changed.hits) - 5) if len(changed.hits) > 5 else ""
    return Refusal(
        "vm-check",
        "[%s] %s; %s touched since %s (%s%s). Run `npm run vm:check -- --changed --base %s`."
        % (
            verdict.code,
            verdict.message,
            "+".join(sorted(changed.sides)) or "no side",
            base,
            ", ".join(shown),
            more,
            base,
        ),
    )


# --------------------------------------------------------------------------- (c) backup


def backup_refusal(root: pathlib.Path, base: str, tip: str = "HEAD") -> Refusal | None:
    code, message = backup_check_trigger.check(root, tip, base)
    if code == 0:
        return None
    return Refusal("backup", message if code == 1 else "UNCHECKED: %s" % message)


# --------------------------------------------------------------------------- (d) the release clone


def _submodules(clone: pathlib.Path) -> list[tuple[str, str]]:
    """(name, path) of every submodule `.gitmodules` at the clone's HEAD declares."""
    rc, out, _err = _git(
        clone, "config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"
    )
    if rc != 0:
        return []
    found = []
    for line in out.splitlines():
        key, _, path = line.partition(" ")
        found.append((key[len("submodule.") : -len(".path")], path.strip()))
    return found


def _local_source(root: pathlib.Path, name: str, path: str) -> pathlib.Path | None:
    """This checkout's own copy of submodule `name`: its worktree when checked out, else its git dir, else None."""
    worktree = root / path
    if (worktree / ".git").exists():
        return worktree
    gitdir = root / ".git" / "modules" / name
    return gitdir if gitdir.is_dir() else None


def clone_refusal(root: pathlib.Path, tree: str, head: str) -> Refusal | None:
    """Clone `head` with its submodules afresh at `<root>/.ci/cache/release/<tree>/` and judge it. The clone is left in place: it is the release clone the builds run in."""
    dest = root / CLONE_REL / tree
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    def fail(why: str) -> Refusal:
        return Refusal("clone", "the release clone %s %s" % (paths_rel(root, dest), why))

    rc, _out, err = _git(root, "clone", "--quiet", "--no-checkout", str(root), str(dest))
    if rc != 0:
        return fail("could not be made: %s" % err)
    rc, _out, err = _git(dest, "checkout", "--quiet", "--detach", head)
    if rc != 0:
        return fail("could not check out %s: %s" % (head[:12], err))
    if _rev(dest, "HEAD^{tree}") != tree:
        return fail("does not name tree %s" % tree[:12])
    for name, path in _submodules(dest):
        source = _local_source(root, name, path)
        if source is None:
            return fail("has no local copy of the submodule %s to clone from" % path)
        _git(dest, "config", "submodule.%s.url" % name, str(source))
    rc, _out, err = _git(dest, "-c", "protocol.file.allow=always", "submodule", "update", "--init")
    if rc != 0:
        return fail("could not put every submodule at its pointer: %s" % err)
    rc, out, err = _git(dest, "submodule", "status")
    if rc != 0:
        return fail("could not list its submodules: %s" % err)
    for line in out.splitlines():
        if line[:1] in ("+", "-", "U"):
            return fail("has a submodule out of place: %s" % line.strip())
    for _name, path in _submodules(dest):
        pointer = _rev(dest, "HEAD:%s" % path)
        if pointer is None:
            return fail("declares the submodule %s in .gitmodules with no gitlink at HEAD" % path)
        if _rev(dest / path, "HEAD") != pointer:
            return fail("has %s away from its pointer %s" % (path, pointer[:12]))
    rc, out, err = _git(dest, "status", "--porcelain", "--ignore-submodules=none")
    if rc != 0:
        return fail("could not report its status: %s" % err)
    if out:
        return fail("is not clean: %s" % ", ".join(out.splitlines()[:5]))
    return None


def paths_rel(root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------- (e) origin/main


def live_fetch(root: pathlib.Path) -> tuple[str | None, str]:
    """(origin/main after a fresh fetch, "") or (None, why the fetch failed)."""
    rc, _out, err = _git(
        root,
        "fetch",
        "--quiet",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        timeout=FETCH_TIMEOUT_S,
    )
    if rc != 0:
        return None, err or "git fetch exited %d" % rc
    sha = _rev(root, "refs/remotes/origin/main")
    return (sha, "") if sha else (None, "refs/remotes/origin/main does not resolve after the fetch")


def origin_main_refusal(root: pathlib.Path, head: str, fetch: Fetch) -> Refusal | None:
    origin_main, why = fetch(root)
    if origin_main is None:
        return Refusal(
            "origin-main", "the fetch of origin main failed, so nothing is judged: %s" % why
        )
    if origin_main != head:
        return Refusal(
            "origin-main",
            "HEAD %s is not origin/main %s; a release is cut from the merged main only"
            % (head[:12], origin_main[:12]),
        )
    return None


def live_heads(root: pathlib.Path) -> tuple[dict[str, str] | None, str]:
    """({branch: tip sha} on origin, "") read with `git ls-remote`, which writes no ref, or (None, why the read failed)."""
    rc, out, err = _git(root, "ls-remote", "origin", "refs/heads/*", timeout=FETCH_TIMEOUT_S)
    if rc != 0:
        return None, err or "git ls-remote origin exited %d" % rc
    heads: dict[str, str] = {}
    for line in out.splitlines():
        sha, _sep, ref = line.partition("\t")
        if ref.startswith("refs/heads/"):
            heads[ref[len("refs/heads/") :]] = sha.strip()
    return heads, ""


def pushed_branch(heads: dict[str, str], head: str) -> str | None:
    """The origin branch whose tip is `head`: a branch other than main first, since a branch release names the branch it ships, else main, else None."""
    names = sorted(name for name, sha in heads.items() if sha == head)
    return next((n for n in names if n != "main"), names[0] if names else None)


def live_ancestor(root: pathlib.Path, ancestor: str, head: str) -> bool | None:
    """`git merge-base --is-ancestor`: True on exit 0, False on 1, None (cannot tell) on anything else, an object this checkout lacks included."""
    rc, _out, _err = _git(root, "merge-base", "--is-ancestor", ancestor, head)
    return {0: True, 1: False}.get(rc)


def branch_release_refusals(
    root: pathlib.Path,
    head: str,
    fetch: Fetch,
    heads: Heads = live_heads,
    ancestor: Ancestor = live_ancestor,
) -> list[Refusal]:
    """The origin-main gate of a branch release: HEAD is a pushed branch tip and descends from a freshly fetched origin/main."""
    origin_main, why = fetch(root)
    if origin_main is None:
        return [
            Refusal(
                "origin-main", "the fetch of origin main failed, so nothing is judged: %s" % why
            )
        ]
    found: list[Refusal] = []
    remote, why = heads(root)
    if remote is None:
        found.append(
            Refusal(
                "origin-main",
                "the read of origin's branches failed, so whether HEAD is pushed is not judged: %s"
                % why,
            )
        )
    elif pushed_branch(remote, head) is None:
        found.append(
            Refusal(
                "origin-main",
                "HEAD %s is the tip of no branch on origin; a branch release ships a pushed head only"
                % head[:12],
            )
        )
    verdict = ancestor(root, origin_main, head)
    if verdict is None:
        found.append(
            Refusal(
                "origin-main",
                "git cannot tell whether origin/main %s is an ancestor of HEAD %s"
                % (origin_main[:12], head[:12]),
            )
        )
    elif not verdict:
        found.append(
            Refusal(
                "origin-main",
                "origin/main %s is not an ancestor of HEAD %s; a branch release ships a head descended from the merged main only"
                % (origin_main[:12], head[:12]),
            )
        )
    return found


# --------------------------------------------------------------------------- (f) the release lock


def live_next_version(root: pathlib.Path) -> str | None:
    """`resolve_version --bump-type patch`, run in `root`."""
    env = dict(os.environ, PYTHONPATH=str(paths.ci_dir()))
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.version.resolve_version", "--bump-type", "patch"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    version = proc.stdout.strip()
    return version if proc.returncode == 0 and version else None


def _github_repository(root: pathlib.Path) -> str:
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    _rc, url, _err = _git(root, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else ""


def live_existing(root: pathlib.Path, version: str) -> tuple[bool, str]:
    """(free, what check_existing_release said): its exit 0 is free, anything else is not."""
    repo = _github_repository(root)
    if not repo:
        return False, "the GitHub repository of origin could not be named"
    env = dict(os.environ, VERSION=version, GITHUB_REPOSITORY=repo, PYTHONPATH=str(paths.ci_dir()))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "rediacc_ci.release.check_existing_release"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=FETCH_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return False, "check_existing_release did not answer within %ds" % FETCH_TIMEOUT_S
    # Its `git fetch --tags --quiet` exits non-zero with nothing printed when a fetched tag would clobber a local one, so an empty answer is named as such rather than shown as a bare code.
    said = (proc.stdout + proc.stderr).strip() or "exit %d with no output" % proc.returncode
    return proc.returncode == 0, said


def lock_refusals(
    root: pathlib.Path, version: str | None, sentinel: SentinelProbe, existing: ExistingProbe
) -> list[Refusal]:
    if not version:
        return [Refusal("lock", "the version about to be cut could not be resolved")]
    found: list[Refusal] = []
    sealed = sentinel(version)
    if sealed is None:
        found.append(
            Refusal(
                "lock",
                "the R2 sentinel cli/v%s/.released could not be read (UNKNOWN), so the lock is not known free"
                % version,
            )
        )
    elif sealed:
        found.append(
            Refusal(
                "lock",
                "the R2 sentinel cli/v%s/.released exists: v%s is taken" % (version, version),
            )
        )
    free, said = existing(root, version)
    if not free:
        found.append(Refusal("lock", "check_existing_release refused v%s: %s" % (version, said)))
    return found


# --------------------------------------------------------------------------- stable


def live_record(key: str) -> tuple[dict[str, Any] | None, str]:
    """(record, "") or (None, "absent") or (None, why it could not be read)."""
    try:
        record = deploy_record.read_json_object(key)
    except deploy_record.RecordError as exc:
        return None, "could not be read: %s" % exc
    return (record, "") if record is not None else (None, "absent")


def transcript_proof(transcript: str | None) -> AskedProof:
    """A predicate proving an `ASKED:` minute against the AskUserQuestion answers of `transcript`; with no transcript nothing is proven."""

    def prove(asked: str) -> bool:
        if not transcript:
            return False
        paths.on_sys_path(paths.hooks_stop_dir())
        try:
            wl_checks = importlib.import_module("wl_checks")
        except ImportError:
            return False
        return bool(wl_checks._asked_in_transcript(asked, transcript))

    return prove


def _iso_epoch(value: str) -> int | None:
    """A record's `recorded_at` (`deploy_record.now()`'s `%Y-%m-%dT%H:%M:%SZ`) as epoch seconds, or None."""
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        return None
    try:
        return int(datetime.datetime.fromisoformat(value).timestamp())
    except ValueError:
        return None


def stable_refusals(
    *,
    version: str | None,
    tag_commit: TagCommit,
    sentinel: SentinelProbe,
    record: RecordReader,
    force_asked: str | None,
    asked_proof: AskedProof,
    now_epoch: int,
) -> list[Refusal]:
    if not version:
        return [Refusal("stable", "the edge version to promote could not be read")]
    found: list[Refusal] = []
    if tag_commit("v%s" % version) is None:
        found.append(Refusal("stable", "the tag v%s does not exist" % version))
    sealed = sentinel(version)
    if sealed is None:
        found.append(
            Refusal(
                "stable", "the R2 sentinel cli/v%s/.released could not be read (UNKNOWN)" % version
            )
        )
    elif not sealed:
        found.append(
            Refusal(
                "stable", "v%s is not sealed: no R2 sentinel cli/v%s/.released" % (version, version)
            )
        )
    key = EDGE_RECORD_KEY % version
    doc, why = record(key)
    if doc is None:
        found.append(Refusal("stable", "the edge record %s is %s" % (key, why)))
        return found
    smoke = doc.get("smoke_rc")
    if smoke != 0 or isinstance(smoke, bool):
        found.append(Refusal("stable", "the edge record %s has smoke_rc %r, not 0" % (key, smoke)))
    forced = False
    if force_asked is not None:
        if not ASKED_RE.fullmatch(force_asked):
            found.append(
                Refusal("stable", "--force-asked %r is not ASKED:<YYYY-MM-DDTHH:MM>Z" % force_asked)
            )
        elif not asked_proof(force_asked):
            found.append(
                Refusal(
                    "stable",
                    "--force-asked %s matches no AskUserQuestion answer in the transcript, so the soak is not skipped"
                    % force_asked,
                )
            )
        else:
            forced = True
    try:
        verdict = check_soak_period.select(
            edge_version=version,
            edge_date=str(doc.get("recorded_at", "")),
            soak_days=SOAK_DAYS,
            now_epoch=now_epoch,
            force=forced,
            epoch=_iso_epoch,
        )
    except check_soak_period.SelectError as exc:
        found.append(Refusal("stable", "the edge record %s: %s" % (key, exc)))
        return found
    if not verdict.ready:
        found.append(
            Refusal("stable", "v%s has not soaked: %s" % (version, "; ".join(verdict.lines)))
        )
    return found


# --------------------------------------------------------------------------- the entry


def check(
    root: pathlib.Path,
    channel: str,
    *,
    fetch: Fetch = live_fetch,
    sentinel: SentinelProbe = order.live_sentinel_exists,
    existing: ExistingProbe = live_existing,
    next_version: NextVersion = live_next_version,
    version: str | None = None,
    edge_version: EdgeVersion | None = None,
    tag_commit: TagCommit | None = None,
    record: RecordReader = live_record,
    force_asked: str | None = None,
    asked_proof: AskedProof | None = None,
    now_epoch: int | None = None,
    clone: Callable[[pathlib.Path, str, str], Refusal | None] = clone_refusal,
    branch_release: bool = False,
    heads: Heads = live_heads,
    ancestor: Ancestor = live_ancestor,
    waiver_text: str | None = None,
    rerun: GateRerun = live_rerun,
    admitted: list[WaiverAdmission] | None = None,
    commit: str | None = None,
) -> list[Refusal]:
    """Every refusal of releasing `root`'s HEAD to `channel`, or of the ancestor `commit` names (D1.8: its tree, receipts, tag range, clone and origin gates; it must be an ancestor of HEAD); empty admits. `branch_release` swaps the origin-main equality for the pushed-descendant rule (edge only). `waiver_text` defaults to $RELEASE_RED_WAIVER; a waiver that admits a red receipt is appended to `admitted`, or printed to stderr when no collector is given, so it is never applied unseen."""
    if channel not in CHANNELS:
        return [Refusal("usage", "--channel %r is not one of %s" % (channel, ", ".join(CHANNELS)))]
    if branch_release and channel != "edge":
        return [Refusal("usage", "--branch-release applies to --channel edge only")]
    pinned = commit is not None
    head = _rev(root, "%s^{commit}" % commit) if pinned else _rev(root, "HEAD")
    tree = _rev(root, "%s^{tree}" % head) if head else None
    if head is None or tree is None:
        return [
            Refusal(
                "git",
                "git cannot name %s or its tree in %s"
                % ("--commit %s" % commit if pinned else "HEAD", root),
            )
        ]
    found: list[Refusal] = []
    if pinned:
        tip = _rev(root, "HEAD")
        verdict = ancestor(root, head, tip) if tip else None
        if verdict is not True:
            return [
                Refusal(
                    "commit",
                    "--commit %s is %s"
                    % (
                        head[:12],
                        "not an ancestor of the branch tip %s" % tip[:12]
                        if verdict is False
                        else "an ancestor git cannot confirm against the branch tip",
                    ),
                )
            ]
    proof = asked_proof or transcript_proof(os.environ.get(TRANSCRIPT_ENV))
    quick, waived = ci_quick_verdict(
        root,
        tree,
        waiver_text=os.environ.get(WAIVER_ENV) if waiver_text is None else waiver_text,
        asked_proof=proof,
        rerun=rerun,
    )
    if quick:
        found.append(quick)
    if waived:
        if admitted is None:
            print(waived.line(), file=sys.stderr)
        else:
            admitted.append(waived)
        for warning in waived.warnings:
            print("local-gates: ci-quick: warning: %s" % warning, file=sys.stderr)
    base = previous_tag(root, head)
    if base is None:
        found.append(
            Refusal(
                "vm-check",
                "no v* tag is reachable from %s, so the range since the previous release is unknown"
                % (head[:12] if pinned else "HEAD"),
            )
        )
    else:
        found.extend(
            r
            for r in (vm_check_refusal(root, tree, base, head), backup_refusal(root, base, head))
            if r
        )
    cloned = clone(root, tree, head)
    if cloned:
        found.append(cloned)
    if branch_release:
        found.extend(branch_release_refusals(root, head, fetch, heads, ancestor))
    else:
        main_refusal = origin_main_refusal(root, head, fetch)
        if main_refusal:
            found.append(main_refusal)
    if channel == "edge":
        found.extend(lock_refusals(root, version or next_version(root), sentinel, existing))
    else:
        found.extend(
            stable_refusals(
                version=version or (edge_version or _live_edge_version)(),
                tag_commit=tag_commit or functools.partial(_tag_commit, root),
                sentinel=sentinel,
                record=record,
                force_asked=force_asked,
                asked_proof=proof,
                now_epoch=int(time.time()) if now_epoch is None else now_epoch,
            )
        )
    return found


def _live_edge_version() -> str | None:
    return order.live_manifest_version("edge")


def _tag_commit(root: pathlib.Path, tag: str) -> str | None:
    return order.live_tag_commit(tag, root)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m " + SELF, description=__doc__.split("\n", 1)[0]
    )
    parser.add_argument("--channel", required=True, choices=CHANNELS)
    parser.add_argument(
        "--version",
        help="the version to judge (edge: the one about to be cut; stable: the edge one promoted)",
    )
    parser.add_argument(
        "--branch-release",
        action="store_true",
        help="edge: HEAD is a pushed branch tip descended from origin/main, not origin/main itself",
    )
    parser.add_argument(
        "--commit",
        help="judge this ancestor of the branch tip instead of HEAD: its tree, receipts, tag range and release clone",
    )
    parser.add_argument(
        "--force-asked", help="stable: skip the soak age, with a proven ASKED:<YYYY-MM-DDTHH:MM>Z"
    )
    parser.add_argument(
        "--transcript",
        help="the transcript the --force-asked minute is proven against (default $%s)"
        % TRANSCRIPT_ENV,
    )
    args = parser.parse_args(argv)
    if args.force_asked is not None and args.channel != "stable":
        parser.error("--force-asked applies to --channel stable only")
    if args.branch_release and args.channel != "edge":
        parser.error("--branch-release applies to --channel edge only")
    transcript = args.transcript or os.environ.get(TRANSCRIPT_ENV)
    admitted: list[WaiverAdmission] = []
    refusals = check(
        paths.repo_root(),
        args.channel,
        version=args.version,
        force_asked=args.force_asked,
        asked_proof=transcript_proof(transcript),
        branch_release=args.branch_release,
        admitted=admitted,
        commit=args.commit,
    )
    # Printed even beside refusals: a waiver that admitted the receipt is a fact of this run whatever else refuses.
    for waived in admitted:
        print(waived.line())
    if refusals:
        for refusal in refusals:
            print(refusal.line())
        return 1
    print("local-gates: admitted: HEAD may be released to %s" % args.channel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
