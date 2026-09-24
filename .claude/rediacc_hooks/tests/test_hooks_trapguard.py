"""trapguard PostToolUse rules: they INJECT rather than block.

The product is stdout, not the exit code. A rule that exits 0 silently and a rule that exits 0 having warned are indistinguishable without asserting on the text, so every case here is `fires` or `silent` plus, where the message is the point, the needle the message must carry.
"""

import os
import re
import subprocess

import pytest

from rediacc_hooks.tests import hookblocks, hookcases

TRAPGUARD = hookcases.HOOKS / "trapguard" / "dispatch.py"
inject_json = hookcases.inject_json
inject_killed = hookcases.inject_killed


def run_inject(payload: str) -> str:
    done = subprocess.run(
        ["python3", str(TRAPGUARD), "--posttool"],
        input=payload.encode(),
        capture_output=True,
        timeout=hookcases.GUARD_TIMEOUT_S,
        check=False,
    )
    return done.stdout.decode("utf-8", "replace")


def inject(spec: tuple[str, str], payload: str, label: str) -> tuple:
    """One trapguard case.

    THE SPEC AND ITS NEEDLE ARE ONE TUPLE, and that is not a style choice. `trap_registry.Registry.inject_cases` reads a `check_inject <fires|silent>` call by taking the LAST quoted argument ON THAT LINE as the needle (`.ci/rediacc_ci/quality/trap_registry.py:414`, the awk `match(line, /"[^"]*"[^"]*$/)` it ports), and `hook_is_live` then asks whether that needle appears in the
    trapguard rule's own source. Spread the needle onto a fourth line and the reader picks up the SPEC as the needle, finds it in no rule body, and every `enforced_by: hook:<rule>` pointer in TRAPS.md reads as one-sided coverage.

    Passing them as two ARGUMENTS is not enough: `ruff format` explodes a call with a magic trailing comma one argument per line, which separated them and turned all five rules one-sided. A tuple is one argument, so it stays on one line whatever the formatter decides about the call around it. A silent case passes "" -- the reader never uses a silent case's needle.
    """
    text, needle = spec
    verb, _, want = text.partition(" ")
    if verb != "check_inject" or want not in ("fires", "silent"):
        raise ValueError("spec must read 'check_inject <fires|silent>': %r" % text)
    return (want, payload, label, needle or None)


def assert_inject(block, want: str, payload: str, label: str, needle: str | None) -> None:
    said = run_inject(payload)
    got = "fires" if said else "silent"
    ok = got == want and (needle is None or needle in said)
    block.note(want, label, ok=ok, detail="got %s" % got)


