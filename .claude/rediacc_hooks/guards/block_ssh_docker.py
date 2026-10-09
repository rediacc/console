"""Block raw ssh+docker on a rediacc-managed machine (allow bridge VM 192.168.111.*).

ROUTED THROUGH lib/command-scan.sh 2026-08-27, which in this tree is `rediacc_hooks.shellscan`. Matching the raw command meant matching PROSE: `echo '<the banned command>'` was refused, and so was a worklist note or a doc quoting it. `scan_target` removes heredoc bodies and quoted spans while still extracting `sh -c` / `eval` payloads, so a command hidden in a wrapper is scanned
exactly as before -- this narrows what the guard refuses, never what it catches.

PORT NOTE. `SCAN=$(hook_scan_target "$CMD")` is a command substitution, so the
trailing newline `scan_target` writes is removed before grep ever sees it; and the subject is fed with `printf '%s'`, not a here-string, so an EMPTY subject would give grep no records at all. Neither detail can be inferred from the Python, and both change what matches, so `scan_target` is wrapped in `_command_substitution` and the plain `grep_q` is used rather than `grep_q_line`.
`shellscan.hook_init` performs exactly this pair, which is why it is called here instead of a second spelling of it.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 9

# The bridge-VM carve-out. Without it every `ssh 192.168.111.x docker ...` is refused, and that address range is the one machine where raw docker over ssh is the sanctioned thing to do.
DEFECT = ("and not hookio.grep_q(BRIDGE, scan)", "and True")

# COMMAND POSITION, NOT A WORD BOUNDARY. `\bssh\b` matched `ssh` anywhere, so `echo the docs say never to run ssh docker in this repo` was refused (found by check:ci-guard-mention-anchoring, 2026-10-09). Now `ssh` must open a command: the line start or a separator, then optional blanks, then an optional directory (`/usr/bin/ssh`). `sudo`, `timeout`, an assignment and the other prefix
# commands reach it through `shellscan.lifted_commands`. `sshpass` is not one shellscan unwraps, so the anchor admits it and its flags by name: `sshpass -p x ssh prod-1 docker ps` was refused through `\bssh\b` and is kept refused. BRIDGE keeps the same anchor so the carve-out answers about the same ssh the refusal found.
SSH_AT_CMD = r"(^|[;&|(`{!])[{S}]*(sshpass([{S}]+-[^{S};|&]+([{S}]+[^-{S};|&][^{S};|&]*)?)*[{S}]+)?([^{S};|&()`]*/)?ssh[{S}]"
SSH_DOCKER = hookio.rx(SSH_AT_CMD + r"[^|;&]*\bdocker\b")
BRIDGE = hookio.rx(SSH_AT_CMD + r"[^|;&]*192\.168\.111\.")

MESSAGE = (
    "❌ BLOCKED: Do not run raw ssh+docker on a rediacc-managed machine. Use: ./rdc.sh "
    "term connect -m MACHINE -r REPO -c DOCKER_CMD. That runs inside the repo sandbox "
    "with DOCKER_HOST preset, no sudo needed. Only bypass by editing "
    ".claude/settings.json if rdc genuinely cannot reach the daemon (e.g. host-level "
    "docker, not a rediacc repo)."
)

EDGE_CASES = [
    ("the plain shape", "ssh prod-1 docker ps"),
    ("the bridge VM is allowed", "ssh 192.168.111.10 docker ps"),
    # The 2026-08-27 routing exists for these two.
    ("quoted prose is not a command", "echo 'ssh prod-1 docker ps'"),
    ("a heredoc body is data", "cat > note.md <<'EOF'\nssh prod-1 docker ps\nEOF"),
    # ... and this is what the routing must NOT have cost.
    ("a wrapper payload is still scanned", "sh -c 'ssh prod-1 docker ps'"),
    ("an eval payload is still scanned", "eval 'ssh prod-1 docker ps'"),
    ("a separator ends the clause before docker", "ssh prod-1 true; docker ps"),
    ("ssh with no docker", "ssh prod-1 uptime"),
    ("docker with no ssh", "docker ps"),
    # Command position: `\bssh\b` refused this sentence before 2026-10-09.
    (
        "a sentence naming the command is not running it",
        "echo the docs say never to run ssh docker in this repo",
    ),
    ("a prefix command still reaches it", "sudo ssh prod-1 docker ps"),
    ("an ssh by path", "/usr/bin/ssh prod-1 docker ps"),
    ("sshpass is a launcher shellscan does not unwrap", "sshpass -p x ssh prod-1 docker ps"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if hookio.grep_q(SSH_DOCKER, scan) and not hookio.grep_q(BRIDGE, scan):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
