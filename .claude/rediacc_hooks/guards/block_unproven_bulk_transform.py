"""block_unproven_bulk_transform: the proof obligation, at the three points a change leaves the tree.

WHY THIS EXISTS.
`wl_proofcheck.py` asks the stop judge whether a bulk mechanical transform proved it did not destroy structure it does not know about. That question rides an LLM call, which is right for a nuanced judgement and wrong for every commit -- a synchronous judge call on `git commit` would make every commit pay for a model round trip.
This guard is the operator's ruling that the SAME demand also lands here, on a cheap, deterministic, staged-scoped check: does a large enough change carry a quoted proof in its own message.
It cannot judge WHETHER a transform is mechanical the way the LLM can and judges SCALE instead, which is the plan's own principle -- batch size scales with proof, not ambition -- applied literally: a diff above the threshold must show proof, regardless of what produced it.

THREE SURFACES, ONE RULE. `git commit` checks the STAGED diff against the message being written. `git push` and `gh pr create` check every commit in the range about to leave the tree, because either one can carry a bulk commit this guard never saw at commit time -- an operator `!`-bypassed commit, a peer's commit merged in, or a commit made before this guard existed.
ONE RULE IS ONE FUNCTION, `_bulk_unproven`, over ONE way of counting, `_name_only` (renames as a delete plus an add). 3a5f3a188 (28 files, no proof) was allowed at commit and refused at push on 2026-09-26: its command ran `node scripts/generate-search-index.js` BEFORE `git commit -- ... packages/www`, and this guard, which runs once before the first clause, counted the 14 files that generator had not yet written as unchanged. See `_earlier_writers`, and `_staged_by_command` for the same timing on an index commit whose own command runs `git add` first.

OWN_SUITE = True, the same sentinel and for the same reason as `block_prose_style_commit`/`block_prose_style_edit`: this is a fresh guard authored directly, with no bash original to port from and no golden to compare against. `test-block_unproven_bulk_transform.py` stands in for that differential, exactly as it does for its siblings.

WHAT COUNTS AS PROOF, kept identical to the standard `wl_proofcheck.PROOF_PROMPT` holds the judge to: a shape-cluster diff, an AST-equality or AST-diff statement, a byte-identity claim, or an explicit statement that files were sampled and read which names the files or how many (`MANUAL_CLAIM`, in the same paragraph or list item as a count or a file name).
A bare file count or diff stat does NOT count -- "884 files changed" is exactly the assertion that shipped alongside a real incident this rule exists for.

THE THRESHOLD IS A SCALE PROXY, NOT A MECHANISM DETECTOR. This guard cannot tell a hand-written 25-file fix from a script applied to 25 files; it does not try to. Above the threshold, EITHER shape must show proof, because the plan's own principle is that scale itself is the risk this proof obligation answers to.

FAILS OPEN ON AN UNRESOLVABLE RANGE, on the same reasoning `messages()`'s `-F <unreadable path>` arm already uses: a range this guard cannot compute is UNEXAMINED, not a finding. A branch with no upstream, or a push whose target this guard cannot resolve, is allowed rather than guessed at.
"""

import glob
import json
import os
import pathlib
import re
import shlex
import subprocess

from rediacc_hooks import commit_policy, hookio, shellscan
from rediacc_hooks.guards import block_prose_style_commit as PSC
from rediacc_hooks.guards import block_unverified_push as PUSH

CHAIN = "pre-bash"
OWN_SUITE = True
# Re-keyed from 41 to 42 on 2026-09-22 by the insertion of block_push_to_protected_branch.py at 39.
ORDER = 41

# The one branch the differential must be able to see: a commit at bulk scale whose own message quotes no proof. Planting `if False:` there lets every such commit through, which is the whole failure this guard exists to refuse.
DEFECT = (
    "if _bulk_unproven(files, _commit_message_text(cmd, cwd)):",
    "if False:",
)

# Measured nowhere yet, chosen rather than derived: 20 files is comfortably above an ordinary multi-file hand fix (this session's own hand-written fixes touched 1-8 files) and comfortably below the smallest bulk transform this branch actually produced (884, then 221, then 6).
# A threshold this far from both boundaries costs false positives only if a future hand-written fix genuinely spans 20+ files, which is itself worth a moment's proof.
BULK_FILE_THRESHOLD = int(os.environ.get("WORKLIST_BULK_FILE_THRESHOLD", "20"))

# A push or PR range check walks every commit in the range; this is the ceiling on how many are inspected before the guard gives up and allows rather than spending unbounded subprocess time on a rebase or a stacked branch.
RANGE_COMMIT_CAP = 200

# The `-- <path>...` tail `block_pathspecless_git_commit.py` requires on every commit here. Its own `DDASH_PATHSPEC` only has to PROVE one is present, so it stops at the first character of the first path; this one has to capture the whole list, and stops at a clause or redirection boundary so a `--` in one clause cannot claim the next clause's words.
# A word made only of digits and followed by `<`/`>` is a file descriptor (`2>&1`), not a path: `-- a b 2>&1` once captured `2` as a third pathspec.
PATHSPEC_TAIL = hookio.rx(r"(^|[{S}])--([{S}]+(?![0-9]+[<>])[^{S};&|<>()]+)+")

