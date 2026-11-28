"""The `Release-Note:` trailer: its grammar, who owes it, and the notes a tag range collects.

ONE MODULE, FIVE READERS (agent/plans/PLAN-release-notes.md D2). The commit-msg hook (`.claude/rediacc_hooks/git/githooks.py`), the land check (`rediacc_ci.dev.worktree_lease`), the CI range gate, the Release body (`rediacc_ci.release.create_github_release`) and the changelog data all import this file, so a message the hook admits is a message the gate admits. The hook loads it by file, so the module
imports only the standard library at load; the prose-style rule set is imported on first use, with `.ci` put on `sys.path` for it.

THE GRAMMAR (D1). `Release-Note: <customer text>` or `Release-Note: none -- <reason>`, one per commit, in the message's trailer block. The text is one line of at most `max_length` characters that names what a customer sees, never a file, a plan, a worklist id, a gate or a codename, and it passes the prose-style rules of severity `error` in the `commit` scope (R1, R2, R8), the same rules `check_prose_style.py` applies. A `none` reason is at least `min_reason_length` characters, so a bare `none -- n/a` is refused.

WHO OWES IT (D2). A Conventional Commits `feat`, `fix` or `perf` subject (scope and `!` allowed) whose paths include at least one customer path: a path matching none of the repo's `internal` globs in `.ci/config/release-notes.json`, none of its gitlinks, and, in the console, no record glob of `.ci/policy/record-paths.json`. Every other commit is exempt; an exempt commit that carries a valid trailer anyway has its note collected, and one that carries an invalid trailer is refused, since a note that reaches a Release body is held to the grammar whatever the commit type.

COLLECTION (D3). `collect(start, end, root)` reads the console commits of `start..end`, then for each configured submodule the gitlink delta between the two trees and that submodule's own commits `old..new`. The console bump is exempt, so a submodule note is counted once, from the submodule commit. Notes are keyed by `(repo, sha)`, ordered by committer time across repos, and deduplicated by normalized text, so the same note landing as a console commit and a submodule commit appears once. `none` notes are counted, never shown.

THE TRAILER BLOCK IS READ THE WAY `git interpret-trailers --parse` READS IT, without starting git: the last paragraph is a trailer block when every line in it is a trailer, a continuation, or a git-generated line, or when its trailer lines are at least a third of its other lines and one of them is git-generated. The `(cherry picked from commit <sha>)` line `git cherry-pick -x` appends at land is git-generated, so a landed commit keeps its trailers. The test file drives both readers over the same messages.
"""

from __future__ import annotations

import dataclasses
import functools
import importlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
from typing import Any

KEY = "Release-Note"

_ROOT = pathlib.Path(__file__).resolve().parents[3]
CONFIG_REL = ".ci/config/release-notes.json"
CONSOLE = "console"

GROUP_ORDER = ("Added", "Fixed", "Improved")
EMPTY_LINE = "No customer-facing changes recorded in this range."

# Conventional Commits: `type(scope)!: subject`. Read leniently (any letter case, spaces around the scope and the colon) because a subject the strict form misses reads as outside the grammar and skips D2; the type is lowercased.
_SUBJECT = re.compile(
    r"^(?P<type>[A-Za-z]+)[ \t]*(?:\((?P<scope>[^()]*)\))?[ \t]*(?P<bang>!)?[ \t]*:[ \t]*\S"
)
# `git interpret-trailers` separators: `:` only (trailer.separators is unset in these repos). Token characters per git's `find_separator`: alphanumerics and `-`.
_TRAILER = re.compile(r"^(?P<key>[A-Za-z0-9][A-Za-z0-9-]*)[ \t]*:[ \t]?(?P<value>.*)$")
_SIGNED_OFF = "Signed-off-by: "
_GIT_GENERATED = (_SIGNED_OFF, "(cherry picked from commit ")
_NONE = re.compile(r"^none(?:\s*--\s*(?P<reason>.*))?$", re.IGNORECASE)
_BREAKING = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)
_SOURCE_EXTENSIONS = "astro|cjs|cts|go|json|jsonl|md|mjs|mts|py|rs|sh|sql|toml|ts|tsx|yaml|yml"
_BARE_FILE = re.compile(r"^[\w-]+(?:\.[\w-]+)*\.(?:%s)$" % _SOURCE_EXTENSIONS)
_PATH_EDGE = "()[]{}<>\"'`,;:!?"
# The variables that pin git to one repository. A collector started from a hook inherits GIT_DIR and GIT_INDEX_FILE, and `git -C <submodule>` would then read the console's objects.
_GIT_REPO_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_PREFIX",
)


