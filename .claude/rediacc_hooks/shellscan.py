#!/usr/bin/env python3
"""Shared command scanning for the gh-pr guardrail hooks (block-admin-merge,
block-nondraft-pr-create, block-premature-ready).

The old inline approach (strip every quoted span, then anchor `gh pr <verb>`
at a command position) had a review-found bypass class: stripping ALL quotes
also erases a command hidden inside a shell-execution wrapper, so
`sh -c 'gh pr merge --admin'`, `bash -c "..."`, `eval "..."`, variable
indirection (`X=--admin; gh pr merge $X`), and `--admin=true` all sailed past
the bans. The stripping exists to avoid PROSE false positives
(`git commit -m "...gh pr merge --admin..."`), so it cannot simply be
removed. This lib keeps the prose defense AND scans wrapper payloads.

scan_target builds the string the anchor runs against, from three parts:
  1. Heredoc bodies removed. A `<<MARKER ... MARKER` body is DATA, never
     executed, so dropping it is safe and kills the heredoc false positive
     (a worklist note mentioning the command used to fire the hook).
  2. Prose-stripped: quoted spans removed (multi-line aware) so quoted prose
     cannot trip the anchor.
  3. Wrapper payloads: the argument of a shell-execution wrapper
     (sh/bash/dash/zsh/ash/ksh -c, or eval) with its quotes turned to spaces,
     so the inner command lands at a command position and IS scanned.

flag_present matches a long flag in every form a shell accepts:
`--flag`, `--flag=value`, `--flag;`, and inside a quoted/assignment token,
so `--admin=true` and `X="--admin"` are caught. Combined with a
command-position verb match, over-blocking a command that both names the flag
and runs the verb is the safe direction.

=============================================================================
THIS FILE IS A TRANSLITERATION, NOT A REWRITE
=============================================================================

The original is `.claude/hooks/pre-bash/lib/command-scan.sh`, and its comments
record SIX separate rounds of bypass findings (rounds 39-40 flag shapes, 42
path-qualified shells, 44 quoted paths, 46 line-wide field scope, the
`FOO=bar ` env-prefix bypass of seven guards, and the `<<-` tab-indented
terminator). Those rounds are the specification: each one names a command that
slipped past an earlier version, and none of them is visible in the behaviour
of the current code alone. So every function below is ported line for line,
with its comment carried across in the same position relative to the code it
explains, and `tests/test_shellscan_differential.py` feeds the same corpus to
both implementations and refuses any divergence.

ONE FUNCTION IN THE ORIGINAL IS DELIBERATELY NOT PORTED: `hook_read_payload`,
added 2026-09-08. It reads the hook event body from stdin under a deadline,
because `$(cat)` and a bare `jq` reading stdin bound nothing -- a stdin that
stays open and silent blocks them forever, and in a PreToolUse hook that is not
a slow check, it is a tool call that never returns. `require-python.sh:66`
carries the measurement that settled it: with the interpreter hidden from PATH
so the arm is actually reached and stdin held open by a writer that never
writes, the unbounded form exits 124 under an external timeout against exit 2
in 0s once stdin is closed.

It has no Python counterpart and should not get one. This module is a SCANNER:
callers hand it a command string they already read. Reading stdin is the
caller's job, and the four bash entry points that do it (`hook_init` in the
original, `block-pathspecless-git-commit.sh`, `cancel-old-ci.sh`,
`refresh-pr-body.sh`) have Python siblings that receive their payload through
`rediacc_hooks.hookio` instead, which never had the unbounded form. The note
lives here rather than nowhere because the differential above checks that the
port keeps the original's dated evidence, and evidence for a function that is
absent by design still has to be answerable.

WHERE THE PYTHON LOOKS UNIDIOMATIC, IT IS ON PURPOSE. Four bash behaviours
have no natural Python spelling and are reproduced by hand rather than
improved away:

  * `$(...)` strips EVERY trailing newline from a command's output, so a
    filter's raw stdout and the value a caller sees are different strings.
    `_command_substitution` is that difference, spelled out, because the
    original's `nohd`/`stripped`/`wrapped` locals all pass through it.
  * awk, sed and grep read RECORDS, not a string. A trailing newline is a
    terminator, not a separator, and an empty input has ZERO records rather
    than one empty one. `_records` is that rule; every filter below rebuilds
    its output the way its tool does (awk always terminates a record it
    prints, GNU sed preserves a missing final newline, grep always adds one).
  * POSIX EREs are leftmost-LONGEST; Python's `re` is leftmost-first with
    backtracking. For the patterns here the two agree, and that agreement is
    an empirical claim the differential checks rather than an assumption:
    every alternation below is either mutually exclusive on its first
    character or falls through to the same branch under backtracking.
  * awk arrays are 1-based and `split` on a REGEX separator does not trim, so
    a leading space yields an empty first field. The loops below keep the
    original's index arithmetic (`j < n` meaning "not the last field") rather
    than switching to Python's slicing, because the join it controls is where
    the wrapper payload's spacing comes from.

NAMES. The bash `hook_` prefix existed because bash has one namespace. Here
the module supplies it: `hook_scan_target` is `shellscan.scan_target`,
`_hook_wrapper_payload` is `shellscan._wrapper_payload`, and so on. The
differential maps them pair by pair, so the mapping is checked and not merely
asserted here.
"""

