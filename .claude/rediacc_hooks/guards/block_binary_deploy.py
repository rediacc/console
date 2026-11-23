"""Block manual binary deploys via scp / sudo cp of the renet binary.

DEPLOYING IS UPLOADING. The original pattern was `^scp `, which refuses every scp of every file in either direction -- including the one that is not a deploy at all:

  scp host:/var/log/renet.log ./logs/     <- pulling a log back to diagnose

That is the opposite of deploying a binary, and refusing it pushes the work onto a clumsier path with no benefit. A guard is judged by what it lets through as much as by what it stops, and until 2026-08-27 nothing here asserted this one let anything through.

The direction is decidable: scp's LAST argument is its destination, and a destination naming a remote host (`host:path`, `user@host:path`) is an upload. Anything else is a download.

THE CLAUSE LOOP IS GONE (review a2d44aa4.1). The bash original split the command on `;&|` and read each clause with a here-string loop; its own comment recorded two ways that loop silently allowed every upload. The guard now reads shellscan's runs, so neither the split nor the loop exists, and scp's operands come from the shell's own word splitting instead of the last blank-separated field of a clause.

AN UPLOAD TO A LOCAL OPS VM IS DEV WORK, NOT A DEPLOY (worklist #4e20f8c5, 2026-10-28). Every scp upload used to be refused, so `scp /tmp/ld-k9/chunkstore.test developer@192.168.111.22:/tmp/` (a Go test binary) and `scp Dockerfile compose.yml developer@192.168.111.22:/tmp/` (two text files) were both refused, though neither is the renet binary and the ops VMs (192.168.111.0/24) are dev-only by operator ruling: a guard blocking dev work there is the bug. An upload whose destination host is an ops VM is now allowed UNLESS a source has a renet name (`INSTALLED_NAME` on its basename), a recursive (`-r`) source is a directory holding one, the destination path lands in the install directory or has a renet name, or any source or the destination is resolved only at run time (a variable, a substitution, a glob, a brace list), which stays judged strictly. Every other host is refused exactly as before.
"""

import os
import re

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import _cases

__getattr__ = _cases.lazy("block_binary_deploy", "EDGE_CASES")

CHAIN = "pre-bash"
ORDER = 7

# Dropping the host-spec test restores the `^scp ` behaviour the 2026-08-27 change removed: every scp is a deploy again, downloads included. It is the one line that separates "uploading a binary" from "pulling a log back".
DEFECT = (
    "upload = unread_upload or hookio.grep_q(HOST_SPEC, dest)",
    "upload = True",
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
# The same spec split into its host and path, for the ops-VM test. Its one caller reads it with `fullmatch`, which anchors both ends already; the `^` only keeps the text parallel to HOST_SPEC (review 8959ce94.1).
_HOST_PATH = re.compile(r"^(?:[A-Za-z0-9_.-]+@)?([A-Za-z0-9_.-]+):(.*)", re.DOTALL)
# The local ops VMs, 192.168.111.0/24: dev-only, so an upload there is not a deploy unless it carries renet.
OPS_VM = re.compile(r"192\.168\.111\.(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])")
# A word bash would still expand (a glob or a brace list) names files this reader cannot list, so it is judged strictly. The characters that start one, tested per scp operand word; a set, since no pattern is involved.
_EXPANDS = frozenset("*?[{")


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
        if re.fullmatch(r"-[A-Za-z0-9]*[IJi].*", option):
            return ""
    return None


def _renet_named(path):
    """Whether a path's last component (trailing slashes dropped) is the renet binary or a staged sibling."""
    return bool(INSTALLED_NAME.fullmatch(os.path.basename(path.rstrip("/"))))


def _unreadable(word):
    """A word whose final value is known only at run time: an unresolved expansion, or a glob or brace list bash would still expand."""
    return shellscan.unresolved(word) or any(ch in _EXPANDS for ch in word)


# How many entries a recursive source is walked through before it is judged strictly: `scp -r . vm:/tmp/` from the repository root is not walked to the end.
_WALK_CAP = 5000


def _tree_carries_renet(top):
    """Whether a local directory a recursive scp sends holds a renet-named file, or holds more entries than `_WALK_CAP` (judged as if it did)."""
    seen = 0
    for _dirpath, dirnames, filenames in os.walk(top):
        seen += len(dirnames) + len(filenames)
        if seen > _WALK_CAP or any(_renet_named(name) for name in filenames):
            return True
    return False


def _lands_in_install_dir(path):
    """Whether a remote scp path lands in the install directory. POSIX keeps a leading `//` through `normpath`, so leading slashes are collapsed first (`//usr/local/bin/x`); a relative path that climbs (`../../usr/local/bin`) is relative to a remote home this reader cannot see, so it counts too (review fe6ccbbb.1)."""
    if not path:
        return False
    landed = os.path.normpath(re.sub(r"^/+", "/", path))
    if landed.startswith("~"):
        landed = os.path.normpath(landed.split("/", 1)[1]) if "/" in landed else "."
    if landed == ".." or landed.startswith("../"):
        return True
    return landed == INSTALL_DIR or landed.startswith(INSTALL_DIR + "/")


def _dev_upload(sources, dest, recursive=False, cwd=None):
    """Whether an upload is dev work on a local ops VM: the destination host is one, nothing is read only at run time, no source has a renet name, no recursive source is a directory holding one, and the copy does not land in the install directory or under a renet name (#4e20f8c5)."""
    spec = _HOST_PATH.fullmatch(dest)
    if spec is None or not OPS_VM.fullmatch(spec.group(1)):
        return False
    if _unreadable(dest) or any(_unreadable(src) for src in sources):
        return False
    if any(_renet_named(src) for src in sources):
        return False
    # A recursive copy sends what a directory holds, so `scp -r bin vm:/tmp/` carries bin/renet though no source is named renet (review fe6ccbbb.2). The directory is read on disk; one that is not there sends nothing.
    if recursive:
        for src in sources:
            top = os.path.join(cwd or os.getcwd(), os.path.expanduser(src))
            if os.path.isdir(top) and _tree_carries_renet(top):
                return False
    path = spec.group(2)
    return not (_lands_in_install_dir(path) or _renet_named(path))


def _recursive(args):
    """Whether scp's options carry `-r`, alone or in a bundle (`-rp`), read the way `_scp_operands` reads them."""
    for word in args:
        if word == "--":
            return False
        if word.startswith("-") and len(word) > 1 and not shellscan.unresolved(word):
            for letter in word[1:]:
                if letter == "r":
                    return True
                if letter in SCP_VALUE_LETTERS:
                    break
    return False


def _uploads(args, cwd=None):
    """Whether scp given `args` sends a file to a host, as a deploy: an upload that is not dev work on an ops VM."""
    operands = _scp_operands(args)
    if len(operands) < 2:
        return False
    dest = operands[-1]
    # A destination built at run time (`$(...)`, an unset variable) cannot be read here. It is an upload unless EVERY source names a host, which makes the copy a download into that local path; one local source can still be going up.
    unread_upload = shellscan.unresolved(dest) and not all(
        hookio.grep_q(HOST_SPEC, src) for src in operands[:-1]
    )
    upload = unread_upload or hookio.grep_q(HOST_SPEC, dest)
    return upload and not _dev_upload(operands[:-1], dest, _recursive(args), cwd)


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
        if any(_uploads(reading, cwd) for reading in readings):
            ev.warn(MESSAGE)
            return hookio.DENY
    return hookio.ALLOW
