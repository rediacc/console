"""Parity of the name-shaped hash inputs (PLAN-ciquick-cpu W2.4): input-hash.ts and the push guard's twin.

A lock entry may declare `lists` (directories whose immediate tracked children it reads), `names` (globs whose matching tracked names it reads) and `refs` (refs whose commit it reads). The runner writes a carried gate's `filesHash` with those lines folded in, and block_unverified_push.py recomputes it at the pushed tree from the recorded `inputs`, so the two must build the same bytes or every such carry is refused (or worse, a moved input is admitted). The TS side is driven for real (`input-hash.ts --print-corpus HEAD` in a scratch repository), never mocked, and the Python side recomputes each gate from the inputs the TS side recorded.

Controls ride the same corpus: a new child of a listed directory moves the hash, an edit to a listed child's content does not, a new HEAD over the same tree moves a refs gate and nothing else, and a gate declaring none of the three records no new key and hashes exactly as before W2.4.
"""

import json
import shutil
import subprocess

import pytest
from rediacc_hooks.guards import block_unverified_push as G

from rediacc_ci import paths

ROOT = paths.repo_root()
TSX = ROOT / "node_modules" / ".bin" / "tsx"
INPUT_HASH = ROOT / "scripts" / "ci-runner" / "input-hash.ts"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not TSX.exists(),
    reason="node or node_modules/.bin/tsx missing: the TS side of the parity cannot run",
)

LOCK = [
    {"id": "g:plain", "run": "x", "gate": True, "paths": ["src/**"]},
    {"id": "g:whole", "run": "x", "gate": True},
    {"id": "g:gitlinkstar", "run": "x", "gate": True, "paths": ["private/x/**"]},
    {"id": "g:lists", "run": "x", "gate": True, "paths": ["other.txt"], "lists": ["src", ""]},
    {"id": "g:names", "run": "x", "gate": True, "names": ["src/**", "**/*.md"]},
    {"id": "g:refs", "run": "x", "gate": True, "paths": ["other.txt"], "refs": ["HEAD", "main"]},
    {
        "id": "g:all",
        "run": "x",
        "gate": True,
        "lists": ["private"],
        "names": ["*.txt"],
        "refs": ["HEAD"],
    },
]


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "src" / "deep").mkdir(parents=True)
    (r / "scripts" / "ci-runner").mkdir(parents=True)
    _git(r, "init", "-q", "--initial-branch=main")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    _git(r, "config", "commit.gpgsign", "false")
    (r / "src" / "a.ts").write_text("a\n", encoding="utf-8")
    (r / "src" / "é.ts").write_text("e\n", encoding="utf-8")
    (r / "src" / "deep" / "b.md").write_text("b\n", encoding="utf-8")
    (r / "other.txt").write_text("o\n", encoding="utf-8")
    (r / "package.json").write_text('{"scripts": {}}\n', encoding="utf-8")
    (r / "scripts" / "ci-runner" / "gates.lock.json").write_text(json.dumps(LOCK), encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "update-index", "--add", "--cacheinfo", "160000,%s,private/x" % ("a" * 40))
    _git(r, "commit", "-q", "-m", "one")
    return r