import json
import os
import re
import subprocess

# `[[:space:]]` in the C locale, written out. Python's `\s` is Unicode-aware (it matches U+00A0 and friends), which would widen every anchor in this file against a command containing non-breaking space -- a silent behaviour change in the direction of matching MORE, which for a guard is the safe direction but is still not what the bash does.
SPACE = r" \t\n\v\f\r"
# The same class with the newline dropped, for the places where the tool works on one record at a time and a newline can therefore never be in the subject. Kept separate rather than reused so that a future edit to one is not silently a change to the other.
BLANK = r" \t\v\f\r"

SHELL_NAMES = ("sh", "bash", "dash", "zsh", "ash", "ksh")


def _records(text):
    """Split text the way awk, sed and grep read records.

    Returns `(records, terminated)`. `terminated` says whether the input's
    last record carried its newline, which is what GNU sed reproduces and awk
    does not. The empty string is ZERO records: `printf '%s' ""` gives a tool
    no input at all, so its main block never runs -- which is why an empty
    command produces an empty wrapper payload rather than an empty line.
    """
    if text == "":
        return [], False
    if text.endswith("\n"):
        return text[:-1].split("\n"), True
    return text.split("\n"), False


def _awk_out(records):
    """awk's `print` terminates every record it emits, input newline or not."""
    return "".join(record + "\n" for record in records)


def _sed_out(records, terminated):
    """GNU sed preserves a missing final newline instead of adding one."""
    if not records:
        return ""
    return "\n".join(records) + ("\n" if terminated else "")


def _grep_out(matches):
    """grep terminates every line it prints, including the last."""
    return "".join(match + "\n" for match in matches)


def _command_substitution(text):
    """`$(cmd)` strips EVERY trailing newline, not one."""
    return text.rstrip("\n")


def _here_string(text):
    """`<<<"$x"` feeds `x` plus one newline, so an empty subject is one empty
    record and not zero records. grep is then run over exactly one line.
    """
    return text + "\n"


def _tr(text, frm, to):
    """`tr` with two single characters: a 1:1 byte map, nothing else."""
    return text.replace(frm, to)


