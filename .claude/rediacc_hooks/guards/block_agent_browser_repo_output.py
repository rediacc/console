"""Block agent-browser output that would land inside the repo working tree.

WHY THIS EXISTS. Two different mechanisms have each put untracked files into this repo, and BOTH exit 0 and print a success line, so nothing catches them:

  1. POSITIONAL FLAG-EATING. `screenshot [selector] [path]` has two positional slots.
     `--full-page` is not a real flag (the real one is `--full`), so it is consumed as
     [path]: the intended path silently becomes the SELECTOR, a file named `--full-page`
     lands in $PWD, and the tool prints "Screenshot saved to --full-page".
     Reproduced 2026-08-27.
  2. AGENT_BROWSER_SCREENSHOT_DIR IS IGNORED. A bare filename resolves against the
     working directory. `.claude/agents/browser-probe.md:119-123` records that this put
     three untracked PNGs into a repo before anyone noticed, and states the rule this
     hook enforces: "Pass an absolute path to every screenshot."

The rule already existed in prose and had no enforcement surface. This is that surface.

THE UNKNOWN-FLAG ALLOWLIST IS DELIBERATE AND MUST NOT BE WIDENED TO SILENCE A FIRE.
An unrecognised `--flag` on an output subcommand is exactly the bug in case 1. When agent-browser gains a genuinely new flag, ADD IT HERE on purpose. Narrowing the match instead fails silently, which is the trade this repo has already ruled on.

PORT NOTE ON `for tok in $SEGMENT`. The bash leaves `$SEGMENT` UNQUOTED, so the shell does two things to it: IFS word splitting, and PATHNAME EXPANSION. A token containing `*`, `?` or `[` is therefore replaced by the files it matches in the CURRENT DIRECTORY, sorted, and left alone only when nothing matches. `_expand` reproduces both, because a port that only split would judge a
different set of tokens than the twin whenever a selector carries a glob character -- which is not exotic for a CSS selector.
"""

import glob

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 33

# Silencing the catch-all is the one change this guard's header forbids by name: the unrecognised-flag arm IS case 1, and without it `--full-page` goes back to being eaten as the output path.
DEFECT = ('if hookio.case_glob(tok, "--*"):', "if False:")

# Only the subcommands that write a file to disk. ANCHORED TO COMMAND POSITION 2026-08-28, after check:ci-guard-mention-anchoring found this guard refusing an ordinary sentence. Matching the phrase ANYWHERE means a doc line, a worklist note or an `echo` explaining the rule is refused as if it were the rule being broken. This NARROWS PROSE ONLY: every control below still blocks the
# real command, at line start and after a separator.
WRITES_A_FILE = hookio.rx(
    r"(^|[;&|(])[{S}]*(sudo[{S}]+)?agent-browser\b[^;|&]*\b(screenshot|pdf|download)\b"
)

SEGMENT_SPAN = r"\bagent-browser\b[^;|&]*"
SEGMENT_VERB = r"\b(screenshot|pdf|download)\b"

# Repo root from BASH_SOURCE, not CLAUDE_PROJECT_DIR, which is unreliable inside hooks.
REPO_ROOT = str(hookio.repo_root())

KNOWN_FLAGS = (
    "--full",
    "--annotate",
    "--json",
    "--headed",
    "--webgpu",
    "--quiet",
    "--screenshot-dir",
    "--screenshot-quality",
    "--screenshot-format",
    "--viewport",
    "--executable-path",
    "--cdp",
    "--device",
    "--provider",
    "--timeout",
    "--screenshot-dir=*",
    "--screenshot-quality=*",
    "--screenshot-format=*",
    "--viewport=*",
    "--executable-path=*",
    "--cdp=*",
    "--device=*",
    "--provider=*",
    "--timeout=*",
    "--hide-scrollbars=*",
    "--hide-scrollbars",
)

