"""What may sit at the repository root and under `agent/`. The library half.

THE RULE IS DATA. Every permitted name, pattern and directory lives in `.ci/policy/tree-shape.json`, which carries the argument for each one; this module only reads it. The gate is `.ci/scripts/quality/check_tree_shape.py`.

EIGHT FINDINGS:

    T1  a depth-1 file at the repository root in no permitted class
    T2  a depth-1 directory at the repository root in no permitted class
    T3  a file directly under agent/ in no permitted class
    T4  a directory under agent/ that is neither reserved nor a session slug
    T5  the policy's agent_dirs and wl_store.AGENT_RESERVED_DIRS disagree
    T6  a module building a repository path out of a bare relative string
    T7  the enumeration lost the tree
    T8  a baseline entry that no longer fires

T5 IS THE DERIVATION, AND IT IS THE REASON THIS GATE IS NOT A SECOND LIST. `wl_store.AGENT_RESERVED_DIRS` already decides which directories under `agent/` are not sessions, and `agent_session_dirs` treats every other one as a peer session. Copying that set here would make two answers to one question, and the first symptom of them drifting is a stop report naming a session
that does not exist -- which had already happened for `pr` and `legacy` when this landed. So the two are compared as SETS, in both directions, and a disagreement is a finding rather than a preference for whichever list the reader happens to open.

T6 IS THE CLASS BEHIND BOTH DEFECTS THAT PROMPTED THIS GATE. `wl_reggate.debt_dir()` fell back to a cwd-relative root and wrote a second ledger under `.claude/hooks/stop/agent/`; `standing_orders_brief` built `pathlib.Path("agent")` and reported `0 plan file(s)` whenever it ran from anywhere but the repository root. Neither is a typo, both are the same mistake, and the
detector is derived rather than typed: a string literal is a finding only when its FIRST path segment is one of the repository's own top-level directory names, which come from git.

THE BASELINE IS SHRINK-ONLY AS A SET, and the decision is `rediacc_ci.quality.shrink_only`, shared rather than copied. Today's tree has no strays at either location, so the baseline exists to hold whatever the scan finds that a reader decides to keep, and its emptiness is not something to rely on.

WHAT A GREEN HERE DOES NOT MEAN. It says nothing about the CONTENT of any file, nothing about trees outside the root and `agent/`, and nothing about a file that is gitignored: `--exclude-standard` is deliberate, because an ignored build artefact is not a stray, it is output.
"""

import ast
import dataclasses
import json
import os
import pathlib
import re

from rediacc_ci import gitx, paths, policy_paths

POLICY_NAME = "tree-shape.json"
BASELINE_REL = ".ci/config/tree-shape-baseline.json"
BASELINE_LABEL = BASELINE_REL
ROOT_ENV = "TREE_SHAPE_ROOT"

AGENT_DIR = "agent"

#: Floors under the enumeration. Both are well below the measured tree (29 root files, 16 root directories, 109 files directly under `agent/` on 2026-09-21): they guard against the enumeration losing the tree, not against ordinary housekeeping. A count of zero is the shape this gate exists to refuse, because zero strays and zero files read identically.
MIN_ROOT_FILES = int(os.environ.get("TREE_SHAPE_MIN_ROOT", "10"))
MIN_AGENT_ENTRIES = int(os.environ.get("TREE_SHAPE_MIN_AGENT", "10"))
#: A floor on the TOP-LEVEL DIRECTORY count as well, because that half has its own way of going vacuous: a pathspec narrow enough to admit only root files yields exactly one directory name, and T2 then cannot fire while everything else still reports.
MIN_ROOT_DIRS = int(os.environ.get("TREE_SHAPE_MIN_ROOT_DIRS", "5"))


@dataclasses.dataclass(frozen=True)
class Finding:
    """One defect. The CODE is what a control asserts on, the message is prose."""

    code: str
    path: str
    message: str


