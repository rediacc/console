"""The per-commit review records, rendered as one table on the PR page (agent/plans/PLAN-github-pr-review-restore.md, "Showing the per-commit records on GitHub", box GR5).

WHAT IT SHOWS. Every commit on a branch gets one review record under `agent/reviews/<branch-slug>/`, written by `.claude/hooks/stop/wl_review.py`: a line of `clean.jsonl` for a clean full-coverage verdict (read through `clean_ledger`, linked as `clean.jsonl#L<n>`), a `<sha40>.md` file for every other verdict, and the `.md` wins for one sha. Nothing put those records on the PR page, so a reader on GitHub saw neither the findings nor how each was resolved. This module renders them: a header with the bump label `pr_labels.aggregate` computes and the commit that earned it, one row per console commit of
the PR, a section for submodule records, the PR commits with no record, the records whose commit is no longer in the PR (a rebase supersedes them), a collapsed details block per finding, and a link to the record directory at the head.

WHERE IT RUNS. A second step of Console CI's `pr-labels` job, which already checks out `agent/reviews`, holds `pull-requests: write`, runs once per green head and is exempt from job aggregation. No model call: the records are committed, and this only reads them.

ONE COMMENT, UPSERTED. The body starts `<!-- per-commit-reviews: <head40> -->`. The leading `<!--` is load-bearing: the Review Gate (`rediacc_ci.quality.review_comments.newest_summary`) skips a body that starts with it, so this table is never mistaken for a review summary that demands a reply. An earlier table is found by that marker and PATCHed in place, so the PR carries one table, not one per push. The same markdown goes to `$GITHUB_STEP_SUMMARY` when it is set.

ADVISORY END TO END. Every failure logs and the step exits 0: a display is never worth failing CI over, and a fork PR's read-only token must not red the job.

    PYTHONPATH=.ci python3 -m rediacc_ci.review.review_table      env: GH_TOKEN PR_NUMBER HEAD_REF HEAD_SHA GITHUB_REPOSITORY
    PYTHONPATH=.ci python3 -m rediacc_ci.review.review_table --render-only --branch <b>   prints the table from the local tree, no gh
"""

from __future__ import annotations

import collections
import contextlib
import dataclasses
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable

from rediacc_ci import log, paths
from rediacc_ci.core.gh_retry import retry_transient
from rediacc_ci.review import clean_ledger, pr_labels
from rediacc_ci.review.pr_labels import BUMP_LABEL, aggregate, branch_slug, read_failure
from rediacc_ci.well_known import GH_ORIGIN

MARKER_PREFIX = "<!-- per-commit-reviews:"
# GitHub refuses a comment body over 65,536 characters; the margin keeps the truncation notes inside it.
BODY_LIMIT = 65536
BODY_BUDGET = 65000
# `pulls/<n>/commits` returns at most 250 commits, paginated or not.
COMMITS_API_CAP = 250
CLAIM_CLIP = 300
REVIEWS_REL = "agent/reviews"
REVIEW_ONLY_SUBJECT = re.compile(r"^chore\(reviews\): record reviews\b")

