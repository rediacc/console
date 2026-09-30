"""Block Co-Authored-By / Generated with lines in commits.

IT MUST BE A COMMIT. This guard's whole history is false positives, and the header used to record three of them: the unanchored `Generated with` fired inside "witho|ut", then on "Re|generated with npm@10" once a word boundary was added, then on an ordinary PR body describing a regenerated i18n baseline. Each fix narrowed the PHRASE. None of them asked the question that actually
separates a violation from a sentence -- is this command writing a commit message at all?

The unfixed half was the trailer token itself, which the old header defended as "unambiguous anywhere". It is not. Measured 2026-08-27, it refused:

  grep -rn 'co-authored-by' docs/        <- searching for the banned trailer
  echo 'the rule bans <the trailer>'     <- prose naming the rule

Both are how you AUDIT this rule, so the guard was blocking its own enforcement. Case-insensitivity made it worse, not better.

So the phrase check now runs only when the command authors a message: a git commit, a git tag -m, or a gh pr create/edit. A heredoc body still counts, because the body is part of the command -- which is the case that matters, and the one every earlier narrowing preserved by accident rather than on purpose.

The line anchoring on `Generated with` stays. A guard whose only failure mode is refusing CORRECT input teaches people to reword honest messages until it stops complaining, and the rewording hides what happened.

PORT NOTE ON A BYTE-VERSUS-CHARACTER DIFFERENCE. `[^[:alnum:]]{0,4}` is
counted by grep in BYTES under LC_ALL=C, and by Python in CHARACTERS. The one
prefix this clause exists for is a single emoji, which is four bytes and one character, so both sides admit it; a prefix of two emoji would be eight bytes and two characters and the two sides would disagree. No corpus case has one, the widening is in the direction of matching more, and narrowing it here would be a behaviour change made for tidiness rather than from a finding.
"""

import contextlib
import pathlib
import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 4

# The commit-verb gate is the whole 2026-08-27 fix. Without it the phrase test runs against every command again, so grepping the docs for the banned trailer is refused as though it were adding one.
# THE SUBJECT IS `scan`, NOT `cmd`, AND THE DIFFERENCE MADE THIS PLANT VACUOUS. The branch below moved to the unwrapped `scan` when bypass-resistant verb detection landed, and this declaration kept naming `cmd`, so the only text in the file the plant still matched was THIS LINE: `source.replace(old, new)` rewrote the tuple into `("if False:", "if False:")` and left the real
# branch untouched, and `test_the_differential_can_fail` then reported the port as answering identically with its defect planted. A plant that edits its own declaration is a control that cannot fire.
DEFECT = ("if not _authors_a_message(scan):", "if False:")

# Not authoring a message -> not this guard's business.
#
# THE GAP MUST NOT CROSS A CLAUSE. `git ... commit` needs to tolerate flags in between (`git -C sub commit`, `git commit -a`), but a gap of "any non-space token" happily spans `|` and `&&`, so this matched:
#
# git log --oneline | grep commit | grep <the trailer>
#
# -- a `git log` in one clause and the word `commit` in another, read as a commit that carries a trailer. Excluding `;|&` from the gap tokens keeps the verb and its subcommand in one clause, which is the same fix block-protected-files needed for the same reason on the same day.
AUTHORS_A_MESSAGE = hookio.rx(
    r"(^|[;&|(]|[{S}])git[{S}]+([^{S};|&]+[{S}]+)*(commit|tag)\b|(^|[;&|(]|[{S}])gh[{S}]+pr[{S}]+(create|edit)\b"
)

