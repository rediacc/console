"""Refuse a hand-written PR body edit; route it through the tool that rebuilds it.

WHY. The console PR description is not free text any more: it carries a delimited worklist-epics block generated from agent/pr/<branch>.md, and CI gates on that block matching the published snapshot. A raw `gh pr edit --body`/`--body-file` writes the WHOLE body, so it silently drops the block, and the next thing anyone learns is a red gate several minutes later with no hint of what
removed it.

THE SAME CLASS ALREADY BIT THIS REPO ONCE, one level down: .ci/scripts/autopilot/submodule-prs.sh's header warns that its block must not share markers with refresh-pr-body.sh, "because that hook rewrites the WHOLE body on every push and anything inside its markers is destroyed on the next one." A whole-body writer is the hazard; this guard is that lesson applied to the model's own
hands.

NOT BLOCKED, deliberately:
  - the sanctioned tool itself, .ci/scripts/pr/sync-epic-block.sh, which
    strips and rebuilds only its own markers;
  - `gh pr create` whose body ALREADY carries the block, and `gh pr create`
    with no body flag at all -- create is the one call with no block to
    destroy, so it is judged on what it produces, not on being a whole-body
    write;
  - `gh api .../pulls/<n> -X PATCH` that carries no body field (a title or
    state change), for the same reason;
  - `gh api .../pulls/<n> -X PATCH` whose body carries a generated block and is
    missing another one THE LIVE DESCRIPTION DOES NOT HAVE EITHER. A write
    cannot drop what is not there, and refusing it left PR #590 with no route to
    correcting its own description at all on 2026-09-23. See `_would_drop`;
  - `gh pr edit` for anything that is not the body: --title, --add-label,
    --add-reviewer, --milestone. The guard keys on the body flags alone,
    because a guard whose usual outcome is a false positive teaches people to
    route around it;
  - the PostToolUse hook refresh-pr-body.sh and the autopilot scripts, which
    are not model Bash calls and never reach this chain;
  - any body write to a SUBMODULE's PR (the repos `.gitmodules` names:
    rediacc/renet, rediacc/account, rediacc/elite, rediacc/homebrew-tap). See
    `_blockless_repos`: no tool writes a generated block into those bodies, so
    a whole-body write there drops nothing, and refusing it left
    `gh api repos/rediacc/renet/pulls/113 -X PATCH -F body=@<file>` with no
    route at all on 2026-09-30.

=============================================================================
PORT NOTE: A DEAD VARIABLE, REPRODUCED RATHER THAN REPAIRED
=============================================================================

The bash declares `HOOK_SAW_BODY_FILE=0` and sets it to 1 inside
`hook_visible_body`. That function is only ever called in a command substitution, so the assignment happens in a SUBSHELL and cannot reach the caller; and nothing reads the variable afterwards in any case. It is dead twice over. The port keeps neither the variable nor a Python stand-in for it, because reproducing a value nobody reads would be reproducing nothing, and the record of
why it is gone is this paragraph. Reported as a finding rather than fixed in the bash, which must stay byte-identical until the P6 cutover.
"""

import os
import pathlib
import re

from rediacc_hooks import commit_policy, hookio, shellscan
from rediacc_hooks.wellknown import ACCOUNT_REPO, ELITE_REPO, GH_REPO, RENET_REPO

CHAIN = "pre-bash"
ORDER = 36

# The `gh api ... -X PATCH -F body=` arm, added 2026-09-04. Without it the door
# this file's own message points people at has no marker check, which is exactly the state it was in until that day.
DEFECT = ("    if patch is not None:", "    if False:")

BEGIN_MARKER = "<!-- worklist-epics:begin -->"
# Every machine-written section of a PR body in this repo. An edit must carry them ALL, because `gh pr edit --body` writes the whole body and anything absent is gone. Measured on PR #585, 2026-09-03: the body carries worklist-epics AND pushed-head.
GENERATED_MARKERS = ("worklist-epics", "pushed-head")

BODY_FILE_ARGS = hookio.rx(r"--body-file([{S}]+|=)[^{S};|&]+")
API_VERB = hookio.rx(r"^[{S}]*gh[{S}]+api([{S}]|$)")
API_PULLS = r"pulls/[0-9]+"
API_PATCH = hookio.rx(r"(^|[{S}])(-X|--method)[{S}]+PATCH([{S}]|$)")
API_BODY_FLAG = hookio.rx(
    r"(^|[{S}])(-F|-f|--field|--raw-field)[{S}]+body=|(^|[{S}])--input([{S}]|=)"
)
API_BODY_ARGS = hookio.rx(r"((-F|--field)[{S}]+body=@|--input([{S}]+|=))[^{S};|&]+")
# The endpoint the PATCH names, reused as the endpoint the CURRENT body is read back from. Taken from the command rather than from the cwd, because the repo a PATCH targets is spelled in its own path.
API_PR_REF = hookio.rx(r"repos/[^{S};|&/]+/[^{S};|&/]+/pulls/[0-9]+")

