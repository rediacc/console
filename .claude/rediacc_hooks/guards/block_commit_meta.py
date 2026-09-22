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

from rediacc_hooks import hookio

CHAIN = "pre-bash"
TWIN = "pre-bash/block-commit-meta.sh"
ORDER = 4

# The commit-verb gate is the whole 2026-08-27 fix. Without it the phrase test runs against every command again, so grepping the docs for the banned trailer is refused as though it were adding one.
DEFECT = ("if not hookio.grep_q(AUTHORS_A_MESSAGE, cmd):", "if False:")

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
FILE_ARGS = hookio.rx(r"(-F|--file)([{S}]+|=)[^{S};|&]+")

MESSAGE = "❌ BLOCKED: Do not add Co-Authored-By or Generated with lines in commits."

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
]


def _commit_file_bodies(cmd, root):
    """Every `-F <path>` / `--file[= ]<path>` target's bytes, read off disk. `-F -` (stdin) is skipped: stdin at hook time is the hook's OWN payload, not the commit's, so there is nothing here to read.

    Each name is tried both as given (an absolute path, or one already relative to the caller's cwd) and rooted at `root` -- the same two candidates `block_untagged_commit.py` tries, for the identical reason.
    """
    bodies = []
    for match in hookio.grep_o(FILE_ARGS, cmd):
        name = hookio.sed_sub(hookio.rx(r"^(-F|--file)([{S}]+|=)"), "", match).rstrip("\n")
        if name in {"", "-"}:
            continue
        for cand in (name, "%s/%s" % (root, name)):
            path = pathlib.Path(cand)
            if path.is_file():
                with contextlib.suppress(OSError):
                    bodies.append(path.read_text(encoding="utf-8", errors="surrogateescape"))
                break
    return bodies


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    if not hookio.grep_q(AUTHORS_A_MESSAGE, cmd):
        return hookio.ALLOW

    if hookio.grep_q(TRAILER_OR_FOOTER, cmd, ignore_case=True):
        ev.warn(MESSAGE)
        return hookio.DENY

    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(
        ["rev-parse", "--show-toplevel"], cwd=ev.cwd
    )
    for body in _commit_file_bodies(cmd, root):
        if hookio.grep_q(TRAILER_OR_FOOTER, body, ignore_case=True):
            ev.warn(MESSAGE)
            return hookio.DENY

    return hookio.ALLOW