# THE SANCTIONED PR-BODY WRITE HAS NO `pr` VERB IN IT, so the gate above could not see it. block-adhoc-sanctioned.sh refuses `gh pr edit --body`/`--body-file` outright (measured 2026-08-25 on PR #574: it exits 1 on the deprecated projectCards GraphQL field with the body UNCHANGED) and redirects every caller to `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>`, where
# the only `pr` is inside the URL path. So the two spellings this guard watched for a PR description were the two nobody in this repository may use, and the one everybody does walked past.
#
# TWO INDEPENDENT CHECKS, NOT ONE COMBINED PATTERN, and the METHOD one is what keeps the audit shapes legal. `gh api`'s flags are order-independent -- `-X PATCH` may precede or follow the endpoint -- so a single sequential regex would have to spell every ordering. More importantly, without the method test a plain READ of a body would be gated:
#
# gh api repos/o/r/pulls/42 --jq .body | grep <the trailer>
#
# which is how this rule gets AUDITED, and refusing it is the exact false-positive class the 2026-08-27 verb gate was written to end. `block_prose_style_commit.py` reached the same two-check answer on 2026-09-17 for the same command; these are that pair, adapted.
#
# `[^;&|\n]*` IS THE CLAUSE FENCE, and it is why this pair needs no space class and so is not written through `hookio.rx`. A gap that could cross `|` would read `gh api <one thing> | ... pulls/42` as one call, which is the same clause-crossing defect the git arm above records.
GH_API_PR_PATCH = r"gh\b[^;&|\n]*\bapi\b[^;&|\n]*\bpulls/[0-9]+"
PATCH_METHOD = hookio.rx(r"(-X|--method)[={S}]?['\"]?PATCH\b")

# THE COLON IS WHAT MAKES IT A TRAILER. The token was left unanchored on the claim -- written into that file -- that it is "unambiguous anywhere". It is not, and the commit-verb gate above does not save it once the verb is really present:
#
# gh pr create --body '... | `grep -rn "co-authored-by" docs/` | ...'
#
# That is a PR body DOCUMENTING this guard's own over-block history, refused by the guard it documents, on 2026-08-27.
#
# LINE-ANCHORING IT WAS THE WRONG FIX, and the first attempt shipped it: a single-line `--body '<trailer>: A <a@b.c>'` puts a REAL trailer mid-line, so the anchor let it straight through. Requiring the colon separates the two without any positional assumption -- a trailer has a separator, prose quoting
# the token does not. BOTH separators: `--trailer <token>=bot` is a real
# trailer git accepts, and the colon-only draft let it through -- caught by the suite case pinning exactly that form. `Generated with` keeps its line anchor, which it earned over three separate false positives.
TRAILER_OR_FOOTER = hookio.rx(
    r"Co-Authored-By[{S}]*[:=]|^[{S}]*([^0-9A-Za-z]{0,4}[{S}]*)?Generated with\b"
)

# THE COMMAND STRING IS NOT WHERE THE MESSAGE LIVES for `-F <file>` / `--file=<file>` / `--file <file>`. The established convention for a commit body long enough to need reflow (`git commit -q -F <file> -- <paths>`, written to dodge the heredoc/prose-wrapping trap) is exactly that shape: the trailer sat in the file's bytes, `cmd` never contained it.
# Two commits carrying `Co-Authored-By: Claude Sonnet 5` reached a real push before this was caught. `block_untagged_commit.py` already solved this exact problem for its own trailer, so `FILE_ARGS` is that guard's pattern verbatim rather than a second, independently-drifting spelling of the same idea.
#
# AND `gh` DOES NOT SPELL IT `-F`. The pattern above was taken verbatim from a guard whose only subject is `git commit`, so it recognised exactly the two flags git offers and no others -- while the commands this guard ALSO gates, `gh pr create` and `gh pr edit`, pass a long body as `--body-file <path>`, and the sanctioned `gh api ... -X PATCH` form passes it as `-F body=@<path>`.
# Neither spelling is a prefix or a suffix of `-F` or `--file`, so `_commit_file_bodies` never opened either file and the trailer check simply did not run for them.
#
# MEASURED, NOT INFERRED: on 2026-09-23 `gh pr create --repo rediacc/console --body-file <path> --draft` created PR #590 with `Generated with [Claude Code]` live in its description, past this guard, and the operator found it on GitHub. That is the same failure the `-F` clause above was added for, one flag name later. The three spellings now share one walk, so a fourth is a
# new row rather than a new code path.
FILE_ARGS = (
    (
        hookio.rx(r"(-F|--file|--body-file)([{S}]+|=)[^{S};|&]+"),
        hookio.rx(r"^(-F|--file|--body-file)([{S}]+|=)"),
    ),
    # `-F body=@<path>` / `--input <path>`: the `gh api` body, whose path sits INSIDE the argument rather than after the flag, so it cannot be a fourth alternative in the pattern above. Same two spellings block_raw_pr_body_edit.py reads for the same call.
    (
        hookio.rx(r"((-F|--field)[{S}]+body=@|--input([{S}]+|=))[^{S};|&]+"),
        hookio.rx(r"^((-F|--field)[{S}]+body=@|--input([{S}]+|=))"),
    ),
)