# A STRUCTURAL PROOF names the tool or the claim it reports, and counts wherever it appears: the tool's own output is the evidence.
PROOF_PHRASE = re.compile(
    r"shape[-_ ]cluster[-_ ]diff|shape_cluster_diff\.py|ast[-_ ]equalit|ast[-_ ]diff|byte[-_ ]identical",
    re.IGNORECASE,
)
# A MANUAL PROOF is a claim that files were sampled and read, and `wl_proofcheck.PROOF_PROMPT` holds the judge to "naming which files or how many".
# The claim alone ("sampled and read", "sampled files") was accepted here until #d47f0539, which made this guard looser than the judge it mirrors: a sentence that names nothing is an assertion, not a check anyone can repeat.
MANUAL_CLAIM = re.compile(
    r"sampled\s+(?:\d+\s+)?files?|sampled\s+and\s+(?:diffed|read|compared)|read\s+across\s+both\s+revisions",
    re.IGNORECASE,
)
# What the claim must name, in its own unit: how many ("4 files", "all 45 files", "40 plan files", "32 named paths"), or which (a file name with an extension, optionally under directories).
# The extension starts with a letter, and a one-character stem needs a 2+ character extension, so "x.md" and "foo.c" are files while "e.g." and "v0.8.3" are not.
MANUAL_COUNT = re.compile(r"\b\d+\s+(?:[\w-]+\s+){0,2}?(?:files?|paths?)\b", re.IGNORECASE)
MANUAL_PATH = re.compile(
    r"(?<![\w.-])(?:[\w.-]+/)*"
    r"(?:[\w-]{2,}(?:\.[\w-]+)*\.[A-Za-z][A-Za-z0-9]{0,7}|[\w-]\.[A-Za-z][A-Za-z0-9]{1,7})(?![\w])"
)
# The unit a claim and its names must share: a paragraph, with each list item its own unit, so a sibling bullet's file name cannot prove a claim that names nothing.
# A paragraph rather than the sentence because the real follow-up proof df01e0083 says "every changed plan file was sampled and read across both revisions." and names the 40 plan files and the paths in the very next sentence.
UNIT_BREAK = re.compile(r"\n[ \t]*\n|\n(?=[ \t]*(?:[-*+]|\d+[.)])[ \t])")

# WHOSE COUNT IT IS, said in the first line (R20260924.22). The fallback to the staged index is kept, because guessing permissively is how a real bulk commit walks past, but a pathspec commit does not commit the index, so presenting the index count as "this commit's" sent a session hunting for 54 files its 17-file commit never touched (2026-09-24 19:01:33).
COUNT_INDEX = "%d staged file(s) is a bulk transform's scale"
COUNT_PATHSPEC = "this commit's pathspec covers %d file(s), a bulk transform's scale"
# Filled with what made the pathspec unreadable and the ceiling's size. Not the shared index: a pathspec commit never commits the index, which is how 69b1f2f145 (45 files, `-- $(cat list)`) was counted as 3 here and refused at `gh pr create` (#c17c47c3).
COUNT_OPAQUE = (
    "this commit's pathspec comes from %s, which only the shell can read, so it is judged at\n"
    "what any pathspec could commit: the %d pending file(s) of this tree, a bulk transform's\n"
    "scale (spell the paths literally, or assign them in this command, to be judged on the\n"
    "commit itself)"
)
COUNT_CEILING = (
    "an earlier clause of this command can still write under this commit's pathspec, which\n"
    "covers up to %d file(s), a bulk transform's scale"
)
COUNT_STAGING = (
    "%d file(s) will be in the index when this commit runs, counting what %s earlier in this\n"
    "command stages%s, a bulk transform's scale"
)
# Filled in when an earlier writer put a staging clause at its ceiling.
COUNT_STAGING_CEILING = " (at its ceiling, every tracked and untracked path in its scope, because\n%s runs first and can still write there)"
COUNT_UNRESOLVED = (
    "pathspec %s did not resolve; %d is the shared index, not this commit, and it is a bulk\n"
    "transform's scale"
)

BLOCK_COMMIT = """BLOCKED: %s, and this commit's own
message carries no proof it did not destroy structure it does not know about.

A bare file count or diff stat does not count. Run
    .ci/scripts/quality/shape_cluster_diff.py --rev HEAD <path...>
(or the equivalent structural/AST proof for this kind of change) and quote its
real output in the commit message, or state which files were sampled and
read across both revisions, naming them or how many in the same paragraph
("sampled 4 files: a.py, b.py, c.py, d.py"). "sampled and read" alone names
nothing and is not proof.
"""

BLOCK_RANGE = """BLOCKED: %s carries %d commit(s) this proof obligation has not seen cleared,
including %s (%d files, no proof quoted in its own message).

Each commit whose own diff reaches the bulk threshold needs its proof quoted
in ITS OWN commit message before it reaches this point. Amend the commit (if
still local) or attach the proof in a follow-up commit naming the one being
proven, then retry.
"""


def _proof_shown(text):
    """A structural proof anywhere, or a manual claim whose own unit names a file count or a file."""
    text = text or ""
    if PROOF_PHRASE.search(text):
        return True
    return any(
        MANUAL_CLAIM.search(unit) and (MANUAL_COUNT.search(unit) or MANUAL_PATH.search(unit))
        for unit in UNIT_BREAK.split(text)
    )


def _bulk_unproven(files, message):
    """THE ONE RULE, which the commit arm and the range arm both apply to one commit: bulk scale with no proof in its own message.

    The range arm additionally clears a commit by a follow-up proof or the baseline; neither exists yet at commit time, so they cannot make the commit arm stricter than the push arm, only the push arm more lenient.
    """
    return len(files) >= BULK_FILE_THRESHOLD and not _proof_shown(message)


def _name_only(args, cwd, want_rc=False):
    """The paths a diff touches, counted ONE way on every arm, or None under `want_rc` when git fails.

    `--no-renames` because the porcelain `git diff` detects renames by default and prints only the new name, while `diff-tree` does not and prints both: a 15-file rename counted 15 at commit and 30 at push, straddling the threshold.
    """
    out = hookio.git_out(
        [*args[:1], "--no-renames", "--name-only", *args[1:]], cwd=cwd, want_rc=want_rc
    )
    if out is None:
        return None
    return [line for line in out.splitlines() if line.strip()]


