"""Block manual binary deploys via scp / sudo cp of the renet binary.

DEPLOYING IS UPLOADING. The original pattern was `^scp `, which refuses every scp of every file in either direction -- including the one that is not a deploy at all:

  scp host:/var/log/renet.log ./logs/     <- pulling a log back to diagnose

That is the opposite of deploying a binary, and refusing it pushes the work onto a clumsier path with no benefit. A guard is judged by what it lets through as much as by what it stops, and until 2026-08-27 nothing here asserted this one let anything through.

The direction is decidable: scp's LAST argument is its destination, and a destination naming a remote host (`host:path`, `user@host:path`) is an upload. Anything else is a download.

THE CLAUSE LOOP IS GONE (review a2d44aa4.1). The bash original split the command on `;&|` and read each clause with a here-string loop; its own comment recorded two ways that loop silently allowed every upload. The guard now reads shellscan's runs, so neither the split nor the loop exists, and scp's operands come from the shell's own word splitting instead of the last blank-separated field of a clause.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 7

# Dropping the host-spec test restores the `^scp ` behaviour the 2026-08-27 change removed: every scp is a deploy again, downloads included. It is the one line that separates "uploading a binary" from "pulling a log back".
DEFECT = (
    "if shellscan.unresolved(dest) or hookio.grep_q(HOST_SPEC, dest):",
    "if True:",
)

MESSAGE = (
    "❌ BLOCKED: Do not manually deploy binaries via scp/ssh. Use ./rdc.sh which "
    "handles provisioning automatically."
)

# The renet binary specifically, however it gets there. ANCHORED TO COMMAND POSITION 2026-08-28, after check:ci-guard-mention-anchoring found this guard refusing an ordinary sentence. Matching the phrase ANYWHERE means a doc line, a worklist note or an `echo` explaining the rule is refused as if it were the rule being broken. This NARROWS PROSE ONLY: every control below still
# blocks the real command, at line start and after a separator.
SUDO_CP = hookio.rx(r"(^|[;&|(])[{B}]*sudo cp[^;&|]*/usr/local/bin/renet")

# EVERY scp RUN, WHATEVER LAUNCHED IT (review a2d44aa4.1, #ecb59527). The guard once matched `scp` after any blank in the raw text, so a sentence naming scp was refused as an upload. Then it matched only at command position with the launchers listed by hand, which let `xargs scp bin/renet host:/p` and `find . -exec scp {} host:/p \;` through. It now asks shellscan for every run the shell would start (`every_run`: the prefix commands stripped, `xargs`, `find -exec`, `npx`, `sh -c` and command substitutions walked) and judges each one named scp by its destination. A sentence that names scp is an `echo` or `git` run, so it never reaches the test.


# A host spec: a hostname (optionally user@) followed by a colon. A local path containing a colon has a slash before it, so it cannot match here.
HOST_SPEC = r"^[A-Za-z0-9_.-]+(@[A-Za-z0-9_.-]+)?:"

EDGE_CASES = [
    ("an upload names a host as its destination", "scp bin/renet host:/usr/local/bin/renet"),
    ("user@host is still a host", "scp bin/renet root@10.0.0.1:/usr/local/bin/renet"),
    # The case the 2026-08-27 change exists for, and the reason a block-only corpus would have missed it entirely.
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
    # Command position, not a blank (#ecb59527). Every launcher a real upload can hide behind still reaches the host-spec test, and a sentence that merely names scp does not.
    ("sudo still reaches the upload", "sudo scp bin/renet root@10.0.0.1:/p"),
    ("scp after && is at command position", "true && scp x h:/p"),
    ("nohup still reaches the upload", "nohup scp x h:/p"),
    ("an assignment prefix still reaches the upload", "FOO=1 scp x h:/p"),
    ("sshpass still reaches the upload", "sshpass -p x scp x h:/p"),
    # Two shapes the blank-anchored pattern let through, refused since the anchor learned a directory and the `(` / `$(` separators.
    ("scp by its full path", "/usr/bin/scp x h:/p"),
    ("scp inside a command substitution", "echo $(scp x h:/p)"),
    (
        "an unquoted sentence naming scp is not an upload",
        "echo never run scp bin/renet host:/usr/local/bin/renet",
    ),
    ("a commit message naming scp is not an upload", "git commit -m 'docs: scp x h:/p'"),
    # Launchers the command-position text pattern missed (review a2d44aa4.1).
    ("xargs still reaches the upload", "xargs scp bin/renet host:/usr/local/bin/renet"),
    ("find -exec still reaches the upload", "find . -name renet -exec scp {} host:/d \\;"),
    ("xargs -I still reaches the upload", "xargs -I{} scp {} host:/d"),
    ("npx still reaches the upload", "npx -y scp x h:/p"),
    ("sh -c still reaches the upload", "bash -c 'scp x h:/p'"),
    ("timeout N still reaches the upload", "timeout 30 scp x h:/p"),
    # xargs appends its input last, so this copies FROM the host: a download.
    ("xargs-appended sources make a download", "echo bin/renet | xargs scp host:/d"),
    # Options are set aside the way getopt reads them (review f212d159.1).
    ("a trailing option does not hide the upload", "scp bin/renet host:/usr/local/bin/renet -q"),
    ("a value option before the operands", "scp -P 2222 -o BatchMode=yes bin/renet host:/p"),
    ("an attached value option", "scp -P2222 bin/renet host:/p"),
    ("a trailing option after a download", "scp host:/var/log/renet.log ./logs/ -q"),
    ("a value that looks like a host is the option's", "scp -J jump:22 a.txt b.txt"),
    # A destination built at run time is judged as an upload (review f212d159.2).
    ("a substituted destination is judged strictly", "scp bin/renet $(cat dest.txt)"),
    ("an assigned destination is read", "D=host:/p; scp bin/renet $D"),
]


# The scp options that take a value (OpenSSH scp(1)): -c cipher, -D sftp_server_path, -F ssh_config, -i identity_file, -J destination, -l limit, -o ssh_option, -P port, -S program, -X sftp_option.
SCP_VALUE_LETTERS = frozenset("cDFiJloPSX")


def _scp_destination(args):
    """scp's destination: the last operand once the options are set aside, or None with fewer than two operands.

    glibc's getopt permutes, so an option may follow the operands (`scp a host:/p -q` uploads), and the last WORD is not the destination (review f212d159.1). Options are read the way getopt reads them: a bundle of letters, where a value letter takes the rest of its word or the next word, and `--` ends the options.
    """
    operands = []
    i = 0
    while i < len(args):
        word = args[i]
        i += 1
        if word == "--":
            operands.extend(args[i:])
            break
        if word.startswith("-") and len(word) > 1 and not shellscan.unresolved(word):
            for j, letter in enumerate(word[1:], start=1):
                if letter in SCP_VALUE_LETTERS:
                    if j == len(word) - 1:
                        i += 1
                    break
            continue
        operands.append(word)
    return operands[-1] if len(operands) >= 2 else None


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    if hookio.grep_q(SUDO_CP, cmd):
        ev.warn(MESSAGE)
        return hookio.DENY

    for run_ in shellscan.every_run(cmd):
        if run_.name.rsplit("/", 1)[-1] != "scp":
            continue
        args = run_.argv if run_.xargv is None else run_.xargv
        dest = _scp_destination(args)
        if dest is None:
            continue
        # A destination built at run time (`$(...)`, an unset variable) cannot be read here, so it is judged the strict way: as an upload (review f212d159.2).
        if shellscan.unresolved(dest) or hookio.grep_q(HOST_SPEC, dest):
            ev.warn(MESSAGE)
            return hookio.DENY
    return hookio.ALLOW
