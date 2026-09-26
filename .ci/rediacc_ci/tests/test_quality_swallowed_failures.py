"""`rediacc_ci.quality.swallowed_failures` against the awk scanner it replaces.

WHY A DIFFERENTIAL. This gate is one 150-line awk program with four rules, a two-pass line folder and a 12-line lookahead window, and its own history is a version that died on all 42 files while printing "OK: no gate captures a probe...". Comparing the port against the real awk on the same input is the only form of this test that can fail for the right reason.

The whole gate is covered by `.ci/shadow/w7p2-swallowed-failures.observations.jsonl` over five distinct trees.
"""

import pathlib
import subprocess

import pytest

from rediacc_ci.quality import swallowed_failures as mod

# THE AWK PROGRAM IS A FROZEN LITERAL NOW, AND THE DIFFERENTIAL IS STILL LIVE.
# It used to be sliced out of `.ci/scripts/quality/check-swallowed-failures.sh` at run time. That twin was retired in W7P5-c, blob `e7b12ba15c41569a88ea8065007e246ab948f2ee`, once `.ci/shadow/w7p2-swallowed-failures.observations.jsonl` held K=5 -- 10 rows, 10 distinct tree ids, 4 distinct fingerprints, every verdict `EQUIVALENT`.
#
# WHAT DID *NOT* CHANGE, and it is the point of freezing it this way rather than freezing the OUTPUTS: every case below still pipes real input through this real awk with a real `awk` binary and compares the port against what it prints. The subject of the comparison is unchanged; only its storage moved from a file on disk into this string.
# Freezing the verdicts instead would have turned a differential into an assertion about remembered text, which is the one thing a differential exists not to be.
#
# WHAT THIS COSTS, said out loud: the old arrangement broke LOUDLY the day someone edited the twin's scanner, which was exactly when it should be re-read. There is no twin to edit any more, so that alarm has no source left. The port is the only implementation, and this literal is the record of what it was proven against.
AWK_PROGRAM = r"""
    BEGIN {
        n = 0; buf = ""; pending_waiver = ""
        # A capture: optional local/export/readonly, then NAME=$( or NAME="$(.
        # The optional quote is load-bearing: `tree_all="$(npm ls ... || true)"`
        # is the commonest spelling in this repo, and omitting it hid every
        # quoted capture, including the dependency-inventory specimens.
        capture_re = "(^|[ \t]|\\()(local[ \t]+|export[ \t]+|readonly[ \t]+)?[A-Za-z_][A-Za-z0-9_]*=[\"\\047]?[$]\\("
        # A status-discarding fallback whose value cannot be told from a
        # legitimate empty result.
        swallow_re = "\\|\\|[ \t]*(true|:|echo[ \t]*\\)|echo[ \t]+\"\"|echo[ \t]+0[ \t]*\\)|echo[ \t]+\"0\"|echo[ \t]+.\\[\\].|echo[ \t]+.\\{\\}.|printf[ \t]+..[ \t]*\\))"
        # Commands whose non-zero exit is a routine answer rather than an error.
        answer_re = "(^|[ \t]|\\(|\\|)(grep|egrep|fgrep|rg|command -v|type -|which|hash|diff|cmp)[ \t]"
        # Tokens meaning the empty case was reported rather than passed over.
        escalate_re = "(log_error|log_warn|log_fail|ci_error|ci_warn|die[ \t]|exit[ \t]+[1-9]|return[ \t]+[1-9]|FAIL|ERROR|::error|::warning|PROBE_FAILED)"
        # Tokens meaning the empty case ended the script successfully.
        pass_re = "(exit[ \t]+0|return[ \t]+0)"
        # How many logical lines after the capture count as downstream.
        window = 12
    }

    # --- pass 1: fold physical lines into logical ones -------------------
    {
        line = $0
        sub(/^[[:space:]]+/, "", line)
        sub(/[[:space:]]+$/, "", line)

        if (buf == "") {
            if (line ~ /^#[[:space:]]*swallowed-failure-ok:/) {
                pending_waiver = line
                next
            }
            # Any other comment or a blank line clears a dangling waiver: a
            # waiver must sit immediately above the line it excuses, or it
            # drifts and starts excusing something nobody read.
            if (line == "" || line ~ /^#/) { pending_waiver = ""; next }
            start = FNR
            buf = line
        } else {
            buf = buf " " line
        }

        tmp = buf
        o = gsub(/\(/, "(", tmp)
        c = gsub(/\)/, ")", tmp)
        if (o > c) next
        if (buf ~ /(\||&&|\\)$/) next

        n++
        LL[n] = buf
        LN[n] = start
        WV[n] = pending_waiver
        pending_waiver = ""
        buf = ""
    }

    # --- pass 2: apply the rules ----------------------------------------
    END {
        # An unterminated buffer (unbalanced parens through EOF) still has to
        # be seen; dropping it would let a defect hide behind a stray paren.
        if (buf != "") { n++; LL[n] = buf; LN[n] = start; WV[n] = pending_waiver }

        for (i = 1; i <= n; i++) {
            s = LL[i]
            if (s !~ capture_re) continue
            if (s !~ swallow_re) continue
            if (s ~ /2>&1/) continue
            if (s ~ answer_re) continue

            var = capture_var(s)
            if (var == "") continue

            if (WV[i] != "") { printf "WAIVER\t%s\t%d\t%s\t%s\n", file, LN[i], var, WV[i]; continue }

            verdict = classify(i, var)
            if (verdict != "") {
                printf "FINDING\t%s\t%d\t%s\t%s\t%s\n", file, LN[i], var, verdict, s
            }
        }
    }

    # Name of the variable being assigned in a capture.
    function capture_var(s,   t) {
        t = s
        sub(/=["\047]?[$]\(.*$/, "", t)
        sub(/^.*[[:space:](]/, "", t)
        sub(/^(local|export|readonly)$/, "", t)
        if (t !~ /^[A-Za-z_][A-Za-z0-9_]*$/) return ""
        return t
    }

    # "" when the empty case is distinguished downstream; otherwise the reason.
    #
    # The test pattern is built per variable rather than templated once: an
    # emptiness test on some OTHER variable says nothing about this one, and
    # that distinction is what keeps the pre-fix check-go-deps probe flagged
    # (its loop tests $path, never $outdated).
    function classify(i, var,   j, tre, limit, branch) {
        # Four shapes count as "the author looked at the empty case":
        #   [[ -z/-n $VAR ]]        emptiness test
        #   [[ $VAR -eq/==/=~ ... ]]  value test, including the =~ normalisers
        #                             that lib/common.sh and the release-state
        #                             validator use
        #   (( VAR ... ))           arithmetic test
        #   jq -e / jq empty <<<$VAR  validity test, which is how
        #                             dependency-inventory checks its npm trees
        tre = "(\\[\\[?[^]]*(-z|-n)[ \t]+.?[$]\\{?" var \
            "|\\[\\[?[^]]*[$]\\{?" var "[^]]*(-eq|-gt|-lt|==|!=|=~)" \
            "|\\(\\([^)]*" var \
            "|jq[ \t]+(-e|empty)[^|]*[$]\\{?" var ")"
        limit = i + window
        if (limit > n) limit = n
        for (j = i + 1; j <= limit; j++) {
            # A capture is only answered for within its own function. Letting
            # the window run past the closing brace made a log_error in the
            # NEXT function count as handling for this one, which silently
            # cleared r2_count_objects in lib/common.sh: a genuine finding, and
            # the one the sibling gate recommends as a remedy.
            if (is_boundary(LL[j])) { limit = j - 1; break }
            if (LL[j] !~ tre) continue
            branch = branch_of(j)
            if (branch ~ escalate_re) return ""
            if (branch ~ pass_re) return "the empty case exits successfully"
            # A test with neither an escalation nor an exit in its own branch:
            # accept it if the surrounding window reports the problem at all.
            if (window_has_escalation(i, limit)) return ""
            return "nothing reports the empty case"
        }
        return "no test distinguishes a failed probe from an empty result"
    }

    # The body governed by the test on logical line j: for an `if`, everything
    # up to the matching else/elif/fi; for a one-line && or || form, the rest of
    # that same line.
    function branch_of(j,   depth, k, body, opened, closed) {
        if (LL[j] !~ /(^|[[:space:]])if[[:space:]]/ && LL[j] !~ /;[[:space:]]*then/) {
            return LL[j]
        }
        body = LL[j]
        depth = 0
        for (k = j; k <= n; k++) {
            opened = (LL[k] ~ /(^|[[:space:]])if[[:space:]]/)
            closed = (LL[k] ~ /(^|[[:space:]])fi([[:space:]]|;|$)/)
            if (opened) depth++
            if (closed) depth--
            if (k > j) body = body " " LL[k]
            # `k > j` alone misses the ONE-LINE `if ...; then ...; fi` shape: it
            # opens and closes depth in the SAME iteration (k == j), so the guard
            # never fires there, and the loop absorbs the NEXT, unrelated line
            # into body before its k > j check finally sees depth <= 0.
            # `opened && closed` catches exactly that same-line close.
            if (depth <= 0 && (k > j || (opened && closed))) break
            if (depth == 1 && k > j && LL[k] ~ /^(else|elif)([[:space:]]|$)/) break
        }
        return body
    }

    function window_has_escalation(i, limit,   j) {
        for (j = i + 1; j <= limit; j++) {
            if (is_boundary(LL[j])) return 0
            if (LL[j] ~ escalate_re) return 1
        }
        return 0
    }

    # End of the enclosing function, or the start of the next one.
    function is_boundary(s) {
        if (s ~ /^\}/) return 1
        if (s ~ /^[A-Za-z_][A-Za-z0-9_]*\(\)[ \t]*\{/) return 1
        if (s ~ /^function[ \t]/) return 1
        return 0
    }"""