# A BODY FILE WRITTEN BY THIS SAME COMMAND IS NOT ON DISK YET, so its bytes are in the command: `printf '%s\n' 'prose' '' '<emoji> Generated with [Claude Code](...)' > $S/pr.md; gh pr create --repo rediacc/renet --body-file $S/pr.md`. That was the first of the two 2026-09-30 attempts (see `_expand`), and the line-anchored footer above cannot see it: the footer is one `printf` ARGUMENT, so on the
# command's line it follows `'' '`, never a line start. A shell WORD that begins with the footer is the same footer, so this form also accepts a quote (or a literal `\n` escape) as the start. It is applied ONLY when the command writes one of its own message files, because a quoted "Generated with" in an ordinary `--body` is exactly the prose false positive the anchor was earned against.
INLINE_FOOTER = hookio.rx(r"(^|['\"]|\\n)[{S}]*([^0-9A-Za-z'\"]{0,4}[{S}]*)?Generated with\b")

# `$NAME` / `${NAME}`: the only expansion `_expand` performs.
SHELL_VAR = re.compile(r"\$(\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")

# The verbs whose preceding `NAME=value` statements can spell a message-file path.
MESSAGE_VERBS = ("git commit", "git tag", "gh pr", "gh api")

MESSAGE = "❌ BLOCKED: Do not add Co-Authored-By or Generated with lines in commits."

# A body file reached ONLY through an inherited variable (#378c645c). The differential's `_base_env` passes the runner's real HOME, where these files do not exist, so the `home-bodies` variant points HOME at this fixture instead: the same `$HOME/...` payloads are admitted under `default` (no file to read) and judged on their bytes here. The footer is assembled so no source line is itself one.
HOME_BODIES = ".commit-meta-bodies"


def _home_fixture(path):
    bodies = pathlib.Path(path) / HOME_BODIES
    bodies.mkdir(parents=True)
    footer = "\U0001f916 " + "Generated" + " with [Claude Code](u)"
    (bodies / "footer.md").write_text("prose\n\n%s\n" % footer, encoding="utf-8")
    (bodies / "clean.md").write_text("prose\n\nConsole PR: x.\n", encoding="utf-8")
    return path


FIXTURES = {"commit-meta-home": _home_fixture}

# `default` first and with no extras, so every record it already froze keeps its key.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {}, {}),
    ("home-bodies", {"HOME": "{FIXTURE:commit-meta-home}"}, {}),
]