# Extract the payload of a shell-wrapper invocation (`<shell> [...anything...] -c <payload>` or `eval <payload>`) by SCANNING TOKENS for the token that actually selects -c mode, instead of enumerating flag shapes in a regex. Review findings (rounds 39-40) showed that a single regex chasing flag shapes is a losing game: bare `-c`, then bundled (`-lc`) and separate (`-eux -c`) short
# flags, then GNU long options (`--posix`, `--norc`) and value-taking short options (`-o pipefail`) each broke it in turn, and there will always be another shape. Token-scanning treats ANY intervening token as skippable and asks only "is THIS token the -c selector" -- a closed, enumerable question (`-c` exactly, or a single-dash bundle ending in `c`) -- so no flag syntax needs to
# be recognized at all. This also drops the old design's second failure mode: the extraction regex and a separate prefix-strip regex had to independently agree on the exact same shape, and
# small drift between the two was itself a bug source; this emits the payload
# directly, so there is nothing left to keep in sync.
#
# Round-42 review finding: the shell-name test required an EXACT, bare token match, so a path-qualified shell (`/bin/bash -c`, `./bash -c`) never matched -- the same enumeration trap the flag side already escaped, just moved to the shell-name side. Fixed the same way: match the BASENAME of the token (strip any leading `.*/`) rather than adding literal path prefixes as more
# alternatives. `env bash -c` was already fine (`env` isn't a shell name, so the scan naturally advances to the next bare `bash` token) -- only direct path-qualification broke it.
#
# Round-44 review finding: the basename strip alone left a QUOTED path broken -- `"/bin/bash"` has its last `/` INSIDE the quotes, so the greedy path-strip left `bash"` (trailing quote intact), which still failed the exact-match test. Fixed by also stripping quote characters from the name copy (either order works: quotes and the basename separator never overlap).
def _wrapper_payload(text):
    records, _ = _records(text)
    for record in records:
        # awk: n = split($0, tok, /[ \t]+/). A REGEX separator, so unlike the
        # default " " separator it does NOT trim: a leading blank yields an empty tok[1], and that empty token is why the join below can emit a leading space. Python's re.split on "" would give one empty field where awk gives zero, hence the guard.
        tok = re.split(r"[ \t]+", record) if record != "" else []
        n = len(tok)
        for i in range(n):
            if tok[i] == "eval":
                out = "".join(tok[j] + (" " if j < n - 1 else "") for j in range(i + 1, n))
                # awk `print` then `exit`: one record, ORS appended, and the whole input abandoned -- later records are never read.
                return out + "\n"
            name = tok[i]
            name = re.sub(r"[\"']", "", name)
            # awk's sub(/.*\//) is greedy and leftmost-longest, so this strips through the LAST slash. Python's greedy `.*` lands in the same
            # place; count=1 keeps it a `sub` and not a `gsub`.
            name = re.sub(r".*/", "", name, count=1)
            if re.search(r"^(sh|bash|dash|zsh|ash|ksh)$", name):
                for j in range(i + 1, n):
                    t = tok[j]
                    if t == "-c" or re.search(r"^-[^-].*c$", t):
                        out = "".join(tok[m] + (" " if m < n - 1 else "") for m in range(j + 1, n))
                        return out + "\n"
                # NO `exit` HERE, and that is load-bearing: a shell name whose token run carries no -c selector falls back to the OUTER
                # loop, so `bash script.sh; sh -c 'gh pr merge'` still finds
                # the second one.
    return ""


# Drop heredoc bodies: from a line introducing `<< [-] ['"]?MARKER['"]?` up to the line that is exactly MARKER (optionally tab-indented for <<-). Keeps the introducing line (which may itself hold the real command) and the rest.
def _strip_heredocs(text):
    records, _ = _records(text)
    out = []
    skip = False
    marker = ""
    for record in records:
        if skip:
            # awk builds this pattern by CONCATENATION, so `marker` is a regex, not a literal. The match above only ever captures `[A-Za-z_][A-Za-z0-9_]*`, so it carries no metacharacters -- which is the only reason a dynamic regex is safe here.
            if re.search("^[ \t]*" + marker + "[ \t]*$", record):
                skip = False
            continue
        line = record
        m = re.search(r"<<-?[ \t]*['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?", line)
        if m:
            mm = m.group(0)
            mm = re.sub(r"<<-?[ \t]*['\"]?", "", mm)
            mm = re.sub(r"['\"]?$", "", mm)
            marker = mm
            skip = True
        out.append(line)
    return _awk_out(out)


# Remove inline environment assignments sitting between a command position and the
# command itself: `FOO=bar git <verb>` becomes ` git <verb>`.
#
# WITHOUT THIS, ONE TOKEN BYPASSED SEVEN GUARDS. Every git guard here anchors its match at a command position, because prose about committing must not be treated as a commit. An assignment prefix puts a word between the anchor and `git`, so the anchor stops matching and the guard exits 0 having decided this is not a git
# command at all. Measured 2026-09-03, plain versus `FOO=bar `-prefixed, on the
# identical command -- every one of these went from refusing to permitting:
#
#   block-unverified-push          rc=2 -> rc=0
#   block-untagged-commit          rc=2 -> rc=0
#   block-destructive-git-restore  rc=2 -> rc=0
#   block-blanket-git-add          rc=2 -> rc=0
#   block-worktree-add             rc=2 -> rc=0
#
# The fix belongs HERE rather than in seven regexes: an assignment prefix is a property of shell syntax, which is what this file normalises, and a seventh copy of the anchor would have been a seventh chance to miss it. The assignments are dropped
# rather than kept because no guard matches on them; the one guard that needs their
# VALUES reads them from the RAW command for exactly that reason.
_ENV_PREFIX = re.compile(
    r"(^|[;&|(]|\$\(|`)(["
    + BLANK
    + r"]*)([A-Za-z_][A-Za-z0-9_]*=[^"
    + BLANK
    + r";&|]*["
    + BLANK
    + r"]+)"
)