# THE PHANTOM PROBE's name, planted at runtime by the _phantom fixture below. The rule keys on a path that is UNTRACKED and PRESENT, which is the state a plumbing-built branch leaves files in, and only the filesystem separates a phantom
# from a real deletion. The name carries this process's pid so the case holds in any
# checkout and a crashed earlier run cannot satisfy it.
PHANTOM_NAME = "tg_phantom_probe_%d.txt" % os.getpid()
CASES = [
    inject(
        ("check_inject fires", "cancelled-run-not-passed"),
        inject_json(
            "gh run view 1 --json jobs", '{"conclusion":"cancelled","name":"Quality / Static"}'
        ),
        "trapguard: a cancelled run gets a warning",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json(
            "gh run view 1 --json jobs", '{"conclusion":"success","name":"Quality / Static"}'
        ),
        "trapguard CONTROL: an all-success run is NOT warned about",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json("gh run view 1 --json jobs", ""),
        "trapguard CONTROL: an empty response does not fire (absence is not a cancellation)",
    ),
    # THE SHAPE THAT WAS DEAD CODE until review of PR #567. A failure-filtered query returning [] contains no word "cancelled" by construction, because the filter removed the cancelled job, so gating on that word made this branch unreachable
    # for the only case it existed to catch.
    inject(
        ("check_inject fires", "cancelled-run-not-passed"),
        inject_json('gh run view 1 --jq .jobs[]|select(.conclusion=="failure")', "[]"),
        "trapguard: a failure-filtered query returning EMPTY is warned about",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json("gh run view 1 --json jobs", "[]"),
        "trapguard CONTROL: an empty result from an UNfiltered query is not that shape",
    ),
    # Precision decay, observed LIVE within an hour of the rule shipping: it warned about
    # output reading `cancelled=0`, which is a session performing exactly the check this
    # rule asks for and finding nothing. Counting cancelled jobs must not be punished.
    inject(
        ("check_inject silent", ""),
        inject_json("gh run view 1 --json jobs", "success=44 skipped=39 cancelled=0 failure=1"),
        "trapguard CONTROL: a cancelled COUNT of zero is the good behaviour, not the trap",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json("gh run view 1 --json jobs", '{"cancelled": 0, "failure": 1}'),
        "trapguard CONTROL: the JSON zero-count shape is silent too",
    ),
    inject(
        ("check_inject fires", "cancelled-run-not-passed"),
        inject_json("gh run view 1 --json jobs", "success=40 cancelled=3 failure=1"),
        "trapguard: a NON-zero cancelled count still fires",
    ),
    # The one that matters: a zero count must not MASK a real cancellation beside it.
    inject(
        ("check_inject fires", "cancelled-run-not-passed"),
        inject_json(
            "gh run view 1 --json jobs", 'cancelled=0\n{"conclusion":"cancelled","name":"Quality"}'
        ),
        "trapguard: a zero count does not mask a real cancelled conclusion",
    ),
    inject(
        ("check_inject fires", "phantom-deletion-diff"),
        inject_json(
            "git diff somebranch -- " + PHANTOM_NAME,
            " %s | 462 ------\n 1 file changed, 462 deletions(-)" % PHANTOM_NAME,
        ),
        "trapguard: all-deletions diff for an UNTRACKED file still on disk is warned about",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json(
            "git diff somebranch -- gone/never-existed.sh",
            " gone/never-existed.sh | 462 ------\n 1 file changed, 462 deletions(-)",
        ),
        "trapguard CONTROL: the SAME output for an absent path stays silent",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json(
            "git diff somebranch",
            " .claude/hooks/test-hooks.sh | 20 +++---\n"
            " 1 file changed, 12 insertions(+), 8 deletions(-)",
        ),
        "trapguard CONTROL: a normal mixed diff stays silent",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json(
            "git diff --cached somebranch",
            " .claude/hooks/test-hooks.sh | 462 ------\n 1 file changed, 462 deletions(-)",
        ),
        "trapguard CONTROL: --cached is exempt (the index IS the subject there)",
    ),
    # THE FALSE POSITIVE THIS RULE SHIPPED WITH, for one hour. A TRACKED file that simply lost lines is a normal diff, and the first version fired on it because it keyed on "the file exists". Existence narrows; tracked-ness decides.
    inject(
        ("check_inject silent", ""),
        inject_json(
            "git diff --stat package-lock.json",
            " package-lock.json | 27 -------\n 1 file changed, 27 deletions(-)",
        ),
        "trapguard CONTROL: a TRACKED file losing lines is an ordinary diff, not a phantom",
    ),
    inject(
        ("check_inject fires", "interrupted-cleanup-skipped"),
        inject_killed(
            "python3 -c mutate; bash suite.sh; cp /tmp/worklist.py.orig .claude/hooks/stop/worklist.py",
            "mutated: guard neutered",
            True,
        ),
        "trapguard: an interrupted command whose tail was a restore is warned about",
    ),
    # The two conditions are INDEPENDENT alternatives, not one gated behind the other, which is the exact defect review found in the sibling rule: the harness reports a kill through `interrupted` on some paths and the timeout text on others, so either alone must be enough.
    inject(
        ("check_inject fires", "interrupted-cleanup-skipped"),
        inject_killed(
            "mutate.sh; bash suite.sh; git checkout -- src/x.py",
            "Command timed out after 2m 0s",
            False,
        ),
        "trapguard: the timeout TEXT alone fires without the interrupted flag",
    ),
    inject(
        ("check_inject fires", "interrupted-cleanup-skipped"),
        inject_killed("mutate.sh; bash suite.sh; cp x.orig x", "", True),
        "trapguard: the interrupted FLAG alone fires without the timeout text",
    ),
    inject(
        ("check_inject silent", ""),
        inject_killed("mutate.sh; bash suite.sh; cp /tmp/x.orig src/x.py", "all done", False),
        "trapguard CONTROL: the same command completing is not warned about",
    ),
    # A restore that IS the command has no earlier step it could have stranded.
    inject(
        ("check_inject silent", ""),
        inject_killed("git restore src/x.py", "", True),
        "trapguard CONTROL: a bare restore with no preceding step stays silent",
    ),
    inject(
        ("check_inject silent", ""),
        inject_killed("npm test; echo done", "Command timed out after 2m 0s", True),
        "trapguard CONTROL: interrupted with nothing to put back stays silent",
    ),
    # history-rewrite-controls. The FIRES/CONTROL pair below differs by exactly one path segment, which is the whole point: the wider prefix is what deleted a live .gitkeep while removing 0.00 MB of history, and the narrower one is the correct command. A rule that cannot tell those two apart would not have caught it.
    inject(
        ("check_inject fires", "user-guide/.gitkeep"),
        inject_json(
            "git -C /tmp/m.git filter-repo --force --path packages/www/public/assets/videos --invert-paths",
            "",
        ),
        "trapguard: an --invert-paths prefix with a LIVE tracked file under it fires",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json(
            "git -C /tmp/m.git filter-repo --force --path packages/www/public/assets/videos/solutions --invert-paths",
            "",
        ),
        "trapguard CONTROL: the SAME command one segment narrower (0 tracked) stays silent",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json(
            "git -C /tmp/m.git filter-repo --force --path packages/www/public/media --invert-paths",
            "",
        ),
        "trapguard CONTROL: an --invert-paths prefix with nothing tracked under it stays silent",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json(
            "git -C /tmp/m.git filter-repo --force --path packages/www/public/assets/tutorials/audio --invert-paths",
            "",
        ),
        "trapguard CONTROL: the untracked audio cache prefix stays silent too",
    ),
    # The two arms are INDEPENDENT, not nested. This one is silent on arm 1 (nothing tracked under the path) and must still fire on arm 2.
    inject(
        ("check_inject fires", "history-rewrite-no-baseline"),
        inject_json(
            "git -C /tmp/m.git filter-repo --force --path packages/www/public/media --invert-paths --message-callback /tmp/strip-ai.py",
            "",
        ),
        "trapguard: a message-callback fires on arm 2 even when arm 1 has nothing to say",
    ),
    # A heredoc BODY is written, not run. Prose describing the rewrite hazard fed the matcher its own trigger words and produced a warning about a rewrite that never happened; the second control proves the stripper eats the body ONLY, so a real command sharing the line-set with a heredoc still fires.
    inject(
        ("check_inject silent", ""),
        inject_json(
            "cat > notes.md <<'MD'\nnever run git filter-repo --message-callback here\nMD", ""
        ),
        "trapguard CONTROL: a rewrite named inside a heredoc BODY is prose, not a run",
    ),
    inject(
        ("check_inject fires", "history-rewrite-no-baseline"),
        inject_json(
            "cat > notes.md <<'MD'\n"
            "prose\n"
            "MD\n"
            "git filter-repo --force --message-callback /tmp/strip.py",
            "",
        ),
        "trapguard: a real rewrite AFTER a heredoc still fires",
    ),
    # THE JUST-IN-TIME HINT. The operator asked, 2026-08-26: "you had known how and when to use verify-rebase because you built it -- is there any hint?" There was none: `worklist.py --git` was referenced by ZERO commands, agents and docs, so the capability existed and the affordance did not. trapguard is the right surface because it never blocks and already exists to say "you just
    # did X".
    #
    # BOTH SIGNALS REQUIRED -- a rebase COMMAND and real rebase OUTPUT -- so a no-op rebase stays quiet and a mention cannot trigger it.
    inject(
        ("check_inject fires", "rebase-unverified"),
        inject_json(
            "git rebase origin/0826-2",
            "Rebasing (1/18)Successfully rebased and updated refs/heads/0826-3.",
        ),
        "trapguard: a completed rebase points at verify-rebase",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json("git rebase origin/main", "Current branch 0826-3 is up to date."),
        "trapguard CONTROL: a no-op rebase has nothing to verify",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json('echo "run git rebase later"', "Successfully rebased and updated refs/heads/x"),
        "trapguard CONTROL: a rebase named in a string is not a rebase",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json("git filter-repo --analyze", "Processed 6177 commits"),
        "trapguard CONTROL: --analyze is a READ of history and is never warned about",
    ),
    # bws-auth-failure. ONE CASE PER MEASURED STRING, because the strings are the whole evidence base: they were taken 2026-09-06 against bws 2.1.0 with deliberately bogus tokens, and the string a genuinely EXPIRED token prints has never been seen here. The default-on arm is what covers that unseen one, so it gets a case of its own with a string nobody has ever measured.
    inject(
        ("check_inject fires", "bws-auth-failure"),
        inject_json("bws secret list", 'Error: [400 Bad Request] {"error":"invalid_client"}'),
        "trapguard: a bws invalid_client failure points at the rotation procedure",
    ),
    inject(
        ("check_inject fires", "bws-auth-failure"),
        inject_json("bws secret list --output json", "Error: Doesn't contain a decryption key"),
        "trapguard: a garbled token's decryption-key error fires too",
    ),
    inject(
        ("check_inject fires", "scripts/dev/bws-rotate.py"),
        inject_json("bws secret get abc", "error: the access token could not be validated"),
        "trapguard: an UNMEASURED auth error still fires, because the default is on",
    ),
    # THE ONE BRANCH THAT MUST STAY SILENT, and the reason it is not a taste question: `Missing access token` means the variable is unset. Nothing expired, and a rotation fixes nothing. A rule written as "fire on any bws error" gets exactly this case wrong.
    inject(
        ("check_inject silent", ""),
        inject_json("bws secret list", "Error: Missing access token"),
        "trapguard CONTROL: an UNSET variable is wiring, not a rotation, and says nothing",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json("bws secret list --color no", '[{"key":"ALPHA","value":"x"}]'),
        "trapguard CONTROL: a bws listing that WORKED is never warned about",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json('echo "run bws secret list later"', "Error: Missing token, invalid_client"),
        "trapguard CONTROL: bws named inside a string is not a bws run",
    ),
    # The two scripts whose names START with `bws` print the notice from their own failure paths. Firing here would double every message they already emit, which is the precision decay this tier's other rules were retuned for.
    inject(
        ("check_inject silent", ""),
        inject_json(
            "scripts/ops/bws-map-refresh.py --dry-run",
            'bws secret list exited 1: [400 Bad Request] {"error":"invalid_client"}',
        ),
        "trapguard CONTROL: a script whose NAME begins with bws is not the bws binary",
    ),
    # 2026-09-24, both live false positives. A usage error never reached Bitwarden; `bws` inside a quoted grep pattern after a `|` is not a pipe into bws.
    inject(
        ("check_inject silent", ""),
        inject_json('bws secret create FULL_CI "" proj', "error: value must not be empty\n\nFor more information, try '--help'."),
        "trapguard CONTROL: a bws usage error is not an auth failure",
    ),
    inject(
        ("check_inject silent", ""),
        inject_json('gh run view 1 --log-failed | grep -iE "error|bws|token"', "error: the access token could not be validated"),
        "trapguard CONTROL: bws after a | INSIDE a quoted pattern is not a bws run",
    ),
    # The pair that proves neither fix went too far: a real auth string still fires beside usage-shaped noise, and a real pipe into bws still counts.
    inject(
        ("check_inject fires", "bws-auth-failure"),
        inject_json("bws secret list", 'Error: [400 Bad Request] {"error":"invalid_client"}\nFor more information, try \'--help\'.'),
        "trapguard: a rotation marker still fires even beside usage-shaped text",
    ),
    inject(
        ("check_inject fires", "bws-auth-failure"),
        inject_json('echo x | bws secret list', "error: the access token could not be validated"),
        "trapguard: a real pipe into bws still counts as a bws run",
    ),
]