REFUSE_WHOLE_BODY = """BLOCKED: do not write a PR body by hand.

The description carries generated `<!-- worklist-epics:begin -->` and
`<!-- pushed-head:begin -->` blocks, and a whole-body write (`gh pr edit --body`,
or `gh api .../pulls/<n> -X PATCH -F body=...`) replaces the WHOLE body, so any
block absent from what you send is gone. CI then fails on a missing block,
minutes later, naming nothing that would point back here.

Use the tool, which strips and rebuilds only its own markers and leaves your
prose alone:

  worklist.py --publish <me> <branch>          # refresh the snapshot
  .ci/scripts/pr/sync-epic-block.sh <pr> <branch>   # sync it into the PR

To change the narrative part of the description, keep EVERY marker in the body
you write -- a body that already carries them all is not refused, because it
cannot be the thing that drops them. Read the current body, change your prose,
leave the marker sections alone, and send it with the PATCH form (`gh pr edit
--body` is refused by block-adhoc-sanctioned.sh: it exits 1 on a deprecated
GraphQL field and leaves the body unchanged). Give the file by its LITERAL path;
a path behind a shell variable is unreadable here and is refused, not trusted:

  gh pr view <pr> --json body -q .body > /abs/path/body.md   # keeps the blocks
  # edit the prose in body.md, leave the worklist-epics and pushed-head sections untouched
  gh api repos/<owner>/<repo>/pulls/<pr> -X PATCH -F body=@/abs/path/body.md

`gh pr edit --title`, `--add-label` and friends are not affected by this guard.
"""

EDGE_CASES = [
    ("the sanctioned tool", ".ci/scripts/pr/sync-epic-block.sh 42 0831-1"),
    ("an edit with no body flag", "gh pr edit 42 --add-label ci"),
    ("an edit dropping every block", 'gh pr edit 42 --body "prose with no block at all"'),
    # The 2026-09-03 correction: the epic block ALONE is not enough.
    (
        "an edit carrying ONLY the epic block still drops pushed-head",
        'gh pr edit 42 --body "x <!-- worklist-epics:begin --> y"',
    ),
    (
        "an edit carrying EVERY generated marker passes",
        'gh pr edit 42 --body "x <!-- worklist-epics:begin --> y <!-- pushed-head:begin --> z"',
    ),
    # The 2026-09-04 arm: the door this guard's own message points at.
    (
        "a PATCH with no readable body file",
        "gh api repos/o/r/pulls/42 -X PATCH -F body=@/nonexistent-body.md",
    ),
    (
        "a PATCH carrying every marker inline",
        (
            "gh api repos/o/r/pulls/42 -X PATCH -f body='<!-- worklist-epics:begin --> "
            "<!-- pushed-head:begin -->'"
        ),
    ),
    ("a PATCH with no body field at all", "gh api repos/o/r/pulls/42 -X PATCH -f title=x"),
    ("a GET is not a PATCH", "gh api repos/o/r/pulls/42"),
    # create: the hole measured 2026-08-27.
    ("a create with no body flag", "gh pr create --draft --title t --fill"),
    ("a create whose body drops the block", 'gh pr create --draft --body "x"'),
    (
        "a create whose body carries the block",
        'gh pr create --draft --body "x <!-- worklist-epics:begin --> y"',
    ),
    ("a create with an unreadable body file", "gh pr create --draft --body-file /nonexistent.md"),
    # 2026-10-07 (#09c80388): the verdict followed the flag's SPELLING, not the body. File-based halves are in test_pr_body_reader.py.
    ("a create by -b with no block", 'gh pr create --draft -b "prose only"'),
    (
        "a create by -b carrying the block",
        'gh pr create --draft -b "x <!-- worklist-epics:begin --> y"',
    ),
    (
        "a create reading a heredoc on stdin with no block",
        "gh pr create --draft --body-file - <<'EOF'\nprose only\nEOF",
    ),
    (
        "a create reading a heredoc on stdin carrying the block",
        "gh pr create --draft -F - <<'EOF'\nx\n<!-- worklist-epics:begin -->\nEOF",
    ),
    (
        "a create whose body file an earlier clause writes",
        (
            "printf '%s' '<!-- worklist-epics:begin -->' > /nonexistent-pr-body.md && "
            "gh pr create --draft --body-file /nonexistent-pr-body.md"
        ),
    ),
    (
        "a write AFTER the create cannot change what it read",
        (
            "gh pr create --draft --body-file /nonexistent-pr-body.md && "
            "echo x > /nonexistent-pr-body.md"
        ),
    ),
    ("an edit by -F", "gh pr edit 42 -F /nonexistent.md"),
    ("an edit by -b", 'gh pr edit 42 -b "prose only"'),
    (
        "a PATCH whose body file an earlier clause writes",
        (
            "printf x > /nonexistent-pr-body.md && "
            "gh api repos/o/r/pulls/42 -X PATCH -F body=@/nonexistent-pr-body.md"
        ),
    ),
    # ORDER MATTERS: the edit arm runs FIRST.
    (
        "a create that passes, then an edit that does not",
        'gh pr create --draft --body "x <!-- worklist-epics:begin --> y" && gh pr edit 5 --body "z"',
    ),
    # THE FLAG BELONGS TO ITS OWN INVOCATION.
    (
        "a body on create and a label on edit",
        (
            'gh pr create --draft --body "x <!-- worklist-epics:begin --> y '
            '<!-- pushed-head:begin --> z" && gh pr edit 5 --add-label ci'
        ),
    ),
    # Prose about the rule is not the rule being broken.
    ("prose naming the flag", "echo 'never use gh pr edit --body by hand'"),
    # 2026-09-30: a submodule PR carries no generated block, so there is none to drop.
    (
        "a submodule PATCH with a blockless body",
        ("gh api repos/" + RENET_REPO + "/pulls/113 -X PATCH -f body='prose only'"),
    ),
    (
        "a console PATCH with the same blockless body is still refused",
        ("gh api repos/" + GH_REPO + "/pulls/591 -X PATCH -f body='prose only'"),
    ),
    (
        "a submodule PATCH beside a console one: the console one is judged",
        (
            "gh api repos/"
            + RENET_REPO
            + "/pulls/113 -X PATCH -f body=x; "
            + "gh api repos/"
            + GH_REPO
            + "/pulls/591 -X PATCH -f body=y"
        ),
    ),
    (
        "a submodule edit by --repo",
        ("gh pr edit 113 --repo " + RENET_REPO + ' --body "prose only"'),
    ),
    ("a submodule edit by -R", ("gh pr edit 89 -R " + ACCOUNT_REPO + ' --body "prose only"')),
    # 2026-10-07 (#8ed364fe): every spelling gh accepts means what gh makes of it.
    ("a submodule edit by -R=", ("gh pr edit 89 -R=" + ACCOUNT_REPO + ' -b "prose only"')),
    ("a PATCH spelled -XPATCH", "gh api repos/o/r/pulls/42 -XPATCH -f body='prose only'"),
    ("a PATCH spelled --method=PATCH", "gh api repos/o/r/pulls/42 --method=PATCH -fbody=x"),
    ("a PATCH by --raw-field=body=", "gh api repos/o/r/pulls/42 -X PATCH --raw-field=body=x"),
    (
        "a PATCH of a review's own body is not the PR body",
        "gh api repos/o/r/pulls/42/reviews/9 -X PATCH -f body=x",
    ),
    ("a console edit by --repo", ("gh pr edit 591 --repo " + GH_REPO + ' --body "prose only"')),
    (
        "a submodule create",
        ("gh pr create --repo " + ELITE_REPO + ' --title t --body "prose only"'),
    ),
    (
        "a submodule create does not excuse a console edit beside it",
        ("gh pr create --repo " + RENET_REPO + ' --body "x" && gh pr edit 5 --body "y"'),
    ),
]


