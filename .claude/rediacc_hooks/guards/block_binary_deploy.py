"""Block manual binary deploys via scp / sudo cp of the renet binary.

DEPLOYING IS UPLOADING. The original pattern was `^scp `, which refuses every scp of every file in either direction -- including the one that is not a deploy at all:

  scp host:/var/log/renet.log ./logs/     <- pulling a log back to diagnose

That is the opposite of deploying a binary, and refusing it pushes the work onto a clumsier path with no benefit. A guard is judged by what it lets through as much as by what it stops, and until 2026-08-27 nothing here asserted this one let anything through.

The direction is decidable: scp's LAST argument is its destination, and a destination naming a remote host (`host:path`, `user@host:path`) is an upload. Anything else is a download.

THE CLAUSE LOOP IS GONE (review a2d44aa4.1). The bash original split the command on `;&|` and read each clause with a here-string loop; its own comment recorded two ways that loop silently allowed every upload. The guard now reads shellscan's runs, so neither the split nor the loop exists, and scp's operands come from the shell's own word splitting instead of the last blank-separated field of a clause.
"""

import os
import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 7

# Dropping the host-spec test restores the `^scp ` behaviour the 2026-08-27 change removed: every scp is a deploy again, downloads included. It is the one line that separates "uploading a binary" from "pulling a log back".
DEFECT = (
    "return unread_upload or hookio.grep_q(HOST_SPEC, dest)",
    "return True",
)

MESSAGE = (
    "❌ BLOCKED: Do not manually deploy binaries via scp/ssh. Use ./rdc.sh which "
    "handles provisioning automatically."
)

