#!/usr/bin/env python3
"""check:ci-commit-citations -- every commit SHA cited in a tracked code, test or plan file names a commit that `origin/main` carries.

WHY (worklist #f7b8953f, 2026-10-23). A PR merges by `gh pr merge --rebase`, which REWRITES every commit of the branch. A SHA a branch file cites for one of the branch's own commits therefore points at nothing once the PR lands: two such SHAs sat in two tests and the retire-bash-oracles inventory after their commits were rewritten, until a hand remap (the worklist item names both). Nothing noticed in between, because a dead SHA reads exactly like a live one.

WHAT IS A CITATION. Purely textual, so a local run and CI agree byte for byte:

  - any word of exactly 9 lowercase hex characters with at least one digit and one letter
    (this repository's `core.abbrev` width, the form `git log --oneline` prints and the
    form every hand citation here takes);
  - any 7..40 hex word right after a commit cue: `commit`, `commits`, `commit:`, `commit/`,
    `sha`, `fixed in`, `landed in`, `reverted`, `cherry-picked from`.

A FIXTURE TOKEN is skipped and counted: a test's made-up SHA spells a word (`dead`, `beef`, `cafe`, `f00d`, `c0de`, `abcdef`, `abc123`, `0000`, `1234567`), which a real 9-character abbreviation does about once in ten thousand. The success line prints how many were skipped, so the skip cannot grow unseen.

Three line shapes are not commit citations of THIS repository and are skipped: an action pin (`uses: owner/repo@<sha>`), a line that says `blob` or `tree` (tombstone rows and object ids), and a line naming a submodule (`private/<name>`, `renet`, `elite`, `submodule`), whose commits live in another object store this checkout does not judge.

WHERE. `git ls-files` of this repository: code and tests (.py .ts .tsx .js .mjs .cjs .sh .go .yml .yaml) and every plan (`agent/plans/**.md`). Never `agent/reviews/**`, `agent/worklist/**` or `agent/ledgers/**`: those are records OF a moment and cite the SHAs that existed then.

THE VERDICT reads commit TOPOLOGY only, never object types, because the CI lane is a `blob:none` partial clone and an object-type answer would differ between a laptop and the runner. Every git read runs with GIT_NO_LAZY_FETCH=1, so an absent object is absent rather than a network round trip.

  ok        a prefix of a commit reachable from origin/<base> (GITHUB_BASE_REF, default main);
  pending   a prefix of a commit only in origin/<base>..HEAD: the branch cites its own commit,
            which the rebase-merge will rewrite. Printed, never failing; remap it on main after
            the merge (the /pr-merge follow-up);
  dead      neither. A finding.

SHRINK-ONLY BASELINE (.ci/config/commit-citations-baseline.json). The findings of the day the gate landed are frozen by a stable id, a hash of the file path and the cited token (never a line number). A NEW dead citation fails. A baselined one that no longer fires fails too, until `--write-baseline` drains it; that writer only ever REMOVES entries, so a drain cannot absorb a fresh finding. `--init-baseline` writes the first file and refuses when one exists.

ANTI-VACUITY. Exit 2 when origin/<base> is not fetched, when no file is scanned, when no citation is found, or when not one citation resolves to the base: each of those is a gate that cannot see, never a clean tree. The success line prints the shape (files, citations, ok, pending, baselined).

A plain check runs `--selftest`'s controls first (a scratch repository, both directions, the plant included) and fails before the scan when one breaks.

Exit codes: 0 clean, 1 a finding or a broken control, 2 the gate could not run.
"""

from __future__ import annotations