@pytest.fixture(scope="module")
def _phantom():
    """The untracked-but-present file the phantom case needs, removed afterwards."""
    path = hookcases.ROOT / PHANTOM_NAME
    path.write_text("x\n", encoding="utf-8")
    yield path
    path.unlink(missing_ok=True)


@pytest.mark.xdist_group("hooks-trapguard")
@pytest.mark.usefixtures("_phantom")
def test_every_trapguard_rule_fires_and_stays_silent_where_it_should():
    block = hookblocks.Block("trapguard")
    for want, payload, label, needle in CASES:
        assert_inject(block, want, payload, label, needle)
    block.done()


# --- `--git rebase-status` against a REAL halted rebase, one per conflict kind ---- The selftest's classifier controls prove the ARITHMETIC over hand-written stage tables; only a real halt proves the verb reads what git actually writes into .git/rebase-merge and the index. The harness refuses to hand back a fixture that did not halt, which already caught a broken fixture of its
# own: the two submodule commits were linear, so git took the descendant and nothing conflicted.
GIT_FIXTURE = hookcases.ROOT / ".ci" / "scripts" / "test" / "lib" / "git-fixture.sh"
WORKLIST = hookcases.HOOKS / "stop" / "worklist.py"


def _fixture_rebase(kind: str) -> str:
    """The fixture's own directory, or "" when it did not halt. Same bytes as the suite ran: the library is bash, so it is sourced rather than transcribed."""
    done = subprocess.run(
        ["bash", "-c", 'source "$1"; git_fixture_rebase "$2"', "--", str(GIT_FIXTURE), kind],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=600,
        check=False,
    )
    return done.stdout.decode().strip() if done.returncode == 0 else ""