# `xargs ... git commit`: the paths are whatever the pipe or `-a <file>` feeds in, which only the shell knows. shellscan strips `xargs` as a prefix command, so the run alone cannot tell.
XARGS_COMMIT = re.compile(r"\bxargs\b[^;&|\n]*\bgit\b[^;&|\n]*\bcommit\b")


def _opaque_pathspec(cmd, scan, unexpanded):
    """What makes this commit's pathspec unreadable before the shell runs, as a label, or None when it is literal (or absent).

    THE COMMIT ARM AND THE RANGE ARM MUST COUNT ONE COMMIT THE SAME WAY. The range arm counts what `diff-tree` says the commit holds. The commit arm can only predict that, and when the pathspec is a substitution, a parameter it cannot expand, `--pathspec-from-file` or `xargs` input, the prediction used to fall back to the shared INDEX, which a pathspec commit never commits.
    In a shared tree, the index held 3 unrelated paths while `git commit -F msg -- $(cat list)` committed 45 (69b1f2f145, #c17c47c3). The same message was refused at `gh pr create`.
    """
    if unexpanded:
        # `PATHSPEC_TAIL` stops at `(`, so `$(cat list)` arrives as the bare token `$`, and a backticked one arrives split at its spaces.
        if any(t == "$" or "$(" in t or "`" in t for t in unexpanded):
            return "a command substitution"
        return ", ".join("`%s`" % t for t in unexpanded)
    commit = _commit_run(cmd)
    if commit is not None and any(a.startswith("--pathspec-from-file") for a in commit.argv):
        return "`--pathspec-from-file`"
    if XARGS_COMMIT.search(scan):
        return "`xargs` input"
    return None


def _pending_ceiling(cwd):
    """Every path a commit with an unreadable pathspec could carry: what differs from HEAD in the worktree, what is staged, and every untracked file that is not ignored."""
    untracked = hookio.git_out(
        ["ls-files", "--others", "--exclude-standard"], cwd=cwd, want_rc=True
    )
    return _union(
        _union(_name_only(["diff", "HEAD"], cwd) or [], _staged_files(cwd)),
        [line for line in (untracked or "").splitlines() if line.strip()],
    )


def _commit_message_text(cmd, cwd):
    return "\n".join(body for _, body in PSC.messages(cmd, cwd))


def _staged_files(cwd):
    return _name_only(["diff", "--cached"], cwd) or []


def _pathspec_files(cwd, paths):
    """What `git commit -- <paths>` will really commit, or [] when that cannot be resolved.

    A PATHSPEC COMMIT DOES NOT COMMIT THE INDEX. git's own wording: "git commit [--] <paths>... commits the contents of the files given on the command line", ignoring what is staged.
    In a tree several sessions share, the index routinely carries a hundred paths nobody in this command mentioned, so the staged count is a fact about the TREE rather than about the commit -- the same class of blindness the repo-context note in `run` records, one scope narrower.

    `HEAD`, not `--cached`, because the content committed comes from the WORKTREE: a path modified but never staged still lands in that commit, and `--cached` would not see it. `want_rc=True` keeps an unresolvable pathspec (a bogus path, a `--` belonging to some other clause) as None rather than as an empty list that would read as "this commit changes nothing".

    `git diff` NEVER REPORTS AN UNTRACKED FILE, staged or not -- that is not a `HEAD`-vs-`--cached` nuance, it is a property of `diff` itself, which only compares TRACKED content.
    Reproduced live 2026-09-23: a single brand-new file, `git add`ed then committed as `git commit -m ... -- <that file>`, made `diff HEAD --name-only -- <path>` print nothing (empty string, not None), so the caller's `paths and _pathspec_files(...)` was falsy and fell through to `_staged_files` -- the FULL shared index, 177 unrelated paths, on a one-file commit.
    `git status --porcelain -- <paths>` sees the file (`??`) where `diff` cannot, so it is unioned in below; the file's own new content is what would land in the commit either way.
    """
    tracked = _name_only(["diff", "HEAD", "--", *paths], cwd, want_rc=True)
    if tracked is None:
        return []

    # `--untracked-files=all` because the default collapses an untracked DIRECTORY to one `?? dir/` line: thirty new files under it counted as one here and thirty at push.
    status_out = hookio.git_out(
        ["status", "--porcelain", "--untracked-files=all", "--", *paths], cwd=cwd, want_rc=True
    )
    untracked: list[str] = []
    if status_out is not None:
        untracked.extend(
            line[3:].strip() for line in status_out.splitlines() if line.startswith("??")
        )

    seen = set(tracked)
    for path in untracked:
        if path not in seen:
            seen.add(path)
            tracked.append(path)
    return tracked


def _pathspecs_resolve(cwd, paths):
    """Does every pathspec token name something this repository knows?

    THE TAIL WAS READ CORRECTLY IS NOT THE SAME CLAIM AS THE PATHS HAVE CHANGES, and `_pathspec_files` cannot tell them apart: it answers `[]` both for a `--` that belonged to some other clause and for a real path with nothing pending. The caller used to treat every `[]` as the first case and fall back to the whole shared index.
    Reproduced live 2026-09-23: one bash command ran `worklist.py --plan-investigate ... --write` and THEN `git commit -- agent/ledgers/plan-investigation.jsonl`. This guard runs BEFORE the command, so at that instant the ledger was clean, the narrowed set was empty, and a one-file commit was refused citing 174 staged files belonging to other sessions.

    `ls-files --error-unmatch` is the tracked answer and an on-disk probe is the untracked one, which together are exactly the paths a commit can name. A token neither knows -- a bogus path, a stray `--` -- still returns False here, so the fallback that stops a real bulk commit walking past is untouched.
    """
    for path in paths:
        if (
            hookio.git_out(["ls-files", "--error-unmatch", "--", path], cwd=cwd, want_rc=True)
            is not None
        ):
            continue
        try:
            if (pathlib.Path(cwd) / path).exists():
                continue
        except OSError:
            pass
        return False
    return True


