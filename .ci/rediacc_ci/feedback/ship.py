"""Feedback ship: a plan whose boxes are all ticked marks its linked fingerprints fixed in the first release that carries every landing commit (PLAN-rdc-feedback R10, D5: box T3).

    PYTHONPATH=.ci python3 -m rediacc_ci.feedback.ship run [--region eu|us|asia|bench ...] [--dry-run] [--snapshot <path>]

RUN:

  1. Read every plan carrying a `Feedback:` header line, top level and `_done/` (a finished plan moves there); a `Status: moved` stub is a pointer and is skipped.
  2. A plan ships when it has at least one box, every box is ticked, and its ticks record at least one `commit:<sha>`. For each landing commit the first release tag containing it is `git tag --contains <sha> --list 'v*'`, release tags only (`vX.Y.Z`), lowest version first; the plan's version is the highest of those, since the fix is out only once every commit is. A commit in no release tag yet leaves the plan pending; a commit git cannot resolve is an error for that plan.
  3. Per region, export every fingerprint; each linked one not already `fixed` in that version gets `status: fixed, fixedIn: <X.Y.Z>`. The CLI renders it `fixed-in-v<X.Y.Z>`.
  4. Write the verdicts and rewrite the snapshot (`link.write_snapshot`), unless `--dry-run`.

One line per plan names its verdict (shipped in X, pending, open boxes, no commit, error); no report field is printed.

EXIT. 0 done; 1 a failed region or a plan whose commit git cannot resolve; 2 a refusal before any request.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from rediacc_ci import log, paths
from rediacc_ci.feedback import client, link, triage

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

SELF = "rediacc_ci.feedback.ship"
BOX_LINE = re.compile(r"^[-*+][ \t]+\[(.)\][ \t]+\S")
COMMIT = re.compile(r"\bcommit:([0-9a-f]{7,40})\b")
RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
STATUS_LINE = re.compile(r"^Status:[ \t]*(\S+)", re.MULTILINE)


# ---- boxes and commits ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Box:
    state: str
    commits: tuple[str, ...]


def boxes(text: str) -> list[Box]:
    """The column-0 boxes of the plan's `## Boxes` section, each with the `commit:<sha>` tokens of its own block (the box line through the line before the next box or heading)."""
    match = re.search(r"^## Boxes[ \t]*$", text, re.MULTILINE)
    if match is None:
        return []
    out: list[Box] = []
    state: str | None = None
    commits: list[str] = []
    for row in text[match.end() :].split("\n"):
        if row.startswith("#"):
            break
        hit = BOX_LINE.match(row)
        if hit:
            if state is not None:
                out.append(Box(state, tuple(commits)))
            state, commits = hit.group(1), []
        if state is not None:
            commits += [c for c in COMMIT.findall(row) if c not in commits]
    if state is not None:
        out.append(Box(state, tuple(commits)))
    return out


def version_key(tag: str) -> tuple[int, int, int]:
    """The numeric order of a release tag; anything that is not `vX.Y.Z` sorts below every release and is filtered out by `RELEASE_TAG` before it is compared."""
    hit = RELEASE_TAG.match(tag)
    return (int(hit[1]), int(hit[2]), int(hit[3])) if hit else (-1, -1, -1)


class UnknownCommitError(LookupError):
    """git cannot resolve a recorded landing commit."""