# --------------------------------------------------------------------------- Reading the policy.


def policy_path(root: pathlib.Path | None = None) -> pathlib.Path:
    return policy_paths.policy_path(POLICY_NAME, root=root)


def load_policy(root: pathlib.Path) -> dict:
    return json.loads(policy_path(root).read_text(encoding="utf-8"))


def _patterns(section: dict) -> list[re.Pattern[str]]:
    return [re.compile(entry["regex"]) for entry in section.get("patterns") or []]


def policy_agent_dirs(policy: dict) -> set[str]:
    return {entry["name"] for entry in policy["agent_dirs"]["classes"]}


# --------------------------------------------------------------------------- The pure core: classification.


def split_entries(paths_in: list[str]) -> tuple[set[str], set[str], set[str], set[str]]:
    """(root files, root dirs, agent files, agent dirs) from a flat path list.

    A DIRECTORY IS INFERRED, never stat'ed. git lists blobs, so the only evidence a directory exists is a path with a separator in it -- which is exactly the evidence this gate wants, because an empty directory git cannot see is not a shape anybody can commit.
    """
    root_files: set[str] = set()
    root_dirs: set[str] = set()
    agent_files: set[str] = set()
    agent_dirs: set[str] = set()
    for rel in paths_in:
        if not rel:
            continue
        parts = rel.split("/")
        if len(parts) == 1:
            root_files.add(parts[0])
            continue
        root_dirs.add(parts[0])
        if parts[0] != AGENT_DIR:
            continue
        if len(parts) == 2:
            agent_files.add(parts[1])
        else:
            agent_dirs.add(parts[1])
    return root_files, root_dirs, agent_files, agent_dirs


def finding_t1(root_files: set[str], policy: dict) -> list[Finding]:
    permitted = set(policy["root_files"]["names"])
    return [
        Finding(
            "T1",
            name,
            "%s sits at the repository root and is in no permitted class. A file here "
            "reaches nobody's eye until something enumerates it, which is how the old "
            "bash worklist suites left debris nobody noticed for weeks. Add a line to "
            "%s with the reason, or move it under the tree that owns it."
            % (name, policy_paths.policy_rel(POLICY_NAME)),
        )
        for name in sorted(root_files - permitted)
    ]


def finding_t2(root_dirs: set[str], policy: dict) -> list[Finding]:
    permitted = set(policy["root_dirs"]["names"])
    return [
        Finding(
            "T2",
            name,
            "%s/ is a new top-level directory and is in no permitted class. A top-level "
            "directory is a new concept in this repository, so it is worth a line in %s "
            "saying what it holds." % (name, policy_paths.policy_rel(POLICY_NAME)),
        )
        for name in sorted(root_dirs - permitted)
    ]


def finding_t3(agent_files: set[str], policy: dict) -> list[Finding]:
    section = policy["agent_files"]
    names = set(section["names"])
    patterns = _patterns(section)
    out = []
    for name in sorted(agent_files - names):
        if any(rx.match(name) for rx in patterns):
            continue
        out.append(
            Finding(
                "T3",
                "%s/%s" % (AGENT_DIR, name),
                "%s/%s is in no permitted class. Everything under agent/ is per-session "
                "state, a durable plan, or a named ledger; a loose file there belongs in "
                "one of those or in nothing at all." % (AGENT_DIR, name),
            )
        )
    return out


def finding_t4(agent_dirs: set[str], policy: dict, reserved: set[str]) -> list[Finding]:
    session_rx = re.compile(policy["agent_session_dirs"]["regex"])
    return [
        Finding(
            "T4",
            "%s/%s" % (AGENT_DIR, name),
            "%s/%s is neither a reserved directory nor a session slug. wl_store."
            "agent_session_dirs treats every non-reserved directory under agent/ as a "
            "peer session, so a directory that is not one is reported to every session "
            "as a peer that does not exist." % (AGENT_DIR, name),
        )
        for name in sorted(agent_dirs - reserved)
        if not session_rx.match(name)
    ]