def _commit_pathspecs(scan):
    """The `-- <path>...` tail of the command, as a list of tokens."""
    matches = hookio.grep_o(PATHSPEC_TAIL, scan)
    if not matches:
        return []
    return [word for word in matches[-1].split() if word != "--"]


# A token that still needs the shell after expansion: a parameter, or a substitution this guard does not run.
UNEXPANDED = re.compile(r"\$|`")
PARAM = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
# The two substitutions worth expanding here, because both are READ-ONLY listings of this tree: `$(ls <glob>...)` and `$(git ls-files <args>...)`.
LISTING_SUBST = re.compile(r"\$\((ls|git ls-files)((?:[ \t]+[^()$`;&|<>]*)?)\)")


def _listing(kind, args, cwd):
    """What `$(ls <args>)` / `$(git ls-files <args>)` prints in `cwd`, or None when it cannot be known without the shell."""
    try:
        words = shlex.split(args)
    except ValueError:
        return None
    if kind == "git ls-files":
        out = hookio.git_out(["ls-files", *words], cwd=cwd, want_rc=True)
        return None if out is None else out.split()
    listed = []
    for word in words:
        if word.startswith("-"):
            return None
        hits = sorted(glob.glob(word, root_dir=cwd)) if glob.has_magic(word) else [word]
        listed.extend(hits or [word])
    return listed


def _expand_pathspecs(tokens, cmd, cwd):
    """`(paths, unexpanded)`: the pathspec tokens with same-command `$NAME`/`${NAME}` assignments expanded, as bash would word-split and glob them.

    R20260924.22. `P="... $(ls .../cli.json)"; git commit -F $M -- $P` left `$P` as a literal token, `_pathspecs_resolve` failed on it, and the guard judged the shared index instead (2026-09-24 19:01:33: "54 staged file(s)" for a 17-file commit). A token that still carries `$` or a backtick afterwards is returned in `unexpanded`, and the caller falls back to the index AND says it did.
    """
    if not any("$" in t or "`" in t for t in tokens):
        return tokens, []
    names = shellscan.assignments_before(cmd, "git commit")
    paths = []
    unexpanded = []
    for token in tokens:
        text = token
        for _ in range(4):
            new = PARAM.sub(lambda m: names.get(m.group(1) or m.group(2), m.group(0)), text)
            if new == text:
                break
            text = new
        pieces = []
        pos = 0
        ok = True
        for match in LISTING_SUBST.finditer(text):
            listed = _listing(match.group(1), match.group(2), cwd)
            if listed is None:
                ok = False
                break
            pieces.append(text[pos : match.start()])
            pieces.append(" ".join(listed))
            pos = match.end()
        pieces.append(text[pos:])
        text = "".join(pieces)
        if not ok or UNEXPANDED.search(text):
            unexpanded.append(token)
            continue
        for word in text.split():
            hits = sorted(glob.glob(word, root_dir=cwd)) if glob.has_magic(word) else []
            paths.extend(hits or [word])
    return paths, unexpanded


def _commit_files(sha, cwd):
    return _name_only(["diff-tree", "--no-commit-id", "-r", "--root", sha], cwd) or []


# Tools that write nothing but their own redirects. Anything else run before `git commit` (a generator, a formatter, `npm run`, `git add`) can change what the commit's pathspec covers.
INERT_TOOLS = frozenset(
    {
        "cd",
        "echo",
        "printf",
        "cat",
        "true",
        "false",
        "test",
        "[",
        "wc",
        "grep",
        "head",
        "tail",
        "cut",
        "sort",
        "uniq",
        "tr",
        "ls",
        "pwd",
        "date",
        "basename",
        "dirname",
        "realpath",
        "readlink",
        "export",
        "sleep",
    }
)
INERT_GIT = frozenset({"status", "log", "diff", "show", "rev-parse", "ls-files"})


def _runs_before_commit(cmd):
    """The runs of `cmd` that execute before its first `git commit`, in order, or [] when there is none."""
    runs = shellscan._analyse(cmd).runs
    idx = next(
        (
            i
            for i, r in enumerate(runs)
            if r.name.rsplit("/", 1)[-1] == "git" and r.git_sub == "commit"
        ),
        None,
    )
    return runs[:idx] if idx else []


def _earlier_writers(cmd, cwd, paths):
    """Labels of the clauses before `git commit` that can change what `paths` cover, in order.

    WHY THIS EXISTS: this guard runs ONCE, before the first clause, so a pathspec commit is counted as the tree stands BEFORE any generator earlier in the same command. 3a5f3a188 ran `node scripts/generate-search-index.js` and then `git commit -- docs/design/06-cli-reshape.md packages/www`: 14 files were counted here, 28 were committed, and the push refused what the commit had
    allowed. A tool outside `INERT_TOOLS` counts as a writer, and so does an inert tool's redirect that lands under a pathspec path or cannot be expanded.
    """
    roots = [os.path.normpath(os.path.join(cwd, p)) for p in paths]
    return _writers_in(_runs_before_commit(cmd), cmd, cwd, roots)


