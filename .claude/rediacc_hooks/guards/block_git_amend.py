"""Block `git commit --amend` for PR babysitting.

WHY THE HEREDOC STRIPPING. The first version grepped the raw command text, so
it fired on any command that merely CONTAINED the phrase -- including
`cat > RULES.md <<'EOF'` writing documentation that explains this very rule.
A guard that blocks you from documenting it is a false positive, and false
positives are how guards get disabled.

The strip is deliberately narrow: only heredocs introduced by `cat` or `tee`,
which write bytes and cannot execute them. A heredoc fed to an INTERPRETER
(`bash <<EOF ... EOF`) really can run the command, so those bodies are left
in place and still match. Widening this to all heredocs would open exactly
that hole.

PORT NOTE ON WHY THIS FILE HAS ITS OWN STRIPPER. `shellscan._strip_heredocs`
looks like the same function and is not: it strips EVERY heredoc, closes the
body on a REGEX built from the marker, and knows nothing about who is writing.
This one strips only a `cat`/`tee` heredoc and closes it on an exact string
comparison (`term == delim` in the awk). Both differences are load-bearing
here, so the awk is ported rather than replaced, and the two live side by side
exactly as the bash's own comment below says they must.
"""

import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-git-amend.sh"
ORDER = 18

# BUT STRIPPING QUOTES ALONE OPENS AN EVASION: without the wrapper payload
# appended, `sh -c "git commit --amend"` has the whole command inside a quoted
# span, the span is removed, and the guard returns 0.
DEFECT = (r'"%s\n%s" % (stripped, wrapped)', r'"%s\n%s" % (stripped, "")')

# ANCHORED TO COMMAND POSITION 2026-08-28, after check:ci-guard-mention-anchoring
# found this guard refusing an ordinary sentence. Matching the phrase ANYWHERE
# means a doc line, a worklist note or an `echo` explaining the rule is refused
# as if it were the rule being broken. This NARROWS PROSE ONLY: every control
# below still blocks the real command, at line start and after a separator.
AMEND = (
    r"(^|[;&|(])["
    + hookio.SPACE
    + r"]*git commit[^|;&]*--amend|(^|[;&|(])["
    + hookio.SPACE
    + r"]*git commit[^|;&]*["
    + hookio.SPACE
    + r"]-[a-zA-Z]*amend"
)

MESSAGE = (
    "❌ BLOCKED: Do not use 'git commit --amend' for PR babysitting. Amending rewrites the "
    "existing PR commit in place, which collapses every CI fix into one commit and destroys "
    "the per-change history (this PR's single commit was already amended 16 times and the "
    "individual changes became impossible to trace). Make EACH fix a NEW commit: git commit "
    "-m 'fix(scope): ...' then a plain 'git push'. The reviewer needs a readable per-commit "
    "trail. If commits genuinely need squashing, that is the user's call at merge time, not "
    "yours."
)

EDGE_CASES = [
    ("the plain shape", "git commit --amend --no-edit"),
    ("the bundled short flag", "git commit -am amend"),
    ("after a separator", "true; git commit --amend"),
    # The two false-positive classes, and the evasion that closing the first
    # one opened.
    (
        "a cat heredoc documenting the rule is data",
        "cat > RULES.md <<'EOF'\ngit commit --amend\nEOF",
    ),
    (
        "a tab-indented terminator really closes the body",
        "cat > R.md <<-'EOF'\n\tgit commit --amend\n\tEOF\ngit commit --amend",
    ),
    (
        "an INTERPRETER heredoc still executes, so it still matches",
        "bash <<EOF\ngit commit --amend\nEOF",
    ),
    ("quoted prose is not a command", "echo 'git commit --amend'"),
    ("a wrapper payload is still scanned", 'sh -c "git commit --amend"'),
    ("an ordinary commit", "git commit -m 'fix(cli): x'"),
]


def _strip_cat_heredocs(text):
    """The awk pass, record for record.

    PORT NOTE ON THE `<<-` ARM, whose comment in the awk is the longest thing
    in the file and is worth carrying in full:

        `<<-` STRIPS LEADING TABS FROM THE TERMINATOR, and comparing $0 raw
        missed that: bash closes the heredoc at a tab-indented delimiter, so
        everything after it is ordinary shell again -- but this scanner stayed
        `inside` to EOF and swallowed it, taking any amend on those lines with
        it. Fail-OPEN, and the whole point of the scanner is to see past
        heredocs, so it undid the guard rather than degrading it.
    """
    records, _ = shellscan._records(text)
    out = []
    inside = False
    dash = False
    delim = ""
    for record in records:
        if inside:
            term = record
            if dash:
                term = re.sub(r"^\t+", "", term, count=1)
            if term == delim:
                inside = False
            continue
        line = record
        # only consider a heredoc whose writer is cat or tee
        writer = re.search(
            r"(^|[|;&" + hookio.SPACE + r"])(cat|tee)([" + hookio.SPACE + r"]|$)", line
        )
        found = re.search(r"<<-?[" + hookio.SPACE + r"]*['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?", line)
        if writer and found:
            d = found.group(0)
            # remember the tab-stripping form for the terminator match
            dash = bool(re.search(r"^<<-", d))
            d = re.sub(r"^<<-?[" + hookio.SPACE + r"]*", "", d)
            d = re.sub(r"['\"]", "", d)
            delim = d
            inside = True
        out.append(line)
    return shellscan._awk_out(out)


def run(ev):
    cmd = ev.raw("tool_input", "command")

    # Drop the bodies of cat/tee heredocs before matching.
    scan = shellscan._command_substitution(_strip_cat_heredocs(cmd))

    # QUOTED SPANS GO TOO, on top of the heredoc stripping above. The awk pass
    # handles a documented heredoc; it does nothing for `echo 'git commit
    # --amend'` or a commit message quoting the rule, both of which were refused
    # as if they were amends.
    #
    # BUT STRIPPING QUOTES ALONE OPENS AN EVASION, and the first draft of this
    # shipped it: `sh -c "git commit --amend"` has the whole command inside a
    # quoted span, so removing quotes removed the amend and the guard returned
    # 0. The comment written alongside that draft claimed the dedicated test
    # file pinned the `sh -c` case. It does not -- the file has no such case,
    # and the claim was never checked. One probe found both the false comment
    # and the hole.
    #
    # So the wrapper payload is extracted and appended, exactly as
    # hook_scan_target does for the guards that use it wholesale. This one
    # cannot use it wholesale: hook_scan_target drops heredoc BODIES, and the
    # awk pass above exists to keep a `cat <<EOF` body as docs while still
    # reading a body that would execute. Two different heredoc rules, so only
    # the wrapper half is borrowed.
    #
    # PORT NOTE: no env-prefix strip in either half, unlike `scan_target`. That
    # is the bash's own shape and not an omission here.
    wrapped = shellscan._command_substitution(
        shellscan._sed_quotes_to_spaces(shellscan._wrapper_payload(shellscan._tr(scan, "\n", " ")))
    )
    stripped = shellscan._command_substitution(
        shellscan._tr(
            shellscan._sed_strip_quoted_spans(shellscan._tr(scan, "\n", "\001")),
            "\001",
            "\n",
        )
    )
    scan = "%s\n%s" % (stripped, wrapped)

    if hookio.grep_q_line(AMEND, scan):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
