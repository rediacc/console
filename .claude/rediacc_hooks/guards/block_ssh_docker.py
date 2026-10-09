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
# commands reach it through `shellscan.lifted_commands`, and so does `sshpass`, a prefix shellscan strips like `sudo` (`shellscan._PREFIX_COMMANDS`, #ec63ff8c): `sshpass -p x ssh prod-1 docker ps` lifts `ssh prod-1 docker ps` onto a line of its own. BRIDGE keeps the same anchor so the carve-out answers about the same ssh the refusal found.
SSH_AT_CMD = r"(^|[;&|(`{!])[{S}]*([^{S};|&()`]*/)?ssh[{S}]"
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
    ("sshpass is a prefix shellscan strips", "sshpass -p x ssh prod-1 docker ps"),
    # The remote command is a payload (#ec63ff8c): each of these was allowed before 2026-10-09.
    ("a quoted remote command", 'ssh prod-1 "docker ps"'),
    (
        "a quoted remote command behind ssh flags and sudo",
        "ssh -p 2222 -i key prod-1 'sudo docker ps'",
    ),
    ("a quoted remote command behind sshpass", 'sshpass -p x ssh prod-1 "docker ps"'),
    (
        "docker after a separator inside the remote command",
        "ssh -t prod-1 'cd /srv && docker compose up -d'",
    ),
    (
        "the bridge carve-out is per ssh, not per line",
        "ssh 192.168.111.10 uptime; ssh prod-1 docker ps",
    ),
    # ... and the argv shapes ssh_remote_commands has to parse to find the remote command; every one runs docker on prod-1 and is refused.
    ("an ssh option after the destination", 'ssh prod-1 -t "docker ps"'),
    ("a double dash before the destination", 'ssh -- prod-1 "docker ps"'),
    ("a shell payload inside the remote command", """ssh prod-1 'bash -lc "docker ps"'"""),
    ("a jump host and a login name", "ssh -J bastion -l root prod-1 'docker ps'"),
    ("docker-compose in the remote command", 'ssh prod-1 "docker-compose ps"'),
    ("an ssh hop inside the remote command", 'ssh bastion ssh prod-1 "docker ps"'),
    ("inside a command substitution", 'X=$(ssh prod-1 "docker ps")'),
    ("sshpass -e takes no value", 'sshpass -e ssh prod-1 "docker ps"'),
    # What the payload reading must NOT refuse: none of these runs docker on a managed machine.
    ("a quoted remote command on the bridge VM", 'ssh 192.168.111.10 "docker ps"'),
    ("a remote command that only names docker", "ssh prod-1 'echo docker'"),
    ("a quoted remote command with no docker", 'ssh prod-1 "uptime"'),
    (
        "an option value is not the remote command",
        "ssh -o 'ProxyCommand=ssh -W %h:%p jump' prod-1 uptime",
    ),
    ("a remote command that only prints docker", """ssh prod-1 'echo "docker ps"'"""),
    ("a control command names no remote command", "ssh -O check prod-1"),
    ("scp of a compose file", "scp docker-compose.yml prod-1:/srv/"),
    ("a login name on the bridge VM", "ssh root@192.168.111.10 'docker ps'"),
    ("sshpass with no docker", "sshpass -p pw ssh prod-1 ls"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if hookio.grep_q(SSH_DOCKER, scan) and not hookio.grep_q(BRIDGE, scan):
        ev.warn(MESSAGE)
        return hookio.DENY
    if remote_docker(cmd):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW


# THE REMOTE COMMAND IS A PAYLOAD, NOT PROSE (#ec63ff8c). ssh joins the words after the destination and the far side's shell parses them again, so `ssh prod-1 "docker ps"` runs docker exactly as `ssh prod-1 docker ps` does. The view above drops every quoted span, so the quoted spelling was allowed (rc 0, 2026-10-09). `shellscan.ssh_remote_commands` names each ssh's destination and remote
# command, and docker must be a command the remote shell RUNS, so `ssh prod-1 'echo docker'` stays allowed. The bridge carve-out is judged per ssh here, by its own destination: `ssh 192.168.111.10 uptime; ssh prod-1 docker ps` was allowed because BRIDGE above found the bridge address anywhere on the line.
DOCKER_PROGRAMS = ("docker", "docker-compose")


def remote_docker(cmd):
    for destination, remote in shellscan.ssh_remote_commands(cmd):
        if "192.168.111." in destination:
            continue
        if any(r.name.rsplit("/", 1)[-1] in DOCKER_PROGRAMS for r in shellscan.every_run(remote)):
            return True
    return False