import bisect
import dataclasses
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
BASELINE_REL = ".ci/config/commit-citations-baseline.json"
EXCLUDED = ("agent/reviews/", "agent/worklist/", "agent/ledgers/")
CODE_EXT = (".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".sh", ".go", ".yml", ".yaml")
PLAN_PREFIX = "agent/plans/"

ABBREV = re.compile(r"(?<![0-9A-Za-z_./@-])([0-9a-f]{9})(?![0-9A-Za-z_-])")
CUE = re.compile(
    r"(?i)\b(?:commits?|sha|fixed in|landed in|reverted|cherry-picked from)\b[\s:`(#/]*"
    r"([0-9a-fA-F]{7,40})(?![0-9A-Za-z_-])"
)
SKIP_LINE = re.compile(
    r"\buses:\s*\S+@[0-9a-f]{40}|\b(?:blob|tree)\b|private/[a-z]+|\brenet\b|\belite\b|\bsubmodule",
    re.IGNORECASE,
)
FIXTURE_WORDS = ("dead", "beef", "cafe", "f00d", "c0de", "abcdef", "abc123", "0000", "1234567")
FIX = (
    "cite the commit origin/main carries (the rebased SHA: "
    "`git log --format='%h %s' origin/main | grep -F '<its subject>'`), or drop the SHA. "
    "A submodule commit names its submodule on the same line (`private/renet <sha>`). "
    "Do not add it to the baseline."
)


@dataclasses.dataclass(frozen=True)
class Citation:
    path: str
    line: int
    token: str

    @property
    def key(self) -> str:
        """The stable id: the path and the token, hashed. A moved paragraph keeps it; a rewritten citation is a new finding, which is when a reader should look again."""
        return hashlib.sha256(("%s\0%s" % (self.path, self.token)).encode()).hexdigest()[:16]


def _git(root, *args) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, env=env, check=False
    )


def in_scope(path: str) -> bool:
    if path.startswith(EXCLUDED):
        return False
    if path.startswith(PLAN_PREFIX) and path.endswith(".md"):
        return True
    return path.endswith(CODE_EXT)


def _shaped(token: str) -> bool:
    return bool(re.search(r"[0-9]", token) and re.search(r"[a-f]", token))


def is_fixture(token: str) -> bool:
    return any(w in token for w in FIXTURE_WORDS)


def citations(path: str, text: str) -> list[Citation]:
    """Every commit citation in one file's text, once per (line, token), fixture tokens included (`run` sets them aside and counts them)."""
    out: list[Citation] = []
    for n, line in enumerate(text.splitlines(), 1):
        if SKIP_LINE.search(line):
            continue
        seen: set[str] = set()
        for m in CUE.finditer(line):
            tok = m.group(1).lower()
            if _shaped(tok) and tok not in seen:
                seen.add(tok)
                out.append(Citation(path, n, tok))
        for m in ABBREV.finditer(line):
            tok = m.group(1)
            if _shaped(tok) and tok not in seen:
                seen.add(tok)
                out.append(Citation(path, n, tok))
    return out


def scan(root) -> tuple[int, list[Citation]]:
    """(files scanned, citations) over the tracked in-scope files under `root`."""
    got = _git(root, "ls-files", "-z")
    if got.returncode:
        raise RuntimeError("git ls-files failed: %s" % got.stderr.strip()[:200])
    files = [p for p in got.stdout.split("\0") if p and in_scope(p)]
    found: list[Citation] = []
    scanned = 0
    for rel in files:
        path = pathlib.Path(root) / rel
        if path.is_symlink() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        found.extend(citations(rel, text))
    return scanned, found


class Commits:
    """A sorted list of full commit ids, answering "is this token a prefix of one of them"."""

    def __init__(self, shas):
        self.shas = sorted(set(shas))

    def __len__(self) -> int:
        return len(self.shas)

    def has_prefix(self, token: str) -> bool:
        i = bisect.bisect_left(self.shas, token)
        return i < len(self.shas) and self.shas[i].startswith(token)


def reachable(root, base_ref: str) -> tuple[Commits, Commits]:
    """(commits of `base_ref`, commits of `base_ref..HEAD`). RuntimeError when the base is not fetched."""
    if _git(root, "rev-parse", "--verify", "-q", "%s^{commit}" % base_ref).returncode:
        raise RuntimeError(
            "%s is not fetched, so no citation can be judged; run: git fetch origin %s"
            % (base_ref, base_ref.split("/", 1)[-1])
        )
    main = _git(root, "rev-list", base_ref)
    branch = _git(root, "rev-list", "%s..HEAD" % base_ref)
    if main.returncode or branch.returncode:
        raise RuntimeError("git rev-list failed: %s" % (main.stderr + branch.stderr).strip()[:200])
    return Commits(main.stdout.split()), Commits(branch.stdout.split())