class ReleaseNotesError(RuntimeError):
    """A collection that cannot be trusted: a missing object, a git failure, an unreadable config."""


# --------------------------------------------------------------------------- config


@functools.cache
def _load_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        msg = "release notes: cannot read %s: %s" % (path, exc)
        raise ReleaseNotesError(msg) from exc


def load_config() -> dict[str, Any]:
    """`.ci/config/release-notes.json` of the checkout this module lives in.

    THE POLICY COMES FROM THIS CHECKOUT, NEVER FROM THE TREE BEING READ. `collect` reads a git range at any `root` (a fixture, a submodule), and the rules it judges that range by are the ones this code ships with; a caller with other rules passes `config=`.
    """
    return _load_json(str(_ROOT / CONFIG_REL))


def _record_globs() -> tuple[tuple[str, tuple[str, ...]], ...]:
    doc = _load_json(str(_policy_paths().policy_path("record-paths.json", _ROOT)))
    return tuple((r["glob"], tuple(r.get("except") or ())) for r in doc.get("records") or ())


@functools.cache
def _glob_re(glob: str) -> re.Pattern[str]:
    """A glob of `**` and `*` only. `**/` spans zero or more directories, a trailing `**` one or more segments, `*` one segment."""
    out = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif glob.startswith("**", i):
            out.append(".+")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def glob_match(glob: str, path: str) -> bool:
    return _glob_re(glob).match(path) is not None


# --------------------------------------------------------------------------- grammar


@dataclasses.dataclass(frozen=True)
class Trailer:
    """One parsed `Release-Note:` value. `none` is True for the `none -- <reason>` form."""

    raw: str
    text: str
    none: bool
    reason: str
    multiline: bool


