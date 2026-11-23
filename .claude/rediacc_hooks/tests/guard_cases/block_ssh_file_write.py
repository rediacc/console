"""The test tables of `block_ssh_file_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

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
    # Rule T, A0 L13: the redirect ssh CARRIES is the remote write, and the quote strip used to delete it.
    ("a quoted remote redirect is a remote write", "ssh prod-1 'cat > /etc/x' < f"),
    ("a double-quoted remote echo redirect is a remote write", 'ssh prod-1 "echo hi > /etc/x"'),
    ("a remote tee with a file operand is a remote write", "ssh -p 22 prod-1 tee /etc/x < f"),
    ("a remote noclobber-proof redirect is a remote write", "ssh prod-1 'printf x >| /etc/x'"),
    # ... and the controls: remote plumbing, a quoted mention, and the bridge VM.
    ("remote stderr plumbing is not a write", "ssh prod-1 'journalctl -u x 2>&1 >/dev/null'"),
    ("a quoted mention of a remote write is prose", "echo \"ssh prod-1 'cat > /etc/x'\""),
    ("the bridge VM may take a quoted remote write", "ssh 192.168.111.10 'cat > /etc/x' < f"),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    (
        "an ssh remote write launched by find -exec",
        r"find . -maxdepth 0 -exec ssh prod-1 'cat > /etc/x' \;",
    ),
    ("-P takes a value, so the remote command is the tee", "ssh -P tag prod-1 tee /etc/x < f"),
    ("an option after the destination is ssh's", "ssh prod-1 -t tee /etc/x < f"),
    ("a remote write one hop further in", 'ssh jump "ssh prod-1 tee /etc/x"'),
    ("a ProxyCommand redirect is local", 'ssh prod-1 -o "ProxyCommand=nc %h %p 2>/tmp/err" uptime'),
]
