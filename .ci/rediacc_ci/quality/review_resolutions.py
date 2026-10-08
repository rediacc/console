"""check:ci-review-resolutions: a deferred review finding is unfinished work, and nothing merges over it.

WHY IT EXISTS (agent/plans/PLAN-deferred-findings-block-merge.md, operator ruling 2026-10-08). Every per-commit review finding under `agent/reviews/<branch>/` ends in a `Resolution:` line. Until this gate, the line `deferred #<item>` counted as resolved in every local reader, and no CI step read the resolutions at all: branch 1007-1 merged as PR #599 carrying a deferral. The ruling: a finding is fixed before merge, always, and the one escape is an operator-ruled waiver.

WHAT IT READS. The live branch's directory only, `agent/reviews/<branch_slug(GITHUB_HEAD_REF or the checked-out branch)>/`, through the CI-side lenient parser `rediacc_ci.review.review_table.load_records` (every `.md` record and each `clean.jsonl` line). Every other directory is merged history and is not judged. No worklist store, no network, stdlib only.

THE FOUR RULES (plan D4), each a refusal with exit 1:

    (i)   a finding whose resolution is the retired `deferred #<item>`, at any severity;
    (ii)  an `open` finding at or above `block_at` from `.ci/config/commit-review.json`,
          the same threshold `wl_review.py --check` applies;
    (iii) a resolution string that matches none of the grammar below. The display
          parser used to map an unknown word to `open`, which hid a typo, a hand edit
          and a grammar a newer writer invented, so here an unreadable resolution is
          a refusal of its own, and so is a record the lenient parser could not read;
    (iv)  ANTI-VACUITY: zero records while `merge-base(origin/<base>, HEAD)..HEAD`
          (no merges) holds a REVIEWABLE commit, one authored at or after
          `review_epoch` that touches a path outside `agent/reviews/`. An empty
          directory is otherwise indistinguishable from a clean one.

THE GRAMMAR, mirrored from `.claude/hooks/stop/wl_review.py` `RESOLUTION_RES` and pinned to it by a parity test (`test_gate_review_resolutions.py`) rather than by an import, so `wl_review` stays free of `.ci` imports and this module stays free of the hook tree:

    open
    fixed <sha40> | <me8> <isoZ>
    not-a-bug | <evidence, 20+ chars> | <me8 or oracle> <isoZ>
    waived #<item> ASKED:<YYYY-MM-DDTHH:MM>Z | <me8> <isoZ>
    deferred #<item> | <me8> <isoZ>          (legacy: still parsed, always refused)

A WAIVER IS TRUSTED ON ITS GRAMMAR. The `ASKED:` minute is matched against the lead transcript by the mark verb, which a runner cannot do; the hand-edit guards are what stop a self-written waiver. So every waiver is PRINTED, in the output and in `$GITHUB_STEP_SUMMARY`, where a reader of the PR sees it.

WHAT A GREEN DOES NOT MEAN. It does not mean every commit is covered by a record: per-commit coverage (patch-id matching across rebases) stays with `wl_review.py --check` and the push guard. Rule iv only refuses the case where the directory holds nothing at all.

EXIT CODES: 0 clean, 1 a refusal, 2 CANNOT RUN (a pull_request run with no head ref, an unreadable config, no base to measure rule iv against while the directory is empty, or a failed control). A local run on `main` or a detached HEAD prints "not a PR branch: nothing to judge" and exits 0.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci import controls
from rediacc_ci.review import review_table
from rediacc_ci.review.pr_labels import branch_slug

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

CONFIG_REL = ".ci/config/commit-review.json"
REVIEWS_REL = review_table.REVIEWS_REL
WORKLIST = "python3 .claude/hooks/stop/worklist.py"
SEV_RANK = {"high": 3, "medium": 2, "low": 1}
CLAIM_CLIP = 200

ISOZ = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
ME8 = r"[0-9a-f]{8}"
ORACLE_SIGNER = "oracle"
# The five shapes are disjoint on their first word, so the order is for reading only.
RESOLUTION_RES = (
    ("open", re.compile(r"^open$")),
    ("fixed", re.compile(r"^fixed ([0-9a-f]{40}) \| (%s) (%s)$" % (ME8, ISOZ))),
    (
        "not-a-bug",
        re.compile(r"^not-a-bug \| (.{20,}) \| (%s|%s) (%s)$" % (ME8, ORACLE_SIGNER, ISOZ)),
    ),
    (
        "waived",
        re.compile(
            r"^waived #([0-9a-f]{6,16}) ASKED:(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})Z \| (%s) (%s)$"
            % (ME8, ISOZ)
        ),
    ),
    ("deferred", re.compile(r"^deferred #([0-9a-f]{6,16}) \| (%s) (%s)$" % (ME8, ISOZ))),
)
KINDS = tuple(kind for kind, _rx in RESOLUTION_RES)
UNKNOWN = "unknown"
NOT_A_PR = "not a PR branch: nothing to judge"


class CannotRunError(Exception):
    """No verdict is possible. Exit 2, never a green."""


def kind_of(resolution: str) -> str:
    """The resolution kind of one `Resolution:` value, or "" when it matches no shape (rule iii).

    The same contract as `wl_review.Finding.resolution_kind`, which is what the parity test compares.
    """
    for kind, rx in RESOLUTION_RES:
        if rx.match(resolution):
            return kind
    return ""


def _clip(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[: cap - 3] + "..."


# --------------------------------------------------------------------------- the verdict


@dataclasses.dataclass
class Row:
    """One finding as the verdict reports it."""

    id: str
    severity: str
    path: str
    line: int
    claim: str
    resolution: str
    file: str

    def where(self) -> str:
        return "%s:%d" % (self.path, self.line)

    def head(self) -> str:
        """The resolution without its signature, for the waiver list."""
        return self.resolution.split(" | ", 1)[0]


@dataclasses.dataclass
class Verdict:
    records: int = 0
    findings: int = 0
    counts: dict[str, int] = dataclasses.field(default_factory=dict)
    deferred: list[Row] = dataclasses.field(default_factory=list)
    blocking: list[Row] = dataclasses.field(default_factory=list)
    unknown: list[Row] = dataclasses.field(default_factory=list)
    malformed: list[str] = dataclasses.field(default_factory=list)
    waived: list[Row] = dataclasses.field(default_factory=list)

    @property
    def refusals(self) -> int:
        return len(self.deferred) + len(self.blocking) + len(self.unknown) + len(self.malformed)


def judge(records: Iterable[review_table.Record], block_at: str) -> Verdict:
    """Rules i, ii and iii over parsed records. Pure: no git, no filesystem."""
    rank = SEV_RANK[block_at]
    v = Verdict(counts=dict.fromkeys((*KINDS, UNKNOWN), 0))
    for rec in records:
        v.records += 1
        if rec.problem:
            v.malformed.append("%s: %s" % (rec.file or rec.sha, rec.problem))
        for f in rec.findings:
            v.findings += 1
            row = Row(f.id, f.severity, f.path, f.line, f.claim, f.resolution, rec.file)
            kind = kind_of(f.resolution)
            v.counts[kind or UNKNOWN] += 1
            if kind == "deferred":
                v.deferred.append(row)
            elif kind == "waived":
                v.waived.append(row)
            elif kind == "open" and SEV_RANK.get(f.severity, SEV_RANK["high"]) >= rank:
                v.blocking.append(row)
            elif not kind:
                v.unknown.append(row)
    return v


# --------------------------------------------------------------------------- the branch and its commits


@dataclasses.dataclass
class Target:
    """Which directory to judge, or why there is nothing to judge."""

    branch: str = ""
    skip: str = ""


def target(env: Mapping[str, str], current: str | None) -> Target:
    """The branch whose directory is judged.

    A pull_request run names its head in GITHUB_HEAD_REF. If that did not arrive (it does not survive every `workflow_call` chain) the run cannot say which directory is live, which is CANNOT RUN rather than a guess. Locally the checked-out branch is the answer, and `main` or a detached HEAD has no PR to judge.
    """
    head = (env.get("GITHUB_HEAD_REF") or "").strip()
    if head:
        return Target(branch=head)
    event = env.get("GITHUB_EVENT_NAME") or ""
    if event.startswith("pull_request"):
        raise CannotRunError(
            "GITHUB_EVENT_NAME=%s but GITHUB_HEAD_REF is empty, so the live review directory "
            "cannot be named. Pass `GITHUB_HEAD_REF: ${{ github.head_ref }}` to the step." % event
        )
    if not current:
        return Target(skip="%s (detached HEAD)" % NOT_A_PR)
    if current == "main":
        return Target(skip="%s (on main)" % NOT_A_PR)
    return Target(branch=current)


def _git(root: pathlib.Path, *args: str, env: Mapping[str, str] | None = None) -> tuple[int, str]:
    full = dict(os.environ if env is None else env)
    full["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
        env=full,
    )
    return proc.returncode, proc.stdout


def _parse_iso(text: str) -> datetime.datetime | None:
    try:
        when = datetime.datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=datetime.UTC)


@dataclasses.dataclass
class Commit:
    sha: str
    author_date: str
    paths: list[str]


def is_reviewable(commit: Commit, epoch: datetime.datetime | None) -> bool:
    """A commit the reviewer owes a record for: it touches something outside `agent/reviews/` and is not authored before the epoch. An empty commit touches nothing and is not reviewable, matching `wl_review.uncovered`."""
    if not commit.paths or all(p.startswith(REVIEWS_REL + "/") for p in commit.paths):
        return False
    when = _parse_iso(commit.author_date)
    return not (epoch and when and when < epoch)


def parse_log(out: str) -> list[Commit]:
    """`git log --format=%x1e%H%x1f%aI --name-only` output, one Commit per record."""
    commits: list[Commit] = []
    for chunk in out.split("\x1e"):
        if not chunk.strip():
            continue
        head, _, rest = chunk.partition("\n")
        sha, _, author_date = head.partition("\x1f")
        commits.append(Commit(sha, author_date, [p for p in rest.split("\n") if p.strip()]))
    return commits


def branch_commits(root: pathlib.Path, base: str) -> list[Commit] | None:
    """The non-merge commits of `merge-base(base, HEAD)..HEAD`, or None when the base does not resolve."""
    rc, mb = _git(root, "merge-base", base, "HEAD")
    if rc != 0 or not mb.strip():
        return None
    rc, out = _git(
        root,
        "log",
        "--no-merges",
        "--format=%x1e%H%x1f%aI",
        "--name-only",
        "%s..HEAD" % mb.strip(),
    )
    return parse_log(out) if rc == 0 else None


def load_config(root: pathlib.Path) -> tuple[str, datetime.datetime | None]:
    """(block_at, review_epoch) from the config the local layer reads too. An unreadable file, or a `block_at` outside the three severities, is CANNOT RUN: falling back to a default would judge against a threshold nobody set."""
    path = root / CONFIG_REL
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRunError("%s is unreadable: %s" % (CONFIG_REL, exc)) from exc
    if not isinstance(cfg, dict):
        raise CannotRunError("%s is not a JSON object" % CONFIG_REL)
    block_at = cfg.get("block_at")
    if block_at not in SEV_RANK:
        raise CannotRunError(
            "%s block_at is %r; expected one of %s" % (CONFIG_REL, block_at, ", ".join(SEV_RANK))
        )
    epoch_text = str(cfg.get("review_epoch") or "")
    epoch = _parse_iso(epoch_text) if epoch_text else None
    if epoch_text and epoch is None:
        raise CannotRunError("%s review_epoch %r is not ISO 8601" % (CONFIG_REL, epoch_text))
    return str(block_at), epoch


# --------------------------------------------------------------------------- the report


def _row_lines(tag: str, r: Row, rel: str) -> list[str]:
    return [
        "  %s [%s] %s %s -- %s" % (tag, r.severity, r.id, r.where(), _clip(r.claim, CLAIM_CLIP)),
        "      Resolution: %s" % r.resolution,
        "      record: %s/%s" % (rel, r.file),
    ]


def report(branch: str, v: Verdict, reviewable: int | None, vacuous: bool) -> list[str]:
    """The lines printed for a verdict. Every refusal names the finding, the record and the next command."""
    rel = "%s/%s" % (REVIEWS_REL, branch_slug(branch))
    out: list[str] = []
    for r in v.deferred:
        out += _row_lines("DEFERRED", r, rel)
    if v.deferred:
        out += [
            "  A deferral is unfinished work (operator ruling 2026-10-08) and blocks the merge",
            "  at any severity. Per finding:",
            "    1. %s --triage <me> '<finding-id> <file>:<line>: <claim>'" % WORKLIST,
            "    2. INLINE or PLAN+SUBAGENT: fix it, commit, then",
            "       %s --review-mark <me> <finding-id> fixed <sha>" % WORKLIST,
            "    3. OPERATOR-ONLY: ask the operator, then",
            "       %s --review-mark <me> <finding-id> waived #<item> ASKED:<YYYY-MM-DDTHH:MM>Z"
            % WORKLIST,
            "    4. Or, when a re-read shows no defect:",
            "       %s --review-mark <me> <finding-id> not-a-bug <evidence>" % WORKLIST,
        ]
    for r in v.blocking:
        out += _row_lines("OPEN", r, rel)
    if v.blocking:
        out.append(
            "  An open finding at or above block_at blocks the merge: fix it and mark it "
            "`fixed <sha>`, or mark it `not-a-bug <evidence>`."
        )
    for r in v.unknown:
        out += _row_lines("UNREADABLE", r, rel)
    if v.unknown:
        out.append(
            "  A resolution outside the grammar (open | fixed | not-a-bug | waived) is not a "
            "resolution. Re-mark the finding with %s --review-mark; never hand-edit a record."
            % WORKLIST
        )
    out += ["  MALFORMED record %s/%s" % (rel, m) for m in v.malformed]
    if v.malformed:
        out.append(
            "  A record the parser cannot read may hide a finding. Re-run its review: "
            "%s --review-run <me> <sha>." % WORKLIST
        )
    if vacuous:
        out += [
            "  NO RECORDS in %s/ while the branch holds %d reviewable commit(s) since its"
            % (rel, reviewable or 0),
            "  merge-base. An empty directory reads exactly like a clean one, so it is refused:",
            "  the reviews were never recorded, never committed, or the directory name is wrong.",
            "  Commit the records (%s --review-commit <me>) or run the reviews" % WORKLIST,
            "  (%s --review-run <me>)." % WORKLIST,
        ]
    out += ["  WAIVED [%s] %s %s -- %s" % (r.severity, r.id, r.where(), r.head()) for r in v.waived]
    return out


def shape(branch: str, v: Verdict, reviewable: int | None) -> str:
    counts = ", ".join("%d %s" % (v.counts.get(k, 0), k) for k in (*KINDS, UNKNOWN))
    return (
        "branch %s: %d record(s), %d finding(s) (%s), %s reviewable commit(s) since merge-base"
        % (
            branch,
            v.records,
            v.findings,
            counts,
            "unknown" if reviewable is None else str(reviewable),
        )
    )


def step_summary(branch: str, v: Verdict, reviewable: int | None, ok: bool) -> str:
    """Markdown for `$GITHUB_STEP_SUMMARY`: the shape, every refusal and every waiver."""
    lines = [
        "### Review resolutions: `%s`" % branch,
        "",
        "%s: %s" % ("PASS" if ok else "FAIL", shape(branch, v, reviewable)),
        "",
    ]
    if v.refusals:
        lines += [
            "| Refusal | Finding | Severity | Location | Resolution |",
            "|---|---|---|---|---|",
        ]
        for tag, rows in (
            ("deferred", v.deferred),
            ("open", v.blocking),
            ("unreadable", v.unknown),
        ):
            lines += [
                "| %s | `%s` | %s | `%s` | %s |"
                % (tag, r.id, r.severity, r.where(), r.resolution.replace("|", "\\|"))
                for r in rows
            ]
        lines += ["| malformed | %s | | | |" % m.replace("|", "\\|") for m in v.malformed]
        lines.append("")
    if v.waived:
        lines += [
            "**Waivers (%d)**, each an operator ruling with its `ASKED:` minute:" % len(v.waived),
            "",
        ]
        lines += [
            "- `%s` [%s] `%s`: %s" % (r.id, r.severity, r.where(), r.head()) for r in v.waived
        ]
        lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- the run


def current_branch(root: pathlib.Path) -> str | None:
    rc, out = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    return (out.strip() or None) if rc == 0 else None


def run(root: pathlib.Path, env: Mapping[str, str]) -> int:
    """The verdict on the tree at `root`. Raises CannotRunError for exit 2."""
    rc, inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if rc != 0 or inside.strip() != "true":
        raise CannotRunError("%s is not a git work tree" % root)
    tgt = target(env, current_branch(root))
    if tgt.skip:
        print("review resolutions: %s" % tgt.skip)
        return 0
    block_at, epoch = load_config(root)
    branch = tgt.branch
    v = judge(review_table.load_records(root, branch), block_at)

    base_name = (env.get("GITHUB_BASE_REF") or "").strip() or "main"
    base = "origin/%s" % base_name
    commits = branch_commits(root, base)
    reviewable = None if commits is None else sum(1 for c in commits if is_reviewable(c, epoch))
    if commits is None and v.records == 0:
        raise CannotRunError(
            "%s does not resolve (or shares no merge-base with HEAD) and %s/%s/ holds no record, "
            "so whether the empty directory is vacuous cannot be measured. Fetch the base: "
            "git fetch origin %s" % (base, REVIEWS_REL, branch_slug(branch), base_name)
        )
    vacuous = v.records == 0 and bool(reviewable)
    ok = v.refusals == 0 and not vacuous

    print("review resolutions: block_at=%s, base=%s" % (block_at, base))
    for line in report(branch, v, reviewable, vacuous):
        print(line)
    summary_path = env.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(step_summary(branch, v, reviewable, ok))
    if ok:
        print("OK %s; %d waiver(s)" % (shape(branch, v, reviewable), len(v.waived)))
        return 0
    print(
        "FAIL %s; %d refusal(s)%s"
        % (
            shape(branch, v, reviewable),
            v.refusals,
            ", and the directory is vacuous" if vacuous else "",
        ),
        file=sys.stderr,
    )
    return 1


# --------------------------------------------------------------------------- the controls

_ME = "d778be9d"
_AT = "2026-10-08T09:00:00Z"
SELFTEST_RESOLUTIONS = (
    ("open", "open"),
    ("fixed %s | %s %s" % ("a" * 40, _ME, _AT), "fixed"),
    ("not-a-bug | the guard at a.py:3 already refuses it | %s %s" % (_ME, _AT), "not-a-bug"),
    ("not-a-bug | the existence oracle refuted the claim | oracle %s" % _AT, "not-a-bug"),
    ("waived #abcdef12 ASKED:2026-10-08T09:14Z | %s %s" % (_ME, _AT), "waived"),
    ("deferred #abcdef12 | %s %s" % (_ME, _AT), "deferred"),
    ("deferred #abcdef12", ""),
    ("waived #abcdef12 | %s %s" % (_ME, _AT), ""),
    ("fixed abc1234 | %s %s" % (_ME, _AT), ""),
    ("postponed #abcdef12 | %s %s" % (_ME, _AT), ""),
    ("not-a-bug | short | %s %s" % (_ME, _AT), ""),
)


def _finding(sev: str, res: str, n: int = 1) -> review_table.Finding:
    return review_table.Finding(
        id="abcdef01.%d" % n, severity=sev, path="a.py", line=n, claim="c", resolution=res
    )


def _record(*findings: review_table.Finding, problem: str = "") -> review_table.Record:
    return review_table.Record(
        sha="abcdef01" + "0" * 32, file="x.md", findings=list(findings), problem=problem
    )


def _fixture_repo(tmp: pathlib.Path) -> pathlib.Path:
    """A repo whose origin/main is one commit behind a branch with three commits: one reviewable, one review-only, one before the epoch."""
    repo = tmp / "repo"
    repo.mkdir()
    env = controls.fixture_git_env()
    env.update(
        {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }
    )

    def commit(rel: str, date: str) -> None:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel + date, encoding="utf-8")
        _git(repo, "add", "--", rel, env=env)
        _git(repo, "commit", "-q", "-m", rel, env={**env, "GIT_AUTHOR_DATE": date})

    _git(repo, "init", "-q", "-b", "main", env=env)
    commit("base.txt", "2026-10-01T00:00:00Z")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD", env=env)
    _git(repo, "checkout", "-q", "-b", "feat", env=env)
    commit("src/a.py", "2026-10-08T00:00:00Z")
    commit("agent/reviews/feat/x.md", "2026-10-08T00:01:00Z")
    commit("src/old.py", "2026-09-01T00:00:00Z")
    return repo


@controls.git_isolated
def selftest() -> int:
    """Both directions on every rule, plus the git walk rule iv depends on."""
    ctl = controls.Controls("review-resolutions", floor=37)

    for text, want in SELFTEST_RESOLUTIONS:
        ctl.check("grammar: %r" % text[:40], kind_of(text), want)

    def verdict(*findings: review_table.Finding, block_at: str = "high") -> Verdict:
        return judge([_record(*findings)], block_at)

    deferred = "deferred #abcdef12 | %s %s" % (_ME, _AT)
    fixed = "fixed %s | %s %s" % ("b" * 40, _ME, _AT)
    waived = "waived #abcdef12 ASKED:2026-10-08T09:14Z | %s %s" % (_ME, _AT)
    for sev in ("low", "medium", "high"):
        ctl.check(
            "rule i: a deferred %s refuses" % sev, len(verdict(_finding(sev, deferred)).deferred), 1
        )
        ctl.check(
            "rule i control: the same %s fixed is clean" % sev,
            verdict(_finding(sev, fixed)).refusals,
            0,
        )
    w = verdict(_finding("high", waived))
    ctl.check("a waiver is not a refusal", w.refusals, 0)
    ctl.check("a waiver is listed", [r.id for r in w.waived], ["abcdef01.1"])
    ctl.check(
        "rule ii: an open high refuses at block_at high",
        len(verdict(_finding("high", "open")).blocking),
        1,
    )
    ctl.check(
        "rule ii control: an open low is advisory at block_at high",
        verdict(_finding("low", "open")).refusals,
        0,
    )
    ctl.check(
        "rule ii: an open medium refuses at block_at medium",
        len(verdict(_finding("medium", "open"), block_at="medium").blocking),
        1,
    )
    ctl.check(
        "rule iii: an unknown resolution word refuses",
        len(verdict(_finding("low", "postponed #abcdef12 | %s %s" % (_ME, _AT))).unknown),
        1,
    )
    ctl.check(
        "rule iii: a malformed record refuses",
        len(judge([_record(problem="garbled")], "high").malformed),
        1,
    )
    ctl.check("an empty record set is zero records", judge([], "high").records, 0)

    ctl.check(
        "target: a head ref wins", target({"GITHUB_HEAD_REF": "1008-1"}, "main").branch, "1008-1"
    )
    ctl.raises(
        "target: pull_request with no head ref cannot run",
        CannotRunError,
        target,
        {"GITHUB_EVENT_NAME": "pull_request"},
        "1008-1",
    )
    ctl.truthy("target: main is not a PR branch", target({}, "main").skip)
    ctl.truthy("target: detached is not a PR branch", target({}, None).skip)
    ctl.check("target: a local branch is judged", target({}, "1008-1").branch, "1008-1")

    epoch = _parse_iso("2026-10-02T07:09:03Z")
    ctl.truthy(
        "reviewable: a source commit after the epoch",
        is_reviewable(Commit("s", "2026-10-08T00:00:00+03:00", ["a.py"]), epoch),
    )
    ctl.falsy(
        "reviewable: a review-only commit is not",
        is_reviewable(Commit("s", "2026-10-08T00:00:00Z", ["agent/reviews/b/x.md"]), epoch),
    )
    ctl.falsy(
        "reviewable: a commit before the epoch is not",
        is_reviewable(Commit("s", "2026-09-01T00:00:00Z", ["a.py"]), epoch),
    )
    ctl.falsy(
        "reviewable: an empty commit is not",
        is_reviewable(Commit("s", "2026-10-08T00:00:00Z", []), epoch),
    )

    with tempfile.TemporaryDirectory(prefix="review-resolutions-") as tmp:
        repo = _fixture_repo(pathlib.Path(tmp))
        commits = branch_commits(repo, "origin/main")
        ctl.check("git walk: three branch commits are read", len(commits or []), 3)
        ctl.check(
            "git walk: exactly one is reviewable",
            sum(1 for c in commits or [] if is_reviewable(c, epoch)),
            1,
        )
        ctl.check(
            "git walk: an absent base is None, never zero",
            branch_commits(repo, "origin/nope"),
            None,
        )

    return 0 if ctl.report() else 1


def main(argv: list[str], *, root: pathlib.Path, env: Mapping[str, str] | None = None) -> int:
    """`--selftest` runs the controls alone; otherwise the controls run first, then the verdict. `--root <dir>` judges another tree (the gate test's fixture repos)."""
    environ = os.environ if env is None else env
    if "--selftest" in argv:
        return selftest()
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            print("review resolutions: --root needs a directory", file=sys.stderr)
            return 2
        root = pathlib.Path(argv[i + 1])
    refused = controls.controls_first("review resolutions", selftest)
    if refused:
        return refused
    try:
        return run(root, environ)
    except CannotRunError as exc:
        print("review resolutions: CANNOT RUN (exit 2, not a verdict): %s" % exc, file=sys.stderr)
        return 2