def _corpus(repo):
    proc = subprocess.run(
        [str(TSX), str(INPUT_HASH), "--print-corpus", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"--print-corpus rc={proc.returncode}\nstderr:\n{proc.stderr}"
    corpus = json.loads(proc.stdout)
    assert set(corpus) == {e["id"] for e in LOCK}, f"the corpus misses gates: {sorted(corpus)}"
    return corpus


def _python_files_hash(repo, inputs):
    entries = G.v2_ls_tree(str(repo), _git(repo, "rev-parse", "HEAD^{tree}"))
    assert entries, "v2_ls_tree read nothing: the recomputation would hash an empty tree"
    lines = G.v2_input_lines(entries, inputs["globs"], inputs["files"])
    extras, unresolved = G.v2_extra_lines(
        entries,
        inputs.get("lists", []),
        inputs.get("names", []),
        inputs.get("refs", []),
        root=str(repo),
    )
    assert unresolved is None, unresolved
    return G.v2_files_hash(lines, extras)


def _assert_parity(repo, corpus):
    for gid, row in corpus.items():
        assert row["reason"] is None, f"{gid} is uncarriable: {row['reason']}"
        assert _python_files_hash(repo, row["inputs"]) == row["filesHash"], (
            f"filesHash differs between input-hash.ts and the guard for {gid}: inputs {row['inputs']}"
        )


def test_every_gate_hashes_alike_in_both_readers(repo):
    corpus = _corpus(repo)
    _assert_parity(repo, corpus)
    assert corpus["g:lists"]["inputs"]["lists"] == ["src", ""]
    assert corpus["g:refs"]["inputs"]["refs"] == ["HEAD", "main"]


def test_a_gate_without_the_fields_keeps_the_pre_w24_bytes(repo):
    corpus = _corpus(repo)
    for gid in ("g:plain", "g:whole", "g:gitlinkstar"):
        inputs = corpus[gid]["inputs"]
        assert not {"lists", "names", "refs"} & set(inputs), f"{gid} recorded a new key: {inputs}"
        entries = G.v2_ls_tree(str(repo), _git(repo, "rev-parse", "HEAD^{tree}"))
        old = G.v2_files_hash(G.v2_input_lines(entries, inputs["globs"], inputs["files"]))
        assert corpus[gid]["filesHash"] == old, f"{gid} moved off the pre-W2.4 preimage"


def test_a_gitlink_star_glob_reaches_the_gitlink_in_both_readers(repo):
    corpus = _corpus(repo)
    whole_minus = G.v2_files_hash([])
    assert corpus["g:gitlinkstar"]["filesHash"] != whole_minus, (
        "the TS side saw no gitlink for private/x/**: the control cannot discriminate"
    )
    assert (
        _python_files_hash(repo, corpus["g:gitlinkstar"]["inputs"])
        == corpus["g:gitlinkstar"]["filesHash"]
    )


def test_controls_move_exactly_the_gates_they_should(repo):
    c0 = _corpus(repo)
    # A new child of a listed directory.
    (repo / "src" / "new.ts").write_text("n\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "child")
    c1 = _corpus(repo)
    _assert_parity(repo, c1)
    assert c1["g:lists"]["filesHash"] != c0["g:lists"]["filesHash"], (
        "a new listed child must move lists"
    )
    assert c1["g:names"]["filesHash"] != c0["g:names"]["filesHash"], (
        "a new names match must move names"
    )
    # An edit to a listed child's content.
    (repo / "src" / "new.ts").write_text("n2\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "edit")
    c2 = _corpus(repo)
    _assert_parity(repo, c2)
    assert c2["g:lists"]["filesHash"] == c1["g:lists"]["filesHash"], (
        "a content edit must not move lists"
    )
    assert c2["g:names"]["filesHash"] == c1["g:names"]["filesHash"], (
        "a content edit must not move names"
    )
    assert c2["g:plain"]["filesHash"] != c1["g:plain"]["filesHash"], (
        "CONTROL: it moves a content reader"
    )
    # A new HEAD over the same tree.
    _git(repo, "commit", "-q", "--allow-empty", "-m", "same tree")
    c3 = _corpus(repo)
    _assert_parity(repo, c3)
    assert c3["g:refs"]["filesHash"] != c2["g:refs"]["filesHash"], (
        "a new HEAD must move a refs gate"
    )
    for gid in ("g:plain", "g:whole", "g:lists", "g:names"):
        assert c3[gid]["filesHash"] == c2[gid]["filesHash"], f"a new HEAD must not move {gid}"


def test_an_unresolved_ref_is_named_by_both_readers(repo):
    lock = [
        {
            "id": "g:noref",
            "run": "x",
            "gate": True,
            "paths": ["other.txt"],
            "refs": ["refs/heads/nope"],
        }
    ]
    (repo / "scripts" / "ci-runner" / "gates.lock.json").write_text(
        json.dumps(lock), encoding="utf-8"
    )
    _git(repo, "commit", "-q", "-am", "noref")
    proc = subprocess.run(
        [str(TSX), str(INPUT_HASH), "--print-corpus", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    row = json.loads(proc.stdout)["g:noref"]
    assert row["reason"] == "ref-unresolved:refs/heads/nope", row
    assert row["inputHash"] is None, row
    entries = G.v2_ls_tree(str(repo), _git(repo, "rev-parse", "HEAD^{tree}"))
    assert (
        G.v2_extra_lines(entries, refs=["refs/heads/nope"], root=str(repo))[1] == "refs/heads/nope"
    )
