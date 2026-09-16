"""The proof for `rediacc_hooks.shellscan`: a differential against the bash.

WHY A DIFFERENTIAL AND NOT A TEST SUITE. A suite written alongside a port
tests what the porter understood. The thing that has to be preserved here is
what the porter did NOT understand -- six rounds of bypass findings recorded
only in `.claude/hooks/pre-bash/lib/command-scan.sh`'s comments, each one a
command shape that beat an earlier version of that file. So the oracle is the
bash itself: every case below is fed to BOTH implementations and every field
of the result is compared, not just a blocked/allowed boolean. A field that
differs names itself and its input.

WHAT IS COMPARED, per command:
  * the raw stdout of each of the three filters (`_hook_strip_heredocs`,
    `_hook_strip_env_prefix`, `_hook_wrapper_payload`), because a difference
    there is a difference the composed scan target can hide;
  * `hook_scan_target`'s raw stdout, byte for byte, trailing newline included;
  * for four verbs (create, merge, ready, edit): the command-position match,
    the segment split, the PR selector and the resolved repo;
  * for five flags: `hook_flag_present`;
  * `hook_target_root` against the real repo root AND against a root that does
    not exist, since its two branches differ only in what git answers.

THE BASH SIDE RUNS THE REAL FILE. `command-scan.sh` is sourced, never copied
and never modified: a differential against a transcribed copy of the oracle
proves the transcription, not the port. It is read-only here.

ONE BASH PROCESS FOR THE WHOLE CORPUS. Each case drives roughly fifty forks
(awk, sed, grep, tr and git), so a subprocess per case would spend its life in
`fork`. The driver below loops inside one shell and frames its results with
the two ASCII control characters that exist for exactly this (0x1f between a
field name and its value, 0x1e between fields); `corpus.harvest` drops any
payload containing either, so the frame cannot be forged by the input.
"""

import ast
import json
import os
import pathlib
import re
import subprocess
import sys
import tokenize

import pytest

from rediacc_hooks import shellscan
from rediacc_hooks.tests import corpus

US = "\x1f"
RS = "\x1e"

VERBS = ("create", "merge", "ready", "edit")
FLAGS = ("admin", "auto", "body", "body-file", "draft")

ROOT = corpus.repo_root()
ARTIFACT_DIR = pathlib.Path(__file__).resolve().parent / ".artifacts"

# A root that cannot resolve, so `hook_target_root`'s "git said no" branch is
# exercised on every case rather than only on the ones with a real `cd`.
ABSENT_ROOT = "/nonexistent-root-for-the-shellscan-differential"

# The driver. It is a string rather than a `.sh` file in the tree on purpose:
# this workstream moves `.claude` to Python, and a second language checked in
# beside the port would be the thing the language gate exists to refuse. A
# fixture written to a temporary directory is not a second language in the
# tree, and it keeps the driver next to the comparison it feeds.
DRIVER = r"""#!/usr/bin/env bash
LIB="$1"; IN_DIR="$2"; ROOT="$3"; TMP="$4"; ABSENT="$5"
# shellcheck source=/dev/null
. "$LIB"
US=$'\037'
k() { printf '%s%s' "$1" "$US"; }
e() { printf '\036'; }
for path in "$IN_DIR"/cmd-*; do
    CMD=""
    IFS= read -r -d '' CMD < "$path" || true
    k case; printf '%s' "${path##*/}"; e
    k heredocs; printf '%s' "$CMD" | _hook_strip_heredocs; e
    k envprefix; printf '%s' "$CMD" | _hook_strip_env_prefix; e
    k wrapper; printf '%s' "$CMD" | tr '\n' ' ' | _hook_wrapper_payload; e
    hook_scan_target "$CMD" > "$TMP/scan"
    k scan; cat "$TMP/scan"; e
    SCAN=$(<"$TMP/scan")
    for verb in create merge ready edit; do
        k "pos:$verb"
        if hook_gh_pr_at_command_pos "$SCAN" "$verb"; then printf 0; else printf 1; fi
        e
        hook_gh_pr_segment "$SCAN" "$verb" > "$TMP/seg"
        k "seg:$verb"; cat "$TMP/seg"; e
        SEG=$(<"$TMP/seg")
        k "sel:$verb"; hook_pr_selector "$SEG" "$verb"; e
        k "repo:$verb"; hook_target_repo "$SEG" "$SCAN" ""; e
    done
    hook_gh_pr_segment "$SCAN" merge > "$TMP/seg"
    k repocwd; hook_target_repo "$(<"$TMP/seg")" "$SCAN" "$ROOT"; e
    for flag in admin auto body body-file draft; do
        k "flag:$flag"
        if hook_flag_present "$CMD" "$flag"; then printf 0; else printf 1; fi
        e
    done
    k troot; hook_target_root "$SCAN" "$ROOT"; e
    k trootx; hook_target_root "$SCAN" "$ABSENT"; e
done
for path in "$IN_DIR"/json-*; do
    CMD=""
    SCAN=""
    k case; printf '%s' "${path##*/}"; e
    if hook_init < "$path"; then k rc; printf 0; else k rc; printf 1; fi
    e
    k cmd; printf '%s' "$CMD"; e
    k scan; printf '%s' "$SCAN"; e
done
"""