EDGE_CASES = [
    ("a tag message carries the same rule", "git tag -a v1 -m Co-Authored-By:bot"),
    # The audit shapes the 2026-08-27 gate exists to let through.
    ("grepping the docs for the trailer", "grep -rn 'Co-Authored-By:' docs/"),
    ("prose naming the rule", "echo 'the rule bans Co-Authored-By: lines'"),
    # The clause-crossing gap.
    (
        "a git verb and the word commit in different clauses",
        "git log | grep commit | grep Co-Authored-By:",
    ),
    # `Generated with` keeps its line anchor, so it needs a real line start.
    ("a footer at the start of a message line", 'git commit -m "fix\n\nGenerated with a robot"'),
    ("the same footer mid-line is prose", 'git commit -m "regenerated with npm@10"'),
    ("an ordinary commit", "git commit -m 'fix(cli): x'"),
    # 2026-09-30: a body file this same command writes is judged on the command's own bytes, in any repo and either flag order. The footer is assembled so this source line is not itself one.
    (
        "a submodule create whose body file this command writes with the footer",
        (
            "S=/tmp/pb; printf '%s\\n' 'prose' '' '\U0001f916 "
            "Generated with [Claude Code](u)' > $S/pr.md; "
            "gh pr create --repo rediacc/renet --title t --body-file $S/pr.md"
        ),
    ),
    (
        "the same with --body-file before --repo",
        (
            "S=/tmp/pb; printf '%s\\n' 'prose' '' '\U0001f916 "
            "Generated with [Claude Code](u)' > $S/pr.md; "
            "gh pr create --body-file $S/pr.md --repo rediacc/renet --title t"
        ),
    ),
    (
        "the same written body without the footer passes",
        (
            "S=/tmp/pb; printf '%s\\n' 'prose' '' 'Console PR: x.' > $S/pr.md; "
            "gh pr create --repo rediacc/renet --title t --body-file $S/pr.md"
        ),
    ),
    (
        "a quoted phrase in an inline --body is prose, not a footer",
        "gh pr create --repo rediacc/renet --title t --body 'refuses \"Generated with\" lines'",
    ),
    # #378c645c: a body file named through a variable the command never assigns. Refused under `home-bodies`, where the file carries the footer; admitted under `default`, where it does not exist.
    (
        "an inherited $HOME body file with the footer",
        "gh pr create --title t --body-file $HOME/%s/footer.md" % HOME_BODIES,
    ),
    ("the braced ${HOME} spelling on a commit", "git commit -F ${HOME}/%s/footer.md" % HOME_BODIES),
    (
        "the gh api body spelling",
        "gh api repos/o/r/pulls/7 -X PATCH -F body=@$HOME/%s/footer.md" % HOME_BODIES,
    ),
    (
        "an inherited $HOME body file without the footer",
        "gh pr create --title t --body-file $HOME/%s/clean.md" % HOME_BODIES,
    ),
    # Unset in every environment the differential runs: the name stays unresolved and fails open.
    (
        "an unset variable's body file is admitted",
        "gh pr create --title t --body-file $COMMIT_META_UNSET_VAR/%s/footer.md" % HOME_BODIES,
    ),
    # A same-command assignment wins over the environment, as in bash: this HOME has no body file.
    (
        "a same-command assignment shadows the inherited value",
        "HOME=/nonexistent; gh pr create --title t --body-file $HOME/%s/footer.md" % HOME_BODIES,
    ),
]


def _authors_a_message(scan):
    """Is this command writing a commit message, a tag message or a PR description?"""
    if hookio.grep_q(AUTHORS_A_MESSAGE, scan):
        return True
    return hookio.grep_q(GH_API_PR_PATCH, scan) and hookio.grep_q(PATCH_METHOD, scan)


def _commit_file_bodies(cmd, root, env):
    """Every message-file target's bytes, read off disk: `-F <path>`, `--file[= ]<path>`, `--body-file[= ]<path>`, `-F body=@<path>` and `--input <path>`. `-F -` (stdin) is skipped: stdin at hook time is the hook's OWN payload, not the commit's, so there is nothing here to read.

    Each name is tried both as given (an absolute path, or one already relative to the caller's cwd) and rooted at `root` -- the same two candidates `block_untagged_commit.py` tries, for the identical reason. `env(name, None)` answers a variable the command does not assign (see `_expand`).
    """
    bodies = []
    written = False
    names = {}
    for verb in MESSAGE_VERBS:
        names.update(shellscan.assignments_before(cmd, verb))
    for pattern, strip in FILE_ARGS:
        found, wrote = _bodies_for(pattern, strip, cmd, root, names, env)
        bodies.extend(found)
        written = written or wrote
    return bodies, written