def _writers_in(runs, cmd, cwd, roots, inert_git=INERT_GIT):
    """Labels of the clauses in `runs` that can write under any of the absolute `roots`, in order."""
    if not runs:
        return []
    names = shellscan.assignments_before(cmd, "git commit")
    out = []
    for run in runs:
        base = run.name.rsplit("/", 1)[-1]
        label = " ".join([base, *run.argv[:1]])
        if base == "git":
            writer = run.git_sub is not None and run.git_sub not in inert_git
        else:
            writer = base not in INERT_TOOLS
        for target in run.writes:
            if writer or target in shellscan._NOT_A_FILE or target.startswith("/dev/fd/"):
                continue
            text = PARAM.sub(lambda m: names.get(m.group(1) or m.group(2), m.group(0)), target)
            if UNEXPANDED.search(text):
                writer = True
                continue
            where = os.path.normpath(os.path.join(run.cwd or cwd, text))
            writer = any(where == r or where.startswith(r + os.sep) for r in roots)
        if writer and label not in out:
            out.append(label)
    return out


def _pathspec_ceiling(cwd, paths, files):
    """Every file `paths` can cover once an earlier clause has written: the pending ones, plus every tracked and every untracked-but-not-ignored path under them."""
    out = list(files)
    seen = set(out)
    for extra in (
        ["ls-files", "--full-name"],
        ["ls-files", "--full-name", "--others", "--exclude-standard"],
    ):
        listed = hookio.git_out([*extra, "--", *paths], cwd=cwd, want_rc=True) or ""
        for line in listed.splitlines():
            if line.strip() and line not in seen:
                seen.add(line)
                out.append(line)
    return out


def _parse_stage(run):
    """`(mode, pathspecs)` for a `git add` / `git rm` run, `None` when it stages nothing, or `("unparsed", None)`.

    `mode` is `all` (tracked changes plus untracked files), `update` (tracked changes only, `add -u` and every `rm`). Empty `pathspecs` under `add -A`/`add -u` is the whole repository, git's own reading since 2.0; empty under a plain `add` stages nothing.

    READ THE WAY GIT READS IT (#e8be3092): `shellscan.git_args`, git's parse-options over the complete `git add`/`git rm` option tables, after `commit_policy.git_split` drops the global options (`--attr-source <tree>` included). The last of a flag and its negation wins, a unique prefix is the option, a valued option (`--chmod +x`) swallows its value, and `--`/`--end-of-options` end the options. Measured on git 2.53.0 against the
    flag-name matching this replaced: `git add -n --no-dry-run -A` staged everything and was read as a dry run (the one under-count, so the one bypass), while `-A --no-all`, `-u --no-update` and `--ignore-removal` with no pathspec, `--dry -A` and `--end-of-options -A` staged nothing and were judged at the ceiling. `--no-all`/`--ignore-removal` with a pathspec stage a subset of the default and `-p`/`-i`/`-e`/`-N` a subset of what they are shown, so each is judged as the default, the larger set; `-A` beside `-u` is a fatal error in git and is judged as `-A`, the larger. An option git would refuse (`problems`), and a `--pathspec-from-file`, stay unreadable and are judged at the ceiling.
    """
    _, sub, args = commit_policy.git_split(run.argv)
    parsed = shellscan.git_args(sub, args)
    if parsed.problems or parsed.values("pathspec-from-file"):
        return ("unparsed", None)
    if parsed.on("dry-run"):
        return None
    specs = list(parsed.operands)
    if sub == "rm":
        return ("update", specs) if specs else None
    add_all = None
    for name, value in parsed.flags:
        if name in ("all", "ignore-removal"):
            add_all = (value != "false") == (name == "all")
    update = parsed.on("update")
    whole = bool(add_all) or update
    mode = "update" if update and not add_all else "all"
    if not specs and not whole:
        return None
    return mode, specs


def _stage_files(cwd, mode, specs, ceiling):
    """What a `git add`/`git rm` over `specs` run in `cwd` stages, or None when git cannot answer: every changed path under `specs` (untracked ones too under `all`), and under `ceiling` every tracked path too, since an earlier clause can still change any of them."""
    tail = ["--", *(specs or [":/"])]
    status = hookio.git_out(
        ["status", "--porcelain", "--no-renames", "--untracked-files=all", *tail],
        cwd=cwd,
        want_rc=True,
    )
    if status is None:
        return None
    out = [
        line[3:]
        for line in status.splitlines()
        if len(line) > 3 and not (mode == "update" and line.startswith("??"))
    ]
    if ceiling:
        listings = [["ls-files", "--full-name"]]
        if mode == "all":
            listings.append(["ls-files", "--full-name", "--others", "--exclude-standard"])
        for extra in listings:
            listed = hookio.git_out([*extra, *tail], cwd=cwd, want_rc=True)
            if listed is None:
                return None
            out.extend(line for line in listed.splitlines() if line.strip())
    return out