def build_cases():
    """The corpus, in the order the driver will see it.

    Harvested payloads first, then the labelled edge cases. Both are named, so
    a failing parametrisation says `harvest-207` or
    `edge-r44-quoted-absolute-shell` rather than an index into a list nobody
    can look up.
    """
    harvested, stats = corpus.harvest()
    cases = [("harvest-%03d" % i, cmd) for i, cmd in enumerate(harvested)]
    cases += [("edge-%s" % label, cmd) for label, cmd in corpus.EDGE_CASES]
    return cases, stats


CASES, HARVEST_STATS = build_cases()
JSON_CASES = list(corpus.JSON_PAYLOADS)


def python_fields(cmd):
    """The Python side of one case, field for field with the driver above."""
    out = {}
    out["heredocs"] = shellscan._strip_heredocs(cmd)
    out["envprefix"] = shellscan._strip_env_prefix(cmd)
    out["wrapper"] = shellscan._wrapper_payload(cmd.replace("\n", " "))
    scan_raw = shellscan.scan_target(cmd)
    out["scan"] = scan_raw
    scan = scan_raw.rstrip("\n")
    for verb in VERBS:
        out["pos:%s" % verb] = "0" if shellscan.gh_pr_at_command_pos(scan, verb) else "1"
        seg_raw = shellscan.gh_pr_segment(scan, verb)
        out["seg:%s" % verb] = seg_raw
        seg = seg_raw.rstrip("\n")
        out["sel:%s" % verb] = shellscan.pr_selector(seg, verb)
        out["repo:%s" % verb] = shellscan.target_repo(seg, scan, "")
    merge_seg = shellscan.gh_pr_segment(scan, "merge").rstrip("\n")
    out["repocwd"] = shellscan.target_repo(merge_seg, scan, str(ROOT))
    for flag in FLAGS:
        out["flag:%s" % flag] = "0" if shellscan.flag_present(cmd, flag) else "1"
    out["troot"] = shellscan.target_root(scan, str(ROOT))
    out["trootx"] = shellscan.target_root(scan, ABSENT_ROOT)
    return out


def python_init_fields(payload):
    state = shellscan.hook_init(payload)
    if state is None:
        return {"rc": "1", "cmd": "", "scan": ""}
    cmd, scan = state
    return {"rc": "0", "cmd": cmd, "scan": scan}


def parse_stream(text):
    """Un-frame the driver's output into a list of per-case field dicts."""
    records = []
    current = None
    for chunk in text.split(RS):
        if chunk == "":
            continue
        key, _, value = chunk.partition(US)
        if key == "case":
            current = {"case": value}
            records.append(current)
            continue
        if current is None:
            msg = "field %r arrived before any case marker" % key
            raise AssertionError(msg)
        current[key] = value
    return records


# EVERY XDIST WORKER REBUILDS A SESSION FIXTURE, because "session" is scoped to a
# PROCESS and xdist workers ARE processes. The `bash_results` fixture below forks
# about 12,000 subshells across 416 input files, and this module's tests are otherwise pure in-process comparison -- so
# without this declaration its cases scatter across every worker and each one pays
# the full driver again.
#
# Measured 2026-09-07: this file and test_shellscan_differential.py together serve
# 6446 of 8968 tests (72 percent of the corpus). At `-n 8` that is roughly 240,000
# forks of duplicated setup before a single one of those tests does useful work,
# which is why the suite is 1.64x SLOWER under 8 workers than serial (619.17s vs
# 1013.59s on a quiesced box).
#
# The group pins all of this module's tests to ONE worker, so the fixture is built
# once. It is INERT without `--dist loadgroup`, so it changes nothing today.
# A SEPARATE GROUP FROM test_guards_differential.py, deliberately. Sharing one
# would pin all 6446 tests of both modules to a SINGLE worker -- trading 8x
# fixture duplication for serialising 72 percent of the corpus onto one core,
# which is the same mistake in the other direction. Two groups let the two
# drivers build on two workers concurrently while each is still built once.
XDIST_GROUP = "hooks-shellscan"


