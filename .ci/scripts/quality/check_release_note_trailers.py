#!/usr/bin/env python3
"""check:ci-release-note-trailers -- every feat, fix or perf commit on a customer path in a PR carries a valid `Release-Note:` trailer.

The design is agent/plans/PLAN-release-notes.md (D2, D3 and box RN4). The commit-msg hook and the land check refuse a commit without the trailer, and neither sees a commit made outside them (a rebase, a push from another machine). This gate reads the commits that really arrived, the console range and each submodule's gitlink delta, through `rediacc_ci.release.release_notes.collect`, the same module the hook and the land check import, so a message those admit is a message this admits.

THE RANGE is read the way `scripts/gates/check-pr-task-trailers.ts` reads its own: `merge-base(PR_BASE_REF, tip)` to the tip, with the tip the PR head (`PR_HEAD_SHA`, else HEAD). A submodule's commits are those between the gitlink at the range start and the gitlink at the tip.

THE RANGE STARTS AT THE COMMIT THAT ADDED THIS FILE, not at the merge-base, while that commit is inside the PR. The branch carries thousands of commits written before the trailer existed, and a retroactive scan would turn every one of them into a finding nobody can repair (history is never rewritten). The anchor is the oldest commit that added this file (`git log --diff-filter=A`), so the rule binds exactly the commits after the gate. Once the anchor is an ancestor of the merge-base (the gate is on main) the range is the plain PR range. The same cut applies to a submodule: its delta starts at the gitlink the console recorded at the anchor.

FAILS CLOSED. A merge-base that cannot be computed, a file with no history, a submodule that is not checked out or lacks the gitlink commit, and a git failure are exit 1, never a clean read. ZERO commits read is exit 77 (cannot run), never 0: an empty range and a broken reader are indistinguishable by exit code, and only one of them is good news.

EXIT CODES: 0 every commit in range is admitted (or the run is on main, where the range is empty by construction); 1 an offender or an unreadable range; 2 the gate's own controls failed; 77 zero commits read.

---- gate ----
step: Release-Note trailers
lane: quality-submodule-branches
needs: none
selftest: true
env-PR_BASE_REF: origin/${{ github.event.pull_request.base.ref }}
env-PR_HEAD_REF: ${{ github.event.pull_request.head.ref || github.ref_name }}
env-PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}
why: a customer-facing commit that carries no Release-Note trailer drops out of the Release body and the changelog
     silently, and the commit-msg hook never sees a commit made outside it. The range gate reads the commits that arrived.
---- end gate ----
"""

from __future__ import annotations

import argparse
import contextlib
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

import _cipath
import _gate_args
from rediacc_ci import controls
from rediacc_ci.release import release_notes as rn

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
GATE_REL = ".ci/scripts/quality/check_release_note_trailers.py"
EXIT_NO_COMMITS = 77
MAX_SHOWN = 40
# The variables that pin git to one repository: a gate started from a hook inherits them, and `git -C <submodule>` would then read the console's objects.
GIT_REPO_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_PREFIX",
)


class GateError(RuntimeError):
    """A range that cannot be read; the gate is red, never clean."""


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in GIT_REPO_VARS}