def git_first_tag(root: Path, sha: str) -> str | None:
    """The lowest release tag containing `sha`; None when no release tag holds it yet."""
    probe = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", sha + "^{commit}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        raise UnknownCommitError(sha)
    done = subprocess.run(
        ["git", "-C", str(root), "tag", "--contains", sha, "--list", "v*"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise UnknownCommitError(sha)
    tags = [t for t in done.stdout.split() if RELEASE_TAG.match(t)]
    return min(tags, key=version_key) if tags else None


@dataclass
class PlanVerdict:
    rel: str
    ids: tuple[str, ...]
    kind: str  # shipped | pending | open | no-commit | error
    version: str | None = None
    detail: str = ""


def judge(rel: str, text: str, first_tag: Callable[[str], str | None]) -> PlanVerdict | None:
    """The ship verdict of one plan; None when it carries no `Feedback:` line or is a moved stub."""
    held = link.feedback_line(text)
    if held is None or not held.ids:
        return None
    status = STATUS_LINE.search(link.plan_header(text))
    if status and status.group(1).lower() == "moved":
        return None
    found = boxes(text)
    if not found:
        return PlanVerdict(rel, held.ids, "open", detail="no boxes")
    still = [b for b in found if b.state not in ("x", "X")]
    if still:
        return PlanVerdict(
            rel, held.ids, "open", detail="%d of %d box(es) open" % (len(still), len(found))
        )
    shas = list(dict.fromkeys(c for b in found for c in b.commits))
    if not shas:
        return PlanVerdict(rel, held.ids, "no-commit", detail="no tick records a commit:<sha>")
    tags: list[str] = []
    for sha in shas:
        try:
            tag = first_tag(sha)
        except UnknownCommitError:
            return PlanVerdict(rel, held.ids, "error", detail="git cannot resolve commit %s" % sha)
        if tag is None:
            return PlanVerdict(
                rel, held.ids, "pending", detail="commit %s is in no release tag yet" % sha
            )
        tags.append(tag)
    top = max(tags, key=version_key)
    return PlanVerdict(rel, held.ids, "shipped", version=top[1:], detail="%d commit(s)" % len(shas))


def plan_files(root: Path) -> list[Path]:
    base = root.joinpath(*link.PLANS_DIR)
    return sorted([*base.glob(link.PLAN_GLOB), *(base / "_done").glob(link.PLAN_GLOB)])


def ship_verdicts(
    items: Sequence[Mapping[str, Any]], shipped: Sequence[PlanVerdict]
) -> list[dict[str, Any]]:
    """`fixed` verdicts for every exported fingerprint a shipped plan links, unless already fixed in that version. Two plans linking one id: the higher version wins, the fix being out only then."""
    want: dict[str, str] = {}
    for v in shipped:
        if v.version is None:
            continue
        for short in v.ids:
            held = want.get(short)
            if held is None or version_key("v" + v.version) > version_key("v" + held):
                want[short] = v.version
    out = []
    for item in items:
        version = want.get(item["fingerprint"][: link.SHORT_FP])
        if version is None:
            continue
        if item["status"] == "fixed" and item.get("fixedIn") == version:
            continue
        out.append(client.verdict(item["fingerprint"], status="fixed", fixedIn=version))
    return out


# ---- the run -------------------------------------------------------------------------------------


@dataclass
class Options:
    regions: tuple[str, ...]
    dry_run: bool = False
    snapshot: Path | None = None
    root: Path | None = None


@dataclass
class Deps:
    open_region: Callable[..., client.Transport] = client.open_region
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    out: Callable[[str], None] = print
    first_tag: Callable[[Path, str], str | None] = git_first_tag
    plans: Callable[[Path], list[Path]] = field(default=plan_files)


def run(opts: Options, deps: Deps | None = None) -> int:
    deps = deps or Deps()
    root = opts.root or paths.repo_root()
    snapshot = opts.snapshot or link.snapshot_path(root)
    rc = 0
    verdicts: list[PlanVerdict] = []
    files = deps.plans(root)
    for path in files:
        rel = paths.relative_to_root(path, root)
        v = judge(rel, path.read_text(encoding="utf-8"), lambda sha: deps.first_tag(root, sha))
        if v is None:
            continue
        verdicts.append(v)
        what = "shipped in v%s" % v.version if v.kind == "shipped" else v.kind
        deps.out("%s: %s (%s), ids %s" % (rel, what, v.detail, ", ".join(v.ids)))
        if v.kind == "error":
            rc = 1
    shipped = [v for v in verdicts if v.kind == "shipped"]
    deps.out(
        "ship: %d plan(s) read, %d carry Feedback:, %d shipped"
        % (len(files), len(verdicts), len(shipped))
    )
    fresh_rows: list[dict[str, Any]] = []
    exported = 0
    for region in opts.regions:
        try:
            transport = deps.open_region(region, not opts.dry_run)
            items = client.export(transport, None, ())
        except client.FeedbackError as exc:
            log.error("%s: %s" % (region, exc))
            rc = max(rc, exc.rc)
            continue
        exported += 1
        vs = ship_verdicts(items, shipped)
        for body in vs:
            deps.out(
                "%s %s fixed-in-v%s"
                % (region, body["fingerprint"][: link.SHORT_FP], body["fixedIn"])
            )
        if vs and not opts.dry_run:
            try:
                written = client.write_verdicts(transport, vs)
            except client.FeedbackError as exc:
                log.error("%s: %s" % (region, exc))
                rc = max(rc, exc.rc)
                continue
            deps.out(
                "%s: %d fixed verdict(s) over %d report(s)"
                % (region, written.fingerprints, written.reports)
            )
        fresh_rows += [link.snapshot_row(i) for i in link.apply_verdicts(items, vs)]
    if opts.dry_run:
        deps.out("ship dry run: no verdict or snapshot written")
        return rc
    if exported:
        try:
            count = link.write_snapshot(snapshot, fresh_rows)
        except link.SnapshotError as exc:
            log.error("%s; it is never overwritten blind" % exc)
            return max(rc, 2)
        deps.out(
            "snapshot: %d fingerprint(s) in %s" % (count, paths.relative_to_root(snapshot, root))
        )
    return rc


def parse_args(argv: Sequence[str]) -> Options:
    parser = argparse.ArgumentParser(prog=SELF, description="feedback ship")
    sub = parser.add_subparsers(dest="verb", required=True)
    link.region_args(sub.add_parser("run", help="mark the fingerprints of shipped plans fixed"))
    ns = link.parse(parser, argv)
    return Options(link.regions_of(ns.region), ns.dry_run, ns.snapshot)


def main(
    argv: Sequence[str] | None = None, run_child: triage.Runner = triage._subprocess_runner
) -> int:
    return link.entry(SELF, __doc__, argv, parse_args, run, run_child)


if __name__ == "__main__":
    sys.exit(main())