@pytest.fixture(scope="session")
def bash_results(tmp_path_factory):
    """Run the real `command-scan.sh` over the whole corpus, once."""
    work = tmp_path_factory.mktemp("shellscan-differential")
    inputs = work / "in"
    inputs.mkdir()
    scratch = work / "tmp"
    scratch.mkdir()
    for i, (_, cmd) in enumerate(CASES):
        (inputs / ("cmd-%05d" % i)).write_bytes(cmd.encode("utf-8"))
    for i, (_, payload) in enumerate(JSON_CASES):
        (inputs / ("json-%05d" % i)).write_bytes(payload.encode("utf-8"))
    driver = work / "driver.bash"
    driver.write_text(DRIVER, encoding="utf-8")
    proc = subprocess.run(
        [
            "bash",
            str(driver),
            str(corpus.LIB),
            str(inputs),
            str(ROOT),
            str(scratch),
            ABSENT_ROOT,
        ],
        capture_output=True,
        check=False,
        # BYTES, then decoded by hand. `encoding=` puts the pipe in text mode,
        # and text mode translates universal newlines: a lone \r in a command
        # comes back as \n. That is not a difference between the two
        # implementations, it is the harness rewriting the oracle's answer --
        # and it was found by this differential failing on a \r case, which is
        # the reason the corpus carries one.
        # An inherited CLAUDE_PROJECT_DIR or GIT_INDEX_FILE would reach git
        # here; the lib reads neither, but a differential that depends on the
        # caller's environment is one that passes for the wrong reason.
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/")},
    )
    stdout = proc.stdout.decode("utf-8", "surrogateescape")
    stderr = proc.stderr.decode("utf-8", "surrogateescape")
    assert proc.returncode == 0, "driver failed: %s" % stderr
    records = parse_stream(stdout)
    cmd_records = [r for r in records if r["case"].startswith("cmd-")]
    json_records = [r for r in records if r["case"].startswith("json-")]
    assert len(cmd_records) == len(CASES), (
        "driver returned %d command records for %d cases -- the frame is out of step, "
        "which invalidates every comparison below" % (len(cmd_records), len(CASES))
    )
    assert len(json_records) == len(JSON_CASES)
    return {"commands": cmd_records, "json": json_records, "stderr": stderr}


def diff_fields(bash_side, python_side, skip=("case",)):
    """Every field where the two disagree, as readable pairs."""
    keys = sorted(set(bash_side) | set(python_side))
    diffs = []
    for key in keys:
        if key in skip:
            continue
        got = python_side.get(key, "<missing from port>")
        want = bash_side.get(key, "<missing from bash>")
        if got != want:
            diffs.append((key, want, got))
    return diffs


def render(diffs, label, cmd):
    lines = ["%s diverged for %r" % (label, cmd)]
    for key, want, got in diffs:
        lines.append("  field %s" % key)
        lines.append("    bash   %r" % want)
        lines.append("    python %r" % got)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The corpus itself, before anything is compared against it
# ---------------------------------------------------------------------------


def test_corpus_is_real_and_large_enough():
    assert HARVEST_STATS["distinct"] >= corpus.MIN_COMMANDS, (
        "only %d distinct payloads recovered from %s; below %d the differential is "
        "proving the port against a handful of strings"
        % (HARVEST_STATS["distinct"], HARVEST_STATS["source"], corpus.MIN_COMMANDS)
    )
    ratio = HARVEST_STATS["recovered"] / HARVEST_STATS["call_sites"]
    assert ratio >= corpus.HARVEST_RATIO_FLOOR, (
        "recovered %d of %d bash_json call sites (%.2f); the unquoting parser has "
        "stopped understanding the suite"
        % (HARVEST_STATS["recovered"], HARVEST_STATS["call_sites"], ratio)
    )