def finding_t5(policy: dict, reserved: set[str]) -> list[Finding]:
    """T5. The policy and the hook must name the same reserved directories."""
    declared = policy_agent_dirs(policy)
    rel = policy_paths.policy_rel(POLICY_NAME)
    out = [
        Finding(
            "T5",
            name,
            "%s is a reserved agent directory in %s but not in wl_store."
            "AGENT_RESERVED_DIRS. The hook will report it to every session as a peer "
            "session that does not exist." % (name, rel),
        )
        for name in sorted(declared - reserved)
    ]
    out.extend(
        Finding(
            "T5",
            name,
            "%s is reserved in wl_store.AGENT_RESERVED_DIRS and has no class in %s. The "
            "two lists are one decision and this gate derives from the hook rather than "
            "copying it, so the missing half is here." % (name, rel),
        )
        for name in sorted(reserved - declared)
    )
    return out


def finding_t7(
    root_files: set[str], agent_entries: int, root_dirs: int = MIN_ROOT_DIRS
) -> list[Finding]:
    out = []
    if root_dirs < MIN_ROOT_DIRS:
        out.append(
            Finding(
                "T7",
                "",
                "VACUOUS INPUT: %d top-level director(ies), floor is %d. A pathspec narrow "
                "enough to yield this many admits only root files, and T2 could not fire."
                % (root_dirs, MIN_ROOT_DIRS),
            )
        )
    if len(root_files) < MIN_ROOT_FILES:
        out.append(
            Finding(
                "T7",
                "",
                "VACUOUS INPUT: %d file(s) at the repository root, floor is %d. The "
                "enumeration lost the tree; refusing a verdict rather than reporting a "
                "clean shape for files nobody listed." % (len(root_files), MIN_ROOT_FILES),
            )
        )
    if agent_entries < MIN_AGENT_ENTRIES:
        out.append(
            Finding(
                "T7",
                "",
                "VACUOUS INPUT: %d entr(ies) under %s/, floor is %d. The enumeration lost "
                "the tree." % (agent_entries, AGENT_DIR, MIN_AGENT_ENTRIES),
            )
        )
    return out


def finding_t8(baseline: list[str], live: set[str]) -> list[Finding]:
    """T8. A baselined stray that no longer fires.

    The baseline is shrink-only, so an entry left in it after the fix hides the next regression at that path. Reported rather than silently dropped, because dropping it is a write and this gate does not write on a check run.
    """
    return [
        Finding(
            "T8",
            entry,
            "%s is in %s but no longer fires. The baseline is SHRINK-ONLY, and an entry "
            "left in it after the fix hides the next regression at that path. Drain it: "
            "check_tree_shape.py --write-baseline" % (entry, BASELINE_LABEL),
        )
        for entry in sorted(set(baseline) - live)
    ]


# --------------------------------------------------------------------------- T6: a repository path built from a bare relative string.


def _callee_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _callee_name(node.value)
        return "%s.%s" % (prefix, node.attr) if prefix else node.attr
    return ""


def _literal_first_arg(
    node: ast.AST, callees: set[str], top_names: set[str]
) -> tuple[int, str] | None:
    """(lineno, literal) when `node` is a call building a repo path from a string.

    THE TEST IS THE FIRST PATH SEGMENT, and the segment set comes from git rather than from a literal in this file. `pathlib.Path(".")` is therefore not a finding, nor is `open("node_modules")`: neither names a tracked top-level directory, and both have legitimate uses where the caller has already chosen its own directory. An absolute literal is somebody else's filesystem and a
    `../` one is a deliberate hop, so both are skipped; the class this catches reads as correct at the repository root and answers somewhere else anywhere else.
    """
    if not isinstance(node, ast.Call) or not node.args:
        return None
    if _callee_name(node.func) not in callees:
        return None
    first = node.args[0]
    if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
        return None
    literal = first.value
    if not literal or literal.startswith(("/", "../")):
        return None
    if literal.split("/", 1)[0] not in top_names:
        return None
    return first.lineno, literal