# The renet binary specifically, however it gets there. JUDGED ON THE cp RUN, NOT THE TEXT (worklist #0c331972). The 2026-08-28 command-position anchor `(^|[;&|(])sudo cp` still read raw text, so a separator INSIDE a quoted sentence was a command position: `echo 'true; sudo cp renet /usr/local/bin/renet'` was refused as a deploy. A deploy is a `cp` that `sudo` runs (`_Run.via`, so `sudo -u root cp`, `xargs`, `sh -c` and `find -exec` all reach it) whose DESTINATION is the installed binary: the last operand, or the `-t`/`--target-directory` directory with a `renet` source. A cp that only READS the installed binary (`sudo cp /usr/local/bin/renet /tmp/bak`) is a backup, the cp twin of the scp download below.
INSTALL_DIR = "/usr/local/bin"
# The installed binary and its staged siblings (`renet.new`, `renet-v2`, `renet_tmp`).
INSTALLED_NAME = re.compile(r"renet(?:[._-].*)?")


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
    # #0c331972: a separator inside quotes is not a command position, and every real spelling still reaches the cp run.
    ("a quoted separator is prose", "echo 'true; sudo cp renet /usr/local/bin/renet'"),
    ("sudo with an option", "sudo -u root cp renet /usr/local/bin/renet"),
    ("sudo cp inside sh -c", "sh -c 'sudo cp bin/renet /usr/local/bin/renet'"),
    ("sudo cp into the directory", "sudo cp bin/renet /usr/local/bin/"),
    ("sudo cp -t the directory", "sudo cp -t /usr/local/bin bin/renet"),
    ("backing up the installed binary is a read", "sudo cp /usr/local/bin/renet /tmp/renet.bak"),
    ("xargs feeds the source", "echo bin/renet | sudo xargs cp -t /usr/local/bin"),
    # Review 0bbd6471.1: every copier `sudo` runs, and a renet-named sibling in the install directory.
    ("sudo cp to a staged sibling", "sudo cp bin/renet /usr/local/bin/renet.new"),
    (
        "the two-step deploy",
        "sudo cp bin/renet /usr/local/bin/renet.new && sudo mv /usr/local/bin/renet.new /usr/local/bin/renet",
    ),
    ("sudo mv onto the binary", "sudo mv /tmp/renet /usr/local/bin/renet"),
    ("sudo install onto the binary", "sudo install -m 755 bin/renet /usr/local/bin/renet"),
    ("a renet-named source into the directory", "sudo cp bin/renet-v2 /usr/local/bin/"),
    ("xargs feeds the destination", "echo /usr/local/bin/renet | sudo xargs cp bin/renet"),
    ("xargs feeds scp a host destination", "echo host:/usr/local/bin/renet | xargs scp bin/renet"),
    ("install -d copies nothing", "sudo install -d /usr/local/bin/"),
    # Review 88362611.1: the destination as bash expands it.
    ("a destination set by an earlier statement", "D=/usr/local/bin/renet; sudo cp bin/renet $D"),
    # Review 126f2a9f.1: bash brace-expands the fed word before xargs reads it.
    (
        "a brace-expanded fed destination",
        "echo {/tmp/x,/usr/local/bin/renet} | sudo xargs cp bin/renet",
    ),
    ("sudo cp of another binary", "sudo cp bin/rdc /usr/local/bin/rdc"),
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
    # In replace mode xargs appends nothing: the fed word stands where the marker is, and scp's own last word stays the destination. Both uploads were allowed before, read as a copy into the fed word.
    (
        "a fed xargs -I still uploads",
        "echo bin/renet | xargs -I{} scp {} host:/usr/local/bin/renet",
    ),
    ("a fed xargs --replace still uploads", "echo bin/renet | xargs --replace=X scp X host:/d"),
    (
        "a fed xargs -I download stays one",
        "echo host:/var/log/renet.log | xargs -I{} scp {} ./logs/",
    ),
    # The marker as the DESTINATION (review c3ac54d7.1): the fed word is where the copy lands.
    (
        "a fed xargs -I destination uploads",
        "echo host:/usr/local/bin | xargs -I{} scp bin/renet {}",
    ),
    (
        "a fed xargs -I with a spaced marker uploads",
        "echo host:/usr/local/bin | xargs -I % scp bin/renet %",
    ),
    (
        "a fed xargs -I local destination is local",
        "echo ./out | xargs -I{} scp host:/var/log/renet.log {}",
    ),
    # Review 036b9e17.1: replace mode inside a bundle of short options, the marker as a source and as the destination.
    (
        "a bundled xargs -rI still uploads",
        "echo bin/renet | xargs -rI{} scp {} host:/usr/local/bin/renet",
    ),
    (
        "a bundled xargs -rI destination uploads",
        "echo host:/usr/local/bin | xargs -rI{} scp bin/renet {}",
    ),
    # Options are set aside the way getopt reads them (review f212d159.1).
    ("a trailing option does not hide the upload", "scp bin/renet host:/usr/local/bin/renet -q"),
    ("a value option before the operands", "scp -P 2222 -o BatchMode=yes bin/renet host:/p"),
    ("an attached value option", "scp -P2222 bin/renet host:/p"),
    ("a trailing option after a download", "scp host:/var/log/renet.log ./logs/ -q"),
    ("a value that looks like a host is the option's", "scp -J jump:22 a.txt b.txt"),
    # A destination built at run time is judged as an upload (review f212d159.2).
    ("a substituted destination is judged strictly", "scp bin/renet $(cat dest.txt)"),
    ("an assigned destination is read", "D=host:/p; scp bin/renet $D"),
    # A host source makes an unreadable local destination a download (review e69e9a3f.1).
    ("a download into a run-time path", 'scp host:/var/log/x "$DIR/"'),
    # One local source among host sources can still be the upload (review 70f58ef3.1).
    ("a mixed source list with a run-time destination", "scp bin/renet host:/x $(cat dest.txt)"),
]


# The scp options that take a value (OpenSSH scp(1)): -c cipher, -D sftp_server_path, -F ssh_config, -i identity_file, -J destination, -l limit, -o ssh_option, -P port, -S program, -X sftp_option.
SCP_VALUE_LETTERS = frozenset("cDFiJloPSX")