def test_corpus_covers_the_shapes_the_findings_name():
    """A large corpus of `ls -la` would still be a large corpus.

    Each predicate here is one of the six rounds. This is the control on the
    corpus: if a class disappears from `test-hooks.sh`, the differential goes
    on passing while no longer testing that round, and this is what says so.
    """
    commands = [cmd for _, cmd in CASES]
    classes = {
        "wrapper -c": lambda c: re.search(r"\b(sh|bash|dash|zsh|ash|ksh)\b[^\n]*-c", c),
        "eval": lambda c: re.search(r"\beval\b", c),
        "heredoc": lambda c: "<<" in c,
        "env prefix": lambda c: re.search(r"(^|[;&|(])\s*[A-Za-z_][A-Za-z0-9_]*=\S*\s+\S", c),
        "gh pr": lambda c: re.search(r"gh\s+pr\s+", c),
        "path-qualified shell": lambda c: re.search(r"[./][a-z/]*\b(sh|bash)\b[^\n]*-c", c),
        "multi-line": lambda c: "\n" in c,
        "quoted prose": lambda c: '"' in c or "'" in c,
        "cd or -C": lambda c: re.search(r"(^|[;&|(])\s*cd\s|-C\s", c),
    }
    counts = {name: sum(1 for c in commands if pred(c)) for name, pred in classes.items()}
    missing = [name for name, n in counts.items() if n == 0]
    assert not missing, "corpus no longer covers: %s (counts %r)" % (missing, counts)


# ---------------------------------------------------------------------------
# The differential
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "cmd"), CASES, ids=[label for label, _ in CASES])
def test_scan_matches_bash(bash_results, label, cmd):
    index = next(i for i, (name, _) in enumerate(CASES) if name == label)
    bash_side = bash_results["commands"][index]
    assert bash_side["case"] == "cmd-%05d" % index
    diffs = diff_fields(bash_side, python_fields(cmd))
    assert not diffs, render(diffs, label, cmd)


@pytest.mark.parametrize(("label", "payload"), JSON_CASES, ids=[label for label, _ in JSON_CASES])
def test_hook_init_matches_bash(bash_results, label, payload):
    index = next(i for i, (name, _) in enumerate(JSON_CASES) if name == label)
    bash_side = bash_results["json"][index]
    diffs = diff_fields(bash_side, python_init_fields(payload))
    assert not diffs, render(diffs, label, payload)


def test_every_compared_field_actually_varies():
    """No field may be constant across the corpus.

    A comparison of two constants is a comparison that cannot fail, and a
    differential made of enough of them is green by construction. This is the
    control ON the differential: it re-derives every field over the whole
    corpus and refuses any that takes a single value. It found one -- the
    `target_root` field evaluated against an absent root was "" on all 385
    cases -- which is why `corpus._absolute_cd_cases` exists.
    """
    seen = {}
    for _, cmd in CASES:
        for key, value in python_fields(cmd).items():
            seen.setdefault(key, set()).add(value)
    constant = sorted(key for key, values in seen.items() if len(values) < 2)
    assert not constant, (
        "these fields take one value across all %d cases, so comparing them proves "
        "nothing: %s" % (len(CASES), constant)
    )


def test_the_differential_can_fail(tmp_path):
    """A differential that has never failed is not evidence.

    This is the planted defect, run every time rather than by hand: one branch
    of the port is disabled in a copy of the module and the comparison must
    catch it. `_strip_env_prefix` is the branch chosen because its finding is
    the most expensive one in the file -- a single `FOO=bar ` token that
    turned five guards from refusing to permitting.
    """
    source = pathlib.Path(shellscan.__file__).read_text(encoding="utf-8")
    broken_src = source.replace(
        '            line, count = _ENV_PREFIX.subn(r"\\1\\2", line)',
        "            line, count = line, 0",
    )
    assert broken_src != source, "the planted defect no longer applies to the port"
    broken_path = tmp_path / "broken_shellscan.py"
    broken_path.write_text(broken_src, encoding="utf-8")
    namespace = {"__name__": "broken_shellscan", "__file__": str(broken_path)}
    exec(compile(broken_src, str(broken_path), "exec"), namespace)  # noqa: S102
    probe = "FOO=bar git commit -m x"
    assert namespace["scan_target"](probe) != shellscan.scan_target(probe), (
        "disabling the env-prefix strip changed nothing, so the differential's green "
        "does not depend on that branch being right"
    )


# ---------------------------------------------------------------------------
# Section 5c of the driver contract: comment archaeology
# ---------------------------------------------------------------------------