def _staged_by_command(cmd, cwd):
    """`(files, stagers, writers)`: every path the `git add`/`git rm` clauses (and a `git commit -a`) of `cmd` will have staged by the time its commit runs, the labels of those clauses, and the labels of the earlier writers that put one of them at its ceiling.

    WHY THIS EXISTS: an index commit (no pathspec) commits the index as it stands WHEN THE COMMIT RUNS, and this guard reads it before the first clause. `node gen.js && git add -A && git commit -F m` over 25 regenerated files counted the empty index here and was refused only at push (worklist #8333146d).
    An add after an earlier writer is judged at its ceiling, the same rule `_pathspec_ceiling` applies to a pathspec. An add whose directory or arguments this guard cannot read is judged at the repository's ceiling: failing open here is exactly the gap this closes.
    """
    runs = _runs_before_commit(cmd)
    commit = _commit_run(cmd)
    top = hookio.git_out(["rev-parse", "--show-toplevel"], cwd=cwd, want_rc=True)
    files: list[str] = []
    labels: list[str] = []
    writer_labels: list[str] = []
    for i, run in enumerate(runs):
        if run.name.rsplit("/", 1)[-1] != "git" or run.git_sub not in ("add", "rm"):
            continue
        parsed = _parse_stage(run)
        if parsed is None:
            continue
        mode, specs = parsed
        where = os.path.normpath(os.path.join(cwd, run.git_dir or "."))
        if (
            specs is not None
            and any(UNEXPANDED.search(s) for s in specs)
            and _expand_pathspecs(specs, cmd, where)[1]
        ):
            specs = None
        elif specs is not None:
            specs = _expand_pathspecs(specs, cmd, where)[0]
        here = hookio.git_out(["rev-parse", "--show-toplevel"], cwd=where, want_rc=True)
        if here is not None and top is not None and here != top:
            continue  # it stages into another repository's index
        roots = [os.path.normpath(os.path.join(where, s)) for s in specs or ["."]]
        if specs is None or (not specs and top):
            roots = [os.path.normpath(top or cwd)]
        writers = _writers_in(runs[:i], cmd, cwd, roots, INERT_GIT | {"add", "rm"})
        # `git rm` deletes clean tracked files too, which no status line shows yet: every tracked path under its pathspec is what it stages.
        ceiling = bool(writers) or run.git_sub == "rm"
        writer_labels.extend(label for label in writers if label not in writer_labels)
        got = None
        if specs is not None and here is not None:
            got = _stage_files(where, mode, specs, ceiling)
        if got is None:
            got = _stage_files(cwd, "all", [":/"], ceiling) or []
        files.extend(got)
        labels.append(" ".join(["git", *run.argv]))
    if commit is not None and _commit_all(commit):
        writers = _writers_in(runs, cmd, cwd, [os.path.normpath(top or cwd)])
        writer_labels.extend(label for label in writers if label not in writer_labels)
        files.extend(_stage_files(cwd, "update", [":/"], bool(writers)) or [])
        labels.append("git commit -a")
    return files, labels, writer_labels


def _commit_run(cmd):
    return next(
        (
            r
            for r in shellscan._analyse(cmd).runs
            if r.name.rsplit("/", 1)[-1] == "git" and r.git_sub == "commit"
        ),
        None,
    )


def _commit_all(run):
    """Whether this `git commit` runs with `-a`/`--all`, which stages every modified and deleted tracked file first. Read by `shellscan.git_commit_args` (#e8be3092): `-qa` is `--all`, `-ma` is the message "a", `-m -a` the message "-a", and the last of `-a`/`--no-all` wins (git 2.53.0 committed nothing for `-a --no-all`, which the hand-written reader this replaced counted as all)."""
    _, _, args = commit_policy.git_split(run.argv)
    return shellscan.git_commit_args(args).on("all")


def _union(first, second):
    out = list(first)
    seen = set(out)
    for path in second:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _commit_message(sha, cwd):
    return hookio.git_out(["log", "-1", "--format=%B", sha], cwd=cwd)


def _range_commits(base, head, cwd):
    """SHAs base..head, oldest excluded, or None when the range cannot be resolved.

    `want_rc=True` is what makes an unresolvable range (no such ref, no
    upstream) come back as None rather than as an empty string that would read as "nothing to check" -- the same distinction `git_out`'s own docstring names as the reason the two modes exist.
    """
    out = hookio.git_out(["rev-list", "%s..%s" % (base, head)], cwd=cwd, want_rc=True)
    if out is None:
        return None
    shas = [line for line in out.splitlines() if line.strip()]
    return shas[:RANGE_COMMIT_CAP]


def _grandfathered_shas(cwd):
    """{full-sha} named in .ci/config/bulk-transform-proof-baseline.json, or empty.

    SHRINK-ONLY, the same convention every other baseline in this repo already follows: pre-existing debt at the moment the baseline landed, never a general escape hatch for a NEW bulk commit.

    Missing file, unreadable JSON, or a wrong shape all read as empty -- a fixture repo with no such file must behave exactly as it did before this existed, and a corrupt baseline must fail toward MORE checking, not less.
    """
    path = pathlib.Path(cwd) / ".ci" / "config" / "bulk-transform-proof-baseline.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    shas = data.get("grandfathered")
    return set(shas) if isinstance(shas, list) else set()


def _proven_by_a_later_commit(sha, newer_messages):
    """Whether a commit NEWER than `sha` in the same range names it and shows proof.

    `newer_messages` is every message strictly closer to HEAD than `sha` -- the shape the module docstring promises ("attach the proof in a follow-up commit naming the one being proven").

    `_commit_message(sha, cwd)` alone, reading only the offending commit's own text, cannot see a follow-up; this is what makes that promise real.

    `sha[:10]` matches how this guard already abbreviates a SHA everywhere else it prints one (`BLOCK_RANGE`), so a follow-up commit only has to spell the same short form.
    """
    return any(_names_sha(msg, sha) and _proof_shown(msg) for msg in newer_messages)


# A hex word of at least 7 characters, git's minimum abbreviation.
_HEX_WORD = re.compile(r"\b[0-9a-f]{7,40}\b")


def _names_sha(msg, sha):
    """Whether `msg` names `sha` by ANY prefix of 7 or more characters.

    Matching only `sha[:10]` refused a follow-up proof written with git's own short form: this repo abbreviates to 9 (`git rev-parse --short`), so a message naming `bd0278084` never matched `bd02780841` and the push stayed blocked on a proof that was there (2026-09-26).
    """
    return any(sha.startswith(word) for word in _HEX_WORD.findall(msg))