def trailers(msg: str) -> list[tuple[str, str, bool]]:
    """Every `(key, value, multiline)` of the message's trailer block, in order; `[]` when there is none.

    The subject paragraph is never a trailer block, as in git.
    """
    lines = msg.replace("\r\n", "\n").rstrip("\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    start = len(lines)
    while start > 0 and lines[start - 1].strip():
        start -= 1
    if start == 0:
        return []
    block = lines[start:]
    # git's `find_trailer_block_start`: a generated line counts as a trailer line, and a block with any other line still qualifies when it holds a generated line and `trailer_lines * 3 >= non_trailer_lines`.
    out: list[list[Any]] = []
    trailer_lines = 0
    non_trailer_lines = 0
    generated = False
    last_was_trailer = False
    for line in block:
        if line[:1] in (" ", "\t"):
            if last_was_trailer and out:
                out[-1][1] += " " + line.strip()
                out[-1][2] = True
            else:
                non_trailer_lines += 1
            continue
        if line.startswith(_GIT_GENERATED):
            generated = True
            trailer_lines += 1
            last_was_trailer = line.startswith(_SIGNED_OFF)
            if last_was_trailer:
                out.append(["Signed-off-by", line[len(_SIGNED_OFF) :].strip(), False])
            continue
        found = _TRAILER.match(line)
        last_was_trailer = bool(found)
        if found:
            trailer_lines += 1
            out.append([found.group("key"), found.group("value").strip(), False])
        else:
            non_trailer_lines += 1
    if not trailer_lines:
        return []
    if non_trailer_lines and not (generated and trailer_lines * 3 >= non_trailer_lines):
        return []
    return [(k, v, m) for k, v, m in out]


def parse(msg: str) -> list[Trailer]:
    """Every `Release-Note:` trailer in `msg` (the key matched case-insensitively, as git does)."""
    found = []
    for key, value, multiline in trailers(msg):
        if key.lower() != KEY.lower():
            continue
        none = _NONE.match(value)
        if none:
            found.append(Trailer(value, "", True, (none.group("reason") or "").strip(), multiline))
        else:
            found.append(Trailer(value, value, False, "", multiline))
    return found


@dataclasses.dataclass(frozen=True)
class Subject:
    type: str
    scope: str
    breaking: bool


def subject_of(subject: str) -> Subject | None:
    """The Conventional Commits head of a subject line, or None for a subject outside the grammar (a `Revert "..."`, a merge)."""
    found = _SUBJECT.match(subject.strip())
    if not found:
        return None
    return Subject(
        found.group("type").lower(), found.group("scope") or "", bool(found.group("bang"))
    )


def is_breaking(msg: str) -> bool:
    """A `!` in the subject or a `BREAKING CHANGE:` footer line (git reads the spaced key as no trailer, so the body is scanned)."""
    subject, _, body = msg.partition("\n")
    head = subject_of(subject)
    if head and head.breaking:
        return True
    return _BREAKING.search(body) is not None


def customer_paths(
    paths: list[str],
    repo: str,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """The paths of `paths` a customer sees, per D2. Empty for a repo outside the config."""
    config = config if config is not None else load_config()
    repo_cfg = (config.get("repos") or {}).get(repo)
    if repo_cfg is None:
        return []
    internal = tuple(repo_cfg.get("internal") or ())
    gitlinks = set(repo_cfg.get("gitlinks") or ())
    records = _record_globs() if repo == CONSOLE else ()
    out = []
    for raw in paths:
        path = raw.strip().removeprefix("./")
        if not path or path in gitlinks:
            continue
        if any(glob_match(g, path) for g in internal):
            continue
        if any(
            glob_match(g, path) and not any(glob_match(e, path) for e in excepts)
            for g, excepts in records
        ):
            continue
        out.append(path)
    return out


def required(
    subject: str,
    paths: list[str],
    repo: str,
    config: dict[str, Any] | None = None,
) -> bool:
    """True when a commit with this subject and these changed paths, in `repo`, owes a `Release-Note:` trailer."""
    config = config if config is not None else load_config()
    head = subject_of(subject)
    if head is None or head.type not in set(config.get("required_types") or ()):
        return False
    return bool(customer_paths(paths, repo, config))


def _looks_like_path(token: str) -> bool:
    token = token.strip(_PATH_EDGE).rstrip(".")
    if not token or "://" in token:
        return False
    if token.startswith(("./", "../", "~/", "/")) and len(token) > 1:
        return True
    if re.match(r"^\.[A-Za-z0-9_-]+/", token):
        return True
    if "/" in token:
        last = token.rsplit("/", 1)[1]
        if token.count("/") >= 2 or (last and _BARE_FILE.match(last)) or last.endswith(".js"):
            return True
    return bool(_BARE_FILE.match(token))


@functools.cache
def _compiled_patterns(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in patterns)


def internal_names(
    text: str,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """What `text` names that a customer note must not: file paths, plan or item ids, gate and hook names, codenames."""
    config = config if config is not None else load_config()
    hits = [
        token.strip(_PATH_EDGE).rstrip(".")
        for token in re.split(r"\s+", text)
        if _looks_like_path(token)
    ]
    for pattern in _compiled_patterns(tuple(config.get("internal_patterns") or ())):
        found = pattern.search(text)
        if found:
            hits.append(found.group(0))
    hits.extend(
        name
        for name in config.get("codenames") or ()
        if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(name), text, re.IGNORECASE)
    )
    return list(dict.fromkeys(hits))


def _ci_on_path() -> None:
    """Put `.ci` on `sys.path` through `rediacc_ci.paths.on_sys_path`, the canonical hop. The hook loads this file by file, with no package root, so `paths.py` (standard library only) is loaded by file path first."""
    spec = importlib.util.spec_from_file_location(
        "_rediacc_ci_paths", _ROOT / ".ci" / "rediacc_ci" / "paths.py"
    )
    if spec is None or spec.loader is None:
        msg = "cannot load .ci/rediacc_ci/paths.py"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.on_sys_path(_ROOT / ".ci")


@functools.cache
def _prose_style() -> Any:
    """`rediacc_ci.quality.prose_style`, imported on first use with `.ci` on `sys.path`: the hook loads this file by file, with no package root of its own."""
    _ci_on_path()
    return importlib.import_module("rediacc_ci.quality.prose_style")


@functools.cache
def _policy_paths() -> Any:
    """`rediacc_ci.policy_paths`, imported on first use with `.ci` on `sys.path`, for the same reason as `_prose_style`."""
    _ci_on_path()
    return importlib.import_module("rediacc_ci.policy_paths")


@functools.cache
def _well_known() -> Any:
    """`rediacc_ci.well_known`, imported on first use with `.ci` on `sys.path`, for the same reason as `_prose_style`."""
    _ci_on_path()
    return importlib.import_module("rediacc_ci.well_known")


@functools.cache
def _prose_rules(root: str) -> tuple[Any, Any]:
    return _prose_style().load_rules_file(root)


def prose_findings(text: str) -> list[str]:
    """`<rule id> <snippet>` for every error-severity prose-style rule the note breaks, through the rule set `check_prose_style.py` applies."""
    globals_, rules = _prose_rules(str(_ROOT))
    return [
        "%s %r" % (f.rule, f.snippet)
        for f in _prose_style().lint_message(text, rules, globals_, "commit")
        if f.severity == "error"
    ]


def note_problems(
    trailer: Trailer,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Why one trailer value is refused; `[]` when it is a valid note."""
    config = config if config is not None else load_config()
    problems = []
    if trailer.multiline:
        problems.append("the note is one line; a continuation line was found")
    if trailer.none:
        need = int(config.get("min_reason_length", 12))
        if len(trailer.reason) < need:
            problems.append(
                "`none` takes a reason of at least %d characters: `%s: none -- <reason>`"
                % (need, KEY)
            )
        return problems
    text = trailer.text
    limit = int(config.get("max_length", 200))
    if not text:
        problems.append("the note is empty")
        return problems
    if len(text) > limit:
        problems.append("the note is %d characters; the limit is %d" % (len(text), limit))
    names = internal_names(text, config)
    if names:
        problems.append(
            "the note names %s; a customer note says what a customer sees, never a file, plan, item, gate or codename"
            % ", ".join(repr(n) for n in names)
        )
    findings = prose_findings(text)
    if findings:
        problems.append("the note breaks the prose style (%s)" % "; ".join(findings))
    return problems


def refusal(
    msg: str,
    paths: list[str],
    repo: str,
    config: dict[str, Any] | None = None,
) -> str:
    """The phrase that refuses this commit message, or `""` when it is admitted.

    `paths` are the commit's changed paths relative to `repo`'s root, and `repo` is `console` or the submodule path (`private/account`, `private/renet`). The phrase names `Release-Note:` so a hook, the land check and the gate print the same reason.
    """
    config = config if config is not None else load_config()
    found = parse(msg)
    if len(found) > 1:
        return "carries %d `%s:` trailers; one per commit" % (len(found), KEY)
    if found:
        problems = note_problems(found[0], config)
        return "invalid `%s:` trailer: %s" % (KEY, "; ".join(problems)) if problems else ""
    subject = msg.split("\n", 1)[0]
    head = subject_of(subject)
    if head is None or not required(subject, paths, repo, config):
        return ""
    shown = customer_paths(paths, repo, config)
    listed = ", ".join(shown[:3]) + (" ..." if len(shown) > 3 else "")
    return (
        "a %s commit on a customer path (%s) needs a `%s: <customer text>` or `%s: none -- <reason>` trailer"
        % (
            head.type,
            listed,
            KEY,
            KEY,
        )
    )


# --------------------------------------------------------------------------- collection


@dataclasses.dataclass(frozen=True)
class CommitNote:
    """One commit of a collected range, with its verdict."""

    repo: str
    sha: str
    subject: str
    type: str
    breaking: bool
    time: int
    note: str
    none: bool
    refusal: str


@dataclasses.dataclass
class Collection:
    """What `collect` read: every commit with its verdict, the shown notes after dedup, and the skips it had to make."""

    commits: list[CommitNote]
    notes: list[CommitNote]
    none_count: int
    warnings: list[str]

    @property
    def offenders(self) -> list[CommitNote]:
        return [c for c in self.commits if c.refusal]


def _git(cwd: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_REPO_VARS}
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and proc.returncode != 0:
        msg = "release notes: `git %s` in %s exited %d: %s" % (
            " ".join(args),
            cwd,
            proc.returncode,
            proc.stderr.strip(),
        )
        raise ReleaseNotesError(msg)
    return proc


_REC = "\x1e"
_FLD = "\x1f"


def _commits(
    repo_root: pathlib.Path,
    rev_range: str,
    repo: str,
    config: dict[str, Any],
) -> list[CommitNote]:
    """Every non-merge commit of `rev_range` in the repository at `repo_root`, oldest first, with its verdict."""
    proc = _git(
        repo_root,
        "log",
        "--no-merges",
        "--reverse",
        "--no-renames",
        "--format=" + _REC + "%H" + _FLD + "%ct" + _FLD + "%B" + _FLD,
        "--name-only",
        rev_range,
    )
    out = []
    for record in proc.stdout.split(_REC)[1:]:
        sha, ctime, body, names = record.split(_FLD, 3)
        msg = body.strip("\n")
        paths = [p for p in names.split("\n") if p.strip()]
        subject = msg.split("\n", 1)[0]
        head = subject_of(subject)
        found = parse(msg)
        verdict = refusal(msg, paths, repo, config)
        note = found[0] if len(found) == 1 and not verdict else None
        out.append(
            CommitNote(
                repo=repo,
                sha=sha,
                subject=subject,
                type=head.type if head else "",
                breaking=is_breaking(msg),
                time=int(ctime or 0),
                note=note.text if note and not note.none else "",
                none=bool(note and note.none),
                refusal=verdict,
            )
        )
    return out


def _gitlink(root: pathlib.Path, ref: str, path: str) -> str | None:
    line = _git(root, "ls-tree", ref, "--", path).stdout.strip()
    meta = line.partition("\t")[0].split()
    if len(meta) != 3 or meta[1] != "commit":
        return None
    return meta[2]


def normalize(text: str) -> str:
    """The dedup key of a note: whitespace collapsed, a trailing period dropped, case folded."""
    return re.sub(r"\s+", " ", text).strip().rstrip(".").casefold()


def collect(
    start: str,
    end: str,
    root: os.PathLike[str] | str | None = None,
    config: dict[str, Any] | None = None,
) -> Collection:
    """The notes of `start..end` in the console at `root` and in each configured submodule's gitlink delta (D3).

    A submodule whose commits are not present locally raises, never reads as an empty range: a release body built from a shallow checkout would silently drop that repo's notes. A submodule added inside the range (no gitlink at `start`) is skipped with a warning, since its whole history is not a delta.
    """
    root = pathlib.Path(root or _ROOT)
    config = config if config is not None else load_config()
    repos = list(config.get("repos") or {})
    commits = _commits(root, "%s..%s" % (start, end), CONSOLE, config)
    warnings: list[str] = []
    for repo in repos:
        if repo == CONSOLE:
            continue
        old = _gitlink(root, start, repo)
        new = _gitlink(root, end, repo)
        if new is None or old == new:
            continue
        if old is None:
            warnings.append(
                "%s: no gitlink at %s; the submodule entered inside the range and its history is not collected"
                % (repo, start)
            )
            continue
        sub = root / repo
        if not sub.is_dir():
            msg = (
                "release notes: submodule %s is not checked out at %s; fetch it before collecting"
                % (
                    repo,
                    sub,
                )
            )
            raise ReleaseNotesError(msg)
        for sha in (old, new):
            if _git(sub, "cat-file", "-e", sha + "^{commit}", check=False).returncode != 0:
                msg = (
                    "release notes: %s commit %s is not present in %s; fetch the submodule before collecting"
                    % (
                        repo,
                        sha,
                        sub,
                    )
                )
                raise ReleaseNotesError(msg)
        commits.extend(_commits(sub, "%s..%s" % (old, new), repo, config))
    order = {repo: i for i, repo in enumerate([CONSOLE, *[r for r in repos if r != CONSOLE]])}
    commits.sort(key=lambda c: (c.time, order.get(c.repo, len(order))))
    seen: set[str] = set()
    notes = []
    none_count = 0
    for commit in commits:
        if commit.none:
            none_count += 1
            continue
        if not commit.note:
            continue
        key = normalize(commit.note)
        if key in seen:
            continue
        seen.add(key)
        notes.append(commit)
    return Collection(commits=commits, notes=notes, none_count=none_count, warnings=warnings)


# --------------------------------------------------------------------------- grouping and rendering


def group(
    notes: list[CommitNote],
    config: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """`{Added, Fixed, Improved}` per D4, notes in the order given; a breaking note is prefixed `Breaking:`.

    A note on an exempt type (D2 collects it) falls in `fallback_group`, since the three groups are the only ones a body or the page shows.
    """
    config = config if config is not None else load_config()
    mapping = config.get("groups") or {}
    fallback = config.get("fallback_group", "Improved")
    groups: dict[str, list[str]] = {name: [] for name in GROUP_ORDER}
    for note in notes:
        name = mapping.get(note.type, fallback)
        groups.setdefault(name, []).append(
            ("Breaking: " + note.note) if note.breaking else note.note
        )
    return groups


def document(
    version: str,
    start_tag: str,
    collection: Collection,
    *,
    orphans: list[str] | None = None,
    stable: str | None = None,
    repo: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The notes document of D8 (`cli/v<V>/release-notes.json`): what `render_markdown` and the changelog page read. `repo` defaults to the registry's console repository."""
    return {
        "version": version.removeprefix("v"),
        "start_tag": start_tag,
        "orphans": list(orphans or ()),
        "groups": group(collection.notes, config),
        "none_count": collection.none_count,
        "stable": stable.removeprefix("v") if stable else None,
        "repo": repo if repo is not None else _well_known().GH_REPO,
    }


def render_markdown(doc: dict[str, Any]) -> str:
    """The Release body of D6 from a notes document."""
    version = "v" + str(doc["version"]).removeprefix("v")
    groups = doc.get("groups") or {}
    names = [n for n in GROUP_ORDER if groups.get(n)] + [
        n for n in groups if n not in GROUP_ORDER and groups.get(n)
    ]
    parts = ["## %s\n\n%s" % (name, "\n".join("- " + n for n in groups[name])) for name in names]
    if not names:
        parts.append(EMPTY_LINE)
    orphans = list(doc.get("orphans") or ())
    if orphans:
        named = orphans[0] if len(orphans) == 1 else ", ".join(orphans[:-1]) + " and " + orphans[-1]
        verb, owner = ("was", "its") if len(orphans) == 1 else ("were", "their")
        parts.append(
            "%s %s tagged but not published; %s changes are listed here." % (named, verb, owner)
        )
    stable = doc.get("stable")
    if stable:
        parts.append(
            "Stable: v%s, marked Latest; this is an edge release." % str(stable).removeprefix("v")
        )
    repo = doc.get("repo")
    start = doc.get("start_tag")
    if repo and start:
        parts.append(
            "**Full Changelog**: %s/%s/compare/%s...%s"
            % (_well_known().GH_ORIGIN, repo, start, version)
        )
    return "\n\n".join(parts) + "\n"