def _expand(name, names, env):
    """`$S/pr.md` with `S=/abs/dir` assigned earlier in the same command, as `/abs/dir/pr.md`; an unassigned `$HOME/pr.md` from the environment the command inherits.

    MEASURED 2026-09-30, and it is the whole defect behind "renet and account admitted, console refused". The console `gh pr create` named its body file by a literal path, was read and refused; the two submodule ones were `S=<scratchpad>; gh pr create --repo rediacc/renet ... --body-file $S/pr-renet.md`, and a file literally named `$S/pr-renet.md` does not exist, so the read failed OPEN and
    both PRs were created with the attribution footer live. The repo and the flag order had nothing to do with it; the SPELLING of the path did. `block_prose_style_commit.py` hit the same wall on 2026-09-25 (#09fd19cd) and answered it with the same helper, `shellscan.assignments_before`.

    THE SAME HOLE, ONE STEP WIDER (#378c645c): `--body-file $HOME/pr.md` names a variable no statement in the command assigns, so the first fix left it unread and a footer in it passed. The hook runs in the SAME environment the command will, so `env` (the event's environment, `os.environ` in production) answers what bash would. A same-command assignment wins over the environment, as it does in bash; a prefix assignment (`S=x gh pr create ... $S/y`) is not one, since bash expands `$S` before it applies, so the environment is right there too. Two passes, so an assigned value that itself names a variable (`S=$HOME/pb`) resolves as well.

    A name still carrying `$` or a backtick afterwards (an UNSET variable, a `$(...)` substitution) is unreadable and FAILS OPEN as before. Refusing it would refuse every command whose body path cannot be resolved statically, and the ordinary one of those writes the file in the same command, which `shellscan.writes_file` already judges on the command's own bytes.
    """
    if "$" not in name:
        return name

    def sub(match):
        key = match.group(2) or match.group(3)
        if key in names:
            return names[key]
        value = env(key, None)
        return match.group(0) if value is None else value

    return SHELL_VAR.sub(sub, SHELL_VAR.sub(sub, name))


def _bodies_for(pattern, strip, cmd, root, names, env):
    """One spelling's worth of `grep -oE <pattern> | sed -E 's/<strip>//'`, resolved and read.

    Returns `(bodies, written)`, `written` saying that this same command writes one of the named files, so its content is in the command text rather than on disk.
    """
    bodies = []
    written = False
    for match in hookio.grep_o(pattern, cmd):
        raw = hookio.sed_sub(strip, "", match).rstrip("\n")
        if raw in {"", "-"}:
            continue
        name = _expand(raw, names, env)
        # Written by this same command: the bytes on disk are an earlier command's (shellscan.writes_file, #9ec22810). Asked for BOTH spellings, because the redirect is usually spelled the way the flag is (`> $S/pr.md ... --body-file $S/pr.md`) and sometimes not.
        if shellscan.writes_file(cmd, raw, name):
            written = True
            continue
        if "$" in name or "`" in name:
            continue
        # AN UNRESOLVED ROOT DROPS THE SECOND CANDIDATE RATHER THAN DEGRADING IT. With `root` empty the rooted spelling collapses to the absolute path "/<name>", which is a different file on the filesystem, and reading its bytes as a commit message body is a verdict about the wrong file.
        for cand in (name, "%s/%s" % (root, name)) if root else (name,):
            path = pathlib.Path(cand)
            if path.is_file():
                with contextlib.suppress(OSError):
                    bodies.append(path.read_text(encoding="utf-8", errors="surrogateescape"))
                break
    return bodies, written


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    # Bypass-resistant VERB detection (unwraps sh -c/eval payloads, strips heredocs+prose): worklist evidence or a python script's own argument text MENTIONING "git commit" or "gh pr create" must not trip this gate, only a real invocation.
    # TRAILER_OR_FOOTER below still reads the RAW cmd, because for a real commit the message body IS the command string and stripping it would hide the content this guard exists to check.
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if not _authors_a_message(scan):
        return hookio.ALLOW

    if hookio.grep_q(TRAILER_OR_FOOTER, cmd, ignore_case=True):
        ev.warn(MESSAGE)
        return hookio.DENY

    # `want_rc=True`, NOT THE DEFAULT THAT DROPS THE STATUS. `git_out`'s default answers with the empty string both when git fails and when it succeeds with no output, and `run_out`'s own docstring names confusing the two as how a failing command becomes an empty string that reads as a real answer. Outside a repository this returns None instead, and the test that makes that
    # answer load-bearing is `_commit_file_bodies`'s own: an unresolved root drops the rooted candidate rather than rendering it. The test lives there because that is the only place `root` is read, and a second test here would be inert.
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(
        ["rev-parse", "--show-toplevel"], cwd=ev.cwd, want_rc=True
    )
    bodies, written = _commit_file_bodies(cmd, root, ev.env)
    for body in bodies:
        if hookio.grep_q(TRAILER_OR_FOOTER, body, ignore_case=True):
            ev.warn(MESSAGE)
            return hookio.DENY
    if written and hookio.grep_q(INLINE_FOOTER, cmd, ignore_case=True):
        ev.warn(MESSAGE)
        return hookio.DENY

    return hookio.ALLOW