def _first_unproven(shas, cwd):
    """The first (sha, file_count) over threshold with no proof anywhere in the range, or None.

    `shas` is newest-first (git rev-list's own order), so a commit's "later, in the same push/PR" proof sits at a LOWER index -- collected once, up front, so an N-commit range costs one pass rather than a quadratic re-scan.
    """
    grandfathered = _grandfathered_shas(cwd)
    messages = [_commit_message(sha, cwd) for sha in shas]
    for i, sha in enumerate(shas):
        if sha in grandfathered:
            continue
        files = _commit_files(sha, cwd)
        if not _bulk_unproven(files, messages[i]):
            continue
        if _proven_by_a_later_commit(sha, messages[:i]):
            continue
        return sha, len(files)
    return None


def _push_target(scan, cwd):
    """(base_ref, head) for the range about to leave via `git push`, or None.

    Prefers the configured upstream (`@{u}`), which is what a plain `git push`
    actually compares against. A branch with none -- a first push, a detached checkout -- is UNRESOLVABLE, and this guard allows rather than guesses which remote branch a bare push would even create.
    """
    del scan  # the branch name on the command line is not trusted over the real upstream
    upstream = hookio.git_out(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=cwd, want_rc=True
    )
    # THE LITERAL "HEAD" IS A SEPARATE FAILURE FROM THE EMPTY ONE, and emptiness alone does not catch it.
    # `rev-parse --abbrev-ref` answers with the string "HEAD" rather than failing when there is nothing symbolic to shorten, and this guard would then compare the range "HEAD..HEAD", which is EMPTY: every commit in the push would go unexamined and the push would be allowed, silently, in exactly the case the docstring above calls unresolvable.
    if not upstream or upstream == "HEAD":
        return None
    return upstream, "HEAD"


def _pr_base(cmd, cwd):
    """The PR's base: the REMOTE branch `--base <ref>` names (default `main`), read as `origin/<ref>` when that ref exists.

    A PR targets the branch on GitHub, never a local ref. A bare `main` here used to be taken literally, and a submodule's local `main` can sit far behind origin: renet's sat 135 commits back on 2026-10-04, so `main..HEAD` swept in an old, already-merged bulk commit and refused a one-commit PR. The local name is used only when no `origin/<ref>` exists.
    """
    ref = "main"
    tokens = cmd.split()
    for index, token in enumerate(tokens):
        if token in ("--base", "-B") and index + 1 < len(tokens):
            ref = tokens[index + 1]
            break
        if token.startswith("--base="):
            ref = token.split("=", 1)[1]
            break
    if ref.startswith("origin/"):
        return ref
    remote = hookio.git_out(["rev-parse", "--verify", "origin/%s" % ref], cwd=cwd, want_rc=True)
    return "origin/%s" % ref if remote is not None else ref


