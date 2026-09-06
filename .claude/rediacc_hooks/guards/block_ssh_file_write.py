"""Block raw SSH file writes via tee/cat/echo/printf redirection (allow bridge VM 192.168.111.*).

Stderr/dev-null redirects (2>&1, 2>/dev/null, >/dev/null) are read-only plumbing, not writes.

Scan the command, not the prose. Matching raw text meant `echo 'cat a | ssh
host tee /etc/x'` was refused -- a string, not a write. hook_scan_target drops
heredoc bodies and quoted spans while still extracting `sh -c` / `eval`
payloads, so a wrapped ssh-write is caught exactly as before.

PORT NOTE ON THE MISSING EMPTY GUARD. Unlike nearly every sibling, this file
has no `[ -z "$CMD" ] && exit 0`: it reads `.tool_input.command` with a bare
`jq -r` (so an absent key is the four characters `null`) and scans whatever it
got, empty string included. `scan_target("")` returns a single newline that the
command substitution then removes, so the empty case reaches grep as one empty
record and matches nothing. That is why `hook_init` is NOT used here and
`ev.raw` plus `scan_target` are spelled out instead -- `hook_init` would return
None on the empty command and skip a scan the bash really does perform.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-ssh-file-write.sh"
ORDER = 10

# The bridge-VM carve-out, read from the RAW command rather than the scan. That
# asymmetry is the bash's own: the write shapes are matched against the
# prose-stripped scan, the address against `$CMD`, so an address that lives
# inside a quoted span still exempts the command.
DEFECT = ("and not hookio.grep_q_line(BRIDGE, cmd)", "and True")

# `sed -E 's/[0-9]?>+[[:space:]]*(&[0-9]|\\/dev\\/null)//g'` -- the read-only
# plumbing, removed before the write shapes are looked for.
PLUMBING = r"[0-9]?>+[" + hookio.SPACE + r"]*(&[0-9]|/dev/null)"

# ANCHORED TO COMMAND POSITION 2026-08-28, found by
# check:ci-guard-mention-anchoring. The first branch already required an actual
# `|` before `ssh`; the SECOND had no anchor at all, so
# "echo the guard blocks ssh ... cat > file redirections" refused as if it were
# the write itself. hook_scan_target's quote-stripping above covers the QUOTED
# case only, same class as block-git-empty-commit.sh's fix the same day.
#
# PORT NOTE ON `\s`. GNU grep's `\s` in the C locale is exactly `[[:space:]]`,
# while Python's is Unicode-aware and would also match U+00A0. The class is
# written out rather than carried across as `\s` so the two sides cannot
# disagree on a non-breaking space.
SSH_WRITE = (
    r"(\|["
    + hookio.SPACE
    + r"]*\bssh\b["
    + hookio.SPACE
    + r"][^|;&]*\btee\b|(^|[;&|(]|&&|\|\|)["
    + hookio.SPACE
    + r"]*\bssh\b["
    + hookio.SPACE
    + r"][^|;&]*\b(cat|echo|printf)\b[^|;&]*>)"
)

BRIDGE = r"192\.168\.111\."

MESSAGE = (
    "❌ BLOCKED: Raw SSH file write detected. Use: ./rdc.sh repo sync upload -m MACHINE -r "
    "REPO --local FILE --remote PATH. That transfers via rsync with delta compression and "
    "proper permissions."
)

EDGE_CASES = [
    ("a pipe into ssh tee", "cat a | ssh prod-1 tee /etc/x"),
    ("ssh with a cat redirection at a command position", "ssh prod-1 cat foo > /etc/x"),
    ("ssh printf redirection after a separator", "true; ssh prod-1 printf hi > /etc/x"),
    # The bridge VM is where raw writes over ssh are the sanctioned thing.
    ("the bridge VM is allowed", "cat a | ssh 192.168.111.10 tee /etc/x"),
    # The 2026-08-28 anchoring exists for this one.
    ("prose naming the rule is not the rule being broken", "echo 'ssh prod-1 cat x > /etc/y'"),
    ("an unanchored mention of the rule", "echo the guard blocks ssh and cat > file"),
    # Read-only plumbing is stripped before the shapes are looked for.
    ("stderr plumbing is not a write", "ssh prod-1 cat /etc/x 2>/dev/null"),
    ("dev-null plumbing is not a write", "ssh prod-1 echo hi >/dev/null"),
    ("a wrapper payload is still scanned", "sh -c 'ssh prod-1 cat a > /etc/x'"),
    ("ssh with no write", "ssh prod-1 uptime"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    stripped = hookio.sed_sub(PLUMBING, "", scan)
    if hookio.grep_q_line(SSH_WRITE, stripped) and not hookio.grep_q_line(BRIDGE, cmd):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