def _strip_env_prefix(text):
    records, terminated = _records(text)
    out = []
    for record in records:
        # The bash is `sed -E ':a; s/.../\1\2/g; ta'`, a label-and-branch loop.
        # It exists because `^` matches only at the true start of the pattern
        # space even under `/g`, so `A=1 B=2 git` needs a SECOND pass before
        # `B=2 ` is at the start and can match. Python's `re.sub` without
        # MULTILINE has the identical `^` rule, so the loop ports one-for-one. It terminates because every substitution deletes a non-empty group 3.
        line = record
        while True:
            line, count = _ENV_PREFIX.subn(r"\1\2", line)
            if count == 0:
                break
        out.append(line)
    return _sed_out(out, terminated)


# The preamble every command guard repeats: read the command out of the hook event, bail when there is nothing to judge, and compute the normalised scan target.
#
# Extracted after check:ci-shape-duplication counted three identical copies (block-untagged-commit, block-unverified-push, block-unlinked-commit-author). The `source` line above cannot be extracted -- something has to load this file -- but everything after it can, and centralising it matters more here than the line count
# suggests: `scan_target` is where the `FOO=bar ` prefix bypass was fixed, and
# a guard that hand-rolls its own preamble is a guard that can drift away from that fix without anything noticing.
#
# Returns (CMD, SCAN), or None when there is no command -- the caller's whole preamble in bash was `hook_init || exit 0`, and here it is
# `state = hook_init(payload)` followed by `if state is None: return`.
#
# THE EMPTY-COMMAND CONTRACT IS NOT WHAT IT LOOKS LIKE. `jq -r` prints the four characters `null` for a key that is absent or JSON null, so a payload
# with no `.tool_input.command` yields the STRING "null", passes the `-z` test
# and is scanned as if someone had typed `null`. Only a jq FAILURE (malformed JSON, so nothing on stdout) or a genuinely empty string command returns 1. That asymmetry is behaviour 25 guards depend on, so it is preserved rather
# than tidied into `None`; the differential pins all four shapes.
def hook_init(payload):
    cmd = _jq_raw_command(payload)
    if cmd == "":
        return None
    scan = _command_substitution(scan_target(cmd))
    return cmd, scan


def _jq_raw_command(payload):
    """`CMD=$(jq -r '.tool_input.command' 2>/dev/null)`, without the fork.

    jq's contract, in the shapes a hook event can actually take:
      * unparseable input          -> jq exits non-zero, stdout empty  -> ""
      * `.tool_input` missing/null -> `null` printed by `-r`           -> "null"
      * command missing/null       -> `null`                           -> "null"
      * command is a string        -> the string, raw (no JSON quoting)
      * command is a non-string    -> its compact JSON form
    The trailing newline jq writes is removed by the command substitution, and
    so is any newline the command itself ends with.
    """
    try:
        doc = json.loads(payload)
    except (ValueError, TypeError):
        return ""
    if isinstance(doc, dict):
        inner = doc.get("tool_input")
    elif doc is None:
        # `null | .tool_input` is null in jq, not an error.
        inner = None
    else:
        # jq refuses to index a number, string or array with a key name and exits 5 with nothing on stdout.
        return ""
    if isinstance(inner, dict):
        value = inner.get("command")
    elif inner is None:
        value = None
    else:
        return ""
    if value is None:
        return _command_substitution("null\n")
    if isinstance(value, str):
        return _command_substitution(value + "\n")
    return _command_substitution(json.dumps(value, separators=(",", ":")) + "\n")