def _root(ev):
    return ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])


# `https://github.com/<owner>/<repo>.git` or `git@github.com:<owner>/<repo>.git` on a `url =` line.
GITMODULE_URL = re.compile(
    r"^\s*url\s*=\s*\S*?github\.com[:/]([^/\s]+/[^/\s]+?)(\.git)?/?\s*$", re.MULTILINE
)


def _slug(repo):
    """`[HOST/]OWNER/REPO[.git]`, quoted or not, as a lowercase `owner/repo`."""
    parts = repo.strip().strip("'\"").rstrip("/").split("/")
    return "/".join(parts[-2:]).lower().removesuffix(".git") if len(parts) >= 2 else ""


def _blockless_repos(root):
    """The repos whose PR bodies carry NO generated block: this checkout's submodules.

    Every generated section is written by console tooling into the CONSOLE PR: `worklist-epics` by sync-epic-block.sh from `agent/pr/<branch>.md`, which only the console tree has, and `pushed-head` by the post-bash refresh hook, which resolves the PR from the project root's own `gh repo view`. The autopilot's `autopilot-submodule-prs` block went with the autopilot (PLAN-remove-autopilot). So a
    submodule PR's body is ordinary prose, and a whole-body write to it is not the hazard this guard exists for. Measured 2026-09-30: `gh api repos/rediacc/renet/pulls/113 -X PATCH -F body=@<file>` was refused for dropping blocks renet#113 never had.

    A DENY-LIST, NOT AN ALLOW-LIST, and deliberately so: a repo this cannot name (`repos/{owner}/{repo}/...`, a fork, an unreadable `.gitmodules`) keeps the guard, because the failure the other way is a silently destroyed console block. Derived from `.gitmodules` rather than typed here, so a new submodule is covered the day it is added.
    """
    text = _read("%s/.gitmodules" % root) if root else ""
    return {_slug(m.group(1)) for m in GITMODULE_URL.finditer(text)}


def _targets_blockless(repo, root):
    return _slug(repo) in _blockless_repos(root)