# The ratio the contract sets. Docstrings count as comments; a module
# docstring is the natural home for a file-header block.
COMMENT_RATIO_FLOOR = 0.90


def bash_comment_bytes(path):
    """Whole-line comments, with their newline. The shebang is not prose."""
    total = 0
    lines = 0
    for line in path.read_text(encoding="utf-8").split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#") and not stripped.startswith("#!"):
            total += len(line.encode("utf-8")) + 1
            lines += 1
    return total, lines


def python_comment_bytes(path):
    """`#` comments plus docstrings, counted CONSERVATIVELY.

    A comment token is counted from its `#` (its indentation is not counted,
    though the bash side's is), and a docstring from its opening quote. The
    asymmetry is deliberate and in the strict direction: the port is credited
    with less than it has, so a ratio that clears the floor clears it honestly.
    """
    text = path.read_text(encoding="utf-8")
    total = 0
    count = 0
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type == tokenize.COMMENT:
                total += len(token.string.encode("utf-8")) + 1
                count += 1
    tree = ast.parse(text)
    for node in ast.walk(tree):
        # `.body` is a LIST on a module, function or class, and a single
        # expression on an IfExp or a lambda. Walking every node and assuming
        # the first shape raises TypeError on the second, which is how this
        # was found.
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for child in body:
            if (
                isinstance(child, ast.Expr)
                and isinstance(child.value, ast.Constant)
                and isinstance(child.value.value, str)
            ):
                segment = ast.get_source_segment(text, child)
                if segment:
                    total += len(segment.encode("utf-8")) + 1
                    count += 1
    return total, count


# Every line of the original naming a DATE, an ISSUE, a REVIEW ROUND or a
# FILE:LINE. The ratio cannot see these: prose can be padded while the one
# paragraph that names a dated incident is dropped, and that paragraph is the
# only record of why a line is shaped the way it is. So they are extracted
# mechanically and each must survive somewhere in the port.
ARCHAEOLOGY = (
    r"\b20\d\d-\d\d-\d\d\b",
    r"#\d+",
    r"[Rr]ounds? ?-?\d+(-\d+)?",
    r"\b[\w./-]+\.sh:\d+(-\d+)?\b",
)


def archaeology_tokens(text):
    found = []
    for pattern in ARCHAEOLOGY:
        for m in re.finditer(pattern, text):
            token = m.group(0)
            if token not in found:
                found.append(token)
    return found


def test_comment_ratio_and_archaeology(bash_results):
    """Write the differential artifact, and refuse a port that lost the prose."""
    port = pathlib.Path(shellscan.__file__)
    bash_bytes, bash_lines = bash_comment_bytes(corpus.LIB)
    py_bytes, py_count = python_comment_bytes(port)
    ratio = py_bytes / bash_bytes

    bash_text = corpus.LIB.read_text(encoding="utf-8")
    port_text = port.read_text(encoding="utf-8")
    tokens = archaeology_tokens(bash_text)
    lost = [t for t in tokens if t not in port_text]

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    artifact = {
        "original": str(corpus.LIB.relative_to(ROOT)),
        "port": str(port.relative_to(ROOT)),
        "original_comment_bytes": bash_bytes,
        "original_comment_lines": bash_lines,
        "port_comment_bytes": py_bytes,
        "port_comment_units": py_count,
        "comment_ratio": round(ratio, 4),
        "comment_ratio_floor": COMMENT_RATIO_FLOOR,
        "archaeology_tokens": tokens,
        "archaeology_lost": lost,
        "corpus": HARVEST_STATS,
        "corpus_edge_cases": len(corpus.EDGE_CASES),
        "corpus_total_commands": len(CASES),
        "json_payloads": len(JSON_CASES),
        "fields_per_command": len(python_fields("gh pr merge 1 --admin")),
        "bash_driver_stderr": bash_results["stderr"][:2000],
    }
    (ARTIFACT_DIR / "shellscan-differential.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(artifact, indent=2, sort_keys=True), file=sys.stderr)

    assert ratio >= COMMENT_RATIO_FLOOR, (
        "port carries %d comment bytes against the original's %d (%.3f), floor %.2f"
        % (py_bytes, bash_bytes, ratio, COMMENT_RATIO_FLOOR)
    )
    assert not lost, (
        "the port dropped the dated evidence in: %s -- the ratio cannot see this, "
        "which is why it is checked separately" % lost
    )