def classify(found, main: Commits, branch: Commits):
    """(ok, pending, dead) lists of citations."""
    ok, pending, dead = [], [], []
    for c in found:
        if main.has_prefix(c.token):
            ok.append(c)
        elif branch.has_prefix(c.token):
            pending.append(c)
        else:
            dead.append(c)
    return ok, pending, dead


def load_baseline(root) -> dict[str, dict]:
    path = pathlib.Path(root) / BASELINE_REL
    doc = json.loads(path.read_text(encoding="utf-8"))
    return dict(doc.get("findings") or {})


def write_baseline(root, entries: dict[str, dict]) -> None:
    doc = {
        "comment": (
            "Shrink-only baseline of check:ci-commit-citations (dead commit SHAs cited in "
            "tracked files). Keyed by a hash of path and token, never a line number. "
            "`--write-baseline` only removes entries; never add one by hand."
        ),
        "findings": {k: entries[k] for k in sorted(entries)},
    }
    # The writer is mode-gated: main() reaches it only under --write-baseline or --init-baseline, and the controls call it on a TemporaryDirectory root.
    path = pathlib.Path(root) / BASELINE_REL
    # tree-write: mode --write-baseline|--init-baseline the baseline directory, created only by the baseline writer
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # tree-write: mode --write-baseline|--init-baseline the temporary copy the baseline writer renames into place
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    # tree-write: mode --write-baseline|--init-baseline the atomic rename of the baseline writer's temporary copy
    tmp.replace(path)


def run(root, base_ref: str, mode: str = "check", out=sys.stdout, err=sys.stderr) -> int:
    try:
        scanned, found = scan(root)
        main, branch = reachable(root, base_ref)
    except RuntimeError as exc:
        print("✗ commit citations: CANNOT RUN: %s" % exc, file=err)
        return 2
    if scanned == 0:
        print("✗ commit citations: CANNOT RUN: VACUOUS, no tracked file is in scope", file=err)
        return 2
    if not found:
        print(
            "✗ commit citations: CANNOT RUN: VACUOUS, %d file(s) scanned and not one citation found; "
            "the extractor is not seeing the tree" % scanned,
            file=err,
        )
        return 2
    fixtures = [c for c in found if is_fixture(c.token)]
    found = [c for c in found if not is_fixture(c.token)]
    ok, pending, dead = classify(found, main, branch)
    if not ok:
        print(
            "✗ commit citations: CANNOT RUN: %d citation(s) and not one resolves to %s (%d "
            "commits); the commit set is not what it seems" % (len(found), base_ref, len(main)),
            file=err,
        )
        return 2
    dead_by_key: dict[str, Citation] = {}
    for c in dead:
        dead_by_key.setdefault(c.key, c)
    path = pathlib.Path(root) / BASELINE_REL
    if mode == "init":
        if path.exists():
            print(
                "✗ %s exists; --init-baseline writes only the first file" % BASELINE_REL, file=err
            )
            return 1
        write_baseline(root, {k: {"path": c.path, "sha": c.token} for k, c in dead_by_key.items()})
        print("✓ wrote %s with %d finding(s)" % (BASELINE_REL, len(dead_by_key)), file=out)
        return 0
    try:
        baseline = load_baseline(root)
    except (OSError, ValueError) as exc:
        print(
            "✗ commit citations: CANNOT RUN: %s is unreadable: %s" % (BASELINE_REL, exc), file=err
        )
        return 2
    new = [c for k, c in sorted(dead_by_key.items()) if k not in baseline]
    fixed = sorted(k for k in baseline if k not in dead_by_key)
    if mode == "write":
        kept = {k: v for k, v in baseline.items() if k in dead_by_key}
        write_baseline(root, kept)
        print(
            "✓ drained %d fixed entr(y/ies) from %s; %d remain; %d new finding(s) were NOT added"
            % (len(fixed), BASELINE_REL, len(kept), len(new)),
            file=out,
        )
        return 1 if new else 0
    for c in pending[:10]:
        print(
            "  pending %s:%d cites %s, a commit only on this branch; the rebase-merge rewrites "
            "it, so remap it on main after the merge" % (c.path, c.line, c.token),
            file=out,
        )
    if len(pending) > 10:
        print("  pending: %d more" % (len(pending) - 10), file=out)
    rc = 0
    for c in new:
        print(
            "✗ %s:%d cites %s, which is no commit of %s or of this branch (a rebase-merge "
            "rewrote it, or it never existed here). Fix: %s"
            % (c.path, c.line, c.token, base_ref, FIX),
            file=err,
        )
        rc = 1
    for k in fixed:
        entry = baseline[k]
        print(
            "✗ baselined %s citing %s no longer fires; drain it: "
            ".ci/scripts/quality/check_commit_citations.py --write-baseline"
            % (entry.get("path"), entry.get("sha")),
            file=err,
        )
        rc = 1
    shape = (
        "%d file(s), %d citation(s): %d on %s, %d pending, %d dead (%d baselined), "
        "%d fixture token(s) skipped"
        % (
            scanned,
            len(found),
            len(ok),
            base_ref,
            len(pending),
            len(dead),
            len(dead_by_key) - len(new),
            len(fixtures),
        )
    )
    if rc == 0:
        print("✓ commit citations: %s" % shape, file=out)
    else:
        print("✗ commit citations: %s" % shape, file=err)
    return rc


