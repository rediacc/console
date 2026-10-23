#!/usr/bin/env python3
"""Move the openSUSE Leap 16.0 Ceph pin to each new OBS build once ci-obs-mirror has captured it (PLAN-plan-per-pr-loop R1, operator /ask 2026-10-23 "Scheduled auto-bump").

OBS `filesystems:ceph:squid/16.0` keeps only its latest build and rebuilds every few days (2.98, 2.100, 2.103, 2.105 in October 2026). ci-obs-mirror captures every build within six hours, but the pin in private/renet still had to be moved by hand, and until it was the nightly's `OBS upstream serves the pin` step stayed red. This module is the two jobs of `.github/workflows/obs-ceph-autobump.yml`:

  plan  (read-only job, default-branch checkout with private/renet) run `npm run pins -- bump os:opensuse-16.0-ceph`, the one write path for a pin. The bump itself refuses a moved Ceph series (`major: refuse`), refuses an EVR with no obs-mirror tag, and runs the entry's gate (`check:ci-ceph-image-pin`). This subcommand then proves the result: the pin now reads the new EVR, and nothing in private/renet moved outside the registry's site files. Writes `action=bump|none`, `old`, `new`.
  land  (write job, no npm, no code from any branch but the default one) put that same old -> new change on the live branch: the head of the one open console PR whose head is an `MMDD-N` branch, the branch rule of CLAUDE.md "One branch, one PR". In private/renet it commits on the same-named branch (cut from the console branch's gitlink when renet has none), in the console it moves the private/renet gitlink, and it pushes both without force.

WHY THE LIVE BRANCH AND NOT A PR. Each repository holds at most one live `MMDD-N` branch and at most one open PR. A bot PR would be a second one; a commit on the live branch rides the PR that is already there, through its CI and its per-commit review. No open PR means there is nothing to ride: `land` exits 1 naming the command a session runs, so the run is red in `ci-trace.py --scheduled` instead of quietly doing nothing.

WHY TWO JOBS. `plan` runs `npm ci` and the console's TypeScript, so it holds only `contents: read` and the read-only checkout token. `land` holds the write token and runs nothing but this file from the default branch: it edits the site lines itself with the registry's own `match` regexes (from the default branch's pins.json, never the live branch's), so no code from the branch it writes to executes under that token.

WHAT `land` REFUSES (exit 1, nothing pushed):

  * no open console PR with an `MMDD-N` head, or more than one;
  * a branch name that is not `MMDD-N` (the App token bypasses the main-branch ruleset, so the name is checked again before every push);
  * an EVR that is not a Leap EVR (obs_mirror.EVR_RE);
  * a site whose match count differs from its `expect`, or whose value is neither the old nor the new EVR (someone moved the pin by hand: the branch's owner decides);
  * a branch snapshot (agent/pr/<branch>.md) that does not name exactly one `PR-TASK:` epic, since check:ci-pr-task-trailers refuses an untagged commit, and that is the rule `pins bump` uses for its drafts;
  * a rejected push (the branch moved under it): the next run retries from the new tip.

Already moved is not a refusal: every site on the new EVR and a gitlink whose commit carries it is `action=none`.

Outputs go to $GITHUB_OUTPUT when it is set and to stdout as KEY=value lines otherwise.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci.infra.obs_mirror import EVR_RE, read_pin

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    RunFn = Callable[[list[str], str | None], subprocess.CompletedProcess[str]]

ROOT = pathlib.Path(__file__).resolve().parents[3]
PINS_REL = ".ci/config/pins.json"
ENTRY_ID = "os:opensuse-16.0-ceph"
OWNER = "rediacc"
CONSOLE = "console"
RENET = "renet"
RENET_PATH = "private/renet"
PIN_REL = ".ceph-image-pin"
# CLAUDE.md "One branch, one PR": the one live branch of a repository is `MMDD-N`.
LIVE_BRANCH_RE = re.compile(r"^[0-9]{4}-[0-9]+$")
TASK_RE = re.compile(r"^`?PR-TASK:\s*([0-9a-f]{6,32})`?\s*$", re.MULTILINE)
BUMP_RE = re.compile(r"^%s: (\S+) -> (\S+)$" % re.escape(ENTRY_ID), re.MULTILINE)
CURRENT_RE = re.compile(r"^REFUSED %s: current\b" % re.escape(ENTRY_ID), re.MULTILINE)
# Not one of rediacc_ci.ci.initialize.BOT_AUTHORS: those skip a push run's downstream jobs, and this commit is tested like any other.
GIT_NAME = "rediacc obs-ceph-autobump"
GIT_EMAIL = "obs-ceph-autobump@users.noreply.github.com"


class AutobumpError(RuntimeError):
    """A refusal the workflow must show as red; nothing was pushed past it."""


def _run(argv: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


def _ok(run: RunFn, argv: list[str], cwd: str | None = None) -> str:
    """stdout of a command that must succeed; its own output is the error otherwise."""
    res = run(argv, cwd)
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or "").strip()[-400:]
        raise AutobumpError("`%s` exited %d: %s" % (" ".join(argv), res.returncode, tail))
    return res.stdout or ""


def _evr(value: str) -> str:
    if not EVR_RE.match(value):
        raise AutobumpError("not a Leap EVR: %r" % value)
    return value


def _branch(value: str) -> str:
    if not LIVE_BRANCH_RE.match(value):
        raise AutobumpError("refusing to write to %r: only an MMDD-N live branch" % value)
    return value


# --- the registry's sites -------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Site:
    repo: str
    file: str
    match: re.Pattern[str]
    expect: int


def sites(pins_json: str, entry_id: str = ENTRY_ID) -> list[Site]:
    """The entry's sites with their `match` regexes; a JS `(?<name>` group is Python's `(?P<name>`."""
    for entry in json.loads(pins_json).get("entries", []):
        if entry.get("id") != entry_id:
            continue
        out = []
        for raw in entry.get("sites", []):
            pattern = re.sub(r"\(\?<(?=[A-Za-z_])", "(?P<", raw["match"])
            out.append(
                Site(
                    raw["repo"], raw["file"], re.compile(pattern, re.MULTILINE), int(raw["expect"])
                )
            )
        if not out:
            raise AutobumpError("%s has no sites in pins.json" % entry_id)
        return out
    raise AutobumpError("no %s entry in pins.json" % entry_id)


def rewrite(text: str, site: Site, old: str, new: str) -> tuple[str, bool]:
    """(text with every site value moved old -> new, changed). Already on `new` is (text, False)."""
    found = list(site.match.finditer(text))
    if len(found) != site.expect:
        raise AutobumpError(
            "%s: %d match(es) of the site pattern, the registry expects %d"
            % (site.file, len(found), site.expect)
        )
    values = {m.group("value") for m in found}
    if values == {new}:
        return text, False
    if values != {old}:
        raise AutobumpError(
            "%s holds %s, neither the old pin %s nor the new %s: the pin was moved by hand"
            % (site.file, ", ".join(sorted(values)), old, new)
        )
    out, last = [], 0
    for m in found:
        start, end = m.span("value")
        out.append(text[last:start] + new)
        last = end
    out.append(text[last:])
    return "".join(out), True


# --- plan -------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Plan:
    action: str
    old: str = ""
    new: str = ""


def parse_bump(rc: int, output: str) -> Plan:
    """The verdict of one `pins -- bump` run: moved, already current, or a refusal."""
    m = BUMP_RE.search(output)
    if rc == 0 and m:
        return Plan("bump", _evr(m.group(1)), _evr(m.group(2)))
    if rc != 0 and CURRENT_RE.search(output):
        return Plan("none")
    raise AutobumpError(
        "npm run pins -- bump %s exited %d: %s" % (ENTRY_ID, rc, output.strip()[-600:])
    )


def plan(run: RunFn = _run, root: pathlib.Path = ROOT) -> Plan:
    res = run(["npm", "run", "--silent", "pins", "--", "bump", ENTRY_ID], str(root))
    verdict = parse_bump(res.returncode, (res.stdout or "") + "\n" + (res.stderr or ""))
    if verdict.action == "none":
        return verdict
    renet = root / RENET_PATH
    pin = read_pin((renet / PIN_REL).read_text(encoding="utf-8"))
    if pin != verdict.new:
        raise AutobumpError("the bump reported %s but %s reads %s" % (verdict.new, PIN_REL, pin))
    registry = (root / PINS_REL).read_text(encoding="utf-8")
    allowed = {s.file for s in sites(registry) if s.repo == RENET_PATH}
    moved = set(_ok(run, ["git", "-C", str(renet), "diff", "--name-only"]).split())
    if not moved or not moved <= allowed:
        raise AutobumpError(
            "the bump moved %s in private/renet; only the registry's sites (%s) may move"
            % (", ".join(sorted(moved)) or "nothing", ", ".join(sorted(allowed)))
        )
    return verdict


# --- land -------------------------------------------------------------------------------------


def live_branch(prs_json: str) -> str:
    """The head of the one open same-repository console PR whose head is MMDD-N."""
    heads = [
        p["headRefName"]
        for p in json.loads(prs_json)
        if not p.get("isCrossRepository") and LIVE_BRANCH_RE.match(p.get("headRefName", ""))
    ]
    if not heads:
        raise AutobumpError(
            "no open console PR has an MMDD-N head, so there is no live branch to land on; "
            "a session runs `npm run pins -- bump %s` on its branch" % ENTRY_ID
        )
    if len(heads) > 1:
        raise AutobumpError(
            "more than one open console PR has an MMDD-N head: %s" % ", ".join(heads)
        )
    return heads[0]


def branch_task(snapshot: str | None, branch: str) -> str:
    ids = sorted(set(TASK_RE.findall(snapshot or "")))
    if len(ids) != 1:
        raise AutobumpError(
            "agent/pr/%s.md names %d PR-TASK epic(s) (%s); a commit needs exactly one"
            % (branch, len(ids), ", ".join(ids) or "none")
        )
    return ids[0]


def message(subject: str, old: str, new: str, task: str) -> str:
    run_url = "%s/%s/actions/runs/%s" % (
        os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
        os.environ.get("GITHUB_REPOSITORY", "%s/%s" % (OWNER, CONSOLE)),
        os.environ.get("GITHUB_RUN_ID", "local"),
    )
    return (
        "%s\n\n"
        "OBS filesystems:ceph:squid/16.0 rebuilt: it serves %s, the pin was %s.\n"
        "ci-obs-mirror captured it (obs-mirror-v1-opensuse-16.0-%s), and\n"
        "`npm run pins -- bump %s` ran rc=0 with its gate check:ci-ceph-image-pin\n"
        "in the plan job of %s.\n\n"
        "PR-TASK: %s\n" % (subject, new, old, new, ENTRY_ID, run_url, task)
    )


def _git(run: RunFn, repo: pathlib.Path, *args: str) -> str:
    ident = ["-c", "user.name=" + GIT_NAME, "-c", "user.email=" + GIT_EMAIL]
    return _ok(run, ["git", "-C", str(repo), *ident, *args])


def _push(run: RunFn, repo: pathlib.Path, branch: str) -> None:
    _git(run, repo, "push", "origin", "HEAD:refs/heads/" + _branch(branch))


def _url(repo: str) -> str:
    return "https://github.com/%s/%s.git" % (OWNER, repo)


def land(
    old: str, new: str, *, work: pathlib.Path, pins_json: str, run: RunFn = _run
) -> dict[str, str]:
    old, new = _evr(old), _evr(new)
    every = sites(pins_json)
    renet_sites = [s for s in every if s.repo == RENET_PATH]
    if len(renet_sites) != len(every):
        raise AutobumpError(
            "%s has a site outside private/renet; land moves renet files only" % ENTRY_ID
        )
    prs = _ok(
        run,
        [
            "gh",
            "pr",
            "list",
            "--repo",
            "%s/%s" % (OWNER, CONSOLE),
            "--state",
            "open",
            "--base",
            "main",
            "--json",
            "headRefName,isCrossRepository",
        ],
    )
    branch = _branch(live_branch(prs))
    console = work / CONSOLE
    _ok(
        run, ["git", "clone", "--filter=blob:none", "--branch", branch, _url(CONSOLE), str(console)]
    )
    snap = console / "agent" / "pr" / ("%s.md" % branch)
    task = branch_task(snap.read_text(encoding="utf-8") if snap.is_file() else None, branch)
    gitlink = _git(run, console, "rev-parse", "HEAD:" + RENET_PATH).strip()

    renet = work / RENET
    if _ok(run, ["git", "ls-remote", "--heads", _url(RENET), "refs/heads/" + branch]).strip():
        _ok(
            run, ["git", "clone", "--filter=blob:none", "--branch", branch, _url(RENET), str(renet)]
        )
    else:
        _ok(run, ["git", "clone", "--filter=blob:none", "--no-checkout", _url(RENET), str(renet)])
        _git(run, renet, "fetch", "origin", gitlink)
        _git(run, renet, "checkout", "-b", branch, gitlink)

    changed = []
    for site in renet_sites:
        path = renet / site.file
        text, moved = rewrite(path.read_text(encoding="utf-8"), site, old, new)
        if moved:
            path.write_text(text, encoding="utf-8")
            changed.append(site.file)
    out = {"branch": branch, "renet": "unchanged", "console": "unchanged"}
    if changed:
        msg = work / "renet.msg"
        subject = "chore(cephpkg): move the Leap 16.0 Ceph pin to %s" % new
        msg.write_text(message(subject, old, new, task), encoding="utf-8")
        _git(run, renet, "commit", "-F", str(msg), "--", *changed)
        _push(run, renet, branch)
        out["renet"] = "pushed"
    tip = _git(run, renet, "rev-parse", "HEAD").strip()

    if tip != gitlink:
        # Moved on renet already but maybe not in the console: a gitlink whose own pin is new needs nothing.
        _git(run, renet, "fetch", "origin", gitlink)
        if read_pin(_git(run, renet, "show", "%s:%s" % (gitlink, PIN_REL))) != new:
            _git(run, console, "update-index", "--cacheinfo", "160000,%s,%s" % (tip, RENET_PATH))
            msg = work / "console.msg"
            subject = "chore(renet): point private/renet at the Leap 16.0 Ceph pin %s" % new
            msg.write_text(message(subject, old, new, task), encoding="utf-8")
            _git(run, console, "commit", "-F", str(msg))
            _push(run, console, branch)
            out["console"] = "pushed"
    out["action"] = "bump" if "pushed" in (out["renet"], out["console"]) else "none"
    return out


# --- cli --------------------------------------------------------------------------------------


def _emit(pairs: dict[str, str]) -> None:
    lines = "".join("%s=%s\n" % (k, v) for k, v in pairs.items())
    target = os.environ.get("GITHUB_OUTPUT", "")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(lines)
    else:
        sys.stdout.write(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obs_ceph_autobump", description=(__doc__ or "").split("\n", 1)[0]
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="run the pin bump on this checkout and prove what it moved")
    land_p = sub.add_parser("land", help="put old -> new on the live branch of console and renet")
    land_p.add_argument("--old", required=True)
    land_p.add_argument("--new", required=True)
    land_p.add_argument("--work", type=pathlib.Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.cmd == "plan":
            verdict = plan()
            _emit({"action": verdict.action, "old": verdict.old, "new": verdict.new})
            return 0
        work = args.work or pathlib.Path(
            tempfile.mkdtemp(prefix="obs-ceph-autobump-", dir=os.environ.get("RUNNER_TEMP") or None)
        )
        registry = (ROOT / PINS_REL).read_text(encoding="utf-8")
        _emit(land(args.old, args.new, work=work, pins_json=registry))
        return 0
    except (AutobumpError, OSError, ValueError, KeyError) as exc:
        print("::error::obs_ceph_autobump: %s" % exc, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
