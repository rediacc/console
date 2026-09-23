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
    are not model Bash calls and never reach this chain.

=============================================================================
PORT NOTE: A DEAD VARIABLE, REPRODUCED RATHER THAN REPAIRED
=============================================================================

The bash declares `HOOK_SAW_BODY_FILE=0` and sets it to 1 inside
`hook_visible_body`. That function is only ever called in a command substitution, so the assignment happens in a SUBSHELL and cannot reach the caller; and nothing reads the variable afterwards in any case. It is dead twice over. The port keeps neither the variable nor a Python stand-in for it, because reproducing a value nobody reads would be reproducing nothing, and the record of
why it is gone is this paragraph. Reported as a finding rather than fixed in the bash, which must stay byte-identical until the P6 cutover.
"""

import pathlib

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-raw-pr-body-edit.sh"
ORDER = 37

# The `gh api ... -X PATCH -F body=` arm, added 2026-09-04. Without it the door
# this file's own message points people at has no marker check, which is exactly the state it was in until that day.
DEFECT = ("if api_segs and hookio.grep_q(", "if False and hookio.grep_q(")

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
]


def _root(ev):
    return ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])


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

    # THE EDIT ARM CHECKS EVERY GENERATED MARKER, NOT JUST THE EPIC ONE. Corrected 2026-09-03, same day, after the narrowing below was written and its own test refused it. The narrowing said an edit carrying `worklist-epics` "cannot drop the block" and is therefore as safe as a create. That was half the picture: `gh pr edit --body` replaces the WHOLE body, and this repo's PR bodies
    # carry a SECOND generated section, `<!-- pushed-head:begin -->`. A body carrying only the epic block passes the narrowed check and silently destroys the pushed-head section -- which is exactly the class of loss this guard exists to prevent, arriving through the door the narrowing opened.
    #
    # So the test that failed was right and the narrowing was wrong. The rule is now: an edit is permitted only when its body carries EVERY marker this repo generates. That keeps the real case the narrowing was written for (fix the prose, leave the machine sections alone) and refuses the case it accidentally allowed. That refusal is the failure mode this file's own header names,
    # quoting block-commit-meta.sh: "a guard whose only failure mode is refusing CORRECT input teaches people to route around it." It bit for real: a PR body had to lose a footer that check-claude-attribution.sh refuses, the corrected body kept the block, and the only routes left were the GitHub UI (unavailable to an agent) or closing and reopening the PR.
    #
    # The asymmetry with create that REMAINS is deliberate and is the whole safety argument: create may write an UNREADABLE body (a heredoc, a file a later step writes) because there is no block yet to destroy. Edit may not -- an unreadable edit body is refused, because it can silently replace one that exists.
    if edit_seg != "" and (
        shellscan.flag_present(edit_seg, "body") or shellscan.flag_present(edit_seg, "body-file")
    ):
        edit_body, _ = _visible_body(cmd, edit_seg, root)
        if _has_every_marker(edit_body):
            return hookio.ALLOW
        ev.warn_raw(REFUSE_WHOLE_BODY)
        return hookio.DENY

    # ---- the SANCTIONED body write is a whole-body write too --------------- block-adhoc-sanctioned.sh refuses `gh pr edit --body` (it exits 1 on the deprecated projectCards GraphQL field with the body UNCHANGED) and prescribes
    # `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>` instead. That form
    # replaces the whole body exactly as `gh pr edit --body` does, and until 2026-09-04 it walked past this guard unread: this file's own message pointed at `gh pr edit --body-file`, the sanctioned guard refused that, and the door it pointed to instead had no marker check at all. Same rule as the edit arm: every generated marker must be visible in the body this call writes, and an
    # unreadable body is refused, because it can silently replace one that exists.
    split = hookio.sed_sub(r"[;&|()`]", "\n", scan)
    lines = hookio.grep_lines(API_VERB, split)
    lines = [line for line in lines if hookio.grep_q_line(API_PULLS, line)]
    lines = [line for line in lines if hookio.grep_q_line(API_PATCH, line)]
    api_segs = hookio._command_substitution(hookio._grep_out(lines))
    if api_segs and hookio.grep_q(API_BODY_FLAG, api_segs):
        patch_body = cmd
        saw = False
        need = False
        for name in _body_files(
            api_segs,
            API_BODY_ARGS,
            hookio.rx(r"^((-F|--field)[{S}]+body=@|--input([{S}]+|=))"),
        ):
            if name == "":
                continue
            need = True
            for cand in (name, "%s/%s" % (root, name)):
                if pathlib.Path(cand).is_file():
                    saw = True
                    patch_body = patch_body + "\n" + hookio._command_substitution(_read(cand))
                    break
        readable = not (need and not saw)
        patch_ok = readable and _has_every_marker(patch_body)
        # THE LIVE BODY IS CONSULTED ONLY FOR THIS ARM, and only once the static rule has already said no, which is what keeps the lookup off the common path and out of every case that never needed it. Two reasons it is this arm rather than both: this is the door the message above prescribes, and the `gh pr edit --body`/`--body-file` door is refused one guard earlier by
        # block-adhoc-sanctioned.sh (ORDER 33 against this file's 37) on the deprecated projectCards field, so its copy of the over-block is unreachable.
        #
        # A WRITE CARRYING NO GENERATED MARKER AT ALL IS STILL REFUSED WITHOUT ASKING GitHub. That is a hand-written body, the thing this guard exists for, and it is also every negative case in the suite: making the verdict depend on a network read there would trade a deterministic refusal for one that answers differently depending on what a PR looks like today.
        if not patch_ok and readable and any(_carries(m, patch_body) for m in GENERATED_MARKERS):
            ref = hookio._command_substitution("\n".join(hookio.grep_o(API_PR_REF, api_segs)))
            patch_ok = not _would_drop(patch_body, ref.split("\n")[0] if ref else "")
        if patch_ok:
            return hookio.ALLOW
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
        if not (
            shellscan.flag_present(create_seg, "body")
            or shellscan.flag_present(create_seg, "body-file")
        ):
            return hookio.ALLOW

        # What body text can we actually see? Same readability rule as block-untagged-commit.sh: judge what can be read, ALLOW what cannot, rather than refusing blind.
        body, saw_file = _visible_body(cmd, create_seg, root)

        # A --body-file naming a path that does not exist yet (written by a later step of the same command, or by a heredoc this scan stripped) is genuinely unreadable. Allow it; CI still gates the result.
        if (
            shellscan.flag_present(create_seg, "body-file")
            and not saw_file
            and not shellscan.flag_present(create_seg, "body")
        ):
            return hookio.ALLOW

        if hookio.grep_q(BEGIN_MARKER, body, fixed=True):
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
