"""Block manual binary deploys via scp / sudo cp of the renet binary.

DEPLOYING IS UPLOADING. The original pattern was `^scp `, which refuses every
scp of every file in either direction -- including the one that is not a
deploy at all:

  scp host:/var/log/renet.log ./logs/     <- pulling a log back to diagnose

That is the opposite of deploying a binary, and refusing it pushes the work
onto a clumsier path with no benefit. A guard is judged by what it lets
through as much as by what it stops, and until 2026-08-27 nothing here
asserted this one let anything through.

The direction is decidable: scp's LAST argument is its destination, and a
destination naming a remote host (`host:path`, `user@host:path`) is an
upload. Anything else is a download.

PORT NOTE ON THE LOOP THE BASH HAD TO GET RIGHT TWICE. The original's second
arm reads:

    while IFS= read -r clause; do ... done <<<"$(printf '%s' "$CMD" | tr ';&|' '\\n\\n\\n')"

and its comment records both mistakes in one line. Piping put the loop in a
subshell where `exit 2` could not leave the script; and `printf '%s'` gave the
clauses no trailing newline, so `read` returned non-zero on the only line and
the body never ran at all -- the guard reported every upload as ALLOWED while
its block case went green on a no-op. Neither hazard exists in Python, so the
prose above is the only surviving record of them, which is exactly what
section 5c of the driver contract is about. What DOES survive as behaviour is
the here-string's newline: `<<<` terminates its subject, so a command with no
trailing newline still yields one final clause. `_here_string` supplies it.
"""

from rediacc_hooks import hookio

CHAIN = "pre-bash"
TWIN = "pre-bash/block-binary-deploy.sh"
ORDER = 7

# Dropping the host-spec test restores the `^scp ` behaviour the 2026-08-27
# change removed: every scp is a deploy again, downloads included. It is the
# one line that separates "uploading a binary" from "pulling a log back".
DEFECT = (
    "if not hookio.grep_q(HOST_SPEC, dest):\n            continue",
    "if False:\n            continue",
)

MESSAGE = (
    "❌ BLOCKED: Do not manually deploy binaries via scp/ssh. Use ./rdc.sh which "
    "handles provisioning automatically."
)

# The renet binary specifically, however it gets there.
# ANCHORED TO COMMAND POSITION 2026-08-28, after check:ci-guard-mention-anchoring
# found this guard refusing an ordinary sentence. Matching the phrase ANYWHERE
# means a doc line, a worklist note or an `echo` explaining the rule is refused
# as if it were the rule being broken. This NARROWS PROSE ONLY: every control
# below still blocks the real command, at line start and after a separator.
SUDO_CP = hookio.rx(r"(^|[;&|(])[{B}]*sudo cp[^;&|]*/usr/local/bin/renet")

SCP_CLAUSE = hookio.rx(r"(^|[{B}])scp[{B}]")

# A host spec: a hostname (optionally user@) followed by a colon. A local
# path containing a colon has a slash before it, so it cannot match here.
HOST_SPEC = r"^[A-Za-z0-9_.-]+(@[A-Za-z0-9_.-]+)?:"

EDGE_CASES = [
    ("an upload names a host as its destination", "scp bin/renet host:/usr/local/bin/renet"),
    ("user@host is still a host", "scp bin/renet root@10.0.0.1:/usr/local/bin/renet"),
    # The case the 2026-08-27 change exists for, and the reason a block-only
    # corpus would have missed it entirely.
    ("a DOWNLOAD is not a deploy", "scp host:/var/log/renet.log ./logs/"),
    ("a local copy is not a deploy", "scp a.txt b.txt"),
    ("a local path with a colon has a slash first", "scp x ./a:b/c"),
    ("sudo cp at a command position", "sudo cp renet /usr/local/bin/renet"),
    ("sudo cp after a separator", "true; sudo cp renet /usr/local/bin/renet"),
    (
        "prose naming the rule is not the rule being broken",
        "echo 'never sudo cp renet /usr/local/bin/renet'",
    ),
    ("scp in a later clause of a chain", "echo hi && scp bin/renet host:/tmp/renet"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    if hookio.grep_q(SUDO_CP, cmd):
        ev.warn(MESSAGE)
        return hookio.DENY

    # Each scp clause, judged by where it is sending things. `tr ';&|' '\n\n\n'`
    # is a byte map, not a split: the separator becomes a newline, so a clause
    # never carries the character that ended it.
    clauses = cmd
    for sep in ";&|":
        clauses = hookio._tr(clauses, sep, "\n")
    records, _ = hookio._records(hookio._here_string(clauses))
    for clause in records:
        if not hookio.grep_q(SCP_CLAUSE, clause):
            continue
        # `awk '{print $NF}'` over one record: the last whitespace-separated
        # field, or nothing at all when the record is empty.
        dest = hookio._command_substitution(hookio.awk_field(clause, -1))
        if not hookio.grep_q(HOST_SPEC, dest):
            continue
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
