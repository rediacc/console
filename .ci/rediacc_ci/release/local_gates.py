"""The gates a local release must pass before it builds or publishes anything (box W2-A of agent/plans/PLAN-local-release.md).

    PYTHONPATH=.ci python3 -m rediacc_ci.release.local_gates --channel edge|stable [--version V] [--force-asked ASKED:<YYYY-MM-DDTHH:MM>Z]

Exit 0 when every gate admits, 1 with one `local-gates: <code>: <why>` line per refusal otherwise, 2 on a usage error. Every gate runs, so one run names every refusal rather than the first.

THE GATES, each a refusal unless it holds:
  ci-quick     a whole, green ci:quick receipt judged `HEAD^{tree}`: the push guard's own `read_receipt` (the per-tree copy `.ci/cache/receipts/<tree>.json` first, then the latest file) and `receipt_refusal`, imported the way `rediacc_ci.ci.gate_model` imports that guard, never copied.
  vm-check     the vm:check trigger paths changed since the previous release tag (the highest-versioned `v*` tag reachable from HEAD, `git tag --merged HEAD --sort=-v:refname`) are admitted by a VERIFIED receipt, through `vm_check_trigger.changed_paths(root, <tag>, "push")` and `vm_check_receipt.admit`. No hit is "not required", and admits.
  backup       when the backup paths moved since that tag, a VERIFIED backup receipt covers the tree: `backup_check_trigger.check(root, "HEAD", base=<tag>)`, the reader the backup push guard and the git-level pre-push hook run. Exit 1 and 2 (cannot judge) both refuse (decision 4).
  clone        a fresh clone of HEAD with its submodules at `.ci/cache/release/<tree>/` is clean, names the tree, and every submodule sits at its gitlink, unmodified (decision 1). The shared checkout always carries other sessions' ledgers, so cleanliness is judged on the clone, which is also where the release builds. Each submodule is cloned from this checkout's own copy of it (`<root>/<path>`, else `<root>/.git/modules/<name>`), never from the network; a pointer commit the local copy lacks is a refusal. HEAD equal to origin/main (below) is what makes those pointers the merged ones.
  origin-main  a fresh `git fetch origin main` succeeded, and HEAD equals origin/main. A failed fetch refuses: a stale origin/main would pass vacuously.
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
from rediacc_ci.drills import backup_check_trigger, vm_check_receipt, vm_check_trigger
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
ASKED_RE = re.compile(r"^ASKED:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")

# The seams. Each answers the question its gate asks of the world, None meaning "could not tell".
Fetch = Callable[[pathlib.Path], "tuple[str | None, str]"]
SentinelProbe = Callable[[str], "bool | None"]
ExistingProbe = Callable[[pathlib.Path, str], "tuple[bool, str]"]
NextVersion = Callable[[pathlib.Path], "str | None"]
EdgeVersion = Callable[[], "str | None"]
TagCommit = Callable[[str], "str | None"]
RecordReader = Callable[[str], "tuple[dict[str, Any] | None, str]"]
AskedProof = Callable[[str], bool]


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


def previous_tag(root: pathlib.Path) -> str | None:
    """The highest-versioned `v*` tag reachable from HEAD, or None when there is none.

    `git tag --merged HEAD --sort=-v:refname`, the version order `resolve_version` reads, and not `git describe`: describe answers the tag nearest by commit distance, so a lower tag on a merged side branch would start the range after the real previous release.
    """
    rc, out, _err = _git(root, "tag", "--merged", "HEAD", "--list", "v*", "--sort=-v:refname")
    first = out.splitlines()[0].strip() if rc == 0 and out else ""
    return first or None


# --------------------------------------------------------------------------- (a) ci:quick


@functools.cache
def _push_guard() -> Any:
    """The push guard `block_unverified_push`, imported once per process from this checkout's `.claude`."""
    paths.on_sys_path(paths.repo_root() / ".claude")
    return importlib.import_module("rediacc_hooks.guards.block_unverified_push")


def ci_quick_refusal(root: pathlib.Path, tree: str) -> Refusal | None:
    guard = _push_guard()
    why = guard.receipt_refusal(str(root), tree, guard.read_receipt(str(root), tree))
    if why is None:
        return None
    return Refusal("ci-quick", "%s (tree %s) Run `npm run ci:quick` on HEAD." % (why, tree[:12]))


# --------------------------------------------------------------------------- (b) vm:check


def vm_check_refusal(root: pathlib.Path, tree: str, base: str) -> Refusal | None:
    changed = vm_check_trigger.changed_paths(root, base, "push", "HEAD")
    if not changed.touched:
        return None
    verdict = vm_check_receipt.admit(root, tree, vm_check_trigger.inputs(root, tree), changed.sides)
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


def backup_refusal(root: pathlib.Path, base: str) -> Refusal | None:
    code, message = backup_check_trigger.check(root, "HEAD", base)
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
        if not ASKED_RE.match(force_asked):
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
) -> list[Refusal]:
    """Every refusal of releasing `root`'s HEAD to `channel`; empty admits."""
    if channel not in CHANNELS:
        return [Refusal("usage", "--channel %r is not one of %s" % (channel, ", ".join(CHANNELS)))]
    head = _rev(root, "HEAD")
    tree = _rev(root, "HEAD^{tree}")
    if head is None or tree is None:
        return [Refusal("git", "git cannot name HEAD or its tree in %s" % root)]
    found: list[Refusal] = []
    quick = ci_quick_refusal(root, tree)
    if quick:
        found.append(quick)
    base = previous_tag(root)
    if base is None:
        found.append(
            Refusal(
                "vm-check",
                "no v* tag is reachable from HEAD, so the range since the previous release is unknown",
            )
        )
    else:
        found.extend(
            r for r in (vm_check_refusal(root, tree, base), backup_refusal(root, base)) if r
        )
    found.extend(r for r in (clone(root, tree, head), origin_main_refusal(root, head, fetch)) if r)
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
                asked_proof=asked_proof or transcript_proof(os.environ.get(TRANSCRIPT_ENV)),
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
    transcript = args.transcript or os.environ.get(TRANSCRIPT_ENV)
    refusals = check(
        paths.repo_root(),
        args.channel,
        version=args.version,
        force_asked=args.force_asked,
        asked_proof=transcript_proof(transcript),
    )
    if refusals:
        for refusal in refusals:
            print(refusal.line())
        return 1
    print("local-gates: admitted: HEAD may be released to %s" % args.channel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