# ---------------------------------------------------------------------------- selftest


def _selftest() -> int:
    """Both directions over a scratch repository: main carries commit A, the branch adds B."""
    fails: list[str] = []

    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r, wanted %r" % (name, got, want))

    def g(root, *args):
        env = dict(
            os.environ,
            GIT_AUTHOR_NAME="t",
            GIT_AUTHOR_EMAIL="t@t",
            GIT_COMMITTER_NAME="t",
            GIT_COMMITTER_EMAIL="t@t",
            GIT_CONFIG_NOSYSTEM="1",
            HOME=str(root),
        )
        r = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, env=env, check=False
        )
        if r.returncode:
            raise RuntimeError(r.stderr)
        return r.stdout.strip()

    # The extractor alone, both directions.
    got = [c.token for c in citations("x.py", "# fixed in 0badc0de1 and commit:abc1234\n")]
    check("extract: a 9-hex word and a cued 7-hex word", sorted(got), ["0badc0de1", "abc1234"])
    check("fixture: a word-spelling token is a fixture", is_fixture("0badc0de1"), True)
    check("fixture: a plain abbreviation is not", is_fixture("5e1f2a3b" + "9"), False)
    check("extract: an all-digit 9-word is no SHA", citations("x.py", "run 123456789\n"), [])
    check(
        "extract: an action pin is skipped", citations("w.yml", "uses: a/b@" + "0a" * 20 + "\n"), []
    )
    check("extract: a submodule line is skipped", citations("x.py", "renet 0badc0de1\n"), [])
    check("extract: inside an identifier is no SHA", citations("x.py", "v_0badc0de1x\n"), [])
    check("scope: a review record is out", in_scope("agent/reviews/b/x.md"), False)
    check("scope: a plan is in", in_scope("agent/plans/PLAN-x.md"), True)
    check("scope: a markdown doc outside plans is out", in_scope("docs/x.md"), False)

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        g(root, "init", "-q", "-b", "main")
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        g(root, "add", "-A")

        def commit(msg):
            # A scratch SHA is random, and one that spells a fixture word or lacks a digit or a letter is skipped by the extractor, which made this selftest fail about one run in thirty. Re-commit under a new message until the 9-hex prefix is one the extractor reads.
            for i in range(64):
                g(root, "commit", "-qm", "%s %d" % (msg, i), *(["--amend"] if i else []))
                sha = g(root, "rev-parse", "HEAD")[:9]
                if _shaped(sha) and not is_fixture(sha):
                    return sha
            raise RuntimeError("no usable scratch SHA in 64 tries")

        a = commit("A")
        g(root, "update-ref", "refs/remotes/origin/main", "HEAD")
        g(root, "checkout", "-q", "-b", "feature")
        (root / "b.py").write_text("y = 2\n", encoding="utf-8")
        g(root, "add", "-A")
        b = commit("B")
        # Built at run time: a literal here would be a dead citation in this very file.
        dead = "5e1f2a3b" + ("8" if "5e1f2a3b" + "9" in a + b else "9")
        (root / "cite.py").write_text("# on main %s\n# branch %s\n" % (a, b), encoding="utf-8")
        (root / "agent" / "reviews" / "x").mkdir(parents=True)
        (root / "agent" / "reviews" / "x" / "r.py").write_text("# %s\n" % dead, encoding="utf-8")
        g(root, "add", "-A")

        def go(mode="check"):
            o, e = io.StringIO(), io.StringIO()
            return run(root, "origin/main", mode, o, e), o.getvalue(), e.getvalue()

        rc, out, _e = go("init")
        check("init: no dead citation yet, empty baseline", rc, 0)
        rc, out, err = go()
        check("clean: ok and pending pass", rc, 0)
        check(
            "clean: the pending branch commit is named",
            "pending cite.py:2 cites %s" % b in out,
            True,
        )
        check("clean: the shape is printed", "1 on origin/main, 1 pending, 0 dead" in out, True)
        # A fixture token is skipped, and counted in the shape.
        (root / "fx.py").write_text("# sha: deadbeef1\n", encoding="utf-8")
        g(root, "add", "-A")
        rc, out, _e = go()
        check("fixture: skipped, counted", (rc, "1 fixture token(s) skipped" in out), (0, True))
        # THE PLANT: a dead SHA in a tracked file fails.
        (root / "dead.py").write_text("# fixed in %s\n" % dead, encoding="utf-8")
        g(root, "add", "-A")
        rc, _o, err = go()
        check("plant: a dead SHA fails", rc, 1)
        check(
            "plant: the finding names file, line and token",
            "dead.py:1 cites %s" % dead in err,
            True,
        )
        check("plant: the fix says not to baseline", "Do not add it to the baseline" in err, True)
        # The drain never absorbs a new finding.
        rc, out, _e = go("write")
        check("write: a new finding is not added", (rc, load_baseline(root)), (1, {}))
        # A baselined finding passes, and fails again once fixed until drained.
        key = Citation("dead.py", 1, dead).key
        write_baseline(root, {key: {"path": "dead.py", "sha": dead}})
        check("baselined: passes", go()[0], 0)
        (root / "dead.py").write_text("# fixed\n", encoding="utf-8")
        rc, _o, err = go()
        check(
            "fixed: a baselined finding that stopped firing fails",
            (rc, "drain it" in err),
            (1, True),
        )
        check("drain: the fixed entry leaves", (go("write")[0], load_baseline(root)), (0, {}))
        # Anti-vacuity: no base ref is CANNOT RUN, not green.
        rc, _o, err = run(root, "origin/nope", "check", io.StringIO(), io.StringIO()), "", ""
        check("vacuity: an unfetched base is exit 2", rc, 2)
        (root / "cite.py").write_text("# none\n", encoding="utf-8")
        g(root, "add", "-A")
        check("vacuity: not one citation resolving to main is exit 2", go()[0], 2)
    for f in fails:
        print("  FAIL %s" % f, file=sys.stderr)
    if fails:
        print("✗ commit citations selftest: %d failure(s)" % len(fails), file=sys.stderr)
        return 1
    print("✓ commit citations selftest: every control held")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    root = ROOT
    if "--root" in argv:
        root = pathlib.Path(argv[argv.index("--root") + 1])
    base = "origin/%s" % (os.environ.get("GITHUB_BASE_REF") or "main")
    mode = "check"
    if "--write-baseline" in argv:
        mode = "write"
    elif "--init-baseline" in argv:
        mode = "init"
    # The controls run first on every check: the registry invokes a .py gate by its bare path, with no `--selftest &&` leg, so this is where a broken extractor or verdict is caught before its green is believed.
    if mode == "check" and _selftest() != 0:
        return 1
    return run(root, base, mode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