# The record grammar, mirrored from `.claude/hooks/stop/wl_review.py` (`render` and `parse`). This parser is lenient where that one is strict: a record the reviewer would call malformed still gets a row here, marked as such, because hiding it would hide the problem from the one page a reader looks at.
TITLE_RE = re.compile(r"^# Review ([0-9a-f]{8}): ?(.*)$")
HEADER_RE = re.compile(r"^([A-Z][A-Za-z-]*): (.*)$")
FINDING_HEAD = re.compile(r"^### ([0-9a-f]{8})\.(\d+) \[(high|medium|low)\] (\S.*):(\d+)$")
DIFF_RE = re.compile(r"^(\d+) bytes, (\d+) files, truncated: (yes|no)$")
LABELS_RE = re.compile(r"^bump=(none|patch|minor|major) kind=([a-z,]+) why=(.*)$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
RESOLUTION_KINDS = ("fixed", "not-a-bug", "deferred", "open")
SEVERITIES = ("high", "medium", "low")

Runner = Callable[[list[str]], tuple[int, str]]


@dataclasses.dataclass
class Finding:
    id: str
    severity: str
    path: str
    line: int
    claim: str = ""
    resolution: str = "open"

    @property
    def resolution_kind(self) -> str:
        head = self.resolution.split(" ", 1)[0]
        return head if head in RESOLUTION_KINDS else "open"


@dataclasses.dataclass
class Record:
    sha: str
    subject: str = ""
    repo: str = "console"
    verdict: str = ""
    reviewed_at: str = ""
    diff_files: int = 0
    truncated: bool = False
    unreviewed: list[str] = dataclasses.field(default_factory=list)
    labels: str = "(none)"
    bump: str = ""
    findings: list[Finding] = dataclasses.field(default_factory=list)
    file: str = ""
    problem: str = ""
    # The 1-based line of `clean.jsonl` a ledger record came from; 0 for a `.md` record.
    line: int = 0

    @property
    def sha8(self) -> str:
        return self.sha[:8]


def parse_record(text: str, file: str = "") -> Record:
    """A `Record` from a review file's text. Never raises: a problem is recorded on the record and shown in its row."""
    lines = text.split("\n")
    rec = Record(sha="", file=file)
    m = TITLE_RE.match(lines[0]) if lines else None
    if m:
        rec.subject = m.group(2)
    else:
        rec.problem = "no `# Review <sha8>: <subject>` title"
    headers: dict[str, str] = {}
    i = 1
    while i < len(lines) and not lines[i].startswith("## "):
        h = HEADER_RE.match(lines[i])
        if h and h.group(1) not in headers:
            headers[h.group(1)] = h.group(2)
        i += 1
    rec.sha = headers.get("Commit", "")
    if not SHA40.match(rec.sha):
        stem = pathlib.Path(file).stem
        rec.sha = stem if SHA40.match(stem) else (m.group(1) if m else rec.sha)
        rec.problem = rec.problem or "no 40-hex `Commit:` header"
    rec.repo = headers.get("Repo", "console") or "console"
    rec.verdict = headers.get("Verdict", "") or "(none)"
    rec.reviewed_at = headers.get("Reviewed-At", "")
    d = DIFF_RE.match(headers.get("Diff", ""))
    if d:
        rec.diff_files = int(d.group(2))
        rec.truncated = d.group(3) == "yes"
    unreviewed = headers.get("Unreviewed", "(none)")
    rec.unreviewed = [] if unreviewed in ("", "(none)") else unreviewed.split(", ")
    rec.labels = headers.get("Labels", "(none)") or "(none)"
    lm = LABELS_RE.match(rec.labels)
    if lm:
        rec.bump = lm.group(1)
    current: Finding | None = None
    for line in lines[i:]:
        fh = FINDING_HEAD.match(line)
        if fh:
            current = Finding(
                id="%s.%s" % (fh.group(1), fh.group(2)),
                severity=fh.group(3),
                path=fh.group(4),
                line=int(fh.group(5)),
            )
            rec.findings.append(current)
        elif current is not None and line.startswith("Claim: "):
            current.claim = line[len("Claim: ") :]
        elif current is not None and line.startswith("Resolution: "):
            current.resolution = line[len("Resolution: ") :]
    return rec


def ledger_record(doc: dict) -> Record:
    """A `Record` from one `clean.jsonl` line. D1 makes it full coverage with no finding."""
    labels = clean_ledger.labels_text(doc)
    lm = LABELS_RE.match(labels)
    diff = doc.get("diff")
    files = diff.get("files") if isinstance(diff, dict) else None
    return Record(
        sha=doc["sha"],
        subject=str(doc.get("subject") or ""),
        repo=str(doc.get("repo") or "console"),
        verdict=doc["verdict"],
        reviewed_at=str(doc.get("reviewed_at") or ""),
        diff_files=files if isinstance(files, int) else 0,
        labels=labels,
        bump=lm.group(1) if lm else "",
        file=clean_ledger.NAME,
        line=int(doc["line"]),
    )


def load_records(root: pathlib.Path, branch: str) -> list[Record]:
    """Every `.md` record and each `clean.jsonl` line whose sha has no `.md` record, in sha order."""
    d = pathlib.Path(root) / REVIEWS_REL / branch_slug(branch)
    out: list[Record] = []
    for path in sorted(d.glob("*.md")) if d.is_dir() else []:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            out.append(Record(sha=path.stem, file=path.name, problem="unreadable: %s" % exc))
            continue
        out.append(parse_record(text, path.name))
    md_shas = {r.sha for r in out} | {pathlib.Path(r.file).stem for r in out}
    out.extend(
        ledger_record(doc)
        for doc in clean_ledger.read(d / clean_ledger.NAME)
        if doc["sha"] not in md_shas
    )
    # The order the `.md` files alone sorted in (by name, which is the sha), so moving a record into the ledger never changes which commit a header names.
    return sorted(out, key=lambda r: pathlib.Path(r.file).stem if r.file.endswith(".md") else r.sha)


@dataclasses.dataclass
class Commit:
    sha: str
    subject: str


@dataclasses.dataclass
class Context:
    branch: str
    head: str = ""
    repo: str = ""
    # None when the commit list could not be read (or was not asked for): every record then gets a row, and nothing is called missing or superseded.
    commits: list[Commit] | None = None


def _cell(text: str) -> str:
    return text.replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def _clip(text: str, cap: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= cap else text[: cap - 3].rstrip() + "..."


def record_url(ctx: Context, rec: Record) -> str:
    rel = "%s/%s/%s" % (REVIEWS_REL, branch_slug(ctx.branch), rec.file or rec.sha + ".md")
    anchor = "#L%d" % rec.line if rec.line else ""
    if ctx.repo and ctx.head:
        return "%s/%s/blob/%s/%s%s" % (GH_ORIGIN, ctx.repo, ctx.head, rel, anchor)
    return rel + anchor


def dir_url(ctx: Context) -> str:
    rel = "%s/%s" % (REVIEWS_REL, branch_slug(ctx.branch))
    if ctx.repo and ctx.head:
        return "%s/%s/tree/%s/%s" % (GH_ORIGIN, ctx.repo, ctx.head, rel)
    return rel


def severities(rec: Record) -> str:
    counts = collections.Counter(f.severity for f in rec.findings)
    return ", ".join("%d %s" % (counts[s], s) for s in SEVERITIES if counts[s]) or "-"


def resolutions(rec: Record) -> str:
    counts = collections.Counter(f.resolution_kind for f in rec.findings)
    return ", ".join("%s %d" % (k, counts[k]) for k in RESOLUTION_KINDS if counts[k]) or "-"


def coverage(rec: Record) -> str:
    if not rec.verdict.startswith(("findings", "clean")):
        return "-"
    if not rec.unreviewed and not rec.truncated:
        return "full"
    seen = max(rec.diff_files - len(rec.unreviewed), 0)
    return "%d/%d files" % (seen, rec.diff_files)


def labels_cell(rec: Record) -> str:
    m = LABELS_RE.match(rec.labels)
    return "bump=%s kind=%s" % (m.group(1), m.group(2)) if m else rec.labels


def verdict_cell(rec: Record) -> str:
    return rec.verdict + (" (malformed: %s)" % rec.problem if rec.problem else "")


def row(ctx: Context, rec: Record, subject: str = "") -> str:
    return "| [`%s`](%s) | %s | %s | %s | %s | %s | %s |" % (
        rec.sha8,
        record_url(ctx, rec),
        _cell(_clip(subject or rec.subject or "(no subject)", 100)),
        _cell(verdict_cell(rec)),
        severities(rec),
        resolutions(rec),
        _cell(labels_cell(rec)),
        coverage(rec),
    )


TABLE_HEAD = (
    "| Commit | Subject | Verdict | Findings | Resolutions | Labels | Coverage |",
    "|---|---|---|---|---|---|---|",
)


def bump_line(records: list[Record], branch_verdicts: list[dict]) -> str:
    """The bump as `pr_labels.aggregate` decides it, and the first commit whose verdict reaches it."""
    labels, _note = aggregate(branch_verdicts)
    if not branch_verdicts:
        return "Bump: no labelled verdicts, so no bump label."
    bump = next((b for b, lab in BUMP_LABEL.items() if lab and lab in labels), "patch")
    earner = next(
        (r for r in records if r.bump == bump and read_verdict_ok(r)),
        None,
    )
    label = BUMP_LABEL[bump] or "no bump label (patch, the release default)"
    where = ", earned by `%s` (%s)" % (earner.sha8, _clip(earner.subject, 80)) if earner else ""
    kinds = [lab for lab in labels if not lab.startswith("bump-")]
    tail = "; kind: %s" % ", ".join(kinds) if kinds else ""
    return "Bump: **%s**%s%s." % (label, where, tail)


def read_verdict_ok(rec: Record) -> bool:
    return rec.verdict in ("findings", "clean")


def details(rec: Record) -> str:
    items = [
        "- `%s` [%s] `%s:%d`: %s\n  Resolution: %s"
        % (
            f.id,
            f.severity,
            f.path,
            f.line,
            _clip(f.claim, CLAIM_CLIP) or "(no claim)",
            _clip(f.resolution, 200),
        )
        for f in rec.findings
    ]
    return "<details><summary><code>%s</code> %s: %d finding(s)</summary>\n\n%s\n\n</details>" % (
        rec.sha8,
        _cell(_clip(rec.subject, 80)),
        len(rec.findings),
        "\n".join(items),
    )


def _order(records: list[Record]) -> list[Record]:
    return sorted(records, key=lambda r: (r.reviewed_at, r.sha))


def render(ctx: Context, records: list[Record], branch_verdicts: list[dict] | None = None) -> str:
    """The comment body (marker first), held below BODY_LIMIT: details are cut first, then table rows."""
    if branch_verdicts is None:
        branch_verdicts = [v for v in (_verdict_of(r) for r in records) if v is not None]
    console = [r for r in records if r.repo == "console"]
    submodule = [r for r in records if r.repo != "console"]
    by_sha = {r.sha: r for r in console}
    rows: list[str] = []
    missing: list[str] = []
    superseded: list[Record] = []
    shown: list[Record] = []
    capped = ctx.commits is not None and len(ctx.commits) >= COMMITS_API_CAP
    if ctx.commits is None:
        for rec in _order(console):
            rows.append(row(ctx, rec))
            shown.append(rec)
    else:
        in_pr: set[str] = set()
        for c in ctx.commits:
            in_pr.add(c.sha)
            hit = by_sha.get(c.sha)
            if hit is not None:
                rows.append(row(ctx, hit, c.subject))
                shown.append(hit)
            elif REVIEW_ONLY_SUBJECT.match(c.subject):
                missing.append(
                    "- `%s` %s: review records only, not reviewed by design"
                    % (c.sha[:8], _cell(_clip(c.subject, 100)))
                )
            else:
                missing.append("- `%s` %s: no record" % (c.sha[:8], _cell(_clip(c.subject, 100))))
        if not capped:
            superseded = [r for r in _order(console) if r.sha not in in_pr]
    findings_total = sum(len(r.findings) for r in records)
    open_total = sum(1 for r in records for f in r.findings if f.resolution_kind == "open")
    head = [
        "%s %s -->" % (MARKER_PREFIX, ctx.head or "local"),
        "## Per-commit reviews: `%s`" % ctx.branch,
        "",
        bump_line(records, branch_verdicts),
        "",
        "%d record(s), %d finding(s), %d open. Records: [`%s/%s/`](%s)%s."
        % (
            len(records),
            findings_total,
            open_total,
            REVIEWS_REL,
            branch_slug(ctx.branch),
            dir_url(ctx),
            " at `%s`" % ctx.head[:8] if ctx.head else "",
        ),
    ]
    if capped:
        head += [
            "",
            "The PR has %d or more commits, the most `pulls/<n>/commits` returns: coverage is unknown past them, and no record is called superseded."
            % COMMITS_API_CAP,
        ]
    sections: list[str] = []
    if submodule:
        sections += ["", "### Submodule commits", "", *TABLE_HEAD]
        sections += [row(ctx, r) for r in _order(submodule)]
        shown += _order(submodule)
    if missing:
        sections += ["", "### PR commits with no record", "", *missing]
    if superseded:
        sections += ["", "### Superseded (rebased)", "", *TABLE_HEAD]
        sections += [row(ctx, r) for r in superseded]
    detail_blocks = [details(r) for r in shown + superseded if r.findings]
    return _fit(ctx, head, rows, sections, detail_blocks)


def _verdict_of(rec: Record) -> dict | None:
    if not read_verdict_ok(rec):
        return None
    m = LABELS_RE.match(rec.labels)
    if not m:
        return None
    kinds = [] if m.group(2) == "none" else m.group(2).split(",")
    return {"bump": m.group(1), "kind": kinds, "why": m.group(3)}


def _assemble(
    head: list[str], rows: list[str], sections: list[str], blocks: list[str], notes: list[str]
) -> str:
    parts = list(head)
    parts += ["", "### Console commits", "", *TABLE_HEAD, *rows] if rows else []
    parts += sections
    if blocks:
        parts += ["", "### Findings", ""] + [b + "\n" for b in blocks]
    parts += ["", *notes] if notes else []
    return "\n".join(parts).rstrip("\n") + "\n"


def _fit(
    ctx: Context, head: list[str], rows: list[str], sections: list[str], blocks: list[str]
) -> str:
    pointer = "Truncated to fit GitHub's comment limit; every record is under [`%s/%s/`](%s)." % (
        REVIEWS_REL,
        branch_slug(ctx.branch),
        dir_url(ctx),
    )
    body = _assemble(head, rows, sections, blocks, [])
    if len(body) <= BODY_BUDGET:
        return body
    keep = list(blocks)
    while keep:
        keep.pop()
        dropped = len(blocks) - len(keep)
        note = "%d finding block(s) omitted. %s" % (dropped, pointer)
        body = _assemble(head, rows, sections, keep, [note])
        if len(body) <= BODY_BUDGET:
            return body
    table = list(rows)
    secs = list(sections)
    while table or secs:
        if secs:
            secs.pop()
        else:
            table.pop()
        note = "Every finding block and %d table line(s) omitted. %s" % (
            len(rows) + len(sections) - len(table) - len(secs),
            pointer,
        )
        body = _assemble(head, table, secs, [], [note])
        if len(body) <= BODY_BUDGET:
            return body
    return body[: BODY_LIMIT - 1]


# --------------------------------------------------------------------------- gh and git


def _gh(args: list[str]) -> tuple[int, str]:
    """One gh call; (exit code, stdout without trailing newlines). On a nonzero exit the text is gh's stderr instead, which is what `read_failure` classifies and what a failed read's caller ignores."""
    try:
        proc = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    if proc.returncode != 0:
        return proc.returncode, (proc.stderr or "").rstrip("\n") or "failed"
    return 0, (proc.stdout or "").rstrip("\n")


_sleep = time.sleep


def _backoff(secs: float) -> None:
    _sleep(secs)


def _git(args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=30,
            cwd=str(paths.repo_root()),
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return proc.returncode, (proc.stdout or "").rstrip("\n")


def parse_commit_lines(text: str) -> list[Commit]:
    out = []
    for line in text.split("\n"):
        sha, _, subject = line.partition(" ")
        if SHA40.match(sha):
            out.append(Commit(sha, subject))
    return out


def pr_commits(repo: str, pr: str, gh: Runner) -> list[Commit] | None:
    rc, text = retry_transient(
        lambda: gh(
            [
                "api",
                "repos/%s/pulls/%s/commits" % (repo, pr),
                "--paginate",
                "--jq",
                '.[] | "\\(.sha) \\(.commit.message | split("\\n")[0])"',
            ]
        ),
        read_failure,
        sleep=_backoff,
    )
    if rc != 0:
        return None
    return parse_commit_lines(text)


def local_commits(branch: str, git: Runner = _git) -> list[Commit] | None:
    """`git log main..<branch>` oldest first, `HEAD` when the branch is the checked-out one; None when neither resolves."""
    rc, current = git(["rev-parse", "--abbrev-ref", "HEAD"])
    ref = "HEAD" if rc == 0 and current == branch else branch
    if git(["rev-parse", "--verify", "-q", ref])[0] != 0:
        return None
    rc, text = git(["log", "--reverse", "--format=%H %s", "main..%s" % ref])
    return parse_commit_lines(text) if rc == 0 else None


def upsert(repo: str, pr: str, body: str, gh: Runner) -> bool:
    """PATCH the comment carrying the marker, or POST a new one. True when the write succeeded."""
    rc, ids = retry_transient(
        lambda: gh(
            [
                "api",
                "repos/%s/issues/%s/comments" % (repo, pr),
                "--paginate",
                "--jq",
                '.[] | select(.body | startswith("%s")) | .id' % MARKER_PREFIX,
            ]
        ),
        read_failure,
        sleep=_backoff,
    )
    if rc != 0:
        log.warn("review_table: could not list the PR comments; not posting")
        return False
    existing = [x for x in ids.split("\n") if x.strip().isdigit()]
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(body)
        body_file = fh.name
    try:
        if existing:
            args = [
                "api",
                "-X",
                "PATCH",
                "repos/%s/issues/comments/%s" % (repo, existing[-1]),
                "-F",
                "body=@%s" % body_file,
            ]
        else:
            args = [
                "api",
                "-X",
                "POST",
                "repos/%s/issues/%s/comments" % (repo, pr),
                "-F",
                "body=@%s" % body_file,
            ]
        rc = gh(args)[0]
    finally:
        with contextlib.suppress(OSError):
            os.unlink(body_file)
    if rc != 0:
        log.warn("review_table: could not write the per-commit review comment")
        return False
    return True


def write_summary(env: dict[str, str], body: str) -> None:
    target = env.get("GITHUB_STEP_SUMMARY", "")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(body + "\n")
    except OSError as exc:
        log.warn("review_table: could not write the step summary (%s)" % exc)


def publish(env: dict[str, str], root: pathlib.Path, gh: Runner = _gh) -> int:
    """Render and post the table. Always 0."""
    pr = env.get("PR_NUMBER", "")
    head_ref = env.get("HEAD_REF", "")
    head_sha = env.get("HEAD_SHA", "")
    repo = env.get("GITHUB_REPOSITORY", "")
    if not (pr and head_ref and repo):
        log.warn(
            "review_table: PR_NUMBER, HEAD_REF and GITHUB_REPOSITORY are required; nothing posted"
        )
        return 0
    commits = pr_commits(repo, pr, gh)
    if commits is None:
        log.warn("review_table: could not read the PR's commits; every record gets a row")
    ctx = Context(branch=head_ref, head=head_sha, repo=repo, commits=commits)
    records = load_records(root, head_ref)
    body = render(ctx, records, branch_verdicts(root, head_ref))
    write_summary(env, body)
    if upsert(repo, pr, body, gh):
        log.info(
            "review_table: %d record(s) shown on PR %s (%d chars)" % (len(records), pr, len(body))
        )
    return 0


def branch_verdicts(root: pathlib.Path, branch: str) -> list[dict]:
    """`pr_labels.verdicts` itself, so the header names the bump the applier applies from one implementation."""
    return pr_labels.verdicts(root, branch)


def render_only(branch: str, root: pathlib.Path, git: Runner = _git) -> str:
    ctx = Context(branch=branch, commits=local_commits(branch, git))
    return render(ctx, load_records(root, branch), branch_verdicts(root, branch))


def _opt(argv: list[str], name: str) -> str:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return ""


USAGE = (
    "\n".join(
        line.strip() for line in (__doc__ or "").splitlines() if line.startswith("    PYTHONPATH=")
    )
    + "\n"
)
FLAGS = {"--render-only", "--branch"}


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    if "--help" in argv or "-h" in argv:
        sys.stdout.write(USAGE)
        return 0
    # A branch name never starts with "-" (git refuses one), so every such argument outside FLAGS is unknown, `--branch`'s value included.
    unknown = [a for a in argv if a.startswith("-") and a not in FLAGS]
    if unknown:
        sys.stderr.write("review_table: unknown option %s\n%s" % (", ".join(unknown), USAGE))
        return 2
    try:
        if "--render-only" in argv:
            branch = _opt(argv, "--branch") or _git(["rev-parse", "--abbrev-ref", "HEAD"])[1]
            sys.stdout.write(render_only(branch, paths.repo_root()))
            return 0
        return publish(dict(os.environ), paths.repo_root())
    except Exception as exc:  # noqa: BLE001 -- advisory: the table never fails CI
        log.warn("review_table failed (%s: %s); nothing more posted" % (type(exc).__name__, exc))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
