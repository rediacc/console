"""`rediacc_ci.quality.env_ast`: the shared parse and the pruned walk the three env-registry scanners stand on.

The pruning is only sound if it never drops a node a scanner would accept, so the cases below state it both ways: every node whose own source text carries a token is still walked (the positive control, on awkward shapes and on a slice of the real tree), and a tokenless tree walks nothing (the negative control, which proves the prune does prune).
"""

import ast
import gc
import subprocess
import weakref

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import env_ast

SHAPES = {
    "plain": 'import os\nx = os.environ.get("A")\ny = 1\n',
    "multi-line call": 'import os\nx = os.environ.get(\n    "A",\n    "d",\n)\n',
    "token on a later line of one expression": 'x = foo(\n    1,\n    2) or __import__("os").getenv("A")\n',
    "decorator carries the token": 'import os\n@dec(os.environ["A"])\n\n\ndef f():\n    pass\n',
    "nested in a class and a function": (
        'import os\nclass C:\n    def m(self):\n        if True:\n            return os.environ["A"]\n'
    ),
    "compare": 'import os\nok = "A" in os.environ\n',
    "assign target": 'import os\nos.environ["A"] = "1"\ndel os.environ["A"]\n',
    "carriage returns": 'import os\r\rx = os.environ.get("A")\r',
}


def _carrying(tree, source):
    """Every node whose own source segment holds a token, by the parser's own spans.

    The segment is cut from lines split ONCE (`ast.get_source_segment` re-splits the whole source per node, which is quadratic on a real module).
    """
    rows = source.encode("utf-8", "surrogateescape").splitlines(keepends=True)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.expr | ast.stmt):
            continue
        assert node.end_lineno is not None
        first, last = node.lineno - 1, node.end_lineno - 1
        if first == last:
            raw = rows[first][node.col_offset : node.end_col_offset]
        else:
            raw = (
                rows[first][node.col_offset :]
                + b"".join(rows[first + 1 : last])
                + rows[last][: node.end_col_offset]
            )
        if b"environ" in raw or b"getenv" in raw:
            out.append(node)
    return out


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_every_node_carrying_a_token_is_still_walked(name):
    source = SHAPES[name]
    tree = env_ast.parse(source)
    walked = {id(node) for node in env_ast.nodes(tree)}
    missing = [ast.dump(n)[:60] for n in _carrying(tree, source) if id(n) not in walked]
    assert not missing, "the pruned walk dropped %s" % missing
    assert walked, "a source with a token must walk at least the module"


def test_a_tokenless_tree_walks_nothing_but_all_nodes_still_sees_everything():
    tree = env_ast.parse("a = 1\nb = a + 2\n")
    assert env_ast.nodes(tree) == []
    assert not env_ast.may_read_env("a = 1\n")
    assert len(env_ast.all_nodes(tree)) == len(list(ast.walk(tree)))


def test_the_pruned_walk_is_a_subsequence_of_ast_walk_in_order():
    tree = env_ast.parse(SHAPES["nested in a class and a function"] + "z = 3\n")
    # `Load()` and its kin are one shared instance per tree, so they have no single rank.
    shared = ast.expr_context
    order = {id(n): i for i, n in enumerate(ast.walk(tree)) if not isinstance(n, shared)}
    ranks = [order[id(n)] for n in env_ast.nodes(tree) if not isinstance(n, shared)]
    assert ranks == sorted(ranks)
    assert len(ranks) < len(order), "the prune must actually drop the tokenless tail"


def test_a_putenv_is_invisible_to_the_pruned_walk_and_seen_by_all_nodes():
    tree = env_ast.parse("import os\nos.putenv('A', '1')\n")
    assert all(
        not (isinstance(n, ast.Attribute) and n.attr == "putenv") for n in env_ast.nodes(tree)
    )
    assert any(isinstance(n, ast.Attribute) and n.attr == "putenv" for n in env_ast.all_nodes(tree))


def test_imports_finds_nested_statements_and_nothing_else():
    tree = env_ast.parse(
        "import a\ndef f():\n    from b import c\n    try:\n        import d\n    except E:\n        import e\n"
    )
    names = [type(n).__name__ for n in env_ast.imports(tree)]
    assert names == ["Import", "ImportFrom", "Import", "Import"]


def test_a_tree_is_parsed_once_and_a_failure_is_never_cached():
    first = env_ast.parse("q = 1\n", "one.py")
    assert env_ast.parse("q = 1\n", "two.py") is first
    for filename in ("a.py", "b.py"):
        with pytest.raises(SyntaxError) as raised:
            env_ast.parse("def broken(:\n", filename)
        assert filename in str(raised.value), "each refusal names its own caller's file"


def test_a_tree_parsed_elsewhere_falls_back_to_the_full_walk():
    tree = ast.parse('import os\nx = os.environ.get("A")\n')
    assert env_ast.nodes(tree) == list(ast.walk(tree))


def test_the_prune_holds_on_a_slice_of_the_real_tree():
    """Positive control on real files: 150 token-bearing tracked modules, every carrying node walked."""
    root = paths.repo_root()
    listed = (
        subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", ".ci/rediacc_ci/*.py", ".claude/*.py"],
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    checked = 0
    for rel in sorted(p for p in listed if p.endswith(".py")):
        source = (root / rel).read_text(encoding="utf-8", errors="surrogateescape")
        if not env_ast.may_read_env(source):
            continue
        tree = env_ast.parse(source, rel)
        walked = {id(node) for node in env_ast.nodes(tree)}
        for node in _carrying(tree, source):
            assert id(node) in walked, "%s: %s dropped" % (rel, ast.dump(node)[:60])
        checked += 1
        if checked >= 150:
            break
    assert checked >= 50, (
        "only %d token-bearing modules found; the slice is not seeing the tree" % checked
    )


class _Cycle:
    """Garbage with a reference cycle, so only the cyclic collector can free it."""

    def __init__(self):
        self.me = self


def test_a_parse_does_not_freeze_unreachable_cycles():
    """`gc.freeze` moves every live object of the process to the permanent generation (e3578f81.1), so an unreachable cycle alive at a parse would never be collected. A cycle dropped before a fresh parse must be gone after it."""
    gc.collect()
    probe = weakref.ref(_Cycle())
    env_ast.parse("fresh_cycle_probe = %d\n" % id(probe))
    assert probe() is None, "the parse froze an unreachable cycle instead of collecting it"
    gc.collect()
    assert probe() is None