def _fixture_cleanup(directory: str) -> None:
    subprocess.run(
        ["bash", "-c", 'source "$1"; git_fixture_cleanup "$2"', "--", str(GIT_FIXTURE), directory],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
        check=False,
    )


def _worklist_git(directory: str, *args: str) -> str:
    done = subprocess.run(
        ["python3", str(WORKLIST), "--git", *args],
        cwd=directory,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=600,
        check=False,
    )
    return (done.stdout + done.stderr).decode("utf-8", "replace")


def _unmerged(directory: str) -> int:
    done = subprocess.run(
        ["git", "ls-files", "-u"],
        cwd=directory,
        capture_output=True,
        check=False,
        timeout=120,
    )
    return len([line for line in done.stdout.decode().splitlines() if line.strip()])


@pytest.mark.xdist_group("hooks-trapguard")
@pytest.mark.parametrize("kind", ["registry", "judgement", "gitlink"])
def test_rebase_status_reads_a_real_halt(kind):
    block = hookblocks.Block("rebase-status/" + kind)
    directory = _fixture_rebase(kind)
    assert directory, "git-fixture: '%s' did not halt" % kind
    try:
        said = _worklist_git(directory, "rebase-status")
        ok = "rebase HALTED" in said and re.search(r"-> %s\b" % re.escape(kind), said) is not None
        block.note(
            0,
            "rebase-status reads a real %s halt and classifies it" % kind,
            ok=ok,
            detail=said[:200],
        )
    finally:
        _fixture_cleanup(directory)
    block.done()