def scan_target(cmd):
    nohd = _command_substitution(_strip_heredocs(cmd))
    stripped = _command_substitution(
        _strip_env_prefix(
            _tr(
                _sed_strip_quoted_spans(_tr(nohd, "\n", "\001")),
                "\001",
                "\n",
            )
        )
    )
    # Extract the wrapper payload (see _wrapper_payload above), then turn its quotes to spaces so the inner command lands at a command position: `sh -c 'gh pr merge --admin'` -> `gh pr merge --admin `.
    wrapped = _command_substitution(
        _strip_env_prefix(_sed_quotes_to_spaces(_wrapper_payload(_tr(nohd, "\n", " "))))
    )
    return "%s\n%s" % (stripped, wrapped)


def _sed_strip_quoted_spans(text):
    """`sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g'`, in that order.

    The order is not cosmetic: single-quoted spans go first, so a double quote
    living inside a single-quoted span is gone before the second expression
    can pair it with an unrelated quote later in the line. The caller has
    already mapped newlines to \\001, so "multi-line aware" means the whole
    command is ONE record here and a quoted span may cross what were lines.
    """
    records, terminated = _records(text)
    out = []
    for record in records:
        line = re.sub(r"'[^']*'", "", record)
        line = re.sub(r'"[^"]*"', "", line)
        out.append(line)
    return _sed_out(out, terminated)


def _sed_quotes_to_spaces(text):
    """`sed -e "s/['\\"]/ /g"` -- every quote character becomes a space."""
    records, terminated = _records(text)
    return _sed_out([re.sub(r"['\"]", " ", record) for record in records], terminated)


# gh_pr_at_command_pos <scan-target> <verb>
# Command position = line start (covers wrapper-payload lines, now
# prefix-stripped), or after ; & | ( $( or a backtick.
def gh_pr_at_command_pos(scan, verb):
    # `verb` is interpolated into the ERE by the original, so it is a PATTERN and not a literal. Every caller passes a bare word (create, merge,
    # ready, edit); re.escape here would be an improvement that changes what
    # is matched, which is the one thing this port may not do.
    pattern = re.compile(
        r"(^|[;&|(]|\$\(|`)["
        + SPACE
        + r"]*gh["
        + SPACE
        + r"]+pr["
        + SPACE
        + r"]+"
        + verb
        + r"(["
        + SPACE
        + r"]|$)"
    )
    records, _ = _records(_here_string(scan))
    return any(pattern.search(record) for record in records)


# flag_present <raw-cmd> <flag-without-dashes>
def flag_present(cmd, flag):
    pattern = re.compile("--" + flag + r"([" + SPACE + r"=;&|)\"'`]|$)")
    records, _ = _records(_here_string(cmd))
    return any(pattern.search(record) for record in records)


# gh_pr_segment <scan-target> <verb> Print ONLY the command segment that actually invokes `gh pr <verb>`, so per-invocation fields (--repo, -R, the PR selector) are read from ONE invocation instead of from the whole bash line.
#
# Round-46 finding, hit live during a real merge: every field was parsed from the entire line, so when several gh commands shared it the repo of one was paired with the PR number of another --
#   gh pr view 94 --repo rediacc/renet; gh pr merge 66 --repo rediacc/account
# resolved as rediacc/renet#66 (a long-merged, unrelated PR) and blocked the merge on THAT PR's unresolved thread. Same class as the wrapper/flag/path findings the rest of this file records: a field read at the wrong scope. Splitting on command separators fixes the scope rather than special-casing the observed pairing. Prints EVERY such segment, one per line, so a caller checks
# each invocation on its own. The old line-wide parsing also silently checked only ONE of several same-verb invocations (the greedy selector regex took the last PR number, the repo grep took the first repo), so a second `gh pr merge` on the
# line went entirely unexamined; looping closes that too.
def gh_pr_segment(scan, verb):
    # `sed -e 's/[;&|()`]/\n/g'`: the separator is REPLACED by a newline, not
    # split on, so the separator character itself never reaches the anchor.
    records, terminated = _records(scan)
    split = _sed_out([re.sub(r"[;&|()`]", "\n", record) for record in records], terminated)
    pattern = re.compile(
        r"^[" + SPACE + r"]*gh[" + SPACE + r"]+pr[" + SPACE + r"]+" + verb + r"([" + SPACE + r"]|$)"
    )
    grep_records, _ = _records(split)
    segs = _command_substitution(_grep_out([r for r in grep_records if pattern.search(r)]))
    # Fail closed: if the split finds nothing (a shape not anticipated here) hand back the WHOLE scan, i.e. the old behavior, never an empty scope that would silently resolve to defaults and skip the real check.
    return segs if segs != "" else scan


