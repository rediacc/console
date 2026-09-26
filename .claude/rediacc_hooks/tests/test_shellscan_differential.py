"""The proof for `rediacc_hooks.shellscan`: a differential against a frozen golden.

WHY A DIFFERENTIAL AND NOT A TEST SUITE. A suite written alongside a port tests what the porter understood. The thing that has to be preserved here is what the porter did NOT understand -- six rounds of bypass findings recorded only in the retired `command-scan.sh`'s comments, each one a command shape that beat an earlier version of that file. So the reference is not this
author's understanding of the problem: every case below is checked against a recorded answer and every field of the result is compared, not just a blocked/allowed boolean. A field that differs names itself and its input.

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

WHERE THE RECORDED ANSWER CAME FROM, since PLAN-retire-bash-oracles A3. Until then this file sourced the tracked bash original, `.claude/oracles/pre-bash/lib/command-scan.sh`, in one shared process and compared every case against it directly. A1 froze that same process's answers into `tests/goldens/shellscan.jsonl` over the FULL corpus, A2 pointed the comparison at that file,
and A3 deleted the oracle and the driver once the golden was proven to match. `test_scan_matches_golden`/`test_hook_init_matches_golden` below are now the only comparison.
"""

import pathlib
import re

import pytest

from rediacc_hooks import shellscan
from rediacc_hooks.tests import corpus, goldenio

VERBS = ("create", "merge", "ready", "edit")
FLAGS = ("admin", "auto", "body", "body-file", "draft")

ROOT = corpus.repo_root()

# A root that cannot resolve, so `hook_target_root`'s "git said no" branch is exercised on every case rather than only on the ones with a real `cd`.
ABSENT_ROOT = "/nonexistent-root-for-the-shellscan-differential"


def build_cases():
    """The corpus, harvested payloads first, then the labelled edge cases.

    Both are named, so a failing parametrisation says `harvest-207` or `edge-r44-quoted-absolute-shell` rather than an index into a list nobody can look up.
    """
    harvested, stats = corpus.harvest()
    cases = [("harvest-%03d" % i, cmd) for i, cmd in enumerate(harvested)]
    cases += [("edge-%s" % label, cmd) for label, cmd in corpus.EDGE_CASES]
    return cases, stats


CASES, HARVEST_STATS = build_cases()
JSON_CASES = list(corpus.JSON_PAYLOADS)


def python_fields(cmd):
    """One case's answer from the live port, field for field with the golden."""
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
    return {key: _detoken(value) for key, value in out.items()}


def python_init_fields(payload):
    state = shellscan.hook_init(payload)
    if state is None:
        return {"rc": "1", "cmd": "", "scan": ""}
    cmd, scan = state
    return {"rc": "0", "cmd": _detoken(cmd), "scan": _detoken(scan)}


def diff_fields(want, got, skip=("case",)):
    """Every field where the two disagree, as readable pairs."""
    keys = sorted(set(want) | set(got))
    diffs = []
    for key in keys:
        if key in skip:
            continue
        got_val = got.get(key, "<missing from port>")
        want_val = want.get(key, "<missing from golden>")
        if got_val != want_val:
            diffs.append((key, want_val, got_val))
    return diffs


def render(diffs, label, cmd):
    lines = ["%s diverged for %r" % (label, cmd)]
    for key, want, got in diffs:
        lines.append("  field %s" % key)
        lines.append("    golden %r" % want)
        lines.append("    python %r" % got)
    return "\n".join(lines)


# --------------------------------------------------------------------------- The corpus itself, before anything is compared against it ---------------------------------------------------------------------------


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

    Each predicate here is one of the six rounds. This is the control on the corpus: if a class disappears from `test-hooks.sh`, the differential goes on passing while no longer testing that round, and this is what says so.
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


# --------------------------------------------------------------------------- The differential ---------------------------------------------------------------------------
#
# AGAINST A FROZEN RECORD. Until PLAN-retire-bash-oracles A3 this section ran beside `test_scan_matches_bash`/`test_hook_init_matches_bash`, which forked `command-scan.sh` for real over the whole corpus every run; A1 froze that driver's answers into `goldens/shellscan.jsonl` over the FULL corpus, A2 pointed these two functions at it, and A3 deleted the driver and its two
# bash-side tests once the golden was proven to match. `regolden.py shellscan --reason '<why>'` re-freezes this file from the current port when a Rule T fix makes it diverge on purpose.