def _awk_program() -> str:
    """The `awk -v file="$1" '<program>'` body, as text."""
    return AWK_PROGRAM


# Every shape the scanner has to get right. The comment names the property.
BODIES = [
    (
        'outdated=$(go list -u -m -json all 2>/dev/null |\n    jq -rs "." 2>/dev/null || true)\n'
        'while IFS=" " read -r path current latest uptime; do :; done <<<"$outdated"\n'
    ),
    "rm -rf /tmp/x || true\n",  # a bare cleanup is not a capture
    'tree_all="$(npm ls --all || true)"\n',  # the quoted capture spelling
    "v=$(probe || :)\n",
    "v=$(probe || echo)\n",
    'v=$(probe || echo "")\n',
    'v=$(probe || echo "[]")\n',
    "v=$(probe || echo unavailable)\n",  # a real sentinel
    "v=$(probe || echo 000)\n",  # also a sentinel
    "v=$(probe)\n",  # no fallback
    "v=$(probe 2>&1 || true)\n",  # stderr folded in
    "v=$(grep -q x f || true)\n",  # an answer command
    "v=$(command -v jq || true)\n",
    "v=$(diff a b || true)\n",
    'v=$(probe || true)\nif [[ -z "$v" ]]; then\nlog_error "probe failed"\nfi\n',
    'v=$(probe || true)\nif [[ -z "$v" ]]; then\nexit 0\nfi\n',
    "v=$(probe || true)\necho done\n",
    'v=$(probe || true)\nif [[ -z "$other" ]]; then\nlog_error x\nfi\n',
    'v=$(probe || true)\nif ((v > 0)); then\nlog_error "bad"\nfi\n',
    'v=$(probe || true)\nif jq -e . <<<"$v"; then\nlog_error x\nfi\n',
    'f() {\nv=$(probe || true)\n}\ng() {\nlog_error "unrelated"\n}\n',
    (
        "# swallowed-failure-ok: a long enough reason to clear the blocker bar here\n"
        "v=$(probe || true)\n"
    ),
    "# swallowed-failure-ok: reason\n# an intervening comment\nv=$(probe || true)\n",
    "v=$(probe || true\n",  # an unterminated buffer through EOF
    "local v=$(probe || true)\necho x\n",
    "export V=$(probe || true)\necho x\n",
    "",  # empty file
]


