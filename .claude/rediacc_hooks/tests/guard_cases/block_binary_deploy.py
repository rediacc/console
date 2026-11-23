"""The test tables of `block_binary_deploy`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

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
    # The cost of keeping the literal reading (review 40df44f9.2): this copies into the local word `x`, and is refused because scp's own words name a host destination.
    ("a plain fed xargs with a host among scp's own words", "echo x | xargs scp bin/renet host:/p"),
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
    # #4e20f8c5: an upload to a local ops VM (192.168.111.0/24) is dev work unless it carries renet. Both refusals of 2026-10-28 are allowed; every renet shape and every other host is still refused.
    (
        "a test binary to an ops VM is dev work",
        "scp /tmp/ld-k9/chunkstore.test developer@192.168.111.22:/tmp/",
    ),
    (
        "text files to an ops VM are dev work",
        "scp Dockerfile compose.yml developer@192.168.111.22:/tmp/",
    ),
    ("an ops VM without a user", "scp -P 22 notes.txt 192.168.111.5:"),
    ("bin/renet to an ops VM is a deploy", "scp bin/renet developer@192.168.111.22:/tmp/"),
    ("renet-v2 to an ops VM is a deploy", "scp /tmp/renet-v2 192.168.111.22:/tmp/"),
    ("a renet among other files to an ops VM", "scp a.txt bin/renet 192.168.111.22:/tmp/"),
    ("any file into the install dir of an ops VM", "scp x.bin 192.168.111.22:/usr/local/bin/"),
    ("any file renamed renet on an ops VM", "scp x.bin 192.168.111.22:/tmp/renet"),
    # Review fe6ccbbb.1: `normpath` keeps a leading `//`, and a climbing relative path is read from a home this reader cannot see.
    (
        "a double-slash install dir on an ops VM",
        "scp x.bin developer@192.168.111.22://usr/local/bin/tool",
    ),
    (
        "a file under the install dir on an ops VM",
        "scp x.bin 192.168.111.22:/usr/local/bin/sub/tool",
    ),
    ("a climbing path to an ops VM", "scp x.bin 192.168.111.22:../../usr/local/bin/tool"),
    ("a climbing home path to an ops VM", "scp x.bin 192.168.111.22:~/../../usr/local/bin/tool"),
    ("a plain relative path to an ops VM is dev work", "scp x.bin 192.168.111.22:work/x.bin"),
    ("any file to a non-ops host", "scp Dockerfile developer@10.0.0.5:/tmp/"),
    ("a near-miss address is not an ops VM", "scp Dockerfile 192.168.1110.2:/tmp/"),
    ("a run-time source to an ops VM", "scp $BIN 192.168.111.22:/tmp/"),
    ("a glob source to an ops VM", "scp bin/* 192.168.111.22:/tmp/"),
    ("a run-time destination with an ops VM elsewhere", "scp x 192.168.111.22:/a $(cat d)"),
    (
        "a test binary to an ops VM through xargs",
        "echo /tmp/k.test | xargs -I{} scp {} 192.168.111.22:/tmp/",
    ),
    ("renet to an ops VM through xargs", "echo bin/renet | xargs -I{} scp {} 192.168.111.22:/tmp/"),
]