GOLDEN_PATH = goldenio.golden_path("shellscan")

# THE CHECKOUT PATH ITSELF, MADE INVISIBLE. `corpus._absolute_cd_cases` builds commands that `cd` into `ROOT` (and, when checked out, its `private/renet` submodule) by literal absolute path -- a different string on every checkout. That path does not stay confined to those two commands' text: any case whose `cd`/`-C` hint resolves to a git root (a same-tree relative `cd` resolves to "" and is unaffected, but a submodule hint like `cd private/renet` resolves via a real `git rev-parse --show-toplevel` to its absolute path) surfaces it too, in `troot`/`trootx`.
# So both the golden KEY (hashed from the command text) and every FIELD VALUE derived from a command are passed through this substitution before they are hashed, written or compared, making the golden -- and its lookup -- independent of where this checkout happens to sit. A submodule's path is `ROOT`-prefixed, so substituting `ROOT` alone also normalizes it.
REPO_TOKEN = "<REPO>"  # noqa: S105


def _detoken(text):
    if text is None:
        return text
    return text.replace(str(ROOT), REPO_TOKEN)


def cmd_key(label, cmd):
    return goldenio.case_key(label, _detoken(cmd))


def json_key(label, payload):
    return goldenio.case_key("json-" + label, _detoken(payload))


def _decode_record(record):
    # `intentional` records WHY a field moved (regolden.py's Rule T marker), not a field of the answer; comparing it made every declared delta a failure.
    return {k: goldenio.decode_field(v) for k, v in record.items() if k != "intentional"}


@pytest.mark.parametrize(("label", "cmd"), CASES, ids=[label for label, _ in CASES])
def test_scan_matches_golden(label, cmd):
    _header, silent, records = goldenio.read_golden(GOLDEN_PATH)
    key = cmd_key(label, cmd)
    want = goldenio.lookup(silent, records, key)
    assert want is not None, (
        "no golden record for %r (key %s) -- run regolden.py shellscan --reason '<why>'"
        % (label, key)
    )
    diffs = diff_fields(_decode_record(want), python_fields(cmd))
    assert not diffs, render(diffs, label, cmd)


@pytest.mark.parametrize(("label", "payload"), JSON_CASES, ids=[label for label, _ in JSON_CASES])
def test_hook_init_matches_golden(label, payload):
    _header, silent, records = goldenio.read_golden(GOLDEN_PATH)
    key = json_key(label, payload)
    want = goldenio.lookup(silent, records, key)
    assert want is not None, (
        "no golden record for json case %r (key %s) -- run regolden.py shellscan --reason '<why>'"
        % (label, key)
    )
    diffs = diff_fields(_decode_record(want), python_init_fields(payload))
    assert not diffs, render(diffs, label, payload)


def test_shellscan_golden_exists():
    """The one golden file this module reads must actually be there.

    `shellscan` has no per-guard split (it is one library, not 46 modules), so this is the shellscan half of `test_guards_differential.test_every_port_has_goldens`: a missing file would otherwise surface only as 416 confusing "no golden record" failures instead of one clear one.
    """
    assert GOLDEN_PATH.is_file(), (
        "%s is missing -- run regolden.py shellscan --reason '<why>' to freeze it" % GOLDEN_PATH
    )


def test_every_compared_field_actually_varies():
    """No field may be constant across the corpus.

    A comparison of two constants is a comparison that cannot fail, and a differential made of enough of them is green by construction. This is the control ON the differential: it re-derives every field over the whole corpus and refuses any that takes a single value. It found one -- the `target_root` field evaluated against an absent root was "" on all 385 cases -- which is why
    `corpus._absolute_cd_cases` exists.
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

    This is the planted defect, run every time rather than by hand: one branch of the port is disabled in a copy of the module and the comparison must catch it. `_strip_env_prefix` is the branch chosen because its finding is
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