@pytest.mark.parametrize("body", BODIES)
def test_scanner_matches_the_twins_awk(tmp_path: pathlib.Path, body: str) -> None:
    target = tmp_path / "subject.sh"
    target.write_text(body, encoding="utf-8")
    proc = subprocess.run(
        ["awk", "-v", "file=%s" % target, _awk_program(), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == "", "a warning means the program running is not the one written"

    expected = []
    for line in proc.stdout.split("\n"):
        if line == "":
            continue
        fields = line.split("\t")
        expected.append((fields[0], fields[2], fields[3]))

    got = [(row.kind, str(row.line), row.var) for row in mod.scan_text(body, str(target))]
    assert got == expected


def test_the_blocker_bar_on_waiver_reasons() -> None:
    """A waiver reopens the hole this gate closes, so it meets the BLOCKER bar."""
    assert validate("the empty case genuinely means the same thing here") is True
    assert validate("todo") is False
    assert validate("it is fine really") is False
    assert validate("not needed by this change and we can revisit it later on") is False


def validate(reason: str) -> bool:
    return mod.validate_blocker_quality("x", reason, "f")


def test_an_empty_corpus_is_refused(tmp_path: pathlib.Path, monkeypatch) -> None:
    """A scan over nothing is the exact failure mode this gate polices."""
    monkeypatch.setenv(mod.ROOT_ENV, str(tmp_path))
    monkeypatch.setenv(mod.DIRS_ENV, "nowhere")
    assert mod.main([]) == 1


# ---------------------------------------------------------------------------
# the one-liner `if ...; then ...; fi` absorption bug (89b2e140)
# ---------------------------------------------------------------------------
#
# AN ABSOLUTE ASSERTION, NOT A DIFFERENTIAL ONE, and that distinction is the whole reason this test exists. `branch_of()` used to end a branch only on
# `depth <= 0 and k > j`, which never fires on the line a one-liner OPENS and
# CLOSES depth in the same step (k == j). The loop therefore absorbed the NEXT,
# unrelated logical line into the branch it reported.
#
# `test_scanner_matches_the_twins_awk` above could not have caught this and still cannot: it compares the port against the awk twin, and BOTH TWINS WERE WRONG IDENTICALLY, so parity stayed green through the entire lifetime of the bug. The shadow ledger is blind to it for the same reason. A parity check cannot see a defect that is uniformly wrong -- only an absolute claim about the
# answer can, which is what this is.
def test_a_one_liner_if_does_not_absorb_the_following_line() -> None:
    """The branch of a same-line `if ...; then ...; fi` ends ON that line."""
    text = 'if [[ -z "$v" ]]; then :; fi\nlog_error "unrelated to the if above"\n'
    lines = mod.fold(text)
    branch = mod.branch_of(lines, 0)
    assert "unrelated to the if above" not in branch, (
        "branch_of absorbed the line AFTER a one-liner if; that is the 89b2e140 "
        "bug, and it misattributes an escalation to a branch that does not have one"
    )
    assert "log_error" not in branch


# WHAT THIS TEST DELIBERATELY DOES NOT CLAIM. I tried to add a second case asserting the bug flipped a real VERDICT, and it failed -- because
# `window_has_escalation` (WINDOW = 12 logical lines) finds the escalation
# anyway in the simple shape, so the absorption is masked at the verdict level. Making it visible needs a boundary-crossing construction where the absorbed line falls outside that window; 89b2e140's author verified one, and I did not reproduce it rather than ship an assertion I had not confirmed. The branch_of-level claim above is the durable guard: it pins the defect itself
# instead of one downstream consequence of it.