def bare_relative_sites(
    source: str,
    rel: str,
    top_names: set[str],
    callees: set[str],
    fs_methods: set[str] | None = None,
) -> list[tuple[int, str]]:
    """[(lineno, literal)] for every repository path REACHED from a bare string.

    REACHED, not merely built, and the distinction is the whole precision of this rule. `pathlib.Path(".ci") / "lib" / "setup.sh"` assigned to a constant that every caller writes as `root / TWIN` is the CORRECT pattern: a relative constant joined to a root it was given. `pathlib.Path("agent").is_dir()` is the defect, because the answer is the caller's working directory. Measured
    on this tree 2026-09-21, a rule that flagged construction alone produced eleven findings and every one of them was the correct pattern.

    So a `Path(...)` literal is a finding only when a filesystem METHOD is called on it in the same expression, while `open`, `os.listdir` and `os.scandir` are findings on sight because they touch the filesystem themselves.

    WHAT IT CANNOT SEE, said out loud: a literal handed to a variable and opened three lines later. Following that would need dataflow, and a rule that half-follows it would report the easy half while implying it had checked both.
    """
    methods = fs_methods or set()
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        direct = _literal_first_arg(node, callees, top_names)
        if direct is not None:
            out.append(direct)
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in methods:
            reached = _literal_first_arg(func.value, {"Path", "pathlib.Path"}, top_names)
            if reached is not None:
                out.append(reached)
    return sorted(set(out))


def finding_t6(sites: list[tuple[str, int, str]]) -> list[Finding]:
    return [
        Finding(
            "T6",
            "%s:%d" % (rel, line),
            "%s:%d builds %r out of a bare relative string, so it answers the CALLER's "
            "working directory rather than the tree. Resolve it from the package instead: "
            "`paths.from_root(...)` under .ci, or the `root` a hook function was already "
            "handed." % (rel, line, literal),
        )
        for rel, line, literal in sites
    ]


# --------------------------------------------------------------------------- The impure half.


def repo_root() -> pathlib.Path:
    override = os.environ.get(ROOT_ENV)
    return pathlib.Path(override) if override else paths.repo_root()


def enumerate_tree(root: pathlib.Path, *pathspecs: str) -> tuple[list[str], str]:
    """Tracked plus untracked-not-ignored paths, and "" when git answered cleanly.

    THE EXIT STATUS IS KEPT, which is why this does not call `gitx.ls_files`: that helper returns `[]` on a non-zero git, and a caller reads an empty list as "nothing there". For a gate whose whole subject is what is there, a swallowed enumeration is indistinguishable from a clean tree.
    """
    args = ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    if pathspecs:
        args.append("--")
        args.extend(pathspecs)
    result = gitx.git(args, root=root)
    if not result.ok:
        return [], "git ls-files failed under %s: %s" % (root, result.stderr.strip() or "no stderr")
    return sorted({p for p in result.stdout.split("\0") if p}), ""


def top_level_names(paths_in: list[str]) -> set[str]:
    """The repository's own top-level directory names, from the enumeration."""
    return {rel.split("/", 1)[0] for rel in paths_in if "/" in rel}


def scan_bare_relative(
    root: pathlib.Path, policy: dict, paths_in: list[str]
) -> list[tuple[str, int, str]]:
    section = policy["bare_relative_scan"]
    prefixes = tuple(section["dirs"])
    callees = set(section["callees"])
    methods = set(section["fs_methods"])
    names = top_level_names(paths_in)
    out = []
    for rel in paths_in:
        if not rel.endswith(".py") or not rel.startswith(prefixes):
            continue
        try:
            source = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.extend(
            (rel, line, literal)
            for line, literal in bare_relative_sites(source, rel, names, callees, methods)
        )
    return out