def _git(root: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=str(root),
        env=_clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and proc.returncode != 0:
        msg = "`git %s` exited %d: %s" % (" ".join(args), proc.returncode, proc.stderr.strip())
        raise GateError(msg)
    return proc


def _is_ancestor(root: pathlib.Path, ancestor: str, descendant: str) -> bool:
    return (
        _git(root, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0
    )


def first_added(root: pathlib.Path, tip: str, rel: str) -> str | None:
    """The oldest commit reachable from `tip` that added `rel`, or None when the file has no history."""
    out = _git(root, "log", tip, "--diff-filter=A", "--format=%H", "--", rel).stdout.split()
    return out[-1] if out else None


def range_start(
    root: pathlib.Path,
    base: str,
    tip: str,
    gate_rel: str = GATE_REL,
    anchor: str | None = None,
) -> tuple[str, str]:
    """`(start, why)`: the merge-base, moved up to the anchor while the anchor commit is inside the PR range."""
    merge_base = _git(root, "merge-base", base, tip).stdout.strip()
    if not merge_base:
        msg = "no merge-base of %s and %s" % (base, tip)
        raise GateError(msg)
    found = anchor or first_added(root, tip, gate_rel)
    if not found:
        msg = (
            "%s has no history at %s, so the range has no start; commit the gate before running it"
            % (gate_rel, tip)
        )
        raise GateError(msg)
    if _is_ancestor(root, found, merge_base):
        return merge_base, "merge-base %s (the gate is already on the base)" % merge_base[:10]
    return found, "gate commit %s (commits before it predate the trailer)" % found[:10]


def evaluate(
    root: pathlib.Path,
    base: str,
    tip: str = "HEAD",
    gate_rel: str = GATE_REL,
    anchor: str | None = None,
) -> tuple[int, list[str]]:
    """`(exit code, report lines)` for the range ending at `tip`."""
    try:
        start, why = range_start(root, base, tip, gate_rel, anchor)
        result = rn.collect(start, tip, root)
    except (GateError, rn.ReleaseNotesError) as exc:
        return 1, ["✗ cannot read the range: %s" % exc]
    lines = ["range from %s to %s" % (start[:10], tip[:10]), "  start: %s" % why]
    lines.extend("  warning: %s" % w for w in result.warnings)
    if not result.commits:
        lines.append("✗ zero commits read; an empty range is CANNOT RUN, never clean")
        return EXIT_NO_COMMITS, lines
    bad = result.offenders
    if bad:
        lines.append(
            "✗ %d of %d commit(s) carry no valid Release-Note trailer"
            % (len(bad), len(result.commits))
        )
        for c in bad[:MAX_SHOWN]:
            lines.append("  %s %s %s" % (c.repo, c.sha[:10], c.subject[:72]))
            lines.append("    %s" % c.refusal)
        if len(bad) > MAX_SHOWN:
            lines.append("  ... and %d more" % (len(bad) - MAX_SHOWN))
        lines.append(
            "  Add `Release-Note: <customer text>` or `Release-Note: none -- <reason>` in a new commit message; history is not rewritten."
        )
        return 1, lines
    repos = sorted({c.repo for c in result.commits})
    lines.append(
        "✓ %d commit(s) read across %s: %d note(s), %d `none`, no offender"
        % (len(result.commits), ", ".join(repos), len(result.notes), result.none_count)
    )
    return 0, lines


# --------------------------------------------------------------------------- fixture and controls

# The fixture repositories hold made-up files under this directory; the directory is named once, apart from the file names, so the dead-path scan sees no full path that does not exist in this tree.
FX_CLI_SRC = "packages/cli/src"
NOTE = "Backups now resume after a dropped connection"


class Fixture:
    """A throwaway console with `private/account` as a real submodule, for the controls and the tests."""

    def __init__(self, base: pathlib.Path) -> None:
        self.base = base
        self.console = base / "console"
        self.sub_origin = base / "account"
        self.sub = self.console / "private" / "account"
        self.base_sha = ""

    def git(self, cwd: pathlib.Path, *args: str) -> str:
        env = _clean_env()
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
        proc = subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "protocol.file.allow=always",
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            msg = "fixture git %s: %s" % (" ".join(args), proc.stderr.strip())
            raise AssertionError(msg)
        return proc.stdout.strip()

    def commit(self, cwd: pathlib.Path, path: str, message: str) -> str:
        target = cwd / path
        target.parent.mkdir(parents=True, exist_ok=True)
        before = target.read_text() if target.exists() else ""
        target.write_text(before + "x\n")
        self.git(cwd, "add", "--", path)
        self.git(cwd, "commit", "-q", "-m", message)
        return self.git(cwd, "rev-parse", "HEAD")

    def bump(self, message: str = "chore(submodules): bump the account pointer") -> str:
        self.git(self.console, "add", "--", "private/account")
        self.git(self.console, "commit", "-q", "-m", message)
        return self.git(self.console, "rev-parse", "HEAD")

    def build(self) -> str:
        """Create both repos, add a pre-gate trailer-less `feat:` to each, commit the gate; return the base sha."""
        self.sub_origin.mkdir(parents=True)
        self.git(self.sub_origin, "init", "-q", "-b", "main")
        self.commit(self.sub_origin, "README.md", "chore: init")
        self.console.mkdir(parents=True)
        self.git(self.console, "init", "-q", "-b", "main")
        self.commit(self.console, "README.md", "chore: init")
        self.git(self.console, "submodule", "add", "-q", str(self.sub_origin), "private/account")
        self.git(self.console, "commit", "-q", "-m", "chore: add the account submodule")
        self.base_sha = self.git(self.console, "rev-parse", "HEAD")
        # Written before the gate: trailer-less customer `feat:` commits in both repos. They sit between the base and the anchor, so a retroactive scan would flag them.
        self.commit(
            self.console, FX_CLI_SRC + "/old.ts", "feat(cli): an old feature with no trailer"
        )
        self.commit(self.sub, "src/old.ts", "feat: an old submodule feature with no trailer")
        self.bump()
        self.commit(self.console, GATE_REL, "ci(release): add the release-note trailer gate")
        return self.base_sha

    def anchor(self) -> str:
        return first_added(self.console, "HEAD", GATE_REL) or ""


@contextlib.contextmanager
def fixture() -> Iterator[Fixture]:
    with tempfile.TemporaryDirectory(prefix="rn-trailers-") as tmp:
        fx = Fixture(pathlib.Path(tmp))
        fx.build()
        yield fx


def run_controls() -> bool:
    """True when every control held. Each drives `evaluate` against real git repositories."""
    ok = True

    def check(label: str, cond: object) -> None:
        nonlocal ok
        if cond:
            print("  PASS  %s" % label)
        else:
            ok = False
            print("  FAIL  %s" % label, file=sys.stderr)

    with fixture() as fx:
        base = fx.base_sha
        rc, _ = evaluate(fx.console, base)
        check("zero commits after the gate commit is 77, never 0", rc == EXIT_NO_COMMITS)

        fx.commit(fx.console, ".github/workflows/x.yml", "feat(ci): an internal change")
        fx.commit(fx.console, "docs/agent-reference/x.md", "chore: a note")
        rc, _ = evaluate(fx.console, base)
        check(
            "only exempt commits is 0, and the trailer-less feat before the gate is not read",
            rc == 0,
        )

        fx.commit(fx.console, FX_CLI_SRC + "/ok.ts", "feat(cli): resume\n\nRelease-Note: %s" % NOTE)
        rc, _ = evaluate(fx.console, base)
        check("a valid trailer is 0", rc == 0)

        sub_sha = fx.commit(fx.sub, "src/new.ts", "feat: a new submodule feature with no trailer")
        fx.bump()
        rc, lines = evaluate(fx.console, base)
        text = "\n".join(lines)
        check("a trailer-less feat in a submodule is 1", rc == 1)
        check(
            "the offender is named by its submodule sha",
            sub_sha[:10] in text and "private/account" in text,
        )

        console_sha = fx.commit(
            fx.console,
            FX_CLI_SRC + "/bad.ts",
            "fix(cli): a console fix\n\nRelease-Note: none -- n/a",
        )
        rc, lines = evaluate(fx.console, base)
        check(
            "a `none` with a short reason is refused in the console",
            rc == 1 and console_sha[:10] in "\n".join(lines),
        )

        rc, _ = evaluate(fx.console, "does-not-exist")
        check("an unreadable base is 1, never 0", rc == 1)

        rc, _ = evaluate(fx.console, base, gate_rel="no/such/gate.py")
        check("a gate file with no history is 1, never 0", rc == 1)

        rc, lines = evaluate(fx.console, fx.anchor())
        check(
            "with the gate on the base the range starts at the merge-base",
            rc == 1 and "already on the base" in "\n".join(lines),
        )
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="check:ci-release-note-trailers")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)

    if controls.controls_first("release-note trailers", lambda: not run_controls()):
        return 2
    if args.selftest:
        return 0

    root = pathlib.Path(args.root).resolve() if args.root else REPO_ROOT
    head = os.environ.get("PR_HEAD_REF") or os.environ.get("GITHUB_HEAD_REF") or ""
    if head == "main":
        print("- skipped: on main; the range gate is a PR artefact")
        return 0
    base = os.environ.get("PR_BASE_REF") or "origin/main"
    tip = os.environ.get("PR_HEAD_SHA") or "HEAD"
    code, lines = evaluate(root, base, tip)
    for line in lines:
        print(line, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    _gate_args.parse(
        "check_release_note_trailers.py", sys.argv[1:], switches=("--selftest",), valued=("--root",)
    )
    raise SystemExit(main(sys.argv[1:]))