# STEP 3: resolve-gitlinks may now WRITE, and these are the two halves that make that safe. The happy path resolves a real halt end to end; the guard refuses a MIXED conflict set rather than half-resolving it, because a half-resolved index reads as nearly done and the next --continue then fails for a reason that no longer names the submodule.
@pytest.mark.xdist_group("hooks-trapguard")
def test_resolve_gitlinks_clears_a_real_gitlink_halt():
    block = hookblocks.Block("resolve-gitlinks/happy")
    directory = _fixture_rebase("gitlink-rebased")
    assert directory, "git-fixture: gitlink-rebased did not halt"
    try:
        said = _worklist_git(directory, "resolve-gitlinks", "--execute")
        left = _unmerged(directory)
        block.note(
            0,
            "resolve-gitlinks --execute clears a real gitlink halt",
            ok="command(s) ran" in said and left == 0,
            detail="left %d unmerged: %s" % (left, said[:160]),
        )
    finally:
        _fixture_cleanup(directory)
    block.done()


@pytest.mark.xdist_group("hooks-trapguard")
def test_resolve_gitlinks_refuses_a_mixed_conflict_set():
    block = hookblocks.Block("resolve-gitlinks/mixed")
    directory = _fixture_rebase("mixed")
    assert directory, "git-fixture: mixed did not halt"
    try:
        before = _unmerged(directory)
        said = _worklist_git(directory, "resolve-gitlinks", "--execute")
        after = _unmerged(directory)
        block.note(
            2,
            "resolve-gitlinks refuses a MIXED set and changes nothing",
            ok="non-gitlink conflict" in said and before == after,
            detail="%d -> %d unmerged: %s" % (before, after, said[:160]),
        )
    finally:
        _fixture_cleanup(directory)
    block.done()