def _scp_operands(args):
    """scp's operands, the options set aside; the last one is the destination.

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
    return operands


def _sudo_copy_deploy(run_, cwd):
    """Is this a copy that `sudo` runs whose file lands in the install directory under a renet name?

    Every copier counts (`cp`, `mv`, `install`, `ln`, `rsync`), read where the copy LANDS (`shellscan.copy_landings`, so `-t`, a directory destination and the words xargs feeds are placed as the tool places them). A renet-named sibling (`renet.new`, `renet-v2`) counts too: `sudo cp bin/renet /usr/local/bin/renet.new` and then `mv` over the binary is the two-step deploy, and the old text match refused it because the text reached `/usr/local/bin/renet` (review 0bbd6471.1).
    """
    if "sudo" not in run_.via:
        return False
    return any(
        os.path.dirname(path) == INSTALL_DIR and INSTALLED_NAME.fullmatch(os.path.basename(path))
        for path, _into in shellscan.copy_landings(run_, cwd, shellscan.COPIERS)
    )


# xargs options that put the fed words in the command's own words in place of appending them: `-I R`, `-IR`, `-i`, `-iR`, `--replace`, `--replace=R`, and BSD's `-J R`.
def _replace_marker(options):
    """The marker an xargs in replace mode substitutes, None when it appends, and "" when it replaces with a marker this reader cannot name."""
    words = list(options)
    for at, option in enumerate(words):
        if option in ("-I", "-J"):
            return words[at + 1] if at + 1 < len(words) else ""
        if option.startswith(("-I", "-J")):
            return option[2:]
        if option in ("-i", "--replace"):
            return "{}"
        if option.startswith("--replace="):
            return option[len("--replace=") :] or "{}"
        if option.startswith("-i"):
            return option[2:]
        # A bundle of short options holding one of the three letters (`-rI{}`, `-0tI R`): which letter takes which value is xargs' own parse, so the marker is not named.
        if not option.startswith("--") and re.search(r"[IJi]", option[1:]):
            return ""
    return None


def _uploads(args):
    """Whether scp given `args` sends a file to a host."""
    operands = _scp_operands(args)
    if len(operands) < 2:
        return False
    dest = operands[-1]
    # A destination built at run time (`$(...)`, an unset variable) cannot be read here. It is an upload unless EVERY source names a host, which makes the copy a download into that local path; one local source can still be going up.
    unread_upload = shellscan.unresolved(dest) and not all(
        hookio.grep_q(HOST_SPEC, src) for src in operands[:-1]
    )
    return unread_upload or hookio.grep_q(HOST_SPEC, dest)


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    cwd = ev.field("cwd") or str(hookio.repo_root())
    for run_ in shellscan.every_run(cmd):
        if _sudo_copy_deploy(run_, cwd):
            ev.warn(MESSAGE)
            return hookio.DENY
        if run_.name.rsplit("/", 1)[-1] != "scp":
            continue
        args = list(run_.argv if run_.xargv is None else run_.xargv)
        readings = [args]
        if run_.feed and "xargs" in run_.via:
            # xargs appends its feed after scp's own words, so a fed word can be the destination (`echo host:/p | xargs scp bin/renet` uploads). In replace mode it appends nothing: each fed word stands wherever the marker is, as a source (`xargs -I{} scp {} host:/p`) or as the destination (`xargs -I{} scp bin/renet {}`), so scp's words are judged with every fed word in the marker's place. With no marker named (plain options, unread options, or a bundle of short ones), the literal and the appended readings are both judged.
            fed = run_.feed.split()
            marker = None if run_.xargs is None else _replace_marker(run_.xargs)
            if marker is None or marker == "":
                # The literal reading is kept beside the appended one: an option this reader took for plain may still be replace mode, and then scp's own last word is the destination.
                readings = [args, args + fed]
            else:
                readings = [[a.replace(marker, word) for a in args] for word in fed]
        if any(_uploads(reading) for reading in readings):
            ev.warn(MESSAGE)
            return hookio.DENY
    return hookio.ALLOW
