"""Block raw SSH file writes via tee/cat/echo/printf redirection (allow bridge VM 192.168.111.*).

Stderr/dev-null redirects (2>&1, 2>/dev/null, >/dev/null) are read-only plumbing, not writes.

Scan the command, not the prose. Matching raw text meant `echo 'cat a | ssh host tee /etc/x'` was refused -- a string, not a write. hook_scan_target drops heredoc bodies and quoted spans while still extracting `sh -c` / `eval` payloads, so a wrapped ssh-write is caught exactly as before.

PORT NOTE ON THE MISSING EMPTY GUARD, kept as history: Rule T (PLAN-retire-bash-oracles A4) added the guard in `run`. Unlike nearly every sibling, this file had no `[ -z "$CMD" ] && exit 0`: it reads `.tool_input.command` with a bare `jq -r` (so an absent key is the four characters `null`) and scans whatever it got, empty string included. `scan_target("")` returns a single newline that the command substitution then removes, so the empty case reaches grep as
one empty record and matches nothing. That is why `hook_init` is NOT used here and `ev.raw` plus `scan_target` are spelled out instead -- `hook_init` would return None on the empty command and skip a scan the bash really does perform.
"""

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import tables

__getattr__ = tables("block_ssh_file_write", "EDGE_CASES")

CHAIN = "pre-bash"
ORDER = 10

# The bridge-VM carve-out, read from the RAW command rather than the scan. That asymmetry is the bash's own: the write shapes are matched against the prose-stripped scan, the address against `$CMD`, so an address that lives inside a quoted span still exempts the command.
DEFECT = ("and not hookio.grep_q_line(BRIDGE, cmd)", "and True")

# `sed -E 's/[0-9]?>+[[:space:]]*(&[0-9]|\\/dev\\/null)//g'` -- the read-only plumbing, removed before the write shapes are looked for.
PLUMBING = hookio.rx(r"[0-9]?>+[{S}]*(&[0-9]|/dev/null)")

# ANCHORED TO COMMAND POSITION 2026-08-28, found by check:ci-guard-mention-anchoring. The first branch already required an actual `|` before `ssh`; the SECOND had no anchor at all, so "echo the guard blocks ssh ... cat > file redirections" refused as if it were the write itself. hook_scan_target's quote-stripping above covers the QUOTED
# case only, same class as block-git-empty-commit.sh's fix the same day.
#
# PORT NOTE ON `\s`. GNU grep's `\s` in the C locale is exactly `[[:space:]]`,
# while Python's is Unicode-aware and would also match U+00A0. The class is
# written out rather than carried across as `\s` so the two sides cannot disagree on a non-breaking space.
SSH_WRITE = hookio.rx(
    r"(\|[{S}]*\bssh\b[{S}][^|;&]*\btee\b|(^|[;&|(]|&&|\|\|)[{S}]*\bssh\b[{S}][^|;&]*\b(cat|echo|printf)\b[^|;&]*>)"
)

BRIDGE = r"192\.168\.111\."

# RULE T (PLAN-retire-bash-oracles A4, A0 L13): THE REDIRECT LOCALITY WAS BACKWARDS. `ssh h cat f > /etc/x` is refused above, yet its `>` is performed by the LOCAL shell and writes a local file. The real remote writes are the ones whose redirect ssh CARRIES: `ssh h 'cat > /etc/x' < f` and `ssh h "echo hi > /etc/x"` hand the remote shell a command containing the redirect, and the prose-stripped scan deletes exactly that quoted span, so both passed with rc 0 (measured 2026-09-24).
#
# `ssh` joins every word after the host with single spaces and the REMOTE shell parses the result, so the quote removal the local shell already did is the right starting point, and `shellscan.write_targets` then asks the same lexer every guard now shares where the remote shell would redirect. A `tee` with a file operand is a write the same way. The local-redirect over-block is KEPT, deliberately: relaxing it would weaken a deny, and the task that found it (Rule T) only licenses tightening where bash really runs something.
#
# ONE ssh PARSER (#503f0ba8). This file carried its own copy of ssh's option table and its own remote-command reader, which read only the `ssh` runs on `_analyse(cmd).runs`: an ssh that `find -exec` or `npx -c` starts was never judged (`find . -exec ssh prod-1 'cat > /etc/x' ';'` ran with rc 0, measured 2026-10-09). `shellscan.ssh_remote_commands` is the reader `block_ssh_docker` uses; it walks launched commands, strips `sshpass`, and yields every hop.

# A remote redirect onto one of these is plumbing, not a file write -- the same set PLUMBING strips above.
REMOTE_PLUMBING = frozenset(("/dev/null", "/dev/stdout", "/dev/stderr"))


def remote_write(cmd):
    """True when some `ssh` in `cmd` makes the remote shell write a file. An interactive login names no remote command and writes nothing."""
    for _destination, remote in shellscan.ssh_remote_commands(cmd):
        if any(target not in REMOTE_PLUMBING for target in shellscan.write_targets(remote)):
            return True
        for inner in shellscan.every_run(remote):
            if inner.name.rsplit("/", 1)[-1] == "tee" and any(
                a not in REMOTE_PLUMBING and not a.startswith("-") for a in inner.argv
            ):
                return True
    return False


MESSAGE = (
    "❌ BLOCKED: Raw SSH file write detected. Use: ./rdc.sh repo sync upload -m MACHINE -r "
    "REPO --local FILE --remote PATH. That transfers via rsync with delta compression and "
    "proper permissions."
)


def run(ev):
    # RULE T (PLAN-retire-bash-oracles A4): the empty guard the PORT NOTE above records as missing. `field` is `// empty`, so an absent or null command is "" rather than the four characters `null`, and nothing is scanned. Neither shape could ever match a write, so no answer changes; what goes is a scan of text nobody typed.
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    stripped = hookio.sed_sub(PLUMBING, "", scan)
    written = hookio.grep_q_line(SSH_WRITE, stripped) or remote_write(cmd)
    if written and not hookio.grep_q_line(BRIDGE, cmd):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
