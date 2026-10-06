"""Parity of the incremental receipt's hash contract: scripts/ci-runner/input-hash.ts and the pre-push guard.

PLAN-fast-loop box F4. The runner (TypeScript) writes a v2 receipt whose carried entries carry `defHash` and `filesHash`; the guard (Python) recomputes both at the pushed tree. Two implementations of one contract agree only if something runs both on one corpus, which is this file. The TS side is driven for real (`--print-corpus HEAD`), never mocked.
"""

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
# `pythonpath` in pyproject.toml carries `.ci` only; the guard lives under `.claude`.
sys.path.insert(0, str(ROOT / ".claude"))

from rediacc_hooks.guards import block_unverified_push as G  # noqa: E402

LOCK = ROOT / "scripts/ci-runner/gates.lock.json"
EXEMPT = ROOT / ".ci/policy/carry-exempt.json"
MIN_REASON = 80
MIN_COMPARED = 10
FORBIDDEN = ("?", "[", "{")

# Skip ONLY when the toolchain to run the TS side is absent; a failure of the TS side itself is a failure here.
needs_node = pytest.mark.skipif(
    shutil.which("npx") is None or shutil.which("node") is None,
    reason="npx/node not installed: the TS side of the parity cannot run",
)


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def _head_tree():
    return _git("rev-parse", "HEAD^{tree}").strip()


def _lock():
    return {e["id"]: e for e in json.loads(_git("show", "HEAD:scripts/ci-runner/gates.lock.json"))}


def _scripts_at_head():
    return json.loads(_git("show", "HEAD:package.json")).get("scripts", {})


@pytest.fixture(scope="module")
def corpus():
    r = subprocess.run(
        ["npx", "tsx", "scripts/ci-runner/input-hash.ts", "--print-corpus", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, f"--print-corpus rc={r.returncode}\nstderr:\n{r.stderr}"
    return json.loads(r.stdout)


@needs_node
def test_defhash_and_fileshash_equal_ts(corpus):
    lock = _lock()
    tree = _head_tree()
    entries = G.v2_ls_tree(str(ROOT), tree)
    compared = 0
    for gid, row in corpus.items():
        if row["inputHash"] is None:
            continue
        inputs = row["inputs"]
        scripts = {n: _scripts_at_head()[n] for n in inputs["scripts"]}
        assert G.v2_def_hash(lock[gid], scripts) == row["defHash"], f"defHash differs for {gid}"
        lines = G.v2_input_lines(entries, inputs["globs"], inputs["files"])
        assert G.v2_files_hash(lines) == row["filesHash"], f"filesHash differs for {gid}"
        compared += 1
    assert compared >= MIN_COMPARED, f"only {compared} entries compared; the parity is vacuous"


@needs_node
def test_forbidden_glob_chars_make_gate_non_carriable(corpus):

    for gid, entry in _lock().items():
        bad = [p for p in entry.get("paths") or [] if any(c in p for c in FORBIDDEN)]
        if not bad:
            continue
        assert corpus[gid]["inputHash"] is None, f"{gid} carries with forbidden glob {bad}"
        assert corpus[gid]["reason"] == "forbidden-glob", f"{gid}: {corpus[gid]['reason']}"


def test_exempt_file_shape_and_reasons():
    doc = json.loads(EXEMPT.read_text(encoding="utf-8"))
    assert doc["schema"] == 1
    ids = [e["id"] for e in doc["exempt"]]
    assert ids, "an empty exempt list means the file lost its entries"
    assert len(ids) == len(set(ids)), "duplicate exempt id"
    lock = _lock()
    for e in doc["exempt"]:
        assert e["id"] in lock, f"exempt id {e['id']} is not in gates.lock.json"
        assert len(e["reason"]) >= MIN_REASON, f"{e['id']}: reason shorter than {MIN_REASON}"


@needs_node
def test_exempt_ids_are_uncarriable_in_ts(corpus):
    for e in json.loads(EXEMPT.read_text(encoding="utf-8"))["exempt"]:
        row = corpus[e["id"]]
        assert row["inputHash"] is None, f"{e['id']} still carries"
        assert row["reason"] == "exempt", f"{e['id']}: reason is {row['reason']!r}, not 'exempt'"


# (glob, path, expected). `**` crosses `/`, `*` does not, everything else is literal.
GLOB_CASES = [
    ("src/**", "src/a.ts", True),
    ("src/**", "src/deep/b.ts", True),
    ("src/*.ts", "src/a.ts", True),
    ("src/*.ts", "src/deep/b.ts", False),
    ("src/*", "src/deep/b.ts", False),
    ("**/package-lock.json", "a/b/package-lock.json", True),
    ("src/a.ts", "src/aXts", False),
    ("a(b).ts", "a(b).ts", True),
    ("a+b.ts", "aab.ts", False),
    ("a+b.ts", "a+b.ts", True),
    ("private/account", "private/account", True),
    ("private/account", "private/account2", False),
    ("**/*.sh", "run.sh", False),
    ("**/*.sh", "x/run.sh", True),
    (".ci/**", ".ci/a/b/c.py", True),
    ("pyproject.toml", "sub/pyproject.toml", False),
]


@pytest.mark.parametrize(("glob", "path", "expected"), GLOB_CASES)
def test_glob_grammar_python(glob, path, expected):
    assert G.v2_match_glob(glob, path) is expected


@needs_node
def test_glob_grammar_ts_equals_python():
    script = (
        "import { matchGlob } from './scripts/ci-runner/input-hash.ts';"
        f"const cases = {json.dumps([[g, p] for g, p, _ in GLOB_CASES])};"
        "process.stdout.write(JSON.stringify(cases.map(([g, p]) => matchGlob(g, p))));"
    )
    r = subprocess.run(
        ["npx", "tsx", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert r.returncode == 0, f"tsx rc={r.returncode}\nstderr:\n{r.stderr}"
    ts = json.loads(r.stdout)
    assert len(ts) == len(GLOB_CASES)
    for (g, p, expected), got in zip(GLOB_CASES, ts, strict=True):
        assert got is expected, f"TS matchGlob({g!r}, {p!r}) = {got}, expected {expected}"