MESSAGE = (
    "❌ BLOCKED: agent-browser would write into the repo working tree.\n"
    "\n"
    "  %s\n"
    "\n"
    "  Write to an absolute path outside the repo, and put the path BEFORE any flags:\n"
    "      agent-browser screenshot /tmp/shot.png --full\n"
    "\n"
    "  Two things make this fail silently if you do not:\n"
    "    - an unknown flag is eaten as the [path] positional (--full-page is not a flag; "
    "--full is)\n"
    "    - AGENT_BROWSER_SCREENSHOT_DIR is ignored, so a bare filename lands in $PWD\n"
    "\n"
    "  Screenshots are disposable. Evidence that must survive belongs in the program\n"
    "  checkpoints directory, not in /tmp and not in the repo.\n"
)

EDGE_CASES = [
    # Case 1, reproduced 2026-08-27.
    (
        "an unrecognised flag is eaten as the path",
        "agent-browser screenshot --full-page /tmp/x.png",
    ),
    # Case 2, in both its shapes.
    ("an absolute path inside the repo", "agent-browser screenshot /home/developer/console/x.png"),
    ("a bare filename resolves against $PWD", "agent-browser screenshot shot.png"),
    ("the correct shape", "agent-browser screenshot /tmp/shot.png --full"),
    ("a known value-taking flag", "agent-browser screenshot /tmp/shot.png --viewport=1280x800"),
    # `head -1` was wrong twice over, so EVERY writing segment is judged.
    (
        "the first segment writes nothing and the second is correct",
        "agent-browser open http://x && agent-browser screenshot /tmp/x.png",
    ),
    (
        "two output subcommands, and the SECOND is the bad one",
        "agent-browser screenshot /tmp/a.png; agent-browser pdf b.pdf",
    ),
    ("a non-writing subcommand is not this guard's business", "agent-browser open http://x"),
    ("prose naming the rule", "echo 'agent-browser screenshot shot.png'"),
]


def _expand(word):
    """One unquoted word, after bash pathname expansion.

    A word with no glob character is itself; one that matches nothing is left literally (nullglob is off); otherwise it becomes its sorted matches.
    """
    if not any(char in word for char in "*?["):
        return [word]
    matches = sorted(glob.glob(word))
    return matches or [word]


def _words(segment):
    """`for tok in $SEGMENT` -- IFS splitting, then pathname expansion."""
    out = []
    for word in segment.split():
        out.extend(_expand(word))
    return out


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    if not hookio.grep_q_line(WRITES_A_FILE, scan):
        return hookio.ALLOW

    # EVERY agent-browser segment that actually writes a file, not just the first one. `head -1` was wrong twice over: in `agent-browser open URL && agent-browser screenshot
    # /abs/x.png` it judged the `open` half, which has no path, and blocked a correct command;
    # and with two output subcommands on one line it never looked at the second at all.
    spans = hookio.grep_o(SEGMENT_SPAN, scan)
    segments = hookio.grep_lines(SEGMENT_VERB, hookio._grep_out(spans))

    for segment in segments:
        words = _words(segment)

        # 1. An unrecognised long flag will be consumed as a positional.
        for tok in words:
            if hookio.case_glob(tok, *KNOWN_FLAGS):
                continue
            if hookio.case_glob(tok, "--*"):
                ev.warn_raw(
                    MESSAGE
                    % (
                        "Unrecognised flag '%s'. agent-browser will consume it as the output PATH."
                        % tok
                    )
                )
                return hookio.DENY

        # 2. An absolute path under the repo root is an in-tree write.
        for tok in words:
            if hookio.case_glob(tok, REPO_ROOT + "/*"):
                ev.warn_raw(MESSAGE % ("'%s' is inside the repo at %s." % (tok, REPO_ROOT)))
                return hookio.DENY

        # 3. No absolute path at all means the file resolves against $PWD.
        printed = "".join(word + "\n" for word in words) if words else "\n"
        if not hookio.grep_q(r"^/", printed):
            ev.warn_raw(
                MESSAGE
                % "No absolute output path. A bare or relative filename resolves against $PWD."
            )
            return hookio.DENY

    return hookio.ALLOW