def _read(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return ""


def _body_files(cmd, pattern, strip):
    """`grep -oE <pattern> | sed -E 's/<strip>//'` over the raw command."""
    return [hookio.sed_sub(strip, "", match).rstrip("\n") for match in hookio.grep_o(pattern, cmd)]


def _visible_body(cmd, seg, root):
    """Read whatever body text this command makes visible.

    --body is in the command, --body-file is on disk. Shared by both arms, because both ask the same question: does the body this call writes carry the block? Content, unlike flags, is read from the RAW command, since a quoted body may itself contain a separator and a segment would truncate it.
    """
    body = cmd if shellscan.flag_present(seg, "body") else ""
    saw_file = False
    for name in _body_files(cmd, BODY_FILE_ARGS, hookio.rx(r"^--body-file([{S}]+|=)")):
        if name in {"", "-"}:
            continue
        for cand in (name, "%s/%s" % (root, name)):
            if pathlib.Path(cand).is_file():
                body = body + "\n" + hookio._command_substitution(_read(cand))
                saw_file = True
                break
    return body, saw_file


# ---- ONE BODY READER FOR EVERY `gh pr create|edit` SPELLING (#09c80388) --
# The text reader above keyed on the LONG flag names only, so on 2026-10-07 the dispatcher returned rc=2 for `gh pr create --body 'prose only'` and rc=0 for `gh pr create -F <file of the same prose>`: gh spells `--body-file` as `-F` and `--body` as `-b`, and neither short form was ever read. The same probe found two more ways the verdict depended on the spelling rather than the
# body: `--body-file -` fed by a heredoc admitted prose the `--body` form refused, and a `--body-file` that an EARLIER clause of the same command writes was judged on the bytes an earlier command left on disk, so `<write the block> > b.md && gh pr create --body-file b.md` was refused over a stale `b.md` (the original #c17c47c3 symptom) and the reverse admitted a stale block.
# The reader below parses the walked argv the way gh's pflag does, resolves a relative path from the directory THAT gh runs in, reads `-` from the heredoc or here-string attached to that very call, and reports an earlier write instead of reading through it, the convention `commit_policy.written_message_files` set for `git commit -F`.

# Which of gh's body flags carries text and which a file to read; their spellings are `shellscan.gh_args`'s business (`-b`, `-bX`, `-b=X`, `-dF X`, and a value-taking flag's value never read as a flag).
BODY_KINDS = {"body": "text", "body-file": "file"}


class Body:
    """What one `gh pr create|edit` call would send as its body.

    `text` is everything readable, `flagged` whether any body flag is present at all, `opaque` whether some source could not be read (a missing file, a path behind an unset variable, a piped stdin), and `written` the `shellscan.Mutator` of an earlier clause that writes a body file, None when nothing does.
    """

    __slots__ = ("flagged", "opaque", "text", "written")

    def __init__(self):
        self.text = ""
        self.flagged = False
        self.opaque = False
        self.written = None


def body_sources(argv):
    """`[(kind, value)]` for every body flag in a walked `gh pr <verb> ...` argv (`argv[0]` is `pr`), kind `text` or `file`, in order, read by `shellscan.gh_args`."""
    return [(BODY_KINDS[n], v) for n, v in shellscan.gh_args(argv).flags if n in BODY_KINDS]


def _is_gh_pr(verb):
    def check(words):
        values = [shellscan._word_value(w) for w in words]
        return shellscan._base(values[0]) == "gh" and shellscan.gh_args(values[1:]).command == (
            "pr",
            verb,
        )

    return check


def _stdin_of(cmd, run, verb):
    """The heredoc and here-string bodies attached to THIS walked `gh pr <verb>`, [] when none is (a pipe, or no stdin at all)."""
    try:
        segments = commit_policy.target_segments(cmd, _is_gh_pr(verb))
    except Exception:  # noqa: BLE001 -- an unlexable command has no readable heredoc
        return []
    # Paired in order, as `commit_policy._stdin_messages` pairs commits, so two creates in one command each get their own heredoc.
    unpaired = list(segments)
    for other in shellscan.gh_pr_runs(cmd, verb):
        want = [other.name, *other.argv]
        match = next((s for s in unpaired if s.words == want), None)
        if match is not None:
            unpaired.remove(match)
        if other is run:
            return match.stdin if match is not None else []
    return []


def _expand(cmd, verb, name):
    """`name` with `$VAR`/`${VAR}` replaced from plain assignments made before `verb`; None while anything stays unexpanded."""
    values = shellscan.assignments_before(cmd, verb)

    def sub(match):
        key = match.group(1) or match.group(2)
        return values.get(key, match.group(0))

    out = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", sub, name)
    return None if ("$" in out or "`" in out) else out


def _written_by_earlier(cmd, verb, name, path, base):
    """The earlier clause of `cmd` that writes the body file `name` (at `path`), None when none does. The two matches `commit_policy.written_message_files` makes: the name as spelled, or the same resolved path."""
    for m in shellscan.earlier_mutators(cmd, verb, {"redirect"}):
        if not m.target:
            continue
        target = _expand(cmd, verb, m.target) or m.target
        if name in (m.target, target):
            return m
        full = target if target.startswith("/") else os.path.join(base, target)
        if os.path.normpath(full) == path:
            return m
    # A `tee`, which `earlier_mutators` does not model, counted only BEFORE the verb: `shellscan.writes_file` reads the whole line, so a write after the call (which cannot change what it reads) would be refused too.
    words = verb.split()
    for run in commit_policy.runs(cmd):
        if shellscan._base(run.name) == words[0] and run.argv[: len(words) - 1] == words[1:]:
            break
        if shellscan._base(run.name) != "tee":
            continue
        for arg in (a for a in run.argv if not a.startswith("-")):
            full = arg if arg.startswith("/") else os.path.join(base, arg)
            if name == arg or os.path.normpath(full) == path:
                return shellscan.Mutator("redirect", "tee %s" % arg, arg)
    return None


def read_body(cmd, run, verb, base):
    """The `Body` one walked `gh pr <verb>` run would send. `base` is the directory the command starts in."""
    body = Body()
    full_verb = "gh pr %s" % verb
    parts = []
    for kind, value in body_sources(run.argv):
        body.flagged = True
        if kind == "text":
            parts.append(value)
            continue
        if value in commit_policy.STDIN_NAMES:
            fed = _stdin_of(cmd, run, verb)
            if fed:
                parts.extend(fed)
            else:
                body.opaque = True
            continue
        name = _expand(cmd, full_verb, value)
        if not name:
            body.opaque = True
            continue
        path = os.path.normpath(
            name if name.startswith("/") else os.path.join(commit_policy.run_dir(run, base), name)
        )
        written = _written_by_earlier(cmd, full_verb, value, path, base)
        if written is not None:
            body.written = body.written or written
            continue
        if not pathlib.Path(path).is_file():
            body.opaque = True
            continue
        parts.append(_read(path))
    body.text = "\n".join(parts)
    return body


WRITTEN_BODY = """BLOCKED: nothing in this command ran, including `%(mutator)s`.

Every pre-bash guard runs ONCE, before the first clause. This `gh pr %(verb)s` reads
its body from a file that `%(mutator)s`, an earlier clause of this same command,
writes, so the bytes on disk now are an earlier command's and judging them says
nothing about the body the PR would get.

Run `%(mutator)s` as its own call, then `gh pr %(verb)s`.
"""


def _judged_runs(cmd, verb, root, cwd):
    """The walked `gh pr <verb>` calls this guard judges: every one whose repository carries the generated block, its repo read from that call (`shellscan.gh_run_repo`, so `-R=x`, `-Rx` and a quoted `--repo` all count). None when the walk finds no such call at all, and the caller falls back to the text segment."""
    runs = shellscan.gh_pr_runs(cmd, verb)
    if not runs:
        return None
    return [r for r in runs if not _targets_blockless(shellscan.gh_run_repo(r, cwd), root)]


def _judged_body(cmd, seg, verb, root, base, runs):
    """The `Body` the judged `gh pr <verb>` calls (`runs`, from `_judged_runs`) would send, read by `read_body`.

    The walk is the reader. Only a command the walk finds no such call in (`runs` is None: a shape the lexer does not model) falls back to the text reader `_visible_body`, judged on the long flag names alone, as before.
    """
    if runs is None:
        body = Body()
        body.flagged = shellscan.flag_present(seg, "body") or shellscan.flag_present(
            seg, "body-file"
        )
        body.text, saw_file = _visible_body(cmd, seg, root)
        body.opaque = (
            shellscan.flag_present(seg, "body-file")
            and not saw_file
            and not shellscan.flag_present(seg, "body")
        )
        return body
    out = Body()
    texts = []
    for run in runs:
        one = read_body(cmd, run, verb, base)
        out.flagged = out.flagged or one.flagged
        out.opaque = out.opaque or one.opaque
        out.written = out.written or one.written
        texts.append(one.text)
    out.text = "\n".join(texts)
    return out


# The PR endpoint a whole-body PATCH names: `repos/<owner>/<repo>/pulls/<n>` and nothing below it (a review or a comment has a body of its own).
API_PR_ENDPOINT = re.compile(r"^repos/([^/]+)/([^/]+)/pulls/[0-9]+$")


def _patch_call(cmd, scan, root, cwd=""):
    """`(body file names, PR ref)` for the whole-body PATCHes `cmd` sends to a PR that carries generated blocks, None when it sends none.

    Read from each walked `gh api` call by `shellscan.gh_args`, so `-XPATCH`, `--method=PATCH`, `-Fbody=@f`, `--field=body=@f`, `-fbody=x` and `--input=f` are the PATCH and the body they are (measured 2026-10-07: every one of those spellings walked past the text reader below, which the long spellings could not). Only a command the walk finds no `gh api` call in keeps the text reader.
    """
    calls = shellscan.gh_runs(cmd, ("api",))
    if not calls:
        return _patch_call_text(scan, root)
    names: list[str] = []
    refs: list[str] = []
    for call in calls:
        parsed = shellscan.gh_args(call.argv)
        # gh fills `{owner}`/`{repo}` from `--repo`, then `GH_REPO`, then the checkout's remote: the same order `gh_run_repo` reads, so `GH_REPO=rediacc/renet gh api 'repos/{owner}/{repo}/pulls/5'` is a renet PR (#d2d5f89d).
        endpoint = shellscan.gh_api_endpoint(parsed)
        if "{owner}" in endpoint or "{repo}" in endpoint:
            endpoint = shellscan.gh_api_endpoint(parsed, shellscan.gh_run_repo(call, cwd))
        m = API_PR_ENDPOINT.match(endpoint)
        if not m or shellscan.gh_api_method(parsed) != "PATCH":
            continue
        # The endpoint names its own repo, so a PATCH to a submodule PR leaves the arm here, call by call: `repos/rediacc/renet/pulls/113` beside `repos/rediacc/console/pulls/591` on one command still has the console one judged.
        if _targets_blockless("%s/%s" % (m.group(1), m.group(2)), root):
            continue
        fields = [
            v for n, v in parsed.flags if n in ("field", "raw-field") and v.startswith("body=")
        ]
        inputs = parsed.values("input")
        if not fields and not inputs:
            continue
        refs.append(m.group(0))
        # `-F body=@<path>` reads a file (`-f body=@x` is the literal text "@x", carried in the command and judged there); `--input <path>` is the whole request body.
        names.extend(
            v[len("body=@") :]
            for n, v in parsed.flags
            if n == "field" and v.startswith("body=@") and v != "body=@"
        )
        names.extend(i for i in inputs if i)
    if not refs:
        return None
    return names, refs[0]


def _patch_call_text(scan, root):
    """`_patch_call` for a command the walk finds no `gh api` call in: the long spellings, by regex over the segments, as before 2026-10-07."""
    split = hookio.sed_sub(r"[;&|()`]", "\n", scan)
    lines = hookio.grep_lines(API_VERB, split)
    lines = [line for line in lines if hookio.grep_q_line(API_PULLS, line)]
    lines = [line for line in lines if hookio.grep_q_line(API_PATCH, line)]
    lines = [
        line
        for line in lines
        if not any(
            _targets_blockless(ref.split("/")[1] + "/" + ref.split("/")[2], root)
            for ref in hookio.grep_o(API_PR_REF, line + "\n")
        )
    ]
    api_segs = hookio._command_substitution(hookio._grep_out(lines))
    if not (api_segs and hookio.grep_q(API_BODY_FLAG, api_segs)):
        return None
    names = [
        n
        for n in _body_files(
            api_segs,
            API_BODY_ARGS,
            hookio.rx(r"^((-F|--field)[{S}]+body=@|--input([{S}]+|=))"),
        )
        if n != ""
    ]
    refs = hookio.grep_o(API_PR_REF, api_segs)
    return names, refs[0] if refs else ""


def _carries(marker, body):
    return hookio.grep_q("<!-- %s:begin -->" % marker, body, fixed=True)


def _has_every_marker(body):
    return all(_carries(m, body) for m in GENERATED_MARKERS)


def _live_body(ref):
    """The PR's CURRENT description, or None when it cannot be read.

    `want_rc=True` is the whole point: `gh` failing and a PR whose body is empty both print nothing, and only one of them is an answer. An unreadable body means the guard cannot tell what the write would drop, so it keeps refusing.
    """
    return hookio.run_out(["gh", "api", ref, "--jq", ".body"], want_rc=True)


def _would_drop(body, ref):
    """The generated markers this write would really remove from the live description.

    A MARKER THE LIVE BODY DOES NOT CARRY CANNOT BE DROPPED BY REPLACING IT, and until 2026-09-23 this guard did not ask. `GENERATED_MARKERS` is the set this repo CAN generate, not the set any given PR has: `pushed-head` is written by the post-bash refresh hook after a push, so a PR created and not yet pushed to has no such section at all. Measured that day on PR #590, whose
    body carried `worklist-epics` and nothing else: every route to removing one bad line from its description was refused for dropping a block that was never there, and the only doors left were the GitHub UI, which an agent does not have, and closing and reopening the PR.

    THE FILE'S OWN HEADER ALREADY RECORDED THIS BITE ONCE, on 2026-09-03 -- "a PR body had to lose a footer that check-claude-attribution.sh refuses, the corrected body kept the block, and the only routes left were the GitHub UI or closing and reopening the PR" -- and the note was written as an accepted cost rather than as a defect. It came back, through the same door, for the
    same reason.
    """
    missing = [m for m in GENERATED_MARKERS if not _carries(m, body)]
    if not missing:
        return []
    live = _live_body(ref) if ref else None
    if live is None:
        return missing
    return [m for m in missing if _carries(m, live)]


def run(ev):
    cmd = ev.raw("tool_input", "command")

    # ANCHORED AT COMMAND POSITION, not matched anywhere on the line.
    #
    # The first version grepped the raw string and blocked `echo "never use gh pr edit --body by hand"`, which is prose ABOUT the rule, not a violation of it. block-commit-meta.sh's header names that failure exactly: "a guard whose only failure mode is refusing CORRECT input teaches people to reword honest messages until it stops complaining." lib/command-scan.sh already solves
    # this, and block-second-open-pr.sh uses the same two calls for `gh pr create`.
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    # The sanctioned tool is allowed to do exactly what it exists to do.
    if hookio.grep_q("sync-epic-block.sh", cmd, fixed=True):
        return hookio.ALLOW

    # ORDER MATTERS: the edit arm runs FIRST. One command can do both, and the create arm below exits 0 on a body that already carries the block -- so with create checked first, `gh pr create --fill && gh pr edit N --body-file b.md` would take that exit and never reach the edit refusal, which applies whether or not the block is there. THE FLAG BELONGS TO ITS OWN INVOCATION, and
    # reading it line-wide is the same scope bug hook_gh_pr_segment was written for. `gh pr create --body "<a body that carries the block>" && gh pr edit N --add-label x` is entirely legal, and a line-wide `--body` test refuses it -- the edit verb is present, the flag is present, and they belong to different commands. Scope both arms to segments.
    #
    # `X=$(cmd && other)` in the bash: when the position test fails the `&&`
    # short-circuits and the substitution is EMPTY, which is what the later `[ -n "$EDIT_SEG" ]` reads. Reproduced as the empty string, not as None.
    edit_seg = (
        hookio._command_substitution(shellscan.gh_pr_segment(scan, "edit"))
        if shellscan.gh_pr_at_command_pos(scan, "edit")
        else ""
    )
    create_seg = (
        hookio._command_substitution(shellscan.gh_pr_segment(scan, "create"))
        if shellscan.gh_pr_at_command_pos(scan, "create")
        else ""
    )

    root = _root(ev)

    # A SUBMODULE PR CARRIES NO GENERATED BLOCK, so neither pr arm applies to one (`_blockless_repos`). The repo is read from each walked call (`_judged_runs`): `--repo`/`-R` in any spelling gh accepts, then a `cd` into private/<submodule>, then the cwd's origin, then rediacc/console. Only a command the walk finds no call in keeps the text reader, `shellscan.target_repo` over the
    # segment. Dropping the call rather than returning ALLOW keeps the other arms running, so `gh pr create --repo rediacc/renet ... && gh pr edit 5 --body x` is still judged on its console edit.
    edit_runs = _judged_runs(cmd, "edit", root, ev.cwd or "")
    create_runs = _judged_runs(cmd, "create", root, ev.cwd or "")
    if edit_runs is not None:
        edit_seg = edit_seg or "gh pr edit"
        if not edit_runs:
            edit_seg = ""
    elif edit_seg != "" and _targets_blockless(
        shellscan.target_repo(edit_seg, scan, ev.cwd or ""), root
    ):
        edit_seg = ""
    if create_runs is not None:
        create_seg = create_seg or "gh pr create"
        if not create_runs:
            create_seg = ""
    elif create_seg != "" and _targets_blockless(
        shellscan.target_repo(create_seg, scan, ev.cwd or ""), root
    ):
        create_seg = ""

    # THE EDIT ARM CHECKS EVERY GENERATED MARKER, NOT JUST THE EPIC ONE. Corrected 2026-09-03, same day, after the narrowing below was written and its own test refused it. The narrowing said an edit carrying `worklist-epics` "cannot drop the block" and is therefore as safe as a create. That was half the picture: `gh pr edit --body` replaces the WHOLE body, and this repo's PR bodies
    # carry a SECOND generated section, `<!-- pushed-head:begin -->`. A body carrying only the epic block passes the narrowed check and silently destroys the pushed-head section -- which is exactly the class of loss this guard exists to prevent, arriving through the door the narrowing opened.
    #
    # So the test that failed was right and the narrowing was wrong. The rule is now: an edit is permitted only when its body carries EVERY marker this repo generates. That keeps the real case the narrowing was written for (fix the prose, leave the machine sections alone) and refuses the case it accidentally allowed. That refusal is the failure mode this file's own header names,
    # quoting block-commit-meta.sh: "a guard whose only failure mode is refusing CORRECT input teaches people to route around it." It bit for real: a PR body had to lose a footer that check-claude-attribution.sh refuses, the corrected body kept the block, and the only routes left were the GitHub UI (unavailable to an agent) or closing and reopening the PR.
    #
    # The asymmetry with create that REMAINS is deliberate and is the whole safety argument: create may write an UNREADABLE body (a heredoc, a file a later step writes) because there is no block yet to destroy. Edit may not -- an unreadable edit body is refused, because it can silently replace one that exists.
    base = ev.field("cwd") or ev.cwd
    if edit_seg != "":
        edit_body = _judged_body(cmd, edit_seg, "edit", root, base, edit_runs)
        if edit_body.flagged:
            if edit_body.written is None and _has_every_marker(edit_body.text):
                return hookio.ALLOW
            # An earlier clause writing the body file is unreadable here, and an unreadable edit body is refused; the preamble says which clause, so the fix is visible.
            ev.warn_raw(
                shellscan.split_refusal(
                    [edit_body.written] if edit_body.written else [], "gh pr edit", "the body file"
                )
            )
            ev.warn_raw(REFUSE_WHOLE_BODY)
            return hookio.DENY

    # ---- the SANCTIONED body write is a whole-body write too --------------- block-adhoc-sanctioned.sh refuses `gh pr edit --body` (it exits 1 on the deprecated projectCards GraphQL field with the body UNCHANGED) and prescribes
    # `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>` instead. That form
    # replaces the whole body exactly as `gh pr edit --body` does, and until 2026-09-04 it walked past this guard unread: this file's own message pointed at `gh pr edit --body-file`, the sanctioned guard refused that, and the door it pointed to instead had no marker check at all. Same rule as the edit arm: every generated marker must be visible in the body this call writes, and an
    # unreadable body is refused, because it can silently replace one that exists.
    patch = _patch_call(cmd, scan, root, ev.cwd or "")
    if patch is not None:
        names, ref = patch
        patch_body = cmd
        saw = False
        need = False
        written = None
        for name in names:
            need = True
            # Same class as the create arm's earlier write (#09c80388): a body file this command writes first is an earlier command's bytes, so it is not read, and an unreadable PATCH body is refused, naming the write.
            path = os.path.normpath(name if name.startswith("/") else os.path.join(base, name))
            written = written or _written_by_earlier(cmd, "gh api", name, path, base)
            if written is not None:
                continue
            for cand in (name, "%s/%s" % (root, name)):
                if pathlib.Path(cand).is_file():
                    saw = True
                    patch_body = patch_body + "\n" + hookio._command_substitution(_read(cand))
                    break
        readable = not (need and not saw) and written is None
        patch_ok = readable and _has_every_marker(patch_body)
        # THE LIVE BODY IS CONSULTED ONLY FOR THIS ARM, and only once the static rule has already said no, which is what keeps the lookup off the common path and out of every case that never needed it. Two reasons it is this arm rather than both: this is the door the message above prescribes, and the `gh pr edit --body`/`--body-file` door is refused one guard earlier by
        # block-adhoc-sanctioned.sh (ORDER 32 against this file's 36) on the deprecated projectCards field, so its copy of the over-block is unreachable.
        #
        # A WRITE CARRYING NO GENERATED MARKER AT ALL IS STILL REFUSED WITHOUT ASKING GitHub. That is a hand-written body, the thing this guard exists for, and it is also every negative case in the suite: making the verdict depend on a network read there would trade a deterministic refusal for one that answers differently depending on what a PR looks like today.
        if not patch_ok and readable and any(_carries(m, patch_body) for m in GENERATED_MARKERS):
            patch_ok = not _would_drop(patch_body, ref)
        if patch_ok:
            return hookio.ALLOW
        ev.warn_raw(
            shellscan.split_refusal([written] if written else [], "gh api", "the body file")
        )
        ev.warn_raw(REFUSE_WHOLE_BODY)
        return hookio.DENY

    # ---- `gh pr create` was the hole, and it is the one that bit -----------
    # Measured 2026-08-27: this guard returned rc=0 for every `gh pr create --body`
    # shape and rc=2 for the matching `edit` ones. The operator's symptom -- "why
    # don't I see the epics in the PR description?" -- came in through create, not edit, and the guard was looking only at the door nobody used.
    #
    # create is NOT refused outright, because it is the one call that legitimately writes a whole body: there is no block yet to destroy. It is refused only when the body it writes does NOT already carry the block, which is precisely the state CI fails on minutes later. A body that carries it passes untouched, so the sanctioned flow (build the body from the snapshot, create with
    # it) is not in this guard's way at all.
    if create_seg != "":
        body = _judged_body(cmd, create_seg, "create", root, base, create_runs)
        if not body.flagged:
            return hookio.ALLOW

        # A body file an EARLIER clause of this command writes holds an earlier command's bytes. Reading them refused `<block> > b.md && gh pr create --body-file b.md` over a stale b.md and admitted the reverse (#c17c47c3); it is refused unread, naming the write, as `commit_policy.written_message_refusal` refuses a `git commit -F` file. Run apart, the same file is read and judged.
        if body.written is not None:
            ev.warn_raw(WRITTEN_BODY % {"mutator": body.written.label, "verb": "create"})
            return hookio.DENY

        if hookio.grep_q(BEGIN_MARKER, body.text, fixed=True):
            return hookio.ALLOW

        # What cannot be read is allowed, the readability rule block_untagged_commit set: a --body-file naming a path that does not exist, a path behind a variable no earlier assignment sets, a `--body-file -` fed by a pipe. CI still gates the result.
        if body.opaque:
            return hookio.ALLOW

        ev.warn_raw(
            "BLOCKED: this `gh pr create` body carries no worklist-epics block.\n"
            "\n"
            "The description is generated content: CI's check:ci-pr-epic-block diffs the\n"
            "`%s` block against agent/pr/<branch>.md. Creating the PR with a\n"
            "hand-written body means the block is absent from the moment the PR exists, and\n"
            "the first anyone hears of it is a red gate several minutes later.\n"
            "\n"
            "Create it, then sync the block in the same breath:\n"
            "\n"
            "  .claude/hooks/stop/worklist.py --publish <me> <branch>   # refresh the snapshot\n"
            '  gh pr create --draft --title "..." --body "..."          # your prose\n'
            "  .ci/scripts/pr/sync-epic-block.sh <pr> <branch>          # add the block\n"
            "\n"
            "A body that already contains the block is NOT refused, so building the body\n"
            "from the snapshot first works too.\n" % BEGIN_MARKER
        )
        return hookio.DENY

    return hookio.ALLOW