# target_repo <segment> <whole-scan> <cwd> Resolve the rediacc repo a `gh pr` invocation targets, in order: 1. --repo/-R in the SAME segment as the verb 2. a `cd`/`git -C` into private/<submodule> anywhere on the line (a cd applies to every later segment, so this one is deliberately line-wide) 3. the session cwd's origin remote 4. rediacc/console
def target_repo(seg, scan, cwd):
    repo = _command_substitution(
        _grep_out(
            [
                re.sub(r"^(--repo[= ]|-R )", "", m, count=1)
                for m in _grep_only(r"(--repo[= ]|-R )[A-Za-z0-9_./-]+", seg + "\n")[:1]
            ]
        )
    )
    if repo == "":
        submodules = r"private/(renet|account|elite|homebrew-tap)"
        first = _grep_only(r"(cd |-C )[^;|&]*" + submodules, scan + "\n")
        second = _grep_only(submodules, _grep_out(first))
        sm = _command_substitution(_grep_out(second[:1]))
        if sm != "":
            # `${sm#private/}` removes the SHORTEST matching prefix, once.
            # `str.removeprefix` is exactly `${sm#private/}`: shortest prefix,
            # once, and a no-op when it is absent.
            repo = "rediacc/" + sm.removeprefix("private/")
    if repo == "" and cwd != "":
        # The pipeline's exit status is sed's, never git's, so a failed git here is indistinguishable from a repo with no origin: both leave `repo` empty and fall through to the default below.
        url = _git_stdout(["-C", cwd, "remote", "get-url", "origin"])
        records, terminated = _records(url)
        out = []
        for record in records:
            line = re.sub(r"\.git$", "", record)
            line = re.sub(r".*[:/]([^/]+/[^/]+)$", r"\1", line)
            out.append(line)
        repo = _command_substitution(_sed_out(out, terminated))
    return repo if repo != "" else "rediacc/console"


# pr_selector <segment> <verb> The PR selector (number/url/branch) belongs to the same invocation as the verb -- read it from the segment, never from the line.
def pr_selector(seg, verb):
    # `sed -n "s/.*gh pr ${verb}[[:space:]]*//p"`: `.*` is greedy, so on a
    # segment naming the verb twice this cuts at the LAST one, and `-n ... p` means non-matching lines are dropped rather than passed through.
    cut = re.compile(r".*gh pr " + verb + r"[" + SPACE + r"]*")
    records, _ = _records(_printf_line(seg))
    kept = []
    for record in records:
        new, count = cut.subn("", record, count=1)
        if count:
            kept.append(new)
    for record in _records(_sed_out(kept, terminated=True))[0]:
        # awk's default FS is space/tab/newline with leading and trailing runs discarded -- NOT Python's str.split(), which also splits on \r and on Unicode separators and would therefore field a `\r` differently.
        fields = [f for f in re.split(r"[ \t]+", record.strip(" \t")) if f != ""]
        for field in fields:
            if not re.search(r"^-", field):
                # awk `print` then `exit`: the FIRST such field on the FIRST line that has one, and no further lines are read.
                return field + "\n"
    return ""