def read_baseline(path: pathlib.Path) -> list[str] | None:
    """The frozen set, or None when the file is absent, which is STRICT MODE."""
    if not path.is_file():
        return None
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("strays") or [])
    except (OSError, ValueError, AttributeError):
        return None


def render_refusal(verdict: str, added: list[str], previous: int, current: int) -> str:
    """The `--write-baseline` refusal, in this gate's own words.

    The DECISION is shared (`shrink_only.write_verdict`); the sentence is not, because the noun and the remedy differ per gate and a message that named neither would be worse than two that each name one.
    """
    if verdict == "missing-baseline":
        return (
            "Refusing to write the baseline: %s does not exist.\n"
            "  With no previous baseline there is nothing to compare against, so all %d "
            "path(s)\n  would be recorded as permitted with no check on what is among "
            "them, and DELETING\n  the file is therefore the cheapest way to defeat this "
            "rule. If this really is a\n  first seed, say so: --write-baseline "
            "--first-seed." % (BASELINE_LABEL, current)
        )
    return (
        "Refusing to write the baseline: it would GAIN %d entr(ies) not in the current "
        "one.\n%s\n\n"
        "  The baseline shrinks. It never grows. A reseed that drains thirty and adds one "
        "still\n  LOOKS like progress in the totals (%d -> %d), which is exactly how a "
        "brand new stray\n  gets enshrined as permanent, invisible debt.\n\n"
        "  Delete the file, or give it a class in %s."
        % (
            len(added),
            "\n".join("    %s" % a for a in added),
            previous,
            current,
            policy_paths.policy_rel(POLICY_NAME),
        )
    )


def findings(
    paths_in: list[str],
    *,
    policy: dict,
    reserved: set[str],
    bare_sites: list[tuple[str, int, str]],
    baseline: list[str] | None,
) -> list[Finding]:
    """Every finding, in code order, with the baseline applied as a SET.

    T5 and T7 are never baselined. T7 is the refusal to judge at all, and T5 is a disagreement between two lists rather than a stray file: freezing either would be freezing the instrument rather than the debt.
    """
    root_files, root_dirs, agent_files, agent_dirs = split_entries(paths_in)
    vacuous = finding_t7(root_files, len(agent_files) + len(agent_dirs), len(root_dirs))
    if vacuous:
        return vacuous
    live = [
        *finding_t1(root_files, policy),
        *finding_t2(root_dirs, policy),
        *finding_t3(agent_files, policy),
        *finding_t4(agent_dirs, policy, reserved),
        *finding_t6(bare_sites),
    ]
    frozen = set(baseline or [])
    kept = [f for f in live if f.path not in frozen]
    kept.extend(finding_t5(policy, reserved))
    kept.extend(finding_t8(baseline or [], {f.path for f in live}))
    return kept


def live_entries(
    paths_in: list[str],
    *,
    policy: dict,
    reserved: set[str],
    bare_sites: list[tuple[str, int, str]],
) -> list[str]:
    """Every baselinable finding's path, ignoring the baseline. The seed set."""
    return [
        f.path
        for f in findings(
            paths_in, policy=policy, reserved=reserved, bare_sites=bare_sites, baseline=[]
        )
        if f.code in ("T1", "T2", "T3", "T4", "T6")
    ]


__all__ = [
    "BASELINE_REL",
    "Finding",
    "bare_relative_sites",
    "enumerate_tree",
    "finding_t1",
    "finding_t2",
    "finding_t3",
    "finding_t4",
    "finding_t5",
    "finding_t6",
    "finding_t7",
    "finding_t8",
    "findings",
    "live_entries",
    "load_policy",
    "policy_agent_dirs",
    "read_baseline",
    "render_refusal",
    "repo_root",
    "scan_bare_relative",
    "split_entries",
    "top_level_names",
]