def run(ev):
    cmd = ev.field("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    root = ev.env("CLAUDE_PROJECT_DIR", "") or hookio.git_out(["rev-parse", "--show-toplevel"])

    # ANOTHER REPO'S STAGED COUNT IS NOT THIS GUARD'S BUSINESS.
    # Same class of defect as block_untagged_commit / block_unverified_push / block_blanket_git_add (see shellscan.target_root's own docstring): reproduced live 2026-09-23, a writer's `git -C <scratchpad fixture> commit` (equally: a leading `cd <fixture> &&`) was refused citing 255 staged files, which was CONSOLE's own count, never the fixture's.
    # `root`/CLAUDE_PROJECT_DIR is only the right tree to judge when the command does not name a different one itself. `target_root` returns "" for an unresolvable hint, so a bogus `-C` path does NOT exempt a command: the guard falls through and keeps judging `root`.
    if shellscan.target_root(scan, root, verb="commit") != "":
        return hookio.ALLOW

    cwd = ev.field("cwd") or root

    # `_commit_run` too: `xargs git commit` puts git behind a prefix command, which `GIT_COMMIT`'s command-position anchor does not reach and shellscan's walk does.
    if PSC.GIT_COMMIT.search(scan) or _commit_run(cmd) is not None:
        # A PATHSPEC NARROWS THE COMMIT, SO IT NARROWS THIS COUNT. Reproduced live 2026-09-23: a three-file `git commit -F <msg> -- <three paths>` was refused citing 183 staged files, none of which that commit would have touched -- the index belonged to other sessions' work in the same tree, which is the normal state here and the reason `block_blanket_git_add.py` exists.
        # An EMPTY narrowed set falls back to the staged count ONLY when the tail did not resolve.
        # Guessing in the permissive direction is how a real bulk commit walks past a guard whose whole subject is scale, so a `--` belonging to some other clause still gets judged on the index. A pathspec naming paths this repository knows is a different answer: the commit really is that narrow, and it reads as empty only because this guard runs BEFORE the command that writes
        # those paths. See `_pathspecs_resolve`.
        paths, unexpanded = _expand_pathspecs(_commit_pathspecs(scan), cmd, cwd)
        files = _pathspec_files(cwd, paths) if paths and not unexpanded else []
        count = COUNT_PATHSPEC
        index_judged = True
        opaque = _opaque_pathspec(cmd, scan, unexpanded)
        if opaque:
            files = _pending_ceiling(cwd)
            count = COUNT_OPAQUE % (opaque, len(files))
        elif not files and not (paths and _pathspecs_resolve(cwd, paths)):
            files = _staged_files(cwd)
            count = (
                COUNT_UNRESOLVED % (" ".join("`%s`" % t for t in paths), len(files))
                if paths
                else COUNT_INDEX % len(files)
            )
        else:
            index_judged = False
            count = count % len(files)
        # AN INDEX COMMIT COMMITS THE INDEX AS IT STANDS WHEN THE COMMIT RUNS, so a `git add`/`git rm`/`commit -a` earlier in this command counts here; see `_staged_by_command`.
        stagers: list[str] = []
        before: list[str] = []
        if index_judged:
            added, stagers, before = _staged_by_command(cmd, cwd)
            if stagers:
                files = _union(files, added)
                ceiling_note = (
                    COUNT_STAGING_CEILING % ", ".join("`%s`" % w for w in before) if before else ""
                )
                count = COUNT_STAGING % (
                    len(files),
                    ", ".join("`%s`" % s for s in stagers),
                    ceiling_note,
                )
        # AN EARLIER CLAUSE THAT WRITES makes the pending set a lower bound, so the pathspec's ceiling is what gets judged; a real bulk commit then meets the same rule here that it meets at push. The refusal names the clause to run on its own.
        # An unreadable pathspec can cover the whole tree, so its ceiling is the repository's.
        scope = paths
        if opaque:
            scope = [":/"]
            writers = _earlier_writers(
                cmd, cwd, [hookio.git_out(["rev-parse", "--show-toplevel"], cwd=cwd) or cwd]
            )
        else:
            writers = _earlier_writers(cmd, cwd, paths) if paths else []
        if writers:
            files = _pathspec_ceiling(cwd, scope, files)
            count = COUNT_CEILING % len(files)
        if _bulk_unproven(files, _commit_message_text(cmd, cwd)):
            # An earlier clause that stages, commits, writes a file or publishes changes what was just counted, or the message file read for proof (R20260924.22).
            mutators = shellscan.earlier_mutators(cmd, "git commit")
            judged = "the index, the worktree and the commit message file"
            if writers:
                # The ceiling came from a clause `earlier_mutators` may not know (a generator), so the named clause is this guard's own.
                mutators = [shellscan.Mutator("writer", label, None) for label in writers]
                judged = "this commit's pathspec"
            elif stagers:
                # `git commit -a` is the verb itself, never a clause to split off.
                mutators = [shellscan.Mutator("writer", label, None) for label in before] + [
                    shellscan.Mutator("stage", label, None)
                    for label in stagers
                    if label != "git commit -a"
                ]
                judged = "the index this commit commits"
            ev.warn_raw(shellscan.split_refusal(mutators, "git commit", judged))
            ev.warn(BLOCK_COMMIT % count)
            return hookio.DENY
        return hookio.ALLOW

    # A DELETE-ONLY PUSH carries no commits, so there is no range to prove; block_unverified_push.every_push_deletes_only is the one definition both push guards read.
    if hookio.grep_q(PUSH.PUSH_AT_COMMAND_POS, scan) and not PUSH.every_push_deletes_only(scan):
        target = _push_target(scan, cwd)
        if target is None:
            return hookio.ALLOW
        base, head = target
        shas = _range_commits(base, head, cwd)
        if shas:
            hit = _first_unproven(shas, cwd)
            if hit:
                sha, count = hit
                _warn_range_split(ev, cmd, "git push")
                ev.warn(BLOCK_RANGE % (base, len(shas), sha[:10], count))
                return hookio.DENY
        return hookio.ALLOW

    if shellscan.gh_pr_at_command_pos(scan, "create"):
        base = _pr_base(cmd, cwd)
        shas = _range_commits(base, "HEAD", cwd)
        if shas:
            hit = _first_unproven(shas, cwd)
            if hit:
                sha, count = hit
                _warn_range_split(ev, cmd, "gh pr create")
                ev.warn(BLOCK_RANGE % (base, len(shas), sha[:10], count))
                return hookio.DENY
        return hookio.ALLOW

    return hookio.ALLOW


def _warn_range_split(ev, cmd, verb):
    """A commit made by an earlier clause of the same command is not yet in the range this guard walked (R20260924.22)."""
    ev.warn_raw(
        shellscan.split_refusal(
            shellscan.earlier_mutators(cmd, verb, {"commit"}), verb, "the commits in the range"
        )
    )


EDGE_CASES = [
    ("a bulk commit with no proof quoted", 'git commit -m "reflow the tree"'),
    ("a small commit, well under threshold", 'git commit -m "fix: a small thing"'),
    ("a plain command is not a target", "ls -la"),
    ("gh pr view is not a write", "gh pr view 1"),
    ("git log is not git commit", 'git log --grep "shape_cluster_diff.py"'),
]


def _bulk_staged_world(target):
    """A scratch repo with a bulk-sized change already staged, so the commit branch has something to refuse."""
    target.mkdir(parents=True, exist_ok=True)
    quiet = {
        "capture_output": True,
        "env": {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": "/nonexistent",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    }

    def run_git(*args):
        subprocess.run(["git", "-C", str(target), *args], check=True, **quiet)

    run_git("init", "-q", "-b", "main")
    (target / "base.txt").write_text("x\n", encoding="utf-8")
    run_git("add", ".")
    run_git("commit", "-q", "-m", "base")
    for i in range(BULK_FILE_THRESHOLD + 2):
        (target / ("bulk-%02d.py" % i)).write_text("x = %d\n" % i, encoding="utf-8")
    run_git("add", ".")
    return target


FIXTURES = {"bulk-staged": _bulk_staged_world}

# CLAUDE_PROJECT_DIR is the guard's fallback working directory when the payload carries none, so pointing it at the fixture is what puts the staged files under the commit case.
ENVS = [("bulk-staged", {"CLAUDE_PROJECT_DIR": "{FIXTURE:bulk-staged}"}, {})]