# target_root <whole-scan> <this-root> The FILESYSTEM git root a command operates on, or "" when it is this one.
#
# DIFFERENT QUESTION FROM target_repo ABOVE, which resolves a GitHub repo NAME for a `gh pr` invocation. This resolves a working tree, for guards that read local git state -- a branch name, a HEAD sha, a gate-run stamp. Those guards are only correct when the tree they inspect is the tree the command touches.
#
# THIRD COPY, SO IT MOVED HERE. block-untagged-commit.sh:52-69 hand-rolled this and its comment records why: without it, `git -C <other-repo> commit` was "judged against CLAUDE_PROJECT_DIR/agent/pr/<console-branch>.md: wrong branch name, wrong epic snapshot, so every such commit was refused for a trailer no epic file could ever supply."
#
# Measured 2026-09-01, the same defect was live in a sibling: `git -C <scratch> push` was refused by block-unverified-push.sh because it compared the SCRATCH repo's push to the CONSOLE tree's gate-run stamp (reproduced: exit 2). warn-remote-drift.sh has the identical shape and is latent -- quiet today only because console's remote happens not to be ahead.
#
# A `cd` applies to every later segment, so the scan is deliberately line-wide, matching target_repo's convention. Prints "" when the command targets THIS root, when no hint is present, or when the hint does not resolve to a git repo -- so a caller can treat empty as "this repo, proceed" and never has to distinguish absent from same.
def target_root(scan, this_root):
    hints = _grep_only(r"(cd [^;|&]*|-C[" + SPACE + r"]+[^" + SPACE + r";|&]+)", _printf_line(scan))
    hint = _command_substitution(_grep_out(hints[-1:]))
    if hint != "":
        # Five sed expressions, applied in order to the one line. Note the FIRST one: the grep above accepts `-C<tab>path`, but this strip requires a literal space after `-C`, so a tab-separated hint keeps its `-C\t` prefix and fails to resolve. That is the bash's behaviour, carried across deliberately -- a `re.sub` widened to `[[:space:]]` here would be a silent behaviour change,
        # and this file's whole point is that behaviour changes come from findings and not from tidying.
        hint = re.sub(r"^(cd |-C )[" + SPACE + r"]*", "", hint, count=1)
        hint = re.sub(r"[" + SPACE + r"]*&&.*$", "", hint, count=1)
        hint = re.sub(r"^[\"']", "", hint, count=1)
        hint = re.sub(r"[\"']$", "", hint, count=1)
        hint = re.sub(r"[" + SPACE + r"]+$", "", hint, count=1)
    if hint == "":
        return ""
    # bash `case "$hint" in /*) ... ;; *) ...` -- a leading slash, nothing more
    # elaborate. A `~` or a `$HOME` is NOT expanded here, in either language.
    abs_path = hint if hint.startswith("/") else this_root + "/" + hint
    target = _git_stdout(["-C", abs_path, "rev-parse", "--show-toplevel"], want_rc=True)
    if target is None:
        return ""
    target = _command_substitution(target)
    if target not in ("", this_root):
        return target
    return ""


def _printf_line(text):
    """`printf '%s\\n' "$x"` -- exactly one newline appended, whatever `x` ends
    with. Not the same as a here-string only in name: both add one newline, and
    both are written out here so a reader does not have to remember which
    call site used which.
    """
    return text + "\n"


def _grep_only(pattern, text):
    """`grep -oE <pattern>` -- every non-overlapping match, in order, one per
    line, across every record. Python's finditer scans left to right and
    resumes after each match, which is GNU grep's rule too; what differs is
    leftmost-longest versus leftmost-first, and the module docstring records
    why the alternations here do not feel it.
    """
    compiled = re.compile(pattern)
    records, _ = _records(text)
    out = []
    for record in records:
        out.extend(m.group(0) for m in compiled.finditer(record))
    return out


def _git_stdout(args, want_rc=False):
    """Run git with stderr discarded.

    `want_rc=False` mirrors a pipeline whose exit status belongs to the LAST
    stage, so a git failure is just empty output. `want_rc=True` mirrors
    `target=$(git ...) || return 0`, where the failure itself is the branch.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            check=False,
        )
    except OSError:
        # `git` absent behaves like `git` failing: bash sends the "command not found" message to the 2>/dev/null the caller already wrote.
        return None if want_rc else ""
    if want_rc and proc.returncode != 0:
        return None
    # Decoded by hand rather than with `encoding=`: text mode translates
    # universal newlines, so a \r would come back as \n and the value would differ from what the bash `$( )` captured. surrogateescape because a path is bytes, and refusing to decode one is not this function's job.
    return proc.stdout.decode("utf-8", "surrogateescape")


def repo_root_env():
    """`CLAUDE_PROJECT_DIR`, the root every guard passes as `this_root`.

    Not part of the bash lib -- each guard computes it itself -- but every
    caller of `target_root` needs the same answer, and a second spelling of it
    is exactly the drift `.ci/rediacc_ci/paths.py` was written to end.
    """
    return os.environ.get("CLAUDE_PROJECT_DIR", "")
